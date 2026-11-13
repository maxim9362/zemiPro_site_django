"""Stage 06.5: end-to-end state, cancellation, disputes and explicit completion."""
import uuid

from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.urls import reverse

from apps.marketplace.models import Order, OrderWorkEvent, Rating
from apps.marketplace.offer_services import submit_offer
from apps.marketplace.services import accept_response, cancel_order, complete_order
from apps.marketplace.tests.factories import (
    make_category, make_city, make_order, make_user, make_worker_profile,
)
from apps.marketplace.work_services import (
    report_work_problem, start_work, submit_work_result,
)


class Stage06WorkTests(TestCase):
    def setUp(self):
        self.city = make_city()
        self.category = make_category()
        self.owner = make_user('work-client')
        self.other = make_user('work-stranger')
        self.workers = [make_user('work-w1'), make_user('work-w2')]
        for worker in self.workers:
            make_worker_profile(worker, city=self.city, category=self.category)
        self.order = make_order(client=self.owner, city=self.city, category=self.category)
        self.responses = [
            submit_offer(
                order=self.order, actor=worker, message=f'Synthetic worker {i}',
                data={
                    'price_kind': 'fixed', 'amount_min_ils': 200 + i * 25,
                    'estimated_timeline': 'Two days',
                    'terms': 'Synthetic completion conditions',
                },
            )[0] for i, worker in enumerate(self.workers)
        ]
        accept_response(self.responses[0], actor=self.owner)

    def test_complete_cycle_with_explicit_result_and_review(self):
        order, did_start = start_work(
            order_id=self.order.pk, actor=self.workers[0],
            operation_key=uuid.uuid4(),
        )
        self.assertTrue(did_start)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.IN_PROGRESS)
        order, sent = submit_work_result(
            order_id=order.pk, actor=self.workers[0], operation_key=uuid.uuid4(),
        )
        self.assertTrue(sent)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.IN_PROGRESS)
        complete_order(order, actor=self.owner)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.COMPLETED)
        self.assertEqual(list(order.work_events.order_by('pk').values_list('action', flat=True)), [
            'started', 'result_submitted', 'result_confirmed',
        ])
        self.client.force_login(self.owner)
        rating_url = reverse('marketplace:rating_create', args=[order.pk])
        self.assertEqual(self.client.get(rating_url).status_code, 200)
        self.assertEqual(self.client.post(
            rating_url,
            {'rating': 5, 'review_text': 'Synthetic verified experience'},
        ).status_code, 302)
        self.assertEqual(Rating.objects.filter(order=order).count(), 1)

    def test_duplicate_action_key_and_unauthorized_actor(self):
        key = uuid.uuid4()
        _, changed = start_work(
            order_id=self.order.pk, actor=self.workers[0], operation_key=key,
        )
        self.assertTrue(changed)
        _, changed = start_work(
            order_id=self.order.pk, actor=self.workers[0], operation_key=key,
        )
        self.assertFalse(changed)
        with self.assertRaises(PermissionDenied):
            start_work(
                order_id=self.order.pk, actor=self.other,
                operation_key=uuid.uuid4(),
            )
        with self.assertRaises(PermissionDenied):
            submit_work_result(
                order_id=self.order.pk, actor=self.owner,
                operation_key=uuid.uuid4(),
            )
        self.assertEqual(OrderWorkEvent.objects.filter(
            order=self.order, action=OrderWorkEvent.Action.STARTED,
        ).count(), 1)

    def test_dispute_by_selected_worker_and_cancellation(self):
        key = uuid.uuid4()
        _, changed = report_work_problem(
            order_id=self.order.pk, actor=self.workers[0],
            problem_code=OrderWorkEvent.ProblemCode.TIMING,
            operation_key=key,
        )
        self.assertTrue(changed)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.DISPUTED)
        with self.assertRaises(ValueError):
            submit_work_result(
                order_id=self.order.pk, actor=self.workers[0],
                operation_key=uuid.uuid4(),
            )
        cancel_order(self.order, actor=self.owner)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.CANCELLED)
        with self.assertRaises(ValueError):
            start_work(
                order_id=self.order.pk, actor=self.workers[0],
                operation_key=uuid.uuid4(),
            )

    def test_no_automatic_completion_and_post_csrf_idor(self):
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.ASSIGNED)
        self.client.force_login(self.other)
        url = reverse(
            'marketplace:order_work_action', args=[self.order.pk, 'start'],
        )
        self.assertEqual(self.client.post(url, {'operation_key': str(uuid.uuid4())}).status_code, 404)
        self.client.force_login(self.workers[0])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertEqual(self.client.post(
            url, {'operation_key': str(uuid.uuid4())},
        ).status_code, 302)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.IN_PROGRESS)
        self.assertFalse(Rating.objects.filter(order=self.order).exists())
