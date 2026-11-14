"""Stage 06.5: serialized work actions; only the customer can confirm completion."""
from django.core.exceptions import PermissionDenied
from django.db import transaction

from apps.moderation.models import Complaint

from .agreement_services import effective_agreement
from .models import Order, OrderStatusEvent, OrderWorkEvent
from .offer_services import _enabled, _key
from .order_lifecycle import transition_order_status
from .order_quota import consume_order_quota


def _locked_order(order_id, actor):
    order = Order.objects.select_for_update().get(pk=order_id)
    if (not _enabled(actor)
            or actor.pk not in (order.client_id, order.worker_id)):
        raise PermissionDenied('Нет права управлять выполнением.')
    return order


def _replay(order, actor, action, operation_key, problem_code=''):
    event = OrderWorkEvent.objects.filter(
        order=order, operation_key=operation_key,
    ).first()
    if event is not None:
        if (event.actor_id != actor.pk or event.action != action
                or event.problem_code != problem_code):
            raise ValueError('Идентификатор операции уже использован.')
    return event


def _event(order, actor, action, key, *, problem_code=''):
    return OrderWorkEvent.objects.create(
        order=order, actor=actor, action=action,
        problem_code=problem_code, operation_key=key,
    )


@transaction.atomic
def start_work(*, order_id, actor, operation_key):
    """Only the assigned specialist may begin after selection of terms."""
    key = _key(operation_key)
    order = _locked_order(order_id, actor)
    if order.worker_id != actor.pk:
        raise PermissionDenied('Начать работу может выбранный исполнитель.')
    replay = _replay(order, actor, OrderWorkEvent.Action.STARTED, key)
    if replay is not None:
        return order, False
    if (order.status != Order.Status.ASSIGNED
            or effective_agreement(order) is None):
        raise ValueError('Начало работы недоступно.')
    transition_order_status(
        order, Order.Status.IN_PROGRESS, actor=actor,
        reason=OrderStatusEvent.Reason.WORK_STARTED,
    )
    _event(order, actor, OrderWorkEvent.Action.STARTED, key)
    return order, True


@transaction.atomic
def submit_work_result(*, order_id, actor, operation_key):
    """The worker reports a result, but this never completes the order."""
    key = _key(operation_key)
    order = _locked_order(order_id, actor)
    if order.worker_id != actor.pk:
        raise PermissionDenied('Результат доступен только выбранному исполнителю.')
    replay = _replay(order, actor, OrderWorkEvent.Action.RESULT_SUBMITTED, key)
    if replay is not None:
        return order, False
    if (order.status != Order.Status.IN_PROGRESS
            or not OrderWorkEvent.objects.filter(
                order=order, action=OrderWorkEvent.Action.STARTED,
            ).exists()
            or OrderWorkEvent.objects.filter(
                order=order, action=OrderWorkEvent.Action.RESULT_SUBMITTED,
            ).exists()):
        raise ValueError('Результат уже передан или работа ещё не начата.')
    consume_order_quota(actor, 'state')
    _event(order, actor, OrderWorkEvent.Action.RESULT_SUBMITTED, key)
    return order, True


@transaction.atomic
def confirm_work_result(*, order_id, actor, operation_key=None):
    """Customer confirmation is an explicit action, never a timeout.

    The customer may independently confirm work performed even if a worker
    did not click 'submit result'; older stage04 owner confirmation remains valid.
    """
    key = _key(operation_key)
    order = _locked_order(order_id, actor)
    if order.client_id != actor.pk:
        raise PermissionDenied('Завершить заказ может только заказчик.')
    replay = _replay(order, actor, OrderWorkEvent.Action.RESULT_CONFIRMED, key)
    if replay is not None:
        return order, False
    if order.status == Order.Status.COMPLETED:
        return order, False
    if order.status != Order.Status.IN_PROGRESS:
        raise ValueError('Подтверждение результата недоступно.')
    transition_order_status(order, Order.Status.COMPLETED, actor=actor)
    _event(order, actor, OrderWorkEvent.Action.RESULT_CONFIRMED, key)
    return order, True


@transaction.atomic
def report_work_problem(*, order_id, actor, problem_code, operation_key):
    """Owner or assigned worker can escalate; store a PII-free reason code."""
    key = _key(operation_key)
    order = _locked_order(order_id, actor)
    if problem_code not in (
        OrderWorkEvent.ProblemCode.TIMING,
        OrderWorkEvent.ProblemCode.QUALITY,
        OrderWorkEvent.ProblemCode.OTHER,
    ):
        raise ValueError('Неизвестная категория проблемы.')
    replay = _replay(
        order, actor, OrderWorkEvent.Action.PROBLEM, key, problem_code,
    )
    if replay is not None:
        return order, False
    if order.status not in (Order.Status.ASSIGNED, Order.Status.IN_PROGRESS):
        raise ValueError('Сообщить о проблеме сейчас нельзя.')
    transition_order_status(order, Order.Status.DISPUTED, actor=actor)
    _event(order, actor, OrderWorkEvent.Action.PROBLEM, key, problem_code=problem_code)
    # Forward the dispute to the existing staff moderation queue. This
    # PII-free complaint is committed atomically with the dispute and event;
    # operation-key replays never create duplicate moderation tasks.
    Complaint.objects.create(
        reporter=actor, target_order=order,
        target_user_id=(
            order.worker_id if actor.pk == order.client_id else order.client_id
        ),
        reason=(
            Complaint.Reason.BAD_SERVICE
            if problem_code == OrderWorkEvent.ProblemCode.QUALITY
            else Complaint.Reason.OTHER
        ),
        message=f'Automated order dispute. Reason code: {problem_code}.',
        status=Complaint.Status.PENDING,
    )
    return order, True
