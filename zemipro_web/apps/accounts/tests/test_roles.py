"""Stage 03.1 — synthetic multi-role/account permissions regressions."""
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils.translation import override

from apps.accounts.models import ClientProfile, WorkerProfile
from apps.accounts.services import (
    create_or_update_client_profile, create_or_update_worker_profile,
)
from apps.locations.models import City
from apps.marketplace.models import Category, Order
from apps.marketplace.tests.factories import make_order


@override_settings(ZEMIPRO_PILOT_CITY_SLUG='ashdod')
class MultiRoleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.city = City.objects.create(slug='ashdod', name_ru='Ашдод')
        cls.other_city = City.objects.create(slug='ashkelon', name_ru='Ашкелон')
        cls.category = Category.objects.create(slug='synthetic-role-skill', name_ru='Тестовая услуга')

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='both-roles', password='Strong-synthetic-9362'
        )
        self.url = reverse('accounts:switch_role')

    def test_switch_requires_session_post_and_csrf(self):
        self.assertEqual(self.client.post(self.url, {'role': 'worker'}).status_code, 302)
        self.user.refresh_from_db()
        self.assertEqual(self.user.active_role, 'client')
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self.url).status_code, 405)
        guarded = Client(enforce_csrf_checks=True)
        guarded.force_login(self.user)
        self.assertEqual(guarded.post(self.url, {'role': 'worker'}).status_code, 403)
        self.user.refresh_from_db()
        self.assertEqual(self.user.active_role, 'client')

    def test_worker_switch_does_not_create_public_empty_worker_profile(self):
        self.client.force_login(self.user)
        response = self.client.post(self.url, {'role': 'worker'})
        self.assertRedirects(response, reverse('accounts:worker_profile'))
        self.user.refresh_from_db()
        self.assertEqual(self.user.active_role, 'worker')
        self.assertFalse(self.user.is_worker)
        self.assertFalse(WorkerProfile.objects.filter(user=self.user).exists())
        self.assertEqual(self.user.role, 'client')

    def test_invalid_role_cannot_escalate_to_admin(self):
        self.client.force_login(self.user)
        for forged in ('admin', 'moderator', 'both', '', 'WORKER'):
            with self.subTest(forged=forged):
                self.assertEqual(self.client.post(self.url, {'role': forged}).status_code, 400)
        self.user.refresh_from_db()
        self.assertEqual(self.user.active_role, 'client')
        self.assertEqual(self.user.role, 'client')
        self.assertFalse(self.user.is_staff)
        self.assertFalse(self.user.is_superuser)

    def test_blocked_user_cannot_switch(self):
        self.client.force_login(self.user)
        get_user_model().objects.filter(pk=self.user.pk).update(is_blocked=True)
        self.assertEqual(self.client.post(self.url, {'role': 'worker'}).status_code, 403)
        self.user.refresh_from_db()
        self.assertEqual(self.user.active_role, 'client')

    def test_both_profiles_and_order_preserved_across_switches(self):
        order = make_order(client=self.user, category=self.category, city=self.city)
        client = create_or_update_client_profile(self.user, {
            'city': self.city, 'contact': 'Synthetic client contact',
        })
        worker = create_or_update_worker_profile(self.user, {
            'city': self.city, 'contact': 'Synthetic worker contact',
            'description': 'A synthetic profile for regression testing.',
            'skills': [self.category], 'service_cities': [self.city],
        })
        self.user.refresh_from_db()
        self.assertEqual(self.user.role, 'client')  # Legacy field preserved.
        self.assertEqual(self.user.active_role, 'worker')
        self.assertTrue(self.user.is_client)
        self.assertTrue(self.user.is_worker)
        self.client.force_login(self.user)
        response = self.client.post(self.url, {'role': 'client'})
        self.assertRedirects(response, reverse('marketplace:client_dashboard'))
        self.user.refresh_from_db()
        self.assertEqual(self.user.active_role, 'client')
        self.assertTrue(self.user.is_worker)
        self.assertEqual(ClientProfile.objects.get(user=self.user).pk, client.pk)
        self.assertEqual(WorkerProfile.objects.get(user=self.user).pk, worker.pk)
        self.assertEqual(WorkerProfile.objects.get(pk=worker.pk).service_cities.count(), 1)
        self.assertEqual(Order.objects.get(pk=order.pk).client_id, self.user.pk)
        response = self.client.post(self.url, {'role': 'worker'})
        self.assertRedirects(response, reverse('marketplace:worker_dashboard'))
        self.assertEqual(get_user_model().objects.count(), 1)
        self.assertEqual(WorkerProfile.objects.filter(user=self.user).count(), 1)

    def test_switch_labels_use_existing_english_and_hebrew_translations(self):
        self.client.force_login(self.user)
        for language, worker_label, client_label in (
            ('en', 'Professional dashboard', 'Customer dashboard'),
            ('he', 'אזור אישי לאיש מקצוע', 'אזור אישי ללקוח'),
        ):
            with self.subTest(language=language), override(language):
                page = self.client.get(reverse('marketplace:home'),
                                       HTTP_ACCEPT_LANGUAGE=language)
                self.assertContains(page, f'aria-label="{worker_label}"')
                self.assertContains(page, f'⇄ {worker_label}')
        self.client.post(self.url, {'role': 'worker'})
        for language, worker_label, client_label in (
            ('en', 'Professional dashboard', 'Customer dashboard'),
            ('he', 'אזור אישי לאיש מקצוע', 'אזור אישי ללקוח'),
        ):
            with self.subTest(language=language), override(language):
                page = self.client.get(reverse('marketplace:home'),
                                       HTTP_ACCEPT_LANGUAGE=language)
                self.assertContains(page, f'aria-label="{client_label}"')
                self.assertContains(page, f'⇄ {client_label}')

    def test_ashdod_gate_and_foreign_profile_not_modified(self):
        other = get_user_model().objects.create_user(username='other-synthetic')
        other_profile = ClientProfile.objects.create(
            user=other, city=self.city, contact='Not exposed to first user'
        )
        self.client.force_login(self.user)
        self.assertEqual(self.client.post(self.url, {'role': 'worker', 'user': other.pk}).status_code, 302)
        self.assertEqual(ClientProfile.objects.get(pk=other_profile.pk).contact,
                         'Not exposed to first user')
        self.assertFalse(WorkerProfile.objects.filter(user=other).exists())
        with self.assertRaises(ValueError):
            create_or_update_worker_profile(self.user, {'city': self.other_city})
        self.assertFalse(WorkerProfile.objects.filter(user=self.user).exists())
