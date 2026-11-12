"""Stage 04.7 durable, PII-free outbox plus in-app/analytics receipts."""
import uuid

from django.db import migrations, models
import django.db.models.deletion


APPEND_ONLY_SQL = """
CREATE OR REPLACE FUNCTION zemipro_order_domain_event_immutable()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'order domain events are append-only';
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER order_domain_event_immutable
BEFORE UPDATE OR DELETE ON marketplace_order_domain_event
FOR EACH ROW EXECUTE FUNCTION zemipro_order_domain_event_immutable();
"""

DROP_TRIGGER_SQL = """
DROP TRIGGER IF EXISTS order_domain_event_immutable ON marketplace_order_domain_event;
DROP FUNCTION IF EXISTS zemipro_order_domain_event_immutable();
"""


def prevent_history_loss(apps, schema_editor):
    Event = apps.get_model('marketplace', 'OrderDomainEvent')
    if Event.objects.using(schema_editor.connection.alias).exists():
        raise RuntimeError('Stage 04.7 downgrade refused: event history would be lost.')


class Migration(migrations.Migration):
    dependencies = [
        ('marketplace', '0013_order_write_quota'),
    ]

    operations = [
        migrations.CreateModel(
            name='OrderDomainEvent',
            fields=[
                ('id', models.BigAutoField(
                    primary_key=True, serialize=False, auto_created=True,
                    verbose_name='ID',
                )),
                ('kind', models.CharField(max_length=24, choices=[
                    ('order_created', 'Создание заявки'),
                    ('order_published', 'Публикация заявки'),
                    ('order_updated', 'Изменение условий'),
                    ('order_cancelled', 'Отмена заявки'),
                ])),
                ('source_key', models.UUIDField(editable=False)),
                ('event_key', models.UUIDField(unique=True, editable=False)),
                ('occurred_at', models.DateTimeField(auto_now_add=True)),
                ('category', models.ForeignKey(
                    to='marketplace.category',
                    on_delete=django.db.models.deletion.PROTECT,
                )),
                ('city', models.ForeignKey(
                    to='locations.city',
                    on_delete=django.db.models.deletion.PROTECT,
                )),
                ('order', models.ForeignKey(
                    to='marketplace.order',
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='domain_events',
                )),
            ],
            options={
                'db_table': 'marketplace_order_domain_event',
                'ordering': ['occurred_at', 'pk'],
            },
        ),
        migrations.AddConstraint(
            model_name='orderdomainevent',
            constraint=models.UniqueConstraint(
                fields=['order', 'kind', 'source_key'],
                name='order_domain_source_unique',
            ),
        ),
        migrations.AddIndex(
            model_name='orderdomainevent',
            index=models.Index(
                fields=['kind', 'occurred_at'], name='order_domain_kind_time_idx',
            ),
        ),
        migrations.CreateModel(
            name='OrderEventDelivery',
            fields=[
                ('id', models.BigAutoField(
                    primary_key=True, serialize=False, auto_created=True,
                    verbose_name='ID',
                )),
                ('consumer', models.CharField(max_length=16, choices=[
                    ('notifications', 'Внутренние уведомления'),
                    ('analytics', 'Внутренняя аналитика'),
                ])),
                ('status', models.CharField(
                    max_length=8, default='pending', choices=[
                        ('pending', 'Ожидает'),
                        ('done', 'Обработано'),
                    ],
                )),
                ('attempts', models.PositiveIntegerField(default=0)),
                ('last_error_code', models.CharField(
                    max_length=32, blank=True, default='',
                )),
                ('processed_at', models.DateTimeField(null=True, blank=True)),
                ('event', models.ForeignKey(
                    to='marketplace.orderdomainevent',
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='deliveries',
                )),
            ],
            options={
                'db_table': 'marketplace_order_event_delivery',
                'ordering': ['event_id', 'consumer'],
            },
        ),
        migrations.AddConstraint(
            model_name='ordereventdelivery',
            constraint=models.UniqueConstraint(
                fields=['event', 'consumer'],
                name='order_delivery_consumer_unique',
            ),
        ),
        migrations.CreateModel(
            name='OrderAnalyticsFact',
            fields=[
                ('id', models.BigAutoField(
                    primary_key=True, serialize=False, auto_created=True,
                    verbose_name='ID',
                )),
                ('kind', models.CharField(max_length=24, choices=[
                    ('order_created', 'Создание заявки'),
                    ('order_published', 'Публикация заявки'),
                    ('order_updated', 'Изменение условий'),
                    ('order_cancelled', 'Отмена заявки'),
                ])),
                ('occurred_at', models.DateTimeField()),
                ('event', models.OneToOneField(
                    to='marketplace.orderdomainevent',
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='analytics_fact',
                )),
                ('category', models.ForeignKey(
                    to='marketplace.category',
                    on_delete=django.db.models.deletion.PROTECT,
                )),
                ('city', models.ForeignKey(
                    to='locations.city',
                    on_delete=django.db.models.deletion.PROTECT,
                )),
            ],
            options={'db_table': 'marketplace_order_analytics_fact'},
        ),
        migrations.AddIndex(
            model_name='orderanalyticsfact',
            index=models.Index(
                fields=['kind', 'occurred_at'], name='order_fact_kind_time_idx',
            ),
        ),
        migrations.RunSQL(APPEND_ONLY_SQL, reverse_sql=DROP_TRIGGER_SQL),
        migrations.RunPython(migrations.RunPython.noop, reverse_code=prevent_history_loss),
    ]
