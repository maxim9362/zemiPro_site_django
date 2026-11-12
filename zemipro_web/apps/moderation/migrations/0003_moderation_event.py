"""Stage 03.6: durable append-only moderation audit with minimal metadata."""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


CREATE_APPEND_ONLY_TRIGGER = """
CREATE OR REPLACE FUNCTION zemipro_moderation_event_immutable()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'moderation event history is append-only';
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER moderation_event_immutable
BEFORE UPDATE OR DELETE ON moderation_event
FOR EACH ROW EXECUTE FUNCTION zemipro_moderation_event_immutable();
"""

DROP_APPEND_ONLY_TRIGGER = """
DROP TRIGGER IF EXISTS moderation_event_immutable ON moderation_event;
DROP FUNCTION IF EXISTS zemipro_moderation_event_immutable();
"""


class Migration(migrations.Migration):
    dependencies = [
        ('moderation', '0002_status_constraint'),
        ('accounts', '0009_worker_portfolio'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ModerationEvent',
            fields=[
                ('id', models.BigAutoField(
                    auto_created=True, primary_key=True,
                    serialize=False, verbose_name='ID',
                )),
                ('action', models.CharField(
                    max_length=40, choices=[
                        ('complaint_resolved', 'Рассмотрена жалоба'),
                        ('complaint_dismissed', 'Жалоба отклонена'),
                        ('account_blocked', 'Пользователь заблокирован'),
                        ('account_unblocked', 'Пользователь разблокирован'),
                        ('privacy_processing', 'Запрос на рассмотрении'),
                        ('privacy_rejected', 'Запрос отклонён'),
                    ],
                )),
                ('occurred_at', models.DateTimeField(auto_now_add=True)),
                ('actor', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='moderation_actions_performed',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('target_user', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='moderation_actions_received',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('complaint', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='audit_events', to='moderation.complaint',
                )),
                ('privacy_request', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='audit_events', to='accounts.privacyrequest',
                )),
            ],
            options={
                'db_table': 'moderation_event',
                'ordering': ['-occurred_at', '-pk'],
                'permissions': [
                    ('moderate_accounts', 'Can block and unblock user accounts'),
                    ('review_complaints', 'Can review complaints'),
                    ('review_privacy_requests', 'Can review privacy requests'),
                ],
            },
        ),
        migrations.AddIndex(
            model_name='moderationevent',
            index=models.Index(
                fields=['target_user', '-occurred_at'],
                name='moderation_target_time_idx',
            ),
        ),
        migrations.RunSQL(
            sql=CREATE_APPEND_ONLY_TRIGGER,
            reverse_sql=DROP_APPEND_ONLY_TRIGGER,
        ),
    ]
