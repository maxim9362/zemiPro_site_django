"""ZP-05-004: forward-only repair of contact-free public search copies.

Preserves raw worker fields and all foreign keys; never logs a user's text.
"""
from django.db import migrations

from apps.accounts.contact_policy_v3 import (
    searchable_public_name,
    searchable_public_text,
)


def rescrub_public_search(apps, schema_editor):
    model = apps.get_model('accounts', 'WorkerProfile')
    alias = schema_editor.connection.alias
    batch = []
    qs = model.objects.using(alias).only(
        'pk', 'display_name', 'description',
    ).order_by('pk')
    for item in qs.iterator(chunk_size=400):
        item.searchable_display_name = searchable_public_name(item.display_name)
        item.searchable_description = searchable_public_text(item.description)
        batch.append(item)
        if len(batch) >= 400:
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
    dependencies = [('accounts', '0016_rescrub_contact_free_search')]
    operations = [
        migrations.RunPython(rescrub_public_search, migrations.RunPython.noop),
    ]
