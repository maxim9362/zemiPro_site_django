#!/usr/bin/env python3
"""Metadata and redacted current-code secret audit. Never prints credential values.

Run in an isolated repository checkout. The tool does not use a network, import
project code, read sensitive-name files, or modify Git/configuration.
"""

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

SENSITIVE_EXT = ('.pem', '.p12', '.pfx', '.key', '.db', '.sqlite', '.sqlite3')
SCANNABLE_EXT = ('.py', '.yml', '.yaml', '.toml', '.ini', '.cfg', '.sh')
USERINFO = re.compile(r'(?i)\b(?:socks5h?|https?)://[^\s@\x22\x27<>/:]+:[^\s@\x22\x27<>]+@')
KEY_MATERIAL = re.compile(r'(?i)-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|\bgh[pousr]_[A-Za-z0-9]{20,}|\bAIza[\w-]{24,}')
LITERAL_ASSIGN = re.compile(r'''(?ix)\b(?:[\w]*_)?(?:TOKEN|PASSWORD|PASSWD|SECRET|API_KEY|PRIVATE_KEY)\s*=\s*['"]([^'"]{12,})['"]''')


def sensitive_path(path):
    name = Path(path).name.lower()
    if name == '.env' or name.startswith('.env.') and name != '.env.example':
        return True
    if 'service_account' in name and name.endswith('.json'):
        return True
    return name.endswith(SENSITIVE_EXT)


def classify_line(line):
    """Only classifications. The passed line and captured values are not returned."""
    findings = []
    if USERINFO.search(line):
        findings.append('CREDENTIALS_IN_URL')
    if KEY_MATERIAL.search(line):
        findings.append('KEY_MATERIAL_LITERAL')
    if LITERAL_ASSIGN.search(line):
        findings.append('CREDENTIAL_VARIABLE_LITERAL')
    return findings


def git_capture(root, args):
    try:
        proc = subprocess.run(
            ['git', '-C', str(root), *args],
            capture_output=True, timeout=60, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return proc.stdout if proc.returncode == 0 else None


def tracked_paths(root):
    data = git_capture(root, ['ls-files', '-z'])
    if data is None:
        raise RuntimeError('Git checkout or git executable unavailable')
    return sorted(set(s.decode('utf-8', 'replace') for s in data.split(b'\0') if s))


def inspect(root, include_history=False):
    root = root.resolve()
    paths = tracked_paths(root)
    flagged_paths = sorted(path for path in paths if sensitive_path(path))
    findings = []
    for rel in paths:
        if sensitive_path(rel) or not rel.lower().endswith(SCANNABLE_EXT):
            continue
        target = root / rel
        if target.is_symlink() or not target.is_file() or target.stat().st_size > 256_000:
            continue
        try:
            lines = target.read_text(encoding='utf-8').splitlines()
        except (UnicodeError, OSError):
            continue
        for number, line in enumerate(lines, 1):
            for kind in classify_line(line):
                findings.append({'file': rel, 'line': number, 'type': kind})
    historical_paths = []
    history_status = 'NOT_REQUESTED'
    if include_history:
        data = git_capture(root, ['log', '--all', '--format=', '--name-only', '-z', '--no-renames'])
        if data is None:
            history_status = 'NOT_AVAILABLE'
        else:
            names = {s.decode('utf-8', 'replace').strip() for s in data.split(b'\0') if s.strip()}
            historical_paths = sorted(p for p in names if sensitive_path(p))
            history_status = 'PATH_METADATA_ONLY'
    return {
        'status': 'REVIEW_REQUIRED' if flagged_paths or findings or historical_paths else 'NO_MATCHES_IN_SCOPE',
        'tracked_file_count': len(paths),
        'tracked_sensitive_paths': flagged_paths,
        'current_source_findings': findings,
        'history_path_status': history_status,
        'history_sensitive_paths': historical_paths,
        'history_blob_contents': 'NOT_SCANNED',
        'secret_file_contents': 'NOT_READ',
        'secret_validity': 'UNVERIFIED',
        'limits': 'Heuristic scan; no claim of full historical coverage or safety.',
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=Path.cwd())
    parser.add_argument('--history-paths', action='store_true')
    opts = parser.parse_args(argv)
    try:
        report = inspect(opts.repo, opts.history_paths)
    except RuntimeError as exc:
        print(json.dumps({'status': 'NOT_RUN', 'reason': str(exc)}))
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if report['status'] == 'REVIEW_REQUIRED' else 0


if __name__ == '__main__':
    sys.exit(main())
