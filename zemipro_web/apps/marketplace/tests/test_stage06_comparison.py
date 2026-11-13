"""Stage-06 comparison is private and uses only published snapshots."""
from django.test import TestCase
from django.urls import reverse

from apps.marketplace.models import Rating
from apps.marketplace.offer_services import submit_offer
from apps.marketplace.tests.factories import (
    make_category, make_city, make_order, make_user, make_worker_profile,
)


class OfferComparisonTests(TestCase):
    def setUp(self):
        self.city = make_city()
        self.category = make_category()
        self.owner = make_user('offers-owner')
        self.other = make_user('offers-other')
        self.workers = [make_user('offers-w1'), make_user('offers-w2')]
        self.profiles = [
            make_worker_profile(worker, city=self.city, category=self.category)
            for worker in self.workers
        ]
        self.order = make_order(client=self.owner, category=self.category, city=self.city)
        for i, worker in enumerate(self.workers):
            submit_offer(
                order=self.order, actor=worker, message=f'Synthetic message {i}',
                data={
                    'price_kind': 'fixed', 'amount_min_ils': 100 + i * 50,
                    'estimated_timeline': '2 days', 'terms': 'Conditions agreed later',
                },
            )
        Rating.objects.create(
            order=make_order(
                client=self.other, category=self.category, city=self.city,
                worker=self.workers[0], status='completed',
            ),
            worker=self.workers[0], client=self.other,
            rating=4, review_text='Synthetic review',
        )

    def test_owner_sees_two_offers_ratings_profiles(self):
        self.client.force_login(self.owner)
        url = reverse('marketplace:order_detail', args=[self.order.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['offer_cards']), 2)
        cards = response.context['offer_cards']
        self.assertIn('100.00', response.content.decode())
        self.assertIn('150.00', response.content.decode())
        self.assertTrue(any(card['rating_count'] == 1 for card in cards))

    def test_outsider_cannot_read_offer_details(self):
        self.client.force_login(self.other)
        response = self.client.get(
            reverse('marketplace:order_detail', args=[self.order.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Synthetic message 0')
        self.assertNotContains(response, 'Conditions agreed later')
        self.assertEqual(response.context['offer_cards'], [])

    def test_worker_cannot_reject_offer_on_behalf_of_owner(self):
        self.client.force_login(self.workers[0])
        from apps.marketplace.models import Response
        offer = Response.objects.filter(worker=self.workers[0]).get()
        response = self.client.post(
            reverse('marketplace:offer_action', args=[offer.pk, 'reject']),
        )
        self.assertEqual(response.status_code, 403)
