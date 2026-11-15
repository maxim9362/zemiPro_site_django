"""07.5 complaints on messages and one appeal with audited decisions."""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion

SQL = """
CREATE OR REPLACE FUNCTION zemipro_stage07_appeal_original_guard() RETURNS TRIGGER AS $$
BEGIN
    IF NEW.complaint_id IS DISTINCT FROM OLD.complaint_id
       OR NEW.filed_by_id IS DISTINCT FROM OLD.filed_by_id
       OR NEW.reason IS DISTINCT FROM OLD.reason
       OR NEW.created_at IS DISTINCT FROM OLD.created_at
    THEN
       RAISE EXCEPTION 'appeal evidence is immutable';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER stage07_appeal_original_guard BEFORE UPDATE
    ON moderation_complaint_appeal FOR EACH ROW
    EXECUTE FUNCTION zemipro_stage07_appeal_original_guard();
"""
REVERSE = """
DROP TRIGGER IF EXISTS stage07_appeal_original_guard ON moderation_complaint_appeal;
DROP FUNCTION IF EXISTS zemipro_stage07_appeal_original_guard();
"""


class Migration(migrations.Migration):
    dependencies = [
        ('moderation', '0004_protect_complaint_reporter'),
        ('marketplace', '0021_stage07_reviews'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='complaint',
            name='target_message',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name='complaints', to='marketplace.message',
            ),
        ),
        migrations.AlterField(
            model_name='moderationevent',
            name='action',
            field=models.CharField(
                max_length=40, choices=[
                    ('complaint_resolved', 'Рассмотрена жалоба'),
                    ('complaint_dismissed', 'Жалоба отклонена'),
                    ('account_blocked', 'Пользователь заблокирован'),
                    ('account_unblocked', 'Пользователь разблокирован'),
                    ('privacy_processing', 'Запрос на рассмотрении'),
                    ('privacy_rejected', 'Запрос отклонён'),
                    ('appeal_filed', 'Апелляция подана'),
                    ('appeal_accepted', 'Апелляция удовлетворена'),
                    ('appeal_rejected', 'Апелляция отклонена'),
                ],
            ),
        ),
        migrations.CreateModel(
            name='ComplaintAppeal',
            fields=[
                ('id', models.BigAutoField(
                    auto_created=True, primary_key=True, serialize=False, verbose_name='ID',
                )),
                ('reason', models.TextField()),
                ('status', models.CharField(
                    choices=[
                        ('pending', 'Awaiting review'), ('accepted', 'Granted'),
                        ('rejected', 'Denied'),
                    ], default='pending', max_length=12,
                )),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('decided_at', models.DateTimeField(blank=True, null=True)),
                ('complaint', models.OneToOneField(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='appeal', to='moderation.complaint',
                )),
                ('decided_by', models.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                    related_name='decided_moderation_appeals', to=settings.AUTH_USER_MODEL,
                )),
                ('filed_by', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='moderation_appeals', to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'db_table': 'moderation_complaint_appeal',
                'ordering': ['-created_at', '-pk'],
            },
        ),
        migrations.AddConstraint(
            model_name='complaintappeal',
            constraint=models.CheckConstraint(
                condition=models.Q(status__in=['pending', 'accepted', 'rejected']),
                name='moderation_appeal_status_allowed',
            ),
        ),
        migrations.RunSQL(SQL, reverse_sql=REVERSE),
    ]
