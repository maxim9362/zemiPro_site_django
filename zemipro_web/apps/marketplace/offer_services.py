"""Stage 06: serialized, privately visible offers and immutable revisions."""
import uuid
from decimal import Decimal, InvalidOperation

from django.core.exceptions import PermissionDenied
from django.db import transaction

from apps.accounts.models import User
from .models import Order, Response, ResponseRevision
from .order_quota import consume_order_quota


OFFER_FIELDS = (
    'price_kind', 'amount_min_ils', 'amount_max_ils', 'pricing_method',
    'estimated_timeline', 'terms',
)
ACTIVE_STATUSES = frozenset({
    Response.Status.PENDING, Response.Status.SENT,
    Response.Status.VIEWED, Response.Status.NEGOTIATING,
})
REVISION_FIELDS = (
    'status', 'message', *OFFER_FIELDS,
)


def _key(value):
    if value is None:
        return uuid.uuid4()
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError('Недопустимый идентификатор операции.') from exc


def _enabled(actor):
    return (
        getattr(actor, 'is_authenticated', False)
        and User.objects.filter(
            pk=actor.pk, is_active=True, is_blocked=False,
            email_verification_required=False,
        ).exists()
    )


def _amount(value):
    if value in (None, ''):
        return None
    try:
        result = Decimal(str(value))
    except (TypeError, InvalidOperation, ValueError) as exc:
        raise ValueError('Некорректная стоимость.') from exc
    if not result.is_finite() or result < 0 or result >= 10000000:
        raise ValueError('Некорректная стоимость.')
    if result.as_tuple().exponent < -2:
        raise ValueError('Стоимость указывается с точностью до агоры.')
    return result


def normalize_offer(data):
    """Never trust HTTP forms as the only validation layer."""
    if not isinstance(data, dict):
        raise ValueError('Некорректные условия предложения.')
    kind = data.get('price_kind', Response.PriceKind.NEGOTIABLE)
    if kind not in Response.PriceKind.values:
        raise ValueError('Некорректный способ расчёта.')
    low, high = _amount(data.get('amount_min_ils')), _amount(data.get('amount_max_ils'))
    if kind == Response.PriceKind.FIXED:
        if low is None or high is not None:
            raise ValueError('Укажите одну фиксированную цену.')
    elif kind == Response.PriceKind.RANGE:
        if low is None or high is None or high < low:
            raise ValueError('Некорректный диапазон стоимости.')
    elif low is not None or high is not None:
        raise ValueError('Числовая сумма не соответствует типу цены.')
    text = {}
    for field, limit in (('pricing_method', 240), ('estimated_timeline', 160), ('terms', 1500)):
        value = data.get(field, '')
        if not isinstance(value, str) or len(value) > limit:
            raise ValueError('Слишком длинные условия предложения.')
        text[field] = value.strip()
    if kind == Response.PriceKind.METHOD and not text['pricing_method']:
        raise ValueError('Укажите принцип расчёта стоимости.')
    return {
        'price_kind': kind, 'amount_min_ils': low, 'amount_max_ils': high, **text,
    }


def record_response_revision(response, *, actor, action, operation_key=None):
    """Only call inside the order/offer lock, in the same atomic transaction."""
    if not transaction.get_connection().in_atomic_block:
        raise RuntimeError('Offer audit requires a transaction.')
    return ResponseRevision.objects.create(
        response=response, number=response.revision, actor_id=actor.pk,
        action=action, operation_key=_key(operation_key),
        **{field: getattr(response, field) for field in REVISION_FIELDS},
    )


def _locked_response(response_id, actor, *, owner=False):
    """Always lock Order first; hide ownership from unauthorized actors."""
    ids = Response.objects.filter(pk=response_id).values_list(
        'order_id', 'worker_id',
    ).first()
    if ids is None or not _enabled(actor):
        raise PermissionDenied('Предложение недоступно.')
    order = Order.objects.select_for_update().get(pk=ids[0])
    if (order.client_id if owner else ids[1]) != actor.pk:
        raise PermissionDenied('Предложение недоступно.')
    response = Response.objects.select_for_update().get(
        pk=response_id, order=order,
    )
    return order, response


def _replay(response, key, *, action, values=None):
    event = ResponseRevision.objects.filter(
        response=response, operation_key=key,
    ).first()
    if event is None:
        return False
    if event.action != action or (values is not None and any(
        getattr(event, field) != value for field, value in values.items()
    )):
        raise ValueError('Идентификатор операции уже использован.')
    return True


@transaction.atomic
def submit_offer(*, order, actor, message, data, operation_key=None):
    """Create at most one offer forever per order/worker, including retries."""
    key = _key(operation_key)
    if not _enabled(actor):
        raise PermissionDenied('Аккаунт недоступен.')
    payload = normalize_offer(data)
    if not isinstance(message, str) or len(message) > 1000:
        raise ValueError('Некорректное сообщение.')
    # Lock order before reading existing offer; the underlying create_response
    # obtains the same lock and verifies service, city, publication, and quota.
    locked = Order.objects.select_for_update().get(pk=order.pk)
    existing = Response.objects.filter(order=locked, worker_id=actor.pk).first()
    if existing is not None:
        if _replay(
            existing, key, action='submitted', values={'message': message, **payload},
        ):
            return existing, False
        raise ValueError('Предложение этому заказу уже отправлено.')
    from .services import create_response
    return create_response(
        locked, actor, message=message, offer_data=payload, operation_key=key,
    ), True


@transaction.atomic
def edit_offer(*, response_id, actor, data, message, expected_revision, operation_key):
    """Optimistic revision + PostgreSQL row lock prevent lost edits."""
    key = _key(operation_key)
    order, response = _locked_response(response_id, actor)
    changes = normalize_offer(data)
    if not isinstance(message, str) or len(message) > 1000:
        raise ValueError('Некорректное сообщение.')
    changed = {'message': message, **changes}
    if _replay(response, key, action='edited', values=changed):
        return response, False
    if (order.worker_id is not None
            or order.status not in (Order.Status.PUBLISHED, Order.Status.IN_DISCUSSION)
            or response.status not in ACTIVE_STATUSES):
        raise ValueError('Редактирование предложения недоступно.')
    if str(response.revision) != str(expected_revision):
        raise ValueError('Предложение изменилось. Обновите страницу.')
    if all(getattr(response, f) == v for f, v in changed.items()):
        return response, False
    consume_order_quota(actor, 'response')
    for field, value in changed.items():
        setattr(response, field, value)
    response.revision += 1
    response.save(update_fields=[*changed, 'revision', 'updated_at'])
    record_response_revision(response, actor=actor, action='edited', operation_key=key)
    return response, True


@transaction.atomic
def set_offer_status(*, response_id, actor, action, operation_key):
    """Owner sees/discusses/rejects; worker withdraws; never owner-forged."""
    actions = {
        'viewed': (True, Response.Status.VIEWED),
        'negotiate': (True, Response.Status.NEGOTIATING),
        'reject': (True, Response.Status.REJECTED),
        'withdraw': (False, Response.Status.WITHDRAWN),
    }
    if action not in actions:
        raise ValueError('Неизвестное действие.')
    owner, target = actions[action]
    key = _key(operation_key)
    order, response = _locked_response(response_id, actor, owner=owner)
    if _replay(response, key, action=action):
        return response, False
    if (order.worker_id is not None
            or order.status not in (Order.Status.PUBLISHED, Order.Status.IN_DISCUSSION)
            or response.status not in ACTIVE_STATUSES):
        raise ValueError('Предложение больше недоступно.')
    if response.status == target:
        return response, False
    if action == 'viewed' and response.status not in (
        Response.Status.PENDING, Response.Status.SENT,
    ):
        return response, False
    consume_order_quota(actor, 'state')
    response.status = target
    response.revision += 1
    response.save(update_fields=['status', 'revision', 'updated_at'])
    record_response_revision(response, actor=actor, action=action, operation_key=key)
    return response, True
