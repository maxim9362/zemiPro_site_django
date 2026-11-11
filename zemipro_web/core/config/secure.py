"""Staging/production must fail closed on missing or insecure configuration."""
from django.core.exceptions import ImproperlyConfigured

from .env import (
    database_config,
    env_bool,
    env_list,
    env_nonnegative_int,
    explicit_allowed_hosts,
    strong_secret_key,
)


def build_secure_settings(default_hsts_seconds, include_subdomains, preload):
    # An operator must not disable HTTPS or secure cookies by accident.
    for variable in (
        'DJANGO_SECURE_SSL_REDIRECT',
        'DJANGO_SESSION_COOKIE_SECURE',
        'DJANGO_CSRF_COOKIE_SECURE',
    ):
        if not env_bool(variable, True):
            raise ImproperlyConfigured(
                f'{variable} must be true for staging and production.'
            )
    hsts_seconds = env_nonnegative_int(
        'DJANGO_SECURE_HSTS_SECONDS', default_hsts_seconds
    )
    return {
        'DEBUG': False,
        'SECRET_KEY': strong_secret_key(),
        'ALLOWED_HOSTS': explicit_allowed_hosts(),
        'CSRF_TRUSTED_ORIGINS': env_list('DJANGO_CSRF_TRUSTED_ORIGINS'),
        'DATABASES': database_config(require_credentials=True),
        'SECURE_SSL_REDIRECT': True,
        'SESSION_COOKIE_SECURE': True,
        'CSRF_COOKIE_SECURE': True,
        'SECURE_HSTS_SECONDS': hsts_seconds,
        # HSTS preload and includeSubDomains opt in only after HTTPS verification.
        'SECURE_HSTS_INCLUDE_SUBDOMAINS': env_bool(
            'DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS', include_subdomains
        ),
        'SECURE_HSTS_PRELOAD': env_bool(
            'DJANGO_SECURE_HSTS_PRELOAD', preload
        ),
        **({
            'SECURE_PROXY_SSL_HEADER': ('HTTP_X_FORWARDED_PROTO', 'https')
        } if env_bool('DJANGO_TRUST_X_FORWARDED_PROTO', False) else {}),
    }
