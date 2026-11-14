"""Stage 04.1: serialized and owner-authorized order lifecycle."""
import uuid

from django.core.exceptions import PermissionDenied
from django.db import transaction

from apps.accounts.models import User
from apps.locations.services import city_is_public
from .models import Order, OrderStatusEvent
from .order_quota import consume_order_quota
from .order_events import emit_order_event


ALLOWED_ORDER_TRANSITIONS = {
    Order.Status.DRAFT: frozenset({Order.Status.PUBLISHED, Order.Status.CANCELLED}),
    Order.Status.PUBLISHED: frozenset({
        Order.Status.DRAFT, Order.Status.IN_DISCUSSION, Order.Status.ASSIGNED,
        Order.Status.CANCELLED, Order.Status.EXPIRED,
    }),
    Order.Status.IN_DISCUSSION: frozenset({
        Order.Status.DRAFT, Order.Status.PUBLISHED, Order.Status.ASSIGNED,
        Order.Status.CANCELLED, Order.Status.EXPIRED,
    }),
    Order.Status.ASSIGNED: frozenset({
        Order.Status.IN_PROGRESS, Order.Status.CANCELLED, Order.Status.DISPUTED,
    }),
    Order.Status.IN_PROGRESS: frozenset({
        Order.Status.COMPLETED, Order.Status.CANCELLED, Order.Status.DISPUTED,
    }),
    Order.Status.DISPUTED: frozenset({
        Order.Status.IN_PROGRESS, Order.Status.COMPLETED, Order.Status.CANCELLED,
    }),
    Order.Status.COMPLETED: frozenset(),
    Order.Status.CANCELLED: frozenset(),
    Order.Status.EXPIRED: frozenset(),
}


def transition_order_status(order, target_status, *, actor, operation_key=None,
                            reason=OrderStatusEvent.Reason.TRANSITION):
    """Row-lock and validate a transition, storing a single immutable event.

    Replaying the same operation key never executes a mutation a second time,
    even after other transitions. An identical current state is a no-op.
    """
    order_id = order.pk if isinstance(order, Order) else order
    if target_status not in Order.Status.values:
        raise ValueError('Неизвестный статус заявки.')
    if reason not in OrderStatusEvent.Reason.values:
        raise ValueError('Неизвестная причина смены статуса.')
    if actor is None or not getattr(actor, 'is_authenticated', False):
        raise PermissionDenied('Нет права управлять заявкой.')
    if operation_key is not None:
        try:
            operation_key = uuid.UUID(str(operation_key))
        except (TypeError, ValueError, AttributeError) as error:
            raise ValueError('Неверный идентификатор операции.') from error

    with transaction.atomic():
        # Different orders must not serialize on the shared city row.
        locked = Order.objects.select_for_update(of=('self',)).select_related('city').get(pk=order_id)
        active_owner = User.objects.filter(
            pk=actor.pk, is_active=True, is_blocked=False,
            email_verification_required=False,
        ).exists()
        selected_worker = (
            locked.worker_id == actor.pk
            and target_status in (Order.Status.IN_PROGRESS, Order.Status.DISPUTED)
            and locked.status in (
                Order.Status.ASSIGNED, Order.Status.IN_PROGRESS, Order.Status.DISPUTED,
            )
        )
        if not active_owner or not (locked.client_id == actor.pk or selected_worker):
            raise PermissionDenied('Нет права управлять заявкой.')

        if operation_key is not None:
            existing = OrderStatusEvent.objects.filter(
                order_id=locked.pk, operation_key=operation_key,
            ).first()
            if existing is not None:
                if existing.new_status != target_status:
                    raise ValueError('Идентификатор операции уже использован.')
                return locked

        if locked.status == target_status:
            return locked
        if target_status not in ALLOWED_ORDER_TRANSITIONS.get(locked.status, frozenset()):
            raise ValueError('Недопустимый переход статуса заявки.')
        update_fields = ['status', 'updated_at']
        if target_status == Order.Status.DRAFT:
            from .models import Response
            if locked.worker_id is not None or Response.objects.filter(order=locked).exists():
                raise ValueError('Нельзя снимать заявку с публикации после откликов.')
            steps = (locked.wizard_data or {}).get('steps')
            if isinstance(steps, dict) and '8' in steps:
                # Withdrawn/reopened orders need a NEW final confirmation.
                locked.wizard_data = {
                    **locked.wizard_data,
                    'steps': {k: val for k, val in steps.items() if k != '8'},
                }
                update_fields.append('wizard_data')
        if target_status == Order.Status.PUBLISHED and not city_is_public(locked.city):
            raise ValueError('Город пока не обслуживается.')
        if (locked.status == Order.Status.DRAFT
                and target_status == Order.Status.PUBLISHED):
            from .wizard_services import validate_wizard_status_publication
            validate_wizard_status_publication(locked)
        if target_status == Order.Status.ASSIGNED and locked.worker_id is None:
            raise ValueError('Нельзя назначить заявку без исполнителя.')

        consume_order_quota(actor, 'state')
        previous = locked.status
        locked.status = target_status
        locked.save(update_fields=update_fields)
        source = OrderStatusEvent.objects.create(
            order=locked, actor_id=actor.pk,
            previous_status=previous, new_status=target_status,
            reason=reason, operation_key=operation_key or uuid.uuid4(),
        )
        if target_status == Order.Status.PUBLISHED:
            emit_order_event(locked, 'order_published', source.operation_key)
        elif target_status == Order.Status.CANCELLED:
            emit_order_event(locked, 'order_cancelled', source.operation_key)
        return locked
