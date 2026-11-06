import os

from django.core.exceptions import ImproperlyConfigured


TRUE_VALUES = {'1', 'true', 'yes', 'on'}
FALSE_VALUES = {'0', 'false', 'no', 'off'}


def env(name, default=None):
    return os.getenv(name, default)


def env_bool(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    raise ImproperlyConfigured(
        f'{name} must be one of: true/false, yes/no, on/off, 1/0.'
    )


def env_list(name, default=''):
    value = os.getenv(name, default)
    return [item.strip() for item in value.split(',') if item.strip()]


def required_env(name):
    value = os.getenv(name)
    if value is None or not value.strip():
        raise ImproperlyConfigured(f'{name} must be set for this environment.')
    return value


def database_config(require_credentials=False):
    getter = required_env if require_credentials else env
    password = (
        getter('DB_PASSWORD')
        if require_credentials
        else env('DB_PASSWORD', 'postgres')
    )
    if require_credentials and password.strip().lower() in {
        'postgres', 'password', 'change-me', 'changeme'
    }:
        raise ImproperlyConfigured(
            'DB_PASSWORD must not use a known development placeholder.'
        )
    return {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': getter('DB_NAME') if require_credentials else env('DB_NAME', 'zemipro_db'),
            'USER': getter('DB_USER') if require_credentials else env('DB_USER', 'postgres'),
            'PASSWORD': password,
            'HOST': getter('DB_HOST') if require_credentials else env('DB_HOST', 'localhost'),
            'PORT': env('DB_PORT', '5432'),
        }
    }


def strong_secret_key():
    secret_key = required_env('DJANGO_SECRET_KEY')
    if (
        secret_key.startswith('django-insecure-')
        or len(secret_key) < 50
        or len(set(secret_key)) < 5
    ):
        raise ImproperlyConfigured(
            'DJANGO_SECRET_KEY must be a strong value of at least 50 characters.'
        )
    return secret_key


def explicit_allowed_hosts():
    hosts = env_list('DJANGO_ALLOWED_HOSTS')
    if not hosts or '*' in hosts:
        raise ImproperlyConfigured(
            'DJANGO_ALLOWED_HOSTS must contain explicit hosts and cannot use "*".'
        )
    return hosts
