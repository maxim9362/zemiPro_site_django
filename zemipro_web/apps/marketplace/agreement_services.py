"""Stage 06.4: immutable agreements with explicit two-party approval."""
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Max

from .models import Order, OrderAgreementDecision, OrderAgreementVersion, Response
from .offer_services import OFFER_FIELDS, _enabled, _key, normalize_offer
from .order_quota import consume_order_quota


def effective_agreement(order):
    """Last mutually accepted agreement, never an unconfirmed proposal."""
    return OrderAgreementVersion.objects.filter(
        order=order, decision__result=OrderAgreementDecision.Result.ACCEPTED,
    ).order_by('-number').first()


def pending_agreement(order):
    return OrderAgreementVersion.objects.filter(
        order=order, decision__isnull=True,
    ).order_by('-number').first()


def _locked_order(order_id, actor):
    order = Order.objects.select_for_update().get(pk=order_id)
    if not _enabled(actor) or actor.pk not in (order.client_id, order.worker_id):
        raise PermissionDenied('Соглашение недоступно.')
    return order


def create_initial_agreement(order, response, *, actor):
    """Create a version and the client's acceptance inside assignment transaction."""
    if not transaction.get_connection().in_atomic_block:
        raise RuntimeError('Agreement requires an atomic transaction.')
    if (order.client_id != actor.pk or order.worker_id != response.worker_id
            or order.status != Order.Status.ASSIGNED
            or response.status != Response.Status.ACCEPTED):
        raise ValueError('Нельзя подтвердить невыбранное предложение.')
    if OrderAgreementVersion.objects.filter(order=order).exists():
        raise ValueError('Соглашение уже зафиксировано.')
    version = OrderAgreementVersion.objects.create(
        order=order, response=response, number=1,
        response_revision=response.revision, proposed_by_id=response.worker_id,
        note=response.message,
        **{field: getattr(response, field) for field in OFFER_FIELDS},
    )
    OrderAgreementDecision.objects.create(
        agreement=version, actor=actor,
        result=OrderAgreementDecision.Result.ACCEPTED,
    )
    return version


@transaction.atomic
def propose_agreement_change(*, order_id, actor, data, note, base_version,
                             operation_key):
    """Keep active version until the other party explicitly approves changes."""
    key = _key(operation_key)
    order = _locked_order(order_id, actor)
    payload = normalize_offer(data)
    if not isinstance(note, str) or len(note) > 1000:
        raise ValueError('Некорректные условия соглашения.')
    replay = OrderAgreementVersion.objects.filter(
        order=order, operation_key=key,
    ).first()
    if replay is not None:
        if (replay.proposed_by_id != actor.pk or replay.note != note
                or any(getattr(replay, field) != value for field, value in payload.items())):
            raise ValueError('Идентификатор операции уже использован.')
        return replay, False
    if order.status not in (
        Order.Status.ASSIGNED, Order.Status.IN_PROGRESS, Order.Status.DISPUTED,
    ):
        raise ValueError('Изменение соглашения недоступно.')
    active = effective_agreement(order)
    if active is None or str(active.number) != str(base_version):
        raise ValueError('Версия соглашения изменилась.')
    if pending_agreement(order) is not None:
        raise ValueError('Предыдущее изменение ещё не рассмотрено.')
    if all(getattr(active, field) == value for field, value in payload.items()):
        raise ValueError('Условия не изменились.')
    consume_order_quota(actor, 'edit')
    response = Response.objects.get(
        order=order, worker_id=order.worker_id, status=Response.Status.ACCEPTED,
    )
    version = OrderAgreementVersion.objects.create(
        order=order, response=response,
        number=OrderAgreementVersion.objects.filter(
            order=order,
        ).aggregate(highest=Max('number'))['highest'] + 1,
        response_revision=response.revision, proposed_by=actor,
        operation_key=key, note=note, **payload,
    )
    return version, True


@transaction.atomic
def decide_agreement_change(*, agreement_id, actor, action, operation_key):
    """Counterparty decision remains immutable; replays never double-apply."""
    if action not in ('accept', 'reject'):
        raise ValueError('Неизвестное действие.')
    key = _key(operation_key)
    order_id = OrderAgreementVersion.objects.filter(
        pk=agreement_id,
    ).values_list('order_id', flat=True).first()
    if order_id is None:
        raise PermissionDenied('Соглашение недоступно.')
    order = _locked_order(order_id, actor)
    version = OrderAgreementVersion.objects.get(pk=agreement_id, order=order)
    counterparty = (
        order.worker_id if version.proposed_by_id == order.client_id
        else order.client_id
    )
    if (actor.pk != counterparty or version.proposed_by_id not in (
        order.client_id, order.worker_id,
    )):
        raise PermissionDenied('Нельзя подтвердить собственное предложение.')
    wanted = (
        OrderAgreementDecision.Result.ACCEPTED if action == 'accept'
        else OrderAgreementDecision.Result.REJECTED
    )
    decision = OrderAgreementDecision.objects.filter(agreement=version).first()
    if decision is not None:
        if decision.result != wanted or decision.operation_key != key:
            raise ValueError('Соглашение уже рассмотрено.')
        return decision, False
    if (order.status not in (
        Order.Status.ASSIGNED, Order.Status.IN_PROGRESS, Order.Status.DISPUTED,
    ) or pending_agreement(order) != version):
        raise ValueError('Соглашение больше недоступно.')
    consume_order_quota(actor, 'state')
    decision = OrderAgreementDecision.objects.create(
        agreement=version, actor=actor, result=wanted, operation_key=key,
    )
    return decision, True
