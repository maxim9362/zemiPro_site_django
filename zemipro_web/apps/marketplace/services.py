from django.db import transaction
from django.db.models import Case, Exists, IntegerField, OuterRef, Q, Value, When

from apps.accounts.models import WorkerProfile
from apps.locations.services import city_is_public, get_public_cities
from .models import Category, Order, Response


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
    if not city_is_public(city):
        raise ValueError('Город пока не обслуживается.')
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



def workers_serving_city(queryset, city, *, category=None):
    """Apply explicit zones, home city fallback, and online opt-in.

    EXISTS subqueries prevent duplicate workers; no out-of-pilot geography is
    exposed even by a crafted category/city query or remote-service flag.
    """
    if not city_is_public(city):
        return queryset.none()
    through = WorkerProfile.service_cities.through
    zones = through.objects.filter(workerprofile_id=OuterRef('pk'))
    serving = zones.filter(city_id=city.pk)
    queryset = queryset.alias(
        _has_explicit_zones=Exists(zones),
        _serves_selected_city=Exists(serving),
    )
    allowed = (
        Q(_serves_selected_city=True)
        | Q(_has_explicit_zones=False, city_id=city.pk)
    )
    if category is not None:
        if category.work_mode in ('online', 'both'):
            allowed |= Q(offers_remote=True)
    else:
        online_categories = Category.objects.filter(
            workers__pk=OuterRef('pk'), is_active=True,
            work_mode__in=('online', 'both'),
        ).filter(Q(section__isnull=True) | Q(section__is_active=True))
        queryset = queryset.alias(
            _has_remote_skill=Exists(online_categories)
        )
        allowed |= Q(offers_remote=True, _has_remote_skill=True)
    return queryset.filter(allowed)


def get_available_orders_for_worker(worker_profile):
    """New orders only in selected zones or eligible opted-in online skills."""
    if (not worker_profile.is_published or not worker_profile.user.is_active
            or worker_profile.user.is_blocked
            or worker_profile.availability == WorkerProfile.Availability.UNAVAILABLE):
        return Order.objects.none()
    skills = worker_profile.skills.filter(is_active=True).filter(
        Q(section__isnull=True) | Q(section__is_active=True)
    )
    if not skills.exists():
        return Order.objects.none()

    base_qs = Order.objects.select_related('category', 'city').filter(
        status=Order.Status.NEW, category__in=skills,
        city__in=get_public_cities(),
    ).exclude(client_id=worker_profile.user_id)

    # A worker without an explicit area inherits only the historical home city;
    # no default nationwide visibility for new or legacy profiles.
    zones = worker_profile.service_cities.filter(is_active=True)
    zone_filter = Q(city__in=zones)
    if not worker_profile.service_cities.exists() and worker_profile.city_id:
        zone_filter = Q(city_id=worker_profile.city_id)
    if worker_profile.offers_remote:
        zone_filter |= Q(category__work_mode__in=('online', 'both'))

    return base_qs.filter(zone_filter).annotate(
        city_priority=Case(
            When(city_id=worker_profile.city_id, then=Value(0)),
            default=Value(1), output_field=IntegerField(),
        )
    ).order_by('city_priority', '-created_at', '-pk')

def create_response(order, worker_user, message=''):
    """Создать отклик мастера на заказ."""
    if not hasattr(worker_user, 'worker_profile'):
        raise ValueError('Пользователь не является мастером.')

    if not city_is_public(order.city):
        raise ValueError('Город пока не обслуживается.')

    if order.client_id == worker_user.pk:
        raise ValueError('Нельзя откликнуться на собственную заявку.')

    if order.status != Order.Status.NEW:
        raise ValueError('Заказ уже не в статусе «В обработке».')

    worker_profile = worker_user.worker_profile
    if (not worker_profile.is_published or worker_profile.user.is_blocked
            or not worker_profile.user.is_active
            or worker_profile.availability == WorkerProfile.Availability.UNAVAILABLE):
        raise ValueError('Анкета мастера не опубликована или недоступна.')

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
