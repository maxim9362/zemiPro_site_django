"""Stage 05.5: synthetic public profiles, private favorites/history and locale UX."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.db import close_old_connections, connections
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import override

from apps.accounts.client_favorites import set_own_favorite
from apps.accounts.models import (
    ClientProfile, FavoriteWorker, WorkerPortfolioPhoto, WorkerProfile,
    WorkerProfileView,
)
from apps.locations.models import City
from apps.marketplace.models import Category, Rating
from apps.marketplace.tests.factories import make_order, make_user


@override_settings(ZEMIPRO_PILOT_CITY_SLUG='ashdod')
class PublicProfileTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.city = City.objects.create(
            slug='ashdod', name_ru='Ашдод', name_en='Ashdod', name_he='אשדוד',
        )
        cls.category = Category.objects.create(
            slug='profile-test-skill', name_ru='Ремонт',
            name_en='Repair', name_he='תיקון', work_mode='onsite',
        )
        cls.owner = make_user('profile-reader', email='reader@example.invalid')
        cls.other = make_user('profile-other', email='other@example.invalid')
        cls.reviewer = make_user('REVIEWER_IDENTITY_PRIVATE')
        ClientProfile.objects.create(user=cls.owner, city=cls.city)
        ClientProfile.objects.create(user=cls.other, city=cls.city)
        cls.worker_user = make_user('profile-worker', email='PRIVATE_USER_EMAIL@example.invalid')
        cls.worker = WorkerProfile.objects.create(
            user=cls.worker_user, city=cls.city, is_published=True,
            display_name='Published specialist',
            description='Synthetic public text with private@example.invalid and +972 50 1234567.',
            contact='CONTACT_NEVER_PUBLIC_555',
            pricing_details='Negotiable', spoken_languages=['ru', 'en', 'he'],
            working_hours='By appointment',
        )
        cls.worker.skills.add(cls.category)
        cls.private_worker_user = make_user('hidden-worker-user')
        cls.hidden = WorkerProfile.objects.create(
            user=cls.private_worker_user, city=cls.city, is_published=False,
            display_name='HIDDEN_PROFILE_555',
            description='Long enough synthetic profile that is not public.',
            pricing_details='Negotiable',
        )
        cls.hidden.skills.add(cls.category)
        WorkerPortfolioPhoto.objects.create(
            worker=cls.worker, file_key='worker-portfolio/' + 'a' * 32 + '.jpg',
            caption='Reach us at photo@example.invalid',
            is_public=True, rights_confirmed_at=timezone.now(),
        )
        review_order = make_order(
            client=cls.reviewer, category=cls.category, city=cls.city,
        )
        Rating.objects.create(
            order=review_order, worker=cls.worker_user,
            client=cls.reviewer, rating=4,
            review_text='My phone is +972 52 1234567.',
        )

    def test_public_profile_masks_contacts_and_authors_and_sets_noindex(self):
        url = reverse('marketplace:worker_public_profile', args=[self.worker.pk])
        response = self.client.get(url + '?arbitrary=do-not-canonicalize')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Published specialist')
        self.assertContains(response, 'name="robots" content="noindex,follow"')
        self.assertContains(
            response, f'<link rel="canonical" href="http://testserver{url}">',
        )
        for secret in (
            'private@example.invalid', 'photo@example.invalid',
            '+972 50 1234567', '+972 52 1234567',
            'REVIEWER_IDENTITY_PRIVATE', 'CONTACT_NEVER_PUBLIC_555',
            'PRIVATE_USER_EMAIL@example.invalid',
        ):
            self.assertNotContains(response, secret)
        self.assertContains(response, 'Примеры работ')
        self.assertContains(response, '4,0/5')

    def test_unpublished_and_blocked_never_visible_even_when_favorited(self):
        self.client.force_login(self.owner)
        url = reverse('marketplace:toggle_favorite_worker', args=[self.worker.pk])
        self.assertEqual(self.client.post(url, {'action': 'add'}).status_code, 302)
        self.client.post(url, {'action': 'add'})
        self.assertEqual(FavoriteWorker.objects.count(), 1)
        self.assertEqual(self.client.post(url, {'action': 'remove'}).status_code, 302)
        self.client.post(url, {'action': 'remove'})
        self.assertFalse(FavoriteWorker.objects.exists())
        self.client.post(url, {'action': 'add'})
        self.worker.is_published = False
        self.worker.save(update_fields=['is_published'])
        self.assertEqual(self.client.get(reverse(
            'marketplace:worker_public_profile', args=[self.worker.pk]
        )).status_code, 404)
        own = self.client.get(reverse('marketplace:client_dashboard'))
        self.assertNotContains(own, 'Published specialist')
        self.assertEqual(self.client.post(url, {'action': 'add'}).status_code, 404)
        self.worker.is_published = True
        self.worker.save(update_fields=['is_published'])
        self.worker_user.is_blocked = True
        self.worker_user.save(update_fields=['is_blocked'])
        self.assertEqual(self.client.get(reverse(
            'marketplace:worker_public_profile', args=[self.worker.pk]
        )).status_code, 404)

    def test_history_default_off_opt_in_owner_only_and_clear(self):
        url = reverse('marketplace:worker_public_profile', args=[self.worker.pk])
        self.client.force_login(self.owner)
        self.client.get(url)
        self.assertFalse(WorkerProfileView.objects.exists())
        settings_url = reverse('accounts:client_settings')
        values = {
            'email': self.owner.email, 'preferred_language': 'ru',
            'city': self.city.pk, 'track_worker_views': 'on',
        }
        self.assertEqual(self.client.post(settings_url, values).status_code, 302)
        self.client.get(url)
        self.client.get(url)
        self.assertEqual(WorkerProfileView.objects.filter(client=self.owner).count(), 1)
        own = self.client.get(reverse('marketplace:client_dashboard'))
        self.assertContains(own, 'Published specialist')
        self.client.force_login(self.other)
        other_page = self.client.get(reverse('marketplace:client_dashboard'))
        self.assertNotContains(other_page, 'Published specialist')
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.owner)
        self.assertEqual(strict.post(reverse('accounts:clear_worker_history')).status_code, 403)
        self.client.force_login(self.owner)
        self.assertEqual(self.client.post(reverse('accounts:clear_worker_history')).status_code, 302)
        self.assertFalse(WorkerProfileView.objects.exists())
        self.client.get(url)
        self.assertEqual(WorkerProfileView.objects.count(), 1)
        self.client.post(settings_url, {
            'email': self.owner.email, 'preferred_language': 'ru',
            'city': self.city.pk,
        })
        self.assertFalse(WorkerProfileView.objects.exists())
        self.assertFalse(ClientProfile.objects.get(user=self.owner).track_worker_views)

    def test_empty_search_never_invents_cards_and_translated_messages(self):
        for language, expected in (('ru', 'изменить'), ('en', 'changing'), ('he', 'לשנות')):
            with self.subTest(language=language), override(language):
                with override(language):
                    url = reverse('catalog_i18n:worker_directory')
                r = self.client.get(url, {'q': 'NO_MATCH_PROFILE_555'},
                                    HTTP_ACCEPT_LANGUAGE=language)
                self.assertEqual(r.status_code, 200)
                self.assertNotContains(r, 'Published specialist')
                self.assertContains(r, expected)
                self.assertContains(r, reverse('marketplace:order_wizard_start'))
                self.assertContains(r, 'noindex,follow')
        invalid = self.client.get(
            reverse('marketplace:worker_directory'), {'language': 'xx'}
        )
        self.assertContains(invalid, 'Сбросить фильтры')

    def test_public_form_csrf_and_private_favorites(self):
        self.client.force_login(self.owner)
        url = reverse('marketplace:toggle_favorite_worker', args=[self.worker.pk])
        self.assertEqual(self.client.post(url, {'action': 'flip'}).status_code, 404)
        self.assertEqual(self.client.get(url).status_code, 404)
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.owner)
        self.assertEqual(strict.post(url, {'action': 'add'}).status_code, 403)
        self.assertFalse(FavoriteWorker.objects.exists())


@override_settings(ZEMIPRO_PILOT_CITY_SLUG='ashdod')
class ConcurrentFavoritesTests(TransactionTestCase):
    def setUp(self):
        self.city = City.objects.create(slug='ashdod', name_ru='Ашдод')
        self.category = Category.objects.create(
            slug='fav-race-category', name_ru='Услуги',
        )
        self.owner = make_user('fav-race-owner')
        worker_user = make_user('fav-race-worker')
        self.worker = WorkerProfile.objects.create(
            user=worker_user, city=self.city, is_published=True,
            display_name='Race worker',
            description='Synthetic published worker for duplicate-favorite test.',
            pricing_details='Negotiable', spoken_languages=['ru'],
        )
        self.worker.skills.add(self.category)

    def test_parallel_add_is_idempotent(self):
        barrier = Barrier(2)

        def add(_):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return set_own_favorite(self.owner, self.worker, saved=True)
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            self.assertEqual(list(executor.map(add, range(2))), [True, True])
        self.assertEqual(FavoriteWorker.objects.count(), 1)
