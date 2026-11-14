"""Stage 07: real PostgreSQL concurrent message replay and parallel delivery."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

from django.db import close_old_connections, connections
from django.test import TransactionTestCase

from apps.marketplace.chat_services import open_conversation, send_message
from apps.marketplace.models import Message, Response
from apps.marketplace.tests.factories import (
    make_category, make_city, make_order, make_user,
)
from apps.notifications.models import Notification


class Stage07ChatConcurrencyTests(TransactionTestCase):
    def setUp(self):
        city = make_city()
        category = make_category()
        self.customer = make_user('stage07-chat-race-customer')
        self.worker = make_user('stage07-chat-race-worker')
        order = make_order(client=self.customer, category=category, city=city)
        self.offer = Response.objects.create(
            order=order, worker=self.worker, status=Response.Status.SENT,
        )
        self.conversation, _ = open_conversation(
            response_id=self.offer.pk, actor=self.customer,
        )

    def parallel(self, job):
        barrier = Barrier(2)

        def run(index):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return job(index)
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(run, range(2)))

    def test_identical_nonce_replay_is_exactly_one_message_and_notice(self):
        key = uuid4()

        def post(index):
            row, created = send_message(
                conversation_id=self.conversation.pk,
                actor=self.worker,
                body='Synthetic safe parallel replay',
                client_nonce=key,
            )
            return row.pk, created

        result = self.parallel(post)
        self.assertEqual(result[0][0], result[1][0])
        self.assertCountEqual([created for _, created in result], [True, False])
        self.assertEqual(Message.objects.filter(
            conversation=self.conversation,
        ).count(), 1)
        self.assertEqual(Notification.objects.filter(
            recipient=self.customer,
            dedupe_key__startswith='chat.message.',
        ).count(), 1)

    def test_two_participants_simultaneous_messages_are_preserved(self):
        keys = [uuid4(), uuid4()]
        authors = [self.customer, self.worker]

        def post(index):
            row, created = send_message(
                conversation_id=self.conversation.pk,
                actor=authors[index],
                body='Synthetic distinct parallel ' + str(index),
                client_nonce=keys[index],
            )
            return row.pk, created

        result = self.parallel(post)
        self.assertTrue(all(created for _, created in result))
        self.assertEqual(len({pk for pk, _ in result}), 2)
        self.assertEqual(
            set(Message.objects.filter(
                conversation=self.conversation,
            ).values_list('sender_id', flat=True)),
            {self.customer.pk, self.worker.pk},
        )
        self.assertEqual(
            Notification.objects.filter(
                dedupe_key__startswith='chat.message.',
            ).count(), 2,
        )
