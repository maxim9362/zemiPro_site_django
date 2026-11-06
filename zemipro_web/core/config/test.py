from .base import *  # noqa: F403


ENVIRONMENT = 'test'
DEBUG = False
SECRET_KEY = 'django-insecure-test-environment-key-not-for-real-deployments'
ALLOWED_HOSTS = ['testserver', 'localhost', '127.0.0.1']
CSRF_TRUSTED_ORIGINS = []

SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_HSTS_SECONDS = 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False

EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
