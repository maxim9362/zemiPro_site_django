"""Offline policy checks; OAuth network and Google credentials are not required."""
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from allauth.account.models import EmailAddress
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.models import SocialAccount, SocialLogin, SocialToken
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import Resolver404, resolve, reverse

from apps.accounts.social_adapter import ZemiProGoogleAdapter
from apps.accounts.delivery import deliver_contact_code
from apps.accounts.forms import RegistrationForm
from apps.accounts.models import VerifiedContact


class EmailGooglePolicyTests(TestCase):
    google_provider_settings = {
        'google': {
            'SCOPE': ['email', 'profile'],
            'AUTH_PARAMS': {'access_type': 'online'},
            'OAUTH_PKCE_ENABLED': True,
            'APP': {
                'client_id': 'synthetic-google-client',
                'secret': 'synthetic-google-secret',
                'key': '',
            },
        },
    }

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
        self.assertTrue(user.email_verification_required)

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

    @override_settings(
        ROOT_URLCONF='apps.accounts.tests.oauth_test_urls',
        ZEMIPRO_GOOGLE_LOGIN_ENABLED=True,
    )
    def test_google_start_requires_csrf_and_uses_state_pkce_without_secret(self):
        with override_settings(SOCIALACCOUNT_PROVIDERS=self.google_provider_settings):
            guarded = Client(enforce_csrf_checks=True)
            url = '/oauth/google/login/'
            self.assertEqual(guarded.post(url).status_code, 403)

            token = 'a' * 32
            guarded.cookies['csrftoken'] = token
            response = guarded.post(
                url,
                {'csrfmiddlewaretoken': token, 'next': 'https://attacker.invalid/'},
                HTTP_X_CSRFTOKEN=token,
            )
        self.assertEqual(response.status_code, 302)
        location = response['Location']
        parsed = urlparse(location)
        self.assertEqual(parsed.hostname, 'accounts.google.com')
        query = parse_qs(parsed.query)
        self.assertTrue(query.get('state', [''])[0])
        self.assertTrue(query.get('code_challenge', [''])[0])
        self.assertEqual(query.get('code_challenge_method'), ['S256'])
        self.assertEqual(query.get('access_type'), ['online'])
        self.assertNotIn('client_secret', query)
        self.assertNotIn('attacker.invalid', location)

    @override_settings(
        ROOT_URLCONF='apps.accounts.tests.oauth_test_urls',
        ZEMIPRO_GOOGLE_LOGIN_ENABLED=True,
    )
    def test_forged_google_callback_state_creates_no_account(self):
        with override_settings(SOCIALACCOUNT_PROVIDERS=self.google_provider_settings):
            response = self.client.get(
                '/oauth/google/login/callback/',
                {'state': 'forged-state', 'code': 'synthetic-code'},
            )
        self.assertIn(response.status_code, (302, 400, 401))
        self.assertFalse(get_user_model().objects.exists())
        self.assertFalse(SocialAccount.objects.exists())
        self.assertNotIn(b'synthetic-code', response.content)

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

    def _persistable_social(self, uid='google-uid-1',
                            email='someone@example.invalid'):
        account = SocialAccount(
            provider='google', uid=uid,
            extra_data={'email': email, 'email_verified': True},
        )
        return SocialLogin(
            user=get_user_model()(email=email),
            account=account,
            token=SocialToken(
                account=account, token='synthetic-access-token',
            ),
            email_addresses=[EmailAddress(
                email=email, verified=True, primary=True,
            )],
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

    def test_first_google_login_creates_one_safe_repeatable_identity(self):
        adapter = ZemiProGoogleAdapter()
        request = self._request()
        social = self._persistable_social()
        adapter.populate_user(request, social, {
            'email': social.user.email,
            'first_name': 'Google', 'last_name': 'Person',
        })
        adapter.pre_social_login(request, social)
        person = adapter.save_user(request, social)

        self.assertTrue(person.username)
        self.assertFalse(person.has_usable_password())
        self.assertFalse(person.is_staff)
        self.assertFalse(person.is_superuser)
        self.assertFalse(person.is_blocked)
        self.assertFalse(person.email_verification_required)
        self.assertIsNotNone(person.email_verified_at)
        self.assertFalse(hasattr(person, 'worker_profile'))
        self.assertEqual(SocialAccount.objects.get().user_id, person.pk)
        self.assertEqual(VerifiedContact.objects.get().user_id, person.pk)
        self.assertFalse(SocialToken.objects.exists())

        # The provider lookup used on repeat login resolves exactly the same
        # linked account and does not create a second local user.
        repeat = SocialLogin(
            user=person, account=SocialAccount.objects.get(),
            email_addresses=[EmailAddress(
                email=person.email, verified=True, primary=True,
            )],
        )
        self.assertTrue(repeat.is_existing)
        adapter.pre_social_login(self._request(), repeat)
        self.assertEqual(get_user_model().objects.count(), 1)

    def test_google_signup_cannot_claim_existing_or_duplicate_email(self):
        existing = get_user_model().objects.create_user(
            username='legacy', email='duplicate@example.invalid',
        )
        social = self._persistable_social(
            uid='google-uid-duplicate', email=existing.email,
        )
        adapter = ZemiProGoogleAdapter()
        adapter.populate_user(self._request(), social, {'email': existing.email})
        with self.assertRaises(ImmediateHttpResponse):
            adapter.save_user(self._request(), social)
        self.assertEqual(get_user_model().objects.count(), 1)
        self.assertFalse(SocialAccount.objects.exists())
        self.assertFalse(VerifiedContact.objects.exists())
