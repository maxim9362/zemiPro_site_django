"""Synthetic Django test factories; do not use outside isolated test databases."""

from django.contrib.auth import get_user_model

from apps.accounts.models import WorkerProfile
from apps.locations.models import City
from apps.marketplace.models import Category, Order


def make_user(username, **kwargs):
    """Create a user with unusable password; force_login for HTTP tests."""
    return get_user_model().objects.create_user(username=username, **kwargs)


def make_city(slug='qa-ashdod', **kwargs):
    return City.objects.create(
        slug=slug,
        name_ru=kwargs.pop('name_ru', 'Тестовый город'),
        **kwargs,
    )


def make_category(slug='qa-cleaning', **kwargs):
    return Category.objects.create(
        slug=slug,
        name_ru=kwargs.pop('name_ru', 'Тестовая услуга'),
        **kwargs,
    )


def make_worker_profile(user, *, city, category):
    profile = WorkerProfile.objects.create(
        user=user, city=city, display_name=user.username,
        description='Synthetic published profile for isolated test fixtures.',
        pricing_details='Negotiable', spoken_languages=['ru'], is_published=True,
    )
    profile.skills.add(category)
    return profile


def make_order(*, client, category, city, **kwargs):
    return Order.objects.create(
        client=client,
        category=category,
        city=city,
        address=kwargs.pop('address', 'Synthetic address, no real residents'),
        description=kwargs.pop(
            'description', 'Synthetic service request for CI permissions checks.'
        ),
        **kwargs,
    )
