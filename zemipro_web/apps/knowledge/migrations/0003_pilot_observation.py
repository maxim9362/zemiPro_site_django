"""Stage 14.4: isolated opt-in pilot, whitelist, auditable metrics and real-order link."""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


GUARD = """
CREATE TRIGGER knowledge_pilot_audit_guard BEFORE UPDATE OR DELETE
ON knowledge_pilot_audit FOR EACH ROW
EXECUTE FUNCTION knowledge_block_revision_mutation();
"""
UNDO = "DROP TRIGGER IF EXISTS knowledge_pilot_audit_guard ON knowledge_pilot_audit;"


class Migration(migrations.Migration):
    dependencies = [
        ('knowledge', '0002_stage14_article_moderation'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='ArticlePilotEnrollment',
            fields=[
                ('id', models.BigAutoField(
                    auto_created=True, primary_key=True, serialize=False, verbose_name='ID',
                )),
                ('consent_version', models.PositiveSmallIntegerField(default=1)),
                ('consented_at', models.DateTimeField()),
                ('revoked_at', models.DateTimeField(null=True, blank=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('worker', models.OneToOneField(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='knowledge_pilot_enrollment', to='accounts.workerprofile',
                )),
                ('accepted_by', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='knowledge_pilot_acceptances', to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'db_table': 'knowledge_pilot_enrollment',
                'default_permissions': ('view',),
            },
        ),
        migrations.CreateModel(
            name='ArticlePilotSelection',
            fields=[
                ('id', models.BigAutoField(
                    auto_created=True, primary_key=True, serialize=False, verbose_name='ID',
                )),
                ('approved_version', models.PositiveIntegerField()),
                ('selected_at', models.DateTimeField()),
                ('revoked_at', models.DateTimeField(null=True, blank=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('article', models.OneToOneField(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='pilot_selection', to='knowledge.expertarticle',
                )),
                ('selected_by', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='knowledge_pilot_selections', to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'db_table': 'knowledge_pilot_selection',
                'default_permissions': ('view',),
            },
        ),
        migrations.CreateModel(
            name='ArticlePilotAudit',
            fields=[
                ('id', models.BigAutoField(
                    auto_created=True, primary_key=True, serialize=False, verbose_name='ID',
                )),
                ('action', models.CharField(
                    max_length=12, choices=[
                        ('consented', 'Согласие получено'),
                        ('withdrawn', 'Согласие отозвано'),
                        ('selected', 'Статья допущена'),
                        ('deselected', 'Допуск отозван'),
                    ],
                )),
                ('content_version', models.PositiveIntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('article', models.ForeignKey(
                    null=True, blank=True, on_delete=django.db.models.deletion.PROTECT,
                    related_name='pilot_audit', to='knowledge.expertarticle',
                )),
                ('worker', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='knowledge_pilot_audit', to='accounts.workerprofile',
                )),
                ('actor', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='knowledge_pilot_audit', to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'db_table': 'knowledge_pilot_audit', 'ordering': ['created_at', 'pk'],
                'default_permissions': ('view',),
            },
        ),
        migrations.CreateModel(
            name='ArticlePilotDailyMetric',
            fields=[
                ('id', models.BigAutoField(
                    auto_created=True, primary_key=True, serialize=False, verbose_name='ID',
                )),
                ('day', models.DateField()),
                ('article_views', models.PositiveIntegerField(default=0)),
                ('profile_clicks', models.PositiveIntegerField(default=0)),
                ('order_clicks', models.PositiveIntegerField(default=0)),
                ('article', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='pilot_metrics', to='knowledge.expertarticle',
                )),
            ],
            options={
                'db_table': 'knowledge_pilot_daily_metric',
                'ordering': ['-day', 'article_id'],
                'default_permissions': ('view',),
            },
        ),
        migrations.CreateModel(
            name='ArticlePilotOrderAttribution',
            fields=[
                ('id', models.BigAutoField(
                    auto_created=True, primary_key=True, serialize=False, verbose_name='ID',
                )),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('article', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='pilot_published_orders', to='knowledge.expertarticle',
                )),
                ('order_digest', models.CharField(max_length=64, unique=True)),
            ],
            options={
                'db_table': 'knowledge_pilot_order_attribution',
                'default_permissions': ('view',),
            },
        ),
        migrations.AddConstraint(
            model_name='articlepilotselection',
            constraint=models.CheckConstraint(
                condition=models.Q(approved_version__gte=1),
                name='knowledge_pilot_version_positive_ck',
            ),
        ),
        migrations.AddConstraint(
            model_name='articlepilotaudit',
            constraint=models.CheckConstraint(
                condition=models.Q(
                    action__in=['consented', 'withdrawn', 'selected', 'deselected'],
                ),
                name='knowledge_pilot_audit_action_ck',
            ),
        ),
        migrations.AddConstraint(
            model_name='articlepilotdailymetric',
            constraint=models.UniqueConstraint(
                fields=['article', 'day'], name='knowledge_pilot_article_day_uq',
            ),
        ),
        migrations.RunSQL(GUARD, reverse_sql=UNDO),
    ]
