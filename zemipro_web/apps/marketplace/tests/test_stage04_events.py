"""Stage 04.7: transactionally durable order events and exactly-once local receipts."""
from concurrent.futures import ThreadPoolExecutor
from io import StringIO
from threading import Barrier
from unittest.mock import patch
import uuid

from django.core.management import call_command
from django.db import DatabaseError, close_old_connections, connections, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils.translation import override

from apps.accounts.models import ClientProfile
from apps.locations.models import City
from apps.marketplace.models import (
    Category, Order, OrderAnalyticsFact, OrderDomainEvent, OrderEventDelivery,
    Response, Subcategory,
)
from apps.marketplace.order_events import (
    deliver_order_events_for_order, emit_order_event, local_order_event_counts,
    process_order_delivery, replay_pending_order_events,
)
from apps.marketplace.order_management import edit_published_order
from apps.marketplace.services import cancel_order, create_order
from apps.marketplace.wizard_forms import ConfirmStepForm, ServiceStepForm
from apps.marketplace.wizard_services import (
    publish_order_wizard, start_order_wizard,
)
from apps.notifications.models import Notification

from .factories import make_user


@override_settings(ZEMIPRO_PILOT_CITY_SLUG='ashdod')
class OrderDomainOutboxTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.city = City.objects.create(
            slug='ashdod', name_ru='Ашдод',
            name_en='Ashdod', name_he='אשדוד',
        )
        cls.category = Category.objects.create(
            slug='047-repair', name_ru='Ремонт',
            name_en='Repair', name_he='תיקונים',
        )
        cls.service = Subcategory.objects.create(
            category=cls.category, slug='047-services',
            name_ru='Работа', work_mode='onsite',
        )
        cls.owner = make_user('047-owner')
        cls.worker = make_user('047-worker')
        cls.other = make_user('047-other')
        ClientProfile.objects.create(user=cls.owner, city=cls.city)

    def created_order(self, text='Synthetic event creation task.'):
        return create_order(
            self.owner, self.category, self.city,
            address='', description=text, subcategory=self.service,
        )

    def test_legacy_order_emits_created_and_published_with_replay_receipts(self):
        order = self.created_order()
        kinds = list(order.domain_events.order_by('pk').values_list('kind', flat=True))
        self.assertEqual(kinds, ['order_created', 'order_published'])
        self.assertEqual(order.domain_events.count(), 2)
        self.assertEqual(OrderEventDelivery.objects.count(), 4)
        self.assertFalse(order.notifications.exists())
        self.assertEqual(deliver_order_events_for_order(order), 4)
        self.assertEqual(deliver_order_events_for_order(order), 0)
        self.assertEqual(replay_pending_order_events(limit=30), 0)
        self.assertEqual(OrderEventDelivery.objects.filter(status='done').count(), 4)
        self.assertEqual(OrderAnalyticsFact.objects.count(), 2)
        self.assertEqual(local_order_event_counts(), {
            'order_created': 1, 'order_published': 1,
        })
        notice = Notification.objects.get(related_order=order)
        self.assertEqual(notice.recipient_id, self.owner.pk)
        self.assertEqual(notice.notification_type, Notification.Type.ORDER_CREATED)
        self.assertIsNotNone(notice.order_event_id)
        self.assertEqual(notice.order_event.kind, 'order_published')
        self.assertEqual(order.status_events.count(), 1)

    def test_legacy_http_notification_is_not_doubled_by_retry(self):
        self.client.force_login(self.owner)
        url = reverse('marketplace:order_create')
        payload = {
            'category': self.category.pk, 'subcategory': self.service.pk,
            'city': self.city.pk, 'customer_name': 'Synthetic Owner',
            'description': 'Synthetic request long enough for legacy creation.',
            'price': 'Договорная',
        }
        self.assertEqual(self.client.post(url, payload).status_code, 302)
        self.assertEqual(self.client.post(url, payload).status_code, 302)
        order = Order.objects.get(client=self.owner)
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(order.notifications.count(), 1)
        self.assertEqual(order.domain_events.count(), 2)
        self.assertEqual(OrderAnalyticsFact.objects.count(), 2)

    def test_draft_creation_then_publish_emits_once_and_no_draft_notice(self):
        form = ServiceStepForm({
            'category': self.category.pk, 'subcategory': self.service.pk,
        })
        order = start_order_wizard(
            actor=self.owner, form=form, token=str(uuid.uuid4()),
        )
        self.assertEqual(
            list(order.domain_events.values_list('kind', flat=True)),
            ['order_created'],
        )
        self.assertEqual(deliver_order_events_for_order(order), 2)
        self.assertFalse(Notification.objects.exists())
        order.wizard_data = {'steps': {
            '1': {'category_id': self.category.pk, 'subcategory_id': self.service.pk},
            '2': {'version_id': None, 'answers': {}},
            '3': {'city_id': self.city.pk, 'mode': 'onsite', 'area': ''},
            '4': {'preferred_date': '', 'urgency': 'normal'},
            '5': {'price_type': 'negotiable', 'amount_min': '', 'amount_max': ''},
            '6': {'description': 'Synthetic draft publishing test'},
            '7': {'display_name': '', 'chat_only': True},
        }}
        order.save(update_fields=['wizard_data'])
        published, created = publish_order_wizard(
            order_id=order.pk, actor=self.owner,
            confirmation_form=ConfirmStepForm(data={'confirm': 'on'}),
        )
        self.assertTrue(created)
        self.assertEqual(published.status, Order.Status.PUBLISHED)
        self.assertEqual(publish_order_wizard(
            order_id=order.pk, actor=self.owner,
            confirmation_form=ConfirmStepForm(data={'confirm': 'on'}),
        )[1], False)
        self.assertCountEqual(
            list(order.domain_events.values_list('kind', flat=True)),
            ['order_created', 'order_published'],
        )
        self.assertEqual(deliver_order_events_for_order(order), 2)
        self.assertEqual(Notification.objects.filter(related_order=order).count(), 1)

    def test_updated_and_cancelled_events_are_safe_and_deduplicate_worker_notices(self):
        order = self.created_order()
        Response.objects.create(order=order, worker=self.worker, message='Synthetic reply')
        self.assertEqual(deliver_order_events_for_order(order), 4)
        form_values = {
            'price_kind': 'fixed', 'amount_min_ils': '350.00',
            'amount_max_ils': '', 'preferred_date': '',
            'urgency': 'normal', 'work_mode': 'onsite',
            'approximate_area': 'Central Ashdod',
            'description': 'PRIVATE_NEW_DESCRIPTION_NOT_IN_EVENT',
        }
        op = uuid.uuid4()
        updated, changed = edit_published_order(
            order_id=order.pk, actor=self.owner, data=form_values,
            operation_key=op,
        )
        self.assertTrue(changed)
        self.assertEqual(updated.pk, order.pk)
        self.assertEqual(edit_published_order(
            order_id=order.pk, actor=self.owner, data=form_values,
            operation_key=op,
        )[1], False)
        self.assertEqual(
            OrderDomainEvent.objects.filter(kind='order_updated').count(), 1,
        )
        self.assertEqual(deliver_order_events_for_order(order), 2)
        worker_notice = Notification.objects.get(
            recipient=self.worker, notification_type=Notification.Type.ORDER_UPDATED,
        )
        with override('en'):
            self.assertEqual(worker_notice.localized_title, 'Request details updated')
            self.assertIn(str(order.pk), worker_notice.localized_message)
        with override('he'):
            self.assertEqual(worker_notice.localized_title, 'פרטי הבקשה עודכנו')
        self.assertEqual(worker_notice.related_order_id, order.pk)
        self.assertNotIn(
            'PRIVATE_NEW_DESCRIPTION_NOT_IN_EVENT',
            str(list(order.domain_events.values())),
        )

        cancel_order(order, actor=self.owner)
        self.assertEqual(deliver_order_events_for_order(order), 2)
        self.assertEqual(deliver_order_events_for_order(order), 0)
        self.assertEqual(Notification.objects.filter(
            recipient=self.worker,
            notification_type=Notification.Type.ORDER_CANCELLED,
        ).count(), 1)
        self.assertEqual(OrderAnalyticsFact.objects.filter(
            kind='order_cancelled',
        ).count(), 1)
        self.assertEqual(order.domain_events.count(), 4)

    def test_public_data_never_contained_in_domain_event_or_fact(self):
        order = create_order(
            self.owner, self.category, self.city,
            address='PRIVATE_STREET_047', description='PRIVATE_DESCRIPTION_047',
            customer_phone='050PRIVATE047', subcategory=self.service,
        )
        event = order.domain_events.first()
        self.assertNotIn('PRIVATE_STREET_047', str(event.__dict__))
        self.assertNotIn('PRIVATE_DESCRIPTION_047', str(event.__dict__))
        self.assertNotIn('050PRIVATE047', str(event.__dict__))
        deliver_order_events_for_order(order)
        fact = OrderAnalyticsFact.objects.get(event=event)
        self.assertEqual(fact.city_id, self.city.pk)
        self.assertEqual(fact.category_id, self.category.pk)
        self.assertNotIn('PRIVATE', str(fact.__dict__))

    def test_event_emission_requires_atomic_and_is_idempotent(self):
        order = self.created_order()
        source = uuid.uuid4()
        with transaction.atomic():
            first, created = emit_order_event(order, 'order_updated', source)
            same, created_again = emit_order_event(order, 'order_updated', source)
        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(first.pk, same.pk)
        self.assertEqual(first.deliveries.count(), 2)
        with self.assertRaises(DatabaseError):
            with transaction.atomic():
                OrderDomainEvent.objects.filter(pk=first.pk).update(kind='order_cancelled')
        with self.assertRaises(DatabaseError):
            with transaction.atomic():
                OrderDomainEvent.objects.filter(pk=first.pk).delete()

    def test_delivery_failure_keeps_pending_receipt_and_safe_error_code(self):
        order = self.created_order()
        receipt = OrderEventDelivery.objects.get(
            event__order=order,
            event__kind=OrderDomainEvent.Kind.PUBLISHED,
            consumer=OrderEventDelivery.Consumer.NOTIFICATIONS,
        )
        with patch(
            'apps.marketplace.order_events._deliver_in_app',
            side_effect=RuntimeError('SYNTHETIC_RAW_SECRET_MUST_NOT_LOG'),
        ):
            with self.assertRaises(RuntimeError):
                process_order_delivery(receipt.pk)
        receipt.refresh_from_db()
        self.assertEqual(receipt.status, OrderEventDelivery.Status.PENDING)
        self.assertEqual(receipt.attempts, 1)
        self.assertEqual(receipt.last_error_code, 'processing_failed')
        self.assertNotIn('SYNTHETIC_RAW_SECRET_MUST_NOT_LOG', receipt.last_error_code)
        self.assertFalse(Notification.objects.filter(related_order=order).exists())
        self.assertTrue(process_order_delivery(receipt.pk))
        self.assertFalse(process_order_delivery(receipt.pk))
        self.assertEqual(Notification.objects.filter(related_order=order).count(), 1)
        receipt.refresh_from_db()
        self.assertEqual(receipt.attempts, 2)
        self.assertEqual(receipt.status, OrderEventDelivery.Status.DONE)

    def test_operator_replay_is_bounded_and_does_not_send_external_mail(self):
        self.created_order()
        output = StringIO()
        call_command('replay_order_events', '--limit', '100', stdout=output)
        self.assertIn('Processed 4 local', output.getvalue())
        output = StringIO()
        call_command('replay_order_events', '--limit', '100', stdout=output)
        self.assertIn('Processed 0 local', output.getvalue())
        self.assertEqual(Notification.objects.count(), 1)
        self.assertEqual(OrderAnalyticsFact.objects.count(), 2)

    def test_outer_transaction_rollback_removes_event_and_order(self):
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                self.created_order()
                raise RuntimeError('synthetic rollback')
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(OrderDomainEvent.objects.count(), 0)
        self.assertEqual(OrderEventDelivery.objects.count(), 0)

    def test_disabled_or_blocked_worker_is_not_notified(self):
        order = self.created_order()
        Response.objects.create(order=order, worker=self.worker)
        self.worker.is_blocked = True
        self.worker.save(update_fields=['is_blocked'])
        cancel_order(order, actor=self.owner)
        deliver_order_events_for_order(order)
        self.assertEqual(Notification.objects.filter(recipient=self.worker).count(), 0)


@override_settings(ZEMIPRO_PILOT_CITY_SLUG='ashdod')
class ConcurrentOrderDeliveryTests(TransactionTestCase):
    def setUp(self):
        self.city = City.objects.create(slug='ashdod', name_ru='Ашдод')
        self.category = Category.objects.create(
            slug='parallel-047', name_ru='Ремонт',
        )
        self.owner = make_user('parallel-047-owner')

    def test_parallel_delivery_commits_only_one_notification(self):
        order = create_order(
            self.owner, self.category, self.city,
            address='', description='Synthetic parallel delivery.',
        )
        delivery = OrderEventDelivery.objects.get(
            event__order=order,
            event__kind=OrderDomainEvent.Kind.PUBLISHED,
            consumer=OrderEventDelivery.Consumer.NOTIFICATIONS,
        )
        barrier = Barrier(2)

        def run(_):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return process_order_delivery(delivery.pk)
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(run, range(2)))
        self.assertCountEqual(results, [True, False])
        self.assertEqual(Notification.objects.filter(related_order=order).count(), 1)
        self.assertEqual(OrderEventDelivery.objects.get(pk=delivery.pk).attempts, 1)
