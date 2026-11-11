"""Probes never leak database errors and do not require real PostgreSQL."""
from unittest.mock import patch

from django.db import DatabaseError
from django.test import RequestFactory, SimpleTestCase
from django.urls import reverse

from core.health import liveness, readiness


class HealthEndpointTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_liveness_returns_200_without_database(self):
        response = liveness(self.factory.get('/health/live/'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b'{"status": "ok"}')
        self.assertIn('no-store', response['Cache-Control'])

    def test_readiness_returns_200_if_database_probe_succeeds(self):
        with patch('core.health.connections') as connections:
            response = readiness(self.factory.get('/health/ready/'))
            connections.__getitem__.return_value.cursor.return_value.__enter__.return_value.execute.assert_called_once_with('SELECT 1')
        self.assertEqual(response.status_code, 200)
        self.assertIn('no-store', response['Cache-Control'])

    def test_readiness_returns_503_without_sensitive_exception_details(self):
        sensitive = 'DB host=secret.example.invalid token=hidden phone=+972501234567'
        with patch('core.health.connections') as connections:
            connections.__getitem__.return_value.cursor.side_effect = DatabaseError(sensitive)
            response = readiness(self.factory.get('/health/ready/'))
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.content, b'{"status": "unavailable"}')
        self.assertNotIn(sensitive.encode(), response.content)
        self.assertIn('no-store', response['Cache-Control'])

    def test_probes_do_not_accept_post(self):
        self.assertEqual(
            liveness(self.factory.post('/health/live/')).status_code, 405
        )
        self.assertEqual(
            readiness(self.factory.post('/health/ready/')).status_code, 405
        )

    def test_named_probe_routes_are_registered(self):
        self.assertEqual(reverse('health_live'), '/health/live/')
        self.assertEqual(reverse('health_ready'), '/health/ready/')
