"""Stage 04.5 immutable order-management history, additive only."""
import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


APPEND_ONLY_SQL = """
CREATE OR REPLACE FUNCTION zemipro_order_management_event_immutable()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'order management history is append-only';
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER order_management_event_immutable
BEFORE UPDATE OR DELETE ON marketplace_order_management_event
FOR EACH ROW EXECUTE FUNCTION zemipro_order_management_event_immutable();
CREATE OR REPLACE FUNCTION zemipro_order_answer_archive_immutable()
RETURNS TRIGGER AS $
BEGIN
    RAISE EXCEPTION 'order questionnaire archive is append-only';
END;
$ LANGUAGE plpgsql;
CREATE TRIGGER order_answer_archive_immutable
BEFORE UPDATE OR DELETE ON marketplace_order_questionnaire_answer_archive
FOR EACH ROW EXECUTE FUNCTION zemipro_order_answer_archive_immutable();
"""

DROP_SQL = """
DROP TRIGGER IF EXISTS order_management_event_immutable ON marketplace_order_management_event;
DROP FUNCTION IF EXISTS zemipro_order_management_event_immutable();
DROP TRIGGER IF EXISTS order_answer_archive_immutable ON marketplace_order_questionnaire_answer_archive;
DROP FUNCTION IF EXISTS zemipro_order_answer_archive_immutable();
"""


class Migration(migrations.Migration):
    dependencies = [
        ('marketplace', '0011_order_details_and_attachments'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='OrderManagementEvent',
            fields=[
                ('id', models.BigAutoField(
                    auto_created=True, primary_key=True, serialize=False,
                    verbose_name='ID',
                )),
                ('action', models.CharField(max_length=16, choices=[
                    ('edited', 'Условия изменены'), ('duplicated', 'Создана копия'),
                ])),
                ('changed_fields', models.JSONField(blank=True, default=list)),
                ('operation_key', models.UUIDField(
                    editable=False, default=uuid.uuid4,
                )),
                ('occurred_at', models.DateTimeField(auto_now_add=True)),
                ('order', models.ForeignKey(
                    to='marketplace.order',
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='management_events',
                )),
                ('target_order', models.ForeignKey(
                    to='marketplace.order', null=True, blank=True,
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='duplicate_source_events',
                )),
                ('actor', models.ForeignKey(
                    to=settings.AUTH_USER_MODEL,
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='order_management_actions',
                )),
            ],
            options={
                'db_table': 'marketplace_order_management_event',
                'ordering': ['occurred_at', 'pk'],
            },
        ),
        migrations.AddConstraint(
            model_name='ordermanagementevent',
            constraint=models.UniqueConstraint(
                fields=['order', 'operation_key'],
                name='order_mgmt_unique_operation',
            ),
        ),
        migrations.AddIndex(
            model_name='ordermanagementevent',
            index=models.Index(
                fields=['order', 'occurred_at'], name='order_mgmt_time_idx',
            ),
        ),
        migrations.CreateModel(
            name='OrderQuestionnaireAnswerArchive',
            fields=[
                ('id', models.BigAutoField(
                    auto_created=True, primary_key=True, serialize=False,
                    verbose_name='ID',
                )),
                ('schema_snapshot', models.JSONField(default=list)),
                ('answers', models.JSONField(default=dict)),
                ('archived_at', models.DateTimeField(auto_now_add=True)),
                ('order', models.ForeignKey(
                    to='marketplace.order',
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='questionnaire_answer_archives',
                )),
                ('version', models.ForeignKey(
                    to='marketplace.questionnaireversion',
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='archived_order_answers',
                )),
            ],
            options={
                'db_table': 'marketplace_order_questionnaire_answer_archive',
                'ordering': ['archived_at', 'pk'],
            },
        ),
        migrations.RunSQL(APPEND_ONLY_SQL, reverse_sql=DROP_SQL),
    ]
