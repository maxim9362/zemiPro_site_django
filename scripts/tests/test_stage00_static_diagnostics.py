import importlib.util
from pathlib import Path
import tempfile
import unittest


TARGET = Path(__file__).resolve().parents[1] / 'stage00_static_diagnostics.py'
spec = importlib.util.spec_from_file_location('stage00_static_diagnostics', TARGET)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class Stage00StaticBaselineTests(unittest.TestCase):
    def make_fixture(self, base):
        for item in module.REQUIRED_PATHS:
            p = base / item
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text('x = 1\n', encoding='utf-8')
        (base / 'zemipro_web/apps/marketplace/migrations/0003_require_order_owner.py').write_text(
            "client__isnull=True\nraise RuntimeError('stop')\n", encoding='utf-8')
        (base / 'docs/SEO_URL_INVENTORY.csv').write_text(
            'old_url,proposed_action,target_new_url,http_status\n'
            'https://zemipro.co.il/master/lachish/,REVIEW,,UNVERIFIED\n', encoding='utf-8')
        p = base / 'zemipro_web/apps/accounts/tests/test_auth.py'
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text('def test_example():\n    assert True\n', encoding='utf-8')

    def test_fixture_passes_static_without_running_database(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            self.make_fixture(base)
            report = module.inspect(base)
            self.assertEqual(report['static_status'], 'PASS')
            self.assertEqual(report['runtime_status'], 'NOT_RUN')
            self.assertEqual(report['syntax_and_test_discovery']['django_test_functions_discovered'], 1)
            self.assertEqual(report['url_inventory']['unverified_http_statuses'], 1)

    def test_invalid_url_causes_fail(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            self.make_fixture(base)
            p = base / 'docs/SEO_URL_INVENTORY.csv'
            p.write_text('old_url,proposed_action,target_new_url,http_status\n'
                         'https://malicious.example/path,REVIEW,,UNVERIFIED\n', encoding='utf-8')
            self.assertEqual(module.inspect(base)['static_status'], 'FAIL')

    def test_duplicate_urls_causes_fail(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            self.make_fixture(base)
            p = base / 'docs/SEO_URL_INVENTORY.csv'
            header = 'old_url,proposed_action,target_new_url,http_status\n'
            row = 'https://zemipro.co.il/,REVIEW,,UNVERIFIED\n'
            p.write_text(header + row + row, encoding='utf-8')
            self.assertEqual(module.inspect(base)['url_inventory']['duplicates'], 1)
            self.assertEqual(module.inspect(base)['static_status'], 'FAIL')

    def test_syntax_error_is_detected(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            self.make_fixture(base)
            (base / 'zemipro_web/apps/accounts/models.py').write_text('def broken(:\n', encoding='utf-8')
            self.assertEqual(module.inspect(base)['syntax_and_test_discovery']['status'], 'FAIL')

    def test_sensitive_files_are_classified_without_reading(self):
        self.assertTrue(module._sensitive_path(Path('index_site/service_account.json')))
        self.assertTrue(module._sensitive_path(Path('.env')))
        self.assertTrue(module._sensitive_path(Path('storage/data.db')))
        self.assertFalse(module._sensitive_path(Path('zemipro_web/.env.example')))

    def test_no_premature_redirect_action(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            self.make_fixture(base)
            p = base / 'docs/SEO_URL_INVENTORY.csv'
            p.write_text('old_url,proposed_action,target_new_url,http_status\n'
                         'https://zemipro.co.il/,301,https://zemipro.co.il/new/,UNVERIFIED\n', encoding='utf-8')
            self.assertEqual(module.inspect(base)['url_inventory']['status'], 'FAIL')


if __name__ == '__main__':
    unittest.main()
