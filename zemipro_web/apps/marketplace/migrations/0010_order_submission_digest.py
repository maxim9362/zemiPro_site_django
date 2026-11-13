"""04.3: store a keyed, non-reversible legacy submit digest for safe POST replay."""
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('marketplace', '0009_order_wizard_drafts')]

    operations = [
        migrations.AddField(
            model_name='order',
            name='submission_digest',
            field=models.CharField(
                max_length=64, blank=True, default='', db_index=True,
                editable=False, verbose_name='Защищённый отпечаток подачи заявки',
            ),
        ),
    ]
