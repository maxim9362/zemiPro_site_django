"""Stage 05.4 registered specialist invitations; no legacy data conversion."""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [
        ('marketplace', '0014_order_domain_outbox'),
        ('accounts', '0013_worker_service_neighborhoods'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name='orderwritequota',
            name='kind',
            field=models.CharField(max_length=8, choices=[
                ('create', 'Создания заявок'),
                ('wizard', 'Сохранения шагов'),
                ('edit', 'Редактирование условий'),
                ('response', 'Отклики исполнителей'),
                ('photo', 'Новые фотографии'),
                ('state', 'Переходы статусов'),
                ('invite', 'Приглашения мастерам'),
            ]),
        ),
        migrations.CreateModel(
            name='OrderInvitation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name='ID')),
                ('status', models.CharField(default='pending', max_length=12, choices=[
                    ('pending', 'Ожидает'), ('accepted', 'Принято'),
                    ('declined', 'Отклонено'), ('withdrawn', 'Отозвано'),
                    ('expired', 'Истекло'), ('unavailable', 'Недоступно'),
                ])),
                ('expires_at', models.DateTimeField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('client', models.ForeignKey(
                    to=settings.AUTH_USER_MODEL, related_name='sent_order_invitations',
                    on_delete=django.db.models.deletion.PROTECT,
                )),
                ('order', models.ForeignKey(
                    to='marketplace.order', related_name='specialist_invitations',
                    on_delete=django.db.models.deletion.PROTECT,
                )),
                ('worker', models.ForeignKey(
                    to='accounts.workerprofile', related_name='order_invitations',
                    on_delete=django.db.models.deletion.PROTECT,
                )),
            ],
            options={
                'db_table': 'marketplace_order_invitation',
                'ordering': ['-created_at', '-pk'],
            },
        ),
        migrations.AddConstraint(
            model_name='orderinvitation',
            constraint=models.UniqueConstraint(
                fields=('order', 'worker'),
                name='market_order_worker_invite_unique',
            ),
        ),
        migrations.AddConstraint(
            model_name='orderinvitation',
            constraint=models.CheckConstraint(
                condition=models.Q(status__in=[
                    'pending', 'accepted', 'declined', 'withdrawn',
                    'expired', 'unavailable',
                ]),
                name='market_order_invite_status_allowed',
            ),
        ),
        migrations.AddIndex(
            model_name='orderinvitation',
            index=models.Index(
                fields=['worker', 'status', '-created_at'],
                name='market_inv_worker_status_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='orderinvitation',
            index=models.Index(
                fields=['client', '-created_at'],
                name='market_inv_client_created_idx',
            ),
        ),
    ]
