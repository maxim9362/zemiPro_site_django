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
                form.add_error(None, str(exc))
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
        messages.error(request, str(exc))
    # PermissionDenied propagates as 403; no redirect to private order details.
    return redirect('marketplace:order_detail', pk=response.order_id)
