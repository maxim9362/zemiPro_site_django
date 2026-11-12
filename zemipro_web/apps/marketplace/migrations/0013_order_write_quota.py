"""Stage 04.6: durable cross-worker order operation budget."""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('marketplace', '0012_order_management_events'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='OrderWriteQuota',
            fields=[
                ('id', models.BigAutoField(
                    auto_created=True, primary_key=True, serialize=False,
                    verbose_name='ID',
                )),
                ('kind', models.CharField(max_length=8, choices=[
                    ('create', 'Создания заявок'),
                    ('wizard', 'Сохранения шагов'),
                    ('edit', 'Редактирование условий'),
                    ('response', 'Отклики исполнителей'),
                    ('photo', 'Новые фотографии'),
                    ('state', 'Переходы статусов'),
                ])),
                ('bucket_start', models.DateTimeField()),
                ('used', models.PositiveIntegerField(default=0)),
                ('owner', models.ForeignKey(
                    to=settings.AUTH_USER_MODEL,
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='order_write_quotas',
                )),
            ],
            options={'db_table': 'marketplace_order_write_quota'},
        ),
        migrations.AddConstraint(
            model_name='orderwritequota',
            constraint=models.UniqueConstraint(
                fields=['owner', 'kind', 'bucket_start'],
                name='order_quota_owner_kind_window_unique',
            ),
        ),
        migrations.AddIndex(
            model_name='orderwritequota',
            index=models.Index(
                fields=['bucket_start'], name='order_quota_window_idx',
            ),
        ),
    ]
