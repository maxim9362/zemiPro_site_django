"""Stage 07.1 synthetic negative permission and message integrity tests."""
from uuid import uuid4

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.marketplace.chat_services import (
    ChatConflict, get_conversation, list_messages, mark_messages_read,
    open_conversation, send_message,
)
from apps.marketplace.models import Conversation, Message, Response
from apps.marketplace.tests.factories import (
    make_category, make_city, make_order, make_user,
)


class ChatPermissionTests(TestCase):
    def setUp(self):
        city = make_city()
        category = make_category()
        self.client_user = make_user('stage07-client')
        self.worker = make_user('stage07-worker')
        self.stranger = make_user('stage07-stranger')
        self.order = make_order(
            client=self.client_user, city=city, category=category,
        )
        self.offer = Response.objects.create(
            order=self.order, worker=self.worker, status=Response.Status.SENT,
        )

    def test_thread_is_bound_to_real_offer_and_authorized_participants(self):
        with self.assertRaises(PermissionDenied):
            open_conversation(response_id=self.offer.pk, actor=self.stranger)
        self.assertEqual(Conversation.objects.count(), 0)
        conversation, created = open_conversation(
            response_id=self.offer.pk, actor=self.client_user,
        )
        self.assertTrue(created)
        same, created = open_conversation(
            response_id=self.offer.pk, actor=self.worker,
        )
        self.assertFalse(created)
        self.assertEqual(conversation.pk, same.pk)
        with self.assertRaises(PermissionDenied):
            get_conversation(conversation_id=conversation.pk, actor=self.stranger)
        with self.assertRaises(PermissionDenied):
            get_conversation(conversation_id=987654, actor=self.client_user)

    def test_replay_read_and_immutable_original(self):
        conversation, _ = open_conversation(
            response_id=self.offer.pk, actor=self.worker,
        )
        nonce = uuid4()
        first, created = send_message(
            conversation_id=conversation.pk, actor=self.worker,
            body='Synthetic private message', client_nonce=nonce,
        )
        self.assertTrue(created)
        again, created = send_message(
            conversation_id=conversation.pk, actor=self.worker,
            body='Synthetic private message', client_nonce=nonce,
        )
        self.assertFalse(created)
        self.assertEqual(first.pk, again.pk)
        with self.assertRaises(ChatConflict):
            send_message(
                conversation_id=conversation.pk, actor=self.worker,
                body='Different replay body', client_nonce=nonce,
            )
        with self.assertRaises(PermissionDenied):
            send_message(
                conversation_id=conversation.pk, actor=self.stranger,
                body='Forged', client_nonce=uuid4(),
            )
        self.assertEqual(
            list_messages(conversation_id=conversation.pk, actor=self.client_user)[0].pk,
            first.pk,
        )
        self.assertEqual(
            mark_messages_read(
                conversation_id=conversation.pk, actor=self.client_user,
                through_id=first.pk,
            ), 1,
        )
        self.assertEqual(
            mark_messages_read(
                conversation_id=conversation.pk, actor=self.client_user,
                through_id=first.pk,
            ), 0,
        )
        first.body = 'Tampered'
        with self.assertRaises(ValidationError):
            first.save()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Message.objects.filter(pk=first.pk).update(body='Tampered')
        self.assertEqual(Message.objects.get(pk=first.pk).body, 'Synthetic private message')

    def test_blocked_and_verification_required_accounts_denied(self):
        conversation, _ = open_conversation(
            response_id=self.offer.pk, actor=self.client_user,
        )
        self.worker.is_blocked = True
        self.worker.save(update_fields=['is_blocked'])
        with self.assertRaises(PermissionDenied):
            send_message(
                conversation_id=conversation.pk, actor=self.client_user,
                body='Cannot send to blocked participant', client_nonce=uuid4(),
            )
        with self.assertRaises(PermissionDenied):
            get_conversation(conversation_id=conversation.pk, actor=self.worker)
        self.worker.is_blocked = False
        self.worker.email_verification_required = True
        self.worker.save(update_fields=['is_blocked', 'email_verification_required'])
        with self.assertRaises(PermissionDenied):
            open_conversation(response_id=self.offer.pk, actor=self.worker)

    def test_closed_offer_and_wrong_worker_cannot_open_or_send(self):
        other = make_user('stage07-other-worker')
        second = Response.objects.create(
            order=self.order, worker=other, status=Response.Status.REJECTED,
        )
        with self.assertRaises(PermissionDenied):
            open_conversation(response_id=second.pk, actor=other)
        conversation, _ = open_conversation(
            response_id=self.offer.pk, actor=self.worker,
        )
        self.order.worker = other
        self.order.save(update_fields=['worker'])
        with self.assertRaises(PermissionDenied):
            send_message(
                conversation_id=conversation.pk, actor=self.worker,
                body='Cannot message after other assignment', client_nonce=uuid4(),
            )
        self.assertEqual(Conversation.objects.count(), 1)

    def test_rate_limit_and_too_large_message(self):
        conversation, _ = open_conversation(
            response_id=self.offer.pk, actor=self.worker,
        )
        with self.assertRaises(ChatConflict):
            send_message(
                conversation_id=conversation.pk, actor=self.worker,
                body='x' * 5001, client_nonce=uuid4(),
            )
        for i in range(15):
            send_message(
                conversation_id=conversation.pk, actor=self.worker,
                body=f'Synthetic {i}', client_nonce=uuid4(),
            )
        with self.assertRaises(ChatConflict):
            send_message(
                conversation_id=conversation.pk, actor=self.worker,
                body='Over quota', client_nonce=uuid4(),
            )
