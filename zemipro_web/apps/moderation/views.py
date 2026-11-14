"""07.5: report intake, moderator queue, decisions and one appeal."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponseBadRequest
from django.shortcuts import render, redirect
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.accounts.models import User
from .case_services import (
    ComplaintConflict, decide_appeal, decide_complaint, file_appeal,
    submit_complaint, visible_target,
)
from .forms import ComplaintForm
from .models import Complaint, ComplaintAppeal


def _target_ids(request):
    query = request.GET
    keys = ('user', 'order', 'rating', 'message')
    specified = [key for key in keys if key in query]
    if len(specified) != 1:
        raise Http404
    try:
        identifier = int(query[specified[0]])
        if identifier < 1 or identifier >= 2**63:
            raise ValueError
    except (TypeError, ValueError):
        raise Http404 from None
    result = {
        'target_user_id': None, 'target_order_id': None,
        'target_rating_id': None, 'target_message_id': None,
    }
    result['target_' + specified[0] + '_id'] = identifier
    return result


@login_required
@never_cache
def complaint_create_view(request):
    target_ids = _target_ids(request)
    try:
        target = visible_target(actor=request.user, **target_ids)
    except PermissionDenied:
        raise Http404 from None
    if request.method == 'POST':
        form = ComplaintForm(request.POST)
        if form.is_valid():
            try:
                submit_complaint(
                    actor=request.user,
                    reason=form.cleaned_data['reason'],
                    message=form.cleaned_data['message'], **target_ids,
                )
            except ComplaintConflict as exc:
                form.add_error(None, str(exc))
            except PermissionDenied:
                raise Http404 from None
            else:
                messages.success(request, _('Жалоба отправлена. Спасибо!'))
                return redirect('moderation:my_complaints')
    elif request.method == 'GET':
        form = ComplaintForm()
    else:
        raise Http404
    return render(request, 'moderation/complaint_create.html', {
        'form': form, 'target_user': target.get('target_user'),
        'target_order': target.get('target_order'),
        'target_rating': target.get('target_rating'),
        'target_message': target.get('target_message'),
    })


def _staff(actor):
    stored = User.objects.filter(
        pk=getattr(actor, 'pk', None), is_staff=True,
        is_active=True, is_blocked=False,
        email_verification_required=False,
    ).first()
    if stored is None or not stored.has_perm('moderation.review_complaints'):
        raise PermissionDenied('Moderator only.')
    return stored


@login_required
@never_cache
def moderator_queue_view(request):
    _staff(request.user)
    return render(request, 'moderation/queue.html', {
        'complaints': Complaint.objects.select_related(
            'target_order',
        ).filter(status=Complaint.Status.PENDING).order_by('created_at', 'pk')[:100],
        'appeals': ComplaintAppeal.objects.select_related('complaint').filter(
            status=ComplaintAppeal.Status.PENDING,
        ).order_by('created_at', 'pk')[:100],
    })


@login_required
@require_POST
@never_cache
def moderator_decision_view(request, pk):
    _staff(request.user)
    action = request.POST.get('action')
    if action not in ('resolve', 'dismiss'):
        return HttpResponseBadRequest('Invalid decision.')
    try:
        decide_complaint(
            actor=request.user, complaint_id=pk,
            approve=(action == 'resolve'),
            note=request.POST.get('note', ''),
        )
    except (ComplaintConflict, ValueError) as exc:
        return HttpResponseBadRequest(str(exc))
    return redirect('moderation:queue')


@login_required
@never_cache
def complaint_appeal_view(request, pk):
    complaint = Complaint.objects.filter(pk=pk).first()
    user = User.objects.filter(
        pk=request.user.pk, is_active=True, is_blocked=False,
        email_verification_required=False,
    ).first()
    if (complaint is None or user is None or complaint.status == Complaint.Status.PENDING
            or user.pk not in (complaint.reporter_id, complaint.target_user_id)):
        raise Http404
    error = ''
    if request.method == 'POST':
        try:
            file_appeal(actor=user, complaint_id=pk, reason=request.POST.get('reason'))
        except ComplaintConflict as exc:
            error = str(exc)
        else:
            return redirect('marketplace:home')
    elif request.method != 'GET':
        raise Http404
    return render(request, 'moderation/appeal.html', {
        'complaint': complaint, 'error': error,
    })


@login_required
@require_POST
@never_cache
def moderator_appeal_decision_view(request, pk):
    _staff(request.user)
    action = request.POST.get('action')
    if action not in ('accept', 'reject'):
        return HttpResponseBadRequest('Invalid decision.')
    try:
        decide_appeal(
            actor=request.user, appeal_id=pk, accept=(action == 'accept'),
        )
    except ComplaintConflict as exc:
        return HttpResponseBadRequest(str(exc))
    return redirect('moderation:queue')

@login_required
@never_cache
def my_complaints_view(request):
    from django.db.models import Q
    stored = User.objects.filter(
        pk=request.user.pk, is_active=True, is_blocked=False,
        email_verification_required=False,
    ).first()
    if stored is None:
        raise PermissionDenied
    cases = Complaint.objects.filter(
        Q(reporter_id=stored.pk) | Q(target_user_id=stored.pk),
    ).distinct().order_by('-created_at', '-pk')[:100]
    return render(request, 'moderation/my_complaints.html', {'cases': cases})
