from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.locations.services import city_is_public

from .models import User, ClientProfile, WorkerProfile


def _validate_public_profile_cities(form_data):
    """Enforce the pilot boundary even for direct service/API callers."""
    city = form_data.get('city')
    if city is not None and not city_is_public(city):
        raise ValueError('Город пока не обслуживается.')
    service_cities = form_data.get('service_cities')
    if service_cities is not None and any(
        not city_is_public(item) for item in service_cities
    ):
        raise ValueError('Город обслуживания пока не доступен.')


def create_client_profile(user, city=None, contact=''):
    """Создать профиль заказчика для пользователя."""
    _validate_public_profile_cities({'city': city})
    profile, created = ClientProfile.objects.get_or_create(
        user=user,
        defaults={'city': city, 'contact': contact},
    )
    return profile


@transaction.atomic
def create_or_update_client_profile(user, form_data):
    """Создать или обновить профиль клиента."""
    _validate_public_profile_cities(form_data)
    profile, created = ClientProfile.objects.get_or_create(user=user)
    profile.city = form_data.get('city', profile.city)
    profile.contact = form_data.get('contact', profile.contact)
    profile.save()

    select_active_role(user, User.ActiveRole.CLIENT)
    return profile


def get_client_profile(user):
    """Получить профиль клиента или None."""
    try:
        return user.client_profile
    except ClientProfile.DoesNotExist:
        return None


def _locked_worker_owner(user):
    if not user.is_authenticated or user.pk is None:
        raise PermissionDenied(_('Требуется вход в аккаунт.'))
    owner = User.objects.select_for_update().get(pk=user.pk)
    if not owner.is_active or owner.is_blocked:
        raise PermissionDenied(_('Аккаунт недоступен.'))
    return owner


def publication_issue(profile):
    """Shared publication criteria; reused after editing a published profile."""
    if not profile.user.is_active or profile.user.is_blocked:
        return _('Аккаунт недоступен.')
    if not profile.display_name.strip():
        return _('Укажите публичное имя или название компании.')
    if not profile.city_id or not city_is_public(profile.city):
        return _('Выберите обслуживаемый город.')
    if len(profile.description.strip()) < 20:
        return _('Для публикации укажите описание минимум 20 символов.')
    if not profile.pricing_details.strip():
        return _('Укажите ориентировочные цены или принцип расчёта.')
    languages = profile.spoken_languages
    if (not isinstance(languages, list) or not languages
            or len(languages) != len(set(languages))
            or any(code not in ('ru', 'en', 'he') for code in languages)):
        return _('Выберите языки общения.')
    if profile.provider_type not in WorkerProfile.ProviderType.values:
        return _('Выберите тип исполнителя.')
    if profile.availability not in WorkerProfile.Availability.values:
        return _('Укажите доступность.')
    if profile.service_cities.exclude(pk__in=get_public_cities()).exists():
        return _('Город обслуживания пока не доступен.')
    skills = profile.skills.filter(is_active=True).filter(
        Q(section__isnull=True) | Q(section__is_active=True)
    )
    if not skills.exists() or profile.skills.exclude(pk__in=skills).exists():
        return _('Выберите активные категории услуг.')
    if profile.offers_remote and not skills.filter(work_mode__in=('online', 'both')).exists():
        return _('Для онлайн-работы выберите услугу с онлайн-форматом.')
    return None


@transaction.atomic
def create_or_update_worker_profile(user, form_data):
    """Update own draft without changing publication, verification or identity."""
    owner = _locked_worker_owner(user)
    _validate_public_profile_cities(form_data)
    profile, _ = WorkerProfile.objects.select_for_update().get_or_create(user=owner)
    fields = (
        'provider_type', 'display_name', 'city', 'contact', 'description',
        'pricing_details', 'spoken_languages', 'availability', 'working_hours',
        'receive_notifications',
    )
    for name in fields:
        if name in form_data:
            setattr(profile, name, form_data[name])
    if 'offers_remote' in form_data:
        profile.offers_remote = bool(form_data['offers_remote'])
    profile.full_clean()
    profile.save()
    if 'skills' in form_data:
        profile.skills.set(form_data['skills'])
    if 'service_cities' in form_data:
        profile.service_cities.set(form_data['service_cities'])
    if profile.is_published and publication_issue(profile):
        profile.is_published = False
        profile.published_at = None
        profile.save(update_fields=['is_published', 'published_at', 'updated_at'])
    select_active_role(user, User.ActiveRole.WORKER)
    return profile


@transaction.atomic
def set_worker_publication(user, publish):
    """Explicit owner publication switch; never accepts a supplied profile id."""
    owner = _locked_worker_owner(user)
    profile = WorkerProfile.objects.select_for_update().select_related(
        'user', 'city',
    ).filter(user=owner).first()
    if profile is None:
        raise ValueError(_('Сначала заполните профиль мастера.'))
    if publish:
        error = publication_issue(profile)
        if error:
            raise ValueError(error)
        profile.is_published = True
        if not profile.published_at:
            profile.published_at = timezone.now()
    else:
        profile.is_published = False
        profile.published_at = None
    profile.save(update_fields=['is_published', 'published_at', 'updated_at'])
    return profile


def get_worker_profile(user):
    """Получить профиль мастера или None."""
    try:
        return user.worker_profile
    except WorkerProfile.DoesNotExist:
        return None


@transaction.atomic
def select_active_role(user, role):
    """Select a dashboard, not a privilege. No profile or historical order is deleted.

    In particular, switching to worker does NOT create a blank, publicly
    discoverable WorkerProfile. Completion of the worker form is required.
    """
    if role not in User.ActiveRole.values:
        raise ValueError('Недопустимая роль.')
    if not user.is_authenticated or user.pk is None:
        raise PermissionDenied('Требуется вход в аккаунт.')
    stored = User.objects.select_for_update().get(pk=user.pk)
    if not stored.is_active or stored.is_blocked:
        raise PermissionDenied('Аккаунт недоступен.')
    if stored.active_role != role:
        stored.active_role = role
        stored.save(update_fields=['active_role'])
    user.active_role = stored.active_role
    return stored.active_role
