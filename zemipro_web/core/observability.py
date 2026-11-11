"""Fail-closed structured application logging without request text or PII.

Never serialize record.getMessage(), args, request, exception or traceback.
Log events are allowlisted constants only, not user-supplied messages.
"""
import json
import logging
from datetime import datetime, timezone


ALLOWED_HEALTH_EVENTS = frozenset({'database_unavailable'})


class SafeJsonFormatter(logging.Formatter):
    def format(self, record):
        if record.name.startswith('django.request'):
            component, event = 'django', 'http_error'
        elif record.name.startswith('django.security'):
            component, event = 'django', 'security_warning'
        elif record.name.startswith('django.db.backends'):
            component, event = 'django', 'database_warning'
        elif record.name.startswith('django'):
            component, event = 'django', 'framework_event'
        elif record.name == 'zemipro.health':
            component = 'health'
            requested_event = getattr(record, 'event', None)
            event = (
                requested_event
                if requested_event in ALLOWED_HEALTH_EVENTS
                else 'health_event'
            )
        else:
            component, event = 'application', 'application_event'

        payload = {
            'timestamp': datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(timespec='milliseconds'),
            'level': record.levelname,
            'component': component,
            'event': event,
        }
        status_code = getattr(record, 'status_code', None)
        if type(status_code) is int and 100 <= status_code <= 599:
            payload['status_code'] = status_code
        return json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
