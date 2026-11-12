"""Stage 03.3: safe owner-only client settings and privacy requests."""
from django.core.exceptions import PermissionDenied
from django.db import transaction

from apps.locations.services import city_is_public
from .models import (
    ClientProfile, ContactChallenge, PrivacyRequest, User, VerifiedContact,
)
from .verification import contact_fingerprint


def _active_owner(user):
    if not user.is_authenticated or user.pk is None:
        raise PermissionDenied('Требуется вход в аккаунт.')
    owner = User.objects.select_for_update().get(pk=user.pk)
    if not owner.is_active or owner.is_blocked:
        raise PermissionDenied('Аккаунт недоступен.')
    return owner


@transaction.atomic
def save_client_settings(user, cleaned):
    """Change only the acting user's data. No arbitrary target id is accepted."""
    owner = _active_owner(user)
    city = cleaned.get('city')
    if city is not None and not city_is_public(city):
        raise ValueError('Город пока не обслуживается.')
    email = (cleaned.get('email') or '').strip().casefold()
    phone = cleaned.get('phone') or ''
    if not email and not phone and (owner.email or owner.phone):
        raise ValueError('Оставьте хотя бы один способ восстановления доступа.')
    language = cleaned.get('preferred_language')
    if language not in {'ru', 'en', 'he'}:
        raise ValueError('Недопустимый язык.')

    for channel, field, old, new, verification_field in (
        ('email', 'email', (owner.email or '').strip().casefold(),
         email, 'email_verified_at'),
        ('phone', 'phone', owner.phone or '', phone, 'phone_verified_at'),
    ):
        if old != new:
            # Preserve no old claim or OTP after a contact change. Request
            # and verification services lock the same User row.
            VerifiedContact.objects.filter(user=owner, channel=channel).delete()
            ContactChallenge.objects.filter(user=owner, channel=channel).delete()
            setattr(owner, verification_field, None)
        setattr(owner, field, new if new or field == 'email' else None)

    owner.first_name = cleaned.get('first_name', '').strip()
    owner.last_name = cleaned.get('last_name', '').strip()
    owner.preferred_language = language
    owner.save(update_fields=[
        'first_name', 'last_name', 'preferred_language', 'email', 'phone',
        'email_verified_at', 'phone_verified_at',
    ])

    profile, _ = ClientProfile.objects.get_or_create(user=owner)
    profile.city = city
    profile.contact = cleaned.get('contact', '').strip()
    profile.receive_optional_updates = bool(
        cleaned.get('receive_optional_updates', False)
    )
    profile.save(update_fields=[
        'city', 'contact', 'receive_optional_updates', 'updated_at',
    ])
    # Do not mutate worker profile, legacy role, orders or private addresses.
    user.first_name = owner.first_name
    user.last_name = owner.last_name
    user.email = owner.email
    user.phone = owner.phone
    user.email_verified_at = owner.email_verified_at
    user.phone_verified_at = owner.phone_verified_at
    user.preferred_language = owner.preferred_language
    return profile


@transaction.atomic
def request_own_privacy_action(user, kind):
    """Request processing only; never erase/provide unreviewed data automatically."""
    owner = _active_owner(user)
    if kind not in PrivacyRequest.Kind.values:
        raise ValueError('Неизвестный запрос.')
    item, _ = PrivacyRequest.objects.get_or_create(
        user=owner, kind=kind, status=PrivacyRequest.Status.PENDING,
    )
    return item
