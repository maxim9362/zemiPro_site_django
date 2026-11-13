"""Stage 05.5 private viewing history: opt-in, no legacy data migration."""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [
        ('accounts', '0013_worker_service_neighborhoods'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='clientprofile',
            name='track_worker_views',
            field=models.BooleanField(default=False),
        ),
        migrations.CreateModel(
            name='WorkerProfileView',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name='ID')),
                ('last_viewed_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('client', models.ForeignKey(
                    to=settings.AUTH_USER_MODEL, related_name='viewed_workers',
                    on_delete=django.db.models.deletion.CASCADE,
                )),
                ('worker', models.ForeignKey(
                    to='accounts.workerprofile', related_name='viewer_history',
                    on_delete=django.db.models.deletion.CASCADE,
                )),
            ],
            options={'db_table': 'accounts_worker_profile_view'},
        ),
        migrations.AddConstraint(
            model_name='workerprofileview',
            constraint=models.UniqueConstraint(
                fields=['client', 'worker'],
                name='accounts_unique_private_worker_view',
            ),
        ),
        migrations.AddIndex(
            model_name='workerprofileview',
            index=models.Index(
                fields=['client', '-last_viewed_at'],
                name='accounts_view_owner_recent_idx',
            ),
        ),
    ]
