from django.db import transaction
from django.db.models import Q

from .models import Order, Response, Rating


def create_order(client, category, city, address, description, price='Договорная', subcategory=None):
    """Создать новую заявку."""
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
    if not skills:
        return Order.objects.none()

    base_qs = Order.objects.filter(
        status=Order.Status.NEW,
        category__in=skills,
    )

    if worker_profile.city:
        city_orders = base_qs.filter(city=worker_profile.city).order_by('-created_at')
        other_orders = base_qs.exclude(city=worker_profile.city).order_by('-created_at')
        return city_orders.union(other_orders)

    return base_qs.order_by('-created_at')


def create_response(order, worker_user, message=''):
    """Создать отклик мастера на заказ."""
    if not hasattr(worker_user, 'worker_profile'):
        raise ValueError('Пользователь не является мастером.')

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
        response.status = Response.Status.ACCEPTED
        response.save(update_fields=['status', 'updated_at'])

        Response.objects.filter(
            order=response.order
        ).exclude(
            pk=response.pk
        ).update(status=Response.Status.REJECTED)

        response.order.worker = response.worker
        response.order.status = Order.Status.IN_PROGRESS
        response.order.save(update_fields=['worker', 'status', 'updated_at'])
    return response


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
