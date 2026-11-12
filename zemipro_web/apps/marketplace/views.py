from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.core.exceptions import PermissionDenied
from django.db.models import Avg, Count, F, Prefetch, Q
from django.http import FileResponse, Http404, JsonResponse, HttpResponsePermanentRedirect
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST
from django.utils.translation import gettext as _

from apps.accounts.forms import RatingCreateForm
from apps.accounts.models import FavoriteWorker
from apps.accounts.client_favorites import (
    own_visible_favorites, toggle_own_favorite, public_worker_queryset,
)
from apps.accounts.models import WorkerProfile
from apps.accounts.services import get_client_profile, get_worker_profile
from apps.locations.models import CityAlias
from apps.locations.services import city_is_public, get_public_cities, public_city_slug
from apps.notifications.services import create_notification
from .catalog_seo import catalog_context, complete_collection, complete_content, complete_names
from .questionnaires import localized_label
from .questionnaire_services import present_order_answers
from .forms import OrderCreateForm, ResponseCreateForm
from .models import (
    Category, ServiceSection, Subcategory, Order, Response, Rating,
    ServiceQuestionnaire, OrderQuestionnaireAnswer,
)
from .services import (
    get_available_orders_for_worker, create_response, create_order,
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
from .order_management import (
    OrderEditForm, duplicate_order, edit_published_order,
    management_timeline, owner_order, withdraw_order,
)
from .attachment_services import (
    OrderPhotoError, can_read_order_photo, delete_order_photo,
    order_attachment_key, visible_order_photos,
)
from apps.accounts.portfolio import private_portfolio_storage
from .models import OrderAttachment

ITEMS_PER_PAGE = 10


def home(request):
    categories = Category.objects.filter(is_active=True).filter(
        Q(section__isnull=True) | Q(section__is_active=True)
    ).order_by('sort_order', 'pk')
    return render(request, 'pages/home.html', {'categories': categories})


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
    workers = public_worker_queryset().prefetch_related('skills', 'service_cities')
    if public_city_slug():
        pilot_city = get_public_cities().first()
        workers = (
            workers_serving_city(workers, pilot_city)
            if pilot_city is not None else workers.none()
        )
    profile = get_object_or_404(workers, pk=pk)
    reviews = Rating.objects.filter(
        worker=profile.user
    ).select_related('client').order_by('-created_at')

    avg_rating = reviews.aggregate(avg=Avg('rating'))['avg'] or 0
    review_count = reviews.count()

    return render(request, 'pages/worker_public_profile.html', {
        'profile': profile,
        'public_photos': profile.portfolio_photos.filter(is_public=True),
        'reviews': reviews[:10],
        'avg_rating': round(avg_rating, 1),
        'review_count': review_count,
        'is_favorite': (
            request.user.is_authenticated
            and FavoriteWorker.objects.filter(
                client=request.user, worker=profile,
            ).exists()
        ),
    })


@login_required
def toggle_favorite_worker_view(request, pk):
    """Add/remove the authenticated user's private favorite via POST only."""
    if request.method != 'POST':
        raise Http404
    worker = get_object_or_404(
        WorkerProfile.objects.select_related('user'), pk=pk,
    )
    try:
        toggle_own_favorite(request.user, worker)
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
        except ValueError as error:
            form.add_error(None, str(error))
        else:
            if created:
                create_notification(
                    recipient=request.user,
                    title='Заявка создана',
                    message=f'Ваша заявка №{order.pk} успешно создана.',
                    notification_type='order_created',
                    related_order=order,
                )
            return redirect('marketplace:order_detail', pk=order.pk)
    return render(request, 'pages/order_create.html', {
        'form': form, 'seo_noindex': True,
        'order_contact_privacy': wizard_copy()['privacy'],
        'wizard_link_label': wizard_copy()['heading'],
    })



def _wizard_render(request, *, step, form, order=None, token='', drafts=None):
    t = wizard_copy()
    return render(request, 'pages/order_wizard.html', {
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
        if form.is_valid():
            # Per-session token prevents accidental repeat creation across taps.
            if token != request.session.get('order_wizard_token'):
                raise Http404
            try:
                order = start_order_wizard(
                    actor=request.user, form=form, token=token,
                )
            except ValueError as error:
                form.add_error(None, str(error))
            else:
                request.session.pop('order_wizard_token', None)
                return redirect('marketplace:order_wizard_edit', pk=order.pk)
    else:
        token = str(uuid.uuid4())
        request.session['order_wizard_token'] = token
        form = ServiceStepForm()
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
                    )
                    if created:
                        create_notification(
                            recipient=request.user, title='Заявка создана',
                            message=f'Ваша заявка №{published.pk} опубликована.',
                            notification_type='order_created', related_order=published,
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
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect('marketplace:order_detail', pk=pk)
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
        has_worker_profile = hasattr(request.user, 'worker_profile')
        is_owner = order.client == request.user

        if has_worker_profile:
            worker_response = Response.objects.filter(
                order=order, worker=request.user
            ).first()

        if is_owner:
            responses = Response.objects.filter(
                order=order
            ).select_related('worker').order_by('-created_at')

            existing_rating = Rating.objects.filter(order=order).first()

    can_read_private = can_view_private_order_details(request.user, order)
    private_question_answers = []
    if can_read_private:
        snapshot = OrderQuestionnaireAnswer.objects.select_related(
            'version',
        ).filter(order=order).first()
        if snapshot is not None:
            private_question_answers = present_order_answers(snapshot)

    return render(request, 'pages/order_detail.html', {
        'order': order,
        'private_question_answers': private_question_answers,
        'worker_response': worker_response,
        'has_worker_profile': has_worker_profile,
        'is_owner': is_owner,
        'responses': responses,
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
    })

@login_required
def order_accept_response_view(request, order_id, response_id):
    if request.method != 'POST':
        raise Http404

    order = get_object_or_404(Order, pk=order_id, client=request.user, status=Order.Status.PUBLISHED)
    response = get_object_or_404(Response, pk=response_id, order=order)

    rejected_workers = list(
        Response.objects.filter(order=order).exclude(pk=response.pk).values_list('worker_id', flat=True)
    )

    try:
        response = accept_response(response, actor=request.user)
    except ValueError as error:
        messages.error(request, _(str(error)))
        return redirect('marketplace:order_detail', pk=order.pk)

    create_notification(
        recipient=response.worker,
        title='Вас выбрали',
        message=f'Клиент выбрал вас исполнителем по заявке №{order.pk}.',
        notification_type='response_accepted',
        related_order=order,
        related_response=response,
    )

    from apps.accounts.models import User
    for worker_id in rejected_workers:
        try:
            worker_user = User.objects.get(pk=worker_id)
            create_notification(
                recipient=worker_user,
                title='Выбран другой мастер',
                message=f'По заявке №{order.pk} клиент выбрал другого мастера.',
                notification_type='response_rejected',
                related_order=order,
            )
        except User.DoesNotExist:
            continue

    messages.success(request, _('Мастер %(worker)s выбран!') % {'worker': response.worker})
    return redirect('marketplace:order_detail', pk=order.pk)


@login_required
def order_cancel_view(request, pk):
    if request.method != 'POST':
        raise Http404

    order = get_object_or_404(
        Order, pk=pk, client=request.user, status__in=(
            Order.Status.DRAFT, Order.Status.PUBLISHED,
            Order.Status.IN_DISCUSSION, Order.Status.ASSIGNED,
            Order.Status.IN_PROGRESS, Order.Status.DISPUTED,
        ),
    )

    responding_workers = list(
        Response.objects.filter(order=order).values_list('worker_id', flat=True)
    )

    cancel_order(order, actor=request.user)

    from apps.accounts.models import User
    for worker_id in responding_workers:
        try:
            worker_user = User.objects.get(pk=worker_id)
            create_notification(
                recipient=worker_user,
                title='Заявка отменена',
                message=f'Заявка №{order.pk}, на которую вы откликались, была отменена клиентом.',
                notification_type='order_cancelled',
                related_order=order,
            )
        except User.DoesNotExist:
            continue

    messages.success(request, _('Заявка отменена.'))
    return redirect('marketplace:order_detail', pk=pk)


@login_required
def order_complete_view(request, pk):
    if request.method != 'POST':
        raise Http404

    order = get_object_or_404(Order, pk=pk, client=request.user, status=Order.Status.IN_PROGRESS)
    complete_order(order, actor=request.user)

    if order.worker:
        create_notification(
            recipient=order.worker,
            title='Заявка завершена',
            message=f'Клиент отметил заявку №{order.pk} как выполненную.',
            notification_type='order_completed',
            related_order=order,
        )

    messages.success(request, _('Заявка отмечена как выполненная!'))
    return redirect('marketplace:order_detail', pk=pk)


@login_required
def rating_create_view(request, pk):
    order = get_object_or_404(
        Order, pk=pk, client=request.user, status=Order.Status.COMPLETED
    )

    if Rating.objects.filter(order=order).exists():
        messages.info(request, _('Вы уже оставили отзыв на этот заказ.'))
        return redirect('marketplace:order_detail', pk=pk)

    if not order.worker:
        messages.error(request, _('Невозможно оставить отзыв: исполнитель не выбран.'))
        return redirect('marketplace:order_detail', pk=pk)

    if request.method == 'POST':
        form = RatingCreateForm(request.POST)
        if form.is_valid():
            rating = form.save(commit=False)
            rating.order = order
            rating.worker = order.worker
            rating.client = request.user
            rating.save()

            create_notification(
                recipient=order.worker,
                title='Новый отзыв',
                message=f'Клиент оставил отзыв по заявке №{order.pk}.',
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
        Order.objects.select_related('category', 'city').filter(
            city__in=get_public_cities()
        ),
        pk=pk, status=Order.Status.PUBLISHED,
    )

    if order.client_id == request.user.pk:
        messages.error(request, _('Нельзя откликнуться на собственную заявку.'))
        return redirect('marketplace:order_detail', pk=order.pk)

    existing = Response.objects.filter(order=order, worker=request.user).first()
    if existing:
        messages.info(request, _('Вы уже откликались на этот заказ.'))
        return redirect('marketplace:order_detail', pk=pk)

    if request.method == 'POST':
        form = ResponseCreateForm(request.POST)
        if form.is_valid():
            try:
                create_response(
                    order=order,
                    worker_user=request.user,
                    message=form.cleaned_data['message'],
                )

                if order.client:
                    create_notification(
                        recipient=order.client,
                        title='Новый отклик',
                        message=f'Мастер откликнулся на вашу заявку №{order.pk}.',
                        notification_type='new_response',
                        related_order=order,
                    )

                messages.success(request, _('Отклик отправлен!'))
                return redirect('marketplace:order_detail', pk=pk)
            except ValueError as e:
                messages.error(request, _(str(e)))
    else:
        form = ResponseCreateForm()

    return render(request, 'pages/order_respond.html', {
        'order': order,
        'form': form,
    })
