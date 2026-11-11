"""Stage 01.2: enforce existing order/response status choices at the database layer.

Never coerce, rewrite or delete unknown historical values. Block the migration
until the owner reviews any unexpected data in an isolated database.
"""
from django.db import migrations, models


ORDER_STATUSES = ('new', 'in_progress', 'completed', 'cancelled')
RESPONSE_STATUSES = ('pending', 'accepted', 'rejected', 'cancelled')


def ensure_valid_marketplace_statuses(apps, schema_editor):
    alias = schema_editor.connection.alias
    for model_name, allowed in (
        ('Order', ORDER_STATUSES),
        ('Response', RESPONSE_STATUSES),
    ):
        model = apps.get_model('marketplace', model_name)
        unknown = model.objects.using(alias).exclude(status__in=allowed).count()
        if unknown:
            raise RuntimeError(
                f'{model_name}: {unknown} unrecognized status value(s); '
                'migration stopped without modifying data. '
                'Investigate in a protected synthetic/restored database.'
            )


class Migration(migrations.Migration):
    dependencies = [
        ('marketplace', '0003_require_order_owner'),
    ]

    operations = [
        migrations.RunPython(
            ensure_valid_marketplace_statuses,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.AddConstraint(
            model_name='order',
            constraint=models.CheckConstraint(
                condition=models.Q(status__in=ORDER_STATUSES),
                name='order_status_allowed',
            ),
        ),
        migrations.AddConstraint(
            model_name='response',
            constraint=models.CheckConstraint(
                condition=models.Q(status__in=RESPONSE_STATUSES),
                name='response_status_allowed',
            ),
        ),
    ]
