"""04.3: authorization, IDOR, direct service ownership and idempotent POST."""
import uuid
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import AnonymousUser, Permission
from django.core.exceptions import PermissionDenied
from django.db import close_old_connections, connections
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.urls import reverse

from apps.locations.models import City
from apps.marketplace.admin import (
    OrderAdmin, OrderQuestionnaireAnswerAdmin, ResponseAdmin,
)
from apps.marketplace.models import (
    Category, Order, OrderQuestionnaireAnswer, OrderStatusEvent,
    Response, ServiceQuestionnaire, Subcategory,
)
from apps.marketplace.questionnaire_examples import DEMO_QUESTIONNAIRES
from apps.marketplace.questionnaire_services import publish_questionnaire
from apps.marketplace.services import (
    accept_response, cancel_order, complete_order, create_order,
)

from .factories import make_user


@override_settings(ZEMIPRO_PILOT_CITY_SLUG='ashdod')
class OrderOwnershipAndIdempotencyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.city = City.objects.create(
            slug='ashdod', name_ru='Ашдод', name_en='Ashdod', name_he='אשדוד',
        )
        cls.other_city = City.objects.create(slug='haifa', name_ru='Хайфа')
        cls.category = Category.objects.create(
            slug='s043-carpentry', name_ru='Столярные работы',
        )
        cls.owner = make_user('s043-owner')
        cls.other = make_user('s043-other')
        cls.worker = make_user('s043-worker')
        cls.staff = make_user('s043-moderator', is_staff=True)
        cls.staff.user_permissions.add(Permission.objects.get(
            content_type__app_label='moderation',
            codename='review_complaints',
        ))

    def payload(self, **kwargs):
        return {
            'category': str(self.category.pk), 'city': str(self.city.pk),
            'customer_name': 'Synthetic Owner', 'description':
            'Synthetic house repair with enough description for legacy input.',
            'price': '250 ₪',
            **kwargs,
        }

    def test_legacy_html_does_not_ask_for_precise_contact_fields(self):
        self.client.force_login(self.owner)
        page = self.client.get(reverse('marketplace:order_create'))
        self.assertEqual(page.status_code, 200)
        self.assertNotContains(page, 'id_customer_phone')
        self.assertNotContains(page, 'id_address')
        self.assertContains(page, reverse('marketplace:order_wizard_start'))

    def test_legacy_post_replay_without_token_returns_same_order_and_event(self):
        self.client.force_login(self.owner)
        url = reverse('marketplace:order_create')
        first = self.client.post(url, self.payload())
        again = self.client.post(url, self.payload())
        self.assertEqual(first.status_code, 302)
        self.assertEqual(again.status_code, 302)
        self.assertEqual(first.url, again.url)
        self.assertEqual(Order.objects.filter(client=self.owner).count(), 1)
        order = Order.objects.get(client=self.owner)
        self.assertEqual(order.status, Order.Status.PUBLISHED)
        self.assertEqual(order.address, '')
        self.assertEqual(order.customer_phone, '')
        self.assertEqual(order.status_events.count(), 1)
        self.assertEqual(OrderStatusEvent.objects.count(), 1)
        self.assertEqual(order.notifications.count(), 1)

    def test_explicit_key_replay_and_mismatch_are_denied_without_new_order(self):
        self.client.force_login(self.owner)
        url = reverse('marketplace:order_create')
        key = str(uuid.uuid4())
        data = self.payload(submission_key=key)
        first = self.client.post(url, data)
        second = self.client.post(url, data)
        self.assertEqual((first.status_code, second.status_code), (302, 302))
        order = Order.objects.get(client=self.owner)
        self.assertEqual(str(order.wizard_token), key)
        self.assertEqual(order.status_events.count(), 1)
        altered = self.client.post(url, self.payload(
            submission_key=key, description='Another synthetic long description'
        ))
        self.assertEqual(altered.status_code, 403)
        self.assertEqual(Order.objects.count(), 1)

    def test_reusing_another_account_key_never_returns_foreign_order(self):
        key = str(uuid.uuid4())
        self.client.force_login(self.owner)
        self.assertEqual(self.client.post(
            reverse('marketplace:order_create'),
            self.payload(submission_key=key),
        ).status_code, 302)
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(
            reverse('marketplace:order_create'),
            self.payload(submission_key=key),
        ).status_code, 403)
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(Order.objects.get().client_id, self.owner.pk)

    def test_forged_client_id_and_worker_id_are_ignored(self):
        self.client.force_login(self.owner)
        payload = self.payload(client=str(self.other.pk), worker=str(self.worker.pk))
        response = self.client.post(reverse('marketplace:order_create'), payload)
        self.assertEqual(response.status_code, 302)
        order = Order.objects.get()
        self.assertEqual(order.client_id, self.owner.pk)
        self.assertIsNone(order.worker_id)

    def test_guest_csrf_and_persisted_block_denied_at_http_boundary(self):
        url = reverse('marketplace:order_create')
        self.assertEqual(self.client.post(url, self.payload()).status_code, 302)
        self.assertFalse(Order.objects.exists())
        protected = Client(enforce_csrf_checks=True)
        protected.force_login(self.owner)
        self.assertEqual(protected.post(url, self.payload()).status_code, 403)
        self.assertFalse(Order.objects.exists())
        self.client.force_login(self.owner)
        self.owner.is_blocked = True
        self.owner.save(update_fields=['is_blocked'])
        self.assertEqual(self.client.post(url, self.payload()).status_code, 403)
        self.assertFalse(Order.objects.exists())

    def test_legacy_http_cannot_bypass_ashdod_only(self):
        self.client.force_login(self.owner)
        response = self.client.post(reverse('marketplace:order_create'), self.payload(
            city=str(self.other_city.pk),
        ))
        self.assertEqual(response.status_code, 200)
        self.assertIn('city', response.context['form'].errors)
        self.assertFalse(Order.objects.exists())

    def test_direct_create_checks_owner_status_and_deduplicates(self):
        for actor in (None, AnonymousUser()):
            with self.subTest(actor=actor), self.assertRaises(ValueError):
                create_order(actor, self.category, self.city, '', 'Synthetic request')
        created = create_order(
            self.owner, self.category, self.city, '', 'Synthetic request'
        )
        again = create_order(
            self.owner, self.category, self.city, '', 'Synthetic request'
        )
        self.assertEqual(again.pk, created.pk)
        self.assertEqual(created.status_events.count(), 1)
        self.owner.email_verification_required = True
        self.owner.save(update_fields=['email_verification_required'])
        with self.assertRaisesMessage(ValueError, 'Аккаунт недоступен'):
            create_order(self.owner, self.category, self.city, '', 'Synthetic request')
        self.assertEqual(Order.objects.count(), 1)

    def test_direct_service_cannot_bypass_published_required_questions(self):
        service = Subcategory.objects.create(
            category=self.category, slug='s043-questionnaire',
            name_ru='Синтетическая услуга',
        )
        template = ServiceQuestionnaire.objects.create(
            service=service, draft_schema=DEMO_QUESTIONNAIRES[0][2],
        )
        version, _ = publish_questionnaire(template.pk)
        with self.assertRaises(ValueError):
            create_order(
                self.owner, self.category, self.city, '', 'Synthetic request',
                subcategory=service,
            )
        self.assertFalse(Order.objects.exists())
        order = create_order(
            self.owner, self.category, self.city, '', 'Synthetic request',
            subcategory=service, questionnaire_version=version,
            questionnaire_answers={'issue': 'pipe', 'urgent': False},
        )
        self.assertEqual(
            OrderQuestionnaireAnswer.objects.get(order=order).answers,
            {'issue': 'pipe', 'urgent': False},
        )
        self.assertEqual(order.status_events.count(), 1)

    def test_service_owner_required_for_accept_cancel_and_complete(self):
        order = create_order(
            self.owner, self.category, self.city, '', 'Synthetic request'
        )
        response = Response.objects.create(order=order, worker=self.worker)
        for actor in (self.other, AnonymousUser(), None):
            with self.subTest(actor=actor), self.assertRaises(PermissionDenied):
                accept_response(response, actor=actor)
            with self.assertRaises(PermissionDenied):
                cancel_order(order, actor=actor)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PUBLISHED)
        self.assertEqual(order.status_events.count(), 1)
        chosen = accept_response(response, actor=self.owner)
        self.assertEqual(chosen.status, Response.Status.ACCEPTED)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.IN_PROGRESS)
        with self.assertRaises(PermissionDenied):
            complete_order(order, actor=self.other)
        self.assertEqual(Order.objects.get(pk=order.pk).status, Order.Status.IN_PROGRESS)
        complete_order(order, actor=self.owner)
        self.assertEqual(Order.objects.get(pk=order.pk).status, Order.Status.COMPLETED)

    def test_assignee_cannot_read_exact_address_phone_or_free_text(self):
        order = Order.objects.create(
            client=self.owner, worker=self.worker, category=self.category,
            city=self.city, status=Order.Status.IN_PROGRESS,
            address='PRIVATE_043_STREET_22',
            customer_name='PRIVATE_043_NAME',
            customer_phone='+972999000043',
            description='PRIVATE_043_DESCRIPTION_CONTACT',
        )
        url = reverse('marketplace:order_detail', args=[order.pk])
        for actor in (self.worker, self.other):
            with self.subTest(actor=actor.username):
                self.client.force_login(actor)
                result = self.client.get(url)
                self.assertEqual(result.status_code, 200)
                for forbidden in (
                    order.address, order.customer_phone,
                    order.customer_name, order.description,
                ):
                    self.assertNotContains(result, forbidden)
        for actor in (self.owner, self.staff):
            self.client.force_login(actor)
            result = self.client.get(url)
            self.assertContains(result, order.address)
            self.assertContains(result, order.customer_phone)

    def test_assignee_does_not_receive_private_questionnaire_snapshot(self):
        # An unassigned worker should never be able to inspect private fields.
        order = Order.objects.create(
            client=self.owner, worker=self.worker, category=self.category,
            city=self.city, status=Order.Status.IN_PROGRESS,
            address='PRIVATE_043_AREA', description='PRIVATE_043_TEXT',
        )
        self.client.force_login(self.worker)
        response = self.client.get(reverse('marketplace:order_detail', args=[order.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'PRIVATE_043_TEXT')

    def test_admin_order_and_questionnaire_views_require_moderator_permission(self):
        from django.test import RequestFactory

        regular = make_user('s043-basic-staff', is_staff=True)
        regular.user_permissions.add(Permission.objects.get(
            content_type__app_label='marketplace', codename='view_order',
        ))
        factory = RequestFactory()
        req = factory.get('/admin/marketplace/order/')
        site = AdminSite()
        for actor, expected in ((regular, False), (self.other, False), (self.staff, True)):
            req.user = actor
            for model, admin_type in (
                (Order, OrderAdmin),
                (Response, ResponseAdmin),
                (OrderQuestionnaireAnswer, OrderQuestionnaireAnswerAdmin),
            ):
                with self.subTest(actor=actor.username, admin=admin_type.__name__):
                    self.assertEqual(
                        admin_type(model, site).has_view_permission(req), expected,
                    )
        sensitive = Order.objects.create(
            client=self.owner, worker=self.worker,
            category=self.category, city=self.city,
            address='PRIVATE_ADMIN_ADDRESS_043',
            customer_phone='PRIVATE_ADMIN_PHONE_043',
            description='PRIVATE_ADMIN_DESCRIPTION_043',
        )
        self.client.force_login(regular)
        response = self.client.get(reverse('admin:marketplace_order_changelist'))
        self.assertEqual(response.status_code, 403)
        self.assertNotContains(response, sensitive.address, status_code=403)
        self.assertNotContains(response, sensitive.customer_phone, status_code=403)

    def test_unverified_session_cannot_create_or_edit(self):
        self.client.force_login(self.owner)
        self.owner.email_verification_required = True
        self.owner.save(update_fields=['email_verification_required'])
        url = reverse('marketplace:order_create')
        response = self.client.post(url, self.payload())
        self.assertNotEqual(response.status_code, 200)
        self.assertFalse(Order.objects.exists())


@override_settings(ZEMIPRO_PILOT_CITY_SLUG='ashdod')
class ParallelLegacySubmissionTests(TransactionTestCase):
    def setUp(self):
        self.city = City.objects.create(slug='ashdod', name_ru='Ашдод')
        self.category = Category.objects.create(
            slug='parallel-043', name_ru='Ремонт',
        )
        self.owner = make_user('parallel-043-owner')

    def test_concurrent_direct_calls_same_payload_produce_single_order(self):
        barrier = Barrier(2)

        def submit(_):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                order = create_order(
                    self.owner, self.category, self.city,
                    '', 'Concurrent identical synthetic request.',
                    price='150 ₪',
                )
                return order.pk
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            ids = list(pool.map(submit, range(2)))
        self.assertEqual(ids[0], ids[1])
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(OrderStatusEvent.objects.count(), 1)
