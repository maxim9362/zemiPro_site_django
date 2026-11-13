"""Persist fail-closed public snapshots without altering private source text."""
from django.db import migrations, models

from apps.accounts.public_snapshot_v1 import (
    POLICY_VERSION,
    build_caption_snapshot,
    build_fail_closed_profile_snapshot,
)


def rebuild_snapshots(apps, schema_editor):
    profile_model = apps.get_model('accounts', 'WorkerProfile')
    photo_model = apps.get_model('accounts', 'WorkerPortfolioPhoto')
    alias = schema_editor.connection.alias

    batch = []
    rows = profile_model.objects.using(alias).select_related('user').order_by('pk')
    for row in rows.iterator(chunk_size=400):
        snapshot = build_fail_closed_profile_snapshot(
            display_name=row.display_name,
            description=row.description,
            pricing_details=row.pricing_details,
            working_hours=row.working_hours,
            private_values=(row.contact, row.user.email, row.user.phone),
        )
        row.public_display_name_snapshot = snapshot['display_name'][:120]
        row.public_description_snapshot = snapshot['description']
        row.public_pricing_details_snapshot = snapshot['pricing_details'][:240]
        row.public_working_hours_snapshot = snapshot['working_hours'][:200]
        row.searchable_display_name = ' '.join(
            row.public_display_name_snapshot.split(),
        )[:120]
        row.searchable_description = ''
        row.public_content_safe = True
        row.public_content_policy_version = POLICY_VERSION
        batch.append(row)
        if len(batch) == 400:
            profile_model.objects.using(alias).bulk_update(
                batch, _PROFILE_DERIVED_FIELDS, batch_size=400,
            )
            batch.clear()
    if batch:
        profile_model.objects.using(alias).bulk_update(
            batch, _PROFILE_DERIVED_FIELDS, batch_size=400,
        )

    batch = []
    for row in photo_model.objects.using(alias).order_by('pk').iterator(chunk_size=400):
        snapshot = build_caption_snapshot(row.caption)
        row.public_caption_snapshot = snapshot or ''
        row.public_content_safe = True
        row.public_content_policy_version = POLICY_VERSION
        batch.append(row)
        if len(batch) == 400:
            photo_model.objects.using(alias).bulk_update(
                batch, _PHOTO_DERIVED_FIELDS, batch_size=400,
            )
            batch.clear()
    if batch:
        photo_model.objects.using(alias).bulk_update(
            batch, _PHOTO_DERIVED_FIELDS, batch_size=400,
        )


_PROFILE_DERIVED_FIELDS = [
    'public_display_name_snapshot', 'public_description_snapshot',
    'public_pricing_details_snapshot', 'public_working_hours_snapshot',
    'searchable_display_name', 'searchable_description',
    'public_content_safe', 'public_content_policy_version',
]
_PHOTO_DERIVED_FIELDS = [
    'public_caption_snapshot', 'public_content_safe',
    'public_content_policy_version',
]


class Migration(migrations.Migration):
    dependencies = [('accounts', '0020_fail_closed_public_text')]

    operations = [
        migrations.AddField(
            model_name='workerprofile', name='public_content_policy_version',
            field=models.PositiveSmallIntegerField(db_index=True, default=0, editable=False),
        ),
        migrations.AddField(
            model_name='workerprofile', name='public_display_name_snapshot',
            field=models.CharField(blank=True, default='', editable=False, max_length=120),
        ),
        migrations.AddField(
            model_name='workerprofile', name='public_description_snapshot',
            field=models.TextField(blank=True, default='', editable=False),
        ),
        migrations.AddField(
            model_name='workerprofile', name='public_pricing_details_snapshot',
            field=models.CharField(blank=True, default='', editable=False, max_length=240),
        ),
        migrations.AddField(
            model_name='workerprofile', name='public_working_hours_snapshot',
            field=models.CharField(blank=True, default='', editable=False, max_length=200),
        ),
        migrations.AddField(
            model_name='workerportfoliophoto', name='public_caption_snapshot',
            field=models.CharField(blank=True, default='', editable=False, max_length=300),
        ),
        migrations.AddField(
            model_name='workerportfoliophoto', name='public_content_safe',
            field=models.BooleanField(default=False, editable=False),
        ),
        migrations.AddField(
            model_name='workerportfoliophoto', name='public_content_policy_version',
            field=models.PositiveSmallIntegerField(default=0, editable=False),
        ),
        migrations.RunPython(rebuild_snapshots, migrations.RunPython.noop),
        migrations.AddIndex(
            model_name='workerprofile',
            index=models.Index(
                fields=[
                    'is_published', 'public_content_safe',
                    'public_content_policy_version', 'city',
                ],
                name='worker_safe_public_idx',
            ),
        ),
    ]
