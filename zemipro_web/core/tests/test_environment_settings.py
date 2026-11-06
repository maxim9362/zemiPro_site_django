import os
import subprocess
import sys

from django.conf import settings
from django.test import SimpleTestCase


class EnvironmentSettingsTests(SimpleTestCase):
    def production_environment(self):
        environment = os.environ.copy()
        environment.update({
            'DJANGO_ENV': 'production',
            'DJANGO_SECRET_KEY': (
                'production-check-only-9hW8k2P7q4R6s1V3x5Z7c9B2n4M6a8D0'
            ),
            'DJANGO_ALLOWED_HOSTS': 'example.com',
            'DB_NAME': 'zemipro_check',
            'DB_USER': 'zemipro_check',
            'DB_PASSWORD': 'production-check-password-9362',
            'DB_HOST': 'db.example.internal',
            'DB_PORT': '5432',
        })
        return environment

    def run_check(self, environment):
        return subprocess.run(
            [sys.executable, 'manage.py', 'check', '--deploy'],
            cwd=settings.BASE_DIR,
            env=environment,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )

    def test_manage_test_command_selects_isolated_test_settings(self):
        self.assertEqual(settings.ENVIRONMENT, 'test')
        self.assertFalse(settings.DEBUG)
        self.assertFalse(settings.SECURE_SSL_REDIRECT)
        self.assertFalse(settings.SESSION_COOKIE_SECURE)
        self.assertFalse(settings.CSRF_COOKIE_SECURE)

    def test_production_settings_pass_django_deployment_checks(self):
        result = self.run_check(self.production_environment())

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn('System check identified no issues', result.stdout)

    def test_production_rejects_weak_secret(self):
        environment = self.production_environment()
        environment['DJANGO_SECRET_KEY'] = 'short'

        result = self.run_check(environment)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn('DJANGO_SECRET_KEY must be a strong value', result.stderr)
