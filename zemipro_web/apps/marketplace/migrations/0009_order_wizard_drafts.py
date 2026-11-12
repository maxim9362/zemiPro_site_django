"""Stage 04.2: additive private draft metadata; no historical rewrites."""
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('marketplace', '0008_order_lifecycle')]

    operations = [
        migrations.AddField(
            model_name='order', name='wizard_data',
            field=models.JSONField(
                blank=True, default=dict, editable=False,
                verbose_name='Приватные данные мастера создания заявки',
            ),
        ),
        migrations.AddField(
            model_name='order', name='wizard_token',
            field=models.UUIDField(
                blank=True, editable=False, null=True, unique=True,
                verbose_name='Ключ защиты от повторного создания черновика',
            ),
        ),
    ]
