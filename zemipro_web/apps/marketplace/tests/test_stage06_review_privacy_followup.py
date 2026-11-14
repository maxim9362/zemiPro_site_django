"""Stage 06 independent-review follow-up for ZP-06-004/005.

Synthetic HTTP regressions for review notification rollback and worker-name privacy.
"""
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

from django.db import close_old_connections, connections
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse

from apps.marketplace.models import Order, Rating
from apps.marketplace.offer_services import submit_offer
from apps.marketplace.tests.factories import (
    make_category, make_city, make_order, make_user, make_worker_profile,
)
from apps.notifications.models import Notification


class ReviewNotificationAtomicityTests(TestCase):
    def setUp(self):
        self.owner = make_user('review-atomic-client')
        self.worker = make_user('review-atomic-worker')
        self.city = make_city('review-atomic-ashdod')
        self.category = make_category('review-atomic-cleaning')
        make_worker_profile(self.worker, city=self.city, category=self.category)
        self.order = make_order(
            client=self.owner, city=self.city, category=self.category,
            status=Order.Status.COMPLETED, worker=self.worker,
        )
        self.url = reverse('marketplace:rating_create', args=[self.order.pk])
        self.client.force_login(self.owner)
        self.payload = {'rating': 5, 'review_text': 'Synthetic quality review'}

    def test_notification_failure_rolls_back_review_then_retry_is_once_only(self):
        with patch(
            'apps.marketplace.views.create_notification',
            side_effect=RuntimeError('Synthetic notice insert failure'),
        ):
            with self.assertRaisesRegex(RuntimeError, 'Synthetic notice'):
                self.client.post(self.url, self.payload)
        self.assertFalse(Rating.objects.filter(order=self.order).exists())
        self.assertFalse(Notification.objects.filter(related_order=self.order).exists())

        self.assertEqual(self.client.post(self.url, self.payload).status_code, 302)
        self.assertEqual(self.client.post(self.url, self.payload).status_code, 302)
        self.assertEqual(Rating.objects.filter(order=self.order).count(), 1)
        self.assertEqual(Notification.objects.filter(
            related_order=self.order, recipient=self.worker,
            notification_type=Notification.Type.REVIEW_CREATED,
        ).count(), 1)

    def test_only_owner_may_create_review(self):
        other = make_user('review-atomic-outsider')
        self.client.force_login(other)
        self.assertEqual(self.client.post(self.url, self.payload).status_code, 404)
        self.assertFalse(Rating.objects.exists())
        self.assertFalse(Notification.objects.exists())


class SelectedWorkerNamePrivacyTests(TestCase):
    def setUp(self):
        self.owner = make_user('worker-public-owner')
        self.worker = make_user('private-login-avoid-render')
        self.city = make_city('worker-public-ashdod')
        self.category = make_category('worker-public-repair')
        profile = make_worker_profile(
            self.worker, city=self.city, category=self.category,
        )
        profile.display_name = 'Verified Public Name Example'
        profile.save()
        self.order = make_order(
            client=self.owner, city=self.city, category=self.category,
        )
        self.response, _ = submit_offer(
            order=self.order, actor=self.worker,
            message='Synthetic proposal', data={
                'price_kind': 'fixed', 'amount_min_ils': '250.00',
            },
        )
        self.client.force_login(self.owner)

    def test_selection_flash_and_order_detail_do_not_expose_private_login(self):
        response = self.client.post(reverse(
            'marketplace:order_accept_response',
            args=[self.order.pk, self.response.pk],
        ), follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Verified Public Name Example')
        self.assertNotContains(response, 'private-login-avoid-render')
        self.order.refresh_from_db()
        self.assertEqual(self.order.worker_id, self.worker.pk)

    def test_private_username_never_used_as_fallback_for_unpublished_profile(self):
        from apps.accounts.models import WorkerProfile
        from apps.marketplace.offer_presentation import selected_worker_public_name
        from apps.marketplace.services import accept_response

        accept_response(self.response, actor=self.owner)
        WorkerProfile.objects.filter(user=self.worker).update(is_published=False)
        self.order.refresh_from_db()
        self.assertNotIn(self.worker.username, selected_worker_public_name(self.order))
        html = self.client.get(reverse('marketplace:order_detail', args=[self.order.pk]))
        self.assertEqual(html.status_code, 200)
        self.assertNotContains(html, 'private-login-avoid-render')


class ParallelReviewNotificationTests(TransactionTestCase):
    def setUp(self):
        self.owner = make_user('review-parallel-owner')
        self.worker = make_user('review-parallel-worker')
        city = make_city('review-parallel-ashdod')
        category = make_category('review-parallel-category')
        make_worker_profile(self.worker, city=city, category=category)
        self.order = make_order(
            client=self.owner, city=city, category=category,
            status=Order.Status.COMPLETED, worker=self.worker,
        )

    def test_concurrent_review_posts_cannot_double_write_or_notify(self):
        barrier = Barrier(2)
        url = reverse('marketplace:rating_create', args=[self.order.pk])

        def post_review(i):
            close_old_connections()
            try:
                client = Client()
                client.force_login(self.owner)
                barrier.wait(timeout=10)
                return client.post(url, {
                    'rating': 5 - i, 'review_text': 'Synthetic review',
                }).status_code
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(pool.map(post_review, range(2)))
        self.assertEqual(statuses, [302, 302])
        self.assertEqual(Rating.objects.filter(order=self.order).count(), 1)
        self.assertEqual(Notification.objects.filter(
            related_order=self.order,
            notification_type=Notification.Type.REVIEW_CREATED,
        ).count(), 1)
