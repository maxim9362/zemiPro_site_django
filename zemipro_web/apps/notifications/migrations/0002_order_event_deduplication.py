"""04.7 in-app delivery deduplication, no external channel activation."""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('notifications', '0001_initial'),
        ('marketplace', '0014_order_domain_outbox'),
    ]

    operations = [
        migrations.AddField(
            model_name='notification',
            name='order_event',
            field=models.ForeignKey(
                to='marketplace.orderdomainevent',
                null=True, blank=True, editable=False,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='notifications',
            ),
        ),
        migrations.AlterField(
            model_name='notification',
            name='notification_type',
            field=models.CharField(
                max_length=30, default='system', db_index=True,
                verbose_name='Тип',
                choices=[
                    ('order_created', 'Заявка создана'),
                    ('order_updated', 'Условия заявки изменены'),
                    ('new_response', 'Новый отклик'),
                    ('response_accepted', 'Вас выбрали'),
                    ('response_rejected', 'Выбран другой мастер'),
                    ('order_cancelled', 'Заявка отменена'),
                    ('order_completed', 'Заявка завершена'),
                    ('review_created', 'Новый отзыв'),
                    ('system', 'Системное'),
                ],
            ),
        ),
        migrations.AddConstraint(
            model_name='notification',
            constraint=models.UniqueConstraint(
                fields=['order_event', 'recipient'],
                name='notif_order_event_recipient_unique',
            ),
        ),
    ]
