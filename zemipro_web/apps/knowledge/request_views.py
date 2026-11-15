"""Stage 14.10 separate, gated recommendation-request UI."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import get_language
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from apps.accounts.public_text import contact_shaped_query

from . import request_services
from .models import RecommendationRequest, RecommendationResponse
from .qa_forms import ModerationForm
from .request_forms import RecommendationRequestForm, RecommendationResponseForm


def _allow():
    try:
        request_services._enabled()
    except PermissionDenied as exc:
        raise Http404 from exc


@require_GET
@never_cache
def request_list(request):
    _allow()
    language = (get_language() or 'ru').split('-')[0]
    visible = request_services.public_requests().filter(language=language)
    query = request.GET.get('q', '').strip()
    invalid = len(query) > 120 or contact_shaped_query(query)
    if invalid:
        visible = visible.none()
        query = ''
    elif query:
        visible = visible.filter(
            Q(public_title__icontains=query) | Q(public_body__icontains=query),
        )
    page = Paginator(visible, 12).get_page(request.GET.get('page'))
    return render(request, 'knowledge/request_list.html', {
        'page_obj': page, 'query': query, 'invalid_query': invalid,
        'seo_noindex': True,
    })


@require_GET
@never_cache
def request_detail(request, slug):
    _allow()
    item = get_object_or_404(
        request_services.public_requests(), slug=slug,
        language=(get_language() or 'ru').split('-')[0],
    )
    return render(request, 'knowledge/request_detail.html', {
        'item': item, 'responses': request_services.public_responses(item),
        'response_form': RecommendationResponseForm(category_id=item.category_id),
        'seo_noindex': True,
    })


@login_required
@require_http_methods(['GET', 'POST'])
@never_cache
def request_create(request):
    _allow()
    form = RecommendationRequestForm(
        request.POST or None,
        initial={'language': (get_language() or 'ru').split('-')[0]},
    )
    if request.method == 'POST' and form.is_valid():
        request_services.create_request(
            actor=request.user, category_id=form.cleaned_data['category'].pk,
            language=form.cleaned_data['language'], title=form.cleaned_data['title'],
            body=form.cleaned_data['body'],
        )
        messages.success(request, 'Request submitted for moderation.')
        return redirect('knowledge_requests:list')
    return render(request, 'knowledge/request_form.html', {
        'form': form, 'seo_noindex': True,
    })


@login_required
@require_POST
def response_create(request, slug):
    _allow()
    item = get_object_or_404(request_services.public_requests(), slug=slug)
    form = RecommendationResponseForm(request.POST, category_id=item.category_id)
    if not form.is_valid():
        raise PermissionDenied('Invalid response.')
    request_services.create_response(
        actor=request.user, request_id=item.pk,
        worker_id=form.cleaned_data['worker'].pk, body=form.cleaned_data['body'],
    )
    messages.success(request, 'Suggestion submitted for moderation.')
    return redirect('knowledge_requests:detail', slug=item.slug)


def _moderator_read(user):
    current = request_services._active_user(user, lock=False)
    if not current.is_staff or not current.has_perm(
        'knowledge.moderate_recommendation_requests',
    ):
        raise PermissionDenied('Moderator only.')


@login_required
@require_GET
def moderation_queue(request):
    _allow()
    _moderator_read(request.user)
    return render(request, 'knowledge/request_moderation.html', {
        'requests': RecommendationRequest.objects.filter(status='pending')[:100],
        'responses': RecommendationResponse.objects.filter(
            status='pending',
        ).select_related('request', 'worker')[:100],
    })


@login_required
@require_POST
def moderate_request(request, request_id):
    form = ModerationForm(request.POST)
    if not form.is_valid():
        raise PermissionDenied('Invalid decision.')
    request_services.moderate_request(
        actor=request.user, request_id=request_id,
        expected_version=form.cleaned_data['expected_version'],
        approve=form.cleaned_data['action'] == 'approve', note=form.cleaned_data['note'],
    )
    return redirect('knowledge:request_moderation')


@login_required
@require_POST
def moderate_response(request, response_id):
    form = ModerationForm(request.POST)
    if not form.is_valid():
        raise PermissionDenied('Invalid decision.')
    request_services.moderate_response(
        actor=request.user, response_id=response_id,
        expected_version=form.cleaned_data['expected_version'],
        approve=form.cleaned_data['action'] == 'approve', note=form.cleaned_data['note'],
    )
    return redirect('knowledge:request_moderation')
