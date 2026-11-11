"""Static checks: staging backup never points at live databases."""
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class StagingBackupConfigTests(SimpleTestCase):
    def setUp(self):
        self.root = Path(settings.BASE_DIR)

    def test_backup_service_is_opt_in_and_not_exposed(self):
        source = (self.root / 'docker-compose.staging.yml').read_text()
        backup = source.split('  backup:', 1)[1].split('  proxy:', 1)[0]
        self.assertIn('profiles: ["maintenance"]', backup)
        self.assertNotIn('    ports:', backup)
        self.assertIn('PGDATABASE: zemipro_staging', backup)
        self.assertIn('staging_backups:/backups', backup)

    def test_backup_script_only_uses_staging_database(self):
        source = (self.root / 'docker/staging-backup.sh').read_text()
        for required in (
            'PGHOST:-', 'PGDATABASE:-', 'PGUSER:-',
            'pg_dump --no-password --format=custom',
            'pg_restore --list', 'sha256sum',
        ):
            with self.subTest(fragment=required):
                self.assertIn(required, source)
        self.assertIn('zemipro_staging', source)
        self.assertNotIn('pg_restore --clean', source)
        self.assertNotIn('DROP DATABASE', source)

    def test_monitor_uses_https_and_hides_response_body(self):
        source = (self.root / 'docker/check-staging-health.sh').read_text()
        self.assertIn('https://*/health/ready/', source)
        self.assertIn('--output /dev/null', source)
        self.assertIn('ALERT: readiness failed', source)

    def test_backup_schedule_requires_operator_install(self):
        source = (
            self.root / 'docker/staging-backup.cron.example'
        ).read_text()
        self.assertIn('15 3 * * *', source)
        self.assertIn('/REPLACE/', source)
        self.assertIn('--profile maintenance run --rm backup', source)
