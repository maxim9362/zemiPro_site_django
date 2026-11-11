"""No-store, safe errors and basic throttle regression tests."""
from unittest.mock import patch

from django.core.cache import cache
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.views.defaults import server_error

from core.middleware import throttle_client_ip


class ErrorAndCacheHeadersTests(TestCase):
    def test_unknown_route_has_safe_404_and_no_store(self):
        with override_settings(DEBUG=False):
            response = self.client.get('/missing-user-request-secret-987654/')
        self.assertEqual(response.status_code, 404)
        self.assertContains(response, 'Страница не найдена', status_code=404)
        self.assertIn('no-store', response['Cache-Control'])
        self.assertNotContains(
            response, 'missing-user-request-secret-987654', status_code=404
        )

    def test_500_page_is_generic_without_traceback(self):
        response = server_error(RequestFactory().get('/private-error/'))
        self.assertEqual(response.status_code, 500)
        self.assertIn('Временная ошибка'.encode(), response.content)
        self.assertNotIn(b'Traceback', response.content)

    def test_public_dynamic_html_is_not_shared_cacheable(self):
        response = self.client.get(reverse('marketplace:categories_list'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('private', response['Cache-Control'])
        self.assertIn('no-store', response['Cache-Control'])

    def test_forwarded_ip_only_trusted_with_explicit_config(self):
        class Request:
            META = {
                'REMOTE_ADDR': '127.0.0.1',
                'HTTP_X_REAL_IP': '203.0.113.3',
            }

        with override_settings(THROTTLE_TRUST_X_REAL_IP=False):
            self.assertEqual(throttle_client_ip(Request()), '127.0.0.1')
        with override_settings(THROTTLE_TRUST_X_REAL_IP=True):
            self.assertEqual(throttle_client_ip(Request()), '203.0.113.3')


@override_settings(
    CACHES={
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'stage-01-6-isolated-throttle',
        },
    },
)
class SensitiveEndpointThrottleTests(TestCase):
    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_login_blocks_after_12_posts_without_leaking_input(self):
        url = reverse('accounts:login')
        for _ in range(12):
            response = self.client.post(
                url, {'username': 'synthetic', 'password': 'wrong-secret'},
                REMOTE_ADDR='192.0.2.10',
            )
            self.assertEqual(response.status_code, 200)
        blocked = self.client.post(
            url, {'username': 'synthetic', 'password': 'wrong-secret'},
            REMOTE_ADDR='192.0.2.10',
        )
        self.assertEqual(blocked.status_code, 429)
        self.assertEqual(blocked['Retry-After'], '300')
        self.assertIn('no-store', blocked['Cache-Control'])
        self.assertNotIn('wrong-secret', blocked.content.decode())

    def test_registration_limit_and_get_still_works(self):
        url = reverse('accounts:register')
        for _ in range(6):
            self.assertEqual(
                self.client.post(url, {}, REMOTE_ADDR='192.0.2.11').status_code,
                200,
            )
        self.assertEqual(
            self.client.post(url, {}, REMOTE_ADDR='192.0.2.11').status_code,
            429,
        )
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_distinct_addresses_have_distinct_quota(self):
        url = reverse('accounts:register')
        for _ in range(6):
            self.client.post(url, {}, REMOTE_ADDR='192.0.2.12')
        self.assertEqual(
            self.client.post(url, {}, REMOTE_ADDR='192.0.2.13').status_code,
            200,
        )

    def test_failed_cache_does_not_unlimit_login(self):
        with patch('core.middleware.cache.add', side_effect=RuntimeError('test')):
            response = self.client.post(
                reverse('accounts:login'), {'username': 'synthetic'},
                REMOTE_ADDR='192.0.2.14',
            )
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('test', response.content.decode())
