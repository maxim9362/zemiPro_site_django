"""Pure settings/deploy checks: no database connections, synthetic secrets only."""
import os
import subprocess
import sys

from django.conf import settings
from django.test import SimpleTestCase


class EnvironmentSettingsTests(SimpleTestCase):
    def secure_environment(self, name='production'):
        environment = os.environ.copy()
        environment.update({
            'DJANGO_ENV': name,
            'DJANGO_SECRET_KEY':
                'test-only-secure-config-9hW8k2P7q4R6s1V3x5Z7c9B2n4M6a8D0',
            'DJANGO_ALLOWED_HOSTS': 'example.com',
            'DB_NAME': 'zemipro_synthetic',
            'DB_USER': 'zemipro_synthetic',
            'DB_PASSWORD': 'test-only-configuration-check',
            'DB_HOST': 'localhost',
            'DB_PORT': '5432',
        })
        # Prevent ambient overrides from the developer's own shell.
        for key in (
            'DJANGO_SECURE_SSL_REDIRECT',
            'DJANGO_SESSION_COOKIE_SECURE',
            'DJANGO_CSRF_COOKIE_SECURE',
            'DJANGO_SECURE_HSTS_SECONDS',
            'DJANGO_TRUST_X_FORWARDED_PROTO',
        ):
            environment.pop(key, None)
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
        self.assertEqual(settings.DATABASES['default']['ENGINE'],
                         'django.db.backends.postgresql')
        self.assertEqual(settings.DATABASES['default']['TEST']['NAME'],
                         'test_zemipro_db')
        self.assertFalse(settings.SECURE_SSL_REDIRECT)

    def test_production_settings_import_and_deploy_check(self):
        result = self.run_check(self.secure_environment())
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_staging_settings_import_and_deploy_check(self):
        result = self.run_check(self.secure_environment('staging'))
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_production_rejects_weak_secret(self):
        environment = self.secure_environment()
        environment['DJANGO_SECRET_KEY'] = 'short'
        result = self.run_check(environment)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('DJANGO_SECRET_KEY must be a strong value', result.stderr)

    def test_production_rejects_placeholder_database_password(self):
        environment = self.secure_environment()
        environment['DB_PASSWORD'] = 'postgres'
        result = self.run_check(environment)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('DB_PASSWORD cannot be a development placeholder', result.stderr)

    def test_production_rejects_disabled_https(self):
        environment = self.secure_environment()
        environment['DJANGO_SECURE_SSL_REDIRECT'] = 'false'
        result = self.run_check(environment)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('must be true for staging and production', result.stderr)

    def test_production_rejects_wildcard_hosts(self):
        environment = self.secure_environment()
        environment['DJANGO_ALLOWED_HOSTS'] = '*'
        result = self.run_check(environment)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('ALLOWED_HOSTS must contain explicit hosts', result.stderr)
