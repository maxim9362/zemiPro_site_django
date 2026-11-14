"""Stage 07.2: HTTP, CSRF, poll recovery and private DOM rendering."""
from uuid import uuid4

from django.test import Client, TestCase
from django.urls import reverse
from django.utils.translation import override

from apps.marketplace.models import Conversation, Message, Response
from apps.marketplace.tests.factories import (
    make_category, make_city, make_order, make_user,
)


class ChatHttpTests(TestCase):
    def setUp(self):
        city = make_city()
        category = make_category()
        self.owner = make_user('chat-web-owner')
        self.worker = make_user('chat-web-worker')
        self.stranger = make_user('chat-web-stranger')
        order = make_order(client=self.owner, city=city, category=category)
        self.offer = Response.objects.create(
            order=order, worker=self.worker, status=Response.Status.SENT,
        )
        self.client.force_login(self.owner)

    def _open(self):
        url = reverse('marketplace:chat_open', args=[self.offer.pk])
        result = self.client.post(url)
        self.assertEqual(result.status_code, 302)
        return Conversation.objects.get(response=self.offer)

    def test_post_only_and_private_read_poll(self):
        open_url = reverse('marketplace:chat_open', args=[self.offer.pk])
        self.assertEqual(self.client.get(open_url).status_code, 405)
        conversation = self._open()
        thread = reverse('marketplace:chat_thread', args=[conversation.pk])
        self.assertEqual(self.client.get(thread).status_code, 200)
        self.assertContains(self.client.get(thread), 'data-poll-url=')
        self.client.force_login(self.stranger)
        self.assertEqual(self.client.get(thread).status_code, 403)
        self.assertEqual(self.client.post(thread, {
            'client_nonce': str(uuid4()), 'body': 'Injected',
        }).status_code, 403)
        self.assertEqual(self.client.get(
            reverse('marketplace:chat_poll', args=[conversation.pk]), {'after': 0},
        ).status_code, 403)
        self.assertEqual(self.client.post(
            reverse('marketplace:chat_read', args=[conversation.pk]), {'through_id': 1},
        ).status_code, 403)
        self.assertEqual(Message.objects.count(), 0)

    def test_post_replay_poll_and_escaping(self):
        conversation = self._open()
        url = reverse('marketplace:chat_thread', args=[conversation.pk])
        nonce = str(uuid4())
        body = '<script>alert("unsafe")</script>'
        for _ in range(2):
            self.assertEqual(self.client.post(
                url, {'body': body, 'client_nonce': nonce},
            ).status_code, 302)
        self.assertEqual(Message.objects.count(), 1)
        self.assertContains(self.client.get(url), '&lt;script&gt;')
        self.assertNotContains(self.client.get(url), '<script>alert')
        poll_url = reverse('marketplace:chat_poll', args=[conversation.pk])
        result = self.client.get(poll_url, {'after': 0})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()['messages'][0]['body'], body)
        self.assertEqual(
            self.client.get(poll_url, {'after': Message.objects.first().pk}).json()['messages'],
            [],
        )

    def test_csrf_and_rtl(self):
        conversation = self._open()
        url = reverse('marketplace:chat_thread', args=[conversation.pk])
        with override('he'):
            self.assertContains(self.client.get(url), 'dir="auto"')
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.owner)
        self.assertEqual(strict.post(url, {
            'body': 'Synthetic', 'client_nonce': str(uuid4()),
        }).status_code, 403)

    def test_persisted_poll_rate_limit(self):
        conversation = self._open()
        url = reverse('marketplace:chat_poll', args=[conversation.pk])
        for _ in range(24):
            self.assertEqual(self.client.get(url, {'after': 0}).status_code, 200)
        self.assertEqual(self.client.get(url, {'after': 0}).status_code, 400)
