#!/usr/bin/env bash
# Reusable isolated Stage 00-02 verification environment for Codex Cloud/Linux.
# It reuses the existing development Compose stack and never removes volumes.
set -euo pipefail

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
REPO_DIR=$(CDPATH= cd -- "$PROJECT_DIR/.." && pwd)

MODE=${1:-help}
PROJECT_NAME=${ZEMIPRO_TEST_PROJECT:-zemipro-shared-test}
WEB_PORT=${ZEMIPRO_TEST_WEB_PORT:-18000}
DB_PORT=${ZEMIPRO_TEST_DB_PORT:-15433}
ARTIFACT_DIR=${ZEMIPRO_TEST_ARTIFACT_DIR:-$PROJECT_DIR/artifacts/shared-test-env}
VENV_DIR=${ZEMIPRO_TEST_VENV:-$PROJECT_DIR/.venv-shared-test}
STATUS_FILE="$ARTIFACT_DIR/status.tsv"
BASE_URL="http://127.0.0.1:$WEB_PORT"

case "$PROJECT_NAME" in
  zemipro-shared-*) ;;
  *)
    echo "SAFE_ABORT: ZEMIPRO_TEST_PROJECT must start with zemipro-shared-" >&2
    exit 2
    ;;
esac

export COMPOSE_PROJECT_NAME="$PROJECT_NAME"
export DB_NAME=zemipro_shared
export DB_USER=zemipro_shared
export DB_PASSWORD=synthetic-shared-db-password
export DJANGO_SECRET_KEY=django-insecure-synthetic-shared-test-only-key
export DB_HOST_PORT="$DB_PORT"
export WEB_HOST_PORT="$WEB_PORT"
export STAGING_DOMAIN=localhost
export STAGING_BIND_IP=127.0.0.1
export STAGING_HTTP_PORT=18080
export STAGING_HTTPS_PORT=18443
export STAGING_DB_PASSWORD=synthetic-shared-staging-password
export STAGING_DJANGO_SECRET_KEY=synthetic-shared-staging-secret-0123456789abcdefghijklmnop

unset DOCKER_CONTEXT
DOCKER=(docker --host=unix:///var/run/docker.sock)
COMPOSE_BASE=(-p "$PROJECT_NAME" -f "$PROJECT_DIR/docker-compose.django.yml")
CA_OVERLAY=""
FAILURES=0

mkdir -p "$ARTIFACT_DIR/logs" "$ARTIFACT_DIR/screenshots"

cleanup_overlay() {
  if [[ -n "$CA_OVERLAY" && -f "$CA_OVERLAY" ]]; then
    rm -f -- "$CA_OVERLAY"
  fi
}
trap cleanup_overlay EXIT

prepare_ca_overlay() {
  local ca_file=${ZEMIPRO_BUILD_CA_FILE:-${SSL_CERT_FILE:-}}
  if [[ -n "$ca_file" && -r "$ca_file" ]]; then
    CA_OVERLAY=$(mktemp "${TMPDIR:-/tmp}/zemipro-compose-ca-XXXXXX.yml")
    cat >"$CA_OVERLAY" <<EOF
services:
  web:
    build:
      secrets:
        - source: zemipro_build_ca
          target: build_ca
secrets:
  zemipro_build_ca:
    file: $ca_file
EOF
    COMPOSE_BASE+=(-f "$CA_OVERLAY")
  fi
}

compose() {
  "${DOCKER[@]}" compose "${COMPOSE_BASE[@]}" "$@"
}

require_tools() {
  local missing=0 tool
  for tool in docker curl git python3.12; do
    if ! command -v "$tool" >/dev/null 2>&1; then
      echo "MISSING_TOOL: $tool" >&2
      missing=1
    fi
  done
  [[ "$missing" -eq 0 ]]
  "${DOCKER[@]}" info >/dev/null
  python3.12 -c 'import sys; assert sys.version_info[:2] == (3, 12), sys.version'
}

wait_ready() {
  local attempt
  for attempt in $(seq 1 90); do
    if curl --fail --silent --max-time 3 "$BASE_URL/health/ready/" \
      | grep -q '"status": "ok"'; then
      return 0
    fi
    sleep 2
  done
  echo "FAIL: readiness timeout for $BASE_URL" >&2
  compose ps --all >&2 || true
  return 1
}

seed_reference_data() {
  compose exec -T web python manage.py seed_service_catalog --plan
  compose exec -T web python manage.py seed_service_catalog
  compose exec -T web python manage.py seed_service_catalog --check
  compose exec -T web python manage.py seed_israel_cities --plan
  compose exec -T web python manage.py seed_israel_cities
  compose exec -T web python manage.py seed_israel_cities --check
  compose exec -T web python manage.py seed_demo_questionnaires --plan
  compose exec -T web python manage.py seed_demo_questionnaires --publish
  compose exec -T web python manage.py seed_demo_questionnaires --check
}

start_environment() {
  require_tools
  prepare_ca_overlay
  compose config --quiet
  compose up -d --build
  wait_ready
  seed_reference_data
  curl --fail --silent --max-time 5 "$BASE_URL/health/live/" >/dev/null
  curl --fail --silent --max-time 5 "$BASE_URL/health/ready/" >/dev/null
  curl --fail --silent --max-time 5 "$BASE_URL/" >/dev/null
  curl --fail --silent --max-time 5 "$BASE_URL/static/css/style.css" >/dev/null
  echo "START_PASS base_url=$BASE_URL project=$PROJECT_NAME"
}

ensure_venv() {
  local requirements_hash marker
  marker="$VENV_DIR/.zemipro-requirements.sha256"
  requirements_hash=$(sha256sum "$PROJECT_DIR/requirements.txt" \
    "$PROJECT_DIR/requirements-ci.txt" | sha256sum | awk '{print $1}')
  if [[ ! -x "$VENV_DIR/bin/python" ]]; then
    python3.12 -m venv "$VENV_DIR"
  fi
  if [[ ! -f "$marker" || "$(cat "$marker")" != "$requirements_hash" ]]; then
    "$VENV_DIR/bin/python" -m pip install \
      -r "$PROJECT_DIR/requirements.txt" -r "$PROJECT_DIR/requirements-ci.txt"
    printf '%s\n' "$requirements_hash" >"$marker"
  fi
}

django_test() {
  env \
    DJANGO_ENV=test \
    DJANGO_SETTINGS_MODULE=core.settings \
    DB_HOST=127.0.0.1 \
    DB_PORT="$DB_PORT" \
    DB_NAME="$DB_NAME" \
    DB_USER="$DB_USER" \
    DB_PASSWORD="$DB_PASSWORD" \
    PYTHONDONTWRITEBYTECODE=1 \
    "$VENV_DIR/bin/python" "$PROJECT_DIR/manage.py" "$@"
}

record_step() {
  local label=$1 log rc
  shift
  log="$ARTIFACT_DIR/logs/${label}.log"
  echo "--- $label"
  set +e
  (set -e; "$@") > >(tee "$log") 2>&1
  rc=$?
  set -e
  if [[ "$rc" -eq 0 ]]; then
    printf '%s\tPASS\t%s\n' "$label" "$log" >>"$STATUS_FILE"
  else
    printf '%s\tFAIL\t%s\n' "$label" "$log" >>"$STATUS_FILE"
    FAILURES=$((FAILURES + 1))
  fi
}

compose_config_check() {
  compose config --quiet
  "${DOCKER[@]}" compose -p zemipro-shared-config-check \
    -f "$PROJECT_DIR/docker-compose.staging.yml" config --quiet
  sh -n "$PROJECT_DIR/docker/entrypoint.sh" \
    "$PROJECT_DIR/docker/staging-backup.sh" \
    "$PROJECT_DIR/docker/check-staging-health.sh"
}

deploy_check() {
  env \
    DJANGO_ENV=production \
    DJANGO_SETTINGS_MODULE=core.settings \
    DJANGO_SECRET_KEY=synthetic-production-check-secret-0123456789abcdefghijklmnop \
    DJANGO_ALLOWED_HOSTS=verify.example.invalid \
    DB_HOST=127.0.0.1 \
    DB_PORT="$DB_PORT" \
    DB_NAME="$DB_NAME" \
    DB_USER="$DB_USER" \
    DB_PASSWORD=synthetic-production-check-db-password \
    "$VENV_DIR/bin/python" "$PROJECT_DIR/manage.py" check --deploy
}

seed_roundtrip_check() {
  django_test seed_service_catalog --plan
  django_test seed_service_catalog
  django_test seed_service_catalog --check
  django_test seed_service_catalog
  django_test seed_israel_cities --plan
  django_test seed_israel_cities
  django_test seed_israel_cities --check
  django_test seed_israel_cities
  django_test seed_demo_questionnaires --plan
  django_test seed_demo_questionnaires --publish
  django_test seed_demo_questionnaires --check
  django_test seed_demo_questionnaires --publish
  django_test shell -c "from apps.marketplace.models import ServiceSection,Category,Subcategory,ServiceQuestionnaire,QuestionnaireVersion; from apps.locations.models import District,City,CityAlias; counts=(ServiceSection.objects.count(),Category.objects.count(),Subcategory.objects.count(),District.objects.count(),City.objects.count(),CityAlias.objects.count(),ServiceQuestionnaire.objects.count(),QuestionnaireVersion.objects.count()); assert counts==(12,19,88,6,25,4,4,4), counts; print('SEED_COUNTS_PASS', counts)"
}

persistence_check() {
  local before after
  before=$(compose exec -T db psql -U "$DB_USER" -d "$DB_NAME" -Atc \
    "SELECT CONCAT((SELECT count(*) FROM django_migrations),':',(SELECT count(*) FROM marketplace_service_section),':',(SELECT count(*) FROM locations_city));")
  compose restart db
  wait_ready
  after=$(compose exec -T db psql -U "$DB_USER" -d "$DB_NAME" -Atc \
    "SELECT CONCAT((SELECT count(*) FROM django_migrations),':',(SELECT count(*) FROM marketplace_service_section),':',(SELECT count(*) FROM locations_city));")
  [[ "$before" == "$after" ]]
  echo "PERSISTENCE_PASS migrations:sections:cities=$after"
}

backup_restore_check() {
  local restore_db=zemipro_restore_check dump=/tmp/zemipro-shared-restore.dump
  compose exec -T db sh -eu -c "dropdb --if-exists -U '$DB_USER' '$restore_db'; rm -f '$dump' '$dump.sha256'"
  compose exec -T db pg_dump -U "$DB_USER" -d "$DB_NAME" \
    --format=custom --no-owner --no-acl --file="$dump"
  compose exec -T db sh -eu -c "sha256sum '$dump' >'$dump.sha256'; sha256sum -c '$dump.sha256'; pg_restore --list '$dump' >/dev/null"
  compose exec -T db createdb -U "$DB_USER" "$restore_db"
  compose exec -T db pg_restore -U "$DB_USER" -d "$restore_db" \
    --exit-on-error --no-owner --no-acl "$dump"
  compose exec -T db sh -eu -c "a=\$(psql -U '$DB_USER' -d '$DB_NAME' -Atc 'SELECT count(*) FROM django_migrations'); b=\$(psql -U '$DB_USER' -d '$restore_db' -Atc 'SELECT count(*) FROM django_migrations'); test \"\$a\" = \"\$b\""
  compose exec -T db dropdb -U "$DB_USER" "$restore_db"
  compose exec -T db rm -f "$dump" "$dump.sha256"
  echo "BACKUP_RESTORE_PASS scope=synthetic_same_host_not_off_host"
}

current_tree_security_check() {
  local prohibited key_files credential_files
  prohibited=$(git -C "$REPO_DIR" ls-files | awk '
    /(^|\/)\.env$/ || /service_account.*\.json$/ || /\.(pem|key|p12|pfx|dump|bak|sqlite|sqlite3|db)$/ {print}
  ')
  [[ -z "$prohibited" ]] || {
    echo "Tracked prohibited files:" >&2
    printf '%s\n' "$prohibited" >&2
    return 1
  }
  key_files=$(git -C "$REPO_DIR" grep -IlE -- \
    '-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----' -- . || true)
  credential_files=$(git -C "$REPO_DIR" grep -IlE -- \
    '(socks5|https?)://[^/@[:space:]]+:[^/@[:space:]]+@' -- . || true)
  [[ -z "$key_files" && -z "$credential_files" ]] || {
    echo "High-confidence credential material found in tracked files (filenames only):" >&2
    printf '%s\n%s\n' "$key_files" "$credential_files" | sed '/^$/d' >&2
    return 1
  }
  if rg -l -i '(^|[[:space:]])(from|import)[[:space:]]+(telegram|flask|sqlite3)' \
    "$PROJECT_DIR/apps" "$PROJECT_DIR/core" | grep -q .; then
    echo "Forbidden legacy runtime import detected" >&2
    return 1
  fi
  if rg -i '(telegram|flask|sqlite)' "$PROJECT_DIR/requirements.txt" >/dev/null; then
    echo "Forbidden legacy runtime dependency detected" >&2
    return 1
  fi
  echo "CURRENT_TREE_SECURITY_PASS no_values_printed=true"
}

coverage_suite() {
  cd "$PROJECT_DIR"
  django_test shell -c "print('TEST_DATABASE_TARGET=test_zemipro_db')"
  env \
    DJANGO_ENV=test DJANGO_SETTINGS_MODULE=core.settings \
    DB_HOST=127.0.0.1 DB_PORT="$DB_PORT" DB_NAME="$DB_NAME" \
    DB_USER="$DB_USER" DB_PASSWORD="$DB_PASSWORD" PYTHONDONTWRITEBYTECODE=1 \
    "$VENV_DIR/bin/python" -m coverage erase
  env \
    DJANGO_ENV=test DJANGO_SETTINGS_MODULE=core.settings \
    DB_HOST=127.0.0.1 DB_PORT="$DB_PORT" DB_NAME="$DB_NAME" \
    DB_USER="$DB_USER" DB_PASSWORD="$DB_PASSWORD" PYTHONDONTWRITEBYTECODE=1 \
    "$VENV_DIR/bin/python" -m coverage run manage.py test --noinput
  "$VENV_DIR/bin/python" -m coverage report
}

verify_environment() {
  start_environment
  ensure_venv
  : >"$STATUS_FILE"
  set -e
  record_step pip-check "$VENV_DIR/bin/python" -m pip check
  record_step python-compile "$VENV_DIR/bin/python" -m compileall -q \
    "$PROJECT_DIR/apps" "$PROJECT_DIR/core" "$PROJECT_DIR/manage.py"
  record_step ruff "$VENV_DIR/bin/python" -m ruff check \
    "$PROJECT_DIR/apps" "$PROJECT_DIR/core" "$PROJECT_DIR/manage.py"
  record_step compose-config compose_config_check
  record_step django-check django_test check
  record_step migration-consistency django_test makemigrations --check --dry-run
  record_step migrations-applied django_test migrate --check
  record_step deploy-check deploy_check
  record_step current-tree-security current_tree_security_check
  record_step seed-roundtrip seed_roundtrip_check
  record_step restart-persistence persistence_check
  record_step backup-restore backup_restore_check
  record_step full-django-coverage coverage_suite
  set +e
  write_report
  if [[ "$FAILURES" -ne 0 ]]; then
    echo "VERIFY_FAIL failures=$FAILURES report=$ARTIFACT_DIR/report.md" >&2
    return 1
  fi
  echo "VERIFY_PASS report=$ARTIFACT_DIR/report.md"
}

browser_check() {
  start_environment
  ensure_venv
  if ! "$VENV_DIR/bin/python" -c 'import playwright' >/dev/null 2>&1; then
    "$VENV_DIR/bin/python" -m pip install playwright==1.56.0
  fi
  local log="$ARTIFACT_DIR/logs/browser.log" rc
  if [[ -f "$STATUS_FILE" ]]; then
    grep -v $'^browser-smoke\t' "$STATUS_FILE" >"$STATUS_FILE.tmp" || true
    mv "$STATUS_FILE.tmp" "$STATUS_FILE"
  fi
  set +e
  env DJANGO_ENV=development DJANGO_SETTINGS_MODULE=core.settings \
    DB_HOST=127.0.0.1 DB_PORT="$DB_PORT" \
    ZEMIPRO_TEST_BASE_URL="$BASE_URL" \
    ZEMIPRO_TEST_SCREENSHOT_DIR="$ARTIFACT_DIR/screenshots" \
    "$VENV_DIR/bin/python" "$PROJECT_DIR/scripts/shared_browser_smoke.py" \
    > >(tee "$log") 2>&1
  rc=$?
  set -e
  # Keep the persistent development volume useful across repeated runs without
  # accumulating browser-only registrations. The prefix is exclusive to this tool.
  compose exec -T web python manage.py shell -c \
    "from apps.accounts.models import User; deleted,_=User.objects.filter(username__startswith='shared_browser_').delete(); print('BROWSER_SYNTHETIC_USERS_REMOVED', deleted)" \
    >>"$log" 2>&1 || true
  if [[ "$rc" -eq 0 ]]; then
    printf 'browser-smoke\tPASS\t%s\n' "$log" >>"$STATUS_FILE"
  else
    printf 'browser-smoke\tFAIL\t%s\n' "$log" >>"$STATUS_FILE"
  fi
  write_report
  return "$rc"
}

write_report() {
  local sha timestamp
  sha=$(git -C "$REPO_DIR" rev-parse HEAD)
  timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  {
    echo "# ZemiPro shared test environment report"
    echo
    echo "- Generated: $timestamp"
    echo "- Commit: \`$sha\`"
    echo "- Compose project: \`$PROJECT_NAME\`"
    echo "- Base URL: \`$BASE_URL\`"
    echo "- Data: synthetic PostgreSQL 17 only"
    echo
    echo "| Check | Status | Evidence |"
    echo "|---|---|---|"
    if [[ -s "$STATUS_FILE" ]]; then
      while IFS=$'\t' read -r label status evidence; do
        echo "| $label | $status | \`$evidence\` |"
      done <"$STATUS_FILE"
    else
      echo "| automated checks | NOT_RUN | Run \`scripts/shared_test_env.sh verify\` |"
    fi
    echo
    echo "Persistent Compose volumes are preserved by \`stop\`; no production, VPS, DNS or Cloudflare resources are used."
  } >"$ARTIFACT_DIR/report.md"
  echo "REPORT_READY $ARTIFACT_DIR/report.md"
}

stop_environment() {
  require_tools
  prepare_ca_overlay
  compose down --remove-orphans
  echo "STOP_PASS volumes_preserved=true project=$PROJECT_NAME"
}

case "$MODE" in
  start) start_environment ;;
  verify) verify_environment ;;
  browser) browser_check ;;
  report) write_report ;;
  stop) stop_environment ;;
  *)
    cat <<EOF
Usage: scripts/shared_test_env.sh {start|verify|browser|report|stop}

  start    Build/start the isolated Compose stack, migrate and seed it.
  verify   Start if needed; run one complete Stage 00-02 automated suite.
  browser  Run real headless Chromium viewport checks and screenshots.
  report   Rebuild the Markdown summary from saved status artifacts.
  stop     Stop only this Compose project; persistent volumes are preserved.
EOF
    [[ "$MODE" == help || "$MODE" == -h || "$MODE" == --help ]]
    ;;
esac
