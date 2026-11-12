"""Stage 03.3: owner-only client preferences and privacy requests."""
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.client_settings import (
    request_own_privacy_action, save_client_settings,
)
from apps.accounts.models import (
    ClientProfile, ContactChallenge, PrivacyRequest, VerifiedContact,
    WorkerProfile,
)
from apps.accounts.verification import contact_fingerprint
from apps.locations.models import City
from apps.marketplace.models import Category, Order
from apps.marketplace.tests.factories import make_order


@override_settings(ZEMIPRO_PILOT_CITY_SLUG='ashdod')
class ClientSettingsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ashdod = City.objects.create(slug='ashdod', name_ru='Ашдод')
        cls.other_city = City.objects.create(
            slug='ashkelon', name_ru='Ашкелон',
        )
        cls.cat = Category.objects.create(
            slug='synthetic-settings', name_ru='Тестовая категория',
        )

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='settings-customer',
            email='old@example.invalid',
            phone='+972501234567',
            password='Synthetic-Strong-9362',
        )
        self.profile = ClientProfile.objects.create(
            user=self.user, city=self.ashdod,
            contact='My private contact',
        )
        self.other_user = get_user_model().objects.create_user(
            username='other-customer', password='Synthetic-Other-9362',
            email='other@example.invalid',
        )
        self.other_profile = ClientProfile.objects.create(
            user=self.other_user, city=self.ashdod,
            contact='TOP-SECRET-OTHER-CONTACT',
        )
        self.order = make_order(
            client=self.user, city=self.ashdod, category=self.cat,
            address='Private synthetic account order address',
        )
        self.other_order = make_order(
            client=self.other_user, city=self.ashdod, category=self.cat,
            address='OTHER-SECRET-ORDER-ADDRESS',
        )
        self.url = reverse('accounts:client_settings')
        self.privacy_url = reverse('accounts:client_privacy_request')

    def _form(self, **overrides):
        values = {
            'first_name': 'ClientFirst',
            'last_name': 'ClientLast',
            'email': 'old@example.invalid',
            'phone': '+972501234567',
            'preferred_language': 'en',
            'city': str(self.ashdod.pk),
            'contact': 'My updated private contact',
            'receive_optional_updates': 'on',
        }
        values.update(overrides)
        return values

    def test_guest_is_redirected_and_other_data_never_in_response(self):
        self.assertEqual(self.client.get(self.url).status_code, 302)
        self.assertEqual(self.client.post(self.url, self._form()).status_code, 302)
        self.assertEqual(self.client.post(self.privacy_url, {
            'kind': 'delete',
        }).status_code, 302)
        self.client.force_login(self.user)
        result = self.client.get(self.url)
        self.assertEqual(result.status_code, 200)
        self.assertContains(result, 'old@example.invalid')
        self.assertContains(result, 'My private contact')
        self.assertNotContains(result, 'TOP-SECRET-OTHER-CONTACT')
        self.assertNotContains(result, 'OTHER-SECRET-ORDER-ADDRESS')
        self.assertIn('no-store', result['Cache-Control'])

    def test_save_only_owner_and_keep_related_orders_worker_identity(self):
        worker = WorkerProfile.objects.create(
            user=self.user, city=self.ashdod, contact='Worker-private',
        )
        self.client.force_login(self.user)
        res = self.client.post(self.url, self._form(
            user_id=str(self.other_user.pk), role='admin',
            is_staff='1', password='poison',
        ))
        self.assertRedirects(res, self.url)
        self.user.refresh_from_db()
        self.profile.refresh_from_db()
        self.other_profile.refresh_from_db()
        self.assertEqual(self.user.first_name, 'ClientFirst')
        self.assertEqual(self.user.last_name, 'ClientLast')
        self.assertEqual(self.user.preferred_language, 'en')
        self.assertEqual(self.user.role, 'client')
        self.assertFalse(self.user.is_staff)
        self.assertTrue(self.user.check_password('Synthetic-Strong-9362'))
        self.assertEqual(self.profile.contact, 'My updated private contact')
        self.assertTrue(self.profile.receive_optional_updates)
        self.assertEqual(self.other_profile.contact, 'TOP-SECRET-OTHER-CONTACT')
        self.assertEqual(Order.objects.get(pk=self.order.pk).client_id, self.user.pk)
        self.assertEqual(Order.objects.get(pk=self.other_order.pk).client_id,
                         self.other_user.pk)
        self.assertEqual(WorkerProfile.objects.get(pk=worker.pk).contact,
                         'Worker-private')
        self.assertEqual(self.client.cookies['django_language'].value, 'en')

    def test_explicit_language_and_optional_notifications_choice(self):
        self.client.force_login(self.user)
        response = self.client.post(self.url, self._form(
            preferred_language='he', receive_optional_updates='',
        ))
        self.assertRedirects(response, self.url)
        self.user.refresh_from_db()
        self.profile.refresh_from_db()
        self.assertEqual(self.user.preferred_language, 'he')
        self.assertFalse(self.profile.receive_optional_updates)
        self.assertEqual(self.client.cookies['django_language'].value, 'he')
        # Operational in-site notifications remain intact, preference only
        # controls future optional external delivery.
        from apps.notifications.services import create_notification
        note = create_notification(
            recipient=self.user, title='Synthetic',
            message='Private event', notification_type='system',
        )
        self.assertIsNotNone(note.pk)
        self.assertEqual(note.recipient_id, self.user.pk)

    def test_changed_email_and_phone_revoke_old_claims_and_challenges(self):
        self.user.email_verified_at = timezone.now()
        self.user.phone_verified_at = timezone.now()
        self.user.save(update_fields=['email_verified_at', 'phone_verified_at'])
        VerifiedContact.objects.create(
            user=self.user, channel='email',
            fingerprint=contact_fingerprint('email', self.user.email),
        )
        VerifiedContact.objects.create(
            user=self.user, channel='phone',
            fingerprint=contact_fingerprint('phone', self.user.phone),
        )
        self.client.force_login(self.user)
        post = self.client.post(self.url, self._form(
            email='NEW@Example.Invalid',
            phone='052-123-4567',
        ))
        self.assertRedirects(post, self.url)
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, 'new@example.invalid')
        self.assertEqual(self.user.phone, '+972521234567')
        self.assertIsNone(self.user.email_verified_at)
        self.assertIsNone(self.user.phone_verified_at)
        self.assertFalse(VerifiedContact.objects.filter(user=self.user).exists())
        self.assertFalse(ContactChallenge.objects.filter(user=self.user).exists())
        self.assertEqual(self.client.session['_auth_user_id'], str(self.user.pk))

    def test_unchanged_contacts_keep_verification_and_claims(self):
        self.user.email_verified_at = timezone.now()
        self.user.save(update_fields=['email_verified_at'])
        claim = VerifiedContact.objects.create(
            user=self.user, channel='email',
            fingerprint=contact_fingerprint('email', self.user.email),
        )
        self.client.force_login(self.user)
        self.assertRedirects(self.client.post(
            self.url, self._form(first_name='Another'),
        ), self.url)
        self.user.refresh_from_db()
        self.assertIsNotNone(self.user.email_verified_at)
        self.assertTrue(VerifiedContact.objects.filter(pk=claim.pk).exists())

    def test_reject_nonpilot_city_invalid_language_and_empty_contact(self):
        self.client.force_login(self.user)
        for changes in (
            {'city': str(self.other_city.pk)},
            {'preferred_language': 'zz'},
            {'email': '', 'phone': ''},
        ):
            with self.subTest(changes=changes):
                response = self.client.post(self.url, self._form(**changes))
                self.assertEqual(response.status_code, 200)
                self.user.refresh_from_db()
                self.profile.refresh_from_db()
                self.assertEqual(self.user.first_name, '')
                self.assertEqual(self.profile.contact, 'My private contact')
                self.assertEqual(self.profile.city_id, self.ashdod.pk)
        with self.assertRaises(ValueError):
            save_client_settings(self.user, {
                'city': self.other_city, 'first_name': 'Forged',
                'email': self.user.email, 'phone': self.user.phone,
                'preferred_language': 'ru',
            })
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, '')

    def test_privacy_requests_are_owned_idempotent_and_non_destructive(self):
        self.client.force_login(self.user)
        for kind in ('export', 'delete'):
            self.assertRedirects(self.client.post(
                self.privacy_url, {'kind': kind, 'user_id': self.other_user.pk},
            ), self.url)
        self.assertRedirects(self.client.post(
            self.privacy_url, {'kind': 'export'},
        ), self.url)
        own = PrivacyRequest.objects.filter(user=self.user)
        self.assertEqual(own.count(), 2)
        self.assertFalse(PrivacyRequest.objects.filter(
            user=self.other_user,
        ).exists())
        self.assertTrue(get_user_model().objects.filter(pk=self.user.pk).exists())
        self.assertTrue(Order.objects.filter(pk=self.order.pk).exists())
        self.assertEqual(self.client.post(
            self.privacy_url, {'kind': 'unsafe'}, 
        ).status_code, 400)

        self.client.force_login(self.other_user)
        page = self.client.get(self.url)
        self.assertNotContains(page, 'settings-customer')
        self.assertNotContains(page, 'My private contact')
        self.assertEqual(page.context['privacy_requests'].count(), 0)
        self.assertEqual(
            request_own_privacy_action(self.other_user, 'export').user_id,
            self.other_user.pk,
        )

    def test_blocked_owner_cannot_read_or_update_privacy(self):
        self.client.force_login(self.user)
        get_user_model().objects.filter(pk=self.user.pk).update(is_blocked=True)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.post(self.url, self._form()).status_code, 403)
        self.assertEqual(self.client.post(self.privacy_url, {
            'kind': 'export',
        }).status_code, 403)
        with self.assertRaises(PermissionDenied):
            request_own_privacy_action(self.user, 'delete')

    def test_mutation_requires_csrf(self):
        guarded = Client(enforce_csrf_checks=True)
        guarded.force_login(self.user)
        self.assertEqual(guarded.post(self.url, self._form()).status_code, 403)
        self.assertEqual(guarded.post(self.privacy_url, {
            'kind': 'delete',
        }).status_code, 403)
        self.assertEqual(self.client.get(self.privacy_url).status_code, 302)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self.privacy_url).status_code, 405)
