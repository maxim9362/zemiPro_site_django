"""Select a Django configuration using the DJANGO_ENV environment variable."""

import os
from importlib import import_module
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv


load_dotenv(Path(__file__).resolve().parent.parent / '.env', override=False)

ENVIRONMENT_MODULES = {
    'development': 'core.config.development',
    'test': 'core.config.test',
    'staging': 'core.config.staging',
    'production': 'core.config.production',
}

ENVIRONMENT = os.getenv('DJANGO_ENV', 'development').strip().lower()
module_path = ENVIRONMENT_MODULES.get(ENVIRONMENT)
if module_path is None:
    allowed = ', '.join(ENVIRONMENT_MODULES)
    raise ImproperlyConfigured(
        f'Unsupported DJANGO_ENV={ENVIRONMENT!r}. Expected one of: {allowed}.'
    )

environment_settings = import_module(module_path)
for setting_name in dir(environment_settings):
    if setting_name.isupper():
        globals()[setting_name] = getattr(environment_settings, setting_name)
