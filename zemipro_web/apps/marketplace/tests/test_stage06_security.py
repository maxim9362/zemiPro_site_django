"""Stage 06.6 synthetic CSRF/IDOR, quota, append-only, rollback and race checks."""
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.core.exceptions import PermissionDenied
from django.db import DatabaseError, close_old_connections, connections, transaction
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse

from apps.marketplace.agreement_services import propose_agreement_change
from apps.marketplace.models import (
    Order, OrderAgreementVersion, OrderWorkEvent, Response, ResponseRevision,
)
from apps.marketplace.offer_services import edit_offer, submit_offer
from apps.marketplace.order_quota import ORDER_WRITE_LIMITS, OrderQuotaExceeded
from apps.marketplace.services import accept_response
from apps.marketplace.tests.factories import (
    make_category, make_city, make_order, make_user, make_worker_profile,
)
from unittest.mock import patch


class OfferAbuseAndRollbackTests(TestCase):
    def setUp(self):
        self.city = make_city()
        self.category = make_category()
        self.owner = make_user('abuse-client')
        self.worker = make_user('abuse-worker')
        self.other = make_user('abuse-stranger')
        make_worker_profile(self.worker, city=self.city, category=self.category)
        self.order = make_order(client=self.owner, category=self.category, city=self.city)
        self.details = {
            'price_kind': 'fixed', 'amount_min_ils': '110.00',
            'estimated_timeline': 'Three days', 'terms': 'Synthetic terms',
        }

    def test_transaction_rollback_does_not_leave_offer_history_or_quota(self):
        with self.assertRaises(RuntimeError), transaction.atomic():
            submit_offer(
                order=self.order, actor=self.worker, message='Synthetic',
                data=self.details, operation_key=uuid.uuid4(),
            )
            raise RuntimeError('Synthetic transaction rollback')
        self.assertFalse(Response.objects.filter(order=self.order).exists())
        self.assertFalse(ResponseRevision.objects.exists())
        from apps.marketplace.models import OrderWriteQuota
        self.assertFalse(OrderWriteQuota.objects.filter(owner=self.worker).exists())

    def test_mass_response_quota_is_durable(self):
        other_order = make_order(client=self.owner, category=self.category, city=self.city)
        with patch.dict(ORDER_WRITE_LIMITS, {'response': (86400, 1)}):
            response, _ = submit_offer(
                order=self.order, actor=self.worker,
                message='First', data=self.details,
            )
            with self.assertRaises(OrderQuotaExceeded):
                submit_offer(
                    order=other_order, actor=self.worker,
                    message='Second', data=self.details,
                )
        self.assertEqual(response.revisions.count(), 1)
        self.assertFalse(Response.objects.filter(order=other_order).exists())

    def test_owner_cannot_edit_worker_price_and_revision_is_db_immutable(self):
        response, _ = submit_offer(
            order=self.order, actor=self.worker, message='Initial',
            data=self.details,
        )
        with self.assertRaises(PermissionDenied):
            edit_offer(
                response_id=response.pk, actor=self.owner,
                message='Forged', data={**self.details, 'amount_min_ils': '1.00'},
                expected_revision=1, operation_key=uuid.uuid4(),
            )
        with self.assertRaises(DatabaseError), transaction.atomic():
            ResponseRevision.objects.filter(response=response).update(
                amount_min_ils='1.00',
            )
        response.refresh_from_db()
        self.assertEqual(response.amount_min_ils, 110)
        self.assertEqual(response.revisions.first().amount_min_ils, 110)

    def test_csrf_and_object_access_on_http_endpoints(self):
        response, _ = submit_offer(
            order=self.order, actor=self.worker, message='Initial',
            data=self.details,
        )
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.owner)
        accept_url = reverse(
            'marketplace:order_accept_response',
            args=[self.order.pk, response.pk],
        )
        self.assertEqual(client.post(accept_url).status_code, 403)
        self.assertEqual(client.post(reverse(
            'marketplace:offer_action', args=[response.pk, 'reject'],
        )).status_code, 403)
        client.force_login(self.other)
        self.assertEqual(client.get(reverse(
            'marketplace:offer_edit', args=[response.pk],
        )).status_code, 404)
        self.assertEqual(client.get(reverse(
            'marketplace:agreement_propose', args=[self.order.pk],
        )).status_code, 403)
        response.refresh_from_db()
        self.assertEqual(response.status, Response.Status.SENT)


class ParallelOfferAndAgreementTests(TransactionTestCase):
    def setUp(self):
        self.city = make_city('parallel-ashdod')
        self.category = make_category('parallel-repair')
        self.owner = make_user('parallel-client')
        self.worker = make_user('parallel-worker')
        make_worker_profile(self.worker, city=self.city, category=self.category)
        self.order = make_order(client=self.owner, category=self.category, city=self.city)

    def _run_parallel(self, work):
        barrier = Barrier(2)
        def runner(i):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return work(i)
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(runner, range(2)))

    def test_same_offer_post_replay_keeps_one_response_and_one_revision(self):
        key = uuid.uuid4()
        def work(_):
            response, created = submit_offer(
                order=self.order, actor=self.worker, message='Same request',
                data={'price_kind': 'fixed', 'amount_min_ils': '300.00'},
                operation_key=key,
            )
            return response.pk, created
        result = self._run_parallel(work)
        self.assertEqual({v[0] for v in result}, {result[0][0]})
        self.assertCountEqual([v[1] for v in result], [True, False])
        self.assertEqual(Response.objects.count(), 1)
        self.assertEqual(ResponseRevision.objects.count(), 1)

    def test_parallel_agreement_proposals_allow_only_one_pending_version(self):
        response, _ = submit_offer(
            order=self.order, actor=self.worker, message='Proposal',
            data={'price_kind': 'fixed', 'amount_min_ils': '100.00'},
        )
        accept_response(response, actor=self.owner)
        def work(i):
            try:
                _, created = propose_agreement_change(
                    order_id=self.order.pk, actor=self.owner, note='Synthetic change',
                    data={'price_kind': 'fixed', 'amount_min_ils': str(200 + i)},
                    base_version=1, operation_key=uuid.uuid4(),
                )
                return created
            except ValueError:
                return False
        self.assertCountEqual(self._run_parallel(work), [True, False])
        self.assertEqual(OrderAgreementVersion.objects.filter(order=self.order).count(), 2)
        self.assertEqual(OrderAgreementVersion.objects.filter(
            order=self.order, decision__isnull=True,
        ).count(), 1)
