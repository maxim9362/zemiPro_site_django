"""Safety middleware: per-process basic throttling and private HTML cache headers.

The default Django LocMemCache is NOT shared across workers. A verified
distributed/edge limiter is required before public production launch.
"""
import hashlib
import hmac
import ipaddress

from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse
from django.utils.deprecation import MiddlewareMixin


class DynamicHtmlNoStoreMiddleware:
    """Protect all dynamic HTML, including error pages, from shared caches."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if response.get('Content-Type', '').split(';', 1)[0].strip() == 'text/html':
            response['Cache-Control'] = 'private, no-store, max-age=0'
        return response


def throttle_client_ip(request):
    """Never trust user-controlled forwarded headers by default."""
    address = request.META.get('REMOTE_ADDR', '')
    if getattr(settings, 'THROTTLE_TRUST_X_REAL_IP', False):
        address = request.META.get('HTTP_X_REAL_IP') or address
    try:
        return str(ipaddress.ip_address(address))
    except ValueError:
        return None


class SensitivePostThrottleMiddleware(MiddlewareMixin):
    """Basic POST limit for login and registration, before form validation."""

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
        digest = hmac.new(
            settings.SECRET_KEY.encode('utf-8'),
            f'{request.path_info}:{address}'.encode('utf-8'),
            hashlib.sha256,
        ).hexdigest()
        key = f'zemipro:post:v1:{digest}'
        try:
            if cache.add(key, 1, timeout=window):
                count = 1
            else:
                try:
                    count = cache.incr(key)
                except ValueError:
                    # Expired between add and increment: restart the window.
                    count = 1 if cache.add(key, 1, timeout=window) else cache.incr(key)
        except Exception:
            # Fail closed on cache errors without exposing internals.
            return HttpResponse('Temporarily unavailable', status=503)

        if count > limit:
            response = HttpResponse('Too many attempts', status=429)
            response['Retry-After'] = str(window)
            response['Cache-Control'] = 'private, no-store'
            return response
        return None
