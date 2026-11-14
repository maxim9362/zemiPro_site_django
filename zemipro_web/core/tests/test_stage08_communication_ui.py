"""Stage 08.5: private communication UI regressions on synthetic Django data."""
from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.locations.models import City
from apps.marketplace.chat_services import open_conversation, send_message
from apps.marketplace.models import Category, Order, Rating, Response
from apps.marketplace.tests.factories import make_order, make_user
from apps.moderation.models import Complaint, ModerationEvent
from apps.notifications.models import Notification


class CommunicationSourceTests(SimpleTestCase):
    def test_safe_dynamic_chat_controls_and_accessible_css(self):
        base = Path(settings.BASE_DIR)
        script = (base / 'static/js/stage07_chat.js').read_text(encoding='utf-8')
        page = (base / 'templates/pages/chat_thread.html').read_text(
            encoding='utf-8'
        )
        actions = (base / 'templates/components/chat_message_actions.html').read_text(
            encoding='utf-8'
        )
        css = (base / 'static/css/communication.css').read_text(encoding='utf-8')
        shell = (base / 'templates/pages/communication_base.html').read_text(
            encoding='utf-8'
        )
        self.assertIn("extends 'pages/app_base.html'", shell)
        self.assertIn('cloneNode(true)', script)
        self.assertIn('body.textContent', script)
        self.assertIn('nearBottom', script)
        self.assertNotIn('innerHTML =', script)
        self.assertNotIn('localStorage.', script)
        self.assertNotIn('sessionStorage.', script)
        self.assertIn('chat-actions-sender', page)
        self.assertIn('chat-actions-receiver', page)
        self.assertIn('role="log"', page)
        self.assertIn('{% load i18n static %}', page)
        self.assertIn('{% csrf_token %}', actions)
        self.assertIn('name="consent" value="yes" required', actions)
        self.assertIn('message_id=message_id', actions)
        self.assertIn('@media(max-width:390px)', css)
        for name in ('complaint_create.html', 'queue.html', 'appeal.html'):
            html = (base / 'templates/moderation' / name).read_text(
                encoding='utf-8'
            )
            self.assertNotIn('javascript:history.back()', html)


@override_settings(ZEMIPRO_PILOT_CITY_SLUG='ashdod')
class CommunicationPageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.city = City.objects.create(
            slug='ashdod', name_ru='Ашдод',
            name_en='Ashdod', name_he='אשדוד',
        )
        cls.category = Category.objects.create(
            slug='qa08-communication', name_ru='Услуги',
            name_en='Services', name_he='שירותים',
        )
        cls.owner = make_user('commui-owner')
        cls.worker = make_user('commui-worker')
        cls.other = make_user('commui-other')
        cls.mod = make_user('commui-moderator', is_staff=True)
        cls.order = make_order(
            client=cls.owner, category=cls.category, city=cls.city,
            status=Order.Status.PUBLISHED,
        )
        cls.offer = Response.objects.create(
            order=cls.order, worker=cls.worker, status=Response.Status.SENT,
        )
        perm = Permission.objects.get(
            content_type=ContentType.objects.get_for_model(ModerationEvent),
            codename='review_complaints',
        )
        cls.mod.user_permissions.add(perm)

    def setUp(self):
        self.conversation, _ = open_conversation(
            response_id=self.offer.pk, actor=self.owner,
        )

    def test_chat_actions_escape_untrusted_body_and_reject_strangers(self):
        message, _ = send_message(
            conversation_id=self.conversation.pk, actor=self.worker,
            body='<script>alert("unsafe")</script>', client_nonce=uuid4(),
        )
        url = reverse('marketplace:chat_thread', args=[self.conversation.pk])
        self.client.force_login(self.owner)
        page = self.client.get(url)
        self.assertEqual(page.status_code, 200)
        for value in (
            'communication.css', 'data-poll-url=', 'data-can-send=',
            'data-message-id="' + str(message.pk) + '"',
            reverse('marketplace:chat_translate', args=[message.pk]),
            '?message=' + str(message.pk), 'chat-actions-sender',
            'chat-actions-receiver', 'name="target_language"',
            'name="consent" value="yes" required', '&lt;script&gt;',
        ):
            self.assertContains(page, value)
        self.assertNotContains(page, '<script>alert("unsafe")</script>')
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_chat_languages_and_no_js_fallback(self):
        self.client.force_login(self.owner)
        url = reverse('marketplace:chat_thread', args=[self.conversation.pk])
        for lang, direction in (('ru', 'ltr'), ('en', 'ltr'), ('he', 'rtl')):
            with self.subTest(lang=lang):
                result = self.client.get(url, HTTP_ACCEPT_LANGUAGE=lang)
                self.assertContains(
                    result, f'<html lang="{lang}" dir="{direction}">'
                )
                self.assertContains(result, '<noscript>')
                self.assertContains(result, 'role="log"')

    def test_notifications_and_email_preferences_remain_private(self):
        notice = Notification.objects.create(
            recipient=self.owner, title='Новый отклик',
            message='Ответ по заявке',
            notification_type=Notification.Type.NEW_RESPONSE,
            related_order=self.order,
        )
        self.client.force_login(self.owner)
        url = reverse('notifications:notification_list')
        page = self.client.get(url)
        self.assertContains(page, 'comm-notification--unread')
        self.assertContains(page, reverse(
            'notifications:notification_mark_read', args=[notice.pk],
        ))
        prefs = self.client.get(reverse('notifications:notification_preferences'))
        self.assertContains(prefs, 'name="email_optional"')
        self.assertContains(prefs, 'disabled')
        self.assertEqual(self.client.post(reverse(
            'notifications:notification_mark_read', args=[notice.pk],
        )).status_code, 302)
        notice.refresh_from_db()
        self.assertTrue(notice.is_read)
        self.client.force_login(self.other)
        outsider = self.client.get(url)
        self.assertNotIn(
            notice.pk, [item.pk for item in outsider.context['page_obj']]
        )

    def test_verified_rating_and_worker_reply_have_same_post_contract(self):
        completed = make_order(
            client=self.owner, category=self.category, city=self.city,
            worker=self.worker, status=Order.Status.COMPLETED,
        )
        url = reverse('marketplace:rating_create', args=[completed.pk])
        self.client.force_login(self.owner)
        page = self.client.get(url)
        self.assertEqual(page.status_code, 200)
        for needle in ('comm-review-form', 'name="rating"', 'name="review_text"'):
            self.assertContains(page, needle)
        rating = Rating.objects.create(
            client=self.owner, worker=self.worker, order=completed,
            rating=5, review_text='Synthetic service experience',
        )
        self.client.force_login(self.worker)
        detail = self.client.get(reverse(
            'marketplace:order_detail', args=[completed.pk],
        ))
        self.assertContains(detail, reverse(
            'marketplace:rating_reply', args=[rating.pk],
        ))
        self.assertContains(detail, 'Отправить ответ')
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(url).status_code, 404)
        outsider = self.client.get(reverse(
            'marketplace:order_detail', args=[completed.pk],
        ))
        self.assertNotContains(outsider, reverse(
            'marketplace:rating_reply', args=[rating.pk],
        ))
        # A blocked selected worker must not acquire a new UI capability.
        self.worker.is_blocked = True
        self.worker.save(update_fields=['is_blocked'])
        self.client.force_login(self.worker)
        blocked = self.client.get(reverse(
            'marketplace:order_detail', args=[completed.pk],
        ))
        self.assertEqual(blocked.status_code, 403)
        self.assertNotIn(
            reverse('marketplace:rating_reply', args=[rating.pk]),
            blocked.content.decode(),
        )

    def test_participant_report_moderator_decision_and_appeal(self):
        msg, _ = send_message(
            conversation_id=self.conversation.pk, actor=self.worker,
            body='Synthetic private reported content', client_nonce=uuid4(),
        )
        report = reverse('moderation:complaint_create') + '?message=' + str(msg.pk)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(report).status_code, 404)
        self.client.force_login(self.owner)
        self.assertContains(self.client.get(report), 'name="reason"')
        result = self.client.post(report, {
            'reason': Complaint.Reason.OTHER,
            'message': 'Synthetic report about the private message',
        })
        self.assertEqual(result.status_code, 302)
        case = Complaint.objects.get(target_message_id=msg.pk)
        self.assertEqual(
            self.client.get(reverse('moderation:queue')).status_code, 403
        )
        self.client.force_login(self.mod)
        queue = self.client.get(reverse('moderation:queue'))
        self.assertContains(queue, 'name="action" value="resolve"')
        self.assertContains(queue, 'name="action" value="dismiss"')
        self.assertContains(queue, 'Synthetic report about the private message')
        self.assertEqual(self.client.post(reverse(
            'moderation:decision', args=[case.pk],
        ), {'action': 'resolve', 'note': 'Reviewed synthetic evidence'}).status_code, 302)
        self.client.force_login(self.owner)
        appeal = self.client.get(reverse('moderation:appeal', args=[case.pk]))
        self.assertEqual(appeal.status_code, 200)
        self.assertContains(appeal, 'name="reason"')
