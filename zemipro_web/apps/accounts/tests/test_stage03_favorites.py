"""Stage 03.3 private favorites: owner scope, pilot boundary and CSRF."""
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import ClientProfile, FavoriteWorker, WorkerProfile
from apps.locations.models import City
from apps.marketplace.models import Category


@override_settings(ZEMIPRO_PILOT_CITY_SLUG='ashdod')
class FavoriteWorkerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ashdod = City.objects.create(slug='ashdod', name_ru='Ашдод')
        cls.foreign_city = City.objects.create(
            slug='ashkelon', name_ru='Ашкелон',
        )
        cls.category = Category.objects.create(
            slug='favorite-service', name_ru='Синтетическая категория',
        )

    def setUp(self):
        self.client_user = get_user_model().objects.create_user(
            username='bookmark-owner',
        )
        self.other_user = get_user_model().objects.create_user(
            username='bookmark-other',
        )
        ClientProfile.objects.create(
            user=self.client_user, city=self.ashdod,
            contact='HIDDEN-OWNER-CONTACT',
        )
        ClientProfile.objects.create(
            user=self.other_user, city=self.ashdod,
            contact='HIDDEN-OTHER-CONTACT',
        )
        self.worker_user = get_user_model().objects.create_user(
            username='favorite-worker',
        )
        self.worker = WorkerProfile.objects.create(
            user=self.worker_user, city=self.ashdod,
            contact='HIDDEN-WORKER-CONTACT', display_name='favorite-worker',
            description='Synthetic published professional profile for favorites.',
            pricing_details='Negotiable', spoken_languages=['ru'], is_published=True,
        )
        self.worker.skills.add(self.category)
        self.foreign_worker = WorkerProfile.objects.create(
            user=get_user_model().objects.create_user(username='offpilot'),
            city=self.foreign_city, contact='SECRET-NONPILOT',
        )
        self.url = reverse('marketplace:toggle_favorite_worker',
                           kwargs={'pk': self.worker.pk})

    def test_login_and_csrf_required_and_get_forbidden(self):
        self.assertEqual(self.client.post(self.url).status_code, 302)
        self.client.force_login(self.client_user)
        self.assertEqual(self.client.get(self.url).status_code, 404)
        guarded = Client(enforce_csrf_checks=True)
        guarded.force_login(self.client_user)
        self.assertEqual(guarded.post(self.url).status_code, 403)
        self.assertFalse(FavoriteWorker.objects.exists())

    def test_add_remove_favorite_is_private_to_owner(self):
        self.client.force_login(self.client_user)
        self.assertRedirects(self.client.post(self.url),
                             reverse('marketplace:worker_public_profile',
                                     kwargs={'pk': self.worker.pk}))
        self.assertEqual(FavoriteWorker.objects.count(), 1)
        page = self.client.get(reverse('marketplace:client_dashboard'))
        self.assertContains(page, 'favorite-worker')
        self.assertNotContains(page, 'HIDDEN-WORKER-CONTACT')
        self.client.force_login(self.other_user)
        other = self.client.get(reverse('marketplace:client_dashboard'))
        self.assertNotContains(other, 'favorite-worker')
        self.assertNotContains(other, 'HIDDEN-OWNER-CONTACT')
        self.client.force_login(self.client_user)
        self.client.post(self.url)  # idempotent replay
        self.assertEqual(FavoriteWorker.objects.count(), 1)
        self.client.post(self.url, {'action': 'remove'})
        self.client.post(self.url, {'action': 'remove'})
        self.assertFalse(FavoriteWorker.objects.exists())

    def test_crafted_offpilot_worker_id_cannot_be_favorited(self):
        self.client.force_login(self.client_user)
        response = self.client.post(reverse(
            'marketplace:toggle_favorite_worker',
            kwargs={'pk': self.foreign_worker.pk},
        ))
        self.assertEqual(response.status_code, 404)
        self.assertFalse(FavoriteWorker.objects.exists())

    def test_blocked_or_self_favorite_denied(self):
        self.client.force_login(self.worker_user)
        self.assertEqual(self.client.post(self.url).status_code, 404)
        self.client.force_login(self.client_user)
        get_user_model().objects.filter(pk=self.client_user.pk).update(
            is_blocked=True,
        )
        self.assertEqual(self.client.post(self.url).status_code, 403)
        self.assertFalse(FavoriteWorker.objects.exists())
