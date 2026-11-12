from django.utils import timezone

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


def get_user_notifications(user):
    """Получить уведомления пользователя, новые сверху."""
    return Notification.objects.filter(recipient=user).order_by('-created_at')


def get_unread_count(user):
    """Количество непрочитанных уведомлений."""
    if not user or not user.is_authenticated or not user.is_active or user.is_blocked:
        return 0
    return Notification.objects.filter(recipient=user, is_read=False).count()


def mark_notification_read(notification, user):
    """Пометить уведомление прочитанным (только владелец)."""
    if notification.recipient != user:
        return False
    if not notification.is_read:
        notification.is_read = True
        notification.read_at = timezone.now()
        notification.save(update_fields=['is_read', 'read_at'])
    return True


def mark_all_notifications_read(user):
    """Пометить все непрочитанные уведомления прочитанными."""
    now = timezone.now()
    Notification.objects.filter(
        recipient=user, is_read=False
    ).update(is_read=True, read_at=now)
