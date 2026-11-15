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

    rights_confirmed_at = models.DateTimeField(null=True, blank=True)
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


class ExpertArticleImage(models.Model):
    """Private, normalized JPEG. Media is never exposed through MEDIA_URL."""

    article = models.ForeignKey(
        ExpertArticle, on_delete=models.PROTECT, related_name='images',
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='expert_article_images',
    )
    jpeg_data = models.BinaryField()
    byte_size = models.PositiveIntegerField()
    caption = models.CharField(max_length=200, blank=True, default='')
    public_caption = models.CharField(
        max_length=200, blank=True, default='', editable=False,
    )
    approved_version = models.PositiveIntegerField(
        null=True, blank=True, editable=False,
    )
    rights_confirmed_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'knowledge_expert_article_image'
        ordering = ['created_at', 'pk']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(byte_size__gt=0, byte_size__lte=5 * 1024 * 1024),
                name='knowledge_image_max_size_ck',
            ),
        ]

    def __str__(self):
        return f'ExpertArticle #{self.article_id} image #{self.pk}'


class ExpertArticleDecision(models.Model):
    """Immutable moderation decision, including private rejection/removal reason."""

    class Kind(models.TextChoices):
        APPROVE = 'approve', 'Одобрить'
        REJECT = 'reject', 'Отклонить'
        REMOVE = 'remove', 'Снять с публикации'

    article = models.ForeignKey(
        ExpertArticle, on_delete=models.PROTECT, related_name='decisions',
    )
    moderator = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='expert_article_decisions',
    )
    version = models.PositiveIntegerField()
    kind = models.CharField(max_length=8, choices=Kind.choices)
    reason = models.CharField(max_length=500, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'knowledge_expert_article_decision'
        ordering = ['created_at', 'pk']
        default_permissions = ('view',)
        constraints = [
            models.UniqueConstraint(
                fields=['article', 'version'], name='knowledge_decision_version_uq',
            ),
            models.CheckConstraint(
                condition=models.Q(kind__in=['approve', 'reject', 'remove']),
                name='knowledge_decision_kind_ck',
            ),
        ]

    def __str__(self):
        return f'ExpertArticle #{self.article_id} decision #{self.pk}'


class ExpertArticleReport(models.Model):
    """Private reports are NOT verified reviews and do not create orders."""

    class Status(models.TextChoices):
        PENDING = 'pending', 'Ожидает проверки'
        DISMISSED = 'dismissed', 'Отклонена'
        REMOVED = 'removed', 'Статья снята с публикации'

    class Reason(models.TextChoices):
        SPAM = 'spam', 'Спам'
        PRIVATE = 'private', 'Персональные данные'
        DANGEROUS = 'dangerous', 'Небезопасный совет'
        COPYRIGHT = 'copyright', 'Нарушение авторских прав'
        OTHER = 'other', 'Другое'

    article = models.ForeignKey(
        ExpertArticle, on_delete=models.PROTECT, related_name='reports',
    )
    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='expert_article_reports',
    )
    reason = models.CharField(max_length=12, choices=Reason.choices)
    message = models.TextField()
    status = models.CharField(
        max_length=10, choices=Status.choices,
        default=Status.PENDING, db_index=True,
    )
    handled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        null=True, blank=True, related_name='handled_expert_article_reports',
    )
    handled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'knowledge_expert_article_report'
        ordering = ['created_at', 'pk']
        constraints = [
            models.UniqueConstraint(
                fields=['article', 'reporter'], name='knowledge_report_once_uq',
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=['pending', 'dismissed', 'removed']),
                name='knowledge_report_status_ck',
            ),
            models.CheckConstraint(
                condition=models.Q(reason__in=[
                    'spam', 'private', 'dangerous', 'copyright', 'other',
                ]),
                name='knowledge_report_reason_ck',
            ),
        ]

    def __str__(self):
        return f'ExpertArticle #{self.article_id} report #{self.pk}'


class ArticlePilotEnrollment(models.Model):
    """Explicit opt-in from a real Ashdod specialist; a moderator cannot opt in for them."""

    worker = models.OneToOneField(
        'accounts.WorkerProfile', on_delete=models.PROTECT,
        related_name='knowledge_pilot_enrollment',
    )
    accepted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='knowledge_pilot_acceptances',
    )
    consent_version = models.PositiveSmallIntegerField(default=1)
    consented_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'knowledge_pilot_enrollment'
        default_permissions = ('view',)

    def __str__(self):
        return f'Article pilot enrollment #{self.pk}'


class ArticlePilotSelection(models.Model):
    """An editor-reviewed, version-specific, limited public pilot whitelist."""

    article = models.OneToOneField(
        ExpertArticle, on_delete=models.PROTECT, related_name='pilot_selection',
    )
    approved_version = models.PositiveIntegerField()
    selected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='knowledge_pilot_selections',
    )
    selected_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'knowledge_pilot_selection'
        default_permissions = ('view',)
        constraints = [
            models.CheckConstraint(
                condition=models.Q(approved_version__gte=1),
                name='knowledge_pilot_version_positive_ck',
            ),
        ]

    def __str__(self):
        return f'Article pilot selection #{self.pk}'


class ArticlePilotAudit(models.Model):
    """Immutable pilot consent/selection audit; no raw text or visitor identity."""

    class Action(models.TextChoices):
        CONSENTED = 'consented', 'Согласие получено'
        WITHDRAWN = 'withdrawn', 'Согласие отозвано'
        SELECTED = 'selected', 'Статья допущена'
        DESELECTED = 'deselected', 'Допуск отозван'

    worker = models.ForeignKey(
        'accounts.WorkerProfile', on_delete=models.PROTECT,
        related_name='knowledge_pilot_audit',
    )
    article = models.ForeignKey(
        ExpertArticle, null=True, blank=True,
        on_delete=models.PROTECT, related_name='pilot_audit',
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='knowledge_pilot_audit',
    )
    action = models.CharField(max_length=12, choices=Action.choices)
    content_version = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'knowledge_pilot_audit'
        ordering = ['created_at', 'pk']
        default_permissions = ('view',)
        constraints = [
            models.CheckConstraint(
                condition=models.Q(action__in=[
                    'consented', 'withdrawn', 'selected', 'deselected',
                ]),
                name='knowledge_pilot_audit_action_ck',
            ),
        ]

    def __str__(self):
        return f'Article pilot audit #{self.pk}'


class ArticlePilotDailyMetric(models.Model):
    """Aggregate event totals. No IP, cookie, session, UA, path or visitor ID."""

    article = models.ForeignKey(
        ExpertArticle, on_delete=models.PROTECT, related_name='pilot_metrics',
    )
    day = models.DateField()
    article_views = models.PositiveIntegerField(default=0)
    profile_clicks = models.PositiveIntegerField(default=0)
    order_clicks = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'knowledge_pilot_daily_metric'
        ordering = ['-day', 'article_id']
        default_permissions = ('view',)
        constraints = [
            models.UniqueConstraint(
                fields=['article', 'day'], name='knowledge_pilot_article_day_uq',
            ),
        ]

    def __str__(self):
        return f'Article pilot aggregate #{self.article_id}'


class ArticlePilotOrderAttribution(models.Model):
    """One real, published order in a source-linked session (NOT a click)."""

    # HMAC of the verified published order ID; never persist the client/order FK.
    # This provides deduplication without keeping a relation to customer PII.
    order_digest = models.CharField(max_length=64, unique=True)
    article = models.ForeignKey(
        ExpertArticle, on_delete=models.PROTECT,
        related_name='pilot_published_orders',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'knowledge_pilot_order_attribution'
        default_permissions = ('view',)

    def __str__(self):
        return f'Article pilot attributed order #{self.pk}'
