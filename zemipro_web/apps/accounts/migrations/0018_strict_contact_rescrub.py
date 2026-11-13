"""Forward migration for ZP-05-005: replace old public search copies.

No raw profile value, FK, publication status or order is modified.
Do not edit 0015, 0016 or 0017; contact_policy_v4 remains frozen.
"""
from django.db import migrations

from apps.accounts.contact_policy_v4 import (
    searchable_public_name,
    searchable_public_text,
)


def rescrub_public_search(apps, schema_editor):
    profile = apps.get_model('accounts', 'WorkerProfile')
    alias = schema_editor.connection.alias
    batch = []
    qs = profile.objects.using(alias).only(
        'pk', 'display_name', 'description',
    ).order_by('pk')
    for row in qs.iterator(chunk_size=400):
        row.searchable_display_name = searchable_public_name(row.display_name)
        row.searchable_description = searchable_public_text(row.description)
        batch.append(row)
        if len(batch) == 400:
            profile.objects.using(alias).bulk_update(
                batch, ['searchable_display_name', 'searchable_description'],
                batch_size=400,
            )
            batch.clear()
    if batch:
        profile.objects.using(alias).bulk_update(
            batch, ['searchable_display_name', 'searchable_description'],
            batch_size=400,
        )


class Migration(migrations.Migration):
    dependencies = [('accounts', '0017_unicode_contact_scrub')]

    operations = [
        migrations.RunPython(rescrub_public_search, migrations.RunPython.noop),
    ]
