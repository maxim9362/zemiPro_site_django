"""New assignment contract: one winner, no implicit work and no replay spam."""
from django.test import TestCase
from django.core.exceptions import PermissionDenied

from apps.marketplace.models import Order, Response
from apps.marketplace.services import accept_response
from apps.marketplace.offer_services import submit_offer
from apps.marketplace.tests.factories import (
    make_category, make_city, make_order, make_user, make_worker_profile,
)


class Stage06AssignmentTests(TestCase):
    def setUp(self):
        self.city = make_city()
        self.category = make_category()
        self.client_user = make_user('assign-client')
        self.other = make_user('assign-other')
        self.workers = [make_user('assign-1'), make_user('assign-2')]
        self.order = make_order(client=self.client_user, category=self.category, city=self.city)
        for worker in self.workers:
            make_worker_profile(worker, city=self.city, category=self.category)
        self.responses = [
            submit_offer(
                order=self.order, actor=worker, message='Synthetic proposal',
                data={'price_kind': 'fixed', 'amount_min_ils': '250.00'},
            )[0] for worker in self.workers
        ]

    def test_select_replay_and_losing_offer(self):
        selected = accept_response(self.responses[0], actor=self.client_user)
        self.assertTrue(selected._assignment_created)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.ASSIGNED)
        self.assertEqual(self.order.worker_id, self.workers[0].pk)
        self.assertFalse(accept_response(
            self.responses[0], actor=self.client_user,
        )._assignment_created)
        with self.assertRaises(ValueError):
            accept_response(self.responses[1], actor=self.client_user)
        self.responses[1].refresh_from_db()
        self.assertEqual(self.responses[1].status, Response.Status.REJECTED)
        self.assertEqual(self.responses[1].revisions.count(), 2)
        self.assertEqual(self.order.status_events.count(), 1)

    def test_rejected_withdrawn_and_blocked_worker(self):
        self.responses[0].status = Response.Status.WITHDRAWN
        self.responses[0].save(update_fields=['status'])
        with self.assertRaises(ValueError):
            accept_response(self.responses[0], actor=self.client_user)
        self.workers[1].is_blocked = True
        self.workers[1].save(update_fields=['is_blocked'])
        with self.assertRaises(ValueError):
            accept_response(self.responses[1], actor=self.client_user)
        self.order.refresh_from_db()
        self.assertIsNone(self.order.worker_id)
        self.assertEqual(self.order.status, Order.Status.PUBLISHED)

    def test_foreign_client_cannot_assign(self):
        with self.assertRaises(PermissionDenied):
            accept_response(self.responses[0], actor=self.other)
