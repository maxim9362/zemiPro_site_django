"""Real PostgreSQL rehearsal of accounts 0019 -> 0020."""
from django.contrib.auth import get_user_model
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

from apps.accounts.models import WorkerProfile
from apps.locations.models import City
from apps.marketplace.models import Category, Order


class ContactPolicyV6MigrationTests(TransactionTestCase):
    def test_forward_migration_preserves_raw_relations_and_closes_search(self):
        previous = ('accounts', '0019_contact_policy_v5_rescrub')
        latest = ('accounts', '0020_fail_closed_public_text')
        executor = MigrationExecutor(connection)
        current_leaves = executor.loader.graph.leaf_nodes()

        user = get_user_model().objects.create_user(
            username='v6-migration-user', password='Synthetic-pass-123!',
        )
        city = City.objects.create(
            slug='v6-migration-ashdod', name_ru='Ашдод',
            name_en='Ashdod', name_he='אשדוד',
        )
        category = Category.objects.create(
            slug='v6-migration-category', name_ru='Ремонт',
        )
        profile = WorkerProfile.objects.create(
            user=user, city=city, display_name='Safe original name',
            description='Safe original synthetic description.',
            pricing_details='Quotation after inspection',
            working_hours='09:00-17:00', is_published=True,
        )
        order = Order.objects.create(
            client=user, category=category, city=city,
            address='PRIVATE SYNTHETIC ADDRESS',
            description='Synthetic order preserved across migration',
        )
        originals = (
            profile.pk, profile.user_id, profile.city_id, order.pk,
            order.client_id, order.address,
        )
        try:
            MigrationExecutor(connection).migrate([previous])
            old_apps = MigrationExecutor(connection).loader.project_state(
                [previous],
            ).apps
            OldProfile = old_apps.get_model('accounts', 'WorkerProfile')
            OldProfile.objects.filter(pk=profile.pk).update(
                display_name='Service 050x7654321',
                description='john собака example точка com',
                searchable_display_name='Service 050x7654321',
                searchable_description='john собака example точка com',
            )

            MigrationExecutor(connection).migrate([latest])
            new_apps = MigrationExecutor(connection).loader.project_state(
                [latest],
            ).apps
            NewProfile = new_apps.get_model('accounts', 'WorkerProfile')
            migrated = NewProfile.objects.get(pk=profile.pk)
            order.refresh_from_db()
            self.assertEqual(
                (
                    migrated.pk, migrated.user_id, migrated.city_id, order.pk,
                    order.client_id, order.address,
                ),
                originals,
            )
            self.assertEqual(migrated.display_name, 'Service 050x7654321')
            self.assertEqual(
                migrated.description, 'john собака example точка com',
            )
            self.assertEqual(migrated.searchable_display_name, '')
            self.assertEqual(migrated.searchable_description, '')
            self.assertFalse(migrated.public_content_safe)
        finally:
            MigrationExecutor(connection).migrate(current_leaves)
