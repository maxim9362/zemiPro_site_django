from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Avg, Count, Q
from django.http import Http404
from django.shortcuts import render, get_object_or_404, redirect

from apps.accounts.forms import RatingCreateForm
from apps.accounts.models import WorkerProfile
from apps.accounts.services import get_client_profile, get_worker_profile
from apps.locations.models import City
from apps.notifications.services import create_notification
from .forms import OrderCreateForm, ResponseCreateForm
from .models import Category, Order, Response, Rating
from .services import (
    get_available_orders_for_worker, create_response,
    accept_response, complete_order, cancel_order,
    can_view_private_order_details,
)

ITEMS_PER_PAGE = 10


def home(request):
    categories = Category.objects.filter(is_active=True).order_by('sort_order')
    return render(request, 'pages/home.html', {'categories': categories})


def categories_list(request):
    categories = Category.objects.filter(is_active=True).order_by('sort_order')
    return render(request, 'pages/categories.html', {'categories': categories})


def category_detail(request, slug):
    category = get_object_or_404(Category, slug=slug, is_active=True)
    cities = City.objects.filter(is_active=True).order_by('name_ru')
    selected_city = request.GET.get('city')

    workers = WorkerProfile.objects.filter(
        skills=category, user__is_active=True
    ).select_related('city', 'user').annotate(
        avg_rating=Avg('user__received_ratings__rating'),
        review_count=Count('user__received_ratings', distinct=True),
    ).order_by('-avg_rating')

    if selected_city:
        workers = workers.filter(city__slug=selected_city)

    paginator = Paginator(workers, ITEMS_PER_PAGE)
    page = paginator.get_page(request.GET.get('page'))

    return render(request, 'pages/category_detail.html', {
        'category': category,
        'page_obj': page,
        'cities': cities,
        'selected_city': selected_city,
    })


def cities_list(request):
    cities = City.objects.filter(is_active=True).order_by('name_ru')
    return render(request, 'pages/cities.html', {'cities': cities})


def city_detail(request, slug):
    city = get_object_or_404(City, slug=slug, is_active=True)
    categories = Category.objects.filter(is_active=True).order_by('sort_order')
    selected_category = request.GET.get('category')

    workers = WorkerProfile.objects.filter(
        city=city, user__is_active=True
    ).select_related('user').annotate(
        avg_rating=Avg('user__received_ratings__rating'),
        review_count=Count('user__received_ratings', distinct=True),
    ).order_by('-avg_rating')

    if selected_category:
        workers = workers.filter(skills__slug=selected_category)

    paginator = Paginator(workers, ITEMS_PER_PAGE)
    page = paginator.get_page(request.GET.get('page'))

    return render(request, 'pages/city_detail.html', {
        'city': city,
        'categories': categories,
        'page_obj': page,
        'selected_category': selected_category,
    })


def worker_public_profile_view(request, pk):
    profile = get_object_or_404(
        WorkerProfile.objects.select_related('city', 'user'),
        pk=pk,
    )
    reviews = Rating.objects.filter(
        worker=profile.user
    ).select_related('client').order_by('-created_at')

    avg_rating = reviews.aggregate(avg=Avg('rating'))['avg'] or 0
    review_count = reviews.count()

    return render(request, 'pages/worker_public_profile.html', {
        'profile': profile,
        'reviews': reviews[:10],
        'avg_rating': round(avg_rating, 1),
        'review_count': review_count,
    })


@login_required
def order_create_view(request):
    initial = {}
    if request.user.is_authenticated:
        profile = get_client_profile(request.user)
        if profile:
            initial = {'city': profile.city}

    if request.method == 'POST':
        form = OrderCreateForm(request.POST)
        if form.is_valid():
            order = form.save(commit=False)
            order.client = request.user
            order.save()

            create_notification(
                recipient=request.user,
                title='Заявка создана',
                message=f'Ваша заявка №{order.pk} успешно создана. Мастера смогут откликнуться на неё.',
                notification_type='order_created',
                related_order=order,
            )

            return redirect('marketplace:order_detail', pk=order.pk)
    else:
        form = OrderCreateForm(initial=initial)

    return render(request, 'pages/order_create.html', {'form': form})


@login_required
def order_detail_view(request, pk):
    order = get_object_or_404(
        Order.objects.select_related('category', 'subcategory', 'city', 'client', 'worker'),
        pk=pk,
    )
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

    return render(request, 'pages/order_detail.html', {
        'order': order,
        'worker_response': worker_response,
        'has_worker_profile': has_worker_profile,
        'is_owner': is_owner,
        'responses': responses,
        'existing_rating': existing_rating,
        'can_view_private_details': can_view_private_order_details(request.user, order),
    })


@login_required
def client_dashboard_view(request):
    profile = get_client_profile(request.user)
    if not profile:
        return redirect('accounts:client_profile')

    my_orders = Order.objects.filter(
        client=request.user
    ).select_related('category', 'city').order_by('-created_at')

    active_orders = my_orders.filter(status=Order.Status.NEW)
    in_progress_orders = my_orders.filter(status=Order.Status.IN_PROGRESS)
    completed_orders = my_orders.filter(status=Order.Status.COMPLETED)
    cancelled_orders = my_orders.filter(status=Order.Status.CANCELLED)

    orders_with_responses = []
    for order in list(active_orders) + list(in_progress_orders):
        resp_count = Response.objects.filter(order=order).count()
        orders_with_responses.append({'order': order, 'response_count': resp_count})

    return render(request, 'pages/client_dashboard.html', {
        'profile': profile,
        'active_orders': active_orders,
        'in_progress_orders': in_progress_orders,
        'completed_orders': completed_orders,
        'cancelled_orders': cancelled_orders,
        'orders_with_responses': orders_with_responses,
    })


@login_required
def order_accept_response_view(request, order_id, response_id):
    if request.method != 'POST':
        raise Http404

    order = get_object_or_404(Order, pk=order_id, client=request.user, status=Order.Status.NEW)
    response = get_object_or_404(Response, pk=response_id, order=order)

    rejected_workers = list(
        Response.objects.filter(order=order).exclude(pk=response.pk).values_list('worker_id', flat=True)
    )

    try:
        response = accept_response(response)
    except ValueError as error:
        messages.error(request, str(error))
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

    messages.success(request, f'Мастер {response.worker} выбран!')
    return redirect('marketplace:order_detail', pk=order.pk)


@login_required
def order_cancel_view(request, pk):
    if request.method != 'POST':
        raise Http404

    order = get_object_or_404(Order, pk=pk, client=request.user, status=Order.Status.NEW)

    responding_workers = list(
        Response.objects.filter(order=order).values_list('worker_id', flat=True)
    )

    cancel_order(order)

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

    messages.success(request, 'Заявка отменена.')
    return redirect('marketplace:order_detail', pk=pk)


@login_required
def order_complete_view(request, pk):
    if request.method != 'POST':
        raise Http404

    order = get_object_or_404(Order, pk=pk, client=request.user, status=Order.Status.IN_PROGRESS)
    complete_order(order)

    if order.worker:
        create_notification(
            recipient=order.worker,
            title='Заявка завершена',
            message=f'Клиент отметил заявку №{order.pk} как выполненную.',
            notification_type='order_completed',
            related_order=order,
        )

    messages.success(request, 'Заявка отмечена как выполненная!')
    return redirect('marketplace:order_detail', pk=pk)


@login_required
def rating_create_view(request, pk):
    order = get_object_or_404(
        Order, pk=pk, client=request.user, status=Order.Status.COMPLETED
    )

    if Rating.objects.filter(order=order).exists():
        messages.info(request, 'Вы уже оставили отзыв на этот заказ.')
        return redirect('marketplace:order_detail', pk=pk)

    if not order.worker:
        messages.error(request, 'Невозможно оставить отзыв: исполнитель не выбран.')
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

            messages.success(request, 'Отзыв сохранён!')
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
    if not profile:
        messages.warning(request, 'Сначала заполните профиль мастера.')
        return redirect('accounts:worker_profile')

    order = get_object_or_404(Order, pk=pk, status=Order.Status.NEW)

    if order.client_id == request.user.pk:
        messages.error(request, 'Нельзя откликнуться на собственную заявку.')
        return redirect('marketplace:order_detail', pk=order.pk)

    existing = Response.objects.filter(order=order, worker=request.user).first()
    if existing:
        messages.info(request, 'Вы уже откликались на этот заказ.')
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

                messages.success(request, 'Отклик отправлен!')
                return redirect('marketplace:order_detail', pk=pk)
            except ValueError as e:
                messages.error(request, str(e))
    else:
        form = ResponseCreateForm()

    return render(request, 'pages/order_respond.html', {
        'order': order,
        'form': form,
    })
