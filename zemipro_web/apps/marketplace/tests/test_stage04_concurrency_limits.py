"""Stage 04.6: shared PostgreSQL quotas and concurrent order mutations."""
from concurrent.futures import ThreadPoolExecutor
from tempfile import TemporaryDirectory
from threading import Barrier
from unittest.mock import patch
import uuid

from django.core.exceptions import PermissionDenied
from django.db import close_old_connections, connections, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse

from apps.accounts.models import ClientProfile, WorkerProfile
from apps.locations.models import City
from apps.marketplace.attachment_services import (
    store_photos_on_locked_order, validate_order_photo_batch,
)
from apps.marketplace.models import (
    Category, Order, OrderAttachment, OrderStatusEvent, OrderWriteQuota,
    Response, Subcategory,
)
from apps.marketplace.order_quota import (
    ORDER_WRITE_LIMITS, OrderQuotaExceeded, consume_order_quota,
)
from apps.marketplace.services import accept_response, create_order, create_response
from apps.marketplace.wizard_forms import ConfirmStepForm, DescriptionStepForm
from apps.marketplace.wizard_services import (
    publish_order_wizard, save_order_wizard_step,
)

from .factories import make_user


@override_settings(ZEMIPRO_PILOT_CITY_SLUG='ashdod')
class QuotaAndReplayTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.city = City.objects.create(
            slug='ashdod', name_ru='Ашдод', name_en='Ashdod', name_he='אשדוד',
        )
        cls.category = Category.objects.create(
            slug='046-general', name_ru='Ремонт', name_en='Repair',
            name_he='תיקונים',
        )
        cls.service = Subcategory.objects.create(
            category=cls.category, slug='046-service',
            name_ru='Покраска', work_mode='onsite',
        )
        cls.owner = make_user('046-owner')
        cls.other = make_user('046-other')
        cls.worker = make_user('046-worker')
        ClientProfile.objects.create(user=cls.owner, city=cls.city)
        worker_profile = WorkerProfile.objects.create(
            user=cls.worker, city=cls.city,
            display_name='Synthetic 046 worker',
            description='Synthetic worker available for repair requests.',
            pricing_details='Negotiable', spoken_languages=['ru'],
            is_published=True,
        )
        worker_profile.skills.add(cls.category)
        worker_profile.services.add(cls.service)

    def setUp(self):
        self.client.force_login(self.owner)

    def create(self, suffix='', *, key=None):
        return create_order(
            self.owner, self.category, self.city, '',
            'Synthetic quota request description with context ' + suffix,
            subcategory=self.service, submission_key=key,
        )

    def test_creation_budget_is_durable_and_replay_consumes_no_extra_units(self):
        key = uuid.uuid4()
        with patch.dict(ORDER_WRITE_LIMITS, {'create': (86400, 1)}):
            first = self.create('one', key=key)
            self.assertEqual(self.create('one', key=key).pk, first.pk)
            quota = OrderWriteQuota.objects.get(
                owner=self.owner, kind='create',
            )
            self.assertEqual(quota.used, 1)
            with self.assertRaises(OrderQuotaExceeded):
                self.create('different', key=uuid.uuid4())
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(OrderWriteQuota.objects.get(kind='create').used, 1)

    def test_legacy_post_reports_http_429_and_retry_after(self):
        with patch.dict(ORDER_WRITE_LIMITS, {'create': (86400, 1)}):
            url = reverse('marketplace:order_create')
            values = {
                'category': self.category.pk, 'subcategory': self.service.pk,
                'city': self.city.pk, 'customer_name': 'Synthetic',
                'description': 'A sufficiently long synthetic work description.',
                'price': 'Договорная',
            }
            self.assertEqual(self.client.post(url, values).status_code, 302)
            again = self.client.post(url, {
                **values, 'description': 'A different sufficiently long synthetic job.',
            })
            self.assertEqual(again.status_code, 429)
            self.assertGreater(int(again['Retry-After']), 0)
            self.assertIn('no-store', again['Cache-Control'])
        self.assertEqual(Order.objects.count(), 1)

    def test_failed_transaction_does_not_consume_budget(self):
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                consume_order_quota(self.owner, 'edit')
                raise RuntimeError('Synthetic rollback')
        self.assertFalse(OrderWriteQuota.objects.filter(kind='edit').exists())

    def test_wizard_step_replays_are_free_but_distinct_updates_have_a_limit(self):
        order = Order.objects.create(
            client=self.owner, category=self.category, subcategory=self.service,
            city=self.city, status=Order.Status.DRAFT,
            wizard_token=uuid.uuid4(), address='', description='',
            wizard_data={'steps': {
                '1': {'category_id': self.category.pk,
                      'subcategory_id': self.service.pk},
                '2': {'version_id': None, 'answers': {}},
                '3': {'city_id': self.city.pk, 'mode': 'onsite', 'area': ''},
                '4': {'preferred_date': '', 'urgency': 'normal'},
                '5': {'price_type': 'negotiable', 'amount_min': '', 'amount_max': ''},
            }},
        )
        with patch.dict(ORDER_WRITE_LIMITS, {'wizard': (3600, 1)}):
            first = DescriptionStepForm(data={'description': 'Synthetic first'})
            save_order_wizard_step(
                order_id=order.pk, actor=self.owner, step=6, form=first,
            )
            same = DescriptionStepForm(data={'description': 'Synthetic first'})
            save_order_wizard_step(
                order_id=order.pk, actor=self.owner, step=6, form=same,
            )
            changed = DescriptionStepForm(data={'description': 'Synthetic changed'})
            with self.assertRaises(OrderQuotaExceeded):
                save_order_wizard_step(
                    order_id=order.pk, actor=self.owner, step=6, form=changed,
                )
        order.refresh_from_db()
        self.assertEqual(order.wizard_data['steps']['6']['description'], 'Synthetic first')
        self.assertEqual(OrderWriteQuota.objects.get(kind='wizard').used, 1)

    def test_status_noop_is_free_and_independent_state_limiter(self):
        order = self.create()
        with patch.dict(ORDER_WRITE_LIMITS, {'state': (3600, 1)}):
            from apps.marketplace.order_lifecycle import transition_order_status
            transition_order_status(order, Order.Status.IN_DISCUSSION, actor=self.owner)
            transition_order_status(order, Order.Status.IN_DISCUSSION, actor=self.owner)
            with self.assertRaises(OrderQuotaExceeded):
                transition_order_status(order, Order.Status.PUBLISHED, actor=self.owner)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.IN_DISCUSSION)
        self.assertEqual(OrderStatusEvent.objects.filter(
            order=order, new_status=Order.Status.IN_DISCUSSION,
        ).count(), 1)

    def test_reply_budget_does_not_count_second_worker_in_same_order(self):
        other_order = self.create('second target')
        first = self.create('first target')
        # The same worker may reply to a distinct order, subject to daily limits.
        with patch.dict(ORDER_WRITE_LIMITS, {'response': (86400, 1)}):
            create_response(first, self.worker, 'Synthetic first reply')
            with self.assertRaises(OrderQuotaExceeded):
                create_response(other_order, self.worker, 'Synthetic second reply')
        self.assertEqual(Response.objects.count(), 1)
        self.assertEqual(OrderWriteQuota.objects.get(kind='response').used, 1)

    def test_blocked_user_cannot_manipulate_quota(self):
        self.owner.is_blocked = True
        self.owner.save(update_fields=['is_blocked'])
        with self.assertRaises(PermissionDenied):
            with transaction.atomic():
                consume_order_quota(self.owner, 'create')
        self.assertFalse(OrderWriteQuota.objects.exists())

    def test_duplicate_photo_upload_does_not_charge_again(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        setting = override_settings(ZEMIPRO_PRIVATE_MEDIA_ROOT=directory.name)
        setting.enable()
        self.addCleanup(setting.disable)
        order = Order.objects.create(
            client=self.owner, category=self.category, subcategory=self.service,
            city=self.city, status=Order.Status.DRAFT,
            address='', description='', wizard_token=uuid.uuid4(),
        )
        with patch.dict(ORDER_WRITE_LIMITS, {'photo': (86400, 1)}):
            for _ in range(2):
                from .test_stage04_details import test_image
                cleaned = validate_order_photo_batch([test_image(color=10)])
                with transaction.atomic():
                    locked = Order.objects.select_for_update().get(pk=order.pk)
                    store_photos_on_locked_order(
                        locked, actor=self.owner, cleaned=cleaned,
                        visibility='private',
                    )
            second = validate_order_photo_batch([test_image(color=170)])
            with self.assertRaises(OrderQuotaExceeded):
                with transaction.atomic():
                    locked = Order.objects.select_for_update().get(pk=order.pk)
                    store_photos_on_locked_order(
                        locked, actor=self.owner, cleaned=second,
                        visibility='private',
                    )
        self.assertEqual(OrderAttachment.objects.filter(order=order).count(), 1)
        self.assertEqual(OrderWriteQuota.objects.get(kind='photo').used, 1)


@override_settings(ZEMIPRO_PILOT_CITY_SLUG='ashdod')
class ConcurrentOrderMutationsTests(TransactionTestCase):
    def setUp(self):
        self.city = City.objects.create(slug='ashdod', name_ru='Ашдод')
        self.category = Category.objects.create(
            slug='concurrency-046', name_ru='Ремонт',
        )
        self.service = Subcategory.objects.create(
            category=self.category, slug='concurrency-046-service',
            name_ru='Ремонт', work_mode='onsite',
        )
        self.owner = make_user('concurrency-046-owner')
        self.worker_a = make_user('concurrency-046-worker-a')
        self.worker_b = make_user('concurrency-046-worker-b')
        for worker in (self.worker_a, self.worker_b):
            profile = WorkerProfile.objects.create(
                user=worker, city=self.city, is_published=True,
                display_name=worker.username,
                description='Synthetic worker for concurrency test.',
                spoken_languages=['ru'], pricing_details='Negotiable',
            )
            profile.skills.add(self.category)
            profile.services.add(self.service)

    def test_parallel_publish_writes_only_one_state_change(self):
        order = Order.objects.create(
            client=self.owner, category=self.category, subcategory=self.service,
            city=self.city, address='', description='',
            status=Order.Status.DRAFT, wizard_token=uuid.uuid4(),
            wizard_data={'steps': {
                '1': {'category_id': self.category.pk,
                      'subcategory_id': self.service.pk},
                '2': {'version_id': None, 'answers': {}},
                '3': {'city_id': self.city.pk, 'mode': 'onsite', 'area': ''},
                '4': {'preferred_date': '', 'urgency': 'normal'},
                '5': {'price_type': 'negotiable', 'amount_min': '', 'amount_max': ''},
                '6': {'description': 'Synthetic parallel publication test'},
                '7': {'display_name': 'Synthetic Owner', 'chat_only': True},
            }},
        )
        barrier = Barrier(2)

        def publish(_):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                _, created = publish_order_wizard(
                    order_id=order.pk, actor=self.owner,
                    confirmation_form=ConfirmStepForm(data={'confirm': 'on'}),
                )
                return created
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            changed = list(executor.map(publish, range(2)))
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PUBLISHED)
        self.assertCountEqual(changed, [False, True])
        self.assertEqual(OrderStatusEvent.objects.filter(
            order=order, new_status=Order.Status.PUBLISHED,
        ).count(), 1)

    def test_rejects_late_reply_while_selecting_worker(self):
        order = create_order(
            self.owner, self.category, self.city, '',
            'Parallel worker assignment synthetic order.', subcategory=self.service,
        )
        initial = Response.objects.create(order=order, worker=self.worker_a)
        barrier = Barrier(2)

        def job(kind):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                if kind == 'select':
                    return ('select', accept_response(initial, actor=self.owner).worker_id)
                try:
                    create_response(order, self.worker_b, 'Parallel synthetic reply')
                    return ('reply', 'created')
                except ValueError:
                    return ('reply', 'rejected')
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(job, ['select', 'reply']))
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.ASSIGNED)
        self.assertEqual(order.worker_id, self.worker_a.pk)
        if Response.objects.filter(order=order, worker=self.worker_b).exists():
            self.assertEqual(Response.objects.get(
                order=order, worker=self.worker_b,
            ).status, Response.Status.REJECTED)
        self.assertIn(('select', self.worker_a.pk), results)
