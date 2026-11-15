"""Stage 09 SEO registry and editorial landing content."""
import hashlib
import re

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


LOCAL_PATH_RE = re.compile(r"^/(?!/)[A-Za-z0-9._~!$&'()*+,;=:@%/-]*/$")


def validate_local_path(value):
    if not LOCAL_PATH_RE.fullmatch(value or '') or '?' in value or '#' in value:
        raise ValidationError('Use an absolute local path ending in /, without query or fragment.')


class SeoLegacyUrl(models.Model):
    """One exact legacy path and its evidence-backed decision."""

    class Decision(models.TextChoices):
        REVIEW = 'review', 'Review'
        KEEP = 'keep', 'Keep'
        REDIRECT = 'redirect', 'Redirect'
        NOT_FOUND = '404', '404 Not Found'
        GONE = '410', '410 Gone'

    class RedirectStatus(models.IntegerChoices):
        MOVED_PERMANENTLY = 301, '301'
        PERMANENT_REDIRECT = 308, '308'

    path = models.CharField(max_length=500, unique=True, validators=[validate_local_path])
    page_type = models.CharField(max_length=40, blank=True, default='')
    decision = models.CharField(max_length=10, choices=Decision.choices, default=Decision.REVIEW)
    target_path = models.CharField(
        max_length=500, blank=True, default='', validators=[validate_local_path],
    )
    redirect_status = models.PositiveSmallIntegerField(
        choices=RedirectStatus.choices, default=RedirectStatus.MOVED_PERMANENTLY,
    )
    evidence_source = models.TextField(blank=True, default='')
    is_active = models.BooleanField(default=False, db_index=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name='approved_legacy_urls', limit_choices_to={'is_staff': True},
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['path']
        permissions = [('approve_legacy_url', 'Can approve legacy URL decisions')]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(is_active=False)
                    | (
                        ~models.Q(decision='review')
                        & models.Q(approved_by__isnull=False)
                        & models.Q(approved_at__isnull=False)
                        & ~models.Q(evidence_source='')
                    )
                ),
                name='seo_active_legacy_is_approved',
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(decision='redirect', target_path__gt='')
                    | (~models.Q(decision='redirect') & models.Q(target_path=''))
                ),
                name='seo_redirect_has_target_only',
            ),
        ]

    def clean(self):
        super().clean()
        errors = {}
        if self.target_path:
            try:
                validate_local_path(self.target_path)
            except ValidationError as exc:
                errors['target_path'] = exc.messages
        if self.decision == self.Decision.REDIRECT:
            if not self.target_path:
                errors['target_path'] = 'A redirect requires an exact target path.'
            elif self.target_path == self.path:
                errors['target_path'] = 'A legacy URL cannot redirect to itself.'
        elif self.target_path:
            errors['target_path'] = 'Only redirect decisions may have a target path.'
        if self.is_active:
            if self.decision == self.Decision.REVIEW:
                errors['is_active'] = 'A review-only decision cannot be activated.'
            if not self.approved_by_id or not self.approved_at:
                errors['is_active'] = 'Activation requires staff approval and timestamp.'
            elif not self.approved_by.is_staff:
                errors['approved_by'] = 'Only staff may approve a legacy URL decision.'
            if not self.evidence_source.strip():
                errors['evidence_source'] = 'Activation requires auditable evidence.'
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.path} [{self.decision}]'


class SeoContentPage(models.Model):
    """Reviewed copy attached to a real catalog landing, not an article system."""

    class PageType(models.TextChoices):
        SECTION = 'section', 'Section'
        CATEGORY = 'category', 'Category'
        SERVICE = 'service', 'Service'
        CITY = 'city', 'City'
        SERVICE_CITY = 'service_city', 'Service in city'

    class Status(models.TextChoices):
        BRIEF = 'brief', 'Brief'
        DRAFT = 'draft', 'Draft'
        REVIEW = 'review', 'Review'
        APPROVED = 'approved', 'Approved'
        PUBLISHED = 'published', 'Published'

    class Language(models.TextChoices):
        RU = 'ru', 'Русский'
        EN = 'en', 'English'
        HE = 'he', 'עברית'

    page_type = models.CharField(max_length=20, choices=PageType.choices)
    language = models.CharField(max_length=2, choices=Language.choices)
    section = models.ForeignKey(
        'marketplace.ServiceSection', on_delete=models.PROTECT, null=True, blank=True,
        related_name='seo_content_pages',
    )
    category = models.ForeignKey(
        'marketplace.Category', on_delete=models.PROTECT, null=True, blank=True,
        related_name='seo_content_pages',
    )
    service = models.ForeignKey(
        'marketplace.Subcategory', on_delete=models.PROTECT, null=True, blank=True,
        related_name='seo_content_pages',
    )
    city = models.ForeignKey(
        'locations.City', on_delete=models.PROTECT, null=True, blank=True,
        related_name='seo_content_pages',
    )
    topic = models.CharField(max_length=180)
    title = models.CharField(max_length=180)
    meta_description = models.CharField(max_length=320)
    summary = models.TextField()
    body = models.TextField()
    source_facts = models.TextField(
        help_text='Human-readable sources; never credentials or personal data.',
    )
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.BRIEF, db_index=True,
    )
    quality_approved = models.BooleanField(default=False)
    content_fingerprint = models.CharField(max_length=64, editable=False, db_index=True)
    version = models.PositiveIntegerField(default=1, editable=False)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='authored_seo_pages',
    )
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name='reviewed_seo_pages', limit_choices_to={'is_staff': True},
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['page_type', 'language', 'pk']
        constraints = [
            models.UniqueConstraint(
                fields=['page_type', 'language', 'section', 'category', 'service', 'city'],
                name='seo_unique_catalog_landing', nulls_distinct=False,
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(status='published', published_at__isnull=False)
                    | (~models.Q(status='published') & models.Q(published_at__isnull=True))
                ),
                name='seo_published_has_timestamp',
            ),
        ]
        permissions = [
            ('review_seo_content', 'Can review SEO content'),
            ('publish_seo_content', 'Can publish SEO content'),
        ]

    def clean(self):
        super().clean()
        required = {
            self.PageType.SECTION: {'section'},
            self.PageType.CATEGORY: {'category'},
            self.PageType.SERVICE: {'service'},
            self.PageType.CITY: {'city'},
            self.PageType.SERVICE_CITY: {'service', 'city'},
        }.get(self.page_type, set())
        present = {
            name for name in ('section', 'category', 'service', 'city')
            if getattr(self, f'{name}_id') is not None
        }
        errors = {}
        if present != required:
            errors['page_type'] = f'Expected catalog relations: {sorted(required)}.'
        pilot_slug = settings.ZEMIPRO_PILOT_CITY_SLUG
        if self.city_id and pilot_slug and self.city and self.city.slug != pilot_slug:
            errors['city'] = 'Only the owner-approved Ashdod pilot may be public.'
        fingerprint = self.build_fingerprint()
        if type(self).objects.filter(
            language=self.language, content_fingerprint=fingerprint,
        ).exclude(pk=self.pk).exists():
            errors['body'] = 'Duplicate content exists for this language.'
        if self.status in {self.Status.APPROVED, self.Status.PUBLISHED}:
            if len(' '.join(self.body.split())) < 160:
                errors['body'] = 'Approved landing content must contain at least 160 characters.'
            if len(' '.join(self.summary.split())) < 40:
                errors['summary'] = 'Approved landing summary must contain at least 40 characters.'
            if len(' '.join(self.meta_description.split())) < 50:
                errors['meta_description'] = 'Approved meta description must contain at least 50 characters.'
            if not self.quality_approved:
                errors['quality_approved'] = 'Approved content requires quality approval.'
            if not self.source_facts.strip():
                errors['source_facts'] = 'Approved content requires fact sources.'
            if not self.reviewer_id or not self.reviewed_at:
                errors['reviewer'] = 'Approved content requires staff review.'
            elif not self.reviewer.is_staff:
                errors['reviewer'] = 'Reviewer must be staff.'
            elif self.reviewer_id == self.author_id:
                errors['reviewer'] = 'Author and approving reviewer must be different users.'
        if self.status == self.Status.PUBLISHED and not self.published_at:
            errors['published_at'] = 'Published content requires a timestamp.'
        if self.status != self.Status.PUBLISHED and self.published_at:
            errors['published_at'] = 'Only published content may have a timestamp.'
        if errors:
            raise ValidationError(errors)

    def build_fingerprint(self):
        normalized = ' '.join(f'{self.title} {self.summary} {self.body}'.split()).casefold()
        return hashlib.sha256(normalized.encode('utf-8')).hexdigest()

    def save(self, *args, **kwargs):
        self.content_fingerprint = self.build_fingerprint()
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.page_type}/{self.language}: {self.title}'


class SeoContentRevision(models.Model):
    """Append-only snapshot of an editorial landing page."""

    page = models.ForeignKey(SeoContentPage, on_delete=models.PROTECT, related_name='revisions')
    version = models.PositiveIntegerField()
    snapshot = models.JSONField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='seo_content_revisions',
    )
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        ordering = ['page_id', 'version']
        constraints = [
            models.UniqueConstraint(
                fields=['page', 'version'], name='seo_unique_page_revision',
            ),
        ]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError('SEO content revisions are immutable.')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('SEO content revisions are immutable.')

    def __str__(self):
        return f'{self.page_id} v{self.version}'
