#!/usr/bin/env python3
"""Read-only Stage 00 static baseline; never contacts a database or runs Django.

Stdlib only; suitable for running before the final isolated Codex/CI verification.
The JSON report contains metadata and statuses, never secrets or file contents.
"""
from __future__ import annotations

import argparse
import ast
import csv
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version
import json
from pathlib import Path
import shutil
import subprocess
import sys
from urllib.parse import urlsplit


REQUIRED_PATHS = (
    'AGENTS.md',
    'zemipro_web/manage.py',
    'zemipro_web/core/settings.py',
    'zemipro_web/core/urls.py',
    'zemipro_web/apps/accounts/models.py',
    'zemipro_web/apps/marketplace/models.py',
    'zemipro_web/apps/marketplace/migrations/0003_require_order_owner.py',
    'zemipro_web/apps/locations/models.py',
    'zemipro_web/docker-compose.django.yml',
    'docs/SEO_URL_INVENTORY.csv',
)
COMMANDS_NOT_RUN = (
    'django_check', 'django_deploy_check', 'makemigrations_check',
    'postgres_migrate', 'django_tests', 'docker_up',
    'backup_restore', 'runtime_http_smoke', 'secret_content_scan',
)


def _sensitive_path(relative: Path) -> bool:
    name = relative.name.lower()
    if name in {'.env', '.envrc'} or (name.startswith('.env.') and name != '.env.example'):
        return True
    if 'service_account' in name and name.endswith('.json'):
        return True
    return name.endswith(('.db', '.sqlite', '.sqlite3', '.p12', '.pfx', '.pem', '.key'))


def _git_metadata(root: Path) -> dict:
    if not shutil.which('git') or not (root / '.git').exists():
        return {'status': 'NOT_AVAILABLE'}
    try:
        proc = subprocess.run(
            ['git', '-C', str(root), 'ls-files', '-z'], capture_output=True,
            timeout=10, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {'status': 'NOT_AVAILABLE'}
    if proc.returncode:
        return {'status': 'NOT_AVAILABLE'}
    names = [Path(p.decode('utf-8', errors='replace')) for p in proc.stdout.split(b'\0') if p]
    sensitive = sorted(p.as_posix() for p in names if _sensitive_path(p))
    return {'status': 'PASS' if not sensitive else 'REVIEW',
            'tracked_sensitive_paths': sensitive,
            'tracked_file_count': len(names)}


def _syntax_and_tests(root: Path) -> dict:
    pyfiles = sorted((root / 'zemipro_web').rglob('*.py'))
    errors = []
    test_count = 0
    test_modules = 0
    for p in pyfiles:
        if any(part in {'venv', '.venv', '__pycache__'} for part in p.parts):
            continue
        try:
            tree = ast.parse(p.read_text(encoding='utf-8'), filename=str(p))
        except (SyntaxError, UnicodeError, OSError) as exc:
            # No source lines or exception strings: some files could contain private data.
            errors.append({'path': p.relative_to(root).as_posix(), 'type': type(exc).__name__})
            continue
        if p.name.startswith('test_') and 'tests' in p.parts:
            test_modules += 1
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith('test_'):
                    test_count += 1
    return {'status': 'PASS' if pyfiles and not errors else 'FAIL',
            'python_files_checked': len(pyfiles),
            'syntax_issues': errors,
            'django_test_modules_found': test_modules,
            'django_test_functions_discovered': test_count,
            'note': 'Discovered tests have NOT been executed.'}


def _url_inventory(root: Path) -> dict:
    p = root / 'docs/SEO_URL_INVENTORY.csv'
    if not p.is_file():
        return {'status': 'NOT_FOUND'}
    with p.open('r', newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        needed = {'old_url', 'proposed_action', 'target_new_url', 'http_status'}
        if not reader.fieldnames or not needed.issubset(set(reader.fieldnames)):
            return {'status': 'FAIL', 'issue': 'missing_required_columns'}
        rows = list(reader)
    urls = [r.get('old_url', '') for r in rows]
    invalid = 0
    for url in urls:
        try:
            u = urlsplit(url)
            valid = (u.scheme == 'https' and u.netloc == 'zemipro.co.il'
                     and u.path.startswith('/') and not u.query and not u.fragment)
        except ValueError:
            valid = False
        if not valid:
            invalid += 1
    dup = len(urls) - len(set(urls))
    action = sum(r.get('proposed_action') not in ('REVIEW', '') for r in rows)
    assigned = sum(bool(r.get('target_new_url')) for r in rows)
    unknown_http = sum(r.get('http_status') in {'UNVERIFIED', 'UNKNOWN', ''} for r in rows)
    return {'status': 'PASS' if rows and not (invalid or dup or action or assigned) else 'FAIL',
            'url_rows': len(rows), 'duplicates': dup, 'invalid_domain_or_url': invalid,
            'premature_actions': action, 'premature_targets': assigned,
            'unverified_http_statuses': unknown_http,
            'note': 'No HTTP or Search Console checks were performed.'}


def _migration_guard(root: Path) -> dict:
    p = root / 'zemipro_web/apps/marketplace/migrations/0003_require_order_owner.py'
    if not p.is_file():
        return {'status': 'FAIL', 'migration_0003_present': False}
    try:
        source = p.read_text(encoding='utf-8')
    except OSError:
        return {'status': 'FAIL', 'migration_0003_present': True}
    guard = 'client__isnull=True' in source and 'raise RuntimeError' in source
    return {'status': 'PASS' if guard else 'REVIEW',
            'migration_0003_present': True, 'null_owner_guard_present': guard,
            'note': 'Guard was checked statically; applying migrations is NOT_RUN.'}


def _package(name: str) -> str:
    try:
        return version(name)
    except PackageNotFoundError:
        return 'NOT_INSTALLED'


def inspect(root: Path) -> dict:
    root = root.expanduser().resolve()
    missing = [p for p in REQUIRED_PATHS if not (root / p).is_file()]
    syntax = _syntax_and_tests(root) if (root / 'zemipro_web').is_dir() else {'status': 'NOT_FOUND'}
    urls = _url_inventory(root)
    migration = _migration_guard(root)
    git = _git_metadata(root)
    fail = bool(missing) or any(x.get('status') == 'FAIL' for x in (syntax, urls, migration))
    return {
        'stage': '00.6',
        'inspection_time_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'scope': 'LOCAL_READ_ONLY_STATIC',
        'static_status': 'FAIL' if fail else 'PASS',
        'runtime_status': 'NOT_RUN',
        'python_runtime': sys.version.split()[0],
        'django_installed_version': _package('Django'),
        'command_presence': {name: bool(shutil.which(name)) for name in
                             ('docker', 'psql', 'pg_dump', 'pg_restore')},
        'missing_required_files': missing,
        'syntax_and_test_discovery': syntax,
        'migration_guard': migration,
        'url_inventory': urls,
        'git_tracked_files': git,
        'checks_not_run': {name: 'NOT_RUN' for name in COMMANDS_NOT_RUN},
        'safety': 'No settings imported, no Django commands, network calls, or SQL run.',
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    report = inspect(args.root)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report['static_status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
