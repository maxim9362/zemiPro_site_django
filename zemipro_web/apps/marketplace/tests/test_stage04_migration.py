"""Stage 04.1: historical Order migration in the isolated PostgreSQL test DB.

No real users, archived production database, or external services are touched.
"""
from django.contrib.auth import get_user_model
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class OrderLegacyStatusMigrationTests(TransactionTestCase):
    def test_legacy_status_and_original_order_fields_survive_migration(self):
        previous = ('marketplace', '0007_protect_worker_history')
        latest = ('marketplace', '0008_order_lifecycle')
        # Historical assertions intentionally stop at 0008. Restore ALL
        # current graph leaves afterwards (including accounts 0012+), rather
        # than only the marketplace leaf; migrations can introduce new fields
        # in unrelated apps which the next ORM tests expect to exist.
        current_leaves = MigrationExecutor(connection).loader.graph.leaf_nodes()
        MigrationExecutor(connection).migrate([previous])
        state = MigrationExecutor(connection).loader.project_state([previous]).apps
        Category = state.get_model('marketplace', 'Category')
        City = state.get_model('locations', 'City')
        Order = state.get_model('marketplace', 'Order')
        # Marketplace 0007 historically references pre-Stage-03 User schema.
        # The physical accounts table remains at the current migration head.
        user = get_user_model().objects.create_user(username='synthetic-stage04-history')
        category = Category.objects.create(slug='synthetic-historical-service', name_ru='Услуга')
        city = City.objects.create(slug='synthetic-historical-ashdod', name_ru='Ашдод')
        old = Order.objects.create(
            client_id=user.pk, category_id=category.pk, city_id=city.pk,
            address='Private synthetic archive address',
            description='A synthetic legacy description',
            customer_phone='0500000000',
            price='899–1099 ₪',
            status='new',
        )
        ongoing = Order.objects.create(
            client_id=user.pk, category_id=category.pk, city_id=city.pk,
            address='Second synthetic address', description='Other historical order',
            price='Договорная', status='in_progress',
        )
        try:
            MigrationExecutor(connection).migrate([latest])
            new_state = MigrationExecutor(connection).loader.project_state([latest]).apps
            NewOrder = new_state.get_model('marketplace', 'Order')
            Event = new_state.get_model('marketplace', 'OrderStatusEvent')
            saved = NewOrder.objects.get(pk=old.pk)
            self.assertEqual(saved.status, 'published')
            self.assertEqual(saved.legacy_status, 'new')
            self.assertEqual(saved.price, '899–1099 ₪')
            self.assertEqual(saved.address, 'Private synthetic archive address')
            self.assertEqual(saved.customer_phone, '0500000000')
            preserved = NewOrder.objects.get(pk=ongoing.pk)
            self.assertEqual(preserved.status, 'in_progress')
            self.assertIsNone(preserved.legacy_status)
            self.assertEqual(preserved.price, 'Договорная')
            self.assertEqual(list(Event.objects.filter(
                order_id=old.pk,
            ).values_list('previous_status', 'new_status', 'reason')), [
                ('new', 'published', 'legacy_migration'),
            ])
            self.assertFalse(Event.objects.filter(order_id=ongoing.pk).exists())
            with self.assertRaisesRegex(RuntimeError, 'downgrade refused'):
                MigrationExecutor(connection).migrate([previous])
            self.assertEqual(NewOrder.objects.get(pk=old.pk).status, 'published')
        finally:
            # The attempted reverse is PostgreSQL-transactional. Restore the
            # whole current graph so later concurrency tests use a complete DB.
            MigrationExecutor(connection).migrate(current_leaves)
