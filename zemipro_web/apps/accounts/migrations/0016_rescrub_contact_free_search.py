"""Stage 05 ZP-05-003: re-scrub pre-existing public search copies.

The frozen contact_policy_v2 is also used by HTML masking and owner services.
Do not modify the policy module in-place in later stages: create v3 instead.
No raw content is logged or sent externally; live DB is never touched by CI.
"""
from django.db import migrations

from apps.accounts.contact_policy_v2 import searchable_public_text


def rescrub_public_search(apps, schema_editor):
    profile_model = apps.get_model('accounts', 'WorkerProfile')
    alias = schema_editor.connection.alias
    batch = []
    queryset = profile_model.objects.using(alias).only(
        'id', 'display_name', 'description',
    ).order_by('pk')
    for profile in queryset.iterator(chunk_size=400):
        profile.searchable_display_name = searchable_public_text(profile.display_name)
        profile.searchable_description = searchable_public_text(profile.description)
        batch.append(profile)
        if len(batch) >= 400:
            profile_model.objects.using(alias).bulk_update(
                batch, ['searchable_display_name', 'searchable_description'],
                batch_size=400,
            )
            batch.clear()
    if batch:
        profile_model.objects.using(alias).bulk_update(
            batch, ['searchable_display_name', 'searchable_description'],
            batch_size=400,
        )


class Migration(migrations.Migration):
    dependencies = [('accounts', '0015_contact_free_search')]

    operations = [
        migrations.RunPython(rescrub_public_search, migrations.RunPython.noop),
    ]
