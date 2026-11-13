"""Private, optional browsing history for specialist profiles (REQ-DIR-004)."""
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from .models import ClientProfile, User, WorkerProfileView
from .client_favorites import public_worker_queryset


@transaction.atomic
def record_worker_view(user, worker):
    if not getattr(user, 'is_authenticated', False) or user.pk == worker.user_id:
        return False
    owner = User.objects.select_for_update().filter(
        pk=user.pk, is_active=True, is_blocked=False,
        email_verification_required=False,
    ).first()
    if owner is None or not ClientProfile.objects.filter(
        user=owner, track_worker_views=True,
    ).exists():
        return False
    now = timezone.now()
    row, created = WorkerProfileView.objects.get_or_create(
        client=owner, worker=worker, defaults={'last_viewed_at': now},
    )
    if not created and row.last_viewed_at <= now - timedelta(minutes=10):
        row.last_viewed_at = now
        row.save(update_fields=['last_viewed_at'])
    # Never store an unbounded viewing history.
    latest = list(WorkerProfileView.objects.filter(
        client=owner,
    ).order_by('-last_viewed_at', '-pk').values_list('pk', flat=True)[:50])
    WorkerProfileView.objects.filter(client=owner).exclude(pk__in=latest).delete()
    return True


def own_visible_worker_history(user):
    if not getattr(user, 'is_authenticated', False) or user.pk is None:
        return WorkerProfileView.objects.none()
    return WorkerProfileView.objects.filter(
        client_id=user.pk, worker__in=public_worker_queryset(),
    ).select_related('worker', 'worker__city').order_by('-last_viewed_at', '-pk')


@transaction.atomic
def clear_own_worker_history(user):
    owner = User.objects.select_for_update().filter(
        pk=getattr(user, 'pk', None), is_active=True, is_blocked=False,
        email_verification_required=False,
    ).first()
    if owner is None:
        return False
    WorkerProfileView.objects.filter(client=owner).delete()
    return True
