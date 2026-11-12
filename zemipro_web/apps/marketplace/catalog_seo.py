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
    # Only evaluate the potentially large translated-content gate when
    # indexing was explicitly enabled and this is an unfiltered public route.
    # Canonical is always the stable, query-free resource URL.
    has_query_filters = bool(request.GET)
    can_index = bool(
        settings.ZEMIPRO_CATALOG_INDEXING_ENABLED
        and not has_query_filters
        and (indexable() if callable(indexable) else indexable)
    )
    return {
        'catalog_localized': True,
        'seo_canonical': canonical,
        'seo_alternates': urls,
        'seo_noindex': not can_index,
    }


def complete_names(entity):
    """Do not treat whitespace or a Russian fallback as a translation."""
    return all(
        isinstance(name := getattr(entity, f'name_{lang}', None), str)
        and bool(name.strip())
        for lang in LANGUAGES
    )


def complete_content(entity, *, description=False):
    """Gate SEO without changing normal RU-fallback rendering.

    The explicitly enabled indexer requires all three authored names.
    When the entity's description appears on the page, its RU/EN/HE
    description must also be populated; for legacy Category, RU is stored
    in the original `description` column.
    """
    if not complete_names(entity):
        return False
    if not description:
        return True
    return all(
        isinstance(value := getattr(
            entity,
            'description' if lang == 'ru' and hasattr(entity, 'description')
            else f'description_{lang}',
            None,
        ), str) and bool(value.strip())
        for lang in LANGUAGES
    )


def complete_collection(entities, *, description=False):
    """Every visible item must be completely translated before indexing."""
    return all(complete_content(item, description=description) for item in entities)
