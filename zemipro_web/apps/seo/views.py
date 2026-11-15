"""Stage 09 public technical SEO endpoints."""
from collections import defaultdict
from xml.etree import ElementTree

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, HttpResponse, HttpResponseGone
from django.http.response import HttpResponseRedirectBase
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _, override
from django.views.decorators.http import require_GET, require_http_methods
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.accounts.client_favorites import public_worker_queryset
from apps.locations.services import get_public_cities
from apps.marketplace.services import workers_serving_city
from apps.marketplace.catalog_seo import complete_collection, complete_content, complete_names
from apps.marketplace.models import Category, Subcategory

from .legacy import redirect_target_is_safe
from .forms import SeoContentEditForm, SeoContentPageForm
from .models import SeoContentPage, SeoLegacyUrl
from .services import approve_content, publish_content, revise_content, unpublish_content


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
        categories = Category.objects.filter(
            section=page.section, is_active=True,
        ).order_by('sort_order', 'pk')
        return bool(
            workers.filter(skills__section=page.section).exists()
            and complete_content(page.section, description=True)
            and categories.exists()
            and complete_collection(categories, description=True)
        )
    if page.page_type == SeoContentPage.PageType.CATEGORY:
        services = Subcategory.objects.filter(
            category=page.category, is_active=True,
        ).order_by('sort_order', 'pk')
        return bool(
            workers.filter(skills=page.category).exists()
            and complete_content(page.category, description=True)
            and services.exists()
            and complete_collection(services, description=True)
        )
    if page.page_type in {
        SeoContentPage.PageType.SERVICE,
        SeoContentPage.PageType.SERVICE_CITY,
    }:
        city = page.city or get_public_cities().first()
        return bool(
            city
            and complete_content(page.service, description=True)
            and complete_names(city)
            and workers_serving_city(
                workers, city, category=page.service.category, service=page.service,
            ).exists()
        )
    if page.page_type == SeoContentPage.PageType.CITY:
        categories = Category.objects.filter(is_active=True).filter(
            section__isnull=True,
        ) | Category.objects.filter(
            is_active=True, section__is_active=True,
        )
        return bool(
            complete_names(page.city)
            and workers.filter(city=page.city).exists()
            and complete_collection(categories)
        )
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


@require_GET
def legacy_url(request, legacy_path):
    """Resolve only an exact approved row; unknown paths never redirect."""
    if not settings.ZEMIPRO_LEGACY_REDIRECTS_ENABLED:
        raise Http404
    exact_path = f'/master/{legacy_path}'
    row = SeoLegacyUrl.objects.filter(path=exact_path, is_active=True).first()
    if row is None:
        raise Http404
    if row.decision == SeoLegacyUrl.Decision.GONE:
        response = HttpResponseGone()
        response['Cache-Control'] = 'public, max-age=300'
        return response
    if row.decision == SeoLegacyUrl.Decision.NOT_FOUND:
        raise Http404
    if row.decision != SeoLegacyUrl.Decision.REDIRECT or not redirect_target_is_safe(row):
        raise Http404
    response = HttpResponseRedirectBase(
        row.target_path, status=row.redirect_status,
    )
    response['Cache-Control'] = 'public, max-age=300'
    return response


def _editorial_queryset(user):
    queryset = SeoContentPage.objects.select_related(
        'author', 'reviewer', 'section', 'category', 'service', 'city',
    )
    return queryset if user.is_staff else queryset.filter(author=user)


@login_required
@require_GET
@never_cache
def editorial_list(request):
    if not request.user.has_perm('seo.view_seocontentpage'):
        raise PermissionDenied
    return render(request, 'seo/editorial_list.html', {
        'pages': _editorial_queryset(request.user).order_by('-updated_at', '-pk')[:100],
        'seo_noindex': True,
    })


@login_required
@require_http_methods(['GET', 'POST'])
@never_cache
def editorial_create(request):
    if not request.user.has_perm('seo.add_seocontentpage'):
        raise PermissionDenied
    form = SeoContentPageForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        page = form.save(commit=False)
        page.author = request.user
        page.status = SeoContentPage.Status.BRIEF
        try:
            page.save()
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, _('SEO-бриф создан.'))
            return redirect('seo:editorial_detail', pk=page.pk)
    return render(request, 'seo/editorial_form.html', {
        'form': form, 'page': None, 'seo_noindex': True,
    })


@login_required
@require_http_methods(['GET', 'POST'])
@never_cache
def editorial_detail(request, pk):
    if not request.user.has_perm('seo.view_seocontentpage'):
        raise PermissionDenied
    if request.method == 'POST' and not request.user.has_perm(
        'seo.change_seocontentpage'
    ):
        raise PermissionDenied
    page = get_object_or_404(_editorial_queryset(request.user), pk=pk)
    if request.method == 'POST':
        form = SeoContentEditForm(request.POST, instance=page)
        if form.is_valid():
            changes = {
                field: form.cleaned_data[field]
                for field in form.Meta.fields
            }
            try:
                revise_content(
                    page_id=page.pk, actor=request.user,
                    expected_version=form.cleaned_data['expected_version'],
                    changes=changes,
                )
            except (PermissionDenied, ValidationError) as exc:
                form.add_error(None, exc)
            else:
                messages.success(request, _('SEO-черновик сохранён в новой версии.'))
                return redirect('seo:editorial_detail', pk=page.pk)
    else:
        form = SeoContentEditForm(instance=page, initial={
            'expected_version': page.version,
        })
    return render(request, 'seo/editorial_form.html', {
        'form': form, 'page': page,
        'revisions': page.revisions.select_related('created_by')[:100],
        'seo_noindex': True,
    })


@login_required
@require_POST
@never_cache
def editorial_action(request, pk, action):
    if not request.user.has_perm('seo.view_seocontentpage'):
        raise PermissionDenied
    page = get_object_or_404(_editorial_queryset(request.user), pk=pk)
    try:
        expected_version = int(request.POST.get('expected_version', ''))
    except (TypeError, ValueError):
        raise Http404 from None
    try:
        if action == 'submit':
            revise_content(
                page_id=page.pk, actor=request.user, expected_version=expected_version,
                changes={'status': SeoContentPage.Status.REVIEW},
            )
        elif action == 'approve':
            approve_content(
                page_id=page.pk, actor=request.user, expected_version=expected_version,
            )
        elif action == 'publish':
            publish_content(
                page_id=page.pk, actor=request.user, expected_version=expected_version,
            )
        elif action == 'unpublish':
            unpublish_content(
                page_id=page.pk, actor=request.user, expected_version=expected_version,
            )
        else:
            raise Http404
    except (PermissionDenied, ValidationError) as exc:
        messages.error(request, str(exc))
    else:
        action_messages = {
            'submit': _('Материал передан на проверку.'),
            'approve': _('Материал одобрен.'),
            'publish': _('Материал опубликован.'),
            'unpublish': _('Материал снят с публикации.'),
        }
        messages.success(request, action_messages[action])
    return redirect('seo:editorial_detail', pk=page.pk)
