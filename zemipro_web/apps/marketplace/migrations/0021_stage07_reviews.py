"""07.4 verified review replies and immutable audit; protect score integrity."""
from django.db import migrations, models
import django.db.models.deletion

SQL = """
CREATE OR REPLACE FUNCTION zemipro_stage07_rating_guard() RETURNS TRIGGER AS $$
BEGIN
    IF NEW.rating IS DISTINCT FROM OLD.rating
       OR NEW.order_id IS DISTINCT FROM OLD.order_id
       OR NEW.worker_id IS DISTINCT FROM OLD.worker_id
       OR NEW.client_id IS DISTINCT FROM OLD.client_id
       OR NEW.review_text IS DISTINCT FROM OLD.review_text
       OR NEW.created_at IS DISTINCT FROM OLD.created_at
    THEN
        RAISE EXCEPTION 'verified review original is immutable';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER stage07_rating_guard BEFORE UPDATE ON marketplace_rating
    FOR EACH ROW EXECUTE FUNCTION zemipro_stage07_rating_guard();
CREATE TRIGGER stage07_rating_reply_guard BEFORE UPDATE OR DELETE
    ON marketplace_rating_reply FOR EACH ROW
    EXECUTE FUNCTION zemipro_stage06_immutable();
CREATE TRIGGER stage07_rating_audit_guard BEFORE UPDATE OR DELETE
    ON marketplace_rating_audit FOR EACH ROW
    EXECUTE FUNCTION zemipro_stage06_immutable();
"""
REVERSE = """
DROP TRIGGER IF EXISTS stage07_rating_guard ON marketplace_rating;
DROP TRIGGER IF EXISTS stage07_rating_reply_guard ON marketplace_rating_reply;
DROP TRIGGER IF EXISTS stage07_rating_audit_guard ON marketplace_rating_audit;
DROP FUNCTION IF EXISTS zemipro_stage07_rating_guard();
"""


class Migration(migrations.Migration):
    dependencies = [('marketplace', '0020_stage07_chat')]

    operations = [
        migrations.AddConstraint(
            model_name='rating',
            constraint=models.CheckConstraint(
                condition=models.Q(rating__gte=1, rating__lte=5),
                name='rating_score_five_point_valid',
            ),
        ),
        migrations.CreateModel(
            name='RatingReply',
            fields=[
                ('id', models.BigAutoField(
                    auto_created=True, primary_key=True, serialize=False, verbose_name='ID',
                )),
                ('body', models.TextField()),
                ('public_body_snapshot', models.TextField(
                    blank=True, default='', editable=False,
                )),
                ('policy_version', models.PositiveSmallIntegerField(
                    default=0, editable=False,
                )),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('rating', models.OneToOneField(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='worker_reply', to='marketplace.rating',
                )),
                ('worker', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='rating_replies', to='accounts.user',
                )),
            ],
            options={'db_table': 'marketplace_rating_reply'},
        ),
        migrations.CreateModel(
            name='RatingAuditEvent',
            fields=[
                ('id', models.BigAutoField(
                    auto_created=True, primary_key=True, serialize=False, verbose_name='ID',
                )),
                ('action', models.CharField(
                    choices=[
                        ('created', 'Review created'),
                        ('replied', 'Worker replied'),
                    ], max_length=12,
                )),
                ('score', models.PositiveSmallIntegerField()),
                ('occurred_at', models.DateTimeField(auto_now_add=True)),
                ('rating', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='audit_events', to='marketplace.rating',
                )),
                ('actor', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='review_actions', to='accounts.user',
                )),
            ],
            options={
                'db_table': 'marketplace_rating_audit',
                'ordering': ['occurred_at', 'pk'],
            },
        ),
        migrations.AddConstraint(
            model_name='ratingauditevent',
            constraint=models.UniqueConstraint(
                fields=['rating', 'action'], name='rating_audit_action_unique',
            ),
        ),
        migrations.RunSQL(SQL, reverse_sql=REVERSE),
    ]
