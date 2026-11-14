"""07.3 notification preferences, deduplication and durable email outbox."""
import django.db.models.deletion
import django.db.models.functions.datetime
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('notifications', '0002_order_event_deduplication'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='notification', name='dedupe_key',
            field=models.CharField(max_length=120, null=True, blank=True, editable=False),
        ),
        migrations.AddConstraint(
            model_name='notification',
            constraint=models.UniqueConstraint(
                fields=['recipient', 'dedupe_key'], name='notif_recipient_key_unique',
            ),
        ),
        migrations.AlterField(
            model_name='notification',
            name='notification_type',
            field=models.CharField(
                max_length=30, default='system', db_index=True,
                verbose_name='Тип', choices=[
                    ('order_created', 'Заявка создана'),
                    ('order_updated', 'Условия заявки изменены'),
                    ('new_response', 'Новый отклик'),
                    ('response_accepted', 'Вас выбрали'),
                    ('response_rejected', 'Выбран другой мастер'),
                    ('order_cancelled', 'Заявка отменена'),
                    ('order_completed', 'Заявка завершена'),
                    ('review_created', 'Новый отзыв'),
                    ('new_message', 'Новое сообщение'),
                    ('invitation', 'Приглашение'),
                    ('complaint', 'Жалоба'),
                    ('review_reply', 'Ответ на отзыв'),
                    ('system', 'Системное'),
                ],
            ),
        ),
        migrations.CreateModel(
            name='NotificationPreference',
            fields=[
                ('id', models.BigAutoField(
                    auto_created=True, primary_key=True, serialize=False, verbose_name='ID',
                )),
                ('in_app_optional', models.BooleanField(default=True)),
                ('email_optional', models.BooleanField(default=False)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('recipient', models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='notification_preference', to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={'db_table': 'notifications_preference'},
        ),
        migrations.CreateModel(
            name='NotificationDelivery',
            fields=[
                ('id', models.BigAutoField(
                    auto_created=True, primary_key=True, serialize=False, verbose_name='ID',
                )),
                ('channel', models.CharField(default='email', max_length=12)),
                ('status', models.CharField(
                    choices=[
                        ('pending', 'Pending'), ('retry', 'Retry'),
                        ('delivered', 'Delivered'), ('dead', 'Dead letter'),
                        ('suppressed', 'Suppressed'),
                    ], default='pending', max_length=12,
                )),
                ('attempts', models.PositiveSmallIntegerField(default=0)),
                ('next_attempt_at', models.DateTimeField(default=django.db.models.functions.datetime.Now)),
                ('last_error_code', models.CharField(blank=True, default='', max_length=40)),
                ('delivered_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('notification', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='deliveries', to='notifications.notification',
                )),
            ],
            options={'db_table': 'notifications_delivery'},
        ),
        migrations.AddConstraint(
            model_name='notificationdelivery',
            constraint=models.UniqueConstraint(
                fields=['notification', 'channel'], name='notif_delivery_unique',
            ),
        ),
        migrations.AddConstraint(
            model_name='notificationdelivery',
            constraint=models.CheckConstraint(
                condition=models.Q(
                    status__in=['pending', 'retry', 'delivered', 'dead', 'suppressed'],
                ), name='notif_delivery_status_valid',
            ),
        ),
        migrations.AddIndex(
            model_name='notificationdelivery',
            index=models.Index(
                fields=['status', 'next_attempt_at'], name='notif_delivery_due_idx',
            ),
        ),
    ]
