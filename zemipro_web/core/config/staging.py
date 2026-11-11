from .base import *  # noqa: F403
from .secure import build_secure_settings


ENVIRONMENT = 'staging'
globals().update(build_secure_settings(
    default_hsts_seconds=3600,
    include_subdomains=False,
    preload=False,
))
