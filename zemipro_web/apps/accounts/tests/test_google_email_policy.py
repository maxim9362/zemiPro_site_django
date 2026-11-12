"""Offline policy checks; OAuth network and Google credentials are not required."""
from types import SimpleNamespace
from unittest.mock import patch

from allauth.exceptions import ImmediateHttpResponse
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory, TestCase
from django.urls import Resolver404, resolve, reverse

from apps.accounts.social_adapter import ZemiProGoogleAdapter
from apps.accounts.delivery import deliver_contact_code
from apps.accounts.forms import RegistrationForm


class EmailGooglePolicyTests(TestCase):
    def test_email_only_registration_and_phone_ignored(self):
        form = RegistrationForm(data={
            'username': 'email-only-visitor', 'email': 'person@example.invalid',
            'phone': '+972501234567',
            'password1': 'Strong-Unique-Pass-9362',
            'password2': 'Strong-Unique-Pass-9362',
        })
        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()
        self.assertEqual(user.email, 'person@example.invalid')
        self.assertIsNone(user.phone)

    def test_google_disabled_until_credential_setup(self):
        self.assertFalse(settings.ZEMIPRO_GOOGLE_LOGIN_ENABLED)
        with self.assertRaises(Resolver404):
            resolve('/oauth/google/login/')
        response = self.client.get(reverse('accounts:login'))
        self.assertNotContains(response, 'google_login')
        self.assertNotContains(response, 'Продолжить с Google')

    def test_sms_is_never_delivered(self):
        with patch('apps.accounts.delivery.send_mail') as send:
            self.assertFalse(deliver_contact_code('phone', '+972501234567', '123456'))
            send.assert_not_called()

    def _request(self):
        request = RequestFactory().get('/oauth/google/login/callback/')
        request.session = self.client.session
        request._messages = FallbackStorage(request)
        return request

    def _social(self, email='someone@example.invalid', verified=True,
                existing=False, user=None):
        profile = user or get_user_model()(email=email)
        return SimpleNamespace(
            account=SimpleNamespace(provider='google'),
            user=profile, is_existing=existing,
            email_addresses=[SimpleNamespace(email=email, verified=verified)],
        )

    def test_unverified_google_email_is_denied(self):
        with self.assertRaises(ImmediateHttpResponse):
            ZemiProGoogleAdapter().pre_social_login(
                self._request(), self._social(verified=False),
            )

    def test_legacy_matching_email_is_not_automatically_claimed(self):
        get_user_model().objects.create_user(
            username='existing', email='someone@example.invalid',
            password='Strong-Existing-Pass-9362',
        )
        with self.assertRaises(ImmediateHttpResponse):
            ZemiProGoogleAdapter().pre_social_login(
                self._request(), self._social(),
            )

    def test_existing_blocked_google_identity_is_denied(self):
        account = get_user_model().objects.create_user(
            username='blocked', is_blocked=True, email='blocked@example.invalid',
        )
        with self.assertRaises(ImmediateHttpResponse):
            ZemiProGoogleAdapter().pre_social_login(
                self._request(), self._social(
                    email=account.email, existing=True, user=account,
                ),
            )

    def test_new_verified_google_identity_passes_policy(self):
        social = self._social()
        with patch.object(
            ZemiProGoogleAdapter.__bases__[0], 'pre_social_login',
        ) as parent:
            ZemiProGoogleAdapter().pre_social_login(self._request(), social)
            parent.assert_called_once()
