"""SEO metadata ONLY for separate language-prefixed catalog routes.

No implicit legacy 301/308, sitemap or robots.txt changes. Public URL migration
requires independently audited production URL inventory in Stage 08.
"""
from django.conf import settings
from django.urls import reverse
from django.utils.translation import override


LANGUAGES = ('ru', 'en', 'he')


def catalog_context(request, route_name, *, kwargs=None, indexable=False):
    match = getattr(request, 'resolver_match', None)
    if match is None or match.namespace != 'catalog_i18n':
        return {'catalog_localized': False}

    kwargs = kwargs or {}
    urls = []
    for language in LANGUAGES:
        with override(language):
            pathname = reverse(f'catalog_i18n:{route_name}', kwargs=kwargs)
        urls.append({
            'language': language,
            'url': request.build_absolute_uri(pathname),
        })
    current = getattr(request, 'LANGUAGE_CODE', settings.LANGUAGE_CODE)
    canonical = next(
        (entry['url'] for entry in urls if entry['language'] == current),
        request.build_absolute_uri(),
    )
    # Prevent indexing of provisional or empty pages and paginated/filtered
    # variants. Canonical is always the stable, query-free resource URL.
    has_query_filters = bool(request.GET)
    can_index = (
        settings.ZEMIPRO_CATALOG_INDEXING_ENABLED and indexable
        and not has_query_filters
    )
    return {
        'catalog_localized': True,
        'seo_canonical': canonical,
        'seo_alternates': urls,
        'seo_noindex': not can_index,
    }


def complete_names(entity):
    """No indexed translated aliases when human review/name is missing."""
    return all(getattr(entity, f'name_{lang}', '') for lang in LANGUAGES)
