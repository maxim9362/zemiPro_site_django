"""Stage 04.5: owner-only management, durable drafts and append-only audit."""
from datetime import timedelta
import uuid

from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.db import DatabaseError, transaction
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import override

from apps.accounts.models import ClientProfile
from apps.locations.models import City
from apps.marketplace.models import (
    Category, Order, OrderManagementEvent, OrderQuestionnaireAnswer,
    OrderQuestionnaireAnswerArchive, Response,
    ServiceQuestionnaire, Subcategory,
)
from apps.marketplace.order_lifecycle import transition_order_status
from apps.marketplace.order_management import (
    OrderEditForm, duplicate_order, edit_published_order,
    management_timeline, withdraw_order,
)
from apps.marketplace.questionnaire_examples import DEMO_QUESTIONNAIRES
from apps.marketplace.questionnaire_services import publish_questionnaire
from apps.marketplace.wizard_forms import ConfirmStepForm

from .factories import make_user


@override_settings(ZEMIPRO_PILOT_CITY_SLUG='ashdod')
class OrderManagementTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.city = City.objects.create(
            slug='ashdod', name_ru='Ашдод', name_en='Ashdod', name_he='אשדוד',
        )
        cls.category = Category.objects.create(
            slug='management-045', name_ru='Ремонт', name_en='Repairs',
            name_he='תיקונים',
        )
        cls.service = Subcategory.objects.create(
            category=cls.category, slug='management-repair-045',
            name_ru='Сантехника', name_en='Plumbing', name_he='אינסטלציה',
            work_mode='onsite',
        )
        cls.owner = make_user('management-045-owner')
        cls.other = make_user('management-045-stranger')
        cls.worker = make_user('management-045-worker')
        ClientProfile.objects.create(user=cls.owner, city=cls.city)

    def setUp(self):
        self.client.force_login(self.owner)

    def order(self, **extra):
        attrs = {
            'client': self.owner, 'category': self.category,
            'subcategory': self.service, 'city': self.city,
            'description': 'Synthetic private plumbing task and conditions.',
            'price': 'Договорная',
        }
        attrs.update(extra)
        return Order.objects.create(**attrs)

    def payload(self, **extra):
        values = {
            'price_kind': 'range', 'amount_min_ils': '200.00',
            'amount_max_ils': '550.00',
            'preferred_date': (timezone.localdate() + timedelta(days=5)).isoformat(),
            'urgency': 'soon', 'work_mode': 'onsite',
            'approximate_area': 'Central Ashdod',
            'description': 'Synthetic corrected terms containing no personal contact.',
        }
        return {**values, **extra}

    def test_management_edit_persists_conditions_and_immutable_safe_history(self):
        order = self.order()
        url = reverse('marketplace:order_management_edit', args=[order.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        key = str(uuid.uuid4())
        post = self.client.post(url, {**self.payload(), 'operation_key': key})
        self.assertEqual(post.status_code, 302)
        order.refresh_from_db()
        self.assertEqual(order.price_kind, Order.PriceKind.RANGE)
        self.assertEqual(str(order.amount_min_ils), '200.00')
        self.assertEqual(str(order.amount_max_ils), '550.00')
        self.assertEqual(order.price, '200.00–550.00 ₪')
        self.assertEqual(order.approximate_area, 'Central Ashdod')
        self.assertEqual(order.status, Order.Status.PUBLISHED)
        self.assertEqual(self.client.post(url, {
            **self.payload(), 'operation_key': key,
        }).status_code, 302)
        self.assertEqual(order.management_events.count(), 1)
        event = order.management_events.get()
        self.assertEqual(event.action, OrderManagementEvent.Action.EDITED)
        self.assertIn('description', event.changed_fields)
        self.assertNotIn('Synthetic corrected', str(event.changed_fields))
        with self.assertRaises(DatabaseError):
            with transaction.atomic():
                OrderManagementEvent.objects.filter(pk=event.pk).update(action='duplicated')
        with self.assertRaises(DatabaseError):
            with transaction.atomic():
                OrderManagementEvent.objects.filter(pk=event.pk).delete()
        self.assertEqual(len(management_timeline(order)), 1)

    def test_edit_permissions_invalid_forms_and_assigned_lock(self):
        order = self.order()
        url = reverse('marketplace:order_management_edit', args=[order.pk])
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(url, self.payload()).status_code, 404)
        self.client.force_login(self.owner)
        bad = self.client.post(url, {
            **self.payload(amount_max_ils='50.00'),
            'operation_key': str(uuid.uuid4()),
        })
        self.assertEqual(bad.status_code, 200)
        self.assertIn('amount_max_ils', bad.context['form'].errors)
        self.assertFalse(order.management_events.exists())
        Order.objects.filter(pk=order.pk).update(
            worker=self.worker, status=Order.Status.IN_PROGRESS,
        )
        self.assertEqual(self.client.get(url).status_code, 404)
        with self.assertRaisesMessage(ValueError, 'Нельзя редактировать'):
            edit_published_order(
                order_id=order.pk, actor=self.owner, data=self.payload(),
                operation_key=uuid.uuid4(),
            )

    def test_direct_management_denies_foreign_unverified_and_blocked_actor(self):
        order = self.order()
        for actor in (self.other, AnonymousUser(), None):
            with self.subTest(actor=actor), self.assertRaises(PermissionDenied):
                duplicate_order(order_id=order.pk, actor=actor, operation_key=uuid.uuid4())
            with self.assertRaises(PermissionDenied):
                withdraw_order(order_id=order.pk, actor=actor, operation_key=uuid.uuid4())
            with self.assertRaises(PermissionDenied):
                edit_published_order(
                    order_id=order.pk, actor=actor, data=self.payload(),
                    operation_key=uuid.uuid4(),
                )
        self.owner.is_blocked = True
        self.owner.save(update_fields=['is_blocked'])
        with self.assertRaises(PermissionDenied):
            duplicate_order(
                order_id=order.pk, actor=self.owner, operation_key=uuid.uuid4(),
            )
        self.assertEqual(Order.objects.count(), 1)

    def test_duplicate_creates_private_draft_with_prefill_not_contacts_or_media(self):
        original = self.order(
            price_kind=Order.PriceKind.FIXED, amount_min_ils='400',
            description='Synthetic original work text',
            address='PRIVATE_STREET_045', customer_phone='0500000045',
            customer_name='Private customer', approximate_area='South Ashdod',
        )
        key = str(uuid.uuid4())
        url = reverse('marketplace:order_management_duplicate', args=[original.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        first = self.client.post(url, {'operation_key': key})
        self.assertEqual(first.status_code, 302)
        clone = Order.objects.get(client=self.owner, status=Order.Status.DRAFT)
        self.assertEqual(first.url, reverse(
            'marketplace:order_wizard_edit', args=[clone.pk],
        ))
        self.assertNotEqual(clone.pk, original.pk)
        self.assertEqual(clone.address, '')
        self.assertEqual(clone.customer_phone, '')
        self.assertEqual(clone.customer_name, '')
        self.assertEqual(clone.description, '')
        self.assertEqual(clone.price, 'Договорная')
        self.assertEqual(clone.wizard_data['prefill']['6']['description'],
                         original.description)
        self.assertEqual(clone.wizard_data['prefill']['5']['amount_min'], '400.00')
        self.assertTrue(clone.wizard_token)
        self.assertFalse(clone.attachments.exists())
        self.assertEqual(self.client.post(url, {
            'operation_key': key,
        }).status_code, 302)
        self.assertEqual(Order.objects.count(), 2)
        self.assertEqual(original.management_events.count(), 1)
        self.assertEqual(clone.status_events.count(), 1)
        # Draft prefill survives the next view/session without duplicate POST.
        browser = Client()
        browser.force_login(self.owner)
        page = browser.get(reverse('marketplace:order_wizard_edit', args=[clone.pk]))
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.context['step'], 2)

    def test_withdraw_and_republish_preserve_status_history(self):
        order = self.order(wizard_token=uuid.uuid4(), wizard_data={
            'steps': {
                '1': {'category_id': self.category.pk, 'subcategory_id': self.service.pk},
                '2': {'version_id': None, 'answers': {}},
                '3': {'city_id': self.city.pk, 'mode': 'onsite',
                      'area': 'Central Ashdod'},
                '4': {'preferred_date': '', 'urgency': 'normal'},
                '5': {'price_type': 'negotiable', 'amount_min': '', 'amount_max': ''},
                '6': {'description': 'Synthetic task ready for republication.'},
                '7': {'display_name': 'Synthetic Owner', 'chat_only': True},
            },
        })
        key = uuid.uuid4()
        withdrawn, created = withdraw_order(
            order_id=order.pk, actor=self.owner, operation_key=key,
        )
        self.assertTrue(created)
        self.assertEqual(withdrawn.status, Order.Status.DRAFT)
        repeated, changed = withdraw_order(
            order_id=order.pk, actor=self.owner, operation_key=key,
        )
        self.assertFalse(changed)
        self.assertEqual(repeated.status, Order.Status.DRAFT)
        from apps.marketplace.wizard_services import publish_order_wizard
        published, changed = publish_order_wizard(
            order_id=order.pk, actor=self.owner,
            confirmation_form=ConfirmStepForm(data={'confirm': 'on'}),
        )
        self.assertTrue(changed)
        self.assertEqual(published.status, Order.Status.PUBLISHED)
        self.assertEqual(list(order.status_events.order_by('pk').values_list(
            'previous_status', 'new_status',
        )), [('published', 'draft'), ('draft', 'published')])
        self.assertEqual(len(management_timeline(order)), 2)

    def test_cannot_withdraw_when_any_responses_exist(self):
        order = self.order()
        Response.objects.create(order=order, worker=self.worker)
        with self.assertRaisesMessage(ValueError, 'При наличии откликов'):
            withdraw_order(
                order_id=order.pk, actor=self.owner,
                operation_key=uuid.uuid4(),
            )
        url = reverse('marketplace:order_management_withdraw', args=[order.pk])
        self.assertEqual(self.client.post(url, {
            'operation_key': str(uuid.uuid4()),
        }).status_code, 302)
        self.assertEqual(Order.objects.get(pk=order.pk).status, Order.Status.PUBLISHED)
        self.assertFalse(order.status_events.exists())

    def test_legacy_can_withdraw_and_requires_new_service_selection(self):
        order = self.order(subcategory=None, wizard_token=None)
        result, _ = withdraw_order(
            order_id=order.pk, actor=self.owner, operation_key=uuid.uuid4(),
        )
        self.assertEqual(result.status, Order.Status.DRAFT)
        self.assertIsNotNone(result.wizard_token)
        self.assertEqual(result.wizard_data['steps'], {})
        url = reverse('marketplace:order_wizard_edit', args=[order.pk])
        page = self.client.get(url)
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.context['step'], 1)
        self.assertNotContains(page, 'PRIVATE_STREET_045')

    def test_no_response_is_required_for_direct_transition_back_to_draft(self):
        order = self.order()
        Response.objects.create(order=order, worker=self.worker)
        with self.assertRaisesMessage(ValueError, 'после откликов'):
            transition_order_status(order, Order.Status.DRAFT, actor=self.owner)
        self.assertEqual(Order.objects.get(pk=order.pk).status, Order.Status.PUBLISHED)

    def test_questionnaire_archives_old_snapshot_after_republication(self):
        questionnaire = ServiceQuestionnaire.objects.create(
            service=self.service,
            draft_schema=DEMO_QUESTIONNAIRES[0][2],
        )
        version, _ = publish_questionnaire(questionnaire.pk)
        order = self.order(wizard_token=uuid.uuid4(), wizard_data={
            'steps': {
                '1': {'category_id': self.category.pk, 'subcategory_id': self.service.pk},
                '2': {'version_id': version.pk, 'answers': {'issue': 'pipe', 'urgent': False}},
                '3': {'city_id': self.city.pk, 'mode': 'onsite', 'area': 'Ashdod center'},
                '4': {'preferred_date': '', 'urgency': 'normal'},
                '5': {'price_type': 'negotiable', 'amount_min': '', 'amount_max': ''},
                '6': {'description': 'Synthetic plumbing description'},
                '7': {'display_name': 'Owner', 'chat_only': True},
            }
        })
        OrderQuestionnaireAnswer.objects.create(
            order=order, version=version, schema_snapshot=version.schema,
            answers={'issue': 'pipe', 'urgent': False},
        )
        withdraw_order(
            order_id=order.pk, actor=self.owner, operation_key=uuid.uuid4(),
        )
        order.refresh_from_db()
        updated = order.wizard_data
        updated['steps']['2']['answers'] = {
            'issue': 'pipe', 'urgent': True, 'access': 'Synthetic access details',
        }
        order.wizard_data = updated
        order.save(update_fields=['wizard_data'])
        from apps.marketplace.wizard_services import publish_order_wizard
        published, _ = publish_order_wizard(
            order_id=order.pk, actor=self.owner,
            confirmation_form=ConfirmStepForm(data={'confirm': 'on'}),
        )
        self.assertEqual(published.status, Order.Status.PUBLISHED)
        archive = OrderQuestionnaireAnswerArchive.objects.get(order=order)
        self.assertEqual(archive.answers, {'issue': 'pipe', 'urgent': False})
        self.assertEqual(OrderQuestionnaireAnswer.objects.get(order=order).answers['urgent'],
                         True)
        with self.assertRaises(DatabaseError):
            with transaction.atomic():
                OrderQuestionnaireAnswerArchive.objects.filter(pk=archive.pk).delete()

    def test_owner_dashboard_includes_drafts_and_is_bounded(self):
        for i in range(14):
            self.order(
                status=Order.Status.DRAFT, wizard_token=uuid.uuid4(),
                description='Synthetic draft hidden from others.',
            )
        self.order(status=Order.Status.IN_DISCUSSION)
        self.order(status=Order.Status.DISPUTED)
        self.order(status=Order.Status.EXPIRED)
        foreign = Order.objects.create(
            client=self.other, category=self.category, city=self.city,
            address='FOREIGN_PRIVATE_ADDRESS_045',
            description='FOREIGN_PRIVATE_CONTENT_045',
        )
        url = reverse('marketplace:client_dashboard')
        first = self.client.get(url)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(len(first.context['draft_orders']), 10)
        self.assertNotContains(first, foreign.address)
        self.assertEqual(len(first.context['active_orders']), 1)
        self.assertEqual(len(first.context['in_progress_orders']), 1)
        self.assertEqual(len(first.context['cancelled_orders']), 1)
        second = self.client.get(url, {'draft_page': '2'})
        self.assertEqual(len(second.context['draft_orders']), 4)

    def test_completed_orders_cannot_be_edited_or_withdrawn(self):
        order = self.order(status=Order.Status.COMPLETED)
        self.assertEqual(self.client.get(reverse(
            'marketplace:order_management_edit', args=[order.pk],
        )).status_code, 404)
        with self.assertRaises(ValueError):
            withdraw_order(
                order_id=order.pk, actor=self.owner, operation_key=uuid.uuid4(),
            )
        with self.assertRaises(ValueError):
            edit_published_order(
                order_id=order.pk, actor=self.owner, data=self.payload(),
                operation_key=uuid.uuid4(),
            )

    def test_edit_form_ils_date_area_and_description_rules(self):
        order = self.order()
        for changed in (
            {'amount_max_ils': '10.00'},
            {'approximate_area': 'Street 15 apartment 4'},
            {'preferred_date': (timezone.localdate() - timedelta(days=1)).isoformat()},
            {'description': ''},
        ):
            with self.subTest(changed=changed):
                form = OrderEditForm(data=self.payload(**changed), order=order)
                self.assertFalse(form.is_valid(), form.errors.as_json())
        with override('he'):
            self.assertTrue(OrderEditForm(order=order).fields['description'].label)
        self.assertFalse(order.management_events.exists())
