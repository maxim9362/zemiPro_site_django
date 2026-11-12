"""Stage 03.2 — synthetic end-to-end account security and contact regressions."""
from datetime import timedelta
from urllib.parse import urlparse
from unittest.mock import patch
import re

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import (
    ContactChallenge, ContactDeliveryEvent, VerifiedContact,
)
from apps.accounts.verification import (
    confirm_contact_verification, normalize_israeli_phone,
    request_contact_verification,
)


class AccountSecurityTests(TestCase):
    def register(self, username='synthetic-registrant', **extra):
        return self.client.post(reverse('accounts:register'), {
            'username': username,
            'email': extra.get('email', 'Synthetic.User@Example.Invalid'),
            'phone': extra.get('phone', '050-123-4567'),
            'password1': 'Synthetic-Password-9362!',
            'password2': 'Synthetic-Password-9362!',
        })

    def test_registration_normalizes_email_phone_and_keeps_username_login(self):
        response = self.register()
        self.assertRedirects(response, reverse('accounts:client_profile'))
        user = get_user_model().objects.get(username='synthetic-registrant')
        self.assertEqual(user.email, 'synthetic.user@example.invalid')
        self.assertEqual(user.phone, '+972501234567')
        self.assertIsNone(user.email_verified_at)
        self.assertIsNone(user.phone_verified_at)
        self.assertEqual(int(self.client.session['_auth_user_id']), user.pk)
        self.client.post(reverse('accounts:logout'))
        logged_in = self.client.post(reverse('accounts:login'), {
            'username': user.username, 'password': 'Synthetic-Password-9362!',
        })
        self.assertRedirects(
            logged_in, reverse('marketplace:client_dashboard'),
            fetch_redirect_response=False,
        )

    def test_missing_or_invalid_contact_registration_is_rejected(self):
        for username, email, phone in (
            ('no-contact', '', ''),
            ('invalid-phone', '', '9999999'),
            ('foreign-phone', '', '+1-202-555-0100'),
            ('short-phone', '', '050-123'),
        ):
            with self.subTest(username=username):
                r = self.register(username, email=email, phone=phone)
                self.assertEqual(r.status_code, 200)
                self.assertFalse(
                    get_user_model().objects.filter(username=username).exists(),
                )

    def test_phone_normalization_local_international_and_landlines(self):
        for entry in ('0501234567', '+972-50-123-4567', '00972 50 123 4567',
                      '972501234567'):
            with self.subTest(entry=entry):
                self.assertEqual(normalize_israeli_phone(entry), '+972501234567')
        self.assertEqual(normalize_israeli_phone('08-123-4567'), '+97281234567')
        for wrong in ('+15551234567', '050123456', '+972999', '010-222-2222'):
            with self.subTest(wrong=wrong), self.assertRaises(ValueError):
                normalize_israeli_phone(wrong)

    def test_contact_labels_have_compiled_en_he_translations(self):
        from django.utils.translation import gettext, override
        for language, expected in (
            ('en', 'Contact verification'),
            ('he', 'אימות פרטי קשר'),
        ):
            with self.subTest(language=language), override(language):
                self.assertEqual(gettext('Подтверждение контактов'), expected)

    @override_settings(ZEMIPRO_CONTACT_DELIVERY_MODE='test-email')
    def test_verified_email_login_and_unverified_duplicate_denied(self):
        self.register()
        user = get_user_model().objects.get(username='synthetic-registrant')
        self.client.post(reverse('accounts:logout'))
        unverified = self.client.post(reverse('accounts:login'), {
            'username': 'synthetic.user@example.invalid',
            'password': 'Synthetic-Password-9362!',
        })
        self.assertEqual(unverified.status_code, 200)
        self.assertNotIn('_auth_user_id', self.client.session)

        self.client.force_login(user)
        request_contact_verification(user, 'email')
        code = re.search(r'\b\d{6}\b', mail.outbox[-1].body).group()
        self.assertTrue(confirm_contact_verification(user, 'email', code))
        get_user_model().objects.create_user(
            username='unverified-duplicate', email=user.email,
            password='Different-Strong-Password-9362!',
        )
        self.client.post(reverse('accounts:logout'))
        fail = self.client.post(reverse('accounts:login'), {
            'username': 'SYNTHETIC.USER@EXAMPLE.INVALID',
            'password': 'Different-Strong-Password-9362!',
        })
        self.assertEqual(fail.status_code, 200)
        self.assertNotIn('_auth_user_id', self.client.session)
        success = self.client.post(reverse('accounts:login'), {
            'username': 'SYNTHETIC.USER@EXAMPLE.INVALID',
            'password': 'Synthetic-Password-9362!',
        })
        self.assertRedirects(success, reverse('marketplace:client_dashboard'),
                             fetch_redirect_response=False)
        self.assertEqual(int(self.client.session['_auth_user_id']), user.pk)

    @override_settings(ZEMIPRO_CONTACT_DELIVERY_MODE='test-email')
    def test_verified_email_alias_does_not_disable_same_text_username(self):
        self.register()
        verified = get_user_model().objects.get(username='synthetic-registrant')
        request_contact_verification(verified, 'email')
        code = re.search(r'\b\d{6}\b', mail.outbox[-1].body).group()
        self.assertTrue(confirm_contact_verification(verified, 'email', code))
        collision = get_user_model().objects.create_user(
            username=verified.email,
            password='Collision-Strong-Password-9362!',
        )
        self.client.post(reverse('accounts:logout'))

        exact = self.client.post(reverse('accounts:login'), {
            'username': collision.username,
            'password': 'Collision-Strong-Password-9362!',
        })
        self.assertEqual(exact.status_code, 302)
        self.assertEqual(int(self.client.session['_auth_user_id']), collision.pk)
        self.client.post(reverse('accounts:logout'))

        alias = self.client.post(reverse('accounts:login'), {
            'username': verified.email,
            'password': 'Synthetic-Password-9362!',
        })
        self.assertEqual(alias.status_code, 302)
        self.assertEqual(int(self.client.session['_auth_user_id']), verified.pk)

    def test_verified_phone_login_requires_the_original_confirmed_number(self):
        self.register(email='')
        user = get_user_model().objects.get(username='synthetic-registrant')
        self.client.post(reverse('accounts:logout'))
        denied = self.client.post(reverse('accounts:login'), {
            'username': '050-123-4567', 'password': 'Synthetic-Password-9362!',
        })
        self.assertEqual(denied.status_code, 200)

        self.client.force_login(user)
        with patch('apps.accounts.verification.deliver_contact_code',
                   return_value=True) as adapter:
            self.assertTrue(request_contact_verification(user, 'phone'))
        code = adapter.call_args.args[2]
        self.assertTrue(confirm_contact_verification(user, 'phone', code))
        self.client.post(reverse('accounts:logout'))
        successful = self.client.post(reverse('accounts:login'), {
            'username': '+972 50 123 4567',
            'password': 'Synthetic-Password-9362!',
        })
        self.assertRedirects(successful, reverse('marketplace:client_dashboard'),
                             fetch_redirect_response=False)
        self.assertEqual(int(self.client.session['_auth_user_id']), user.pk)

    def test_login_blocked_user_denied_and_logout_post_only(self):
        user = get_user_model().objects.create_user(
            username='blocked', password='Synthetic-Password-9362!',
        )
        user.is_blocked = True
        user.save(update_fields=['is_blocked'])
        rejected = self.client.post(reverse('accounts:login'), {
            'username': user.username, 'password': 'Synthetic-Password-9362!',
        })
        self.assertEqual(rejected.status_code, 200)
        self.assertNotIn('_auth_user_id', self.client.session)
        user.is_blocked = False
        user.save(update_fields=['is_blocked'])
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse('accounts:logout')).status_code, 405)
        self.assertEqual(self.client.post(reverse('accounts:logout')).status_code, 302)
        self.assertNotIn('_auth_user_id', self.client.session)

    @override_settings(ZEMIPRO_CONTACT_DELIVERY_MODE='test-email')
    def test_email_code_is_one_use_and_recovery_requires_verified_claim(self):
        self.register()
        user = get_user_model().objects.get(username='synthetic-registrant')
        req = self.client.post(reverse('accounts:request_verification'), {
            'channel': 'email',
        })
        self.assertRedirects(req, reverse('accounts:contact_verification'))
        self.assertEqual(len(mail.outbox), 1)
        code = re.search(r'\b\d{6}\b', mail.outbox[-1].body).group()
        challenge = ContactChallenge.objects.get(user=user, channel='email')
        self.assertNotIn(code, challenge.code_digest)
        self.assertNotIn(user.email, challenge.destination_digest)
        self.assertTrue(ContactDeliveryEvent.objects.filter(
            user=user, outcome='sent',
        ).exists())
        self.assertFalse(VerifiedContact.objects.exists())

        # Recovery before confirmation is generic and sends no reset link.
        unverified = self.client.post(reverse('accounts:password_reset'), {
            'email': user.email,
        })
        self.assertRedirects(unverified, reverse('accounts:password_reset_done'))
        self.assertEqual(len(mail.outbox), 1)

        bad = self.client.post(reverse('accounts:confirm_verification'), {
            'channel': 'email', 'code': '999999' if code != '999999' else '999998',
        })
        self.assertRedirects(bad, reverse('accounts:contact_verification'))
        self.assertIsNone(get_user_model().objects.get(pk=user.pk).email_verified_at)
        ok = self.client.post(reverse('accounts:confirm_verification'), {
            'channel': 'email', 'code': code,
        })
        self.assertRedirects(ok, reverse('accounts:contact_verification'))
        user.refresh_from_db()
        self.assertIsNotNone(user.email_verified_at)
        self.assertEqual(VerifiedContact.objects.filter(user=user).count(), 1)
        self.assertFalse(ContactChallenge.objects.filter(user=user).exists())
        self.assertFalse(confirm_contact_verification(user, 'email', code))

        self.client.post(reverse('accounts:password_reset'), {'email': user.email})
        self.assertEqual(len(mail.outbox), 2)
        self.assertIn('/accounts/reset/', mail.outbox[-1].body)
        self.assertNotIn(code, mail.outbox[-1].body)

        # Complete the one-use Django reset link and confirm the new password.
        url = re.search(r'https?://[^\s]+', mail.outbox[-1].body).group()
        first = self.client.get(urlparse(url).path)
        self.assertEqual(first.status_code, 302)
        second = self.client.get(first['Location'])
        self.assertEqual(second.status_code, 200)
        self.assertContains(second, 'type="password"')
        saved = self.client.post(first['Location'], {
            'new_password1': 'Updated-Strong-Password-9362!',
            'new_password2': 'Updated-Strong-Password-9362!',
        })
        self.assertRedirects(saved, reverse('accounts:password_reset_complete'))
        self.client.post(reverse('accounts:logout'))
        self.assertTrue(self.client.login(
            username=user.username,
            password='Updated-Strong-Password-9362!',
        ))

    def test_sms_mock_confirmation_never_persists_the_code_or_raw_phone(self):
        self.register(email='')
        user = get_user_model().objects.get(username='synthetic-registrant')
        with patch('apps.accounts.verification.deliver_contact_code',
                   return_value=True) as delivery:
            self.assertTrue(request_contact_verification(user, 'phone'))
        channel, destination, code = delivery.call_args.args
        self.assertEqual((channel, destination), ('phone', '+972501234567'))
        self.assertTrue(re.fullmatch(r'\d{6}', code))
        self.assertTrue(confirm_contact_verification(user, 'phone', code))
        user.refresh_from_db()
        self.assertIsNotNone(user.phone_verified_at)
        audit = ContactDeliveryEvent.objects.get(user=user)
        self.assertEqual(audit.outcome, 'sent')
        self.assertNotIn(destination, audit.destination_digest)
        self.assertNotIn(code, audit.destination_digest)
        self.assertFalse(ContactChallenge.objects.filter(user=user).exists())

    def test_delivery_disabled_is_fail_closed_without_claim(self):
        self.register(email='no-delivery@example.invalid', phone='')
        user = get_user_model().objects.get(username='synthetic-registrant')
        self.assertFalse(request_contact_verification(user, 'email'))
        self.assertFalse(ContactChallenge.objects.exists())
        self.assertFalse(VerifiedContact.objects.exists())
        self.assertEqual(ContactDeliveryEvent.objects.get().outcome, 'unavailable')

    @override_settings(ZEMIPRO_CONTACT_DELIVERY_MODE='test-email')
    def test_expired_code_and_five_failed_guesses_cannot_verify(self):
        self.register()
        user = get_user_model().objects.get(username='synthetic-registrant')
        request_contact_verification(user, 'email')
        code = re.search(r'\b\d{6}\b', mail.outbox[-1].body).group()
        bad_code = '123456' if code != '123456' else '654321'
        for _ in range(5):
            self.assertFalse(confirm_contact_verification(user, 'email', bad_code))
        self.assertFalse(confirm_contact_verification(user, 'email', code))
        ContactChallenge.objects.filter(user=user).update(
            expires_at=timezone.now() - timedelta(seconds=1), attempts=0,
        )
        self.assertFalse(confirm_contact_verification(user, 'email', code))
        self.assertFalse(VerifiedContact.objects.exists())

    @override_settings(ZEMIPRO_CONTACT_DELIVERY_MODE='test-email')
    def test_resend_cooldown_and_opaque_delivery_audit(self):
        self.register()
        user = get_user_model().objects.get(username='synthetic-registrant')
        self.assertTrue(request_contact_verification(user, 'email'))
        with self.assertRaisesMessage(ValueError, 'Повторите запрос позже'):
            request_contact_verification(user, 'email')
        self.assertEqual(len(mail.outbox), 1)
        event = ContactDeliveryEvent.objects.get(user=user)
        self.assertEqual(len(event.destination_digest), 64)
        self.assertNotIn('synthetic.user@example.invalid', event.destination_digest)

    @override_settings(ZEMIPRO_CONTACT_DELIVERY_MODE='test-email')
    def test_duplicated_unverified_contact_cannot_steal_verified_email(self):
        self.register()
        verified = get_user_model().objects.get(username='synthetic-registrant')
        request_contact_verification(verified, 'email')
        code = re.search(r'\b\d{6}\b', mail.outbox[-1].body).group()
        self.assertTrue(confirm_contact_verification(verified, 'email', code))
        other = get_user_model().objects.create_user(
            username='other', email=verified.email,
            password='Synthetic-Password-9362!',
        )
        with self.assertRaisesMessage(ValueError, 'Контакт уже подтверждён'):
            request_contact_verification(other, 'email')
        self.assertEqual(VerifiedContact.objects.count(), 1)
        mail.outbox.clear()
        self.client.post(reverse('accounts:password_reset'), {
            'email': verified.email,
        })
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(VerifiedContact.objects.get().user_id, verified.pk)

    @override_settings(ZEMIPRO_CONTACT_DELIVERY_MODE='test-email')
    def test_changing_email_without_reverification_disables_recovery(self):
        self.register()
        user = get_user_model().objects.get(username='synthetic-registrant')
        request_contact_verification(user, 'email')
        code = re.search(r'\b\d{6}\b', mail.outbox[-1].body).group()
        self.assertTrue(confirm_contact_verification(user, 'email', code))
        get_user_model().objects.filter(pk=user.pk).update(
            email='new-address@example.invalid',
        )
        mail.outbox.clear()
        self.client.post(reverse('accounts:password_reset'), {
            'email': 'new-address@example.invalid',
        })
        self.assertEqual(len(mail.outbox), 0)

    def test_csrf_and_login_required_on_verification_endpoints(self):
        self.assertEqual(
            self.client.post(reverse('accounts:request_verification'), {
                'channel': 'email',
            }).status_code, 302,
        )
        self.register()
        guarded = Client(enforce_csrf_checks=True)
        guarded.force_login(
            get_user_model().objects.get(username='synthetic-registrant')
        )
        for name, data in (
            ('accounts:request_verification', {'channel': 'email'}),
            ('accounts:confirm_verification',
             {'channel': 'email', 'code': '123456'}),
        ):
            with self.subTest(name=name):
                self.assertEqual(guarded.post(reverse(name), data).status_code, 403)
        self.assertEqual(
            self.client.get(reverse('accounts:request_verification')).status_code,
            405,
        )
        self.assertEqual(
            self.client.get(reverse('accounts:confirm_verification')).status_code,
            405,
        )

    def test_phone_only_account_can_reset_password_with_verified_sms_mock(self):
        self.register(email='')
        user = get_user_model().objects.get(username='synthetic-registrant')
        url = reverse('accounts:phone_recovery')
        credentials = {'username': user.username, 'phone': '050-123-4567'}

        # An unverified input never becomes a recovery identity.
        with patch('apps.accounts.verification.deliver_contact_code',
                   return_value=True) as adapter:
            before = self.client.post(url, credentials)
        self.assertRedirects(before, reverse('accounts:phone_recovery_confirm'))
        adapter.assert_not_called()
        self.assertFalse(ContactChallenge.objects.exists())

        with patch('apps.accounts.verification.deliver_contact_code',
                   return_value=True) as adapter:
            self.assertTrue(request_contact_verification(user, 'phone'))
        verify_code = adapter.call_args.args[2]
        self.assertTrue(confirm_contact_verification(user, 'phone', verify_code))
        self.client.post(reverse('accounts:logout'))

        with patch('apps.accounts.verification.deliver_contact_code',
                   return_value=True) as adapter:
            requested = self.client.post(url, credentials)
        self.assertRedirects(requested, reverse('accounts:phone_recovery_confirm'))
        code = adapter.call_args.args[2]
        self.assertEqual(adapter.call_args.args[:2], ('phone', '+972501234567'))
        self.assertTrue(re.fullmatch(r'\d{6}', code))

        confirm = reverse('accounts:phone_recovery_confirm')
        denied = self.client.post(confirm, {
            **credentials, 'code': '000000' if code != '000000' else '000001',
            'new_password1': 'Updated-Strong-Phone-9362!',
            'new_password2': 'Updated-Strong-Phone-9362!',
        })
        self.assertEqual(denied.status_code, 200)
        user.refresh_from_db()
        self.assertTrue(user.check_password('Synthetic-Password-9362!'))

        weak = self.client.post(confirm, {
            **credentials, 'code': code,
            'new_password1': '12345', 'new_password2': '12345',
        })
        self.assertEqual(weak.status_code, 200)
        user.refresh_from_db()
        self.assertTrue(user.check_password('Synthetic-Password-9362!'))

        recovered = self.client.post(confirm, {
            **credentials, 'code': code,
            'new_password1': 'Updated-Strong-Phone-9362!',
            'new_password2': 'Updated-Strong-Phone-9362!',
        })
        self.assertRedirects(recovered, reverse('accounts:login'))
        user.refresh_from_db()
        self.assertTrue(user.check_password('Updated-Strong-Phone-9362!'))
        self.assertFalse(ContactChallenge.objects.filter(user=user).exists())
        self.assertFalse(self.client.login(username=user.username,
                                           password='Synthetic-Password-9362!'))
        self.assertTrue(self.client.login(username=user.username,
                                          password='Updated-Strong-Phone-9362!'))
        self.assertEqual(self.client.post(confirm, {
            **credentials, 'code': code,
            'new_password1': 'Other-Strong-Phone-9362!',
            'new_password2': 'Other-Strong-Phone-9362!',
        }).status_code, 200)

    def test_phone_recovery_has_generic_unknown_user_response_and_csrf(self):
        url = reverse('accounts:phone_recovery')
        with patch('apps.accounts.verification.deliver_contact_code',
                   return_value=True) as adapter:
            response = self.client.post(url, {
                'username': 'unknown-synthetic-account', 'phone': '0501234567',
            })
        self.assertRedirects(response, reverse('accounts:phone_recovery_confirm'))
        adapter.assert_not_called()
        self.assertFalse(ContactDeliveryEvent.objects.exists())
        guarded = Client(enforce_csrf_checks=True)
        self.assertEqual(guarded.post(url, {
            'username': 'unknown', 'phone': '0501234567',
        }).status_code, 403)
        self.assertEqual(guarded.post(reverse('accounts:phone_recovery_confirm'), {
            'username': 'unknown', 'phone': '0501234567',
            'code': '123456', 'new_password1': 'Synthetic-Strong-9362!',
            'new_password2': 'Synthetic-Strong-9362!',
        }).status_code, 403)

    def test_credential_reset_throttle_is_per_ip_and_opaque(self):
        url = reverse('accounts:password_reset')
        for _ in range(5):
            self.assertEqual(self.client.post(
                url, {'email': 'absent@example.invalid'}, REMOTE_ADDR='192.0.2.142',
            ).status_code, 302)
        refused = self.client.post(
            url, {'email': 'absent@example.invalid'}, REMOTE_ADDR='192.0.2.142',
        )
        self.assertEqual(refused.status_code, 429)
        self.assertIn('Retry-After', refused)
