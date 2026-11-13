"""Independent Stage 06 remediation regressions: failure-injection and replay.

Tests only isolated synthetic accounts/orders on the configured PostgreSQL test DB.
"""
import uuid
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from apps.marketplace.agreement_services import (
    decide_agreement_change, effective_agreement, propose_agreement_change,
)
from apps.marketplace.models import (
    Order, OrderAgreementDecision, OrderAgreementVersion, OrderStatusEvent,
    OrderWorkEvent, OrderWriteQuota, Response, ResponseRevision,
)
from apps.marketplace.offer_services import submit_offer
from apps.marketplace.services import accept_response
from apps.marketplace.tests.factories import (
    make_category, make_city, make_order, make_user, make_worker_profile,
)
from apps.marketplace.work_services import start_work
from apps.notifications.models import Notification
from apps.notifications.services import create_notification as real_create_notification


class NotificationFailureInjectionTests(TestCase):
    def setUp(self):
        self.city = make_city()
        self.category = make_category()
        self.owner = make_user('notice-owner')
        self.worker1 = make_user('notice-worker1')
        self.worker2 = make_user('notice-worker2')
        for user in (self.worker1, self.worker2):
            make_worker_profile(user, city=self.city, category=self.category)
        self.order = make_order(
            client=self.owner, city=self.city, category=self.category,
        )
        self.details = {
            'price_kind': 'fixed', 'amount_min_ils': '180.00',
            'estimated_timeline': 'Synthetic two days',
            'terms': 'Synthetic work terms',
        }

    def _offer(self, worker, *, amount='180.00'):
        return submit_offer(
            order=self.order, actor=worker,
            message='Synthetic test offer',
            data={**self.details, 'amount_min_ils': amount},
        )[0]

    def _assigned(self):
        response = self._offer(self.worker1)
        accept_response(response, actor=self.owner)
        return response

    @staticmethod
    def _error(*args, **kwargs):
        raise RuntimeError('Injected synthetic notification persistence failure')

    def test_submit_failure_rolls_back_offer_revision_quota_and_retries(self):
        self.client.force_login(self.worker1)
        key = str(uuid.uuid4())
        url = reverse('marketplace:order_respond', args=[self.order.pk])
        form = {'message': 'Synthetic test offer', 'operation_key': key, **self.details}
        with patch('apps.marketplace.views.create_notification', side_effect=self._error):
            with self.assertRaisesRegex(RuntimeError, 'Injected synthetic'):
                self.client.post(url, form)
        self.assertFalse(Response.objects.filter(order=self.order).exists())
        self.assertFalse(ResponseRevision.objects.exists())
        self.assertFalse(Notification.objects.exists())
        self.assertFalse(OrderWriteQuota.objects.filter(owner=self.worker1).exists())

        self.assertEqual(self.client.post(url, form).status_code, 302)
        self.assertEqual(self.client.post(url, form).status_code, 302)
        self.assertEqual(Response.objects.filter(order=self.order).count(), 1)
        self.assertEqual(ResponseRevision.objects.count(), 1)
        self.assertEqual(Notification.objects.filter(
            notification_type=Notification.Type.NEW_RESPONSE,
        ).count(), 1)

    def test_failure_on_second_selection_notice_reverts_everything(self):
        first = self._offer(self.worker1)
        second = self._offer(self.worker2, amount='250.00')
        self.client.force_login(self.owner)
        url = reverse(
            'marketplace:order_accept_response',
            args=[self.order.pk, first.pk],
        )
        delivered = []

        def fail_second(*args, **kwargs):
            delivered.append(kwargs['notification_type'])
            if len(delivered) == 2:
                raise RuntimeError('Injected second-recipient failure')
            return real_create_notification(*args, **kwargs)

        with patch('apps.marketplace.views.create_notification', side_effect=fail_second):
            with self.assertRaisesRegex(RuntimeError, 'second-recipient'):
                self.client.post(url)
        self.assertEqual(delivered, ['response_accepted', 'response_rejected'])
        self.order.refresh_from_db()
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PUBLISHED)
        self.assertIsNone(self.order.worker_id)
        self.assertEqual(first.status, Response.Status.SENT)
        self.assertEqual(second.status, Response.Status.SENT)
        self.assertEqual(first.revisions.count(), 1)
        self.assertEqual(second.revisions.count(), 1)
        self.assertFalse(OrderAgreementVersion.objects.filter(order=self.order).exists())
        self.assertFalse(OrderStatusEvent.objects.filter(order=self.order).exists())
        self.assertFalse(Notification.objects.filter(related_order=self.order).exists())

        self.assertEqual(self.client.post(url).status_code, 302)
        self.assertEqual(self.client.post(url).status_code, 302)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.ASSIGNED)
        self.assertEqual(self.order.worker_id, self.worker1.pk)
        self.assertEqual(OrderAgreementVersion.objects.filter(order=self.order).count(), 1)
        self.assertEqual(Notification.objects.filter(
            related_order=self.order, notification_type='response_accepted',
        ).count(), 1)
        self.assertEqual(Notification.objects.filter(
            related_order=self.order, notification_type='response_rejected',
        ).count(), 1)

    def test_start_notice_failure_rolls_back_transition_and_can_retry(self):
        self._assigned()
        self.client.force_login(self.worker1)
        key = str(uuid.uuid4())
        url = reverse('marketplace:order_work_action', args=[self.order.pk, 'start'])
        with patch('apps.marketplace.views.create_notification', side_effect=self._error):
            with self.assertRaises(RuntimeError):
                self.client.post(url, {'operation_key': key})
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.ASSIGNED)
        self.assertFalse(OrderWorkEvent.objects.filter(order=self.order).exists())
        self.assertFalse(Notification.objects.exists())
        self.assertFalse(OrderStatusEvent.objects.filter(
            order=self.order, new_status=Order.Status.IN_PROGRESS,
        ).exists())

        self.assertEqual(self.client.post(url, {'operation_key': key}).status_code, 302)
        self.assertEqual(self.client.post(url, {'operation_key': key}).status_code, 302)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.IN_PROGRESS)
        self.assertEqual(self.order.work_events.count(), 1)
        self.assertEqual(Notification.objects.filter(
            related_order=self.order, notification_type='order_updated',
        ).count(), 1)

    def test_result_notice_failure_rolls_back_event_and_retries(self):
        self._assigned()
        start_work(order_id=self.order.pk, actor=self.worker1, operation_key=uuid.uuid4())
        self.client.force_login(self.worker1)
        key = str(uuid.uuid4())
        url = reverse('marketplace:order_work_action', args=[self.order.pk, 'result'])
        with patch('apps.marketplace.views.create_notification', side_effect=self._error):
            with self.assertRaises(RuntimeError):
                self.client.post(url, {'operation_key': key})
        self.assertFalse(OrderWorkEvent.objects.filter(
            order=self.order, action=OrderWorkEvent.Action.RESULT_SUBMITTED,
        ).exists())
        self.assertFalse(Notification.objects.exists())

        self.assertEqual(self.client.post(url, {'operation_key': key}).status_code, 302)
        self.assertEqual(self.client.post(url, {'operation_key': key}).status_code, 302)
        self.assertEqual(OrderWorkEvent.objects.filter(
            order=self.order, action=OrderWorkEvent.Action.RESULT_SUBMITTED,
        ).count(), 1)
        self.assertEqual(Notification.objects.filter(
            related_order=self.order, notification_type='order_updated',
        ).count(), 1)

    def test_problem_notice_failure_rolls_back_dispute_and_retries(self):
        self._assigned()
        self.client.force_login(self.worker1)
        key = str(uuid.uuid4())
        url = reverse('marketplace:order_work_action', args=[self.order.pk, 'problem'])
        data = {'operation_key': key, 'problem_code': 'quality'}
        with patch('apps.marketplace.views.create_notification', side_effect=self._error):
            with self.assertRaises(RuntimeError):
                self.client.post(url, data)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.ASSIGNED)
        self.assertFalse(OrderWorkEvent.objects.filter(
            order=self.order, action=OrderWorkEvent.Action.PROBLEM,
        ).exists())
        self.assertFalse(Notification.objects.exists())

        self.assertEqual(self.client.post(url, data).status_code, 302)
        self.assertEqual(self.client.post(url, data).status_code, 302)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.DISPUTED)
        self.assertEqual(OrderWorkEvent.objects.filter(
            order=self.order, action=OrderWorkEvent.Action.PROBLEM,
        ).count(), 1)
        self.assertEqual(Notification.objects.filter(
            related_order=self.order, notification_type='order_updated',
        ).count(), 1)

    def test_complete_notice_failure_rolls_back_confirmation(self):
        self._assigned()
        start_work(order_id=self.order.pk, actor=self.worker1, operation_key=uuid.uuid4())
        self.client.force_login(self.owner)
        url = reverse('marketplace:order_complete', args=[self.order.pk])
        with patch('apps.marketplace.views.create_notification', side_effect=self._error):
            with self.assertRaises(RuntimeError):
                self.client.post(url)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.IN_PROGRESS)
        self.assertFalse(OrderWorkEvent.objects.filter(
            order=self.order, action=OrderWorkEvent.Action.RESULT_CONFIRMED,
        ).exists())
        self.assertFalse(Notification.objects.exists())

        self.assertEqual(self.client.post(url).status_code, 302)
        self.assertEqual(self.client.post(url).status_code, 302)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.COMPLETED)
        self.assertEqual(OrderWorkEvent.objects.filter(
            order=self.order, action=OrderWorkEvent.Action.RESULT_CONFIRMED,
        ).count(), 1)
        self.assertEqual(Notification.objects.filter(
            related_order=self.order, notification_type='order_completed',
        ).count(), 1)


class AgreementNotificationTests(TestCase):
    def setUp(self):
        self.city = make_city()
        self.category = make_category()
        self.owner = make_user('agreement-notice-client', preferred_language='he')
        self.worker = make_user('agreement-notice-worker', preferred_language='en')
        make_worker_profile(self.worker, city=self.city, category=self.category)
        self.order = make_order(client=self.owner, city=self.city, category=self.category)
        offer = submit_offer(
            order=self.order, actor=self.worker, message='Private synthetic terms',
            data={
                'price_kind': 'fixed', 'amount_min_ils': '300.00',
                'estimated_timeline': 'Two days', 'terms': 'Private synthetic terms',
            },
        )[0]
        accept_response(offer, actor=self.owner)
        self.change = {
            'price_kind': 'fixed', 'amount_min_ils': '350.00',
            'estimated_timeline': 'Three days', 'terms': 'Revised synthetic terms',
        }

    @staticmethod
    def _error(*args, **kwargs):
        raise RuntimeError('Synthetic agreement notice failure')

    def _proposal(self, *, key):
        return propose_agreement_change(
            order_id=self.order.pk, actor=self.owner, data=self.change,
            note='No personal details in notifications',
            base_version=1, operation_key=key,
        )

    def test_proposal_notifies_worker_once_in_english_and_decision_owner_in_hebrew(self):
        key = uuid.uuid4()
        proposal, created = self._proposal(key=key)
        self.assertTrue(created)
        again, created = self._proposal(key=key)
        self.assertFalse(created)
        self.assertEqual(proposal.pk, again.pk)
        self.assertEqual(effective_agreement(self.order).number, 1)
        notices = Notification.objects.filter(recipient=self.worker)
        self.assertEqual(notices.count(), 1)
        self.assertIn('Agreement change proposed', notices.get().title)
        self.assertIn('version 2', notices.get().message)
        self.assertNotIn('Revised synthetic terms', notices.get().message)

        decision_key = uuid.uuid4()
        decision, did_change = decide_agreement_change(
            agreement_id=proposal.pk, actor=self.worker,
            action='accept', operation_key=decision_key,
        )
        self.assertTrue(did_change)
        replay, did_change = decide_agreement_change(
            agreement_id=proposal.pk, actor=self.worker,
            action='accept', operation_key=decision_key,
        )
        self.assertFalse(did_change)
        self.assertEqual(replay.pk, decision.pk)
        self.assertEqual(effective_agreement(self.order).number, 2)
        owner_notices = Notification.objects.filter(recipient=self.owner)
        self.assertEqual(owner_notices.count(), 1)
        self.assertIn('אושר', owner_notices.get().title)
        self.assertNotIn('Revised synthetic terms', owner_notices.get().message)

    def test_proposal_notification_failure_rolls_back_version_and_quota(self):
        key = uuid.uuid4()
        with patch('apps.marketplace.agreement_services.create_notification', side_effect=self._error):
            with self.assertRaises(RuntimeError):
                self._proposal(key=key)
        self.assertEqual(OrderAgreementVersion.objects.filter(order=self.order).count(), 1)
        self.assertFalse(OrderWriteQuota.objects.filter(
            owner=self.owner, kind='edit',
        ).exists())
        self.assertFalse(Notification.objects.exists())
        self.assertEqual(effective_agreement(self.order).number, 1)

        proposal, created = self._proposal(key=key)
        self.assertTrue(created)
        self.assertEqual(proposal.number, 2)
        self.assertEqual(Notification.objects.filter(recipient=self.worker).count(), 1)

    def test_decision_notification_failure_rolls_back_decision_then_replays(self):
        proposal, _ = self._proposal(key=uuid.uuid4())
        decision_key = uuid.uuid4()
        with patch('apps.marketplace.agreement_services.create_notification', side_effect=self._error):
            with self.assertRaises(RuntimeError):
                decide_agreement_change(
                    agreement_id=proposal.pk, actor=self.worker,
                    action='reject', operation_key=decision_key,
                )
        self.assertFalse(OrderAgreementDecision.objects.filter(
            agreement=proposal,
        ).exists())
        self.assertEqual(effective_agreement(self.order).number, 1)
        self.assertEqual(Notification.objects.filter(recipient=self.worker).count(), 1)
        self.assertFalse(Notification.objects.filter(recipient=self.owner).exists())

        decision, did_change = decide_agreement_change(
            agreement_id=proposal.pk, actor=self.worker,
            action='reject', operation_key=decision_key,
        )
        self.assertTrue(did_change)
        self.assertEqual(decision.result, OrderAgreementDecision.Result.REJECTED)
        self.assertEqual(Notification.objects.filter(recipient=self.owner).count(), 1)
        self.assertEqual(Notification.objects.filter(recipient=self.worker).count(), 1)
        self.assertEqual(effective_agreement(self.order).number, 1)

    def test_owner_proposal_notifies_worker_without_exposing_raw_terms(self):
        proposal, created = self._proposal(key=uuid.uuid4())
        self.assertTrue(created)
        self.assertEqual(proposal.proposed_by_id, self.owner.pk)
        notice = Notification.objects.get(recipient=self.worker)
        self.assertNotIn(self.change['terms'], notice.message)
        self.assertNotIn('300.00', notice.message)
