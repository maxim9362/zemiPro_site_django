"""Approval and validation for exact, evidence-backed legacy decisions."""
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.urls import Resolver404, resolve
from django.utils import timezone

from apps.accounts.client_favorites import public_worker_queryset
from apps.locations.models import City
from apps.locations.services import city_is_public
from apps.marketplace.models import Category, ServiceSection, Subcategory

from .catalog import public_pilot_city, published_landing, service_workers
from .models import SeoContentPage, SeoLegacyUrl


def _active_category(slug):
    return Category.objects.filter(slug=slug, is_active=True).filter(
        section__isnull=True,
    ).first() or Category.objects.filter(
        slug=slug, is_active=True, section__is_active=True,
    ).first()


def target_is_public(path):
    """Validate a destination against public ORM state, not URL shape alone."""
    try:
        match = resolve(path)
    except Resolver404:
        return False
    name, kwargs = match.view_name, match.kwargs
    if name == 'marketplace:home':
        return True
    if name == 'catalog_i18n:category_detail':
        category = _active_category(kwargs['slug'])
        return bool(category and public_worker_queryset().filter(skills=category).exists())
    if name == 'catalog_i18n:section_detail':
        section = ServiceSection.objects.filter(
            slug=kwargs['slug'], is_active=True,
        ).first()
        return bool(section and public_worker_queryset().filter(
            skills__section=section,
        ).exists())
    if name in {'catalog_i18n:service_detail', 'catalog_i18n:service_city_detail'}:
        category = _active_category(kwargs['category_slug'])
        service = Subcategory.objects.filter(
            category=category, slug=kwargs['service_slug'], is_active=True,
        ).select_related('category', 'category__section').first()
        if service is None:
            return False
        city = (
            City.objects.filter(slug=kwargs['city_slug']).first()
            if 'city_slug' in kwargs else public_pilot_city()
        )
        if not city_is_public(city) or not service_workers(service, city).exists():
            return False
        page_type = (
            SeoContentPage.PageType.SERVICE_CITY
            if 'city_slug' in kwargs else SeoContentPage.PageType.SERVICE
        )
        language = path.split('/', 2)[1]
        return published_landing(
            page_type=page_type, service=service,
            city=city if page_type == SeoContentPage.PageType.SERVICE_CITY else None,
            language=language,
        ) is not None
    if name == 'catalog_i18n:city_detail':
        city = City.objects.filter(slug=kwargs['slug']).first()
        return bool(
            city_is_public(city)
            and public_worker_queryset().filter(city=city).exists()
        )
    if name == 'catalog_i18n:worker_public_profile':
        return public_worker_queryset().filter(
            pk=kwargs['pk'], public_description_snapshot__gt='',
        ).exists()
    return False


def redirect_target_is_safe(row):
    if row.decision != SeoLegacyUrl.Decision.REDIRECT:
        return True
    if SeoLegacyUrl.objects.filter(
        path=row.target_path, is_active=True,
    ).exclude(pk=row.pk).exists():
        return False
    return target_is_public(row.target_path)


@transaction.atomic
def activate_legacy_url(*, row_id, actor):
    if not actor.is_staff or not actor.has_perm('seo.approve_legacy_url'):
        raise PermissionDenied
    row = SeoLegacyUrl.objects.select_for_update().get(pk=row_id)
    if row.decision == SeoLegacyUrl.Decision.REVIEW:
        raise ValidationError('A review-only decision cannot be activated.')
    if not row.evidence_source.strip():
        raise ValidationError('Evidence is required before activation.')
    if row.decision == SeoLegacyUrl.Decision.REDIRECT and not redirect_target_is_safe(row):
        raise ValidationError('Redirect target is not a useful public Django page.')
    if row.decision == SeoLegacyUrl.Decision.KEEP:
        try:
            match = resolve(row.path)
        except Resolver404 as exc:
            raise ValidationError('KEEP requires an existing Django route.') from exc
        if match.view_name == 'seo_legacy_url':
            raise ValidationError('KEEP cannot be served by the legacy fallback route.')
    row.approved_by = actor
    row.approved_at = timezone.now()
    row.is_active = True
    row.save()
    return row


@transaction.atomic
def deactivate_legacy_url(*, row_id, actor):
    if not actor.is_staff or not actor.has_perm('seo.approve_legacy_url'):
        raise PermissionDenied
    row = SeoLegacyUrl.objects.select_for_update().get(pk=row_id)
    row.is_active = False
    row.save(update_fields=['is_active', 'updated_at'])
    return row
