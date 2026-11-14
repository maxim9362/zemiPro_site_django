from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import render, redirect, get_object_or_404

from .models import Notification
from .services import (
    _eligible_user, get_user_notifications, mark_notification_read,
    mark_all_notifications_read,
)


@login_required
@never_cache
def notification_list_view(request):
    if not _eligible_user(request.user):
        raise PermissionDenied('Notification unavailable.')
    notifications = get_user_notifications(request.user)
    paginator = Paginator(notifications, 20)
    page = paginator.get_page(request.GET.get('page'))
    return render(request, 'notifications/notification_list.html', {
        'page_obj': page,
    })


@login_required
@never_cache
def notification_mark_read_view(request, pk):
    if not _eligible_user(request.user):
        raise PermissionDenied('Notification unavailable.')
    if request.method != 'POST':
        raise Http404

    notification = get_object_or_404(Notification, pk=pk, recipient=request.user)
    mark_notification_read(notification, request.user)

    if notification.related_order:
        return redirect('marketplace:order_detail', pk=notification.related_order_id)
    return redirect('notifications:notification_list')


@login_required
@never_cache
def notification_mark_all_read_view(request):
    if not _eligible_user(request.user):
        raise PermissionDenied('Notification unavailable.')
    if request.method != 'POST':
        raise Http404

    mark_all_notifications_read(request.user)
    return redirect('notifications:notification_list')

@login_required
@never_cache
@require_http_methods(['GET', 'POST'])
def notification_preferences_view(request):
    from apps.accounts.models import User
    from .models import NotificationPreference
    from .domain_services import set_preferences

    stored = User.objects.filter(
        pk=request.user.pk, is_active=True, is_blocked=False,
        email_verification_required=False,
    ).first()
    if stored is None:
        raise PermissionDenied
    if request.method == 'POST':
        set_preferences(
            actor=stored,
            in_app_optional=request.POST.get('in_app_optional') == 'on',
            email_optional=request.POST.get('email_optional') == 'on',
        )
        return redirect('notifications:notification_preferences')
    pref = NotificationPreference.objects.filter(recipient_id=stored.pk).first()
    return render(request, 'notifications/preferences.html', {
        'pref': pref, 'email_verified': bool(stored.email_verified_at),
    })
