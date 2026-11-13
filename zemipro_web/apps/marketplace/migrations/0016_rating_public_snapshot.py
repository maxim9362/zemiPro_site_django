"""Backfill public review snapshots; preserve every private review verbatim."""
from django.db import migrations, models

from apps.accounts.public_snapshot_v1 import POLICY_VERSION, build_caption_snapshot


def rebuild_review_snapshots(apps, schema_editor):
    rating_model = apps.get_model('marketplace', 'Rating')
    alias = schema_editor.connection.alias
    batch = []
    rows = rating_model.objects.using(alias).order_by('pk')
    for row in rows.iterator(chunk_size=400):
        snapshot = build_caption_snapshot(row.review_text)
        row.public_review_text_snapshot = snapshot or ''
        row.public_content_safe = True
        row.public_content_policy_version = POLICY_VERSION
        batch.append(row)
        if len(batch) == 400:
            rating_model.objects.using(alias).bulk_update(
                batch, _DERIVED_FIELDS, batch_size=400,
            )
            batch.clear()
    if batch:
        rating_model.objects.using(alias).bulk_update(
            batch, _DERIVED_FIELDS, batch_size=400,
        )


_DERIVED_FIELDS = [
    'public_review_text_snapshot', 'public_content_safe',
    'public_content_policy_version',
]


class Migration(migrations.Migration):
    dependencies = [
        ('accounts', '0021_public_content_snapshots'),
        ('marketplace', '0015_order_invitation'),
    ]

    operations = [
        migrations.AddField(
            model_name='rating', name='public_review_text_snapshot',
            field=models.TextField(blank=True, default='', editable=False),
        ),
        migrations.AddField(
            model_name='rating', name='public_content_safe',
            field=models.BooleanField(default=False, editable=False),
        ),
        migrations.AddField(
            model_name='rating', name='public_content_policy_version',
            field=models.PositiveSmallIntegerField(default=0, editable=False),
        ),
        migrations.RunPython(rebuild_review_snapshots, migrations.RunPython.noop),
    ]
