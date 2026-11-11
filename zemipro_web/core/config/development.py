from .base import *  # noqa: F403
from .env import env, env_bool, env_list


ENVIRONMENT = 'development'
DEBUG = env_bool('DJANGO_DEBUG', True)
SECRET_KEY = env(
    'DJANGO_SECRET_KEY',
    'django-insecure-development-only-key-never-use-in-production',
)
ALLOWED_HOSTS = env_list('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1')
CSRF_TRUSTED_ORIGINS = env_list('DJANGO_CSRF_TRUSTED_ORIGINS')

SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_HSTS_SECONDS = 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False
