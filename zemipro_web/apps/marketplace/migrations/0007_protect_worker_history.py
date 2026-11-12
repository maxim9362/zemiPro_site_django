"""Stage 03.6: prevent accidental removal of historical worker responses/ratings."""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('marketplace', '0006_versioned_questionnaires'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name='response', name='worker',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='responses', to=settings.AUTH_USER_MODEL,
                verbose_name='Исполнитель',
            ),
        ),
        migrations.AlterField(
            model_name='rating', name='worker',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='received_ratings', to=settings.AUTH_USER_MODEL,
                verbose_name='Исполнитель',
            ),
        ),
    ]
