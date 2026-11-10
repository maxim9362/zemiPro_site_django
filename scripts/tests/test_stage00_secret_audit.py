import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

PATH = Path(__file__).resolve().parents[1] / 'stage00_secret_audit.py'
spec = importlib.util.spec_from_file_location('stage00_secret_audit', PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class SecretAuditTests(unittest.TestCase):
    def test_sensitive_names(self):
        self.assertTrue(mod.sensitive_path('index_site/service_account.json'))
        self.assertTrue(mod.sensitive_path('.env'))
        self.assertTrue(mod.sensitive_path('storage/cache.db'))
        self.assertFalse(mod.sensitive_path('zemipro_web/.env.example'))

    def test_url_credential_is_redacted(self):
        secret = 'socks5://' + 'some_user:example_hidden_password@example.net:1234'
        self.assertIn('CREDENTIALS_IN_URL', mod.classify_line('PROXY_URL = ' + repr(secret)))
        self.assertNotIn('example_hidden_password', repr(mod.classify_line(secret)))

    def test_environment_reference_not_flagged(self):
        self.assertEqual(mod.classify_line('API_TOKEN = os.getenv("API_TOKEN")'), [])

    def test_private_key_marker(self):
        self.assertIn('KEY_MATERIAL_LITERAL', mod.classify_line('-----BEGIN ' + 'PRIVATE KEY-----'))

    def test_tracked_file_metadata_without_reading_sensitive_data(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(['git', 'init', '-q', str(root)], check=True)
            (root / '.env').write_text('SECRET=not_for_report\n')
            (root / 'app.py').write_text('PROXY_URL = "' + 'socks5://' + 'u:p@example.net' + '"\n')
            subprocess.run(['git', '-C', str(root), 'add', '.env', 'app.py'], check=True)
            report = mod.inspect(root)
            self.assertIn('.env', report['tracked_sensitive_paths'])
            self.assertEqual(report['secret_file_contents'], 'NOT_READ')
            self.assertEqual(report['status'], 'REVIEW_REQUIRED')
            self.assertNotIn('not_for_report', str(report))
            self.assertEqual(report['current_source_findings'][0]['type'], 'CREDENTIALS_IN_URL')

    def test_history_paths_without_blob_content(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(['git', 'init', '-q', str(root)], check=True)
            subprocess.run(['git', '-C', str(root), 'config', 'user.email', 'test@example.test'], check=True)
            subprocess.run(['git', '-C', str(root), 'config', 'user.name', 'Test'], check=True)
            (root / '.env').write_text('PRIVATE_KEY=historical_sensitive_value\n')
            subprocess.run(['git', '-C', str(root), 'add', '.env'], check=True)
            subprocess.run(['git', '-C', str(root), 'commit', '-qm', 'fixture'], check=True)
            (root / '.env').unlink()
            subprocess.run(['git', '-C', str(root), 'rm', '--cached', '-q', '.env'], check=True)
            subprocess.run(['git', '-C', str(root), 'commit', '-qm', 'remove'], check=True)
            report = mod.inspect(root, include_history=True)
            self.assertIn('.env', report['history_sensitive_paths'])
            self.assertEqual(report['history_blob_contents'], 'NOT_SCANNED')
            self.assertNotIn('historical_sensitive_value', str(report))


if __name__ == '__main__':
    unittest.main()
