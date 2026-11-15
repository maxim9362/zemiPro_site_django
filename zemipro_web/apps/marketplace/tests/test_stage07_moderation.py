"""07.5: participant-only message complaints, audited moderator decisions/appeals."""
from uuid import uuid4

from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied
from django.db import DatabaseError, transaction
from django.test import TestCase
from django.urls import reverse

from apps.marketplace.chat_services import open_conversation, send_message
from apps.marketplace.models import Order, Response
from apps.marketplace.tests.factories import (
    make_category, make_city, make_order, make_user, make_worker_profile,
)
from apps.moderation.case_services import (
    ComplaintConflict, decide_appeal, decide_complaint,
    file_appeal, submit_complaint, visible_target,
)
from apps.moderation.models import Complaint, ComplaintAppeal, ModerationEvent


class Stage07CaseTests(TestCase):
    def setUp(self):
        city = make_city()
        category = make_category()
        self.owner = make_user('stage07-case-owner')
        self.worker = make_user('stage07-case-worker')
        self.stranger = make_user('stage07-case-stranger')
        self.moderator = make_user('stage07-case-moderator', is_staff=True)
        self.staff_no_perm = make_user('stage07-case-limited-staff', is_staff=True)
        p = Permission.objects.get(
            content_type=ContentType.objects.get_for_model(ModerationEvent),
            codename='review_complaints',
        )
        self.moderator.user_permissions.add(p)
        make_worker_profile(self.worker, city=city, category=category)
        self.order = make_order(
            client=self.owner, city=city, category=category,
            status=Order.Status.PUBLISHED,
        )
        self.offer = Response.objects.create(
            order=self.order, worker=self.worker, status=Response.Status.SENT,
        )

    def test_message_report_idor_and_authenticated_staff_permissions(self):
        conv, _ = open_conversation(response_id=self.offer.pk, actor=self.worker)
        message, _ = send_message(
            conversation_id=conv.pk, actor=self.worker,
            body='Private synthetic message', client_nonce=uuid4(),
        )
        with self.assertRaises(PermissionDenied):
            visible_target(actor=self.stranger, target_message_id=message.pk)
        with self.assertRaises(PermissionDenied):
            visible_target(actor=self.worker, target_message_id=message.pk)
        url = reverse('moderation:complaint_create') + f'?message={message.pk}'
        self.client.force_login(self.stranger)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.post(
            url, {'reason': Complaint.Reason.OTHER,
                  'message': 'Synthetic report of abusive message'},
        ).status_code, 302)
        case = Complaint.objects.get()
        self.assertEqual(case.target_message_id, message.pk)
        self.assertEqual(case.target_user_id, self.worker.pk)
        self.client.force_login(self.staff_no_perm)
        self.assertEqual(self.client.get(reverse('moderation:queue')).status_code, 403)
        self.client.force_login(self.moderator)
        self.assertContains(self.client.get(reverse('moderation:queue')), str(case.pk))

    def test_moderator_resolution_appeal_and_audit_are_enforced(self):
        case = submit_complaint(
            actor=self.owner, reason=Complaint.Reason.OTHER,
            message='Synthetic complaint concerning the order',
            target_order_id=self.order.pk,
        )
        with self.assertRaises(PermissionDenied):
            decide_complaint(
                actor=self.staff_no_perm, complaint_id=case.pk, approve=True,
            )
        decided = decide_complaint(
            actor=self.moderator, complaint_id=case.pk,
            approve=True, note='Synthetic review complete',
        )
        self.assertEqual(decided.status, Complaint.Status.RESOLVED)
        appeal, created = file_appeal(
            actor=self.owner, complaint_id=case.pk,
            reason='Synthetic appeal', 
        )
        self.assertTrue(created)
        again, created = file_appeal(
            actor=self.owner, complaint_id=case.pk,
            reason='Synthetic appeal',
        )
        self.assertFalse(created)
        self.assertEqual(again.pk, appeal.pk)
        with self.assertRaises(ComplaintConflict):
            file_appeal(
                actor=self.owner, complaint_id=case.pk,
                reason='Different appeal',
            )
        with self.assertRaises(PermissionDenied):
            file_appeal(
                actor=self.stranger, complaint_id=case.pk, reason='Forged',
            )
        self.assertEqual(
            decide_appeal(actor=self.moderator, appeal_id=appeal.pk, accept=False).status,
            ComplaintAppeal.Status.REJECTED,
        )
        self.assertEqual(
            list(case.audit_events.order_by('occurred_at').values_list('action', flat=True)),
            [
                ModerationEvent.Action.RESOLVE,
                ModerationEvent.Action.APPEAL_FILED,
                ModerationEvent.Action.APPEAL_REJECTED,
            ],
        )
        with self.assertRaises(DatabaseError), transaction.atomic():
            ModerationEvent.objects.filter(complaint=case).update(action='forged')

    def test_quota_and_blocked_user(self):
        for i in range(5):
            submit_complaint(
                actor=self.owner, reason=Complaint.Reason.OTHER,
                message=f'Synthetic report {i}', target_order_id=self.order.pk,
            )
        with self.assertRaises(ComplaintConflict):
            submit_complaint(
                actor=self.owner, reason=Complaint.Reason.OTHER,
                message='Over quota', target_order_id=self.order.pk,
            )
        self.owner.is_blocked = True
        self.owner.save(update_fields=['is_blocked'])
        with self.assertRaises(PermissionDenied):
            submit_complaint(
                actor=self.owner, reason=Complaint.Reason.OTHER,
                message='Blocked', target_order_id=self.order.pk,
            )
