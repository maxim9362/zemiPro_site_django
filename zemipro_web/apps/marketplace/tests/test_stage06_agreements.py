"""Stage 06.4 synthetic bilateral agreement and immutability regression."""
import uuid

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError, transaction
from django.test import TestCase

from apps.marketplace.agreement_services import (
    decide_agreement_change, effective_agreement, propose_agreement_change,
)
from apps.marketplace.models import (
    Order, OrderAgreementVersion, OrderAgreementDecision,
)
from apps.marketplace.offer_services import submit_offer
from apps.marketplace.services import accept_response
from apps.marketplace.tests.factories import (
    make_category, make_city, make_order, make_user, make_worker_profile,
)


class AgreementRevisionTests(TestCase):
    def setUp(self):
        self.city = make_city()
        self.category = make_category()
        self.client_user = make_user('agreement-client')
        self.worker = make_user('agreement-worker')
        self.other = make_user('agreement-stranger')
        make_worker_profile(self.worker, city=self.city, category=self.category)
        self.order = make_order(client=self.client_user, category=self.category, city=self.city)
        self.response, _ = submit_offer(
            order=self.order, actor=self.worker, message='Original synthetic offer',
            data={
                'price_kind': 'fixed', 'amount_min_ils': '200.00',
                'estimated_timeline': 'Two days', 'terms': 'Synthetic terms v1',
            },
        )
        accept_response(self.response, actor=self.client_user)

    def test_selection_creates_one_immutable_terms_snapshot(self):
        current = effective_agreement(self.order)
        self.assertEqual(current.number, 1)
        self.assertEqual(current.note, 'Original synthetic offer')
        self.assertEqual(current.amount_min_ils, 200)
        self.assertEqual(current.decision.actor_id, self.client_user.pk)
        with self.assertRaises(ValidationError):
            current.save()
        with self.assertRaises(DatabaseError), transaction.atomic():
            OrderAgreementVersion.objects.filter(pk=current.pk).update(terms='tampered')
        current.refresh_from_db()
        self.assertEqual(current.terms, 'Synthetic terms v1')
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.ASSIGNED)
        self.assertEqual(OrderAgreementVersion.objects.count(), 1)

    def test_counterparty_confirms_new_version_without_mutating_prior(self):
        key = uuid.uuid4()
        data = {
            'price_kind': 'fixed', 'amount_min_ils': '225.00',
            'estimated_timeline': 'Three days', 'terms': 'Synthetic terms v2',
        }
        proposal, created = propose_agreement_change(
            order_id=self.order.pk, actor=self.client_user, data=data,
            note='Client adjustment', base_version=1, operation_key=key,
        )
        self.assertTrue(created)
        self.assertEqual(effective_agreement(self.order).number, 1)
        replay, again = propose_agreement_change(
            order_id=self.order.pk, actor=self.client_user, data=data,
            note='Client adjustment', base_version=1, operation_key=key,
        )
        self.assertFalse(again)
        self.assertEqual(replay.pk, proposal.pk)
        with self.assertRaises(PermissionDenied):
            decide_agreement_change(
                agreement_id=proposal.pk, actor=self.client_user,
                action='accept', operation_key=uuid.uuid4(),
            )
        decision, changed = decide_agreement_change(
            agreement_id=proposal.pk, actor=self.worker, action='accept',
            operation_key=uuid.uuid4(),
        )
        self.assertTrue(changed)
        self.assertEqual(decision.result, OrderAgreementDecision.Result.ACCEPTED)
        self.assertEqual(effective_agreement(self.order).number, 2)
        self.assertEqual(self.response.amount_min_ils, 200)
        self.assertEqual(OrderAgreementVersion.objects.count(), 2)

    def test_stranger_cannot_change_and_owner_cannot_confirm_own(self):
        with self.assertRaises(PermissionDenied):
            propose_agreement_change(
                order_id=self.order.pk, actor=self.other,
                data={'price_kind': 'negotiable'}, note='Intrusion',
                base_version=1, operation_key=uuid.uuid4(),
            )

    def test_http_owner_and_worker_can_view_but_stranger_cannot(self):
        from django.urls import reverse
        url = reverse('marketplace:order_detail', args=[self.order.pk])
        for account in (self.client_user, self.worker):
            self.client.force_login(account)
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'Synthetic terms v1')
        self.client.force_login(self.other)
        response = self.client.get(url)
        self.assertNotContains(response, 'Synthetic terms v1')
