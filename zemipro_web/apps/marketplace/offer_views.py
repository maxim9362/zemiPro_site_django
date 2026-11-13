"""Owner/worker-only stage 06 HTTP actions. Default Django CSRF middleware applies."""
import uuid

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_POST

from .forms import ResponseCreateForm
from .models import Order, Response
from .offer_services import edit_offer, set_offer_status
from .offer_ui import offer_copy
from .order_quota import OrderQuotaExceeded


@login_required
@never_cache
@require_http_methods(['GET', 'POST'])
def edit_offer_view(request, pk):
    response = get_object_or_404(
        Response.objects.select_related('order'), pk=pk, worker_id=request.user.pk,
    )
    order = response.order
    if (order.worker_id is not None
            or order.status not in (Order.Status.PUBLISHED, Order.Status.IN_DISCUSSION)
            or response.status not in (
                Response.Status.PENDING, Response.Status.SENT,
                Response.Status.VIEWED, Response.Status.NEGOTIATING,
            )):
        raise Http404
    copy = offer_copy()
    if request.method == 'POST':
        form = ResponseCreateForm(request.POST, instance=response)
        if form.is_valid():
            try:
                edit_offer(
                    response_id=response.pk, actor=request.user,
                    message=form.cleaned_data['message'],
                    data=form.cleaned_data,
                    expected_revision=request.POST.get('expected_revision'),
                    operation_key=request.POST.get('operation_key'),
                )
                return redirect('marketplace:order_detail', pk=order.pk)
            except OrderQuotaExceeded as exc:
                from .views import _order_quota_response
                return _order_quota_response(exc)
            except ValueError as exc:
                form.add_error(None, copy['action_error'])
        key = request.POST.get('operation_key') or uuid.uuid4()
    else:
        form = ResponseCreateForm(instance=response)
        key = uuid.uuid4()
    return render(request, 'pages/offer_form.html', {
        'form': form, 'response': response, 'order': order,
        'page_title': copy['edit'], 'submit_label': copy['save'],
        'offer_copy': copy, 'operation_key': key,
    })


@login_required
@never_cache
@require_POST
def offer_action_view(request, pk, action):
    response = get_object_or_404(Response, pk=pk)
    try:
        set_offer_status(
            response_id=response.pk, actor=request.user, action=action,
            operation_key=request.POST.get('operation_key'),
        )
    except OrderQuotaExceeded as exc:
        from .views import _order_quota_response
        return _order_quota_response(exc)
    except ValueError as exc:
        messages.error(request, offer_copy()['action_error'])
    # PermissionDenied propagates as 403; no redirect to private order details.
    return redirect('marketplace:order_detail', pk=response.order_id)


@login_required
@never_cache
@require_http_methods(['GET', 'POST'])
def agreement_propose_view(request, pk):
    from apps.accounts.models import User
    from .agreement_services import effective_agreement, propose_agreement_change

    order = get_object_or_404(Order, pk=pk)
    if (order.worker_id is None
            or request.user.pk not in (order.client_id, order.worker_id)
            or not User.objects.filter(
                pk=request.user.pk, is_active=True, is_blocked=False,
                email_verification_required=False,
            ).exists()):
        raise PermissionDenied('Соглашение недоступно.')
    active = effective_agreement(order)
    if active is None:
        raise Http404
    copy = offer_copy()
    initial = {field: getattr(active, field) for field in (
        'price_kind', 'amount_min_ils', 'amount_max_ils',
        'pricing_method', 'estimated_timeline', 'terms',
    )}
    initial['message'] = ''
    if request.method == 'POST':
        form = ResponseCreateForm(request.POST)
        if form.is_valid():
            try:
                propose_agreement_change(
                    order_id=order.pk, actor=request.user, data=form.cleaned_data,
                    note=form.cleaned_data['message'],
                    base_version=request.POST.get('base_version'),
                    operation_key=request.POST.get('operation_key'),
                )
                return redirect('marketplace:order_detail', pk=order.pk)
            except OrderQuotaExceeded as exc:
                from .views import _order_quota_response
                return _order_quota_response(exc)
            except ValueError as exc:
                form.add_error(None, str(exc))
    else:
        form = ResponseCreateForm(initial=initial)
    return render(request, 'pages/offer_form.html', {
        'form': form, 'order': order, 'response': None,
        'base_version': active.number, 'offer_copy': copy,
        'page_title': copy['change_agreement'],
        'submit_label': copy['change_agreement'],
        'operation_key': request.POST.get('operation_key') or uuid.uuid4(),
    })


@login_required
@never_cache
@require_POST
def agreement_decide_view(request, pk, action):
    from .agreement_services import decide_agreement_change

    try:
        decision, _ = decide_agreement_change(
            agreement_id=pk, actor=request.user, action=action,
            operation_key=request.POST.get('operation_key'),
        )
    except OrderQuotaExceeded as exc:
        from .views import _order_quota_response
        return _order_quota_response(exc)
    except ValueError as exc:
        messages.error(request, str(exc))
        # Never leak an unowned order ID on failed decisions.
        return redirect('marketplace:client_dashboard')
    return redirect('marketplace:order_detail', pk=decision.agreement.order_id)
