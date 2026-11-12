"""Stage 03.4 — synthetic worker/company publication and security regressions."""
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils.translation import override

from apps.accounts.forms import WorkerProfileForm
from apps.accounts.models import ClientProfile, WorkerProfile
from apps.accounts.services import (
    create_or_update_worker_profile, publication_issue, set_worker_publication,
)
from apps.locations.models import City
from apps.marketplace.models import Category
from apps.marketplace.tests.factories import make_order


@override_settings(ZEMIPRO_PILOT_CITY_SLUG='ashdod')
class WorkerPublicationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.city = City.objects.create(
            slug='ashdod', name_ru='Ашдод', name_en='Ashdod', name_he='אשדוד',
        )
        cls.other_city = City.objects.create(slug='ashkelon', name_ru='Ашкелон')
        cls.category = Category.objects.create(
            slug='stage03-worker-skill', name_ru='Синтетическая услуга',
        )

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='private-worker-login', email='private@example.invalid',
            phone='+972501234567', password='Strong-synthetic-password',
        )
        self.other = get_user_model().objects.create_user(username='other-account')
        ClientProfile.objects.create(user=self.user, city=self.city)
        self.url = reverse('accounts:worker_profile')
        self.data = {
            'provider_type': 'company',
            'display_name': 'Synthetic Ashdod Company',
            'city': str(self.city.pk),
            'contact': 'NEVER_SHOW_034_CONTACT',
            'description': 'Synthetic company description with sufficient details.',
            'skills': [str(self.category.pk)],
            'service_cities': [str(self.city.pk)],
            'spoken_languages': ['ru', 'he'],
            'pricing_details': 'From 150 ILS, agreed in advance.',
            'availability': 'limited',
            'working_hours': 'Sunday–Thursday, 09:00–17:00',
            'offers_remote': '',
            'receive_notifications': 'on',
        }
        self.client.force_login(self.user)

    def publish(self):
        self.assertRedirects(self.client.post(
            self.url, {**self.data, 'action': 'publish'},
        ), self.url)
        return WorkerProfile.objects.get(user=self.user)

    def test_save_draft_does_not_grant_publication_or_verification(self):
        self.assertRedirects(self.client.post(
            self.url, {**self.data, 'action': 'save',
                       'is_published': '1', 'is_verified': '1',
                       'user': self.other.pk, 'is_staff': '1'},
        ), self.url)
        profile = WorkerProfile.objects.get(user=self.user)
        self.assertEqual(profile.provider_type, 'company')
        self.assertEqual(profile.spoken_languages, ['ru', 'he'])
        self.assertFalse(profile.is_published)
        self.assertFalse(profile.is_verified)
        self.assertEqual(profile.user_id, self.user.pk)
        self.assertEqual(self.client.get(reverse(
            'marketplace:worker_public_profile', args=[profile.pk],
        )).status_code, 404)

    def test_company_public_profile_no_private_contacts_three_locales(self):
        profile = self.publish()
        self.assertTrue(profile.is_published)
        self.assertIsNotNone(profile.published_at)
        self.assertFalse(profile.is_verified)
        public_url = reverse('marketplace:worker_public_profile', args=[profile.pk])
        for language, direction in (('ru', 'ltr'), ('en', 'ltr'), ('he', 'rtl')):
            with self.subTest(language=language), override(language):
                response = self.client.get(public_url, HTTP_ACCEPT_LANGUAGE=language)
                self.assertContains(response, f'dir="{direction}"')
                self.assertContains(response, 'Synthetic Ashdod Company')
                self.assertContains(response, '150 ILS')
                for sensitive in (
                    'NEVER_SHOW_034_CONTACT', 'private@example.invalid',
                    '+972501234567', 'private-worker-login',
                ):
                    self.assertNotContains(response, sensitive)
        category = self.client.get(reverse(
            'marketplace:category_detail', args=[self.category.slug],
        ))
        self.assertContains(category, 'Synthetic Ashdod Company')
        self.assertNotContains(category, 'NEVER_SHOW_034_CONTACT')

    def test_unpublish_preserves_existing_order_and_hides_every_public_route(self):
        profile = self.publish()
        order = make_order(client=self.user, category=self.category, city=self.city)
        self.assertRedirects(self.client.post(
            self.url, {'action': 'unpublish'},
        ), self.url)
        profile.refresh_from_db()
        self.assertFalse(profile.is_published)
        self.assertIsNone(profile.published_at)
        self.assertEqual(self.client.get(reverse(
            'marketplace:worker_public_profile', args=[profile.pk],
        )).status_code, 404)
        for url in (
            reverse('marketplace:category_detail', args=[self.category.slug]),
            reverse('marketplace:city_detail', args=[self.city.slug]),
        ):
            self.assertNotContains(self.client.get(url), 'Synthetic Ashdod Company')
        order.refresh_from_db()
        self.assertEqual(order.client_id, self.user.pk)
        self.assertEqual(WorkerProfile.objects.filter(user=self.user).count(), 1)

    def test_incomplete_draft_and_inactive_skill_cannot_publish(self):
        draft = create_or_update_worker_profile(
            self.user, {'display_name': 'Incomplete'},
        )
        self.assertIsNotNone(publication_issue(draft))
        with self.assertRaises(ValueError):
            set_worker_publication(self.user, True)
        bad = self.client.post(
            self.url, {**self.data, 'action': 'publish', 'pricing_details': ''},
        )
        self.assertContains(bad, 'Укажите ориентировочные цены')
        draft.refresh_from_db()
        self.assertFalse(draft.is_published)
        profile = self.publish()
        self.category.is_active = False
        self.category.save(update_fields=['is_active'])
        profile.is_published = False
        profile.save(update_fields=['is_published'])
        with self.assertRaises(ValueError):
            set_worker_publication(self.user, True)

    def test_blocked_account_cannot_save_or_publish(self):
        profile = self.publish()
        get_user_model().objects.filter(pk=self.user.pk).update(is_blocked=True)
        self.assertEqual(
            self.client.post(self.url, {'action': 'unpublish'}).status_code, 403,
        )
        self.assertEqual(self.client.post(self.url, {
            **self.data, 'action': 'save',
        }).status_code, 403)
        with self.assertRaises(PermissionDenied):
            set_worker_publication(self.user, True)
        self.assertEqual(self.client.get(reverse(
            'marketplace:worker_public_profile', args=[profile.pk],
        )).status_code, 404)

    def test_other_user_cannot_edit_or_unpublish_by_forged_id(self):
        profile = self.publish()
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(self.url, {
            'action': 'unpublish', 'user_id': self.user.pk, 'profile_id': profile.pk,
        }).status_code, 400)
        profile.refresh_from_db()
        self.assertTrue(profile.is_published)
        self.assertRedirects(self.client.post(
            self.url, {**self.data, 'action': 'save', 'profile_id': profile.pk},
        ), self.url)
        profile.refresh_from_db()
        self.assertEqual(profile.display_name, 'Synthetic Ashdod Company')
        self.assertEqual(WorkerProfile.objects.filter(user=self.other).count(), 1)

    def test_non_ashdod_city_rejected_in_form_and_service(self):
        self.assertFalse(WorkerProfileForm({
            **self.data, 'city': str(self.other_city.pk),
        }).is_valid())
        with self.assertRaises(ValueError):
            create_or_update_worker_profile(self.user, {
                'city': self.other_city, 'display_name': 'Cannot serve city',
            })
        self.assertFalse(WorkerProfile.objects.filter(user=self.user).exists())
        self.assertEqual(list(WorkerProfileForm().fields['city'].queryset.values_list(
            'slug', flat=True,
        )), ['ashdod'])

    def test_edit_removing_required_language_unpublishes(self):
        profile = self.publish()
        self.assertRedirects(self.client.post(
            self.url, {**self.data, 'action': 'save', 'spoken_languages': []},
        ), self.url)
        profile.refresh_from_db()
        self.assertFalse(profile.is_published)
        self.assertEqual(profile.spoken_languages, [])

    def test_guest_get_csrf_and_invalid_action(self):
        self.client.logout()
        self.assertEqual(self.client.post(
            self.url, {**self.data, 'action': 'publish'},
        ).status_code, 302)
        self.client.force_login(self.user)
        self.assertEqual(self.client.post(
            self.url, {'action': 'admin'},
        ).status_code, 400)
        secure = Client(enforce_csrf_checks=True)
        secure.force_login(self.user)
        self.assertEqual(secure.post(
            self.url, {**self.data, 'action': 'publish'},
        ).status_code, 403)
        self.assertFalse(WorkerProfile.objects.filter(user=self.user).exists())
