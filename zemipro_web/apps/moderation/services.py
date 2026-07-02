from django.utils import timezone

from .models import Complaint


def create_complaint(reporter, reason, message, target_user=None,
                     target_order=None, target_rating=None):
    """Создать жалобу."""
    complaint = Complaint.objects.create(
        reporter=reporter,
        reason=reason,
        message=message,
        target_user=target_user,
        target_order=target_order,
        target_rating=target_rating,
    )
    return complaint


def resolve_complaint(complaint, admin_note=''):
    """Рассмотреть жалобу."""
    complaint.status = Complaint.Status.RESOLVED
    complaint.admin_note = admin_note
    complaint.resolved_at = timezone.now()
    complaint.save(update_fields=['status', 'admin_note', 'resolved_at'])


def dismiss_complaint(complaint, admin_note=''):
    """Отклонить жалобу."""
    complaint.status = Complaint.Status.DISMISSED
    complaint.admin_note = admin_note
    complaint.resolved_at = timezone.now()
    complaint.save(update_fields=['status', 'admin_note', 'resolved_at'])


def block_user(user):
    """Заблокировать пользователя."""
    user.is_blocked = True
    user.is_active = False
    user.save(update_fields=['is_blocked', 'is_active'])


def unblock_user(user):
    """Разблокировать пользователя."""
    user.is_blocked = False
    user.is_active = True
    user.save(update_fields=['is_blocked', 'is_active'])
