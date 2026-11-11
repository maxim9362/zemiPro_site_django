"""Defensive log redaction regression checks; no database required."""
import json
import logging

from django.conf import settings
from django.test import SimpleTestCase

from core.observability import SafeJsonFormatter


class SafeJsonLoggingTests(SimpleTestCase):
    def test_request_path_query_string_phone_and_exception_never_logged(self):
        sensitive = 'address=private-street phone=+972501234567 token=hidden'
        record = logging.LogRecord(
            name='django.request',
            level=logging.ERROR,
            pathname='/orders/private/',
            lineno=123,
            msg=sensitive,
            args=(),
            exc_info=None,
        )
        record.status_code = 500
        record.request = {'path': '/orders/?' + sensitive}
        result = SafeJsonFormatter().format(record)
        payload = json.loads(result)
        self.assertEqual(payload['component'], 'django')
        self.assertEqual(payload['event'], 'http_error')
        self.assertEqual(payload['status_code'], 500)
        self.assertNotIn(sensitive, result)
        self.assertNotIn('/orders/', result)
        self.assertNotIn('token=', result)

    def test_untrusted_event_field_is_not_written(self):
        record = logging.LogRecord(
            name='zemipro.health', level=logging.WARNING,
            pathname='/sensitive/', lineno=1,
            msg='sensitive-password', args=(), exc_info=None,
        )
        record.event = 'Bearer private-access-token'
        result = SafeJsonFormatter().format(record)
        self.assertNotIn('private-access-token', result)
        self.assertIn('health_event', result)

    def test_allowlisted_health_event_is_visible(self):
        record = logging.LogRecord(
            name='zemipro.health', level=logging.WARNING,
            pathname='test', lineno=1,
            msg='do not log this', args=(), exc_info=None,
        )
        record.event = 'database_unavailable'
        payload = json.loads(SafeJsonFormatter().format(record))
        self.assertEqual(payload['event'], 'database_unavailable')
        self.assertNotIn('do not log this', str(payload))

    def test_all_framework_loggers_use_redacted_console(self):
        loggers = settings.LOGGING['loggers']
        for name in (
            'django', 'django.request', 'django.security',
            'django.server', 'django.db.backends',
        ):
            with self.subTest(logger=name):
                self.assertEqual(loggers[name]['handlers'], ['console'])
                self.assertFalse(loggers[name]['propagate'])
