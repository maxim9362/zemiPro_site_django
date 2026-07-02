from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import render, redirect, get_object_or_404

from .models import Notification
from .services import get_user_notifications, mark_notification_read, mark_all_notifications_read


@login_required
def notification_list_view(request):
    notifications = get_user_notifications(request.user)
    paginator = Paginator(notifications, 20)
    page = paginator.get_page(request.GET.get('page'))
    return render(request, 'notifications/notification_list.html', {
        'page_obj': page,
    })


@login_required
def notification_mark_read_view(request, pk):
    if request.method != 'POST':
        raise Http404

    notification = get_object_or_404(Notification, pk=pk, recipient=request.user)
    mark_notification_read(notification, request.user)

    if notification.related_order:
        return redirect('marketplace:order_detail', pk=notification.related_order_id)
    return redirect('notifications:notification_list')


@login_required
def notification_mark_all_read_view(request):
    if request.method != 'POST':
        raise Http404

    mark_all_notifications_read(request.user)
    return redirect('notifications:notification_list')
