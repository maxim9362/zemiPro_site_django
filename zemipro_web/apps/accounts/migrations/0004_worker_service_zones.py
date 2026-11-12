"""Stage 02.2: opt-in worker multi-city zones; no destructive data backfill."""
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('accounts', '0003_sensitive_post_counter'),
        ('locations', '0002_district_city_alias'),
    ]

    operations = [
        migrations.AddField(
            model_name='workerprofile', name='offers_remote',
            field=models.BooleanField(default=False, verbose_name='Работаю онлайн'),
        ),
        migrations.AddField(
            model_name='workerprofile', name='service_cities',
            field=models.ManyToManyField(
                blank=True, related_name='service_workers',
                to='locations.city', verbose_name='Города обслуживания',
            ),
        ),
    ]
