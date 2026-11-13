"""Prove Stage 03.7 migration aborts on a populated legacy ID.

Only the isolated Django test database is migrated. No production data is
accessed, exported, modified or even queried by this test.
"""
from django.contrib.auth import get_user_model
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class TelegramIdentifierRemovalSafetyTests(TransactionTestCase):
    def test_populated_legacy_column_blocks_schema_change(self):
        previous = ('accounts', '0009_worker_portfolio')
        telegram_removal = ('accounts', '0010_remove_legacy_telegram_id')
        latest = ('accounts', '0011_user_email_verification_required')
        # Capture every leaf, including later migrations added in new stages.
        # Historical test must not leave the test DB at the old 0011 schema.
        executor = MigrationExecutor(connection)
        current_leaves = executor.loader.graph.leaf_nodes()
        executor.migrate([previous])
        historical_user = executor.loader.project_state([previous]).apps.get_model(
            'accounts', 'User',
        )
        synthetic_pk = None
        try:
            user = historical_user.objects.create(
                username='s037-legacy-fixture',
                password='!Synthetic-unusable-hash',
            )
            synthetic_pk = user.pk
            sample_id = 987654321012
            with connection.cursor() as cursor:
                cursor.execute(
                    'UPDATE accounts_user SET telegram_id = %s WHERE id = %s',
                    [sample_id, synthetic_pk],
                )
            with self.assertRaisesRegex(RuntimeError, 'existing legacy Telegram identifiers'):
                MigrationExecutor(connection).migrate([telegram_removal])
            with connection.cursor() as cursor:
                cursor.execute(
                    'SELECT telegram_id FROM accounts_user WHERE id = %s',
                    [synthetic_pk],
                )
                self.assertEqual(cursor.fetchone()[0], sample_id)
                # Cleanup is for this one synthetic fixture in the test DB.
                cursor.execute(
                    'UPDATE accounts_user SET telegram_id = NULL WHERE id = %s',
                    [synthetic_pk],
                )
            MigrationExecutor(connection).migrate([latest])
            with connection.cursor() as cursor:
                columns = connection.introspection.get_table_description(
                    cursor, 'accounts_user',
                )
            self.assertNotIn('telegram_id', {column.name for column in columns})
            self.assertTrue(get_user_model().objects.filter(
                pk=synthetic_pk,
            ).exists())
        finally:
            # The explicit historical check stops at 0011, but later schema
            # additions must be restored before ANY other TransactionTestCase.
            with connection.cursor() as cursor:
                columns = connection.introspection.get_table_description(
                    cursor, 'accounts_user',
                )
                if ('telegram_id' in {column.name for column in columns}
                        and synthetic_pk is not None):
                    cursor.execute(
                        'UPDATE accounts_user SET telegram_id = NULL WHERE id = %s',
                        [synthetic_pk],
                    )
            MigrationExecutor(connection).migrate(current_leaves)
