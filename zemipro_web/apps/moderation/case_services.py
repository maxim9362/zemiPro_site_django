"""Stage 07.5: private complaint targets, staff queue, appeals and immutable audit."""
import hashlib
import hmac
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import SensitivePostCounter, User, WorkerProfile
from apps.marketplace.chat_services import get_conversation
from apps.marketplace.models import Message, Order, Rating, Response
from apps.notifications.domain_services import create_domain_notification

from .models import Complaint, ComplaintAppeal, ModerationEvent
from .services import _require_moderator, dismiss_complaint, resolve_complaint


class ComplaintConflict(ValueError):
    """Safe complaint error without revealing another user's data."""


def _reporter(actor):
    stored = User.objects.filter(
        pk=getattr(actor, 'pk', None), is_active=True, is_blocked=False,
        email_verification_required=False,
    ).first()
    if stored is None:
        raise PermissionDenied('Complaint unavailable.')
    return stored


def visible_target(*, actor, target_user_id=None, target_order_id=None,
                   target_rating_id=None, target_message_id=None):
    """Resolve exactly one reportable object with no private-object existence oracle."""
    reporter = _reporter(actor)
    targets = [
        target_user_id, target_order_id, target_rating_id, target_message_id,
    ]
    if sum(value is not None for value in targets) != 1:
        raise PermissionDenied('Complaint unavailable.')
    result = {}
    if target_message_id is not None:
        msg = Message.objects.select_related(
            'conversation__response__order',
        ).filter(pk=target_message_id).first()
        if msg is None or msg.sender_id == reporter.pk:
            raise PermissionDenied('Complaint unavailable.')
        get_conversation(conversation_id=msg.conversation_id, actor=reporter)
        result = {'target_message': msg, 'target_user_id': msg.sender_id}
    elif target_order_id is not None:
        order = Order.objects.filter(pk=target_order_id).first()
        if order is None:
            raise PermissionDenied('Complaint unavailable.')
        if not (
            order.client_id == reporter.pk or order.worker_id == reporter.pk
            or Response.objects.filter(order=order, worker_id=reporter.pk).exists()
        ):
            raise PermissionDenied('Complaint unavailable.')
        result = {'target_order': order}
    elif target_rating_id is not None:
        rating = Rating.objects.select_related('order').filter(
            pk=target_rating_id,
        ).first()
        if rating is None:
            raise PermissionDenied('Complaint unavailable.')
        if not (
            reporter.pk in (rating.worker_id, rating.client_id)
            or WorkerProfile.objects.filter(
                user_id=rating.worker_id, is_published=True,
            ).exists()
        ):
            raise PermissionDenied('Complaint unavailable.')
        result = {'target_rating': rating, 'target_user_id': rating.worker_id}
    else:
        worker = WorkerProfile.objects.select_related('user').filter(
            user_id=target_user_id, is_published=True,
        ).first()
        if worker is None or worker.user_id == reporter.pk:
            raise PermissionDenied('Complaint unavailable.')
        result = {'target_user': worker.user}
    return result


def _consume_limit(user):
    key = hmac.new(
        settings.SECRET_KEY.encode(),
        f'stage07:complaint:{user.pk}'.encode('ascii'),
        hashlib.sha256,
    ).hexdigest()
    now = timezone.now()
    quota, _ = SensitivePostCounter.objects.select_for_update().get_or_create(
        bucket_hash=key,
        defaults={'attempts': 0, 'expires_at': now + timedelta(hours=1)},
    )
    if quota.expires_at <= now:
        quota.attempts = 0
        quota.expires_at = now + timedelta(hours=1)
    if quota.attempts >= 5:
        raise ComplaintConflict('Complaint rate limit reached.')
    quota.attempts += 1
    quota.save(update_fields=['attempts', 'expires_at'])


@transaction.atomic
def submit_complaint(*, actor, reason, message, target_user_id=None,
                     target_order_id=None, target_rating_id=None,
                     target_message_id=None):
    reporter = _reporter(actor)
    if reason not in Complaint.Reason.values:
        raise ComplaintConflict('Invalid reason.')
    if not isinstance(message, str) or not message.strip() or len(message) > 3000:
        raise ComplaintConflict('Invalid report length.')
    target = visible_target(
        actor=reporter, target_user_id=target_user_id,
        target_order_id=target_order_id, target_rating_id=target_rating_id,
        target_message_id=target_message_id,
    )
    _consume_limit(reporter)
    complaint = Complaint.objects.create(
        reporter=reporter, reason=reason, message=message, **target,
    )
    # Do not notify unprivileged staff; the queue still retains all reports.
    for user in User.objects.filter(is_staff=True, is_active=True, is_blocked=False):
        if user.has_perm('moderation.review_complaints'):
            create_domain_notification(
                recipient_id=user.pk, event_key=f'complaint.new.{complaint.pk}',
                event='complaint', mandatory=True,
            )
    return complaint


@transaction.atomic
def file_appeal(*, actor, complaint_id, reason):
    user = _reporter(actor)
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 2000:
        raise ComplaintConflict('Invalid appeal length.')
    complaint = Complaint.objects.select_for_update().filter(pk=complaint_id).first()
    if complaint is None or complaint.status == Complaint.Status.PENDING:
        raise PermissionDenied('Appeal unavailable.')
    if user.pk not in (complaint.reporter_id, complaint.target_user_id):
        raise PermissionDenied('Appeal unavailable.')
    row = ComplaintAppeal.objects.filter(complaint=complaint).first()
    if row is not None:
        if row.filed_by_id == user.pk and row.reason == reason:
            return row, False
        raise ComplaintConflict('The appeal has already been filed.')
    row = ComplaintAppeal.objects.create(
        complaint=complaint, filed_by=user, reason=reason,
    )
    ModerationEvent.objects.create(
        actor=user, complaint=complaint,
        target_user=complaint.target_user,
        action=ModerationEvent.Action.APPEAL_FILED,
    )
    for reviewer in User.objects.filter(
        is_staff=True, is_active=True, is_blocked=False,
    ):
        if reviewer.has_perm('moderation.review_complaints'):
            create_domain_notification(
                recipient_id=reviewer.pk, event_key=f'appeal.new.{row.pk}',
                event='complaint', mandatory=True,
            )
    return row, True


@transaction.atomic
def decide_appeal(*, actor, appeal_id, accept):
    staff = _require_moderator(actor, 'review_complaints')
    appeal = ComplaintAppeal.objects.select_for_update().select_related(
        'complaint',
    ).filter(pk=appeal_id).first()
    if appeal is None:
        raise PermissionDenied('Appeal unavailable.')
    if appeal.status != ComplaintAppeal.Status.PENDING:
        raise ComplaintConflict('Appeal already decided.')
    appeal.status = (
        ComplaintAppeal.Status.ACCEPTED if accept
        else ComplaintAppeal.Status.REJECTED
    )
    appeal.decided_by = staff
    appeal.decided_at = timezone.now()
    appeal.save(update_fields=['status', 'decided_by', 'decided_at'])
    ModerationEvent.objects.create(
        actor=staff, complaint=appeal.complaint,
        target_user=appeal.complaint.target_user,
        action=(ModerationEvent.Action.APPEAL_ACCEPTED if accept
                else ModerationEvent.Action.APPEAL_REJECTED),
    )
    create_domain_notification(
        recipient_id=appeal.filed_by_id, event_key=f'appeal.decision.{appeal.pk}',
        event='complaint', mandatory=True,
    )
    return appeal


@transaction.atomic
def decide_complaint(*, actor, complaint_id, approve, note=''):
    """Existing audited moderation helpers; no alternative permission bypass."""
    if not isinstance(note, str) or len(note) > 2000:
        raise ComplaintConflict('Invalid moderator note.')
    row = Complaint.objects.filter(pk=complaint_id).first()
    if row is None:
        raise PermissionDenied('Complaint unavailable.')
    if approve:
        updated = resolve_complaint(row, actor=actor, admin_note=note)
    else:
        updated = dismiss_complaint(row, actor=actor, admin_note=note)
    create_domain_notification(
        recipient_id=updated.reporter_id,
        event_key=f'complaint.decision.{updated.pk}',
        event='complaint', mandatory=True,
    )
    if updated.target_user_id and updated.target_user_id != updated.reporter_id:
        create_domain_notification(
            recipient_id=updated.target_user_id,
            event_key=f'complaint.target.{updated.pk}',
            event='complaint', mandatory=True,
        )
    return updated
