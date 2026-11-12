"""Stage 03.7: remove unused Telegram ID only when no historical IDs exist.

Fail closed in a single atomic PostgreSQL migration: never discard non-null
legacy identifiers. Existing migration history is intentionally preserved.
"""
from django.db import migrations


def require_empty_legacy_identifier(apps, schema_editor):
    if schema_editor.connection.vendor != 'postgresql':
        raise RuntimeError('Stage 03.7 supports PostgreSQL only.')
    schema_editor.execute('LOCK TABLE "accounts_user" IN ACCESS EXCLUSIVE MODE')
    historical_user = apps.get_model('accounts', 'User')
    if historical_user.objects.using(schema_editor.connection.alias).filter(
        telegram_id__isnull=False,
    ).exists():
        raise RuntimeError(
            'Stage 03.7 aborted: existing legacy Telegram identifiers require '
            'owner-approved data review and backup before schema removal.'
        )


class Migration(migrations.Migration):
    dependencies = [('accounts', '0009_worker_portfolio')]
    operations = [
        migrations.RunPython(
            require_empty_legacy_identifier,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.RemoveField(model_name='user', name='telegram_id'),
    ]
