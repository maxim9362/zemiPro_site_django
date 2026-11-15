"""14.2 — private moderated article images, decisions and article reports."""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


SQL = """
CREATE TRIGGER knowledge_decision_guard BEFORE UPDATE OR DELETE
ON knowledge_expert_article_decision FOR EACH ROW
EXECUTE FUNCTION knowledge_block_revision_mutation();

ALTER TABLE knowledge_expert_article_image
ADD CONSTRAINT knowledge_image_bytes_match_ck
CHECK (octet_length(jpeg_data) = byte_size);

CREATE FUNCTION knowledge_report_identity_guard() RETURNS trigger AS $$
BEGIN
    IF NEW.article_id IS DISTINCT FROM OLD.article_id
       OR NEW.reporter_id IS DISTINCT FROM OLD.reporter_id
       OR NEW.reason IS DISTINCT FROM OLD.reason
       OR NEW.message IS DISTINCT FROM OLD.message
       OR NEW.created_at IS DISTINCT FROM OLD.created_at
    THEN
        RAISE EXCEPTION 'expert article report identity is immutable';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER knowledge_report_identity_guard
BEFORE UPDATE OR DELETE ON knowledge_expert_article_report
FOR EACH ROW EXECUTE FUNCTION knowledge_report_identity_guard();
"""

REVERSE = """
DROP TRIGGER IF EXISTS knowledge_report_identity_guard ON knowledge_expert_article_report;
DROP FUNCTION IF EXISTS knowledge_report_identity_guard();
ALTER TABLE knowledge_expert_article_image
DROP CONSTRAINT IF EXISTS knowledge_image_bytes_match_ck;
DROP TRIGGER IF EXISTS knowledge_decision_guard ON knowledge_expert_article_decision;
"""


class Migration(migrations.Migration):
    dependencies = [
        ('knowledge', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='expertarticle',
            name='rights_confirmed_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name='ExpertArticleImage',
            fields=[
                ('id', models.BigAutoField(
                    auto_created=True, primary_key=True, serialize=False,
                    verbose_name='ID',
                )),
                ('jpeg_data', models.BinaryField()),
                ('byte_size', models.PositiveIntegerField()),
                ('caption', models.CharField(
                    blank=True, default='', max_length=200,
                )),
                ('public_caption', models.CharField(
                    blank=True, default='', editable=False, max_length=200,
                )),
                ('approved_version', models.PositiveIntegerField(
                    blank=True, editable=False, null=True,
                )),
                ('rights_confirmed_at', models.DateTimeField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('article', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='images', to='knowledge.expertarticle',
                )),
                ('uploaded_by', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='expert_article_images', to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'db_table': 'knowledge_expert_article_image',
                'ordering': ['created_at', 'pk'],
            },
        ),
        migrations.CreateModel(
            name='ExpertArticleDecision',
            fields=[
                ('id', models.BigAutoField(
                    auto_created=True, primary_key=True, serialize=False,
                    verbose_name='ID',
                )),
                ('version', models.PositiveIntegerField()),
                ('kind', models.CharField(
                    choices=[
                        ('approve', 'Одобрить'), ('reject', 'Отклонить'),
                        ('remove', 'Снять с публикации'),
                    ], max_length=8,
                )),
                ('reason', models.CharField(
                    blank=True, default='', max_length=500,
                )),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('article', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='decisions', to='knowledge.expertarticle',
                )),
                ('moderator', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='expert_article_decisions', to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'db_table': 'knowledge_expert_article_decision',
                'ordering': ['created_at', 'pk'],
                'default_permissions': ('view',),
            },
        ),
        migrations.CreateModel(
            name='ExpertArticleReport',
            fields=[
                ('id', models.BigAutoField(
                    auto_created=True, primary_key=True, serialize=False,
                    verbose_name='ID',
                )),
                ('reason', models.CharField(
                    choices=[
                        ('spam', 'Спам'),
                        ('private', 'Персональные данные'),
                        ('dangerous', 'Небезопасный совет'),
                        ('copyright', 'Нарушение авторских прав'),
                        ('other', 'Другое'),
                    ], max_length=12,
                )),
                ('message', models.TextField()),
                ('status', models.CharField(
                    choices=[
                        ('pending', 'Ожидает проверки'),
                        ('dismissed', 'Отклонена'),
                        ('removed', 'Статья снята с публикации'),
                    ],
                    db_index=True, default='pending', max_length=10,
                )),
                ('handled_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('article', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='reports', to='knowledge.expertarticle',
                )),
                ('reporter', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='expert_article_reports', to=settings.AUTH_USER_MODEL,
                )),
                ('handled_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='handled_expert_article_reports',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'db_table': 'knowledge_expert_article_report',
                'ordering': ['created_at', 'pk'],
            },
        ),
        migrations.AddConstraint(
            model_name='expertarticleimage',
            constraint=models.CheckConstraint(
                condition=models.Q(
                    byte_size__gt=0, byte_size__lte=5 * 1024 * 1024,
                ),
                name='knowledge_image_max_size_ck',
            ),
        ),
        migrations.AddConstraint(
            model_name='expertarticledecision',
            constraint=models.UniqueConstraint(
                fields=['article', 'version'], name='knowledge_decision_version_uq',
            ),
        ),
        migrations.AddConstraint(
            model_name='expertarticledecision',
            constraint=models.CheckConstraint(
                condition=models.Q(kind__in=['approve', 'reject', 'remove']),
                name='knowledge_decision_kind_ck',
            ),
        ),
        migrations.AddConstraint(
            model_name='expertarticlereport',
            constraint=models.UniqueConstraint(
                fields=['article', 'reporter'], name='knowledge_report_once_uq',
            ),
        ),
        migrations.AddConstraint(
            model_name='expertarticlereport',
            constraint=models.CheckConstraint(
                condition=models.Q(status__in=['pending', 'dismissed', 'removed']),
                name='knowledge_report_status_ck',
            ),
        ),
        migrations.AddConstraint(
            model_name='expertarticlereport',
            constraint=models.CheckConstraint(
                condition=models.Q(reason__in=[
                    'spam', 'private', 'dangerous', 'copyright', 'other',
                ]),
                name='knowledge_report_reason_ck',
            ),
        ),
        migrations.RunSQL(SQL, reverse_sql=REVERSE),
    ]
