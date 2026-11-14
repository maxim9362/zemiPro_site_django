"""Stage 04.1: lifecycle, replay and authorization regressions."""
import uuid

from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied
from django.db import DatabaseError, IntegrityError, transaction
from django.test import TestCase, override_settings

from apps.marketplace.models import Order, OrderStatusEvent, Response, Subcategory
from apps.marketplace.order_lifecycle import transition_order_status
from apps.marketplace.services import accept_response, cancel_order, create_order

from .factories import make_category, make_city, make_order, make_user, make_worker_profile


@override_settings(ZEMIPRO_PILOT_CITY_SLUG=None)
class OrderLifecycleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.city = make_city('stage04-ashdod')
        cls.other_city = make_city('stage04-haifa')
        cls.category = make_category('stage04-category')
        cls.service = Subcategory.objects.create(
            category=cls.category, slug='stage04-service', name_ru='Сервис',
            work_mode='onsite',
        )
        cls.owner = make_user('stage04-owner')
        cls.other_user = make_user('stage04-stranger')
        cls.worker = make_user('stage04-worker')

    def make_draft(self):
        # These status-transition tests use an otherwise valid materialized
        # wizard draft. A raw/incomplete draft may never publish via service.
        description = 'Synthetic service request for CI permissions checks.'
        steps = {
            '1': {'category_id': self.category.pk,
                  'subcategory_id': self.service.pk},
            '2': {'version_id': None, 'answers': {}},
            '3': {'city_id': self.city.pk, 'mode': 'onsite', 'area': ''},
            '4': {'preferred_date': '', 'urgency': 'normal'},
            '5': {'price_type': 'negotiable',
                  'amount_min': '', 'amount_max': ''},
            '6': {'description': description},
            '7': {'display_name': '', 'chat_only': True},
            '8': {'confirm': True},  # synthetic, already-confirmed lifecycle fixture
        }
        return make_order(
            client=self.owner, category=self.category,
            subcategory=self.service, city=self.city,
            status=Order.Status.DRAFT, wizard_token=uuid.uuid4(),
            wizard_data={'steps': steps}, description=description,
            price_kind=Order.PriceKind.NEGOTIABLE,
            work_mode=Order.WorkMode.ONSITE,
            urgency=Order.Urgency.NORMAL,
        )

    def test_direct_publish_requires_final_confirmation(self):
        order = self.make_draft()
        data = dict(order.wizard_data)
        data['steps'] = {k: v for k, v in data['steps'].items() if k != '8'}
        order.wizard_data = data
        order.save(update_fields=['wizard_data'])
        with self.assertRaises(ValueError):
            transition_order_status(order, Order.Status.PUBLISHED, actor=self.owner)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.DRAFT)
        self.assertFalse(order.status_events.filter(
            new_status=Order.Status.PUBLISHED,
        ).exists())

    def test_withdraw_requires_fresh_final_confirmation(self):
        order = self.make_draft()
        transition_order_status(order, Order.Status.PUBLISHED, actor=self.owner)
        transition_order_status(order, Order.Status.DRAFT, actor=self.owner)
        order.refresh_from_db()
        self.assertNotIn('8', order.wizard_data['steps'])
        with self.assertRaises(ValueError):
            transition_order_status(order, Order.Status.PUBLISHED, actor=self.owner)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.DRAFT)
        self.assertEqual(order.status_events.filter(
            new_status=Order.Status.PUBLISHED,
        ).count(), 1)

    def test_declared_states_and_default_published(self):
        self.assertEqual(set(Order.Status.values), {
            'draft', 'published', 'in_discussion', 'assigned',
            'in_progress', 'completed', 'cancelled', 'expired', 'disputed',
        })
        order = make_order(client=self.owner, category=self.category, city=self.city)
        self.assertEqual(order.status, Order.Status.PUBLISHED)

    def test_publish_discuss_republish_and_cancel_events(self):
        order = self.make_draft()
        for state in (
            Order.Status.PUBLISHED, Order.Status.IN_DISCUSSION,
            Order.Status.PUBLISHED, Order.Status.CANCELLED,
        ):
            transition_order_status(order, state, actor=self.owner)
        self.assertEqual(list(order.status_events.order_by('pk').values_list(
            'previous_status', 'new_status',
        )), [
            ('draft', 'published'), ('published', 'in_discussion'),
            ('in_discussion', 'published'), ('published', 'cancelled'),
        ])

    def test_invalid_and_terminal_transitions_do_not_write(self):
        order = self.make_draft()
        for state in (Order.Status.COMPLETED, Order.Status.IN_PROGRESS, 'new', 'bad'):
            with self.subTest(state=state), self.assertRaises(ValueError):
                transition_order_status(order, state, actor=self.owner)
        self.assertFalse(order.status_events.exists())
        transition_order_status(order, Order.Status.CANCELLED, actor=self.owner)
        with self.assertRaises(ValueError):
            transition_order_status(order, Order.Status.PUBLISHED, actor=self.owner)
        self.assertEqual(order.status_events.count(), 1)

    def test_idempotent_target_and_replayed_key(self):
        order = self.make_draft()
        key = uuid.uuid4()
        transition_order_status(order, Order.Status.PUBLISHED, actor=self.owner, operation_key=key)
        transition_order_status(order, Order.Status.PUBLISHED, actor=self.owner, operation_key=key)
        transition_order_status(order, Order.Status.PUBLISHED, actor=self.owner)
        self.assertEqual(order.status_events.count(), 1)
        transition_order_status(order, Order.Status.IN_DISCUSSION, actor=self.owner)
        transition_order_status(order, Order.Status.PUBLISHED, actor=self.owner, operation_key=key)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.IN_DISCUSSION)
        self.assertEqual(order.status_events.count(), 2)
        with self.assertRaises(ValueError):
            transition_order_status(order, Order.Status.CANCELLED, actor=self.owner, operation_key=key)

    def test_idor_guest_blocked_and_unverified_guards(self):
        order = self.make_draft()
        for actor in (self.other_user, AnonymousUser()):
            with self.subTest(actor=actor), self.assertRaises(PermissionDenied):
                transition_order_status(order, Order.Status.PUBLISHED, actor=actor)
        self.owner.is_blocked = True
        self.owner.save(update_fields=['is_blocked'])
        with self.assertRaises(PermissionDenied):
            transition_order_status(order, Order.Status.PUBLISHED, actor=self.owner)
        self.owner.is_blocked = False
        self.owner.email_verification_required = True
        self.owner.save(update_fields=['is_blocked', 'email_verification_required'])
        with self.assertRaises(PermissionDenied):
            transition_order_status(order, Order.Status.PUBLISHED, actor=self.owner)
        self.assertEqual(order.status_events.count(), 0)

    @override_settings(ZEMIPRO_PILOT_CITY_SLUG='ashdod')
    def test_ashdod_only_cannot_publish_foreign_city(self):
        order = make_order(
            client=self.owner, category=self.category,
            city=self.other_city, status=Order.Status.DRAFT,
        )
        with self.assertRaisesMessage(ValueError, 'Город пока не обслуживается'):
            transition_order_status(order, Order.Status.PUBLISHED, actor=self.owner)
        self.assertFalse(order.status_events.exists())

    def test_acceptance_generates_only_assigned_event(self):
        order = make_order(client=self.owner, category=self.category, city=self.city)
        with self.assertRaises(ValueError):
            transition_order_status(order, Order.Status.ASSIGNED, actor=self.owner)
        make_worker_profile(self.worker, city=self.city, category=self.category)
        response = Response.objects.create(order=order, worker=self.worker)
        accept_response(response, actor=self.owner)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.ASSIGNED)
        self.assertEqual(order.worker_id, self.worker.pk)
        self.assertEqual(list(order.status_events.order_by('pk').values_list(
            'previous_status', 'new_status',
        )), [('published', 'assigned')])
        replay = accept_response(response, actor=self.owner)
        self.assertFalse(replay._assignment_created)
        self.assertEqual(order.status_events.count(), 1)

    def test_create_and_repeat_cancel_no_duplicate_event(self):
        order = create_order(
            self.owner, self.category, self.city,
            'Synthetic private location', 'Synthetic service request',
        )
        cancel_order(order, actor=self.owner)
        cancel_order(order, actor=self.owner)
        self.assertEqual(list(order.status_events.order_by('pk').values_list(
            'previous_status', 'new_status',
        )), [('', 'published'), ('published', 'cancelled')])

    def test_database_constraint_rejects_old_new_status(self):
        order = self.make_draft()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Order.objects.filter(pk=order.pk).update(status='new')

    def test_status_events_are_append_only(self):
        order = self.make_draft()
        transition_order_status(order, Order.Status.PUBLISHED, actor=self.owner)
        event = order.status_events.get()
        with self.assertRaises(DatabaseError):
            with transaction.atomic():
                OrderStatusEvent.objects.filter(pk=event.pk).update(new_status='cancelled')
        with self.assertRaises(DatabaseError):
            with transaction.atomic():
                OrderStatusEvent.objects.filter(pk=event.pk).delete()
        self.assertEqual(order.status_events.count(), 1)
