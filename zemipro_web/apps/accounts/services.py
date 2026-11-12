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


def create_or_update_client_profile(user, form_data):
    """Создать или обновить профиль клиента."""
    _validate_public_profile_cities(form_data)
    profile, created = ClientProfile.objects.get_or_create(user=user)
    profile.city = form_data.get('city', profile.city)
    profile.contact = form_data.get('contact', profile.contact)
    profile.save()

    if created or user.role != User.Role.CLIENT:
        user.role = User.Role.CLIENT
        user.save(update_fields=['role'])

    return profile


def get_client_profile(user):
    """Получить профиль клиента или None."""
    try:
        return user.client_profile
    except ClientProfile.DoesNotExist:
        return None


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

    if created or user.role != User.Role.WORKER:
        user.role = User.Role.WORKER
        user.save(update_fields=['role'])

    return profile


def get_worker_profile(user):
    """Получить профиль мастера или None."""
    try:
        return user.worker_profile
    except WorkerProfile.DoesNotExist:
        return None
