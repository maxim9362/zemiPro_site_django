"""Stage 03.2: bounded, secret-free contact verification service.

Verification is strictly optional for browsing; password recovery accepts ONLY
a previously claimed and verified email. No real delivery is available by
default. The production SMS/email provider is a pre-public-release gate.
"""
from datetime import timedelta
import hashlib
import hmac
import re
import secrets

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone

from .delivery import deliver_contact_code
from .models import ContactChallenge, ContactDeliveryEvent, User, VerifiedContact


def normalize_israeli_phone(value):
    """Accept +972, 00972, or local 0; store canonical Israel E.164."""
    if not isinstance(value, str):
        raise ValueError('Invalid Israeli phone')
    raw = re.sub(r'[\s().-]', '', value.strip())
    if raw.startswith('00972'):
        national = raw[5:]
    elif raw.startswith('+972'):
        national = raw[4:]
    elif raw.startswith('972'):
        national = raw[3:]
    elif raw.startswith('0'):
        national = raw[1:]
    else:
        raise ValueError('Invalid Israeli phone')
    # Mobile: 5xxxxxxxx; landline/fixed: 2xxxxxxx, 3xxxxxxx, etc.
    if not (
        re.fullmatch(r'5\d{8}', national)
        or re.fullmatch(r'[234789]\d{7}', national)
        or re.fullmatch(r'[234789]\d{8}', national)
    ):
        raise ValueError('Invalid Israeli phone')
    return '+972' + national


def normalized_destination(user, channel):
    if channel == ContactChallenge.Channel.EMAIL:
        return (user.email or '').strip().casefold()
    if channel == ContactChallenge.Channel.PHONE:
        value = user.phone or ''
        return normalize_israeli_phone(value) if value else ''
    raise ValueError('Недопустимый канал подтверждения.')


def contact_fingerprint(channel, destination):
    """HMAC avoids storing a reversible address/phone in audit/claims."""
    return hmac.new(
        settings.SECRET_KEY.encode('utf-8'),
        f'zemipro:verified-contact:{channel}:{destination}'.encode('utf-8'),
        hashlib.sha256,
    ).hexdigest()


def _code_digest(user_pk, channel, destination_digest, code):
    data = f'zemipro:contact-code:{user_pk}:{channel}:{destination_digest}:{code}'
    return hmac.new(
        settings.SECRET_KEY.encode('utf-8'),
        data.encode('utf-8'), hashlib.sha256,
    ).hexdigest()


@transaction.atomic
def request_contact_verification(user, channel):
    """Issue a 10-minute code, max one every 60 seconds per account/channel.

    Returns False when delivery has not been configured; never exposes a code.
    """
    if not user.is_authenticated or user.pk is None:
        raise PermissionDenied('Требуется авторизация.')
    stored = User.objects.select_for_update().get(pk=user.pk)
    if not stored.is_active or stored.is_blocked:
        raise PermissionDenied('Аккаунт недоступен.')
    destination = normalized_destination(stored, channel)
    if not destination:
        raise ValueError('Укажите контакт в профиле.')
    digest = contact_fingerprint(channel, destination)
    if VerifiedContact.objects.filter(fingerprint=digest).exclude(
        user_id=stored.pk
    ).exists():
        raise ValueError('Контакт уже подтверждён другим аккаунтом.')
    if VerifiedContact.objects.filter(user=stored, fingerprint=digest).exists():
        return True

    now = timezone.now()
    current = ContactChallenge.objects.select_for_update().filter(
        user=stored, channel=channel,
    ).first()
    if current is not None and current.sent_at > now - timedelta(seconds=60):
        raise ValueError('Повторите запрос позже.')

    code = f'{secrets.randbelow(1000000):06d}'
    outcome = ContactDeliveryEvent.Outcome.UNAVAILABLE
    try:
        delivered = deliver_contact_code(channel, destination, code)
        if delivered:
            outcome = ContactDeliveryEvent.Outcome.SENT
    except Exception:
        outcome = ContactDeliveryEvent.Outcome.FAILED
        delivered = False

    ContactDeliveryEvent.objects.create(
        user=stored, channel=channel, destination_digest=digest,
        outcome=outcome,
    )
    if not delivered:
        return False
    ContactChallenge.objects.update_or_create(
        user=stored, channel=channel,
        defaults={
            'destination_digest': digest,
            'code_digest': _code_digest(stored.pk, channel, digest, code),
            'attempts': 0,
            'expires_at': now + timedelta(minutes=10),
            'sent_at': now,
        },
    )
    return True


@transaction.atomic
def confirm_contact_verification(user, channel, code):
    """Single-use confirmation with five guesses at most per issued code."""
    if not user.is_authenticated or user.pk is None:
        raise PermissionDenied('Требуется авторизация.')
    stored = User.objects.select_for_update().get(pk=user.pk)
    if not stored.is_active or stored.is_blocked:
        raise PermissionDenied('Аккаунт недоступен.')
    destination = normalized_destination(stored, channel)
    if not destination:
        return False
    digest = contact_fingerprint(channel, destination)
    challenge = ContactChallenge.objects.select_for_update().filter(
        user=stored, channel=channel,
    ).first()
    if (
        challenge is None or challenge.expires_at <= timezone.now()
        or challenge.destination_digest != digest or challenge.attempts >= 5
    ):
        return False

    if not (
        isinstance(code, str) and len(code) == 6 and code.isascii()
        and code.isdigit() and hmac.compare_digest(
            challenge.code_digest,
            _code_digest(stored.pk, channel, digest, code),
        )
    ):
        challenge.attempts += 1
        challenge.save(update_fields=['attempts'])
        return False

    # Unique fingerprint is DB-enforced; two accounts cannot claim one contact.
    if VerifiedContact.objects.filter(fingerprint=digest).exclude(
        user_id=stored.pk,
    ).exists():
        return False
    VerifiedContact.objects.get_or_create(
        fingerprint=digest,
        defaults={'user': stored, 'channel': channel},
    )
    field = (
        'email_verified_at' if channel == ContactChallenge.Channel.EMAIL
        else 'phone_verified_at'
    )
    now = timezone.now()
    setattr(stored, field, now)
    stored.save(update_fields=[field])
    setattr(user, field, now)
    challenge.delete()
    return True
