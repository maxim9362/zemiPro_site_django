"""Available public geography for the owner's Ashdod-only first pilot.

The full 25-city catalogue remains in PostgreSQL for FK stability, test data
and later expansion. This is an application visibility/creation gate, not a
destructive migration or a replacement for City.is_active.
"""
from django.conf import settings

from .models import City


def public_city_slug():
    """A fixed default allowlist; None is used only for legacy multi-city QA."""
    return getattr(settings, 'ZEMIPRO_PILOT_CITY_SLUG', 'ashdod')


def get_public_cities():
    """Public city choices: only active Ashdod while the pilot gate is enabled."""
    queryset = City.objects.filter(is_active=True)
    slug = public_city_slug()
    return queryset.filter(slug=slug) if slug else queryset


def city_is_public(city):
    """Fail closed for missing/inactive/nonpilot city objects."""
    slug = public_city_slug()
    return bool(city is not None and city.is_active and (not slug or city.slug == slug))


def get_active_cities():
    """Historical helper: public, not entire internal technical registry."""
    return get_public_cities().order_by('name_ru')
