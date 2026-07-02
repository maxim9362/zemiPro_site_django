from django.db import transaction

from .models import User, ClientProfile, WorkerProfile


def create_client_profile(user, city=None, contact=''):
    """Создать профиль заказчика для пользователя."""
    profile, created = ClientProfile.objects.get_or_create(
        user=user,
        defaults={'city': city, 'contact': contact},
    )
    return profile


def create_or_update_client_profile(user, form_data):
    """Создать или обновить профиль клиента."""
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
    profile, created = WorkerProfile.objects.get_or_create(user=user)

    profile.city = form_data.get('city', profile.city)
    profile.contact = form_data.get('contact', profile.contact)
    profile.description = form_data.get('description', profile.description)
    profile.receive_notifications = form_data.get('receive_notifications', profile.receive_notifications)
    profile.save()

    skills = form_data.get('skills')
    if skills is not None:
        profile.skills.set(skills)

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
