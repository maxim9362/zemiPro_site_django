"""Stage 01 local-review regression: bounded dashboard and independent pagination."""
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import ClientProfile
from apps.marketplace.models import Order, Response
from .factories import make_category, make_city, make_order, make_user


class ClientDashboardPaginationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.city = make_city(slug='paging-city')
        cls.category = make_category(slug='paging-category')
        cls.owner = make_user('paging-owner')
        cls.unrelated = make_user('paging-unrelated')
        cls.worker = make_user('paging-worker')
        ClientProfile.objects.create(user=cls.owner, city=cls.city)
        for status, quantity in (
            (Order.Status.NEW, 14),
            (Order.Status.IN_PROGRESS, 12),
            (Order.Status.COMPLETED, 11),
            (Order.Status.CANCELLED, 11),
        ):
            for number in range(quantity):
                make_order(
                    client=cls.owner, category=cls.category, city=cls.city,
                    status=status,
                    address=f'owner-{status}-{number}',
                    description='Synthetic ' + ('bounded description ' * 35),
                )
        make_order(
            client=cls.unrelated, category=cls.category, city=cls.city,
            address='another-client-private-address',
        )

    def setUp(self):
        self.client.force_login(self.owner)
        self.url = reverse('marketplace:client_dashboard')

    def test_default_dashboard_is_bounded_and_private(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        for key in (
            'active_orders', 'in_progress_orders',
            'completed_orders', 'cancelled_orders',
        ):
            self.assertEqual(len(response.context[key]), 10, key)
            self.assertEqual(response.context[key].number, 1, key)
        self.assertEqual(len(response.context['orders_with_responses']), 10)
        self.assertLess(len(response.content), 150_000)
        self.assertNotContains(response, 'another-client-private-address')
        self.assertIn('no-store', response['Cache-Control'])

    def test_sections_paginate_independently_and_keep_other_page_numbers(self):
        response = self.client.get(self.url, {
            'active_page': '2', 'progress_page': '2',
            'completed_page': '2', 'cancelled_page': '2',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['active_orders']), 4)
        self.assertEqual(len(response.context['in_progress_orders']), 2)
        self.assertEqual(len(response.context['completed_orders']), 1)
        self.assertEqual(len(response.context['cancelled_orders']), 1)
        self.assertContains(response, 'active_page=1&amp;progress_page=2')
        self.assertContains(response, 'active_page=2&amp;progress_page=1')

    def test_malformed_page_parameter_uses_safe_first_page(self):
        response = self.client.get(self.url, {
            'active_page': 'bad-input', 'completed_page': '-100',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['active_orders'].number, 1)
        # Django Paginator.get_page() resolves out-of-range negative pages to the last page.
        self.assertEqual(response.context['completed_orders'].number, 2)

    def test_response_counts_remain_aggregated_on_visible_active_page(self):
        newest = Order.objects.filter(
            client=self.owner, status=Order.Status.NEW,
        ).order_by('-created_at', '-pk').first()
        Response.objects.create(order=newest, worker=self.worker)
        response = self.client.get(self.url)
        items = response.context['orders_with_responses']
        self.assertEqual(items[0]['order'].pk, newest.pk)
        self.assertEqual(items[0]['response_count'], 1)
        self.assertEqual(sum(item['response_count'] for item in items), 1)
