"""Stage 01.2: schema invariants must be enforced by PostgreSQL, not forms."""
from django.db import IntegrityError, transaction
from django.db.migrations.loader import MigrationLoader
from django.db.models.deletion import ProtectedError
from django.test import SimpleTestCase, TestCase

from apps.accounts.models import User
from apps.locations.models import City
from apps.marketplace.models import Category, Order, Response, Subcategory
from apps.moderation.models import Complaint


class MigrationGraphTests(SimpleTestCase):
    def test_stage01_migrations_have_no_conflicting_leaves(self):
        loader = MigrationLoader(None)
        self.assertEqual(loader.detect_conflicts(), {})
        for app_label, migration_name in (
            ('accounts', '0002_initial'),
            ('marketplace', '0004_status_constraints'),
            ('locations', '0001_initial'),
            ('moderation', '0002_status_constraint'),
            ('notifications', '0001_initial'),
            ('analytics', '0001_initial'),
        ):
            with self.subTest(app=app_label):
                self.assertIn(
                    (app_label, migration_name), loader.disk_migrations
                )


class DatabaseSchemaConstraintsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username='schema-owner')
        cls.worker = User.objects.create_user(username='schema-worker')
        cls.category = Category.objects.create(
            slug='schema-plumbing', name_ru='Сантехника'
        )
        cls.city = City.objects.create(
            slug='schema-ashdod', name_ru='Ашдод'
        )
        cls.order = Order.objects.create(
            client=cls.owner,
            category=cls.category,
            city=cls.city,
            address='Synthetic test location',
            description='Synthetic schema constraint test',
        )

    def test_order_status_unknown_value_rejected_by_database(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Order.objects.filter(pk=self.order.pk).update(status='unknown')

    def test_response_status_unknown_value_rejected_by_database(self):
        response = Response.objects.create(
            order=self.order, worker=self.worker,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Response.objects.filter(pk=response.pk).update(status='unknown')

    def test_complaint_status_unknown_value_rejected_by_database(self):
        complaint = Complaint.objects.create(
            reporter=self.owner,
            reason=Complaint.Reason.SPAM,
            message='Synthetic complaint, no personal data',
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Complaint.objects.filter(pk=complaint.pk).update(status='unknown')

    def test_all_declared_status_values_are_accepted(self):
        for status in Order.Status.values:
            Order.objects.filter(pk=self.order.pk).update(status=status)
        response = Response.objects.create(
            order=self.order, worker=self.worker,
        )
        for status in Response.Status.values:
            Response.objects.filter(pk=response.pk).update(status=status)
        complaint = Complaint.objects.create(
            reporter=self.owner,
            reason=Complaint.Reason.SPAM,
            message='Synthetic complaint',
        )
        for status in Complaint.Status.values:
            Complaint.objects.filter(pk=complaint.pk).update(status=status)

    def test_owner_delete_is_protected_by_existing_order(self):
        with self.assertRaises(ProtectedError):
            self.owner.delete()
        self.assertTrue(Order.objects.filter(pk=self.order.pk).exists())

    def test_response_unique_order_worker(self):
        Response.objects.create(order=self.order, worker=self.worker)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Response.objects.create(order=self.order, worker=self.worker)

    def test_subcategory_slug_unique_within_category_only(self):
        Subcategory.objects.create(
            category=self.category, slug='repair', name_ru='Ремонт'
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Subcategory.objects.create(
                    category=self.category, slug='repair', name_ru='Другое'
                )
        other = Category.objects.create(
            slug='schema-other', name_ru='Другая категория'
        )
        Subcategory.objects.create(
            category=other, slug='repair', name_ru='Ремонт'
        )
