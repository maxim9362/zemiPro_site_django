# ZemiPro — 01.3: CI and synthetic QA acceptance

**Source of truth:** `docs/DEVELOPMENT_PLAN.md` 01.3, `AGENTS.md`,
`REQ-QA-001/003`, `REQ-SEC-003`. The CI workflow lives in
`.github/workflows/django-ci.yml`; it runs on stage-01-development pushes,
PRs targeting main and explicit workflow dispatch.

## Design

- GitHub-hosted Ubuntu runner with **ephemeral PostgreSQL 17** service.
- No shared databases, copied production dumps, live user data, remote
  deployments or external service credentials.
- PostgreSQL uses CI-only synthetic credentials and creates `zemipro_ci`;
  Django's test runner uses its separate `test_zemipro_db`.
- Python 3.12 and exact runtime/CI dependency pins; no Telegram/PSEO/SQLite.
- Checks: `pip check`, `compileall`, Ruff (`E4/E7/E9/F`) over existing
  `apps`, `core` and `manage.py`, Django system check, migration
  drift check, clean migrations, repeated migration check, complete Django
  `manage.py test` suite, production-like deploy check using synthetic
  variables, and coverage report.
- Coverage threshold: **60%** of `apps.marketplace.services`, the current
  critical order/response transactional service layer; this threshold
  is a *starting gate*, not a claim of global 60% project coverage.
  Extend scope and threshold after obtaining a measured baseline.
- No test is skipped intentionally or marked successful without a real run.

## Local reproduction on an explicitly isolated PostgreSQL

```bash
cd zemipro_web
python -m pip install -r requirements.txt -r requirements-ci.txt
python -m pip check
python -m compileall -q apps core manage.py
python -m ruff check apps core manage.py
# Make sure DB_* and DJANGO_ENV=test target ONLY a synthetic local DB.
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py migrate --noinput
python manage.py migrate --check
python -m coverage run manage.py test
python -m coverage report
```

**Warning:** `manage.py test` creates/drops a `test_zemipro_db`. Never run
the test suite against a production or shared database. Verify the instance
identity and privileges before running these commands.

## Required CI check before stage 01 is accepted

The workflow job is named **`django-postgresql`**. The CI job fails when a
lint, check, migration, test or coverage step fails (no `continue-on-error`).
However, **a failing check does not automatically block a GitHub merge unless
branch protection/ruleset requires that check**. Before the final stage 01 PR,
verify a repository ruleset for main requires `django-postgresql`, disallows
bypass and requires PR reviews as appropriate. Check the actual required-check
name and test a deliberately failing change in an isolated, non-production
PR/draft without merging. Do not claim the stage 01.3 merge gate is passed
until that behavior is observed.

## Current verification

- Prior 17 stage-00 Django tests are historical evidence only.
- Configuration tests from 01.1 and PostgreSQL schema tests from 01.2 must run
  in this CI, not just appear in source.
- `CI PASS/FAIL` and coverage percentage must come from actual GitHub Actions
  run output; if actions are disabled or the workflow is pending, label it
  `BLOCKED/NOT_RUN` instead.
- Final independent Codex Cloud review occurs **after 01.1–01.6**.
