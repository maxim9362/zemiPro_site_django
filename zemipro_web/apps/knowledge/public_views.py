"""Stage 14.3: public article pages limited to moderated Ashdod content."""
from urllib.parse import urlencode

from django.conf import settings
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import Http404, HttpResponse
from django.shortcuts import redirect
from django.shortcuts import get_object_or_404, render
from django.utils.translation import get_language
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from apps.accounts.public_text import contains_public_contact
from apps.marketplace.models import Category
from .public_content import (
    public_article_image, public_article_images, public_articles,
)
from .public_search import PublicArticleSearchForm
from .public_seo import article_seo, list_seo, public_path


def _allow_public():
    if not settings.ZEMIPRO_KNOWLEDGE_ARTICLES_ENABLED:
        raise Http404


@require_GET
@never_cache
def article_list(request):
    _allow_public()
    visible = public_articles()
    categories = list(Category.objects.filter(
        pk__in=visible.values('category_id'), is_active=True,
    ).order_by('sort_order', 'pk').distinct())
    form = PublicArticleSearchForm(
        request.GET if request.GET else None, categories=categories,
    )
    # An unbound form (no filters) is valid for browsing all approved articles.
    # Django forms.is_valid() returns False for unbound forms by design.
    valid = not form.is_bound or form.is_valid()
    preserved = {}
    invalid_query = not valid
    if valid:
        fields = (
            form.cleaned_data if form.is_bound
            else {'q': '', 'category': '', 'language': ''}
        )
        if fields['q']:
            # Search ONLY approved, contact-free snapshots, never drafts.
            visible = visible.filter(
                Q(public_title__icontains=fields['q']) |
                Q(public_excerpt__icontains=fields['q']) |
                Q(public_body__icontains=fields['q']),
            )
        if fields['category']:
            visible = visible.filter(category_id=int(fields['category']))
        if fields['language']:
            visible = visible.filter(language=fields['language'])
        preserved = {
            key: fields[key] for key in ('q', 'category', 'language') if fields[key]
        }
    else:
        # Do not echo rejected/possibly private search values in HTML.
        visible = visible.none()
        form = PublicArticleSearchForm(categories=categories)
    query = urlencode(preserved)
    page = Paginator(visible.order_by('-published_at', '-pk'), 12).get_page(
        request.GET.get('page'),
    )
    page.object_list = list(page.object_list)
    for article in page.object_list:
        article.public_path = public_path(article)
    context = {
        'form': form,
        'page_obj': page,
        'invalid_query': invalid_query,
        'pagination_query': query,
        'language_switch_next': request.path + ('?' + query if query else ''),
        **list_seo(request),
    }
    return render(request, 'knowledge/public_list.html', context)


@require_GET
@never_cache
def article_detail(request, slug):
    _allow_public()
    language = (get_language() or 'ru').split('-')[0]
    if language not in ('ru', 'en', 'he'):
        raise Http404
    article = get_object_or_404(
        public_articles(), slug=slug, language=language,
    )
    seo = article_seo(request, article)
    # No raw author name, source text or unrestricted uploads in context.
    response = render(request, 'knowledge/public_detail.html', {
        'article': article,
        'images': public_article_images(article),
        **seo,
    })
    from .pilot_metrics import safe_record_metric
    safe_record_metric(article, 'article_view')
    from .rollout_metrics import record
    record('article', 'article_view', article.pk)
    return response


@require_GET
@never_cache
def article_outbound(request, slug, destination):
    """Same-origin redirect, strictly whitelisted targets; no external URL input."""
    _allow_public()
    language = (get_language() or 'ru').split('-')[0]
    if language not in ('ru', 'en', 'he') or destination not in ('profile', 'order'):
        raise Http404
    article = get_object_or_404(
        public_articles(), slug=slug, language=language,
    )
    from django.urls import reverse
    from .pilot_metrics import safe_record_metric, start_order_ref

    if destination == 'profile':
        safe_record_metric(article, 'profile_click')
        from .rollout_metrics import record
        record('article', 'profile_click', article.pk)
        target = reverse('marketplace:worker_public_profile', args=[article.author_id])
    else:
        safe_record_metric(article, 'order_click')
        from .rollout_metrics import record
        record('article', 'order_started', article.pk)
        start_order_ref(request, article)
        target = reverse('marketplace:order_wizard_start')
    response = redirect(target)
    response['Cache-Control'] = 'private, no-store'
    return response


@require_GET
@never_cache
def article_image(request, image_id):
    _allow_public()
    image = public_article_image(image_id)
    if image is None or contains_public_contact(image.public_caption):
        raise Http404
    # Uploaded originals, metadata and unapproved copies are never served.
    data = bytes(image.jpeg_data)
    if not data.startswith(b'\xff\xd8') or not data.endswith(b'\xff\xd9'):
        raise Http404
    response = HttpResponse(data, content_type='image/jpeg')
    response['Cache-Control'] = 'private, no-store, max-age=0'
    response['X-Content-Type-Options'] = 'nosniff'
    response['Content-Security-Policy'] = "default-src 'none'; sandbox"
    response['Content-Disposition'] = 'inline; filename="expert-article.jpg"'
    return response
