from django.utils import timezone

from apps.accounts.models import User

from .models import Notification


def create_notification(recipient, title, message, notification_type='system',
                        related_order=None, related_response=None):
    """Создать уведомление. Если recipient пустой — ничего не делать."""
    if not recipient or not recipient.is_active or recipient.is_blocked:
        return None
    return Notification.objects.create(
        recipient=recipient,
        title=title,
        message=message,
        notification_type=notification_type,
        related_order=related_order,
        related_response=related_response,
    )


def _eligible_user(user):
    if not getattr(user, 'is_authenticated', False):
        return False
    return User.objects.filter(
        pk=user.pk, is_active=True, is_blocked=False,
        email_verification_required=False,
    ).exists()


def get_user_notifications(user):
    """Persisted recipient authorization; no stale-session data leaks."""
    if not _eligible_user(user):
        return Notification.objects.none()
    return Notification.objects.filter(recipient=user).order_by('-created_at')


def get_unread_count(user):
    """Количество непрочитанных уведомлений."""
    if not _eligible_user(user):
        return 0
    return Notification.objects.filter(recipient=user, is_read=False).count()


def mark_notification_read(notification, user):
    """Пометить уведомление прочитанным (только владелец)."""
    if notification.recipient_id != getattr(user, 'pk', None) or not _eligible_user(user):
        return False
    if not notification.is_read:
        notification.is_read = True
        notification.read_at = timezone.now()
        notification.save(update_fields=['is_read', 'read_at'])
    return True


def mark_all_notifications_read(user):
    """Only an active, persisted, verified recipient may mark notices read."""
    if not _eligible_user(user):
        return 0
    now = timezone.now()
    Notification.objects.filter(
        recipient=user, is_read=False
    ).update(is_read=True, read_at=now)
