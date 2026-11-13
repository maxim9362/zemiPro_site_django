"""Stage 04.7: transactional, PII-free outbox and replay-safe local delivery.

No SMTP, SMS, push, external analytics or background sending is enabled here.
"""
import uuid

from django.db import connection, transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.notifications.models import Notification

from .models import (
    OrderAnalyticsFact, OrderDomainEvent, OrderEventDelivery, Response,
)


def emit_order_event(order, kind, source_key):
    """Record an immutable event + two pending receipts in the caller's tx."""
    if not connection.in_atomic_block:
        raise RuntimeError('Order events must be emitted inside the order transaction.')
    if kind not in OrderDomainEvent.Kind.values:
        raise ValueError('Unknown order event kind.')
    try:
        source = uuid.UUID(str(source_key))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError('Invalid order event source key.') from exc
    stable = uuid.uuid5(
        uuid.NAMESPACE_URL,
        f'zemipro:order:{order.pk}:{kind}:{source}',
    )
    event, created = OrderDomainEvent.objects.get_or_create(
        event_key=stable,
        defaults={
            'order_id': order.pk, 'kind': kind, 'source_key': source,
            'category_id': order.category_id, 'city_id': order.city_id,
        },
    )
    if event.order_id != order.pk or event.kind != kind or event.source_key != source:
        raise ValueError('Order event key collision.')
    if created:
        OrderEventDelivery.objects.bulk_create([
            OrderEventDelivery(
                event=event, consumer=consumer,
                status=OrderEventDelivery.Status.PENDING,
            )
            for consumer in OrderEventDelivery.Consumer.values
        ])
    return event, created


def _eligible_target_ids(ids):
    """Only current, verified, unblocked account holders receive in-app items."""
    return list(User.objects.filter(
        pk__in=set(ids), is_active=True, is_blocked=False,
        email_verification_required=False,
    ).order_by('pk').values_list('pk', flat=True))


def _deliver_in_app(event):
    order = event.order
    kind = event.kind
    if kind == OrderDomainEvent.Kind.CREATED:
        # Drafts never produce a customer notification. Publication does.
        return

    if kind == OrderDomainEvent.Kind.PUBLISHED:
        ids = [order.client_id]
        notification_type = Notification.Type.ORDER_CREATED
        title = 'Заявка создана'
        message = f'Ваша заявка №{order.pk} опубликована.'
    elif kind == OrderDomainEvent.Kind.UPDATED:
        ids = Response.objects.filter(order_id=order.pk).values_list(
            'worker_id', flat=True,
        )
        notification_type = Notification.Type.ORDER_UPDATED
        title = 'Условия заявки изменены'
        message = f'Условия заявки №{order.pk} изменены.'
    elif kind == OrderDomainEvent.Kind.CANCELLED:
        ids = list(Response.objects.filter(order_id=order.pk).values_list(
            'worker_id', flat=True,
        ))
        if order.worker_id is not None:
            ids.append(order.worker_id)
        notification_type = Notification.Type.ORDER_CANCELLED
        title = 'Заявка отменена'
        message = f'Заявка №{order.pk} отменена.'
    else:
        raise ValueError('Unsupported order notification event.')

    for recipient_id in _eligible_target_ids(ids):
        Notification.objects.get_or_create(
            order_event_id=event.pk, recipient_id=recipient_id,
            defaults={
                'title': title, 'message': message,
                'notification_type': notification_type,
                'related_order_id': order.pk,
            },
        )


def _deliver_analytics(event):
    """Append one coarse local fact; never export private order contents."""
    OrderAnalyticsFact.objects.get_or_create(
        event=event,
        defaults={
            'kind': event.kind,
            'city_id': event.city_id,
            'category_id': event.category_id,
            'occurred_at': event.occurred_at,
        },
    )


def process_order_delivery(delivery_id):
    """A completed receipt is a no-op even under concurrent repeated calls.

    Changes to receipts and their in-app/fact targets commit together. Failures
    keep a pending receipt for retry and record only a generic error code.
    """
    try:
        with transaction.atomic():
            receipt = (
                OrderEventDelivery.objects.select_for_update()
                .select_related('event__order')
                .get(pk=delivery_id)
            )
            if receipt.status == OrderEventDelivery.Status.DONE:
                return False
            if receipt.consumer == OrderEventDelivery.Consumer.NOTIFICATIONS:
                _deliver_in_app(receipt.event)
            elif receipt.consumer == OrderEventDelivery.Consumer.ANALYTICS:
                _deliver_analytics(receipt.event)
            else:
                raise ValueError('Unknown order event consumer.')
            receipt.status = OrderEventDelivery.Status.DONE
            receipt.attempts += 1
            receipt.processed_at = timezone.now()
            receipt.last_error_code = ''
            receipt.save(update_fields=[
                'status', 'attempts', 'processed_at', 'last_error_code',
            ])
            return True
    except Exception:
        # The primary atomic block rolled back all side effects. Keep a
        # non-PII failure receipt if the database is still accessible.
        try:
            with transaction.atomic():
                receipt = OrderEventDelivery.objects.select_for_update().get(
                    pk=delivery_id,
                )
                if receipt.status == OrderEventDelivery.Status.PENDING:
                    receipt.attempts += 1
                    receipt.last_error_code = 'processing_failed'
                    receipt.save(update_fields=['attempts', 'last_error_code'])
        except Exception:
            pass
        raise


def deliver_order_events_for_order(order, *, limit=100):
    """Bounded synchronous local delivery; pending remains replayable."""
    order_id = order.pk if hasattr(order, 'pk') else order
    ids = list(OrderEventDelivery.objects.filter(
        event__order_id=order_id,
        status=OrderEventDelivery.Status.PENDING,
    ).order_by('event_id', 'consumer').values_list('pk', flat=True)[:limit])
    return sum(int(process_order_delivery(pk)) for pk in ids)


def replay_pending_order_events(*, limit=100):
    """Idempotent bounded operator replay of persisted delivery receipts."""
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError('Replay limit must be within 1..1000.')
    ids = list(OrderEventDelivery.objects.filter(
        status=OrderEventDelivery.Status.PENDING,
    ).order_by('event_id', 'consumer').values_list('pk', flat=True)[:limit])
    return sum(int(process_order_delivery(pk)) for pk in ids)


def local_order_event_counts():
    """Non-identifying analytics aggregate sourced only from delivery facts."""
    from django.db.models import Count

    return dict(
        OrderAnalyticsFact.objects.values_list('kind')
        .annotate(total=Count('pk'))
        .values_list('kind', 'total')
    )
