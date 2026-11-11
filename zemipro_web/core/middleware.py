"""Sensitive HTTP safeguards: durable PostgreSQL counters and no-store HTML.

PostgreSQL INSERT .. ON CONFLICT .. RETURNING is atomic and shared by all
Gunicorn workers connected to the same isolated Django PostgreSQL database.
"""
from datetime import datetime, timezone
import hashlib
import hmac
import ipaddress

from django.conf import settings
from django.db import DatabaseError, connection
from django.http import HttpResponse
from django.utils.deprecation import MiddlewareMixin

from apps.accounts.models import SensitivePostCounter


class DynamicHtmlNoStoreMiddleware:
    """Protect dynamic HTML (including errors) from shared caches."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if response.get('Content-Type', '').split(';', 1)[0].strip() == 'text/html':
            response['Cache-Control'] = 'private, no-store, max-age=0'
        return response


def throttle_client_ip(request):
    """Never trust client-provided X-Real-IP unless a trusted proxy overwrites it."""
    address = request.META.get('REMOTE_ADDR', '')
    if getattr(settings, 'THROTTLE_TRUST_X_REAL_IP', False):
        address = request.META.get('HTTP_X_REAL_IP') or address
    try:
        return str(ipaddress.ip_address(address))
    except ValueError:
        return None


def increment_attempt_counter(key, expires_at):
    """One atomic PostgreSQL upsert: global counter across web processes."""
    table = connection.ops.quote_name(SensitivePostCounter._meta.db_table)
    with connection.cursor() as cursor:
        cursor.execute(
            f'INSERT INTO {table} (bucket_hash, attempts, expires_at) '
            'VALUES (%s, 1, %s) '
            'ON CONFLICT (bucket_hash) DO UPDATE '
            'SET attempts = accounts_sensitive_post_counter.attempts + 1 '
            'RETURNING attempts',
            [key, expires_at],
        )
        return cursor.fetchone()[0]


class SensitivePostThrottleMiddleware(MiddlewareMixin):
    """Enforce one fixed-window threshold via shared PostgreSQL counters."""

    RULES = {
        '/accounts/login/': (12, 300),
        '/accounts/register/': (6, 900),
    }

    def process_view(self, request, view_func, view_args, view_kwargs):
        if request.method != 'POST':
            return None
        rule = self.RULES.get(request.path_info)
        if rule is None:
            return None
        address = throttle_client_ip(request)
        if address is None:
            return HttpResponse('Temporarily unavailable', status=503)

        limit, window = rule
        now = datetime.now(timezone.utc)
        bucket = int(now.timestamp() // window)
        key = hmac.new(
            settings.SECRET_KEY.encode('utf-8'),
            f'{request.path_info}:{address}:{bucket}'.encode('utf-8'),
            hashlib.sha256,
        ).hexdigest()
        expires_at = datetime.fromtimestamp((bucket + 1) * window, tz=timezone.utc)
        try:
            count = increment_attempt_counter(key, expires_at)
        except DatabaseError:
            # Sensitive actions fail closed during any DB outage.
            return HttpResponse('Temporarily unavailable', status=503)

        if count > limit:
            response = HttpResponse('Too many attempts', status=429)
            response['Retry-After'] = str(window)
            response['Cache-Control'] = 'private, no-store'
            return response
        return None
