#!/usr/bin/env bash
# Stage 01: disposable GitHub runner only, never authorized for a real VPS.
set -euo pipefail
export COMPOSE_PROJECT_NAME="zemipro-staging"
compose=(docker compose -f docker-compose.staging.yml)

if [[ "${GITHUB_ACTIONS:-}" != "true" || "${STAGING_DOMAIN:-}" != "localhost" ||
      "${STAGING_BIND_IP:-}" != "127.0.0.1" ||
      "${STAGING_HTTPS_PORT:-}" != "18443" ]]; then
  echo "SAFE_ABORT: requires isolated GitHub Actions localhost configuration" >&2
  exit 2
fi
if [[ -z "${STAGING_DB_PASSWORD:-}" || -z "${STAGING_DJANGO_SECRET_KEY:-}" ]]; then
  echo "SAFE_ABORT: synthetic staging credentials missing" >&2
  exit 2
fi

# The runner is disposable. Do not export Docker environment or actual secrets.
"${compose[@]}" up -d --build

ready() {
  # --insecure is for the *disposable localhost* Caddy internal CA ONLY.
  # It must not be copied to any real staging HTTPS certificate test.
  curl --insecure --fail --silent --max-time 5 \
    "https://localhost:18443/health/ready/" | grep -q '"status": "ok"'
}
wait_ready() {
  local attempt
  for attempt in $(seq 1 90); do
    if ready; then return 0; fi
    sleep 2
  done
  echo "FAIL: disposable HTTPS readiness did not become available" >&2
  return 1
}

wait_ready
curl --insecure --fail --silent --output /dev/null \
  "https://localhost:18443/"
curl --insecure --fail --silent --output /dev/null \
  "https://localhost:18443/static/css/style.css"
media_code=$(curl --insecure --silent --output /dev/null \
  --write-out '%{http_code}' "https://localhost:18443/media/private-test")
[[ "$media_code" == "404" ]] || { echo "FAIL: public media exposure" >&2; exit 1; }

# Assert Caddy has provisioned HTTPS and Django applies secure HSTS headers.
curl --insecure --silent --head "https://localhost:18443/" \
  | tr -d '\r' | grep -qi '^strict-transport-security:'
http_code=$(curl --silent --output /dev/null \
  --write-out '%{http_code}' "http://localhost:18080/")
[[ "$http_code" == "308" || "$http_code" == "301" ]] || {
  echo "FAIL: HTTP must redirect to HTTPS" >&2
  exit 1
}

# PostgreSQL must have applied migrations, and the volume must survive restart.
before=$("${compose[@]}" exec -T db psql -U zemipro_staging \
  -d zemipro_staging -Atc "SELECT COUNT(*) FROM django_migrations")
[[ "$before" =~ ^[0-9]+$ && "$before" -ge 29 ]] || {
  echo "FAIL: missing clean staging migrations" >&2
  exit 1
}
"${compose[@]}" restart db
wait_ready
after=$("${compose[@]}" exec -T db psql -U zemipro_staging \
  -d zemipro_staging -Atc "SELECT COUNT(*) FROM django_migrations")
[[ "$before" == "$after" ]] || { echo "FAIL: migrations not persistent" >&2; exit 1; }
"${compose[@]}" exec -T web python manage.py migrate --check

# Make one synthetic dump and verify format and checksum within private volume.
"${compose[@]}" --profile maintenance run --rm -T backup
"${compose[@]}" --profile maintenance run --rm -T \
  --entrypoint /bin/sh backup -ec '
  set -- /backups/zemipro-staging-*.dump
  [ "$#" -eq 1 ] && [ -f "$1" ]
  sha256sum -c "$1.sha256"
  pg_restore --list "$1" >/dev/null
'

# Narrow synthetic HTTP timing. This is NOT a production/staging host SLO.
times="${RUNNER_TEMP}/zemipro-stage01-http-times.txt"
: > "$times"
for attempt in $(seq 1 100); do
  curl --insecure --fail --silent --output /dev/null \
    --write-out '%{time_total}\n' \
    "https://localhost:18443/categories/" >> "$times"
done
python3 - "$times" <<'PY'
import statistics
import sys
from pathlib import Path

durations = sorted(float(line) for line in Path(sys.argv[1]).read_text().splitlines())
assert len(durations) == 100
print(f"ephemeral_ci_p50_ms={statistics.median(durations) * 1000:.1f}")
print(f"ephemeral_ci_p95_ms={durations[94] * 1000:.1f}")
print("scope=synthetic_localhost_untrusted_certificate_not_real_staging")
PY

echo "PASS: disposable staging loopback TLS, health, static/media, DB persistence, backup integrity"
