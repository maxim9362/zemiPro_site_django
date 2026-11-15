"""Stage 14.1 — isolated article schema. Never migrate a production DB from this commit."""
import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


IMMUTABLE_SQL = """
CREATE FUNCTION knowledge_block_revision_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'expert article revisions are immutable';
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER knowledge_revision_guard BEFORE UPDATE OR DELETE
    ON knowledge_expert_article_revision FOR EACH ROW
    EXECUTE FUNCTION knowledge_block_revision_mutation();
"""

IMMUTABLE_REVERSE_SQL = """
DROP TRIGGER IF EXISTS knowledge_revision_guard ON knowledge_expert_article_revision;
DROP FUNCTION IF EXISTS knowledge_block_revision_mutation();
"""


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('accounts', '0022_user_safe_runtime_manager'),
        ('marketplace', '0023_stage07_chat_integrity'),
    ]

    operations = [
        migrations.CreateModel(
            name='ExpertArticle',
            fields=[
                ('id', models.BigAutoField(
                    auto_created=True, primary_key=True, serialize=False, verbose_name='ID',
                )),
                ('slug', models.SlugField(allow_unicode=True, max_length=160)),
                ('language', models.CharField(
                    choices=[('ru', 'Русский'), ('en', 'English'), ('he', 'עברית')],
                    max_length=2,
                )),
                ('translation_group', models.UUIDField(
                    default=uuid.uuid4, editable=False,
                )),
                ('translation_kind', models.CharField(
                    choices=[
                        ('original', 'Оригинал автора'),
                        ('human', 'Проверенный перевод'),
                        ('machine', 'Машинный перевод'),
                    ], default='original', max_length=10,
                )),
                ('status', models.CharField(
                    choices=[
                        ('draft', 'Черновик'),
                        ('pending_review', 'На модерации'),
                        ('published', 'Опубликована'),
                        ('rejected', 'Отклонена'),
                        ('archived', 'Архив'),
                    ], db_index=True, default='draft', max_length=16,
                )),
                ('title', models.CharField(max_length=180)),
                ('excerpt', models.CharField(blank=True, default='', max_length=400)),
                ('body', models.TextField()),
                ('content_version', models.PositiveIntegerField(
                    default=0, editable=False,
                )),
                ('public_title', models.CharField(
                    blank=True, default='', editable=False, max_length=180,
                )),
                ('public_excerpt', models.CharField(
                    blank=True, default='', editable=False, max_length=400,
                )),
                ('public_body', models.TextField(blank=True, default='', editable=False)),
                ('public_content_safe', models.BooleanField(
                    default=False, editable=False,
                )),
                ('approved_version', models.PositiveIntegerField(
                    blank=True, editable=False, null=True,
                )),
                ('submitted_at', models.DateTimeField(blank=True, null=True)),
                ('moderated_at', models.DateTimeField(blank=True, null=True)),
                ('published_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('author', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='expert_articles', to='accounts.workerprofile',
                )),
                ('category', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='expert_articles', to='marketplace.category',
                )),
                ('subcategory', models.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                    related_name='expert_articles', to='marketplace.subcategory',
                )),
                ('moderated_by', models.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                    related_name='moderated_expert_articles', to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'db_table': 'knowledge_expert_article',
                'ordering': ['-created_at', '-pk'],
                'permissions': [
                    ('moderate_expert_articles', 'Can moderate expert articles'),
                ],
            },
        ),
        migrations.CreateModel(
            name='ExpertArticleRevision',
            fields=[
                ('id', models.BigAutoField(
                    auto_created=True, primary_key=True, serialize=False, verbose_name='ID',
                )),
                ('version', models.PositiveIntegerField()),
                ('action', models.CharField(
                    choices=[
                        ('created', 'Создано'),
                        ('edited', 'Изменено'),
                        ('submitted', 'Отправлено на проверку'),
                        ('approved', 'Одобрено'),
                        ('rejected', 'Отклонено'),
                        ('archived', 'Архивировано'),
                    ], max_length=16,
                )),
                ('status_snapshot', models.CharField(
                    choices=[
                        ('draft', 'Черновик'),
                        ('pending_review', 'На модерации'),
                        ('published', 'Опубликована'),
                        ('rejected', 'Отклонена'),
                        ('archived', 'Архив'),
                    ], max_length=16,
                )),
                ('title', models.CharField(max_length=180)),
                ('excerpt', models.CharField(blank=True, default='', max_length=400)),
                ('body', models.TextField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('article', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='revisions', to='knowledge.expertarticle',
                )),
                ('actor', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='expert_article_revisions', to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'db_table': 'knowledge_expert_article_revision',
                'ordering': ['article_id', 'version'],
                'default_permissions': ('view',),
            },
        ),
        migrations.AddIndex(
            model_name='expertarticle',
            index=models.Index(
                fields=['status', 'language', '-published_at'],
                name='knowledge_status_lang_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='expertarticle',
            index=models.Index(
                fields=['category', 'status'], name='knowledge_category_idx',
            ),
        ),
        migrations.AddConstraint(
            model_name='expertarticle',
            constraint=models.CheckConstraint(
                condition=models.Q(status__in=[
                    'draft', 'pending_review', 'published', 'rejected', 'archived',
                ]),
                name='knowledge_article_status_ck',
            ),
        ),
        migrations.AddConstraint(
            model_name='expertarticle',
            constraint=models.CheckConstraint(
                condition=models.Q(language__in=['ru', 'en', 'he']),
                name='knowledge_article_language_ck',
            ),
        ),
        migrations.AddConstraint(
            model_name='expertarticle',
            constraint=models.CheckConstraint(
                condition=models.Q(translation_kind__in=['original', 'human', 'machine']),
                name='knowledge_article_translation_ck',
            ),
        ),
        migrations.AddConstraint(
            model_name='expertarticle',
            constraint=models.UniqueConstraint(
                fields=['slug', 'language'], name='knowledge_article_slug_lang_uq',
            ),
        ),
        migrations.AddConstraint(
            model_name='expertarticle',
            constraint=models.UniqueConstraint(
                fields=['translation_group', 'language'], name='knowledge_group_lang_uq',
            ),
        ),
        migrations.AddConstraint(
            model_name='expertarticle',
            constraint=models.CheckConstraint(
                condition=(
                    ~models.Q(status='published') |
                    (
                        models.Q(public_content_safe=True) &
                        ~models.Q(public_title='') &
                        ~models.Q(public_body='') &
                        models.Q(approved_version__isnull=False) &
                        models.Q(published_at__isnull=False)
                    )
                ),
                name='knowledge_publish_requires_review_ck',
            ),
        ),
        migrations.AddConstraint(
            model_name='expertarticlerevision',
            constraint=models.UniqueConstraint(
                fields=['article', 'version'], name='knowledge_article_revision_uq',
            ),
        ),
        migrations.AddConstraint(
            model_name='expertarticlerevision',
            constraint=models.CheckConstraint(
                condition=models.Q(version__gte=1), name='knowledge_revision_version_ck',
            ),
        ),
        migrations.AddConstraint(
            model_name='expertarticlerevision',
            constraint=models.CheckConstraint(
                condition=models.Q(status_snapshot__in=[
                    'draft', 'pending_review', 'published', 'rejected', 'archived',
                ]),
                name='knowledge_revision_status_ck',
            ),
        ),
        migrations.RunSQL(IMMUTABLE_SQL, reverse_sql=IMMUTABLE_REVERSE_SQL),
    ]
