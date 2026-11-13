"""Stage 05 reviewer findings: backfill only sanitized PUBLIC keyword fields.

No user/contact data logged, no publication status changed and no production
migration is run by creating this file; CI applies it to an isolated database.
"""
import re

from django.db import migrations, models

EMAIL = re.compile(r'(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?!\w)')
PHONE = re.compile(r'(?<!\w)(?:\+?\d[\d \-().]{6,}\d)(?!\w)')


def _safe_text(value):
    text = EMAIL.sub(' ', value or '')

    def strip_number(match):
        return ' ' if sum(ch.isdigit() for ch in match.group()) >= 8 else match.group()

    return ' '.join(PHONE.sub(strip_number, text).split())


def backfill(apps, schema_editor):
    model = apps.get_model('accounts', 'WorkerProfile')
    alias = schema_editor.connection.alias
    batch = []
    qs = model.objects.using(alias).only(
        'pk', 'display_name', 'description',
    ).order_by('pk')
    for profile in qs.iterator(chunk_size=400):
        profile.searchable_display_name = _safe_text(profile.display_name)
        profile.searchable_description = _safe_text(profile.description)
        batch.append(profile)
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
    dependencies = [
        ('accounts', '0014_private_view_history'),
    ]

    operations = [
        migrations.AddField(
            model_name='workerprofile',
            name='searchable_display_name',
            field=models.CharField(
                max_length=120, blank=True, default='', editable=False,
            ),
        ),
        migrations.AddField(
            model_name='workerprofile',
            name='searchable_description',
            field=models.TextField(
                blank=True, default='', editable=False,
            ),
        ),
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
