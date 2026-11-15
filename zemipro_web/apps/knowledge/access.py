"""Read-only article permissions for private GET paths (no row locks)."""
from django.core.exceptions import PermissionDenied

from apps.accounts.models import User, WorkerProfile
from apps.locations.models import City


def authoring_profile(actor):
    if not getattr(actor, 'is_authenticated', False) or not getattr(actor, 'pk', None):
        raise PermissionDenied('Account unavailable.')
    if not User.objects.filter(
        pk=actor.pk, is_active=True, is_blocked=False,
        email_verification_required=False,
    ).exists():
        raise PermissionDenied('Account unavailable.')
    worker = WorkerProfile.objects.filter(
        user_id=actor.pk, is_published=True,
    ).first()
    if worker is None or not City.objects.filter(
        pk=worker.city_id, slug='ashdod', is_active=True,
    ).exists():
        raise PermissionDenied('Published Ashdod specialist profile required.')
    return worker
