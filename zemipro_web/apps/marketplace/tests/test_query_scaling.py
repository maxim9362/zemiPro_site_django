"""Stage 01.6 SQL query scaling: synthetic PostgreSQL only."""
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.accounts.models import ClientProfile, WorkerProfile
from .factories import make_category, make_city, make_order, make_user


class QueryScalingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.city = make_city(slug='perf-city')
        cls.category = make_category(slug='perf-category')
        cls.owner = make_user('perf-owner')
        ClientProfile.objects.create(user=cls.owner, city=cls.city)

    def make_worker(self, number):
        user = make_user(f'perf-worker-{number}')
        profile = WorkerProfile.objects.create(
            user=user, city=self.city, display_name=user.username,
            description='Synthetic published professional profile in CI.',
            pricing_details='Negotiable', spoken_languages=['ru'], is_published=True,
        )
        profile.skills.add(self.category)
        return profile

    def test_city_page_skills_query_does_not_scale_with_worker_count(self):
        self.make_worker(0)
        url = reverse('marketplace:city_detail', args=[self.city.slug])
        with CaptureQueriesContext(connection) as small:
            self.assertEqual(self.client.get(url).status_code, 200)

        for number in range(1, 9):
            self.make_worker(number)
        with CaptureQueriesContext(connection) as large:
            response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'perf-worker-8')
        self.assertLessEqual(len(large), len(small) + 1)

    def test_category_page_user_city_queries_do_not_scale(self):
        self.make_worker(0)
        url = reverse('marketplace:category_detail', args=[self.category.slug])
        with CaptureQueriesContext(connection) as small:
            self.assertEqual(self.client.get(url).status_code, 200)

        for number in range(1, 9):
            self.make_worker(number)
        with CaptureQueriesContext(connection) as large:
            self.assertEqual(self.client.get(url).status_code, 200)
        self.assertLessEqual(len(large), len(small) + 1)

    def test_client_dashboard_response_count_is_aggregated(self):
        make_order(client=self.owner, category=self.category, city=self.city)
        self.client.force_login(self.owner)
        url = reverse('marketplace:client_dashboard')
        with CaptureQueriesContext(connection) as small:
            self.assertEqual(self.client.get(url).status_code, 200)

        for number in range(1, 9):
            make_order(
                client=self.owner, category=self.category, city=self.city,
                address=f'Synthetic location {number}',
            )
        with CaptureQueriesContext(connection) as large:
            response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Откликов:')
        self.assertLessEqual(len(large), len(small) + 1)

    def test_worker_profile_prefetches_skills(self):
        profile = self.make_worker(0)
        url = reverse('marketplace:worker_public_profile', args=[profile.pk])
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.category.name_ru)
        self.assertLessEqual(len(queries), 8)

    def test_worker_dashboard_related_orders_are_joined(self):
        profile = self.make_worker(0)
        self.client.force_login(profile.user)
        for number in range(8):
            make_order(
                client=self.owner, category=self.category, city=self.city,
                address=f'Synthetic work {number}',
            )
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(reverse('marketplace:worker_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.category.name_ru)
        self.assertLessEqual(len(queries), 12)
