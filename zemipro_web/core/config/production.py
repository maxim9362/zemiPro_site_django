from .base import *  # noqa: F403
from .secure import build_secure_settings


ENVIRONMENT = 'production'
globals().update(build_secure_settings(
    default_hsts_seconds=31536000,
    include_subdomains=False,
    preload=False,
))
