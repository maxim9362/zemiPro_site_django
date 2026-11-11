"""Minimal liveness/readiness probes with no diagnostic data in responses."""
import logging

from django.db import DatabaseError, connections
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET


logger = logging.getLogger('zemipro.health')


@never_cache
@require_GET
def liveness(request):
    """Django application handles HTTP requests; no database dependency."""
    return JsonResponse({'status': 'ok'})


@never_cache
@require_GET
def readiness(request):
    """Database is queryable; do not expose connection or exception details."""
    try:
        with connections['default'].cursor() as cursor:
            cursor.execute('SELECT 1')
    except DatabaseError:
        # Do not attach exc_info, SQL, hostname or user-supplied values.
        logger.warning('redacted', extra={'event': 'database_unavailable'})
        return JsonResponse({'status': 'unavailable'}, status=503)

    return JsonResponse({'status': 'ok'})
