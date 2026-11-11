#!/usr/bin/env python3
"""Stage 00 rehearsal only: local synthetic PostgreSQL backup and isolated restore.

Intentionally refuses production/remote hosts and non-fixture database names.
It never creates/drops databases or clears existing tables.
"""
import argparse
import hashlib
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile


REPO_ROOT = Path(__file__).resolve().parents[1]
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
DB_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
COMMAND_TIMEOUT_SECONDS = 300


class SafetyError(Exception):
    pass


def connection(kind):
    """Build isolated libpq environment without exposing credentials in argv."""
    prefix = f"ZEMIPRO_{kind.upper()}_"
    name = os.environ.get(prefix + "DB_NAME", "")
    host = os.environ.get(prefix + "DB_HOST", "")
    user = os.environ.get(prefix + "DB_USER", "")
    port = os.environ.get(prefix + "DB_PORT", "5432")
    expected_prefix = "zemipro_fixture_" if kind == "source" else "zemipro_restore_"
    if not DB_NAME_RE.fullmatch(name) or not name.startswith(expected_prefix):
        raise SafetyError(f"{kind} DB name must start with {expected_prefix}")
    if host not in LOCAL_HOSTS:
        raise SafetyError(f"{kind} DB host must be local loopback")
    if not user or not port.isdecimal() or not (1 <= int(port) <= 65535):
        raise SafetyError(f"{kind} DB user and valid port must be provided")
    child_env = os.environ.copy()
    for key in ("PGSERVICE", "PGSERVICEFILE", "PGHOSTADDR", "PGDATABASE",
                "PGHOST", "PGPORT", "PGUSER", "PGPASSWORD", "PGOPTIONS"):
        child_env.pop(key, None)
    child_env.update(
        PGHOST=host,
        PGPORT=port,
        PGUSER=user,
        PGDATABASE=name,
        PGCONNECT_TIMEOUT="5",
    )
    password = os.environ.get(prefix + "DB_PASSWORD")
    if password:
        child_env["PGPASSWORD"] = password
    return name, child_env


def archive_path(path, *, must_exist):
    target = Path(path).expanduser().resolve()
    if target == REPO_ROOT or REPO_ROOT in target.parents:
        raise SafetyError("Archive must stay outside the repository")
    if must_exist:
        if not target.is_file():
            raise SafetyError("Archive file does not exist")
    elif not target.parent.is_dir() or target.exists():
        raise SafetyError("Output directory must exist and archive must not exist")
    return target


def run(command, env=None, *, capture=False):
    # Never print subprocess stderr: some clients may echo connection details.
    try:
        result = subprocess.run(
            command,
            env=env,
            stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=COMMAND_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SafetyError(f"Unable to run {command[0]} safely ({type(exc).__name__})") from None
    if result.returncode:
        raise SafetyError(f"{command[0]} failed with exit code {result.returncode}")
    return result.stdout.strip() if capture else None


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def verify_archive(path):
    run(["pg_restore", "--list", str(path)])
    if path.stat().st_size < 1:
        raise SafetyError("Archive is empty")
    print(f"archive_bytes={path.stat().st_size}")
    print(f"archive_sha256={digest(path)}")


def backup(output):
    name, env = connection("source")
    dest = archive_path(output, must_exist=False)
    file_id, temporary = tempfile.mkstemp(
        prefix=".zemipro_snapshot_", suffix=".partial", dir=dest.parent
    )
    os.close(file_id)
    try:
        os.chmod(temporary, 0o600)
        run(["pg_dump", "--no-password", "--format=custom",
             "--file", temporary, "--dbname", name], env)
        run(["pg_restore", "--list", temporary])
        if not Path(temporary).stat().st_size:
            raise SafetyError("pg_dump produced an empty file")
        if dest.exists():
            raise SafetyError("Output was created by another process")
        os.replace(temporary, dest)
        verify_archive(dest)
        print("backup_status=PASS (synthetic source only)")
    finally:
        Path(temporary).unlink(missing_ok=True)


def restore(source):
    dest_name, env = connection("restore")
    archive = archive_path(source, must_exist=True)
    run(["pg_restore", "--list", str(archive)])
    empty_sql = (
        "SELECT count(*) FROM pg_class c JOIN pg_namespace n "
        "ON c.relnamespace = n.oid WHERE c.relkind IN ('r','p') "
        "AND n.nspname NOT IN ('pg_catalog','information_schema') "
        "AND n.nspname NOT LIKE 'pg_toast%';"
    )
    count = run(["psql", "--no-psqlrc", "--no-password",
                 "--tuples-only", "--no-align",
                 "--dbname", dest_name, "--command", empty_sql],
                env, capture=True)
    if count != "0":
        raise SafetyError("Restore target must exist and contain no user tables")
    run(["pg_restore", "--no-password", "--exit-on-error",
         "--no-owner", "--no-acl", "--dbname", dest_name, str(archive)], env)
    print("restore_status=PASS (isolated empty local target only)")
    print("Verify table and row counts against source before acceptance.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("backup").add_argument("archive")
    sub.add_parser("verify").add_argument("archive")
    sub.add_parser("restore").add_argument("archive")
    args = parser.parse_args(argv)
    try:
        if args.action == "backup":
            backup(args.archive)
        elif args.action == "verify":
            verify_archive(archive_path(args.archive, must_exist=True))
        else:
            restore(args.archive)
    except SafetyError as exc:
        print(f"SAFE_ABORT: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
