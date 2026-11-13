"""Stage 03.3: user-private favorites limited to publicly serviceable workers."""
from django.core.exceptions import PermissionDenied
from django.db import transaction

from apps.locations.services import get_public_cities, public_city_slug
from apps.marketplace.services import workers_serving_city
from .models import FavoriteWorker, User, WorkerProfile
from .public_text import POLICY_VERSION


def public_worker_queryset():
    workers = WorkerProfile.objects.filter(
        user__is_active=True, user__is_blocked=False,
        user__email_verification_required=False,
        is_published=True, city__in=get_public_cities(),
        public_content_safe=True,
        public_content_policy_version=POLICY_VERSION,
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
def set_own_favorite(user, worker, *, saved):
    """Set desired private state; retries cannot silently undo an action."""
    if not user.is_authenticated or user.pk is None:
        raise PermissionDenied
    owner = User.objects.select_for_update().get(pk=user.pk)
    if (not owner.is_active or owner.is_blocked
            or owner.email_verification_required):
        raise PermissionDenied
    if worker.user_id == owner.pk:
        raise ValueError('Нельзя сохранить собственный профиль.')
    if not public_worker_queryset().filter(pk=worker.pk).exists():
        raise ValueError('Мастер пока не доступен.')
    if not saved:
        FavoriteWorker.objects.filter(client=owner, worker_id=worker.pk).delete()
        return False
    FavoriteWorker.objects.get_or_create(client=owner, worker=worker)
    return True
