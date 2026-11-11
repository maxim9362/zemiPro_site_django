"""Isolated settings for Django's test runner; never use a live PostgreSQL host."""
from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403


ENVIRONMENT = 'test'
DEBUG = False
SECRET_KEY = 'django-insecure-test-environment-key-not-for-deployment'
ALLOWED_HOSTS = ['testserver', 'localhost', '127.0.0.1']
CSRF_TRUSTED_ORIGINS = []

# Fail closed if someone attempts to execute tests against a remote PostgreSQL.
# Docker service names below are appropriate only for isolated test containers.
if DATABASES['default']['HOST'].lower() not in {
    'localhost', '127.0.0.1', '::1', 'db', 'postgres'
}:
    raise ImproperlyConfigured(
        'DJANGO_ENV=test requires local/isolated PostgreSQL (DB_HOST).'
    )

DATABASES['default']['TEST'] = {'NAME': 'test_zemipro_db'}
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_HSTS_SECONDS = 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False

EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
