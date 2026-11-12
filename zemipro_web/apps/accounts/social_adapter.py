"""OAuth security: new Google identities only; existing accounts link explicitly.

No automatic login or merge based on the raw email string. Never trust
unverified provider email, and never silently elevate staff/worker roles.
"""
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib import messages
from django.db import IntegrityError, transaction
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from .models import User, VerifiedContact
from .verification import contact_fingerprint


class ZemiProGoogleAdapter(DefaultSocialAccountAdapter):
    def _deny(self, request):
        messages.error(
            request,
            _('Google-вход недоступен для этого аккаунта. Войдите по email и паролю.'),
        )
        raise ImmediateHttpResponse(HttpResponseRedirect(reverse('accounts:login')))

    def pre_social_login(self, request, sociallogin):
        if sociallogin.account.provider != 'google':
            self._deny(request)
        if sociallogin.is_existing:
            person = User.objects.filter(pk=sociallogin.user.pk).first()
            if person is None or not person.is_active or person.is_blocked:
                self._deny(request)
            return
        address = (sociallogin.user.email or '').strip().casefold()
        approved = {
            item.email.strip().casefold() for item in sociallogin.email_addresses
            if item.verified
        }
        if not address or address not in approved:
            self._deny(request)
        if User.objects.filter(email__iexact=address).exists():
            # Existing local or legacy email needs an explicit, authenticated
            # connection operation, never an implicit match-based takeover.
            self._deny(request)
        return super().pre_social_login(request, sociallogin)

    def save_user(self, request, sociallogin, form=None):
        """Atomically create one non-privileged user for one verified identity."""
        address = (sociallogin.user.email or '').strip().casefold()
        approved = {
            item.email.strip().casefold() for item in sociallogin.email_addresses
            if item.verified
        }
        if not address or address not in approved:
            self._deny(request)
        try:
            with transaction.atomic():
                # Repeat the pre-login check inside the write transaction. The
                # unique VerifiedContact fingerprint closes concurrent races.
                if User.objects.filter(email__iexact=address).exists():
                    self._deny(request)
                person = super().save_user(request, sociallogin, form)
                VerifiedContact.objects.create(
                    user=person,
                    channel='email',
                    fingerprint=contact_fingerprint('email', address),
                )
                person.email_verified_at = timezone.now()
                person.email_verification_required = False
                person.save(update_fields=[
                    'email_verified_at', 'email_verification_required',
                ])
        except IntegrityError:
            self._deny(request)
        return person
