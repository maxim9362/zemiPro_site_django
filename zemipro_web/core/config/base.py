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

LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/client/dashboard/'
LOGOUT_REDIRECT_URL = '/'
PASSWORD_RESET_TIMEOUT = 3600
# External contact delivery is explicitly disabled until a provider is
# configured and accepted before the first public release.
ZEMIPRO_CONTACT_DELIVERY_MODE = 'disabled'
EMAIL_BACKEND = 'django.core.mail.backends.dummy.EmailBackend'
DEFAULT_FROM_EMAIL = 'noreply@zemipro.invalid'

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
