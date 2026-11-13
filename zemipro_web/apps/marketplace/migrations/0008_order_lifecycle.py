"""Stage 04.1: preserve legacy status in a new canonical lifecycle."""
import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


ORDER_STATUSES = (
    'draft', 'published', 'in_discussion', 'assigned', 'in_progress',
    'completed', 'cancelled', 'expired', 'disputed',
)

APPEND_ONLY_SQL = """
CREATE OR REPLACE FUNCTION zemipro_order_status_event_immutable()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'order status event history is append-only';
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER order_status_event_immutable
BEFORE UPDATE OR DELETE ON marketplace_order_status_event
FOR EACH ROW EXECUTE FUNCTION zemipro_order_status_event_immutable();
"""

DROP_TRIGGER_SQL = """
DROP TRIGGER IF EXISTS order_status_event_immutable ON marketplace_order_status_event;
DROP FUNCTION IF EXISTS zemipro_order_status_event_immutable();
"""


def upgrade_legacy_statuses(apps, schema_editor):
    db = schema_editor.connection.alias
    Order = apps.get_model('marketplace', 'Order')
    Event = apps.get_model('marketplace', 'OrderStatusEvent')
    pending = []
    order_ids = []
    for row in Order.objects.using(db).filter(status='new').only('pk').iterator(chunk_size=400):
        order_ids.append(row.pk)
        pending.append(Event(
            order_id=row.pk, actor_id=None, previous_status='new',
            new_status='published', reason='legacy_migration',
            operation_key=uuid.uuid4(),
        ))
        if len(order_ids) >= 400:
            Order.objects.using(db).filter(pk__in=order_ids).update(
                status='published', legacy_status='new',
            )
            Event.objects.using(db).bulk_create(pending, batch_size=400)
            pending.clear()
            order_ids.clear()
    if order_ids:
        Order.objects.using(db).filter(pk__in=order_ids).update(
            status='published', legacy_status='new',
        )
        Event.objects.using(db).bulk_create(pending, batch_size=400)


def reverse_only_when_safe(apps, schema_editor):
    db = schema_editor.connection.alias
    Order = apps.get_model('marketplace', 'Order')
    Event = apps.get_model('marketplace', 'OrderStatusEvent')
    if (Event.objects.using(db).exists()
            or Order.objects.using(db).exclude(status__in=(
                'published', 'in_progress', 'completed', 'cancelled',
            )).exists()):
        raise RuntimeError(
            'Stage 04.1 downgrade refused: status events or new states '
            'would be lost. Restore with an approved data-preserving plan.'
        )
    Order.objects.using(db).filter(status='published').update(
        status='new', legacy_status=None,
    )


class Migration(migrations.Migration):
    dependencies = [
        ('marketplace', '0007_protect_worker_history'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RemoveConstraint(model_name='order', name='order_status_allowed'),
        migrations.AddField(
            model_name='order', name='legacy_status',
            field=models.CharField(
                max_length=20, null=True, blank=True, editable=False,
                verbose_name='Исходный исторический статус',
            ),
        ),
        migrations.AlterField(
            model_name='order', name='status',
            field=models.CharField(
                choices=[
                    ('draft', 'Черновик'), ('published', 'Опубликован'),
                    ('in_discussion', 'Обсуждение'),
                    ('assigned', 'Исполнитель выбран'),
                    ('in_progress', 'В процессе'), ('completed', 'Выполнен'),
                    ('cancelled', 'Отменён'), ('expired', 'Истёк срок'),
                    ('disputed', 'Спор'),
                ],
                max_length=20, default='published', db_index=True,
                verbose_name='Статус',
            ),
        ),
        migrations.CreateModel(
            name='OrderStatusEvent',
            fields=[
                ('id', models.BigAutoField(
                    auto_created=True, primary_key=True,
                    serialize=False, verbose_name='ID',
                )),
                ('previous_status', models.CharField(
                    max_length=20, blank=True, default='',
                )),
                ('new_status', models.CharField(
                    max_length=20, choices=[
                        ('draft', 'Черновик'), ('published', 'Опубликован'),
                        ('in_discussion', 'Обсуждение'),
                        ('assigned', 'Исполнитель выбран'),
                        ('in_progress', 'В процессе'), ('completed', 'Выполнен'),
                        ('cancelled', 'Отменён'), ('expired', 'Истёк срок'),
                        ('disputed', 'Спор'),
                    ],
                )),
                ('reason', models.CharField(
                    max_length=32, default='transition', choices=[
                        ('created', 'Создание'),
                        ('transition', 'Смена статуса'),
                        ('worker_assigned', 'Выбор мастера'),
                        ('work_started', 'Начало работы'),
                        ('legacy_migration', 'Историческая миграция'),
                    ],
                )),
                ('operation_key', models.UUIDField(default=uuid.uuid4, editable=False)),
                ('occurred_at', models.DateTimeField(auto_now_add=True)),
                ('actor', models.ForeignKey(
                    to=settings.AUTH_USER_MODEL, blank=True, null=True,
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='order_status_actions',
                )),
                ('order', models.ForeignKey(
                    to='marketplace.order',
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='status_events',
                )),
            ],
            options={
                'db_table': 'marketplace_order_status_event',
                'verbose_name': 'Событие статуса заявки',
                'verbose_name_plural': 'События статусов заявок',
                'ordering': ['-occurred_at', '-pk'],
            },
        ),
        migrations.AddIndex(
            model_name='orderstatusevent',
            index=models.Index(fields=['order', '-occurred_at'], name='order_event_time_idx'),
        ),
        migrations.AddConstraint(
            model_name='orderstatusevent',
            constraint=models.UniqueConstraint(
                fields=['order', 'operation_key'],
                name='order_event_unique_operation',
            ),
        ),
        migrations.RunPython(upgrade_legacy_statuses, reverse_only_when_safe),
        migrations.AddConstraint(
            model_name='order',
            constraint=models.CheckConstraint(
                condition=models.Q(status__in=ORDER_STATUSES),
                name='order_status_allowed',
            ),
        ),
        migrations.RunSQL(sql=APPEND_ONLY_SQL, reverse_sql=DROP_TRIGGER_SQL),
    ]
