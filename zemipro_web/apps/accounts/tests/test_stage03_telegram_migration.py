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
        current = ('accounts', '0010_remove_legacy_telegram_id')
        MigrationExecutor(connection).migrate([previous])
        synthetic_pk = None
        try:
            user = get_user_model().objects.create_user(
                username='s037-legacy-fixture',
                password='Synthetic-Pass-9362',
            )
            synthetic_pk = user.pk
            sample_id = 987654321012
            with connection.cursor() as cursor:
                cursor.execute(
                    'UPDATE accounts_user SET telegram_id = %s WHERE id = %s',
                    [sample_id, synthetic_pk],
                )
            with self.assertRaisesRegex(RuntimeError, 'existing legacy Telegram identifiers'):
                MigrationExecutor(connection).migrate([current])
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
            MigrationExecutor(connection).migrate([current])
            with connection.cursor() as cursor:
                columns = connection.introspection.get_table_description(
                    cursor, 'accounts_user',
                )
            self.assertNotIn('telegram_id', {column.name for column in columns})
            self.assertTrue(get_user_model().objects.filter(
                pk=synthetic_pk,
            ).exists())
        finally:
            # Restore the latest schema if a preceding assertion failed.
            with connection.cursor() as cursor:
                columns = connection.introspection.get_table_description(
                    cursor, 'accounts_user',
                )
                if 'telegram_id' in {column.name for column in columns}:
                    if synthetic_pk is not None:
                        cursor.execute(
                            'UPDATE accounts_user SET telegram_id = NULL WHERE id = %s',
                            [synthetic_pk],
                        )
                    MigrationExecutor(connection).migrate([current])
