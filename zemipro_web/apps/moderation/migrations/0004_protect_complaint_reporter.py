"""Stage 03.6: protect reporter identity and complaint history from cascade."""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('moderation', '0003_moderation_event'),
    ]
    operations = [
        migrations.AlterField(
            model_name='complaint', name='reporter',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='complaints_filed',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Кто пожаловался',
            ),
        ),
    ]
