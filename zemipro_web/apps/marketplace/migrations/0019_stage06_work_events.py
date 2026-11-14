"""Stage 06.5: immutable evidence for work start, result and problems."""
import uuid

from django.db import migrations, models
import django.db.models.deletion


APPEND_ONLY = """
CREATE TRIGGER order_work_event_immutable BEFORE UPDATE OR DELETE
ON marketplace_order_work_event FOR EACH ROW
EXECUTE FUNCTION zemipro_stage06_immutable();
"""

REVERSE = """
DROP TRIGGER IF EXISTS order_work_event_immutable ON marketplace_order_work_event;
"""


class Migration(migrations.Migration):
    dependencies = [('marketplace', '0018_stage06_agreements')]

    operations = [
        migrations.CreateModel(
            name='OrderWorkEvent',
            fields=[
                ('id', models.BigAutoField(
                    auto_created=True, primary_key=True,
                    serialize=False, verbose_name='ID',
                )),
                ('action', models.CharField(
                    choices=[
                        ('started', 'Начало работы'),
                        ('result_submitted', 'Результат передан'),
                        ('result_confirmed', 'Результат подтверждён'),
                        ('problem', 'Сообщено о проблеме'),
                    ], max_length=20,
                )),
                ('problem_code', models.CharField(
                    choices=[
                        ('', 'Нет'), ('timing', 'Сроки'),
                        ('quality', 'Качество'), ('other', 'Другая проблема'),
                    ], default='', max_length=8,
                )),
                ('operation_key', models.UUIDField(
                    default=uuid.uuid4, editable=False,
                )),
                ('occurred_at', models.DateTimeField(auto_now_add=True)),
                ('order', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='work_events', to='marketplace.order',
                )),
                ('actor', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='order_work_events', to='accounts.user',
                )),
            ],
            options={
                'db_table': 'marketplace_order_work_event',
                'ordering': ['occurred_at', 'pk'],
            },
        ),
        migrations.AddConstraint(
            model_name='orderworkevent',
            constraint=models.UniqueConstraint(
                fields=('order', 'operation_key'), name='work_event_operation_unique',
            ),
        ),
        migrations.AddConstraint(
            model_name='orderworkevent',
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(
                        action='problem', problem_code__in=['timing', 'quality', 'other'],
                    ) | models.Q(
                        action__in=['started', 'result_submitted', 'result_confirmed'],
                        problem_code='',
                    )
                ), name='work_event_action_problem_valid',
            ),
        ),
        migrations.RunSQL(APPEND_ONLY, reverse_sql=REVERSE),
    ]
