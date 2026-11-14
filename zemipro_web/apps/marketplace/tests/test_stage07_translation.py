"""Stage 07.6: consent, privacy, IDOR, provider isolation and original retention."""
from unittest.mock import Mock, patch
from uuid import uuid4

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError, transaction
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.marketplace.chat_services import get_conversation, open_conversation, send_message
from apps.marketplace.models import Message, MessageTranslation, Response
from apps.marketplace.tests.factories import make_category, make_city, make_order, make_user
from apps.marketplace.translation_services import TranslationUnavailable, translate_message


class Stage07TranslationTests(TestCase):
    def setUp(self):
        city = make_city()
        category = make_category()
        self.customer = make_user('stage07-translation-customer')
        self.worker = make_user('stage07-translation-worker')
        self.stranger = make_user('stage07-translation-stranger')
        self.order = make_order(client=self.customer, category=category, city=city)
        self.offer = Response.objects.create(
            order=self.order, worker=self.worker, status=Response.Status.SENT,
        )
        self.conversation, created = open_conversation(
            response_id=self.offer.pk, actor=self.worker,
        )
        self.assertTrue(created)
        self.original, created = send_message(
            conversation_id=self.conversation.pk, actor=self.worker,
            body='Hello there', client_nonce=uuid4(),
        )
        self.assertTrue(created)

    @override_settings(ZEMIPRO_GEMINI_TRANSLATION_ENABLED=False)
    def test_gemini_disabled_does_not_block_chat_or_mutate_original(self):
        translator = Mock(return_value='Здравствуйте')
        with self.assertRaises(TranslationUnavailable):
            translate_message(
                message_id=self.original.pk, actor=self.customer,
                target_language='ru', consent=True, translator=translator,
            )
        translator.assert_not_called()
        self.assertEqual(MessageTranslation.objects.count(), 0)
        self.assertEqual(Message.objects.get(pk=self.original.pk).body, 'Hello there')
        new, created = send_message(
            conversation_id=self.conversation.pk, actor=self.customer,
            body='I am still connected', client_nonce=uuid4(),
        )
        self.assertTrue(created)
        self.assertEqual(new.body, 'I am still connected')
        self.assertEqual(
            get_conversation(
                conversation_id=self.conversation.pk, actor=self.customer,
            ).pk, self.conversation.pk,
        )

    @override_settings(ZEMIPRO_GEMINI_TRANSLATION_ENABLED=True)
    def test_consent_and_idor_gates_before_provider(self):
        translator = Mock(return_value='Здравствуйте')
        with self.assertRaises(PermissionDenied):
            translate_message(
                message_id=self.original.pk, actor=self.stranger,
                target_language='ru', consent=True, translator=translator,
            )
        with self.assertRaises(TranslationUnavailable):
            translate_message(
                message_id=self.original.pk, actor=self.customer,
                target_language='ru', consent=False, translator=translator,
            )
        with self.assertRaises(TranslationUnavailable):
            translate_message(
                message_id=self.original.pk, actor=self.customer,
                target_language='fr', consent=True, translator=translator,
            )
        translator.assert_not_called()

    @override_settings(ZEMIPRO_GEMINI_TRANSLATION_ENABLED=True)
    def test_unsafe_personal_data_never_reaches_provider(self):
        provider = Mock(return_value='unsafe')
        for text in (
            'Call +972501234567 please',
            'email user@example.invalid',
            'רחוב הרצל',
            'address downtown',
        ):
            msg, _ = send_message(
                conversation_id=self.conversation.pk, actor=self.worker,
                body=text, client_nonce=uuid4(),
            )
            with self.assertRaises(TranslationUnavailable):
                translate_message(
                    message_id=msg.pk, actor=self.customer, target_language='he',
                    consent=True, translator=provider,
                )
        provider.assert_not_called()
        self.assertEqual(MessageTranslation.objects.count(), 0)

    @override_settings(ZEMIPRO_GEMINI_TRANSLATION_ENABLED=True)
    def test_one_append_only_translation_and_original_for_three_languages(self):
        by_language = {'ru': 'Привет', 'en': 'Hi', 'he': 'שלום'}
        provider = Mock(side_effect=lambda original, lang: by_language[lang])
        for code in by_language:
            translated, created = translate_message(
                message_id=self.original.pk, actor=self.customer,
                target_language=code, consent=True, translator=provider,
            )
            self.assertTrue(created)
            self.assertEqual(translated.translated_body, by_language[code])
        translated, created = translate_message(
            message_id=self.original.pk, actor=self.worker, target_language='he',
            consent=False, translator=provider,
        )
        self.assertFalse(created)
        self.assertEqual(provider.call_count, 3)
        self.assertEqual(MessageTranslation.objects.count(), 3)
        self.assertEqual(Message.objects.get(pk=self.original.pk).body, 'Hello there')
        with self.assertRaises(DatabaseError), transaction.atomic():
            MessageTranslation.objects.filter(pk=translated.pk).update(
                translated_body='Falsified',
            )
        translated.translated_body = 'Altered'
        with self.assertRaises(ValidationError):
            translated.save()

    @override_settings(ZEMIPRO_GEMINI_TRANSLATION_ENABLED=True)
    def test_failed_provider_does_not_modify_chat(self):
        provider = Mock(side_effect=TimeoutError('Synthetic network failure'))
        with self.assertRaises(TranslationUnavailable):
            translate_message(
                message_id=self.original.pk, actor=self.customer,
                target_language='ru', consent=True, translator=provider,
            )
        self.assertEqual(MessageTranslation.objects.count(), 0)
        self.assertEqual(Message.objects.get(pk=self.original.pk).body, 'Hello there')
        self.assertEqual(
            self.conversation.messages.filter(pk=self.original.pk).count(), 1,
        )

    @override_settings(ZEMIPRO_GEMINI_TRANSLATION_ENABLED=True)
    def test_quota_enforced_across_messages(self):
        translator = Mock(return_value='Synthetic translation')
        ids = [self.original.pk]
        for idx in range(10):
            msg, _ = send_message(
                conversation_id=self.conversation.pk, actor=self.worker,
                body=f'Synthetic word number {chr(65 + idx)}',
                client_nonce=uuid4(),
            )
            ids.append(msg.pk)
        for mid in ids[:10]:
            row, created = translate_message(
                message_id=mid, actor=self.customer, target_language='ru',
                consent=True, translator=translator,
            )
            self.assertTrue(created)
        with self.assertRaises(TranslationUnavailable):
            translate_message(
                message_id=ids[10], actor=self.customer,
                target_language='ru', consent=True, translator=translator,
            )
        self.assertEqual(translator.call_count, 10)
        self.assertEqual(MessageTranslation.objects.count(), 10)

    @override_settings(ZEMIPRO_GEMINI_TRANSLATION_ENABLED=True)
    def test_http_translation_marked_original_retrievable_and_csrf(self):
        url = reverse('marketplace:chat_translate', args=[self.original.pk])
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.customer)
        self.assertEqual(strict.post(url, {
            'target_language': 'ru', 'consent': 'yes',
        }).status_code, 403)
        self.client.force_login(self.stranger)
        self.assertEqual(self.client.post(url, {
            'target_language': 'ru', 'consent': 'yes',
        }).status_code, 403)
        self.client.force_login(self.customer)
        with patch(
            'apps.marketplace.translation_services._gemini_translation',
            return_value='<script>alert(1)</script>',
        ):
            page = self.client.post(url, {'target_language': 'ru', 'consent': 'yes'})
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'Показать оригинал')
        self.assertContains(page, 'Машинный перевод')
        self.assertContains(page, '&lt;script&gt;')
        self.assertNotContains(page, '<script>alert(1)</script>')
        self.assertContains(page, 'Hello there')

    @override_settings(ZEMIPRO_GEMINI_TRANSLATION_ENABLED=False)
    def test_http_disabled_returns_safe_error_without_chat_outage(self):
        self.client.force_login(self.customer)
        url = reverse('marketplace:chat_translate', args=[self.original.pk])
        page = self.client.post(url, {'target_language': 'he', 'consent': 'yes'})
        self.assertEqual(page.status_code, 503)
        self.assertContains(page, 'Hello there', status_code=503)
        self.assertEqual(MessageTranslation.objects.count(), 0)
        chat_url = reverse('marketplace:chat_thread', args=[self.conversation.pk])
        self.assertEqual(self.client.get(chat_url).status_code, 200)
