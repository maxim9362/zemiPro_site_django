"""SEO-ready *metadata* only. No indexable pages/sitemaps/legacy redirects yet.

Stage 09 retains control of sitemap, robots and indexing. Our canonical and
hreflang always represent real, separately approved article language variants.
"""
import json

from django.urls import reverse
from django.utils.translation import override

from .models import ExpertArticle
from .public_content import public_articles


LANGUAGES = ('ru', 'en', 'he')


def public_path(article):
    """Generate the language-specific *relative* URL, not the UI's current locale."""
    with override(article.language):
        return reverse('knowledge_public:article_detail', kwargs={'slug': article.slug})


def public_url(request, article):
    return request.build_absolute_uri(public_path(article))


def list_seo(request):
    with override(request.LANGUAGE_CODE):
        pathname = reverse('knowledge_public:article_list')
    # A locale index may be useful later, but is explicitly NOINDEX at Stage 14.3.
    return {
        'seo_noindex': True,
        'seo_canonical': request.build_absolute_uri(pathname),
        'seo_alternates': [],
    }


def article_seo(request, article):
    variants = list(public_articles().filter(
        translation_group=article.translation_group,
        translation_kind__in=(
            ExpertArticle.TranslationKind.ORIGINAL,
            ExpertArticle.TranslationKind.HUMAN,
        ),
    ).order_by('language', 'pk'))
    original = next((
        item for item in variants
        if item.translation_kind == ExpertArticle.TranslationKind.ORIGINAL
    ), None)
    machine = article.translation_kind == ExpertArticle.TranslationKind.MACHINE
    canonical_article = original if machine and original else article
    canonical = public_url(request, canonical_article)
    # Do not attribute unverified machine translations to their author in SEO.
    alternates = [
        {'language': item.language, 'url': public_url(request, item)}
        for item in variants
    ] if not machine else []

    schema_json = ''
    if not machine:
        schema = {
            '@context': 'https://schema.org',
            '@type': 'Article',
            'headline': article.public_title,
            'description': article.public_excerpt or article.public_title,
            'inLanguage': article.language,
            'datePublished': article.published_at.isoformat(),
            'dateModified': article.moderated_at.isoformat()
            if article.moderated_at else article.published_at.isoformat(),
            'mainEntityOfPage': canonical,
            'isAccessibleForFree': True,
            'author': {
                '@type': (
                    'Organization' if article.author.provider_type == 'company'
                    else 'Person'
                ),
                'name': article.author.public_display_name_snapshot,
            },
        }
        # Prevent script-breaking markup in authored text; json.dumps escapes
        # quotes, then Unicode escapes protect HTML parsing context.
        schema_json = json.dumps(schema, ensure_ascii=False).replace(
            '&', r'\u0026',
        ).replace('<', r'\u003c').replace('>', r'\u003e').replace(
            '\u2028', r'\u2028',
        ).replace('\u2029', r'\u2029')

    return {
        'seo_noindex': True,  # Always: only Stage09 can authorize indexing.
        'seo_canonical': canonical,
        'seo_alternates': alternates,
        'schema_json': schema_json,
        'original_url': public_url(request, original) if original else '',
    }


def sitemap_candidates():
    """Unpublished hook for Stage09; no sitemap URL or indexability introduced."""
    return public_articles().filter(
        translation_kind__in=(
            ExpertArticle.TranslationKind.ORIGINAL,
            ExpertArticle.TranslationKind.HUMAN,
        ),
    )
