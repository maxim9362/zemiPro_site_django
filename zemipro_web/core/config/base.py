import os

from django.core.exceptions import ImproperlyConfigured

from pathlib import Path

from dotenv import load_dotenv

from .env import database_config, env_bool


BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / '.env', override=False)

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',
    'apps.accounts',
    'apps.marketplace',
    'apps.locations',
    'apps.seo',
    'apps.notifications',
    'apps.moderation',
    'apps.analytics',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'core.middleware.LegacySafeLocaleMiddleware',
    'django.middleware.common.CommonMiddleware',
    'core.middleware.DynamicHtmlNoStoreMiddleware',
    'core.middleware.SensitivePostThrottleMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'allauth.account.middleware.AccountMiddleware',
    'core.middleware.BlockedAccountMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'core.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'apps.notifications.context_processors.notifications_counter',
            ],
        },
    },
]

WSGI_APPLICATION = 'core.wsgi.application'
ASGI_APPLICATION = 'core.asgi.application'
DATABASES = database_config()

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'ru'
LANGUAGES = [
    ('ru', 'Русский'),
    ('en', 'English'),
    ('he', 'עברית'),
]
TIME_ZONE = 'Asia/Jerusalem'
USE_I18N = True
LOCALE_PATHS = [BASE_DIR / 'locale']
# New prefixed catalog pages remain noindex until explicit editorial/SEO approval.
ZEMIPRO_CATALOG_INDEXING_ENABLED = env_bool('ZEMIPRO_CATALOG_INDEXING_ENABLED', False)
# Owner-approved first public pilot: only Ashdod. Expansion requires a code review.
# Not environment-overridable, so a production .env cannot silently open all cities.
ZEMIPRO_PILOT_CITY_SLUG = 'ashdod'
# Stage 07.6: external AI translation is strictly opt-in and disabled by default.
# The API key is never stored in code, test fixtures or logs.
ZEMIPRO_GEMINI_TRANSLATION_ENABLED = env_bool(
    'ZEMIPRO_GEMINI_TRANSLATION_ENABLED', False,
)
ZEMIPRO_GEMINI_TRANSLATION_API_KEY = os.environ.get(
    'ZEMIPRO_GEMINI_TRANSLATION_API_KEY', '',
).strip()
ZEMIPRO_GEMINI_TRANSLATION_MODEL = os.environ.get(
    'ZEMIPRO_GEMINI_TRANSLATION_MODEL', 'gemini-2.5-flash-lite',
).strip()

USE_TZ = True

STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'
# Stage 03.5: never expose worker portfolio originals through MEDIA_URL/static serving.
# Deployment must mount persistent, private storage with backups before public release.
ZEMIPRO_PRIVATE_MEDIA_ROOT = BASE_DIR / 'private_media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
AUTH_USER_MODEL = 'accounts.User'
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]

# Existing username/password forms remain Django-native. allauth serves only OAuth.
SOCIALACCOUNT_ONLY = True
SOCIALACCOUNT_LOGIN_ON_GET = False
SOCIALACCOUNT_AUTO_SIGNUP = True
SOCIALACCOUNT_EMAIL_AUTHENTICATION = False
SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT = False
SOCIALACCOUNT_STORE_TOKENS = False
# allauth local-account flows are disabled; our separate Django email OTP
# performs local proof and our social adapter requires verified Google email.
ACCOUNT_EMAIL_VERIFICATION = 'none'
SOCIALACCOUNT_EMAIL_VERIFICATION = 'none'
SOCIALACCOUNT_ADAPTER = 'apps.accounts.social_adapter.ZemiProGoogleAdapter'
SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'SCOPE': ['email', 'profile'],
        'AUTH_PARAMS': {'access_type': 'online'},
        'OAUTH_PKCE_ENABLED': True,
    },
}
ZEMIPRO_GOOGLE_LOGIN_ENABLED = env_bool('ZEMIPRO_GOOGLE_LOGIN_ENABLED', False)
if ZEMIPRO_GOOGLE_LOGIN_ENABLED:
    client_id = os.environ.get('ZEMIPRO_GOOGLE_CLIENT_ID', '').strip()
    client_secret = os.environ.get('ZEMIPRO_GOOGLE_CLIENT_SECRET', '').strip()
    if not client_id or not client_secret:
        raise ImproperlyConfigured('Enabled Google OAuth requires client credentials.')
    SOCIALACCOUNT_PROVIDERS['google']['APP'] = {
        'client_id': client_id,
        'secret': client_secret,
        'key': '',
    }


LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/client/dashboard/'
LOGOUT_REDIRECT_URL = '/'
PASSWORD_RESET_TIMEOUT = 3600
# No SMS at any runtime. SMTP is opt-in, never enabled by default.
ZEMIPRO_CONTACT_DELIVERY_MODE = os.environ.get(
    'ZEMIPRO_CONTACT_DELIVERY_MODE', 'disabled',
).strip().lower()
if ZEMIPRO_CONTACT_DELIVERY_MODE not in ('disabled', 'test-email', 'smtp'):
    raise ImproperlyConfigured('Invalid ZEMIPRO_CONTACT_DELIVERY_MODE.')
EMAIL_BACKEND = 'django.core.mail.backends.dummy.EmailBackend'
DEFAULT_FROM_EMAIL = 'noreply@zemipro.invalid'
if ZEMIPRO_CONTACT_DELIVERY_MODE == 'smtp':
    host = os.environ.get('ZEMIPRO_SMTP_HOST', '').strip()
    username = os.environ.get('ZEMIPRO_SMTP_USERNAME', '').strip()
    password = os.environ.get('ZEMIPRO_SMTP_PASSWORD', '').strip()
    sender = os.environ.get('ZEMIPRO_EMAIL_FROM', '').strip()
    try:
        port = int(os.environ.get('ZEMIPRO_SMTP_PORT', '587'))
    except ValueError as exc:
        raise ImproperlyConfigured('Invalid SMTP port.') from exc
    if not all((host, username, password, sender)) or '@' not in sender or not 1 <= port <= 65535:
        raise ImproperlyConfigured('SMTP requires valid credentials, host, sender and port.')
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
    EMAIL_HOST = host
    EMAIL_PORT = port
    EMAIL_HOST_USER = username
    EMAIL_HOST_PASSWORD = password
    EMAIL_USE_TLS = True
    EMAIL_USE_SSL = False
    EMAIL_TIMEOUT = 10
    DEFAULT_FROM_EMAIL = sender

# Optional Stage 07 worker can only be enabled with approved SMTP delivery.
ZEMIPRO_STAGE07_EMAIL_ENABLED = (
    env_bool('ZEMIPRO_STAGE07_EMAIL_ENABLED', False)
    and ZEMIPRO_CONTACT_DELIVERY_MODE == 'smtp'
)


# Structured logs deliberately exclude request paths, query strings, headers,
# exception messages, tracebacks and user input. Use stable events only.
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'safe_json': {'()': 'core.observability.SafeJsonFormatter'},
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'safe_json',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'WARNING',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
        'django.request': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
        'django.security': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
        'django.server': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
        'django.db.backends': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': False,
        },
        'zemipro': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}

# Only when Caddy overwrites X-Real-IP on an isolated internal network.
THROTTLE_TRUST_X_REAL_IP = env_bool('ZEMIPRO_TRUST_X_REAL_IP', False)
