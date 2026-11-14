"""Stage 07 private chat: persisted participant gates and transactional replay safety."""
from datetime import timedelta
from hashlib import sha256
import re
import uuid

from django.core.exceptions import PermissionDenied
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.portfolio import (
    PortfolioError, private_portfolio_storage, sanitize_portfolio_image,
)

from .models import Conversation, Message, MessageAttachment, Order, Response

ACTIVE_RESPONSE = frozenset({
    Response.Status.PENDING, Response.Status.SENT, Response.Status.VIEWED,
    Response.Status.NEGOTIATING, Response.Status.ACCEPTED,
})
ACTIVE_ORDER = frozenset({
    Order.Status.PUBLISHED, Order.Status.IN_DISCUSSION, Order.Status.ASSIGNED,
    Order.Status.IN_PROGRESS, Order.Status.COMPLETED, Order.Status.DISPUTED,
})
MAX_BODY = 5000
MAX_MESSAGES_PER_MINUTE = 15
MAX_MESSAGE_PHOTOS = 3
_ATTACHMENT_KEY = re.compile(r'chat-attachments/[0-9a-f]{32}\.jpg\Z')


class ChatConflict(ValueError):
    """A safe, non-identifying client error."""


def _account(actor):
    if not getattr(actor, 'is_authenticated', False) or actor.pk is None:
        raise PermissionDenied('Chat unavailable.')
    stored = User.objects.filter(
        pk=actor.pk, is_active=True, is_blocked=False,
        email_verification_required=False,
    ).first()
    if stored is None:
        raise PermissionDenied('Chat unavailable.')
    return stored


def _authorize(conversation, actor):
    stored = _account(actor)
    participants = (conversation.response.order.client_id, conversation.response.worker_id)
    if participants[0] == participants[1] or stored.pk not in participants:
        raise PermissionDenied('Chat unavailable.')
    return stored


def _can_send(conversation):
    response = conversation.response
    order = response.order
    return (
        response.status in ACTIVE_RESPONSE
        and order.status in ACTIVE_ORDER
        and (order.worker_id is None or order.worker_id == response.worker_id)
        and User.objects.filter(
            pk=order.client_id, is_active=True, is_blocked=False,
            email_verification_required=False,
        ).exists()
        and User.objects.filter(
            pk=response.worker_id, is_active=True, is_blocked=False,
            email_verification_required=False,
        ).exists()
    )


@transaction.atomic
def open_conversation(*, response_id, actor):
    """Do not accept participant IDs from the browser; lock Order before Response."""
    _account(actor)
    order_id = Response.objects.filter(pk=response_id).values_list('order_id', flat=True).first()
    if order_id is None:
        raise PermissionDenied('Chat unavailable.')
    order = Order.objects.select_for_update().get(pk=order_id)
    response = Response.objects.select_for_update().select_related('order').filter(
        pk=response_id, order_id=order.pk,
    ).first()
    if response is None:
        raise PermissionDenied('Chat unavailable.')
    conversation = Conversation(response=response)
    _authorize(conversation, actor)
    if not _can_send(conversation):
        raise PermissionDenied('Chat unavailable.')
    return Conversation.objects.get_or_create(response=response)


def get_conversation(*, conversation_id, actor):
    """No staff bypass and no existence oracle for arbitrary conversation IDs."""
    conversation = Conversation.objects.select_related('response__order').filter(
        pk=conversation_id,
    ).first()
    if conversation is None:
        raise PermissionDenied('Chat unavailable.')
    _authorize(conversation, actor)
    return conversation


@transaction.atomic
def send_message(*, conversation_id, actor, body, client_nonce):
    """Serialize writes per thread and return the same row for an exact POST replay."""
    stored = _account(actor)
    try:
        nonce = uuid.UUID(str(client_nonce))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ChatConflict('Invalid message key.') from exc
    if not isinstance(body, str) or not body.strip() or len(body) > MAX_BODY:
        raise ChatConflict('Invalid message length.')
    order_id = Conversation.objects.filter(
        pk=conversation_id,
    ).values_list('response__order_id', flat=True).first()
    if order_id is None:
        raise PermissionDenied('Chat unavailable.')
    Order.objects.select_for_update().get(pk=order_id)
    conversation = Conversation.objects.select_for_update().select_related(
        'response__order',
    ).filter(pk=conversation_id).first()
    if conversation is None:
        raise PermissionDenied('Chat unavailable.')
    _authorize(conversation, stored)
    previous = Message.objects.filter(
        conversation=conversation, sender=stored, client_nonce=nonce,
    ).first()
    if previous is not None:
        if previous.body != body:
            raise ChatConflict('Message key reused with different content.')
        return previous, False
    if not _can_send(conversation):
        raise PermissionDenied('Chat unavailable.')
    last_minute = timezone.now() - timedelta(minutes=1)
    if Message.objects.filter(
        conversation=conversation, sender=stored, created_at__gte=last_minute,
    ).count() >= MAX_MESSAGES_PER_MINUTE:
        raise ChatConflict('Message rate limit reached.')
    message = Message.objects.create(
        conversation=conversation, sender=stored, body=body, client_nonce=nonce,
    )
    from apps.notifications.domain_services import create_domain_notification
    other_id = (
        conversation.response.worker_id
        if stored.pk == conversation.response.order.client_id
        else conversation.response.order.client_id
    )
    create_domain_notification(
        recipient_id=other_id, event_key=f'chat.message.{message.pk}',
        event='message', related_order=conversation.response.order,
        related_response=conversation.response,
    )
    return message, True


def list_messages(*, conversation_id, actor, before_id=None, limit=40):
    conversation = get_conversation(conversation_id=conversation_id, actor=actor)
    qs = Message.objects.filter(conversation=conversation)
    if before_id is not None:
        if not isinstance(before_id, int) or before_id < 1:
            raise ChatConflict('Invalid page cursor.')
        qs = qs.filter(pk__lt=before_id)
    return list(qs.select_related('sender').order_by('-pk')[:min(max(limit, 1), 60)])[::-1]


@transaction.atomic
def mark_messages_read(*, conversation_id, actor, through_id):
    conversation = get_conversation(conversation_id=conversation_id, actor=actor)
    if not isinstance(through_id, int) or through_id < 1:
        raise ChatConflict('Invalid read cursor.')
    if not Message.objects.filter(
        conversation=conversation, pk=through_id,
    ).exists():
        raise ChatConflict('Invalid read cursor.')
    return Message.objects.filter(
        conversation=conversation, pk__lte=through_id, read_at__isnull=True,
    ).exclude(sender_id=actor.pk).update(read_at=timezone.now())


def _attachment_message(*, message_id, actor):
    message = Message.objects.select_related(
        'conversation__response__order',
    ).filter(pk=message_id).first()
    if message is None:
        raise PermissionDenied('Attachment unavailable.')
    _authorize(message.conversation, actor)
    return message


@transaction.atomic
def attach_message_image(*, message_id, actor, upload):
    """Strip EXIF, rewrite as JPEG and store behind a permission-checked route."""
    message = _attachment_message(message_id=message_id, actor=actor)
    if message.sender_id != actor.pk:
        raise PermissionDenied('Attachment unavailable.')
    if not _can_send(message.conversation):
        raise PermissionDenied('Attachment unavailable.')
    try:
        cleaned = sanitize_portfolio_image(upload)
    except PortfolioError as exc:
        raise ChatConflict('Invalid image attachment.') from exc
    # Re-lock message to serialize concurrent uploads and recheck its sender.
    locked = Message.objects.select_for_update().get(pk=message.pk)
    if locked.sender_id != actor.pk:
        raise PermissionDenied('Attachment unavailable.')
    digest = sha256(cleaned).hexdigest()
    existing = MessageAttachment.objects.filter(
        message=locked, content_sha256=digest,
    ).first()
    if existing is not None:
        return existing, False
    if MessageAttachment.objects.filter(message=locked).count() >= MAX_MESSAGE_PHOTOS:
        raise ChatConflict('Attachment limit reached.')
    storage = private_portfolio_storage()
    file_key = storage.save(
        f'chat-attachments/{uuid.uuid4().hex}.jpg', ContentFile(cleaned),
    )
    try:
        item = MessageAttachment.objects.create(
            message=locked, file_key=file_key,
            content_sha256=digest, byte_size=len(cleaned),
        )
    except Exception:
        storage.delete(file_key)
        raise
    return item, True


def open_message_image(*, attachment_id, actor):
    attachment = MessageAttachment.objects.select_related(
        'message__conversation__response__order',
    ).filter(pk=attachment_id).first()
    if attachment is None:
        raise PermissionDenied('Attachment unavailable.')
    _authorize(attachment.message.conversation, actor)
    if not _ATTACHMENT_KEY.fullmatch(attachment.file_key):
        raise PermissionDenied('Attachment unavailable.')
    return private_portfolio_storage().open(attachment.file_key, 'rb')


@transaction.atomic
def take_poll_slot(*, conversation_id, actor):
    """Shared, bounded polling quota; one opaque row per account and thread."""
    import hashlib
    import hmac
    from django.conf import settings
    from apps.accounts.models import SensitivePostCounter

    get_conversation(conversation_id=conversation_id, actor=actor)
    key = hmac.new(
        settings.SECRET_KEY.encode('utf-8'),
        f'chat-poll:{actor.pk}:{conversation_id}'.encode('ascii'),
        hashlib.sha256,
    ).hexdigest()
    now = timezone.now()
    row, _ = SensitivePostCounter.objects.select_for_update().get_or_create(
        bucket_hash=key,
        defaults={'attempts': 0, 'expires_at': now + timedelta(minutes=1)},
    )
    if row.expires_at <= now:
        row.attempts = 0
        row.expires_at = now + timedelta(minutes=1)
    if row.attempts >= 24:
        raise ChatConflict('Chat polling rate limit reached.')
    row.attempts += 1
    row.save(update_fields=['attempts', 'expires_at'])
