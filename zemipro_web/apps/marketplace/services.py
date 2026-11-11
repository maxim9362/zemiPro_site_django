from django.db import transaction
from django.db.models import Case, IntegerField, Value, When

from .models import Order, Response, Rating


def can_view_private_order_details(user, order):
    """Allow private order data only to its owner, assignee, or staff."""
    if not user.is_authenticated:
        return False
    return bool(
        user.is_staff
        or order.client_id == user.id
        or order.worker_id == user.id
    )


def create_order(client, category, city, address, description, price='Договорная', subcategory=None):
    """Создать новую заявку."""
    if client is None or not client.is_authenticated:
        raise ValueError('Для создания заявки требуется авторизация.')
    order = Order.objects.create(
        client=client,
        category=category,
        subcategory=subcategory,
        city=city,
        address=address,
        description=description,
        price=price,
    )
    return order


def get_available_orders_for_worker(worker_profile):
    """Получить заявки, подходящие мастеру по городу и категориям."""
    skills = worker_profile.skills.all()
    if not skills.exists():
        return Order.objects.none()

    # These related objects are rendered on every card.
    base_qs = Order.objects.select_related('category', 'city').filter(
        status=Order.Status.NEW,
        category__in=skills,
    ).exclude(client_id=worker_profile.user_id)

    if worker_profile.city:
        return base_qs.annotate(
            city_priority=Case(
                When(city=worker_profile.city, then=Value(0)),
                default=Value(1),
                output_field=IntegerField(),
            )
        ).order_by('city_priority', '-created_at', '-pk')

    return base_qs.order_by('-created_at', '-pk')


def create_response(order, worker_user, message=''):
    """Создать отклик мастера на заказ."""
    if not hasattr(worker_user, 'worker_profile'):
        raise ValueError('Пользователь не является мастером.')

    if order.client_id == worker_user.pk:
        raise ValueError('Нельзя откликнуться на собственную заявку.')

    if order.status != Order.Status.NEW:
        raise ValueError('Заказ уже не в статусе «В обработке».')

    existing = Response.objects.filter(order=order, worker=worker_user).first()
    if existing:
        raise ValueError('Вы уже откликались на этот заказ.')

    response = Response.objects.create(
        order=order,
        worker=worker_user,
        message=message,
    )
    return response


def accept_response(response):
    """Принять отклик, отклонить остальные, назначить исполнителя."""
    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=response.order_id)
        if order.status != Order.Status.NEW:
            raise ValueError('Исполнитель для этой заявки уже выбран.')

        locked_response = Response.objects.select_for_update().select_related(
            'worker'
        ).get(pk=response.pk, order=order)
        if locked_response.status != Response.Status.PENDING:
            raise ValueError('Этот отклик уже обработан.')

        locked_response.status = Response.Status.ACCEPTED
        locked_response.save(update_fields=['status', 'updated_at'])

        Response.objects.filter(
            order=order
        ).exclude(
            pk=locked_response.pk
        ).update(status=Response.Status.REJECTED)

        order.worker = locked_response.worker
        order.status = Order.Status.IN_PROGRESS
        order.save(update_fields=['worker', 'status', 'updated_at'])

        locked_response.order = order
    return locked_response


def complete_order(order):
    """Завершить заказ."""
    order.status = Order.Status.COMPLETED
    order.save(update_fields=['status', 'updated_at'])
    return order


def cancel_order(order):
    """Отменить заказ."""
    order.status = Order.Status.CANCELLED
    order.save(update_fields=['status', 'updated_at'])
    return order
