from pathlib import Path
from unittest.mock import Mock, patch
from uuid import uuid4
from django.conf import settings
from django.db import DatabaseError, transaction
from django.test import TestCase, override_settings
from apps.marketplace.tests import test_stage07_chat_attachments as fixtures
from apps.marketplace.chat_services import attach_message_image, mark_messages_read
from apps.marketplace.models import Conversation, Message, Response
from apps.marketplace.tests.factories import make_order
from apps.notifications.domain_services import (
    create_domain_notification,
    process_email_outbox,
    set_preferences,
)
from django.utils import timezone


class Adversarial(TestCase):
    setUp = fixtures.Stage07PrivateAttachmentTests.setUp

    def test_outer_rollback_does_not_leave_private_file(self):
        before = set(Path(settings.ZEMIPRO_PRIVATE_MEDIA_ROOT).rglob("*.jpg"))
        with self.assertRaises(RuntimeError), transaction.atomic():
            attach_message_image(
                message_id=self.message.pk, actor=self.worker, upload=fixtures.synthetic_image()
            )
            raise RuntimeError("synthetic outer transaction failure")
        self.assertEqual(set(Path(settings.ZEMIPRO_PRIVATE_MEDIA_ROOT).rglob("*.jpg")), before)

    def test_conversation_cannot_be_rebound_to_other_customer(self):
        old = self.conversation.response.order
        order = make_order(client=self.stranger, category=old.category, city=old.city)
        response = Response.objects.create(order=order, worker=self.worker, status="sent")
        with self.assertRaises(DatabaseError), transaction.atomic():
            Conversation.objects.filter(pk=self.conversation.pk).update(response=response)

    def test_message_sender_must_be_participant_even_in_orm(self):
        with self.assertRaises(DatabaseError), transaction.atomic():
            Message.objects.create(
                conversation=self.conversation,
                sender=self.stranger,
                body="Forged sender",
                client_nonce=uuid4(),
            )

    def test_read_marker_cannot_be_reverted(self):
        mark_messages_read(
            conversation_id=self.conversation.pk, actor=self.owner, through_id=self.message.pk
        )
        with self.assertRaises(DatabaseError), transaction.atomic():
            Message.objects.filter(pk=self.message.pk).update(read_at=None)

    @override_settings(
        ZEMIPRO_STAGE07_EMAIL_ENABLED=True, DEFAULT_FROM_EMAIL="test@example.invalid"
    )
    def test_unverified_account_cannot_receive_queued_email(self):
        self.owner.email = "synthetic@example.invalid"
        self.owner.save(update_fields=["email"])
        self.owner.email_verified_at = timezone.now()
        self.owner.email_verification_required = False
        self.owner.save(update_fields=["email_verified_at", "email_verification_required"])
        set_preferences(actor=self.owner, in_app_optional=True, email_optional=True)
        create_domain_notification(
            recipient_id=self.owner.pk, event_key="synthetic.delivery", event="message"
        )
        type(self.owner).objects.filter(pk=self.owner.pk).update(email_verification_required=True)
        sender = Mock(return_value=1)
        process_email_outbox(sender=sender)
        sender.assert_not_called()

    def test_history_pagination_and_no_javascript_read(self):
        from django.urls import reverse

        rows = [
            Message.objects.create(
                conversation=self.conversation,
                sender=self.worker,
                body=f"Synthetic older message {i}",
                client_nonce=uuid4(),
            )
            for i in range(45)
        ]
        self.client.force_login(self.owner)
        url = reverse("marketplace:chat_thread", args=[self.conversation.pk])
        page = self.client.get(url)
        self.assertEqual(len(page.context["rows"]), 40)
        cursor = page.context["older_cursor"]
        older = self.client.get(url, {"before": cursor})
        self.assertEqual(len(older.context["rows"]), 6)
        self.assertEqual(older.context["rows"][0].pk, self.message.pk)
        read = self.client.post(
            reverse("marketplace:chat_read", args=[self.conversation.pk]),
            {"through_id": rows[-1].pk, "return_to_thread": "1"},
        )
        self.assertEqual(read.status_code, 302)
        self.assertFalse(
            Message.objects.filter(conversation=self.conversation, read_at=None).exists()
        )
        poll = self.client.get(
            reverse("marketplace:chat_poll", args=[self.conversation.pk]), {"after": rows[-1].pk}
        )
        self.assertIn(self.message.pk, poll.json()["read_ids"])

    def test_source_response_parties_cannot_be_changed(self):
        with self.assertRaises(DatabaseError), transaction.atomic():
            Response.objects.filter(pk=self.conversation.response_id).update(worker=self.stranger)
        order = self.conversation.response.order
        with self.assertRaises(DatabaseError), transaction.atomic():
            type(order).objects.filter(pk=order.pk).update(client=self.stranger)

    @override_settings(ZEMIPRO_GEMINI_TRANSLATION_ENABLED=True)
    def test_revocation_during_translation_does_not_publish_result(self):
        from django.core.exceptions import PermissionDenied
        from apps.marketplace.translation_services import translate_message
        from apps.marketplace.models import MessageTranslation

        def provider(*args):
            type(self.owner).objects.filter(pk=self.owner.pk).update(is_blocked=True)
            return "Synthetic translation"

        with self.assertRaises(PermissionDenied):
            translate_message(
                message_id=self.message.pk,
                actor=self.owner,
                target_language="he",
                consent=True,
                translator=provider,
            )
        self.assertFalse(MessageTranslation.objects.exists())

    def test_message_notification_failure_rolls_back_and_same_nonce_retries(self):
        from apps.marketplace.chat_services import send_message
        from apps.notifications.models import Notification
        key = uuid4()
        before = Message.objects.count()
        notices = Notification.objects.count()
        args = dict(conversation_id=self.conversation.pk, actor=self.owner,
                    body='Synthetic failure injection', client_nonce=key)
        with patch('apps.notifications.domain_services.create_domain_notification',
                   side_effect=RuntimeError('synthetic notification failure')):
            with self.assertRaises(RuntimeError):
                send_message(**args)
        self.assertEqual(Message.objects.count(), before)
        self.assertEqual(Notification.objects.count(), notices)
        message, created = send_message(**args)
        self.assertTrue(created)
        replay, created = send_message(**args)
        self.assertFalse(created)
        self.assertEqual(message.pk, replay.pk)
        self.assertEqual(Message.objects.count(), before + 1)
        self.assertEqual(Notification.objects.count(), notices + 1)

    def test_schema_rollback_refuses_to_discard_private_image(self):
        from importlib import import_module
        from django.apps import apps
        from django.db import connection
        from django.db.migrations.exceptions import IrreversibleError
        migration = import_module('apps.marketplace.migrations.0023_stage07_chat_integrity')
        attachment, _ = attach_message_image(
            message_id=self.message.pk, actor=self.worker, upload=fixtures.synthetic_image(),
        )
        with connection.schema_editor() as editor:
            with self.assertRaises(IrreversibleError):
                migration.protect_private_images(apps, editor)
        attachment.refresh_from_db()
        self.assertTrue(attachment.jpeg_data)

    def test_poll_delivers_attachment_added_after_message_cursor(self):
        from django.urls import reverse
        attachment, _ = attach_message_image(
            message_id=self.message.pk, actor=self.worker, upload=fixtures.synthetic_image(),
        )
        self.client.force_login(self.owner)
        url = reverse('marketplace:chat_poll', args=[self.conversation.pk])
        response = self.client.get(url, {'after': self.message.pk})
        self.assertEqual(response.json()['messages'], [])
        self.assertEqual(response.json()['attachments'], [{
            'id': attachment.pk, 'message_id': self.message.pk,
            'url': reverse('marketplace:chat_attachment', args=[attachment.pk]),
        }])
        self.client.force_login(self.stranger)
        self.assertEqual(self.client.get(url).status_code, 403)
