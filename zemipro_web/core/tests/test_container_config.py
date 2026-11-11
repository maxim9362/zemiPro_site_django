"""Static safety regression tests for optional Compose deployments.

These tests do not launch Docker or connect to a server.
"""
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class ContainerConfigurationTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.root = Path(settings.BASE_DIR)

    def test_docker_build_ignores_local_secrets_and_media(self):
        contents = (self.root / '.dockerignore').read_text(encoding='utf-8')
        for entry in ('.env', '.env.*', '*.pem', '*.key', 'media/', 'secrets/'):
            with self.subTest(entry=entry):
                self.assertIn(entry, contents)
        self.assertIn('USER django:django', (
            self.root / 'Dockerfile.django'
        ).read_text(encoding='utf-8'))

    def test_staging_database_is_not_published(self):
        contents = (
            self.root / 'docker-compose.staging.yml'
        ).read_text(encoding='utf-8')
        db_section = contents.split('  db:', 1)[1].split('  web:', 1)[0]
        self.assertNotIn('    ports:', db_section)
        self.assertIn('staging_postgres:', contents)
        self.assertIn('internal: true', contents)

    def test_staging_requires_independent_credentials_and_https(self):
        contents = (
            self.root / 'docker-compose.staging.yml'
        ).read_text(encoding='utf-8')
        self.assertIn('STAGING_DJANGO_SECRET_KEY:?', contents)
        self.assertIn('STAGING_DB_PASSWORD:?', contents)
        self.assertIn('DJANGO_ENV: staging', contents)
        self.assertIn('DJANGO_TRUST_X_FORWARDED_PROTO: "true"', contents)
        caddy = (self.root / 'Caddyfile.staging').read_text(encoding='utf-8')
        self.assertIn('{$STAGING_DOMAIN}', caddy)
        self.assertIn('reverse_proxy web:8000', caddy)
        self.assertIn('handle /media/*', caddy)
        self.assertIn('respond 404', caddy)

    def test_startup_migrations_fail_closed_outside_dev_and_staging(self):
        contents = (
            self.root / 'docker/entrypoint.sh'
        ).read_text(encoding='utf-8')
        self.assertIn('development|staging)', contents)
        self.assertIn('python manage.py migrate --noinput', contents)
        self.assertIn('exec "$@"', contents)

    def test_dev_ports_bind_loopback_only(self):
        contents = (
            self.root / 'docker-compose.django.yml'
        ).read_text(encoding='utf-8')
        self.assertIn('"127.0.0.1:', contents)
        self.assertIn('dev_postgres:', contents)
        self.assertIn('dev_media:', contents)

    def test_shell_scripts_use_lf_and_django_has_writable_home(self):
        # The repository root is outside Docker's /app build context.
        # Assert Git checkout attributes only when the file is actually present.
        attributes_path = self.root.parent / '.gitattributes'
        if attributes_path.is_file():
            attributes = attributes_path.read_text(encoding='utf-8')
            self.assertIn('*.sh text eol=lf', attributes)
        for script in (
            'docker/entrypoint.sh',
            'docker/staging-backup.sh',
            'docker/check-staging-health.sh',
            'docker/ci-staging-smoke.sh',
        ):
            with self.subTest(path=script):
                data = (self.root / script).read_bytes()
                self.assertNotIn(b'\r\n', data)

        dockerfile = (self.root / 'Dockerfile.django').read_text(encoding='utf-8')
        self.assertIn('HOME=/home/django', dockerfile)
        self.assertIn('--create-home --home-dir /home/django', dockerfile)
        self.assertIn('chmod 0700 /home/django', dockerfile)
