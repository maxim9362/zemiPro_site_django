"""07.3: localized and duplicate-free in-app events and safe provider retries."""
from unittest.mock import Mock
from uuid import uuid4

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.marketplace.chat_services import open_conversation, send_message
from apps.marketplace.models import Response
from apps.marketplace.tests.factories import make_category, make_city, make_order, make_user
from apps.notifications.models import Notification, NotificationDelivery
from apps.notifications.domain_services import (
    create_domain_notification, process_email_outbox, set_preferences,
)


class Stage07NotificationTests(TestCase):
    def setUp(self):
        self.owner = make_user('stage07-notify-owner', preferred_language='he')
        self.worker = make_user('stage07-notify-worker', preferred_language='en')
        city = make_city()
        category = make_category()
        self.order = make_order(client=self.owner, city=city, category=category)
        self.response = Response.objects.create(
            order=self.order, worker=self.worker, status=Response.Status.SENT,
        )

    def test_message_event_dedup_and_recipient_language(self):
        conversation, _ = open_conversation(response_id=self.response.pk, actor=self.worker)
        nonce = uuid4()
        message, created = send_message(
            conversation_id=conversation.pk, actor=self.worker,
            body='Synthetic private body', client_nonce=nonce,
        )
        self.assertTrue(created)
        self.assertEqual(self.owner.notifications.count(), 1)
        notice = self.owner.notifications.get()
        self.assertEqual(notice.title, 'הודעה חדשה')
        self.assertNotIn(message.body, notice.message)
        again, created = send_message(
            conversation_id=conversation.pk, actor=self.worker,
            body='Synthetic private body', client_nonce=nonce,
        )
        self.assertFalse(created)
        self.assertEqual(again.pk, message.pk)
        self.assertEqual(self.owner.notifications.count(), 1)
        self.assertEqual(NotificationDelivery.objects.count(), 0)

    def test_mandatory_not_muted_and_event_is_idempotent(self):
        set_preferences(actor=self.owner, in_app_optional=False, email_optional=False)
        notice, created = create_domain_notification(
            recipient_id=self.owner.pk, event_key='optional.123', event='invitation',
        )
        self.assertIsNone(notice)
        self.assertFalse(created)
        must, created = create_domain_notification(
            recipient_id=self.owner.pk, event_key='mandatory.123',
            event='complaint', mandatory=True,
        )
        self.assertTrue(created)
        self.assertEqual(must.title, 'תלונה')
        again, created = create_domain_notification(
            recipient_id=self.owner.pk, event_key='mandatory.123',
            event='complaint', mandatory=True,
        )
        self.assertFalse(created)
        self.assertEqual(must.pk, again.pk)

    def enable_test_email(self):
        self.worker.email_verified_at = timezone.now()
        self.worker.email = 'synthetic@example.invalid'
        self.worker.save(update_fields=['email_verified_at', 'email'])
        set_preferences(actor=self.worker, in_app_optional=True, email_optional=True)

    @override_settings(ZEMIPRO_STAGE07_EMAIL_ENABLED=False)
    def test_email_provider_disabled_without_business_loss(self):
        self.enable_test_email()
        notice, created = create_domain_notification(
            recipient_id=self.worker.pk, event_key='work.123',
            event='completion', mandatory=True,
        )
        self.assertTrue(created)
        self.assertEqual(NotificationDelivery.objects.count(), 1)
        sender = Mock(side_effect=RuntimeError('Provider unavailable'))
        result = process_email_outbox(sender=sender)
        self.assertTrue(result['disabled'])
        sender.assert_not_called()
        self.assertTrue(Notification.objects.filter(pk=notice.pk).exists())

    @override_settings(ZEMIPRO_STAGE07_EMAIL_ENABLED=True,
                       DEFAULT_FROM_EMAIL='system@example.invalid')
    def test_email_failure_goes_to_dead_letter(self):
        self.enable_test_email()
        notice, _ = create_domain_notification(
            recipient_id=self.worker.pk, event_key='failure.123',
            event='message', mandatory=True,
        )
        sender = Mock(side_effect=RuntimeError('Synthetic provider failure'))
        for unused in range(5):
            NotificationDelivery.objects.filter(notification=notice).update(
                next_attempt_at=timezone.now(),
            )
            result = process_email_outbox(limit=1, sender=sender)
        delivery = NotificationDelivery.objects.get(notification=notice)
        self.assertEqual(delivery.status, NotificationDelivery.Status.DEAD)
        self.assertEqual(delivery.attempts, 5)
        self.assertEqual(result['dead'], 1)
        self.assertEqual(sender.call_count, 5)
        self.assertTrue(Notification.objects.filter(pk=notice.pk).exists())
        self.assertTrue(Response.objects.filter(pk=self.response.pk).exists())

    def test_blocked_and_unverified_user_cannot_access_notification_http(self):
        create_domain_notification(
            recipient_id=self.owner.pk, event_key='security.123',
            event='complaint', mandatory=True,
        )
        notice = self.owner.notifications.get()
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(reverse(
            'notifications:notification_list',
        )).status_code, 200)
        self.owner.is_blocked = True
        self.owner.save(update_fields=['is_blocked'])
        for path in (
            reverse('notifications:notification_list'),
            reverse('notifications:notification_preferences'),
        ):
            self.assertIn(self.client.get(path).status_code, (302, 403))
        self.assertIn(self.client.post(reverse(
            'notifications:notification_mark_read', args=[notice.pk],
        )).status_code, (302, 403))
        self.assertIn(self.client.post(reverse(
            'notifications:notification_mark_all_read',
        )).status_code, (302, 403))
        self.owner.is_blocked = False
        self.owner.email_verification_required = True
        self.owner.save(update_fields=[
            'is_blocked', 'email_verification_required',
        ])
        self.assertIn(self.client.get(reverse(
            'notifications:notification_list',
        )).status_code, (302, 403))
        self.assertFalse(
            Notification.objects.get(pk=notice.pk).is_read
        )
