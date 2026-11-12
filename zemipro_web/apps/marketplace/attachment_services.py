"""04.4 — private, sanitized order photographs and explicit disclosure policies.

Only metadata-free JPEG renditions are stored. Original filenames/bytes and
private storage keys never appear in templates, APIs or access logs.
"""
from hashlib import sha256
from uuid import uuid4
import re

from django.core.exceptions import PermissionDenied
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import User
from apps.accounts.portfolio import (
    PortfolioError, private_portfolio_storage, sanitize_portfolio_image,
)

from .models import Order, OrderAttachment
from .wizard_services import ensure_wizard_owner


MAX_ORDER_PHOTOS = 5
_KEY_PATTERN = re.compile(r'order-attachments/[0-9a-f]{32}\.jpg\Z')


class OrderPhotoError(ValueError):
    """Client-safe photo validation error without exposing input bytes or paths."""


def order_attachment_key(photo):
    if not _KEY_PATTERN.fullmatch(photo.file_key):
        raise OrderPhotoError(_('Некорректный ключ фотографии.'))
    return photo.file_key


def validate_order_photo_batch(uploads):
    """Sanitize before entering transaction to keep row-lock duration bounded."""
    uploads = list(uploads)
    if len(uploads) > MAX_ORDER_PHOTOS:
        raise OrderPhotoError(_('Можно добавить не более 5 фотографий.'))
    result = []
    for upload in uploads:
        try:
            cleaned = sanitize_portfolio_image(upload)
        except PortfolioError as exc:
            raise OrderPhotoError(str(exc)) from exc
        result.append((sha256(cleaned).hexdigest(), cleaned))
    return result


def validate_visibility(visibility, *, public_consent=False):
    if visibility not in OrderAttachment.Visibility.values:
        raise OrderPhotoError(_('Недопустимый режим доступа к фотографии.'))
    if visibility == OrderAttachment.Visibility.PUBLIC and public_consent is not True:
        raise OrderPhotoError(_('Подтвердите согласие на публичный показ фотографии.'))


def store_photos_on_locked_order(order, *, actor, cleaned, visibility,
                                 public_consent=False):
    """Must be called with an already locked draft Order inside transaction.atomic.

    Cleanup files if creating any DB row fails. Repeated identical image/visibility
    is idempotent; no raw media URL is returned.
    """
    validate_visibility(visibility, public_consent=public_consent)
    if order.status != Order.Status.DRAFT or order.client_id != actor.pk:
        raise PermissionDenied
    if not cleaned:
        return []

    # Deduplicate decoded, metadata-free content, including same batch repeats.
    fresh = {}
    for digest, image in cleaned:
        if not OrderAttachment.objects.filter(
            order=order, content_sha256=digest, visibility=visibility,
        ).exists():
            fresh.setdefault(digest, image)
    if OrderAttachment.objects.filter(order=order).count() + len(fresh) > MAX_ORDER_PHOTOS:
        raise OrderPhotoError(_('Можно добавить не более 5 фотографий.'))

    storage = private_portfolio_storage()
    saved = []
    created = []
    try:
        for digest, image in fresh.items():
            name = storage.save(
                f'order-attachments/{uuid4().hex}.jpg',
                ContentFile(image),
            )
            saved.append(name)
            photo = OrderAttachment.objects.create(
                order=order, uploaded_by_id=actor.pk,
                file_key=name, visibility=visibility,
                content_sha256=digest, byte_size=len(image),
                public_consent_at=(
                    timezone.now()
                    if visibility == OrderAttachment.Visibility.PUBLIC else None
                ),
            )
            created.append(photo)
    except Exception:
        for name in saved:
            storage.delete(name)
        raise
    return created


def visible_order_photos(order, user):
    """The photo list itself is filtered, not only the streaming endpoint."""
    qs = OrderAttachment.objects.filter(order=order)
    stored = None
    if getattr(user, 'is_authenticated', False):
        stored = User.objects.filter(
            pk=user.pk, is_active=True, is_blocked=False,
            email_verification_required=False,
        ).first()
    if stored:
        if stored.pk == order.client_id:
            return qs
        if stored.is_staff and stored.has_perm('moderation.review_complaints'):
            return qs
        if (order.status != Order.Status.DRAFT
                and order.worker_id == stored.pk):
            return qs.filter(visibility__in=(
                OrderAttachment.Visibility.PUBLIC, OrderAttachment.Visibility.ASSIGNEE,
            ))
    if order.status == Order.Status.DRAFT:
        # Even a previously public-consented photo stays closed until publish.
        return qs.none()
    return qs.filter(
        visibility=OrderAttachment.Visibility.PUBLIC,
        public_consent_at__isnull=False,
    )


def can_read_order_photo(photo, user):
    return visible_order_photos(photo.order, user).filter(pk=photo.pk).exists()


@transaction.atomic
def delete_order_photo(*, photo_id, actor):
    """Owner may revoke sharing even after publication; no anonymous deletion."""
    ensure_wizard_owner(actor)
    photo = OrderAttachment.objects.select_for_update().select_related('order').filter(
        pk=photo_id, order__client_id=actor.pk,
    ).first()
    if photo is None:
        raise PermissionDenied
    # Serialize against a simultaneous upload/publication.
    order = Order.objects.select_for_update().get(pk=photo.order_id)
    if order.client_id != actor.pk:
        raise PermissionDenied
    storage = private_portfolio_storage()
    key = order_attachment_key(photo)
    photo.delete()
    transaction.on_commit(lambda: storage.delete(key))
    return order
