"""Stage 03.6 — audited moderation actions require an authorized staff actor."""
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import PrivacyRequest, User
from .models import Complaint, ModerationEvent


def _require_moderator(actor, permission):
    if actor is None or not actor.is_authenticated or actor.pk is None:
        raise PermissionDenied('Недостаточно прав для модерации.')
    # Read current database state and permissions, not cached User/has_perm.
    # All callers are transactional and keep this row locked during mutation.
    stored = User.objects.select_for_update().filter(
        pk=actor.pk, is_active=True, is_blocked=False, is_staff=True,
        email_verification_required=False,
    ).first()
    if stored is None or not stored.has_perm(f'moderation.{permission}'):
        raise PermissionDenied('Недостаточно прав для модерации.')
    return stored


def create_complaint(reporter, reason, message, target_user=None,
                     target_order=None, target_rating=None):
    if (reporter is None or not reporter.is_authenticated
            or not User.objects.filter(
                pk=reporter.pk, is_active=True, is_blocked=False,
            ).exists()):
        raise PermissionDenied('Аккаунт недоступен.')
    return Complaint.objects.create(
        reporter=reporter, reason=reason, message=message,
        target_user=target_user, target_order=target_order,
        target_rating=target_rating,
    )


@transaction.atomic
def resolve_complaint(complaint, admin_note='', *, actor):
    actor = _require_moderator(actor, 'review_complaints')
    row = Complaint.objects.select_for_update().get(pk=complaint.pk)
    if row.status != Complaint.Status.PENDING:
        raise ValueError('Жалоба уже рассмотрена.')
    row.status = Complaint.Status.RESOLVED
    row.admin_note = admin_note
    row.resolved_at = timezone.now()
    row.save(update_fields=['status', 'admin_note', 'resolved_at'])
    ModerationEvent.objects.create(
        actor=actor, complaint=row, target_user=row.target_user,
        action=ModerationEvent.Action.RESOLVE,
    )
    return row


@transaction.atomic
def dismiss_complaint(complaint, admin_note='', *, actor):
    actor = _require_moderator(actor, 'review_complaints')
    row = Complaint.objects.select_for_update().get(pk=complaint.pk)
    if row.status != Complaint.Status.PENDING:
        raise ValueError('Жалоба уже рассмотрена.')
    row.status = Complaint.Status.DISMISSED
    row.admin_note = admin_note
    row.resolved_at = timezone.now()
    row.save(update_fields=['status', 'admin_note', 'resolved_at'])
    ModerationEvent.objects.create(
        actor=actor, complaint=row, target_user=row.target_user,
        action=ModerationEvent.Action.DISMISS,
    )
    return row


@transaction.atomic
def block_user(user, *, actor, complaint=None):
    actor = _require_moderator(actor, 'moderate_accounts')
    target = User.objects.select_for_update().get(pk=user.pk)
    if target.pk == actor.pk or target.is_superuser or target.is_staff:
        raise PermissionDenied('Нельзя блокировать административный аккаунт.')
    if target.is_blocked:
        return False
    target.is_blocked = True
    target.is_active = False
    target.save(update_fields=['is_blocked', 'is_active'])
    ModerationEvent.objects.create(
        actor=actor, target_user=target, complaint=complaint,
        action=ModerationEvent.Action.BLOCK,
    )
    return True


@transaction.atomic
def unblock_user(user, *, actor, complaint=None):
    actor = _require_moderator(actor, 'moderate_accounts')
    target = User.objects.select_for_update().get(pk=user.pk)
    if target.pk == actor.pk or target.is_superuser or target.is_staff:
        raise PermissionDenied('Нельзя изменять административный аккаунт.')
    if not target.is_blocked:
        return False
    target.is_blocked = False
    target.is_active = True
    target.save(update_fields=['is_blocked', 'is_active'])
    ModerationEvent.objects.create(
        actor=actor, target_user=target, complaint=complaint,
        action=ModerationEvent.Action.UNBLOCK,
    )
    return True


@transaction.atomic
def review_privacy_request(item, *, actor, reject=False):
    """Never mark completed or silently export/delete any personal data."""
    actor = _require_moderator(actor, 'review_privacy_requests')
    request = PrivacyRequest.objects.select_for_update().get(pk=item.pk)
    if request.status != PrivacyRequest.Status.PENDING:
        raise ValueError('Запрос уже обрабатывается.')
    request.status = (
        PrivacyRequest.Status.REJECTED if reject
        else PrivacyRequest.Status.PROCESSING
    )
    request.reviewed_at = timezone.now()
    request.save(update_fields=['status', 'reviewed_at'])
    ModerationEvent.objects.create(
        actor=actor, target_user=request.user, privacy_request=request,
        action=(ModerationEvent.Action.PRIVACY_REJECT if reject
                else ModerationEvent.Action.PRIVACY_REVIEW),
    )
    return request
