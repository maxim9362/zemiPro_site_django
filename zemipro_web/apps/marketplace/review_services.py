"""07.4: verified one-time public reply and append-only review evidence."""
from django.core.exceptions import PermissionDenied
from django.db import transaction

from apps.accounts.models import User
from apps.notifications.domain_services import create_domain_notification

from .models import Order, Rating, RatingAuditEvent, RatingReply


class ReviewConflict(ValueError):
    """Safe public error without customer/worker PII."""


@transaction.atomic
def submit_review_reply(*, rating_id, actor, body):
    if not isinstance(body, str) or not body.strip() or len(body) > 1000:
        raise ReviewConflict('Invalid reply length.')
    if not getattr(actor, 'is_authenticated', False):
        raise PermissionDenied('Review unavailable.')
    if not User.objects.filter(
        pk=actor.pk, is_active=True, is_blocked=False,
        email_verification_required=False,
    ).exists():
        raise PermissionDenied('Review unavailable.')
    order_id = Rating.objects.filter(pk=rating_id).values_list('order_id', flat=True).first()
    if order_id is None:
        raise PermissionDenied('Review unavailable.')
    order = Order.objects.select_for_update().get(pk=order_id)
    rating = Rating.objects.select_for_update().get(pk=rating_id, order_id=order.pk)
    if (order.status != Order.Status.COMPLETED or order.worker_id != actor.pk
            or rating.worker_id != actor.pk or rating.client_id != order.client_id
            or rating.client_id == actor.pk):
        raise PermissionDenied('Review unavailable.')
    existing = RatingReply.objects.filter(rating=rating).first()
    if existing is not None:
        if existing.body == body:
            return existing, False
        raise ReviewConflict('A public reply already exists.')
    reply = RatingReply.objects.create(rating=rating, worker_id=actor.pk, body=body)
    RatingAuditEvent.objects.get_or_create(
        rating=rating, action=RatingAuditEvent.Action.REPLIED,
        defaults={'actor_id': actor.pk, 'score': rating.rating},
    )
    create_domain_notification(
        recipient_id=rating.client_id, event_key=f'review.reply.{reply.pk}',
        event='review_reply', related_order=order, mandatory=False,
    )
    return reply, True
