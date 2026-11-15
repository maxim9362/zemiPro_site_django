"""Stage 14.8 public-safe personal recommendation interface."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.http import Http404, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import get_language
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from apps.accounts.client_favorites import public_worker_queryset

from . import recommendation_services
from .models import PersonalRecommendation, PersonalRecommendationReport
from .qa_forms import ModerationForm, ReportForm
from .recommendation_forms import RecommendationForm


def _allow():
    try:
        recommendation_services._enabled()
    except PermissionDenied as exc:
        raise Http404 from exc


@require_GET
@never_cache
def recommendation_list(request):
    _allow()
    language = (get_language() or 'ru').split('-')[0]
    items = recommendation_services.public_recommendations().filter(language=language)
    page = Paginator(items, 12).get_page(request.GET.get('page'))
    return render(request, 'knowledge/recommendation_list.html', {
        'page_obj': page, 'seo_noindex': True,
    })


@login_required
@never_cache
@require_http_methods(['GET', 'POST'])
def recommendation_create(request, worker_id):
    _allow()
    worker = get_object_or_404(public_worker_queryset(), pk=worker_id)
    form = RecommendationForm(
        request.POST or None,
        initial={'language': (get_language() or 'ru').split('-')[0]},
    )
    if request.method == 'POST' and form.is_valid():
        try:
            with transaction.atomic():
                item = recommendation_services.create_recommendation(
                    actor=request.user, worker_id=worker.pk, **form.cleaned_data,
                )
                recommendation_services.submit_recommendation(
                    actor=request.user, recommendation_id=item.pk,
                    expected_version=item.content_version,
                )
        except recommendation_services.QAConflict as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, 'Recommendation submitted for moderation.')
            return redirect('knowledge_recommendations:list')
    return render(request, 'knowledge/recommendation_form.html', {
        'form': form, 'worker': worker, 'seo_noindex': True,
    }, status=400 if request.method == 'POST' else 200)


@login_required
@require_GET
@never_cache
def moderation_queue(request):
    _allow()
    user = recommendation_services._active_user(request.user, lock=False)
    if not user.is_staff or not user.has_perm(
        'knowledge.moderate_personal_recommendations',
    ):
        raise PermissionDenied('Moderator only.')
    return render(request, 'knowledge/recommendation_moderation.html', {
        'items': PersonalRecommendation.objects.filter(status='pending').select_related(
            'worker',
        )[:100],
        'reports': PersonalRecommendationReport.objects.filter(
            status='pending',
        ).select_related('recommendation')[:100],
    })


@login_required
@require_POST
def moderate(request, recommendation_id):
    form = ModerationForm(request.POST)
    if not form.is_valid():
        raise PermissionDenied('Invalid moderation decision.')
    try:
        recommendation_services.moderate_recommendation(
            actor=request.user, recommendation_id=recommendation_id,
            expected_version=form.cleaned_data['expected_version'],
            approve=form.cleaned_data['action'] == 'approve',
            note=form.cleaned_data['note'],
        )
    except recommendation_services.QAConflict as exc:
        return HttpResponseBadRequest(str(exc))
    return redirect('knowledge:recommendation_moderation')


@login_required
@require_POST
def report(request, recommendation_id):
    _allow()
    form = ReportForm(request.POST)
    if not form.is_valid():
        raise PermissionDenied('Invalid report.')
    try:
        recommendation_services.report_recommendation(
            actor=request.user, recommendation_id=recommendation_id,
            **form.cleaned_data,
        )
    except recommendation_services.QAConflict as exc:
        return HttpResponseBadRequest(str(exc))
    messages.success(request, 'Report submitted.')
    return redirect('knowledge_recommendations:list')


@login_required
@require_POST
def moderate_report(request, report_id):
    action = request.POST.get('action')
    if action not in ('dismiss', 'remove'):
        raise PermissionDenied('Invalid moderation decision.')
    try:
        recommendation_services.decide_report(
            actor=request.user, report_id=report_id, remove=action == 'remove',
        )
    except recommendation_services.QAConflict as exc:
        return HttpResponseBadRequest(str(exc))
    return redirect('knowledge:recommendation_moderation')
