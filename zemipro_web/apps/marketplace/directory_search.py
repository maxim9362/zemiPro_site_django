"""Read-only public specialist search, backed by existing PostgreSQL models.

All filters are conjunctive. Invalid form input fails closed; no guessed
service matches, geodistances, prices, or review scores are generated.
"""
from decimal import Decimal

from django import forms
from django.db.models import Avg, Count, Exists, F, OuterRef, Q
from django.db.models.functions import Lower
from django.utils.translation import gettext_lazy as _

from apps.accounts.client_favorites import public_worker_queryset
from apps.accounts.models import WorkerProfile
from apps.locations.models import City
from apps.locations.services import get_public_cities, public_city_slug
from .models import Category, Subcategory
from .services import workers_serving_city


def active_categories():
    return Category.objects.filter(is_active=True).filter(
        Q(section__isnull=True) | Q(section__is_active=True)
    )


def active_services():
    return Subcategory.objects.filter(
        is_active=True, category__is_active=True,
    ).filter(
        Q(category__section__isnull=True) | Q(category__section__is_active=True)
    )


class WorkerDirectoryForm(forms.Form):
    q = forms.CharField(
        max_length=100, required=False, strip=True,
        label=_('Ключевые слова'),
        widget=forms.TextInput(attrs={'placeholder': _('Имя или специализация')}),
    )
    category = forms.ModelChoiceField(
        queryset=active_categories().order_by('sort_order', 'pk'),
        empty_label=_('Все категории'), required=False, label=_('Категория'),
    )
    service = forms.ModelChoiceField(
        queryset=active_services().order_by('category_id', 'sort_order', 'pk'),
        empty_label=_('Все конкретные услуги'), required=False,
        label=_('Конкретная услуга'),
    )
    city = forms.ModelChoiceField(
        queryset=City.objects.none(), required=False,
        empty_label=_('Город пилота'), label=_('Город'),
    )
    language = forms.ChoiceField(
        required=False, label=_('Язык общения'),
        choices=(
            ('', _('Любой язык')), ('ru', _('Русский')),
            ('en', _('Английский')), ('he', _('Иврит')),
        ),
    )
    mode = forms.ChoiceField(
        required=False, label=_('Формат работы'),
        choices=(
            ('', _('Любой формат')),
            ('onsite', _('Выезд / локально')),
            ('online', _('Онлайн')),
        ),
    )
    price_from = forms.DecimalField(
        required=False, max_digits=10, decimal_places=2, min_value=Decimal('0'),
        label=_('Стартовая цена от (₪)'),
    )
    price_to = forms.DecimalField(
        required=False, max_digits=10, decimal_places=2, min_value=Decimal('0'),
        label=_('Стартовая цена до (₪)'),
    )
    min_rating = forms.DecimalField(
        required=False, max_digits=2, decimal_places=1,
        min_value=Decimal('1.0'), max_value=Decimal('5.0'),
        label=_('Минимальный реальный рейтинг'),
    )
    availability = forms.ChoiceField(
        required=False, label=_('Доступность (по заявлению мастера)'),
        choices=(('', _('Любая доступность')), *WorkerProfile.Availability.choices),
    )
    sort = forms.ChoiceField(
        required=False, label=_('Сортировка'),
        choices=(
            ('rating', _('Рейтинг (реальные отзывы)')),
            ('price_asc', _('Стартовая цена: по возрастанию')),
            ('price_desc', _('Стартовая цена: по убыванию')),
            ('newest', _('Недавно опубликованные')),
            ('name', _('Имя по алфавиту')),
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['city'].queryset = get_public_cities().order_by('name_ru', 'pk')

    def clean(self):
        data = super().clean()
        category, service = data.get('category'), data.get('service')
        if category and service and service.category_id != category.pk:
            self.add_error('service', _('Услуга не принадлежит выбранной категории.'))
        if (data.get('price_from') is not None
                and data.get('price_to') is not None
                and data['price_from'] > data['price_to']):
            self.add_error('price_to', _('Цена до должна быть не меньше цены от.'))
        return data


def _onsite_in_city(queryset, city):
    """Only an explicitly served city or the unconfigured home-city fallback."""
    through = WorkerProfile.service_cities.through
    zones = through.objects.filter(workerprofile_id=OuterRef('pk'))
    return queryset.alias(
        _search_has_zones=Exists(zones),
        _search_serves_city=Exists(zones.filter(city_id=city.pk)),
    ).filter(
        Q(_search_serves_city=True)
        | Q(_search_has_zones=False, city_id=city.pk)
    )


def search_worker_profiles(form):
    """Return safe, stable, paginatable public results with *actual* DB ratings."""
    if not form.is_valid():
        return WorkerProfile.objects.none()

    params = form.cleaned_data
    category = params['category']
    service = params['service']
    selected_category = category or (service.category if service else None)
    city = params['city']
    if city is None and public_city_slug():
        city = get_public_cities().first()

    workers = public_worker_queryset()
    if selected_category:
        belongs_to_category = active_categories().filter(
            pk=selected_category.pk, workers=OuterRef('pk'),
        )
        workers = workers.alias(
            _category_match=Exists(belongs_to_category)
        ).filter(_category_match=True)
    if service:
        offers_service = active_services().filter(
            pk=service.pk, workers=OuterRef('pk'),
        )
        workers = workers.alias(
            _service_match=Exists(offers_service)
        ).filter(_service_match=True)
    if city:
        workers = workers_serving_city(workers, city, category=selected_category)

    query = params['q']
    if query:
        matching_categories = active_categories().filter(
            workers=OuterRef('pk'),
        ).filter(
            Q(name_ru__icontains=query)
            | Q(name_en__icontains=query)
            | Q(name_he__icontains=query)
        )
        matching_services = active_services().filter(
            workers=OuterRef('pk'),
        ).filter(
            Q(name_ru__icontains=query)
            | Q(name_en__icontains=query)
            | Q(name_he__icontains=query)
        )
        workers = workers.alias(
            _search_category_text=Exists(matching_categories),
            _search_service_text=Exists(matching_services),
        ).filter(
            Q(display_name__icontains=query)
            | Q(description__icontains=query)
            | Q(_search_category_text=True)
            | Q(_search_service_text=True)
        )

    if params['language']:
        # PostgreSQL JSONB array containment: exact language code, not substring.
        workers = workers.filter(spoken_languages__contains=[params['language']])
    if params['availability']:
        workers = workers.filter(availability=params['availability'])
    if params['price_from'] is not None:
        workers = workers.filter(starting_price_ils__gte=params['price_from'])
    if params['price_to'] is not None:
        workers = workers.filter(starting_price_ils__lte=params['price_to'])

    mode = params['mode']
    if mode == 'online':
        if (service and service.work_mode not in ('online', 'both')) or (
            not service and category and category.work_mode not in ('online', 'both')
        ):
            return workers.none()
        workers = workers.filter(offers_remote=True)
        if selected_category is None:
            online_skill = active_categories().filter(
                workers=OuterRef('pk'), work_mode__in=('online', 'both'),
            )
            workers = workers.alias(
                _has_online_skill=Exists(online_skill)
            ).filter(_has_online_skill=True)
    elif mode == 'onsite':
        if (service and service.work_mode == 'online') or (
            not service and category and category.work_mode == 'online'
        ):
            return workers.none()
        if selected_category is None:
            onsite_skill = active_categories().filter(
                workers=OuterRef('pk'), work_mode__in=('onsite', 'both'),
            )
            workers = workers.alias(
                _has_onsite_skill=Exists(onsite_skill)
            ).filter(_has_onsite_skill=True)
        if city:
            workers = _onsite_in_city(workers, city)

    # The join is only to actual Rating rows; an unrated worker stays NULL.
    workers = workers.annotate(
        avg_rating=Avg('user__received_ratings__rating'),
        review_count=Count('user__received_ratings', distinct=True),
    )
    if params['min_rating'] is not None:
        workers = workers.filter(avg_rating__gte=params['min_rating'])

    sort = params['sort'] or 'rating'
    if sort == 'price_asc':
        return workers.order_by(F('starting_price_ils').asc(nulls_last=True), 'pk')
    if sort == 'price_desc':
        return workers.order_by(F('starting_price_ils').desc(nulls_last=True), 'pk')
    if sort == 'name':
        return workers.order_by(Lower('display_name'), 'pk')
    if sort == 'newest':
        return workers.order_by(F('published_at').desc(nulls_last=True), 'pk')
    return workers.order_by(F('avg_rating').desc(nulls_last=True), 'pk')
