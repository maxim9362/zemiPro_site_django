"""PostgreSQL rehearsal of the forward-only public snapshot migration."""
from django.contrib.auth import get_user_model
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

from apps.accounts.models import WorkerProfile
from apps.locations.models import City
from apps.marketplace.models import Category, Order


class PublicSnapshotMigrationTests(TransactionTestCase):
    def test_0020_to_0021_preserves_raw_relations_and_hides_unsafe_projection(self):
        previous = ('accounts', '0020_fail_closed_public_text')
        latest = ('accounts', '0021_public_content_snapshots')
        current_leaves = MigrationExecutor(connection).loader.graph.leaf_nodes()

        user = get_user_model().objects.create_user(
            username='snapshot-migration-user',
            email='private-identity@example.test',
        )
        city = City.objects.create(
            slug='snapshot-migration-ashdod', name_ru='Ашдод',
            name_en='Ashdod', name_he='אשדוד',
        )
        category = Category.objects.create(
            slug='snapshot-migration-category', name_ru='Ремонт',
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
            old_profile = old_apps.get_model('accounts', 'WorkerProfile')
            old_profile.objects.filter(pk=profile.pk).update(
                display_name='john-at-example-dot-com',
                description='t_e_l_e_g_r_a_m contacthandle',
                searchable_display_name='john-at-example-dot-com',
                searchable_description='contacthandle',
                public_content_safe=True,
            )

            MigrationExecutor(connection).migrate([latest])
            new_apps = MigrationExecutor(connection).loader.project_state(
                [latest],
            ).apps
            migrated = new_apps.get_model('accounts', 'WorkerProfile').objects.get(
                pk=profile.pk,
            )
            order.refresh_from_db()
            self.assertEqual(
                (
                    migrated.pk, migrated.user_id, migrated.city_id, order.pk,
                    order.client_id, order.address,
                ),
                originals,
            )
            self.assertEqual(migrated.display_name, 'john-at-example-dot-com')
            self.assertEqual(
                migrated.description, 't_e_l_e_g_r_a_m contacthandle',
            )
            self.assertEqual(migrated.searchable_display_name, '')
            self.assertEqual(migrated.searchable_description, '')
            self.assertEqual(migrated.public_display_name_snapshot, '')
            self.assertTrue(migrated.public_content_safe)
            self.assertEqual(migrated.public_content_policy_version, 1)
        finally:
            MigrationExecutor(connection).migrate(current_leaves)
