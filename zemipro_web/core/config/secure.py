from .env import (
    database_config,
    env,
    env_bool,
    env_list,
    explicit_allowed_hosts,
    strong_secret_key,
)


def build_secure_settings(default_hsts_seconds, include_subdomains, preload):
    settings = {
        'DEBUG': False,
        'SECRET_KEY': strong_secret_key(),
        'ALLOWED_HOSTS': explicit_allowed_hosts(),
        'CSRF_TRUSTED_ORIGINS': env_list('DJANGO_CSRF_TRUSTED_ORIGINS'),
        'DATABASES': database_config(require_credentials=True),
        'SECURE_SSL_REDIRECT': env_bool('DJANGO_SECURE_SSL_REDIRECT', True),
        'SESSION_COOKIE_SECURE': env_bool('DJANGO_SESSION_COOKIE_SECURE', True),
        'CSRF_COOKIE_SECURE': env_bool('DJANGO_CSRF_COOKIE_SECURE', True),
        'SECURE_HSTS_SECONDS': int(env(
            'DJANGO_SECURE_HSTS_SECONDS',
            str(default_hsts_seconds),
        )),
        'SECURE_HSTS_INCLUDE_SUBDOMAINS': env_bool(
            'DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS',
            include_subdomains,
        ),
        'SECURE_HSTS_PRELOAD': env_bool(
            'DJANGO_SECURE_HSTS_PRELOAD',
            preload,
        ),
    }
    if env_bool('DJANGO_TRUST_X_FORWARDED_PROTO', False):
        settings['SECURE_PROXY_SSL_HEADER'] = ('HTTP_X_FORWARDED_PROTO', 'https')
    return settings
