"""Read-only SEO catalog projections backed by existing marketplace data."""
from django.db.models import Avg, Count
from django.utils.translation import get_language

from apps.accounts.client_favorites import public_worker_queryset
from apps.locations.services import city_is_public, get_public_cities
from apps.marketplace.models import Category, ServiceSection, Subcategory
from apps.marketplace.services import workers_serving_city

from .models import SeoContentPage


def active_sections():
    return ServiceSection.objects.filter(is_active=True).order_by('sort_order', 'pk')


def active_categories():
    return Category.objects.filter(is_active=True).filter(
        section__isnull=True,
    ) | Category.objects.filter(is_active=True, section__is_active=True)


def active_services():
    return Subcategory.objects.filter(
        is_active=True, category__is_active=True,
    ).filter(
        category__section__isnull=True,
    ) | Subcategory.objects.filter(
        is_active=True, category__is_active=True, category__section__is_active=True,
    )


def service_workers(service, city):
    """Actual, privacy-safe, published workers declaring this exact service."""
    if not city_is_public(city):
        return public_worker_queryset().none()
    workers = public_worker_queryset().filter(services=service).annotate(
        avg_rating=Avg('user__received_ratings__rating'),
        review_count=Count('user__received_ratings', distinct=True),
    )
    return workers_serving_city(
        workers, city, category=service.category, service=service,
    ).distinct().order_by('-review_count', 'pk')


def public_pilot_city():
    return get_public_cities().order_by('pk').first()


def published_landing(*, page_type, section=None, category=None, service=None, city=None,
                      language=None):
    code = (language or get_language() or 'ru').split('-')[0]
    return SeoContentPage.objects.filter(
        page_type=page_type, language=code, section=section, category=category,
        service=service, city=city, status=SeoContentPage.Status.PUBLISHED,
        quality_approved=True, published_at__isnull=False,
    ).first()
