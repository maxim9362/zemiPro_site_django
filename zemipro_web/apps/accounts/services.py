from django.core.exceptions import PermissionDenied
from django.db import transaction

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


@transaction.atomic
def create_or_update_worker_profile(user, form_data):
    """Создать или обновить профиль мастера. Возвращает профиль."""
    _validate_public_profile_cities(form_data)
    profile, created = WorkerProfile.objects.get_or_create(user=user)

    profile.city = form_data.get('city', profile.city)
    profile.contact = form_data.get('contact', profile.contact)
    profile.description = form_data.get('description', profile.description)
    profile.receive_notifications = form_data.get('receive_notifications', profile.receive_notifications)
    profile.save()

    skills = form_data.get('skills')
    if skills is not None:
        profile.skills.set(skills)

    if 'service_cities' in form_data:
        profile.service_cities.set(form_data['service_cities'])
    if 'offers_remote' in form_data:
        profile.offers_remote = bool(form_data['offers_remote'])
        profile.save(update_fields=['offers_remote', 'updated_at'])

    select_active_role(user, User.ActiveRole.WORKER)
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
