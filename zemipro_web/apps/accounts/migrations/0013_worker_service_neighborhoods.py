"""Stage 05.2: explicit worker neighborhood coverage, empty by default."""
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('accounts', '0012_worker_directory_search'),
        ('locations', '0003_service_neighborhoods'),
    ]

    operations = [
        migrations.AddField(
            model_name='workerprofile',
            name='service_neighborhoods',
            field=models.ManyToManyField(
                to='locations.neighborhood', blank=True,
                related_name='service_workers', verbose_name='Районы обслуживания',
            ),
        ),
    ]
