"""Stage 01.2: ensure complaint status is one of the existing model choices."""
from django.db import migrations, models


COMPLAINT_STATUSES = ('pending', 'resolved', 'dismissed')


def ensure_valid_complaint_statuses(apps, schema_editor):
    alias = schema_editor.connection.alias
    complaint = apps.get_model('moderation', 'Complaint')
    unknown = complaint.objects.using(alias).exclude(
        status__in=COMPLAINT_STATUSES
    ).count()
    if unknown:
        raise RuntimeError(
            f'Complaint: {unknown} unrecognized status value(s); '
            'migration stopped without modifying data. '
            'Investigate in a protected synthetic/restored database.'
        )


class Migration(migrations.Migration):
    dependencies = [
        ('moderation', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(
            ensure_valid_complaint_statuses,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.AddConstraint(
            model_name='complaint',
            constraint=models.CheckConstraint(
                condition=models.Q(status__in=COMPLAINT_STATUSES),
                name='complaint_status_allowed',
            ),
        ),
    ]
