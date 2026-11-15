"""Transactional Stage 09 editorial operations."""
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from .models import SeoContentPage, SeoContentRevision


EDITABLE_FIELDS = (
    'topic', 'title', 'meta_description', 'summary', 'body', 'source_facts',
    'quality_approved', 'status', 'reviewer_id', 'reviewed_at', 'published_at',
)


def _snapshot(page):
    snapshot = {}
    for field in EDITABLE_FIELDS:
        value = getattr(page, field)
        snapshot[field] = value.isoformat() if hasattr(value, 'isoformat') else value
    return snapshot


@transaction.atomic
def revise_content(*, page_id, actor, expected_version, changes):
    page = SeoContentPage.objects.select_for_update().get(pk=page_id)
    if not actor.is_staff and page.author_id != actor.pk:
        raise PermissionDenied
    if page.version != expected_version:
        raise ValidationError('Content version changed; reload before editing.')
    if page.status == SeoContentPage.Status.PUBLISHED and not actor.has_perm(
        'seo.publish_seo_content'
    ):
        raise PermissionDenied
    allowed = set(EDITABLE_FIELDS) - {
        'quality_approved', 'reviewer_id', 'reviewed_at', 'published_at',
    }
    unknown = set(changes) - allowed
    if unknown:
        raise ValidationError(f'Fields are not editable: {sorted(unknown)}')
    if 'status' in changes and changes['status'] not in {
        SeoContentPage.Status.BRIEF,
        SeoContentPage.Status.DRAFT,
        SeoContentPage.Status.REVIEW,
    }:
        raise ValidationError('Approval and publication require dedicated operations.')
    SeoContentRevision.objects.create(
        page=page, version=page.version, snapshot=_snapshot(page), created_by=actor,
    )
    for field, value in changes.items():
        setattr(page, field, value)
    page.version += 1
    page.save()
    return page


@transaction.atomic
def approve_content(*, page_id, actor, expected_version):
    if not actor.has_perm('seo.review_seo_content'):
        raise PermissionDenied
    page = SeoContentPage.objects.select_for_update().get(pk=page_id)
    if page.version != expected_version or page.status != SeoContentPage.Status.REVIEW:
        raise ValidationError('Content is not the expected review version.')
    if page.author_id == actor.pk:
        raise ValidationError('Author and approving reviewer must be different users.')
    SeoContentRevision.objects.create(
        page=page, version=page.version, snapshot=_snapshot(page), created_by=actor,
    )
    page.status = SeoContentPage.Status.APPROVED
    page.quality_approved = True
    page.reviewer = actor
    page.reviewed_at = timezone.now()
    page.version += 1
    page.save()
    return page


@transaction.atomic
def publish_content(*, page_id, actor, expected_version):
    if not actor.has_perm('seo.publish_seo_content'):
        raise PermissionDenied
    page = SeoContentPage.objects.select_for_update().get(pk=page_id)
    if page.version != expected_version or page.status != SeoContentPage.Status.APPROVED:
        raise ValidationError('Only the expected approved version may be published.')
    SeoContentRevision.objects.create(
        page=page, version=page.version, snapshot=_snapshot(page), created_by=actor,
    )
    page.status = SeoContentPage.Status.PUBLISHED
    page.published_at = timezone.now()
    page.version += 1
    page.save()
    return page


@transaction.atomic
def unpublish_content(*, page_id, actor, expected_version):
    if not actor.has_perm('seo.publish_seo_content'):
        raise PermissionDenied
    page = SeoContentPage.objects.select_for_update().get(pk=page_id)
    if page.version != expected_version or page.status != SeoContentPage.Status.PUBLISHED:
        raise ValidationError('Only the expected published version may be withdrawn.')
    SeoContentRevision.objects.create(
        page=page, version=page.version, snapshot=_snapshot(page), created_by=actor,
    )
    page.status = SeoContentPage.Status.APPROVED
    page.published_at = None
    page.version += 1
    page.save()
    return page
