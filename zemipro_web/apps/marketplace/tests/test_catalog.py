from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User, WorkerProfile
from apps.locations.models import City
from apps.marketplace.models import Category, Order, Rating


class CatalogPageTests(TestCase):
    def setUp(self):
        self.city = City.objects.create(
            name_ru='Ашдод', name_en='Ashdod', name_he='אשדוד', slug='ashdod'
        )
        self.category = Category.objects.create(
            name_ru='Сантехника', name_en='Plumbing', name_he='אינסטלציה',
            slug='plumbing',
        )
        self.client_user = User.objects.create_user(username='client')
        self.worker_user = User.objects.create_user(username='rated-worker')
        self.profile = WorkerProfile.objects.create(
            user=self.worker_user, city=self.city, display_name='rated-worker',
            description='Synthetic published experienced worker in CI.',
            pricing_details='Negotiable', spoken_languages=['ru'], is_published=True,
        )
        self.profile.skills.add(self.category)
        completed_order = Order.objects.create(
            client=self.client_user,
            worker=self.worker_user,
            category=self.category,
            city=self.city,
            address='Protected address',
            description='Completed work used to verify rating aggregation.',
            status=Order.Status.COMPLETED,
        )
        Rating.objects.create(
            order=completed_order,
            worker=self.worker_user,
            client=self.client_user,
            rating=5,
        )

    def test_category_and_city_pages_use_user_rating_relation(self):
        category_response = self.client.get(
            reverse('marketplace:category_detail', args=[self.category.slug])
        )
        city_response = self.client.get(
            reverse('marketplace:city_detail', args=[self.city.slug])
        )

        self.assertEqual(category_response.status_code, 200)
        self.assertEqual(city_response.status_code, 200)
        self.assertContains(category_response, 'rated-worker')
        self.assertContains(city_response, 'rated-worker')
        worker = category_response.context['page_obj'].object_list[0]
        self.assertEqual(worker.avg_rating, 5)
        self.assertEqual(worker.review_count, 1)

    def test_city_names_follow_active_request_language(self):
        cities_url = reverse('marketplace:cities_list')
        detail_url = reverse('marketplace:city_detail', args=[self.city.slug])

        english = self.client.get(cities_url, HTTP_ACCEPT_LANGUAGE='en')
        hebrew = self.client.get(detail_url, HTTP_ACCEPT_LANGUAGE='he')
        russian = self.client.get(cities_url, HTTP_ACCEPT_LANGUAGE='ru')

        self.assertContains(english, 'Ashdod')
        self.assertContains(hebrew, 'אשדוד')
        self.assertContains(russian, 'Ашдод')

    def test_city_name_falls_back_to_russian_when_translation_is_missing(self):
        city = City.objects.create(name_ru='Явне', slug='yavne')
        response = self.client.get(
            reverse('marketplace:city_detail', args=[city.slug]),
            HTTP_ACCEPT_LANGUAGE='en',
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Явне')

    def test_blocked_and_inactive_workers_not_publicly_visible(self):
        for blocked, active in ((True, True), (False, False)):
            with self.subTest(blocked=blocked, active=active):
                self.worker_user.is_blocked = blocked
                self.worker_user.is_active = active
                self.worker_user.save(update_fields=['is_blocked', 'is_active'])
                profile = reverse(
                    'marketplace:worker_public_profile', args=[self.profile.pk]
                )
                self.assertEqual(self.client.get(profile).status_code, 404)
                self.assertNotContains(
                    self.client.get(reverse(
                        'marketplace:city_detail', args=[self.city.slug]
                    )), 'rated-worker',
                )
                self.assertNotContains(
                    self.client.get(reverse(
                        'marketplace:category_detail', args=[self.category.slug]
                    )), 'rated-worker',
                )
                self.worker_user.is_blocked = False
                self.worker_user.is_active = True
                self.worker_user.save(update_fields=['is_blocked', 'is_active'])

    def test_rated_worker_sorts_before_unrated_with_stable_tiebreak(self):
        for number in range(2):
            user = User.objects.create_user(username=f'zz-unrated-{number}')
            profile = WorkerProfile.objects.create(
                user=user, city=self.city, display_name=user.username,
                description='Synthetic published unrated worker profile in CI.',
                pricing_details='Negotiable', spoken_languages=['ru'],
                is_published=True,
            )
            profile.skills.add(self.category)

        for url in (
            reverse('marketplace:city_detail', args=[self.city.slug]),
            reverse('marketplace:category_detail', args=[self.category.slug]),
        ):
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                profiles = list(response.context['page_obj'].object_list)
                self.assertEqual(profiles[0].user_id, self.worker_user.pk)
                self.assertEqual(
                    [p.user.username for p in profiles[1:]],
                    ['zz-unrated-0', 'zz-unrated-1'],
                )

    def test_root_html_language_and_direction_follow_active_locale(self):
        url = reverse('marketplace:categories_list')
        for language, direction in (('ru', 'ltr'), ('en', 'ltr'), ('he', 'rtl')):
            with self.subTest(language=language):
                response = self.client.get(url, HTTP_ACCEPT_LANGUAGE=language)
                self.assertContains(response, f'<html lang="{language}" dir="{direction}">')
