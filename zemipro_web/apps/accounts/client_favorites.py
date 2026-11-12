"""Stage 03.3: user-private favorites limited to publicly serviceable workers."""
from django.core.exceptions import PermissionDenied
from django.db import transaction

from apps.locations.services import get_public_cities, public_city_slug
from apps.marketplace.services import workers_serving_city
from .models import FavoriteWorker, User, WorkerProfile


def public_worker_queryset():
    workers = WorkerProfile.objects.filter(
        user__is_active=True, user__is_blocked=False,
        is_published=True, city__in=get_public_cities(),
    ).exclude(display_name='').exclude(description='').exclude(
        pricing_details='',
    ).select_related('city', 'user')
    if public_city_slug():
        city = get_public_cities().first()
        return workers_serving_city(workers, city) if city else workers.none()
    return workers


def own_visible_favorites(user):
    if not user.is_authenticated or user.pk is None:
        return FavoriteWorker.objects.none()
    return FavoriteWorker.objects.filter(
        client_id=user.pk, worker__in=public_worker_queryset(),
    ).select_related('worker', 'worker__user', 'worker__city').order_by(
        '-created_at', '-pk',
    )


@transaction.atomic
def toggle_own_favorite(user, worker):
    """Return True if added, False if removed. Never accept a client id."""
    if not user.is_authenticated or user.pk is None:
        raise PermissionDenied
    owner = User.objects.select_for_update().get(pk=user.pk)
    if not owner.is_active or owner.is_blocked:
        raise PermissionDenied
    if worker.user_id == owner.pk:
        raise ValueError('Нельзя сохранить собственный профиль.')
    if not public_worker_queryset().filter(pk=worker.pk).exists():
        raise ValueError('Мастер пока не доступен.')
    existing = FavoriteWorker.objects.filter(
        client=owner, worker_id=worker.pk,
    )
    if existing.exists():
        existing.delete()
        return False
    FavoriteWorker.objects.create(client=owner, worker=worker)
    return True
