"""Stage 14.11 privacy-minimizing external-worker registration invites."""
import hashlib
import hmac
import secrets
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .models import ExternalWorkerInvite
from .qa_services import _active_user, _charge


SESSION_KEY = 'external_worker_invite_digest'
TOKEN_BYTES = 32
TTL_DAYS = 7


def _enabled():
    if not getattr(settings, 'ZEMIPRO_EXTERNAL_WORKER_INVITES_ENABLED', False):
        raise PermissionDenied('External worker invitations are not enabled.')


def _digest(token):
    if not isinstance(token, str) or not 32 <= len(token) <= 128:
        return ''
    return hmac.new(
        settings.SECRET_KEY.encode(), token.encode(), hashlib.sha256,
    ).hexdigest()


@transaction.atomic
def create_invite(*, actor):
    """Return a one-time raw URL token; only its HMAC digest is persisted."""
    _enabled()
    user = _active_user(actor)
    _charge(user, 'question')
    token = secrets.token_urlsafe(TOKEN_BYTES)
    invite = ExternalWorkerInvite.objects.create(
        inviter=user, token_digest=_digest(token),
        expires_at=timezone.now() + timedelta(days=TTL_DAYS),
    )
    return invite, token


@transaction.atomic
def open_invite(token):
    _enabled()
    digest = _digest(token)
    if not digest:
        raise PermissionDenied('Invitation is unavailable.')
    invite = ExternalWorkerInvite.objects.select_for_update().filter(
        token_digest=digest, expires_at__gt=timezone.now(), claimed_count=0,
    ).first()
    if invite is None:
        raise PermissionDenied('Invitation is unavailable.')
    ExternalWorkerInvite.objects.filter(pk=invite.pk).update(
        opened_count=F('opened_count') + 1,
    )
    return invite


def remember_invite(request, invite):
    request.session[SESSION_KEY] = invite.token_digest
    request.session.modified = True


@transaction.atomic
def claim_invite_from_session(request):
    """Count a genuine completed registration without storing the new user ID."""
    digest = request.session.pop(SESSION_KEY, '')
    if not digest or not getattr(settings, 'ZEMIPRO_EXTERNAL_WORKER_INVITES_ENABLED', False):
        return False
    invite = ExternalWorkerInvite.objects.select_for_update().filter(
        token_digest=digest, expires_at__gt=timezone.now(), claimed_count=0,
    ).first()
    if invite is None:
        return False
    invite.claimed_count = 1
    invite.claimed_at = timezone.now()
    invite.save(update_fields=['claimed_count', 'claimed_at'])
    return True


def invite_from_session(request):
    digest = request.session.get(SESSION_KEY, '')
    if not digest or not getattr(settings, 'ZEMIPRO_EXTERNAL_WORKER_INVITES_ENABLED', False):
        return None
    return ExternalWorkerInvite.objects.filter(
        token_digest=digest, expires_at__gt=timezone.now(), claimed_count=0,
    ).only('pk', 'expires_at').first()
