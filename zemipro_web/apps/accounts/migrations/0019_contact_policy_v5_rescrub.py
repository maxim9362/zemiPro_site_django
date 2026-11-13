"""ZP-05-006/007 forward-only re-scrub of derived public search fields.

Do not alter 0015–0018 or original user-authored texts / identity relations.
"""
from django.db import migrations

from apps.accounts.contact_policy_v5 import (
    searchable_public_name,
    searchable_public_text,
)


def rescrub_public_search(apps, schema_editor):
    model = apps.get_model('accounts', 'WorkerProfile')
    alias = schema_editor.connection.alias
    batch = []
    records = model.objects.using(alias).only(
        'pk', 'display_name', 'description',
    ).order_by('pk')
    for row in records.iterator(chunk_size=400):
        row.searchable_display_name = searchable_public_name(row.display_name)
        row.searchable_description = searchable_public_text(row.description)
        batch.append(row)
        if len(batch) == 400:
            model.objects.using(alias).bulk_update(
                batch, ['searchable_display_name', 'searchable_description'],
                batch_size=400,
            )
            batch.clear()
    if batch:
        model.objects.using(alias).bulk_update(
            batch, ['searchable_display_name', 'searchable_description'],
            batch_size=400,
        )


class Migration(migrations.Migration):
    dependencies = [('accounts', '0018_strict_contact_rescrub')]
    operations = [
        migrations.RunPython(rescrub_public_search, migrations.RunPython.noop),
    ]
