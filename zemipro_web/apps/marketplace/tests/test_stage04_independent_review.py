"""Independent review regressions ZP-04-001..006. Synthetic PostgreSQL only."""
from concurrent.futures import ThreadPoolExecutor
from tempfile import TemporaryDirectory
from threading import Barrier
from uuid import uuid4

from django.core.files.base import ContentFile
from django.db import close_old_connections, connections
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import override

from apps.accounts.models import ClientProfile
from apps.accounts.portfolio import private_portfolio_storage
from apps.locations.models import City
from apps.marketplace.models import (
    Category, Order, OrderAttachment, OrderDomainEvent,
    OrderManagementEvent, OrderStatusEvent, Subcategory,
)
from apps.marketplace.order_lifecycle import transition_order_status
from apps.marketplace.order_management import management_timeline, withdraw_order
from apps.marketplace.wizard_ui import localized_order_action, localized_order_status
from apps.notifications.models import Notification

from .factories import make_user


@override_settings(ZEMIPRO_PILOT_CITY_SLUG='ashdod')
class Stage04IndependentReviewFixTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.city = City.objects.create(
            slug='ashdod', name_ru='Ашдод', name_en='Ashdod',
            name_he='אשדוד',
        )
        cls.category = Category.objects.create(
            slug='review-fixes-04', name_ru='Ремонт',
            name_en='Repairs', name_he='תיקונים',
        )
        cls.service = Subcategory.objects.create(
            category=cls.category, slug='review-service-04',
            name_ru='Ремонт дома', name_en='Home repairs',
            name_he='תיקוני בית', work_mode='onsite',
        )
        cls.owner = make_user('stage04-review-owner')
        cls.other = make_user('stage04-review-stranger')
        cls.worker = make_user('stage04-review-worker')
        ClientProfile.objects.create(user=cls.owner, city=cls.city)

    def setUp(self):
        self.client.force_login(self.owner)
        root = TemporaryDirectory()
        self.addCleanup(root.cleanup)
        override = override_settings(ZEMIPRO_PRIVATE_MEDIA_ROOT=root.name)
        override.enable()
        self.addCleanup(override.disable)

    def order(self, **kwargs):
        values = {
            'client': self.owner, 'category': self.category,
            'subcategory': self.service, 'city': self.city,
            'description': 'Synthetic plumbing project, no real person.',
            'address': '', 'customer_phone': '',
        }
        values.update(kwargs)
        return Order.objects.create(**values)

    def photo(self, order, visibility, index):
        key = f'order-attachments/{uuid4().hex}.jpg'
        private_portfolio_storage().save(key, ContentFile(b'\xff\xd8test-only-jpeg'))
        return OrderAttachment.objects.create(
            order=order, uploaded_by=self.owner, file_key=key,
            visibility=visibility,
            public_consent_at=timezone.now() if visibility == 'public' else None,
            content_sha256=f'{index:064x}', byte_size=16,
        )

    def test_001_cancelled_unpublished_images_remain_private_for_every_role(self):
        order = self.order(
            status=Order.Status.DRAFT, wizard_token=uuid4(),
            wizard_data={'steps': {'1': {
                'category_id': self.category.pk, 'subcategory_id': self.service.pk,
            }}},
        )
        photos = [
            self.photo(order, visibility, i)
            for i, visibility in enumerate(('private', 'assignee', 'public'), 1)
        ]
        # The public consent was saved but publication never happened.
        for actor in (self.other, self.worker):
            self.client.force_login(actor)
            for photo in photos:
                self.assertEqual(self.client.get(reverse(
                    'marketplace:order_attachment_image', args=[photo.pk],
                )).status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get(reverse(
            'marketplace:order_attachment_image', args=[photos[2].pk],
        )).status_code, 404)
        transition_order_status(order, Order.Status.CANCELLED, actor=self.owner)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELLED)
        self.assertFalse(order.status_events.filter(
            new_status=Order.Status.PUBLISHED,
        ).exists())
        for actor in (None, self.other, self.worker):
            if actor is None:
                self.client.logout()
            else:
                self.client.force_login(actor)
            for photo in photos:
                self.assertEqual(self.client.get(reverse(
                    'marketplace:order_attachment_image', args=[photo.pk],
                )).status_code, 404)
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(reverse(
            'marketplace:order_attachment_image', args=[photos[2].pk],
        )).status_code, 200)

    def test_001_withdrawn_public_image_is_hidden_again(self):
        order = self.order(status=Order.Status.PUBLISHED, wizard_token=uuid4())
        photo = self.photo(order, 'public', 1)
        OrderStatusEvent.objects.create(
            order=order, actor=self.owner, previous_status='draft',
            new_status=Order.Status.PUBLISHED,
        )
        self.client.logout()
        self.assertEqual(self.client.get(reverse(
            'marketplace:order_attachment_image', args=[photo.pk],
        )).status_code, 200)
        transition_order_status(order, Order.Status.DRAFT, actor=self.owner)
        self.assertEqual(self.client.get(reverse(
            'marketplace:order_attachment_image', args=[photo.pk],
        )).status_code, 404)

    def test_002_incomplete_draft_cannot_publish_from_low_level_service(self):
        draft = self.order(
            status=Order.Status.DRAFT, wizard_token=uuid4(),
            wizard_data={'steps': {'1': {
                'category_id': self.category.pk,
                'subcategory_id': self.service.pk,
            }}},
        )
        with self.assertRaises(ValueError):
            transition_order_status(
                draft, Order.Status.PUBLISHED, actor=self.owner,
            )
        draft.refresh_from_db()
        self.assertEqual(draft.status, Order.Status.DRAFT)
        self.assertFalse(draft.status_events.filter(
            new_status=Order.Status.PUBLISHED,
        ).exists())
        self.assertFalse(OrderDomainEvent.objects.filter(
            order=draft, kind='order_published',
        ).exists())

    def test_004_withdraw_and_republish_preserves_historical_contacts(self):
        order = self.order(
            price='500 ₪', address='PRIVATE_STREET_004',
            customer_phone='PRIVATE_050_004',
            customer_name='Synthetic Contact',
        )
        withdrawn, created = withdraw_order(
            order_id=order.pk, actor=self.owner, operation_key=uuid4(),
        )
        self.assertTrue(created)
        self.assertEqual(withdrawn.status, Order.Status.DRAFT)
        edit = reverse('marketplace:order_wizard_edit', args=[order.pk])
        steps = {
            1: {'category': self.category.pk, 'subcategory': self.service.pk},
            2: {'questionnaire_version': ''},
            3: {'city': self.city.pk, 'mode': 'onsite', 'area': 'Ashdod center'},
            4: {'preferred_date': '', 'urgency': 'normal'},
            5: {'price_type': 'negotiable'},
            6: {'description': 'New synthetic description after re-publication.'},
            7: {'display_name': 'Synthetic Contact', 'chat_ack': 'on'},
            8: {'confirm': 'on'},
        }
        for step, values in steps.items():
            response = self.client.post(
                f'{edit}?step={step}',
                {'action': 'publish' if step == 8 else 'next', **values},
            )
            self.assertEqual(response.status_code, 302, (step, response.content[:300]))
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PUBLISHED)
        self.assertEqual(order.address, 'PRIVATE_STREET_004')
        self.assertEqual(order.customer_phone, 'PRIVATE_050_004')
        self.client.force_login(self.other)
        page = self.client.get(reverse('marketplace:order_detail', args=[order.pk]))
        self.assertNotContains(page, 'PRIVATE_STREET_004')
        self.assertNotContains(page, 'PRIVATE_050_004')

    def test_005_all_states_and_audit_actions_translate_to_english_hebrew(self):
        order = self.order(status=Order.Status.IN_DISCUSSION)
        OrderStatusEvent.objects.create(
            order=order, actor=self.owner, new_status=Order.Status.ASSIGNED,
        )
        OrderManagementEvent.objects.create(
            order=order, actor=self.owner,
            action=OrderManagementEvent.Action.EDITED,
            changed_fields=['description'],
        )
        for lang, state_text, action_text in (
            ('en', 'In discussion', 'Terms updated'),
            ('he', 'בדיון', 'פרטי הבקשה עודכנו'),
        ):
            with self.subTest(language=lang), override(lang):
                self.assertEqual(localized_order_status(order.status), state_text)
                self.assertEqual(order.localized_status, state_text)
                self.assertEqual(
                    localized_order_action('edited'), action_text,
                )
                timeline = management_timeline(order)
                self.assertIn('Professional selected' if lang == 'en'
                              else 'נבחר בעל מקצוע',
                              [event['summary'] for event in timeline])
                self.assertIn(action_text, [event['summary'] for event in timeline])
                for status in Order.Status.values:
                    self.assertNotEqual(
                        localized_order_status(status),
                        Order.Status(status).label if status != 'published' else
                        Order.Status.PUBLISHED.label,
                    )

    def test_006_all_dashboard_pagers_preserve_other_page_numbers(self):
        for i in range(12):
            self.order(status=Order.Status.DRAFT, wizard_token=uuid4())
            self.order(status=Order.Status.PUBLISHED)
        response = self.client.get(reverse('marketplace:client_dashboard'), {
            'draft_page': '2', 'active_page': '2',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'draft_page=1&amp;active_page=2')
        self.assertContains(response, 'active_page=1&amp;progress_page=1')
        self.assertContains(response, '&amp;draft_page=2')
        # No unrelated owner/private data is in the paginated HTML.
        self.order(client=self.other, address='PRIVATE_FOREIGN_006')
        page = self.client.get(reverse('marketplace:client_dashboard'))
        self.assertNotContains(page, 'PRIVATE_FOREIGN_006')


@override_settings(ZEMIPRO_PILOT_CITY_SLUG='ashdod')
class Stage04CompletionRaceTests(TransactionTestCase):
    """Real independent PostgreSQL connections exercise stale HTTP races."""

    def setUp(self):
        self.city = City.objects.create(slug='ashdod', name_ru='Ашдод')
        self.category = Category.objects.create(
            slug='race-review-04', name_ru='Ремонт',
        )
        self.owner = make_user('stage04-race-owner')
        self.worker = make_user('stage04-race-worker')
        self.order = Order.objects.create(
            client=self.owner, category=self.category, city=self.city,
            status=Order.Status.IN_PROGRESS, worker=self.worker,
            address='', description='Synthetic work completed.',
        )

    def parallel_posts(self, names):
        barrier = Barrier(2)

        def fire(name):
            close_old_connections()
            client = Client()
            try:
                client.force_login(self.owner)
                barrier.wait(timeout=15)
                response = client.post(reverse(name, args=[self.order.pk]))
                return response.status_code
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(fire, names))

    def test_003_two_completions_yield_one_notification_and_no_http_error(self):
        statuses = self.parallel_posts((
            'marketplace:order_complete', 'marketplace:order_complete',
        ))
        self.assertEqual(statuses, [302, 302])
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.COMPLETED)
        self.assertEqual(self.order.status_events.filter(
            new_status=Order.Status.COMPLETED,
        ).count(), 1)
        self.assertEqual(Notification.objects.filter(
            related_order=self.order, notification_type=Notification.Type.ORDER_COMPLETED,
        ).count(), 1)

    def test_003_cancel_competes_with_completion_without_http_500(self):
        statuses = self.parallel_posts((
            'marketplace:order_complete', 'marketplace:order_cancel',
        ))
        self.assertEqual(statuses, [302, 302])
        self.order.refresh_from_db()
        self.assertIn(self.order.status, (
            Order.Status.COMPLETED, Order.Status.CANCELLED,
        ))
        self.assertEqual(self.order.status_events.count(), 1)
        self.assertEqual(Notification.objects.filter(
            related_order=self.order, notification_type=Notification.Type.ORDER_COMPLETED,
        ).count(), int(self.order.status == Order.Status.COMPLETED))
