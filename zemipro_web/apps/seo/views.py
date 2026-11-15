"""Stage 09 public technical SEO endpoints."""
from collections import defaultdict
from xml.etree import ElementTree

from django.conf import settings
from django.http import HttpResponse
from django.urls import reverse
from django.utils.translation import override
from django.views.decorators.http import require_GET

from apps.accounts.client_favorites import public_worker_queryset
from apps.locations.services import get_public_cities
from apps.marketplace.services import workers_serving_city

from .models import SeoContentPage


LANGUAGES = ('ru', 'en', 'he')
SITEMAP_NS = 'http://www.sitemaps.org/schemas/sitemap/0.9'
XHTML_NS = 'http://www.w3.org/1999/xhtml'
ElementTree.register_namespace('', SITEMAP_NS)
ElementTree.register_namespace('xhtml', XHTML_NS)


def _landing_key(page):
    return (
        page.page_type, page.section_id, page.category_id,
        page.service_id, page.city_id,
    )


def _landing_path(page, language):
    with override(language):
        if page.page_type == SeoContentPage.PageType.SECTION:
            return reverse('catalog_i18n:section_detail', kwargs={'slug': page.section.slug})
        if page.page_type == SeoContentPage.PageType.CATEGORY:
            return reverse('catalog_i18n:category_detail', kwargs={'slug': page.category.slug})
        if page.page_type == SeoContentPage.PageType.SERVICE:
            return reverse('catalog_i18n:service_detail', kwargs={
                'category_slug': page.service.category.slug,
                'service_slug': page.service.slug,
            })
        if page.page_type == SeoContentPage.PageType.CITY:
            return reverse('catalog_i18n:city_detail', kwargs={'slug': page.city.slug})
        if page.page_type == SeoContentPage.PageType.SERVICE_CITY:
            return reverse('catalog_i18n:service_city_detail', kwargs={
                'category_slug': page.service.category.slug,
                'service_slug': page.service.slug,
                'city_slug': page.city.slug,
            })
    raise ValueError('Unsupported SEO landing type.')


def _has_real_value(page):
    workers = public_worker_queryset()
    if page.page_type == SeoContentPage.PageType.SECTION:
        return workers.filter(skills__section=page.section).exists()
    if page.page_type == SeoContentPage.PageType.CATEGORY:
        return workers.filter(skills=page.category).exists()
    if page.page_type in {
        SeoContentPage.PageType.SERVICE,
        SeoContentPage.PageType.SERVICE_CITY,
    }:
        city = page.city or get_public_cities().first()
        return bool(city and workers_serving_city(
            workers, city, category=page.service.category, service=page.service,
        ).exists())
    if page.page_type == SeoContentPage.PageType.CITY:
        return workers.filter(city=page.city).exists()
    return False


def _add_url(urlset, *, location, alternates, lastmod=None):
    node = ElementTree.SubElement(urlset, f'{{{SITEMAP_NS}}}url')
    ElementTree.SubElement(node, f'{{{SITEMAP_NS}}}loc').text = location
    if lastmod:
        ElementTree.SubElement(node, f'{{{SITEMAP_NS}}}lastmod').text = (
            lastmod.date().isoformat()
        )
    for language, href in alternates.items():
        ElementTree.SubElement(node, f'{{{XHTML_NS}}}link', {
            'rel': 'alternate', 'hreflang': language, 'href': href,
        })
    ElementTree.SubElement(node, f'{{{XHTML_NS}}}link', {
        'rel': 'alternate', 'hreflang': 'x-default', 'href': alternates['ru'],
    })


@require_GET
def sitemap(request):
    urlset = ElementTree.Element(f'{{{SITEMAP_NS}}}urlset')
    if settings.ZEMIPRO_CATALOG_INDEXING_ENABLED:
        pages = SeoContentPage.objects.filter(
            status=SeoContentPage.Status.PUBLISHED,
            quality_approved=True, published_at__isnull=False,
        ).select_related('section', 'category', 'service__category', 'city')
        groups = defaultdict(dict)
        for page in pages:
            groups[_landing_key(page)][page.language] = page
        for translations in groups.values():
            if set(translations) != set(LANGUAGES):
                continue
            representative = translations['ru']
            if not _has_real_value(representative):
                continue
            alternates = {
                language: request.build_absolute_uri(_landing_path(page, language))
                for language, page in translations.items()
            }
            lastmod = max(page.updated_at for page in translations.values())
            for language in LANGUAGES:
                _add_url(
                    urlset, location=alternates[language], alternates=alternates,
                    lastmod=lastmod,
                )
        for profile in public_worker_queryset().filter(
            public_description_snapshot__gt='',
        ).order_by('pk'):
            alternates = {}
            for language in LANGUAGES:
                with override(language):
                    path = reverse(
                        'catalog_i18n:worker_public_profile', args=[profile.pk],
                    )
                alternates[language] = request.build_absolute_uri(path)
            for language in LANGUAGES:
                _add_url(
                    urlset, location=alternates[language], alternates=alternates,
                    lastmod=profile.updated_at,
                )
    body = ElementTree.tostring(urlset, encoding='utf-8', xml_declaration=True)
    response = HttpResponse(body, content_type='application/xml; charset=utf-8')
    response['Cache-Control'] = 'public, max-age=300'
    return response


@require_GET
def robots(request):
    if not settings.ZEMIPRO_CATALOG_INDEXING_ENABLED:
        lines = ['User-agent: *', 'Disallow: /']
    else:
        lines = [
            'User-agent: *', 'Allow: /', 'Disallow: /admin/',
            'Disallow: /accounts/', 'Disallow: /orders/',
            'Disallow: /offers/', 'Disallow: /agreements/',
            'Disallow: /chat/', 'Disallow: /notifications/',
            'Disallow: /moderation/', 'Disallow: /knowledge/',
        ]
    lines.extend(['', f'Sitemap: {request.build_absolute_uri(reverse("seo_sitemap"))}', ''])
    return HttpResponse('\n'.join(lines), content_type='text/plain; charset=utf-8')
