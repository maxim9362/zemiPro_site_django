"""Stage 14.1: expert articles are NOT orders, questionnaires or verified reviews.

Raw user content is private. Public snapshots are empty until the separately
permissioned, moderated publishing service is implemented in Stage 14.2.
No public views, admin writes or external media endpoints are installed here.
"""
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class ExpertArticle(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'draft', 'Черновик'
        PENDING_REVIEW = 'pending_review', 'На модерации'
        PUBLISHED = 'published', 'Опубликована'
        REJECTED = 'rejected', 'Отклонена'
        ARCHIVED = 'archived', 'Архив'

    class TranslationKind(models.TextChoices):
        ORIGINAL = 'original', 'Оригинал автора'
        HUMAN = 'human', 'Проверенный перевод'
        MACHINE = 'machine', 'Машинный перевод'

    class Language(models.TextChoices):
        RU = 'ru', 'Русский'
        EN = 'en', 'English'
        HE = 'he', 'עברית'

    author = models.ForeignKey(
        'accounts.WorkerProfile', on_delete=models.PROTECT, related_name='expert_articles',
    )
    category = models.ForeignKey(
        'marketplace.Category', on_delete=models.PROTECT, related_name='expert_articles',
    )
    subcategory = models.ForeignKey(
        'marketplace.Subcategory', on_delete=models.PROTECT,
        null=True, blank=True, related_name='expert_articles',
    )
    slug = models.SlugField(max_length=160, allow_unicode=True)
    language = models.CharField(max_length=2, choices=Language.choices)
    translation_group = models.UUIDField(default=uuid.uuid4, editable=False)
    translation_kind = models.CharField(
        max_length=10, choices=TranslationKind.choices,
        default=TranslationKind.ORIGINAL,
    )
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.DRAFT, db_index=True,
    )

    # Untrusted author drafts: these fields must NEVER be returned in public views.
    title = models.CharField(max_length=180)
    excerpt = models.CharField(max_length=400, blank=True, default='')
    body = models.TextField()
    content_version = models.PositiveIntegerField(default=0, editable=False)

    # Reviewed, contact-free snapshots: empty/fail-closed by default.
    public_title = models.CharField(max_length=180, blank=True, default='', editable=False)
    public_excerpt = models.CharField(max_length=400, blank=True, default='', editable=False)
    public_body = models.TextField(blank=True, default='', editable=False)
    public_content_safe = models.BooleanField(default=False, editable=False)
    approved_version = models.PositiveIntegerField(
        null=True, blank=True, editable=False,
    )

    moderated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name='moderated_expert_articles',
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    moderated_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'knowledge_expert_article'
        ordering = ['-created_at', '-pk']
        permissions = [('moderate_expert_articles', 'Can moderate expert articles')]
        indexes = [
            models.Index(
                fields=['status', 'language', '-published_at'],
                name='knowledge_status_lang_idx',
            ),
            models.Index(fields=['category', 'status'], name='knowledge_category_idx'),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=[
                    'draft', 'pending_review', 'published', 'rejected', 'archived',
                ]),
                name='knowledge_article_status_ck',
            ),
            models.CheckConstraint(
                condition=models.Q(language__in=['ru', 'en', 'he']),
                name='knowledge_article_language_ck',
            ),
            models.CheckConstraint(
                condition=models.Q(translation_kind__in=['original', 'human', 'machine']),
                name='knowledge_article_translation_ck',
            ),
            models.UniqueConstraint(
                fields=['slug', 'language'], name='knowledge_article_slug_lang_uq',
            ),
            models.UniqueConstraint(
                fields=['translation_group', 'language'], name='knowledge_group_lang_uq',
            ),
            models.CheckConstraint(
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
        ]

    def clean(self):
        super().clean()
        if self.subcategory_id and self.category_id:
            if not self.subcategory.category_id == self.category_id:
                raise ValidationError({
                    'subcategory': 'Подкатегория не относится к выбранной категории.',
                })

    def __str__(self):
        # Do not expose potentially private author text in Django admin/logs.
        return f'ExpertArticle #{self.pk or "new"} ({self.status})'


class ExpertArticleRevision(models.Model):
    """Immutable source/audit record. Mutations and deletes are blocked by PostgreSQL."""

    class Action(models.TextChoices):
        CREATED = 'created', 'Создано'
        EDITED = 'edited', 'Изменено'
        SUBMITTED = 'submitted', 'Отправлено на проверку'
        APPROVED = 'approved', 'Одобрено'
        REJECTED = 'rejected', 'Отклонено'
        ARCHIVED = 'archived', 'Архивировано'

    article = models.ForeignKey(
        ExpertArticle, on_delete=models.PROTECT, related_name='revisions',
    )
    version = models.PositiveIntegerField()
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='expert_article_revisions',
    )
    action = models.CharField(max_length=16, choices=Action.choices)
    status_snapshot = models.CharField(max_length=16, choices=ExpertArticle.Status.choices)
    title = models.CharField(max_length=180)
    excerpt = models.CharField(max_length=400, blank=True, default='')
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'knowledge_expert_article_revision'
        ordering = ['article_id', 'version']
        default_permissions = ('view',)
        constraints = [
            models.UniqueConstraint(
                fields=['article', 'version'], name='knowledge_article_revision_uq',
            ),
            models.CheckConstraint(
                condition=models.Q(version__gte=1), name='knowledge_revision_version_ck',
            ),
            models.CheckConstraint(
                condition=models.Q(status_snapshot__in=[
                    'draft', 'pending_review', 'published', 'rejected', 'archived',
                ]),
                name='knowledge_revision_status_ck',
            ),
        ]

    def __str__(self):
        return f'ExpertArticle #{self.article_id} revision {self.version}'
