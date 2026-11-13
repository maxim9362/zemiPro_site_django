"""Synthetic stage-06.1 offer safety and revision tests."""
import uuid
from decimal import Decimal

from django.core.exceptions import PermissionDenied
from django.test import TestCase

from apps.marketplace.models import Response, ResponseRevision
from apps.marketplace.offer_services import edit_offer, set_offer_status, submit_offer
from apps.marketplace.tests.factories import (
    make_category, make_city, make_order, make_user, make_worker_profile,
)


class OfferRevisionTests(TestCase):
    def setUp(self):
        self.city = make_city()
        self.category = make_category()
        self.owner = make_user('stage06-client')
        self.worker = make_user('stage06-worker')
        self.stranger = make_user('stage06-stranger')
        make_worker_profile(self.worker, city=self.city, category=self.category)
        self.order = make_order(
            client=self.owner, category=self.category, city=self.city,
        )
        self.details = {
            'price_kind': 'range', 'amount_min_ils': '100.00',
            'amount_max_ils': '150.00', 'pricing_method': '',
            'estimated_timeline': 'Two days', 'terms': 'Synthetic offer conditions',
        }

    def test_create_replay_duplicate_and_revision(self):
        key = uuid.uuid4()
        response, created = submit_offer(
            order=self.order, actor=self.worker, message='Synthetic details',
            data=self.details, operation_key=key,
        )
        self.assertTrue(created)
        self.assertEqual(response.status, Response.Status.SENT)
        self.assertEqual(response.amount_max_ils, Decimal('150'))
        repeat, created = submit_offer(
            order=self.order, actor=self.worker, message='Synthetic details',
            data=self.details, operation_key=key,
        )
        self.assertFalse(created)
        self.assertEqual(repeat.pk, response.pk)
        with self.assertRaises(ValueError):
            submit_offer(
                order=self.order, actor=self.worker, message='Different',
                data=self.details, operation_key=key,
            )
        with self.assertRaises(ValueError):
            submit_offer(
                order=self.order, actor=self.worker, message='Synthetic details',
                data=self.details, operation_key=uuid.uuid4(),
            )
        self.assertEqual(Response.objects.count(), 1)
        self.assertEqual(response.revisions.count(), 1)

    def test_worker_edit_is_versioned_and_others_cannot_change(self):
        response, _ = submit_offer(
            order=self.order, actor=self.worker, message='Initial',
            data=self.details,
        )
        key = uuid.uuid4()
        edited, changed = edit_offer(
            response_id=response.pk, actor=self.worker,
            data={**self.details, 'amount_max_ils': '200.00'},
            message='Revised', expected_revision=1, operation_key=key,
        )
        self.assertTrue(changed)
        self.assertEqual(edited.revision, 2)
        self.assertEqual(edited.revisions.count(), 2)
        self.assertEqual(edited.revisions.first().message, 'Initial')
        with self.assertRaises(PermissionDenied):
            edit_offer(
                response_id=response.pk, actor=self.stranger,
                data=self.details, message='Override',
                expected_revision=2, operation_key=uuid.uuid4(),
            )
        with self.assertRaises(ValueError):
            edit_offer(
                response_id=response.pk, actor=self.worker,
                data=self.details, message='Stale',
                expected_revision=1, operation_key=uuid.uuid4(),
            )
        with self.assertRaises(ValueError):
            edited.revisions.first().save()
        self.assertEqual(ResponseRevision.objects.count(), 2)

    def test_status_actor_and_price_validation(self):
        response, _ = submit_offer(
            order=self.order, actor=self.worker, message='Initial',
            data=self.details,
        )
        with self.assertRaises(PermissionDenied):
            set_offer_status(
                response_id=response.pk, actor=self.worker,
                action='reject', operation_key=uuid.uuid4(),
            )
        set_offer_status(
            response_id=response.pk, actor=self.owner,
            action='viewed', operation_key=uuid.uuid4(),
        )
        set_offer_status(
            response_id=response.pk, actor=self.worker,
            action='withdraw', operation_key=uuid.uuid4(),
        )
        with self.assertRaises(ValueError):
            edit_offer(
                response_id=response.pk, actor=self.worker,
                data=self.details, message='Forbidden',
                expected_revision=3, operation_key=uuid.uuid4(),
            )
        with self.assertRaises(ValueError):
            submit_offer(
                order=self.order, actor=self.stranger, message='bad',
                data={**self.details, 'amount_max_ils': '-1.00'},
            )
