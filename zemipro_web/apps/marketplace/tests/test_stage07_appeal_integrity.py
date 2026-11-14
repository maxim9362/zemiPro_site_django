from django.test import TestCase
from django.db import DatabaseError, transaction
from django.core.exceptions import PermissionDenied
from apps.marketplace.tests import test_stage07_moderation as fixtures
from apps.moderation.case_services import (
    submit_complaint,
    decide_complaint,
    file_appeal,
    decide_appeal,
)
from apps.moderation.models import ComplaintAppeal


class AppealEvidence(TestCase):
    setUp = fixtures.Stage07CaseTests.setUp

    def appeal(self):
        c = submit_complaint(
            actor=self.owner, reason="other", message="Synthetic", target_order_id=self.order.pk
        )
        decide_complaint(actor=self.moderator, complaint_id=c.pk, approve=True)
        return file_appeal(actor=self.owner, complaint_id=c.pk, reason="Synthetic appeal")[0]

    def test_no_delete_appeal(self):
        a = self.appeal()
        with self.assertRaises(DatabaseError), transaction.atomic():
            ComplaintAppeal.objects.filter(pk=a.pk).delete()

    def test_no_rewrite_decision(self):
        a = self.appeal()
        decide_appeal(actor=self.moderator, appeal_id=a.pk, accept=True)
        with self.assertRaises(DatabaseError), transaction.atomic():
            ComplaintAppeal.objects.filter(pk=a.pk).update(status="rejected")

    def test_unverified_moderator_denied_at_service(self):
        a = self.appeal()
        type(self.moderator).objects.filter(pk=self.moderator.pk).update(
            email_verification_required=True
        )
        with self.assertRaises(PermissionDenied):
            decide_appeal(actor=self.moderator, appeal_id=a.pk, accept=True)

    def test_moderation_failure_rolls_back_decision_audit_and_notice(self):
        from unittest.mock import patch
        from apps.moderation.models import Complaint, ModerationEvent
        from apps.notifications.models import Notification
        a = self.appeal()
        before = ModerationEvent.objects.count(), Notification.objects.count()
        with patch('apps.moderation.case_services.create_domain_notification',
                   side_effect=RuntimeError('synthetic notification failure')):
            with self.assertRaises(RuntimeError):
                decide_appeal(actor=self.moderator, appeal_id=a.pk, accept=True)
        a.refresh_from_db()
        self.assertEqual(a.status, ComplaintAppeal.Status.PENDING)
        self.assertEqual((ModerationEvent.objects.count(), Notification.objects.count()), before)
        decide_appeal(actor=self.moderator, appeal_id=a.pk, accept=True)
        self.assertEqual(ModerationEvent.objects.count(), before[0] + 1)
        self.assertEqual(Notification.objects.count(), before[1] + 1)
        self.assertEqual(Complaint.objects.get(pk=a.complaint_id).status, Complaint.Status.RESOLVED)

    def test_failed_appeal_restores_quota_and_allows_same_request(self):
        from unittest.mock import patch
        from apps.accounts.models import SensitivePostCounter
        from apps.moderation.models import ModerationEvent
        c = submit_complaint(actor=self.owner, reason='other', message='Synthetic',
                             target_order_id=self.order.pk)
        decide_complaint(actor=self.moderator, complaint_id=c.pk, approve=True)
        quota = list(SensitivePostCounter.objects.values_list('pk', 'attempts'))
        audit = ModerationEvent.objects.count()
        params = dict(actor=self.owner, complaint_id=c.pk, reason='Synthetic appeal')
        with patch('apps.moderation.case_services.create_domain_notification',
                   side_effect=RuntimeError('synthetic notification failure')):
            with self.assertRaises(RuntimeError):
                file_appeal(**params)
        self.assertFalse(ComplaintAppeal.objects.exists())
        self.assertEqual(ModerationEvent.objects.count(), audit)
        self.assertEqual(list(SensitivePostCounter.objects.values_list('pk', 'attempts')), quota)
        appeal, created = file_appeal(**params)
        self.assertTrue(created)
        replay, created = file_appeal(**params)
        self.assertFalse(created)
        self.assertEqual(appeal.pk, replay.pk)

    def test_appeal_rate_limit_is_enforced_before_history_write(self):
        from apps.accounts.models import SensitivePostCounter
        from apps.moderation.case_services import ComplaintConflict
        c = submit_complaint(actor=self.owner, reason='other', message='Synthetic',
                             target_order_id=self.order.pk)
        decide_complaint(actor=self.moderator, complaint_id=c.pk, approve=True)
        SensitivePostCounter.objects.update(attempts=5)
        with self.assertRaises(ComplaintConflict):
            file_appeal(actor=self.owner, complaint_id=c.pk, reason='Synthetic appeal')
        self.assertFalse(ComplaintAppeal.objects.exists())

    def test_stage07_navigation_preferences_and_moderation_are_localized(self):
        from django.urls import reverse
        from django.utils import translation
        self.client.force_login(self.moderator)
        for language, chat, settings, queue in (
            ('en', 'Messages', 'Notification settings', 'Moderation queue'),
            ('he', 'התכתבות', 'הגדרות התראות', 'תור לבדיקה'),
        ):
            with self.subTest(language=language), translation.override(language):
                response = self.client.get(reverse('notifications:notification_preferences'),
                                           HTTP_ACCEPT_LANGUAGE=language)
                self.assertContains(response, settings)
                self.assertContains(response, chat)
                self.assertNotContains(response, 'Переписка')
                response = self.client.get(reverse('moderation:queue'),
                                           HTTP_ACCEPT_LANGUAGE=language)
                self.assertContains(response, queue)
                self.assertNotContains(response, 'Очередь модерации')
