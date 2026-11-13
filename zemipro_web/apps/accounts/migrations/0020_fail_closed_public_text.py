"""Fail-closed Stage 05 public text/search projections.

Raw profile text, publication status, identity relations and order data are
preserved.  Only derived search data and the derived public safety gate are
updated.  Historical migrations and policies remain immutable.
"""
from django.db import migrations, models

from apps.accounts.contact_policy_v6 import (
    profile_public_content_is_safe,
    searchable_public_name,
)


def rebuild_public_projections(apps, schema_editor):
    profile = apps.get_model('accounts', 'WorkerProfile')
    alias = schema_editor.connection.alias
    batch = []
    records = profile.objects.using(alias).only(
        'pk', 'display_name', 'description', 'pricing_details', 'working_hours',
    ).order_by('pk')
    for row in records.iterator(chunk_size=400):
        row.searchable_display_name = searchable_public_name(row.display_name)
        # Arbitrary descriptions are intentionally not keyword-indexed. Search
        # remains available through safe names and curated category/service data.
        row.searchable_description = ''
        row.public_content_safe = profile_public_content_is_safe(
            display_name=row.display_name,
            description=row.description,
            pricing_details=row.pricing_details,
            working_hours=row.working_hours,
        )
        batch.append(row)
        if len(batch) == 400:
            profile.objects.using(alias).bulk_update(
                batch,
                [
                    'searchable_display_name', 'searchable_description',
                    'public_content_safe',
                ],
                batch_size=400,
            )
            batch.clear()
    if batch:
        profile.objects.using(alias).bulk_update(
            batch,
            [
                'searchable_display_name', 'searchable_description',
                'public_content_safe',
            ],
            batch_size=400,
        )


class Migration(migrations.Migration):
    dependencies = [('accounts', '0019_contact_policy_v5_rescrub')]

    operations = [
        migrations.AddField(
            model_name='workerprofile',
            name='public_content_safe',
            field=models.BooleanField(
                db_index=True, default=False, editable=False,
                verbose_name='Публичный текст прошёл защитную проверку',
            ),
        ),
        migrations.RunPython(
            rebuild_public_projections,
            migrations.RunPython.noop,
        ),
    ]
