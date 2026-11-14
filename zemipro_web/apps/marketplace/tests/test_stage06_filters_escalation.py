"""Stage 06.2 and 06.5 acceptance: owner comparison filters and moderation queue."""
import uuid
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from apps.marketplace.models import Order, OrderWorkEvent, Rating
from apps.marketplace.offer_services import set_offer_status, submit_offer
from apps.marketplace.services import accept_response
from apps.marketplace.tests.factories import (
    make_category, make_city, make_order, make_user, make_worker_profile,
)
from apps.marketplace.work_services import report_work_problem
from apps.moderation.models import Complaint


class OwnerOfferFilterAndSortTests(TestCase):
    def setUp(self):
        self.city = make_city('filters-ashdod')
        self.category = make_category('filters-repair')
        self.owner = make_user('filters-owner')
        self.outsider = make_user('filters-outsider')
        self.workers = [
            make_user('filters-worker-1'),
            make_user('filters-worker-2'),
            make_user('filters-worker-3'),
        ]
        for worker in self.workers:
            make_worker_profile(worker, city=self.city, category=self.category)
        self.order = make_order(client=self.owner, city=self.city, category=self.category)
        self.responses = [
            submit_offer(
                order=self.order, actor=worker, message=f'Synthetic offer {i}',
                data={
                    'price_kind': 'fixed' if i != 2 else 'negotiable',
                    'amount_min_ils': str(price) if i != 2 else '',
                    'estimated_timeline': 'Synthetic two days',
                },
            )[0]
            for i, (worker, price) in enumerate(zip(self.workers, (300, 100, 0)))
        ]
        Rating.objects.create(
            order=make_order(
                client=self.outsider, city=self.city, category=self.category,
                status=Order.Status.COMPLETED, worker=self.workers[0],
            ),
            client=self.outsider, worker=self.workers[0],
            rating=5, review_text='Synthetic experience',
        )
        self.url = reverse('marketplace:order_detail', args=[self.order.pk])

    def test_ascending_descending_price_and_rating_with_negotiable_last(self):
        self.client.force_login(self.owner)
        for sort, expected in (
            ('price_asc', [1, 0, 2]),
            ('price_desc', [0, 1, 2]),
            ('rating_desc', [0, 2, 1]),
        ):
            # All unreviewed workers tie; display order is newest pk first
            # except for price sorts, which are stable by response pk.
            response = self.client.get(self.url, {'offer_sort': sort})
            self.assertEqual(response.status_code, 200)
            ids = [
                card['response'].pk for card in response.context['offer_cards']
            ]
            if sort == 'rating_desc':
                self.assertEqual(ids[0], self.responses[0].pk)
                self.assertEqual(set(ids[1:]), {
                    self.responses[1].pk, self.responses[2].pk,
                })
            else:
                self.assertEqual(ids, [
                    self.responses[i].pk for i in expected
                ])

    def test_status_filter_and_unknown_query_keys_fail_closed(self):
        set_offer_status(
            response_id=self.responses[1].pk, actor=self.owner,
            action='reject', operation_key=uuid.uuid4(),
        )
        self.client.force_login(self.owner)
        active = self.client.get(self.url, {'offer_status': 'active'})
        self.assertEqual(len(active.context['offer_cards']), 2)
        rejected = self.client.get(self.url, {'offer_status': 'rejected'})
        self.assertEqual(len(rejected.context['offer_cards']), 1)
        self.assertEqual(rejected.context['offer_cards'][0]['response'].pk,
                         self.responses[1].pk)
        empty = self.client.get(self.url, {'offer_status': 'accepted'})
        self.assertEqual(empty.status_code, 200)
        self.assertEqual(len(empty.context['offer_cards']), 0)
        self.assertContains(empty, 'Нет предложений по фильтру.')
        invalid = self.client.get(
            self.url, {'offer_status': 'DROP TABLE', 'offer_sort': 'worker__email'},
        )
        self.assertEqual(invalid.context['offer_status_selected'], 'all')
        self.assertEqual(invalid.context['offer_sort_selected'], 'newest')
        self.assertEqual(len(invalid.context['offer_cards']), 3)

    def test_sort_and_filter_do_not_expose_offers_to_outsider(self):
        self.client.force_login(self.outsider)
        res = self.client.get(
            self.url, {'offer_status': 'all', 'offer_sort': 'price_asc'},
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.context['offer_cards'], [])
        self.assertEqual(res.context['offer_total_count'], 0)
        self.assertNotContains(res, 'Synthetic offer 0')


class ModerationEscalationTests(TestCase):
    def setUp(self):
        self.city = make_city('moderation-stage06-ashdod')
        self.category = make_category('moderation-stage06-cleaning')
        self.owner = make_user('moderation-stage06-owner')
        self.worker = make_user('moderation-stage06-worker')
        make_worker_profile(self.worker, city=self.city, category=self.category)
        self.order = make_order(client=self.owner, city=self.city, category=self.category)
        offer, _ = submit_offer(
            order=self.order, actor=self.worker, message='Synthetic',
            data={'price_kind': 'fixed', 'amount_min_ils': '200.00'},
        )
        accept_response(offer, actor=self.owner)

    def test_dispute_creates_pending_staff_queue_item_once_and_no_pii(self):
        key = uuid.uuid4()
        _, changed = report_work_problem(
            order_id=self.order.pk, actor=self.owner,
            problem_code=OrderWorkEvent.ProblemCode.QUALITY,
            operation_key=key,
        )
        self.assertTrue(changed)
        again, created = report_work_problem(
            order_id=self.order.pk, actor=self.owner,
            problem_code=OrderWorkEvent.ProblemCode.QUALITY,
            operation_key=key,
        )
        self.assertFalse(created)
        self.assertEqual(again.pk, self.order.pk)
        complaint = Complaint.objects.get(target_order=self.order)
        self.assertEqual(complaint.status, Complaint.Status.PENDING)
        self.assertEqual(complaint.reason, Complaint.Reason.BAD_SERVICE)
        self.assertEqual(complaint.reporter_id, self.owner.pk)
        self.assertEqual(complaint.target_user_id, self.worker.pk)
        self.assertNotIn(self.order.address, complaint.message)
        self.assertNotIn(self.order.description, complaint.message)
        self.assertEqual(Complaint.objects.filter(target_order=self.order).count(), 1)

    def test_failed_moderation_queue_write_rolls_back_problem_and_status(self):
        with patch(
            'apps.marketplace.work_services.Complaint.objects.create',
            side_effect=RuntimeError('Synthetic moderation persistence failure'),
        ):
            with self.assertRaisesRegex(RuntimeError, 'Synthetic moderation'):
                report_work_problem(
                    order_id=self.order.pk, actor=self.worker,
                    problem_code=OrderWorkEvent.ProblemCode.TIMING,
                    operation_key=uuid.uuid4(),
                )
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.ASSIGNED)
        self.assertFalse(OrderWorkEvent.objects.filter(order=self.order).exists())
        self.assertFalse(Complaint.objects.filter(target_order=self.order).exists())

    def test_dispute_http_notification_failure_rolls_back_moderation_item(self):
        self.client.force_login(self.worker)
        url = reverse(
            'marketplace:order_work_action', args=[self.order.pk, 'problem'],
        )
        data = {'problem_code': 'quality', 'operation_key': str(uuid.uuid4())}
        with patch(
            'apps.marketplace.views.create_notification',
            side_effect=RuntimeError('Synthetic notification failure'),
        ):
            with self.assertRaises(RuntimeError):
                self.client.post(url, data)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.ASSIGNED)
        self.assertFalse(Complaint.objects.filter(target_order=self.order).exists())
        self.assertFalse(OrderWorkEvent.objects.filter(order=self.order).exists())
        self.assertEqual(self.client.post(url, data).status_code, 302)
        self.assertEqual(Complaint.objects.filter(target_order=self.order).count(), 1)
