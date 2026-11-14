import logging
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Avg, Count, F, Prefetch, Q
from django.http import FileResponse, Http404, HttpResponse, JsonResponse, HttpResponsePermanentRedirect
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST
from django.utils.translation import gettext as _

from apps.accounts.forms import RatingCreateForm
from apps.accounts.models import FavoriteWorker
from apps.accounts.client_favorites import (
    own_visible_favorites, set_own_favorite, public_worker_queryset,
)
from apps.accounts.models import WorkerProfile
from apps.accounts.worker_views import record_worker_view, own_visible_worker_history
from apps.accounts.services import get_client_profile, get_worker_profile
from apps.locations.models import CityAlias, Neighborhood
from apps.locations.services import city_is_public, get_public_cities, public_city_slug
from apps.notifications.services import create_notification
from .catalog_seo import catalog_context, complete_collection, complete_content, complete_names
from .directory_search import (
    WorkerDirectoryForm, active_categories, search_worker_profiles,
)
from .directory_ranking import ranking_audit_rows
from .directory_ui import directory_copy
from .invitation_ui import invitation_copy
from .invitation_services import (
    InvitationConflict, create_invitation, act_on_invitation,
    invitable_orders, worker_matches_order,
)
from .questionnaires import localized_label
from .questionnaire_services import present_order_answers
from .forms import OrderCreateForm, ResponseCreateForm
from .offer_services import submit_offer
from .offer_presentation import (
    owner_offer_cards, selected_worker_public_name,
    filter_and_sort_offer_cards, owner_offer_filter_context,
)
from .offer_ui import offer_copy, stage06_notice
from .agreement_presentation import private_agreement_context
from .models import (
    Category, ServiceSection, Subcategory, Order, Response, Rating, OrderInvitation,
    ServiceQuestionnaire, OrderQuestionnaireAnswer,
)
from .services import (
    get_available_orders_for_worker, create_order,
    accept_response, complete_order, cancel_order,
    can_view_private_order_details, workers_serving_city,
)

from django.views.decorators.cache import never_cache
import uuid

from .wizard_forms import STEP_FORMS, ServiceStepForm, QuestionsStepForm
from .wizard_services import (
    ensure_wizard_owner, get_owner_wizard, publish_order_wizard,
    save_order_wizard_step, start_order_wizard, wizard_initial,
    wizard_max_step, wizard_summary,
)
from .wizard_ui import wizard_copy
from .order_quota import OrderQuotaExceeded
from .order_events import deliver_order_events_for_order
from .order_management import (
    OrderEditForm, duplicate_order, edit_published_order,
    management_timeline, withdraw_order,
)
from .attachment_services import (
    OrderPhotoError, can_read_order_photo, delete_order_photo,
    order_attachment_key, visible_order_photos,
)
from apps.accounts.portfolio import private_portfolio_storage
from .models import OrderAttachment

ITEMS_PER_PAGE = 10
LOGGER = logging.getLogger('zemipro')


def _flush_order_events(order):
    """Notification failure must not undo a committed successful order action."""
    try:
        deliver_order_events_for_order(order)
    except Exception:
        # The receipts remain pending and replayable. No payloads or paths
        # from the event, request or exception enter the structured log.
        LOGGER.warning('order_event_local_delivery_deferred')


def _order_quota_response(error):
    """Return a non-PII 429 rather than masking a durable quota as success."""
    response = HttpResponse(
        wizard_copy()['throttled'], status=429,
        content_type='text/plain; charset=utf-8',
    )
    response['Retry-After'] = str(error.retry_after)
    response['Cache-Control'] = 'private, no-store'
    return response


def home(request):
    categories = Category.objects.filter(is_active=True).filter(
        Q(section__isnull=True) | Q(section__is_active=True)
    ).order_by('sort_order', 'pk')
    return render(request, 'pages/home.html', {'categories': categories})


@require_GET
def worker_directory_view(request):
    """Public read-only specialist directory; never render private contacts."""
    form = WorkerDirectoryForm(request.GET)
    workers = search_worker_profiles(form).select_related(
        'user', 'city',
    ).prefetch_related(Prefetch(
        'skills',
        queryset=active_categories().order_by('sort_order', 'pk'),
        to_attr='public_search_skills',
    ))
    paginator = Paginator(workers, ITEMS_PER_PAGE)
    page = paginator.get_page(request.GET.get('page'))
    if form.is_valid():
        params = form.cleaned_data
        ranking_audit_rows(
            page, params=params,
            city=bool(
                params['city'] or params['neighborhood'] or public_city_slug()
            ),
        )
    # Only verified filter names/values survive links; no arbitrary GET reflection.
    preserved = {}
    if form.is_valid():
        for name in form.fields:
            value = request.GET.get(name, '')
            if value:
                preserved[name] = value
    safe_query = urlencode(preserved)
    # Never index user-generated/filter URLs automatically. Localized
    # canonical + hreflang come from the existing Stage 02 catalog policy.
    seo = catalog_context(request, 'worker_directory', indexable=False)
    if not seo.get('catalog_localized'):
        seo['seo_canonical'] = request.build_absolute_uri(
            reverse('marketplace:worker_directory')
        )
    if form.errors:
        for field_name in form.errors:
            if field_name in form.fields:
                form.fields[field_name].widget.attrs['aria-invalid'] = 'true'
    return render(request, 'pages/worker_directory.html', {
        'form': form,
        'page_obj': page,
        'pagination_query': safe_query,
        'directory_copy': directory_copy(),
        'language_switch_next': request.path + (
            '?' + safe_query if safe_query else ''
        ),
        **seo,
        # No unapproved mass indexing of directory pages, including empty
        # results, deep pagination and filtered combinations.
        'seo_noindex': True,
    })


def categories_list(request):
    categories = Category.objects.filter(
        is_active=True
    ).filter(Q(section__isnull=True) | Q(section__is_active=True)).order_by(
        'sort_order', 'pk'
    )
    sections = ServiceSection.objects.filter(is_active=True).prefetch_related(
        Prefetch(
            'categories',
            queryset=Category.objects.filter(is_active=True).order_by(
                'sort_order', 'pk'
            ),
        )
    )
    unassigned_categories = categories.filter(section__isnull=True)
    context = {
        'categories': categories,
        'sections': sections,
        'unassigned_categories': unassigned_categories,
    }
    def ready_for_indexing():
        if not categories.exists():
            return False
        # Sections without categories are not rendered by the template.
        for section in sections:
            visible = list(section.categories.all())
            if visible and not (
                complete_names(section)
                and complete_collection(visible, description=True)
            ):
                return False
        return complete_collection(unassigned_categories, description=True)

    context.update(catalog_context(
        request, 'categories_list', indexable=ready_for_indexing,
    ))
    return render(request, 'pages/categories.html', context)



def api_questionnaire(request, service_id):
    """Public read-only published schema. Only safe labels and stable option IDs."""
    if request.method != 'GET':
        raise Http404
    service = get_object_or_404(
        Subcategory.objects.filter(
            is_active=True, category__is_active=True,
        ).filter(
            Q(category__section__isnull=True)
            | Q(category__section__is_active=True)
        ), pk=service_id,
    )
    template = ServiceQuestionnaire.objects.select_related(
        'published_version',
    ).filter(service=service).first()
    version = template.published_version if template is not None else None
    if version is None:
        return JsonResponse({'version': None, 'questions': []})
    questions = []
    for question in version.schema:
        condition = question.get('depends_on')
        questions.append({
            'key': question['key'],
            'type': question['type'],
            'label': localized_label(question['labels']),
            'required': question['required'],
            'options': (
                [{'value': 'true', 'label': _('Да')},
                 {'value': 'false', 'label': _('Нет')}]
                if question['type'] == 'boolean'
                else [
                    {'value': item['value'], 'label': localized_label(item['labels'])}
                    for item in question.get('options', [])
                ]
            ),
            'depends_on': condition,
        })
    return JsonResponse({'version': version.pk, 'questions': questions})


def api_subcategories(request, category_id):
    """Public localized dependent choices; no free-text or private data."""
    if request.method != 'GET':
        raise Http404
    get_object_or_404(
        Category.objects.filter(is_active=True).filter(
            Q(section__isnull=True) | Q(section__is_active=True)
        ),
        pk=category_id,
    )
    choices = Subcategory.objects.filter(
        category_id=category_id, is_active=True,
    ).order_by('sort_order', 'pk')
    return JsonResponse([
        {'id': item.pk, 'name': item.localized_name}
        for item in choices
    ], safe=False)


def category_detail(request, slug):
    category = get_object_or_404(
        Category.objects.filter(
            Q(section__isnull=True) | Q(section__is_active=True)
        ), slug=slug, is_active=True,
    )
    cities = get_public_cities().order_by('name_ru')
    selected_city = request.GET.get('city')

    workers = public_worker_queryset().filter(
        skills=category,
    ).annotate(
        avg_rating=Avg('user__received_ratings__rating'),
        review_count=Count('user__received_ratings', distinct=True),
    ).order_by(F('avg_rating').desc(nulls_last=True), 'pk')

    if selected_city:
        target_city = get_public_cities().filter(slug=selected_city).first()
        if target_city is None:
            workers = workers.none()
        else:
            workers = workers_serving_city(workers, target_city, category=category)
    elif public_city_slug():
        # Do not advertise workers serving only outside the first pilot city.
        pilot_city = get_public_cities().first()
        workers = (
            workers_serving_city(workers, pilot_city, category=category)
            if pilot_city is not None else workers.none()
        )

    paginator = Paginator(workers, ITEMS_PER_PAGE)
    page = paginator.get_page(request.GET.get('page'))

    subcategories = Subcategory.objects.filter(
        category=category, is_active=True
    ).order_by('sort_order', 'pk')

    context = {
        'subcategories': subcategories,
        'category': category,
        'page_obj': page,
        'cities': cities,
        'selected_city': selected_city,
    }
    context.update(catalog_context(
        request, 'category_detail', kwargs={'slug': category.slug},
        indexable=lambda: (
            page.paginator.count > 0
            and complete_content(category, description=True)
            and complete_collection(subcategories)
            and complete_collection(cities)
            and all(
                worker.city is None or complete_names(worker.city)
                for worker in page.object_list
            )
        ),
    ))
    return render(request, 'pages/category_detail.html', context)


def cities_list(request):
    cities = get_public_cities().select_related(
        'district'
    ).order_by('name_ru', 'pk')
    context = {'cities': cities}
    context.update(catalog_context(
        request, 'cities_list', indexable=lambda: (
            cities.exists()
            and all(
                complete_names(city)
                and (city.district is None or complete_names(city.district))
                for city in cities
            )
        ),
    ))
    return render(request, 'pages/cities.html', context)


def city_detail(request, slug):
    is_prefixed = (
        request.resolver_match is not None
        and request.resolver_match.namespace == 'catalog_i18n'
    )
    if is_prefixed:
        alias = CityAlias.objects.select_related('city').filter(slug=slug).first()
        if alias is not None:
            if not city_is_public(alias.city):
                raise Http404
            pathname = reverse(
                'catalog_i18n:city_detail', kwargs={'slug': alias.city.slug},
            )
            if request.GET:
                pathname += '?' + request.GET.urlencode()
            return HttpResponsePermanentRedirect(pathname)
    city = get_object_or_404(get_public_cities(), slug=slug)
    categories = Category.objects.filter(is_active=True).filter(
        Q(section__isnull=True) | Q(section__is_active=True)
    ).order_by('sort_order', 'pk')
    selected_category = request.GET.get('category')

    workers = public_worker_queryset().prefetch_related('skills').annotate(
        avg_rating=Avg('user__received_ratings__rating'),
        review_count=Count('user__received_ratings', distinct=True),
    ).order_by(F('avg_rating').desc(nulls_last=True), 'pk')

    if selected_category:
        category = categories.filter(slug=selected_category).first()
        if category is None:
            workers = workers.none()
        else:
            workers = workers.filter(skills=category)
            workers = workers_serving_city(workers, city, category=category)
    else:
        workers = workers_serving_city(workers, city)

    paginator = Paginator(workers, ITEMS_PER_PAGE)
    page = paginator.get_page(request.GET.get('page'))

    context = {
        'city': city,
        'categories': categories,
        'page_obj': page,
        'selected_category': selected_category,
    }
    context.update(catalog_context(
        request, 'city_detail', kwargs={'slug': city.slug},
        indexable=lambda: (
            complete_names(city)
            and page.paginator.count > 0
            and complete_collection(categories)
            and all(
                complete_collection(worker.skills.all())
                for worker in page.object_list
            )
        ),
    ))
    return render(request, 'pages/city_detail.html', context)



def section_detail(request, slug):
    section = get_object_or_404(
        ServiceSection, slug=slug, is_active=True,
    )
    categories = Category.objects.filter(
        section=section, is_active=True,
    ).order_by('sort_order', 'pk')
    context = {'section': section, 'categories': categories}
    context.update(catalog_context(
        request, 'section_detail', kwargs={'slug': section.slug},
        indexable=lambda: (
            complete_content(section, description=True)
            and categories.exists()
            and complete_collection(categories, description=True)
        ),
    ))
    return render(request, 'pages/section_detail.html', context)


def service_detail(request, category_slug, service_slug):
    service = get_object_or_404(
        Subcategory.objects.select_related('category', 'category__section')
        .filter(
            Q(category__section__isnull=True)
            | Q(category__section__is_active=True),
        ),
        category__slug=category_slug, slug=service_slug,
        is_active=True, category__is_active=True,
    )
    # We don't have service-specific workers yet. Avoid implying supply
    # based on category membership, and never index an empty/thin service page.
    context = {'service': service, 'category': service.category}
    context.update(catalog_context(
        request, 'service_detail',
        kwargs={
            'category_slug': service.category.slug,
            'service_slug': service.slug,
        },
        indexable=False,
    ))
    return render(request, 'pages/service_detail.html', context)


def worker_public_profile_view(request, pk):
    workers = public_worker_queryset().prefetch_related(
        Prefetch('skills', queryset=active_categories().order_by('sort_order', 'pk')),
        Prefetch('services', queryset=Subcategory.objects.filter(
            is_active=True, category__is_active=True,
        ).order_by('category_id', 'sort_order', 'pk')),
        Prefetch('service_cities', queryset=get_public_cities(),
                 to_attr='public_service_cities'),
        Prefetch('service_neighborhoods', queryset=Neighborhood.objects.filter(
            is_active=True, city__in=get_public_cities(),
        ), to_attr='public_service_neighborhoods'),
    )
    if public_city_slug():
        pilot_city = get_public_cities().first()
        workers = (
            workers_serving_city(workers, pilot_city)
            if pilot_city is not None else workers.none()
        )
    profile = get_object_or_404(workers, pk=pk)
    record_worker_view(request.user, profile)
    reviews = Rating.objects.filter(
        worker_id=profile.user_id,
    ).order_by('-created_at')

    review_stats = reviews.aggregate(avg=Avg('rating'), count=Count('pk'))
    avg_rating = review_stats['avg'] or 0
    review_count = review_stats['count']

    response = render(request, 'pages/worker_public_profile.html', {
        'profile': profile,
        'public_photos': profile.portfolio_photos.filter(is_public=True),
        'reviews': reviews[:10],
        'avg_rating': round(avg_rating, 1),
        'review_count': review_count,
        'invite_copy': invitation_copy(),
        'directory_copy': directory_copy(),
        'seo_noindex': True,
        'seo_canonical': request.build_absolute_uri(
            reverse('marketplace:worker_public_profile', args=[profile.pk])
        ),
        'is_favorite': (
            request.user.is_authenticated
            and FavoriteWorker.objects.filter(
                client=request.user, worker=profile,
            ).exists()
        ),
    })
    # The favorite/opt-in experience is per-user; never cache publicly.
    response['Cache-Control'] = 'private, no-store'
    return response



@login_required
@never_cache
def worker_invitation_select_view(request, pk):
    """Registered specialist → owned published request, with POST confirmation."""
    worker = get_object_or_404(public_worker_queryset(), pk=pk)
    copy = invitation_copy()
    if request.method == 'POST':
        try:
            order_id = int(request.POST.get('order_id', ''))
        except (TypeError, ValueError):
            raise Http404 from None
        try:
            invitation, created = create_invitation(
                actor=request.user, order_id=order_id, worker_id=worker.pk,
            )
        except OrderQuotaExceeded as error:
            return _order_quota_response(error)
        except (InvitationConflict, ValueError, PermissionDenied):
            # Never reveal whether someone else's order ID exists.
            raise Http404 from None
        messages.success(request, copy['sent'] if created else copy['existing'])
        return redirect('marketplace:invitation_detail', pk=invitation.pk)
    if request.method != 'GET':
        raise Http404
    orders = invitable_orders(request.user, worker)
    selected_order = request.GET.get('order', '')
    return render(request, 'pages/worker_invitation_select.html', {
        'worker': worker, 'orders': orders, 'selected_order': selected_order,
        'invite_copy': copy, 'seo_noindex': True,
    })


@login_required
@never_cache
def invitation_detail_view(request, pk):
    invitation = get_object_or_404(
        OrderInvitation.objects.select_related(
            'order', 'order__category', 'order__subcategory', 'order__city',
            'worker', 'worker__user',
        ).filter(Q(client_id=request.user.pk) | Q(worker__user_id=request.user.pk)),
        pk=pk,
    )
    if not request.user.is_active or request.user.is_blocked or request.user.email_verification_required:
        raise Http404
    return render(request, 'pages/invitation_detail.html', {
        'invitation': invitation,
        'is_client': invitation.client_id == request.user.pk,
        'invite_copy': invitation_copy(),
        'seo_noindex': True,
    })


@login_required
@require_POST
@never_cache
def invitation_action_view(request, pk, action):
    if action not in ('accept', 'decline', 'withdraw'):
        raise Http404
    try:
        invite, _ = act_on_invitation(
            actor=request.user, invitation_id=pk, action=action,
        )
    except (PermissionDenied, OrderInvitation.DoesNotExist):
        raise Http404 from None
    except (InvitationConflict, ValueError):
        messages.warning(request, invitation_copy()['conflict'])
        return redirect('marketplace:invitation_detail', pk=pk)
    return redirect('marketplace:invitation_detail', pk=invite.pk)


@login_required
@never_cache
def toggle_favorite_worker_view(request, pk):
    """Add/remove the authenticated user's private favorite via POST only."""
    if request.method != 'POST':
        raise Http404
    worker = get_object_or_404(
        WorkerProfile.objects.select_related('user'), pk=pk,
    )
    action = request.POST.get('action', 'add')
    if action not in ('add', 'remove'):
        raise Http404
    try:
        set_own_favorite(request.user, worker, saved=action == 'add')
    except ValueError:
        raise Http404 from None
    return redirect('marketplace:worker_public_profile', pk=pk)


@login_required
@never_cache
def order_create_view(request):
    """Retain legacy POST compatibility but route writes through owner service.

    New CTAs open the wizard; the old GET remains for integrations.
    Legacy writes use the same centralized owner and replay checks.
    """
    if request.method not in ('GET', 'POST'):
        raise Http404
    ensure_wizard_owner(request.user)
    if request.method == 'GET':
        profile = get_client_profile(request.user)
        initial = {'city': profile.city} if profile else {}
        return render(request, 'pages/order_create.html', {
            'form': OrderCreateForm(initial=initial), 'seo_noindex': True,
            'order_contact_privacy': wizard_copy()['privacy'],
            'wizard_link_label': wizard_copy()['heading'],
        })
    form = OrderCreateForm(request.POST)
    if form.is_valid():
        values = form.cleaned_data
        try:
            order, created = create_order(
                client=request.user,
                category=values['category'],
                subcategory=values['subcategory'],
                city=values['city'],
                address=values.get('address') or '',
                description=values['description'],
                price=values['price'],
                customer_name=values.get('customer_name') or '',
                customer_phone=values.get('customer_phone') or '',
                questionnaire_version=form.active_questionnaire_version,
                questionnaire_answers=form.questionnaire_answers,
                submission_key=request.POST.get('submission_key'),
                return_created=True,
            )
        except OrderQuotaExceeded as error:
            return _order_quota_response(error)
        except ValueError as error:
            form.add_error(None, str(error))
        else:
            _flush_order_events(order)
            return redirect('marketplace:order_detail', pk=order.pk)
    return render(request, 'pages/order_create.html', {
        'form': form, 'seo_noindex': True,
        'order_contact_privacy': wizard_copy()['privacy'],
        'wizard_link_label': wizard_copy()['heading'],
    })



def _wizard_render(request, *, step, form, order=None, token='', drafts=None):
    t = wizard_copy()
    return render(request, 'pages/order_wizard.html', {
        'invite_copy': invitation_copy(),
        'invite_worker_pk': getattr(request, '_invite_worker_pk', None),
        'copy': t, 'form': form, 'step': step, 'order': order,
        'previous_step': max(1, step - 1),
        'wizard_steps': [
            {'number': number, 'title': t['step' + str(number)]}
            for number in range(1, 9)
        ],
        'token': token, 'drafts': drafts or [],
        'wizard_title': t['step' + str(step)],
        'is_new_wizard': order is None,
        'summary_rows': wizard_summary(order) if order and step == 8 else [],
        'saved_photos': list(visible_order_photos(order, request.user))
        if order and step in (6, 8) else [],
        'questionnaire_questions': (
            form.questionnaire_questions if step == 2 else []
        ),
        'has_questions': (
            bool(form.active_questionnaire_version) if step == 2 else False
        ),
        'seo_noindex': True,
    })


def _wizard_form_for_step(order, step, data=None):
    kwargs = {} if data is None else {'data': data}
    if step == 2:
        return QuestionsStepForm(
            service_id=order.subcategory_id,
            stored_answers=wizard_initial(order, 2), **kwargs,
        )
    if step == 3:
        return STEP_FORMS[step](
            service=order.subcategory,
            initial=wizard_initial(order, step), **kwargs,
        )
    return STEP_FORMS[step](initial=wizard_initial(order, step), **kwargs)


@login_required
@never_cache
def order_wizard_start_view(request):
    """Default visible entry point; older POST /orders/create/ remains compatible."""
    ensure_wizard_owner(request.user)
    if request.method == 'POST':
        if request.POST.get('action') != 'start':
            raise Http404
        form = ServiceStepForm(request.POST)
        token = request.POST.get('token', '')
        invite_worker_value = request.POST.get('invite_worker', '')
        try:
            invite_worker_id = int(invite_worker_value) if invite_worker_value else None
        except (TypeError, ValueError):
            raise Http404 from None
        if form.is_valid():
            # Per-session token prevents accidental repeat creation across taps.
            if token != request.session.get('order_wizard_token'):
                raise Http404
            try:
                order = start_order_wizard(
                    actor=request.user, form=form, token=token,
                    invite_worker_id=invite_worker_id,
                )
            except OrderQuotaExceeded as error:
                return _order_quota_response(error)
            except ValueError as error:
                form.add_error(None, str(error))
            else:
                request.session.pop('order_wizard_token', None)
                return redirect('marketplace:order_wizard_edit', pk=order.pk)
    else:
        token = str(uuid.uuid4())
        request.session['order_wizard_token'] = token
        initial = {}
        worker_id = request.GET.get('worker', '')
        if worker_id:
            worker = get_object_or_404(public_worker_queryset(), pk=worker_id)
            if worker.user_id == request.user.pk:
                raise Http404
            selected_service = worker.services.filter(
                is_active=True, category__is_active=True,
                category__in=worker.skills.all(),
            ).order_by('pk').first()
            if selected_service:
                initial = {
                    'category': selected_service.category_id,
                    'subcategory': selected_service.pk,
                }
            request._invite_worker_pk = worker.pk
        form = ServiceStepForm(initial=initial)
    if request.method == 'POST':
        request._invite_worker_pk = invite_worker_id
    drafts = Order.objects.filter(
        client=request.user, status=Order.Status.DRAFT,
        wizard_token__isnull=False,
    ).select_related('subcategory').order_by('-updated_at', '-pk')[:10]
    return _wizard_render(
        request, step=1, form=form,
        token=request.session.get('order_wizard_token', ''),
        drafts=drafts,
    )


@login_required
@never_cache
def order_wizard_edit_view(request, pk):
    """Resume any saved step but never expose draft state across owners."""
    ensure_wizard_owner(request.user)
    order = get_owner_wizard(pk, request.user)
    if order is None:
        raise Http404
    if order.status == Order.Status.PUBLISHED:
        return redirect('marketplace:order_detail', pk=order.pk)
    if order.status != Order.Status.DRAFT:
        raise Http404

    latest = wizard_max_step(order)
    try:
        step = int(request.GET.get('step', latest))
    except (TypeError, ValueError):
        raise Http404 from None
    if not 1 <= step <= 8:
        raise Http404
    if step > latest:
        return redirect(
            reverse('marketplace:order_wizard_edit', args=[pk]) + f'?step={latest}'
        )
    if request.method == 'POST':
        if request.POST.get('action') != ('publish' if step == 8 else 'next'):
            raise Http404
        form = _wizard_form_for_step(order, step, request.POST)
        if form.is_valid():
            try:
                if step == 8:
                    published, created = publish_order_wizard(
                        order_id=order.pk, actor=request.user,
                        confirmation_form=form,
                    )
                    _flush_order_events(published)
                    invite_id = (published.wizard_data or {}).get('invite_worker_id')
                    if invite_id and worker_matches_order(invite_id, published):
                        return redirect(
                            reverse('marketplace:worker_invitation_select', args=[invite_id])
                            + f'?order={published.pk}'
                        )
                    return redirect('marketplace:order_detail', pk=published.pk)
                saved = save_order_wizard_step(
                    order_id=order.pk, actor=request.user,
                    step=step, form=form,
                    uploads=request.FILES.getlist('photos') if step == 6 else (),
                    photo_visibility=(
                        request.POST.get('photo_visibility', 'private')
                        if step == 6 else 'private'
                    ),
                    public_consent=(
                        request.POST.get('public_photo_consent') == 'on'
                        if step == 6 else False
                    ),
                )
                next_step = min(step + 1, wizard_max_step(saved))
                return redirect(
                    reverse('marketplace:order_wizard_edit', args=[pk])
                    + f'?step={next_step}'
                )
            except OrderQuotaExceeded as error:
                return _order_quota_response(error)
            except ValueError as error:
                form.add_error(None, str(error))
        # Re-render bound fields and errors without losing the draft.
    else:
        form = _wizard_form_for_step(order, step)
    return _wizard_render(request, step=step, form=form, order=order)



@require_GET
@never_cache
def order_attachment_image_view(request, pk):
    """Stream a normalized JPEG only to explicitly entitled viewers."""
    photo = get_object_or_404(
        OrderAttachment.objects.select_related('order'), pk=pk,
    )
    if not can_read_order_photo(photo, request.user):
        raise Http404
    try:
        key = order_attachment_key(photo)
        source = private_portfolio_storage().open(key, 'rb')
    except (OrderPhotoError, OSError, FileNotFoundError):
        raise Http404 from None
    response = FileResponse(
        source, content_type='image/jpeg', as_attachment=False,
        filename='order-photo.jpg',
    )
    response['Cache-Control'] = 'private, no-store, max-age=0'
    response['X-Content-Type-Options'] = 'nosniff'
    response['Content-Security-Policy'] = "default-src 'none'; sandbox"
    response['X-Robots-Tag'] = 'noindex, nofollow, noarchive'
    return response


@login_required
@require_POST
@never_cache
def order_attachment_delete_view(request, pk):
    """Revoke previously granted image access without waiting for stage 04.5."""
    try:
        order = delete_order_photo(photo_id=pk, actor=request.user)
    except (OrderPhotoError, PermissionDenied):
        raise Http404 from None
    if order.status == Order.Status.DRAFT:
        return redirect(
            reverse('marketplace:order_wizard_edit', args=[order.pk]) + '?step=6'
        )
    return redirect('marketplace:order_detail', pk=order.pk)




@login_required
@never_cache
def order_management_edit_view(request, pk):
    """Edit all safe conditions pre-assignment; require POST for mutations."""
    order = get_object_or_404(
        Order.objects.select_related('category', 'subcategory'), pk=pk,
        client=request.user,
    )
    ensure_wizard_owner(request.user)
    if request.method not in ('GET', 'POST'):
        raise Http404
    if order.worker_id or order.status not in (
        Order.Status.PUBLISHED, Order.Status.IN_DISCUSSION,
    ):
        raise Http404
    if request.method == 'POST':
        try:
            result, changed = edit_published_order(
                order_id=order.pk, actor=request.user, data=request.POST,
                operation_key=request.POST.get('operation_key'),
            )
        except OrderQuotaExceeded as error:
            return _order_quota_response(error)
        except ValueError as exc:
            form = OrderEditForm(request.POST, order=order)
            form.is_valid()
            form.add_error(None, str(exc))
        else:
            if isinstance(result, OrderEditForm):
                form = result
            else:
                if changed:
                    messages.success(request, wizard_copy()['edit_saved'])
                _flush_order_events(order)
                return redirect('marketplace:order_detail', pk=order.pk)
    else:
        form = OrderEditForm(order=order)
    return render(request, 'pages/order_management_edit.html', {
        'form': form, 'order': order, 'copy': wizard_copy(),
        'operation_key': (request.POST.get('operation_key')
                          if request.method == 'POST' else uuid.uuid4()),
        'seo_noindex': True,
    })


@login_required
@require_POST
@never_cache
def order_management_withdraw_view(request, pk):
    get_object_or_404(Order, pk=pk, client=request.user)
    try:
        order, _ = withdraw_order(
            order_id=pk, actor=request.user,
            operation_key=request.POST.get('operation_key'),
        )
    except OrderQuotaExceeded as error:
        return _order_quota_response(error)
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect('marketplace:order_detail', pk=pk)
    return redirect('marketplace:order_wizard_edit', pk=order.pk)


@login_required
@require_POST
@never_cache
def order_management_duplicate_view(request, pk):
    get_object_or_404(Order, pk=pk, client=request.user)
    try:
        clone, _ = duplicate_order(
            order_id=pk, actor=request.user,
            operation_key=request.POST.get('operation_key'),
        )
    except OrderQuotaExceeded as error:
        return _order_quota_response(error)
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect('marketplace:order_detail', pk=pk)
    _flush_order_events(clone)
    return redirect('marketplace:order_wizard_edit', pk=clone.pk)




@login_required
def order_detail_view(request, pk):
    order = get_object_or_404(
        Order.objects.select_related('category', 'subcategory', 'city', 'client', 'worker'),
        pk=pk,
    )
    if order.status == Order.Status.DRAFT:
        if order.client_id != request.user.pk or not order.wizard_token:
            raise Http404
        return redirect('marketplace:order_wizard_edit', pk=order.pk)
    worker_response = None
    has_worker_profile = False
    is_owner = False
    existing_rating = None
    responses = []

    if request.user.is_authenticated:
        # Persisted account gates must guard even GET projections: a blocked or
        # unverified owner must not read private offers via a stale session.
        from apps.accounts.models import User
        account_enabled = User.objects.filter(
            pk=request.user.pk, is_active=True, is_blocked=False,
            email_verification_required=False,
        ).exists()
        has_worker_profile = account_enabled and hasattr(
            request.user, 'worker_profile',
        )
        is_owner = account_enabled and order.client_id == request.user.pk

        if has_worker_profile:
            worker_response = Response.objects.filter(
                order=order, worker=request.user
            ).first()

        if is_owner:
            responses = list(Response.objects.filter(
                order=order
            ).select_related('worker').order_by('-created_at'))

            existing_rating = Rating.objects.filter(order=order).first()

    can_read_private = can_view_private_order_details(request.user, order)
    private_question_answers = []
    if can_read_private:
        snapshot = OrderQuestionnaireAnswer.objects.select_related(
            'version',
        ).filter(order=order).first()
        if snapshot is not None:
            private_question_answers = present_order_answers(snapshot)

    agreement_context = private_agreement_context(order, request.user)
    work_party = bool(agreement_context['agreement_current'])
    work_started = False
    work_result_submitted = False
    if work_party:
        from .models import OrderWorkEvent
        work_started = OrderWorkEvent.objects.filter(
            order=order, action=OrderWorkEvent.Action.STARTED,
        ).exists()
        work_result_submitted = OrderWorkEvent.objects.filter(
            order=order, action=OrderWorkEvent.Action.RESULT_SUBMITTED,
        ).exists()

    # Accept only known sort and filter keys, and only apply them to the
    # owner-authorized offer projection (never to another user's order).
    offer_options = owner_offer_filter_context(
        status_filter=request.GET.get('offer_status', 'all'),
        sort=request.GET.get('offer_sort', 'newest'),
    )
    owner_cards = owner_offer_cards(order, responses) if is_owner else []
    visible_cards = filter_and_sort_offer_cards(
        owner_cards, status_filter=offer_options['offer_status_selected'],
        sort=offer_options['offer_sort_selected'],
    ) if is_owner else []

    return render(request, 'pages/order_detail.html', {
        'order': order,
        'private_question_answers': private_question_answers,
        'worker_response': worker_response,
        'has_worker_profile': has_worker_profile,
        'is_owner': is_owner,
        'responses': responses,
        'offer_cards': visible_cards,
        'offer_total_count': len(owner_cards),
        **offer_options,
        'offer_copy': offer_copy(),
        'selected_worker_public_name': selected_worker_public_name(order) if is_owner else '',
        **agreement_context,
        'work_started': work_started,
        'work_result_submitted': work_result_submitted,
        'existing_rating': existing_rating,
        'can_view_private_details': can_read_private,
        'order_photos': list(visible_order_photos(order, request.user)),
        'structured_info': [
            (wizard_copy()['area'], order.approximate_area),
            (wizard_copy()['mode'], wizard_copy().get(order.work_mode, '')),
            (wizard_copy()['date'], order.preferred_date),
            (wizard_copy()['urgency'], wizard_copy().get(order.urgency, '')),
        ] if order.price_kind != Order.PriceKind.LEGACY else [],
        'photo_is_owner': is_owner,
        'can_edit_order': is_owner and order.worker_id is None
            and order.status in (Order.Status.PUBLISHED, Order.Status.IN_DISCUSSION),
        'can_withdraw_order': is_owner and order.worker_id is None
            and order.status in (Order.Status.PUBLISHED, Order.Status.IN_DISCUSSION)
            and not Response.objects.filter(order=order).exists(),
        'can_cancel_order': is_owner and order.status in (
            Order.Status.DRAFT, Order.Status.PUBLISHED,
            Order.Status.IN_DISCUSSION, Order.Status.ASSIGNED,
            Order.Status.IN_PROGRESS, Order.Status.DISPUTED,
        ),
        'order_history': management_timeline(order) if is_owner else [],
        'management_copy': wizard_copy(),
        'operation_withdraw': uuid.uuid4(),
        'operation_duplicate': uuid.uuid4(),
    })


@login_required
def client_dashboard_view(request):
    profile = get_client_profile(request.user)
    if not profile:
        return redirect('accounts:client_profile')

    # Four independent, bounded slices: 1000 historical orders must not
    # inflate a single HTML response or disclose another client's orders.
    my_orders = Order.objects.filter(
        client=request.user
    ).select_related('category', 'city', 'worker').order_by('-created_at', '-pk')

    draft_orders = Paginator(
        my_orders.filter(status=Order.Status.DRAFT),
        ITEMS_PER_PAGE,
    ).get_page(request.GET.get('draft_page'))

    active_orders = Paginator(
        my_orders.filter(status__in=(
            Order.Status.PUBLISHED, Order.Status.IN_DISCUSSION,
        )).annotate(
            response_count=Count('responses')
        ),
        ITEMS_PER_PAGE,
    ).get_page(request.GET.get('active_page'))

    in_progress_orders = Paginator(
        my_orders.filter(status__in=(
            Order.Status.ASSIGNED, Order.Status.IN_PROGRESS, Order.Status.DISPUTED,
        )),
        ITEMS_PER_PAGE,
    ).get_page(request.GET.get('progress_page'))

    completed_orders = Paginator(
        my_orders.filter(status=Order.Status.COMPLETED),
        ITEMS_PER_PAGE,
    ).get_page(request.GET.get('completed_page'))

    cancelled_orders = Paginator(
        my_orders.filter(status__in=(Order.Status.CANCELLED, Order.Status.EXPIRED)),
        ITEMS_PER_PAGE,
    ).get_page(request.GET.get('cancelled_page'))

    orders_with_responses = [
        {'order': order, 'response_count': order.response_count}
        for order in active_orders
    ]

    return render(request, 'pages/client_dashboard.html', {
        'profile': profile,
        'draft_orders': draft_orders,
        'management_copy': wizard_copy(),
        'active_orders': active_orders,
        'in_progress_orders': in_progress_orders,
        'completed_orders': completed_orders,
        'cancelled_orders': cancelled_orders,
        'orders_with_responses': orders_with_responses,
        'favorite_workers': own_visible_favorites(request.user)[:12],
        'viewed_workers': own_visible_worker_history(request.user)[:12]
            if profile.track_worker_views else [],
        'track_worker_views': profile.track_worker_views,
        'directory_copy': directory_copy(),
        'client_invitations': OrderInvitation.objects.filter(
            client_id=request.user.pk,
        ).select_related(
            'order', 'order__category', 'order__city', 'worker', 'worker__user',
        )[:20],
        'invite_copy': invitation_copy(),
    })

@login_required
def order_accept_response_view(request, order_id, response_id):
    if request.method != 'POST':
        raise Http404

    order = get_object_or_404(Order, pk=order_id, client=request.user)
    response = get_object_or_404(Response, pk=response_id, order=order)

    try:
        # The choice, agreement snapshot, status history and ALL in-app
        # notifications must commit together. An error on the second notice
        # rolls the first notice and the winner selection back as well.
        with transaction.atomic():
            response = accept_response(response, actor=request.user)
            if getattr(response, '_assignment_created', False):
                create_notification(
                    recipient=response.worker,
                    **stage06_notice(response.worker, 'response_accepted', order.pk),
                    notification_type='response_accepted',
                    related_order=order,
                    related_response=response,
                )
                from apps.accounts.models import User
                for worker_id in response._rejected_worker_ids:
                    worker_user = User.objects.filter(pk=worker_id).first()
                    if worker_user:
                        create_notification(
                            recipient=worker_user,
                            **stage06_notice(worker_user, 'response_rejected', order.pk),
                            notification_type='response_rejected',
                            related_order=order,
                        )
    except OrderQuotaExceeded as error:
        return _order_quota_response(error)
    except ValueError as error:
        messages.error(request, _(str(error)))
        return redirect('marketplace:order_detail', pk=order.pk)

    messages.success(request, _('Мастер %(worker)s выбран!') % {
        'worker': selected_worker_public_name(order),
    })
    return redirect('marketplace:order_detail', pk=order.pk)


@login_required
def order_cancel_view(request, pk):
    if request.method != 'POST':
        raise Http404

    # Serialize status evaluation with the transition. A competitor can
    # finish/cancel the same order after an initial GET but before our POST.
    changed = False
    with transaction.atomic():
        order = get_object_or_404(
            Order.objects.select_for_update(), pk=pk, client=request.user,
        )
        allowed = (
            Order.Status.DRAFT, Order.Status.PUBLISHED,
            Order.Status.IN_DISCUSSION, Order.Status.ASSIGNED,
            Order.Status.IN_PROGRESS, Order.Status.DISPUTED,
        )
        if order.status in allowed:
            try:
                cancel_order(order, actor=request.user)
            except OrderQuotaExceeded as error:
                return _order_quota_response(error)
            except ValueError:
                messages.error(request, wizard_copy()['cancel_conflict'])
            else:
                changed = True
        elif order.status != Order.Status.CANCELLED:
            messages.error(request, wizard_copy()['cancel_conflict'])
    if changed:
        _flush_order_events(order)
        messages.success(request, _('Заявка отменена.'))
    return redirect('marketplace:order_detail', pk=pk)


@login_required
def order_complete_view(request, pk):
    if request.method != 'POST':
        raise Http404

    # The notification is committed in the SAME transaction as the first
    # successful state transition, while the row lock prevents double sends.
    with transaction.atomic():
        order = get_object_or_404(
            Order.objects.select_for_update(), pk=pk, client=request.user,
        )
        if order.status == Order.Status.IN_PROGRESS:
            try:
                complete_order(order, actor=request.user)
            except OrderQuotaExceeded as error:
                return _order_quota_response(error)
            except ValueError:
                messages.error(request, wizard_copy()['complete_conflict'])
            else:
                if order.worker_id:
                    create_notification(
                        recipient=order.worker,
                        **stage06_notice(order.worker, 'order_completed', order.pk),
                        notification_type='order_completed',
                        related_order=order,
                    )
                messages.success(request, _('Заявка отмечена как выполненная!'))
        elif order.status != Order.Status.COMPLETED:
            messages.error(request, wizard_copy()['complete_conflict'])
    return redirect('marketplace:order_detail', pk=pk)


@login_required
@require_POST
@never_cache
def order_work_action_view(request, pk, action):
    """A work transition and its notice are a single PostgreSQL transaction."""
    from .work_services import (
        report_work_problem, start_work, submit_work_result,
    )
    if action not in ('start', 'result', 'problem'):
        raise Http404
    order = get_object_or_404(
        Order.objects.filter(
            Q(client_id=request.user.pk) | Q(worker_id=request.user.pk),
        ), pk=pk,
    )
    try:
        with transaction.atomic():
            if action == 'start':
                order, changed = start_work(
                    order_id=order.pk, actor=request.user,
                    operation_key=request.POST.get('operation_key'),
                )
            elif action == 'result':
                order, changed = submit_work_result(
                    order_id=order.pk, actor=request.user,
                    operation_key=request.POST.get('operation_key'),
                )
            else:
                order, changed = report_work_problem(
                    order_id=order.pk, actor=request.user,
                    problem_code=request.POST.get('problem_code'),
                    operation_key=request.POST.get('operation_key'),
                )
            if changed:
                recipient_id = (
                    order.client_id if request.user.pk == order.worker_id
                    else order.worker_id
                )
                if recipient_id:
                    from apps.accounts.models import User
                    recipient = User.objects.filter(pk=recipient_id).first()
                    if recipient:
                        create_notification(
                            recipient=recipient,
                            **stage06_notice(recipient, 'order_updated', order.pk),
                            notification_type='order_updated',
                            related_order=order,
                        )
    except OrderQuotaExceeded as error:
        return _order_quota_response(error)
    except ValueError:
        messages.error(request, offer_copy()['action_error'])
        return redirect('marketplace:order_detail', pk=order.pk)
    if changed:
        messages.success(request, offer_copy()['status_updated'])
    return redirect('marketplace:order_detail', pk=order.pk)


@login_required
def rating_create_view(request, pk):
    """A review and its worker notification commit atomically under Order lock.

    Locking the Order also serializes duplicate client POSTs, including those
    where the first notification temporarily fails. No review or recipient
    notice may survive that failure by itself.
    """
    order = get_object_or_404(
        Order, pk=pk, client=request.user, status=Order.Status.COMPLETED,
    )
    if Rating.objects.filter(order=order).exists():
        messages.info(request, _('Вы уже оставили отзыв на этот заказ.'))
        return redirect('marketplace:order_detail', pk=pk)
    if not order.worker_id:
        messages.error(request, _('Невозможно оставить отзыв: исполнитель не выбран.'))
        return redirect('marketplace:order_detail', pk=pk)

    if request.method == 'POST':
        form = RatingCreateForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                # Re-read the persisted order after concurrent completion,
                # cancellation or another review; lock before duplicate check.
                order = get_object_or_404(
                    Order.objects.select_for_update(),
                    pk=pk, client=request.user, status=Order.Status.COMPLETED,
                )
                if Rating.objects.filter(order=order).exists():
                    messages.info(request, _('Вы уже оставили отзыв на этот заказ.'))
                    return redirect('marketplace:order_detail', pk=pk)
                if not order.worker_id:
                    messages.error(
                        request, _('Невозможно оставить отзыв: исполнитель не выбран.'),
                    )
                    return redirect('marketplace:order_detail', pk=pk)
                rating = form.save(commit=False)
                rating.order = order
                rating.worker_id = order.worker_id
                rating.client = request.user
                rating.save()
                create_notification(
                    recipient=order.worker,
                    **stage06_notice(order.worker, 'review_created', order.pk),
                    notification_type='review_created',
                    related_order=order,
                )
            messages.success(request, _('Отзыв сохранён!'))
            return redirect('marketplace:order_detail', pk=pk)
    else:
        form = RatingCreateForm()

    return render(request, 'pages/rating_create.html', {
        'order': order,
        'form': form,
    })


@login_required
def worker_dashboard_view(request):
    profile = get_worker_profile(request.user)
    if not profile:
        return redirect('accounts:worker_profile')

    available_orders = get_available_orders_for_worker(profile)
    paginator = Paginator(available_orders, ITEMS_PER_PAGE)
    orders_page = paginator.get_page(request.GET.get('page'))

    my_responses = Response.objects.filter(
        worker=request.user
    ).select_related('order', 'order__category', 'order__city').order_by('-created_at')[:20]

    return render(request, 'pages/worker_dashboard.html', {
        'profile': profile,
        'page_obj': orders_page,
        'my_responses': my_responses,
        'worker_invitations': OrderInvitation.objects.filter(
            worker=profile,
        ).select_related(
            'order', 'order__category', 'order__subcategory',
            'order__city', 'worker', 'worker__user',
        )[:20],
        'invite_copy': invitation_copy(),
    })


@login_required
def order_respond_view(request, pk):
    profile = get_worker_profile(request.user)
    if not profile or not profile.is_published or request.user.is_blocked:
        messages.warning(
            request, _('Для откликов сначала опубликуйте анкету мастера.'),
        )
        return redirect('accounts:worker_profile')
    if public_city_slug() and not city_is_public(profile.city):
        raise Http404

    order = get_object_or_404(
        Order.objects.select_related('category', 'subcategory', 'city').filter(
            city__in=get_public_cities(), status=Order.Status.PUBLISHED,
        ), pk=pk,
    )

    if order.client_id == request.user.pk:
        messages.error(request, _('Нельзя откликнуться на собственную заявку.'))
        return redirect('marketplace:order_detail', pk=order.pk)

    if not get_available_orders_for_worker(profile).filter(pk=order.pk).exists():
        raise Http404

    existing = Response.objects.filter(order=order, worker=request.user).first()
    if existing:
        messages.info(request, _('Вы уже откликались на этот заказ.'))
        return redirect('marketplace:order_detail', pk=pk)

    if request.method == 'POST':
        form = ResponseCreateForm(request.POST)
        if form.is_valid():
            try:
                # The response/revision and customer notice share one commit.
                # If notification creation fails, the response can be retried
                # with the same operation_key without a ghost successful reply.
                with transaction.atomic():
                    response, created = submit_offer(
                        order=order, actor=request.user,
                        message=form.cleaned_data['message'],
                        data=form.cleaned_data,
                        operation_key=request.POST.get('operation_key'),
                    )
                    if created and order.client:
                        create_notification(
                            recipient=order.client,
                            **stage06_notice(order.client, 'new_response', order.pk),
                            notification_type='new_response',
                            related_order=order,
                        )

                messages.success(request, _('Отклик отправлен!'))
                return redirect('marketplace:order_detail', pk=pk)
            except OrderQuotaExceeded as error:
                return _order_quota_response(error)
            except ValueError as e:
                messages.error(request, _(str(e)))
    else:
        form = ResponseCreateForm()

    return render(request, 'pages/offer_form.html', {
        'order': order, 'form': form, 'response': None,
        'offer_copy': offer_copy(), 'page_title': offer_copy()['submit'],
        'submit_label': offer_copy()['submit'],
        'operation_key': request.POST.get('operation_key') or uuid.uuid4(),
    })
