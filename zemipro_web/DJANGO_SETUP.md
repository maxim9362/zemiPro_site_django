# Django environment setup — ZemiPro (substage 01.1)

This document describes development and configuration verification, **not** an
authorization to deploy or migrate production databases. Approved architecture:
one Django/PostgreSQL application inside `zemipro_web/`, no Telegram/PSEO/SQLite
runtime or legacy-data import.

## Versions and prerequisites

- Python **3.12.x**, reference patch **3.12.14** in root `.python-version`.
- Django **5.2.19 LTS**; exact runtime pins in `requirements.txt`.
- PostgreSQL (local development/test database). Do not use production hosts,
  credentials, real customer data, or pre-existing server volumes.
- Docker/staging and CI configurations were implemented in 01.3–01.5; required real-world acceptance is still pending.

## Linux

```bash
cd zemipro_web
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
# Create an empty local PostgreSQL database/role matching your .env first.
.venv/bin/python manage.py check
.venv/bin/python manage.py migrate
.venv/bin/python manage.py seed_repair_categories
.venv/bin/python manage.py seed_israel_cities
.venv/bin/python manage.py runserver
```

## Windows PowerShell

```powershell
cd zemipro_web
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
# Create an empty local PostgreSQL database/role matching your .env first.
.venv\Scripts\python.exe manage.py check
.venv\Scripts\python.exe manage.py migrate
.venv\Scripts\python.exe manage.py seed_repair_categories
.venv\Scripts\python.exe manage.py seed_israel_cities
.venv\Scripts\python.exe manage.py runserver
```

Use the *untracked* `.env` file for locally generated values only. For Windows
`cmd.exe`, use `.venv\Scripts\python.exe` directly or activate with
`.venv\Scripts\activate.bat`. For Linux, use `.venv/bin/python`.
The local address is http://127.0.0.1:8000/.

## Environment selection

`DJANGO_SETTINGS_MODULE` remains `core.settings` in `manage.py`, WSGI and
ASGI. It dispatches to `core.config` based on `DJANGO_ENV`:

| `DJANGO_ENV` | Purpose | Defaults and safeguards |
| --- | --- | --- |
| `development` | local development | `DEBUG=True`, HTTP, local PostgreSQL defaults |
| `test` | isolated test runner | `DEBUG=False`, no redirect, local DB host, test-only DB |
| `staging` | production-like verification | `DEBUG=False`, HTTPS, strong secret, explicit DB/hosts |
| `production` | live config (not deployed) | Same validation; long HSTS without preload by default |

A local `python manage.py test` uses `test` settings even if an untracked
`.env` selects `development`. Explicit `DJANGO_ENV=production/staging` from
the process environment blocks the test command. Test mode accepts only
`DB_HOST=localhost,127.0.0.1,::1,db,postgres`; even for these hosts, make
sure the container/port is a dedicated **synthetic** PostgreSQL instance.
The test database `test_zemipro_db` is managed by Django's test runner.
Django migrations on the real dev or production DB are not run by this command.

## Staging and production configuration (offline check only)

Use **distinct** secrets and PostgreSQL for every environment. Supply these
values through the environment/secret manager; never commit real values:

- `DJANGO_ENV` = `staging` or `production`.
- `DJANGO_SECRET_KEY`: independent randomly generated key of 50+ characters.
- `DJANGO_ALLOWED_HOSTS`: explicit hosts (not `*`).
- `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST` and optional `DB_PORT`.
- `DJANGO_CSRF_TRUSTED_ORIGINS` when required by the actual HTTPS origin.
- If using a trusted reverse proxy **that overwrites incoming header values**,
  only then use `DJANGO_TRUST_X_FORWARDED_PROTO=True`.

Staging and production reject missing/weak secrets and placeholder DB passwords,
ignore `DJANGO_DEBUG` and force HTTPS redirect and secure session/CSRF cookies.
HSTS defaults: staging = 3600 seconds, production = 31536000 seconds.
IncludeSubDomains and preload remain **disabled** until all subdomains have
verified HTTPS and the owner explicitly approves opting in. HSTS config cannot
be turned off by accident; check any changes to `DJANGO_SECURE_HSTS_SECONDS`.

For an **offline-only** deployment configuration check, inject synthetic
environment variables and run:

```bash
python manage.py check --deploy
python -m pip check
```

Do **not** run `migrate`, `collectstatic` against production paths, or
`runserver` in staging/production without a separate owner command.
Some Django deployment checks may warn that HSTS preload is not enabled;
it is intentionally opt-in, not a reason to enable it blindly.

## Email and Google authentication (Draft PR #10)

The default configuration sends no email and exposes no Google OAuth route:
`ZEMIPRO_CONTACT_DELIVERY_MODE=disabled` and
`ZEMIPRO_GOOGLE_LOGIN_ENABLED=False`. New local registrations require email
verification before private pages become available; legacy username/password
accounts remain compatible. SMS, phone login and phone recovery are unsupported.

For an owner-approved isolated staging check, configure Google Client ID/Secret
in the environment and set `ZEMIPRO_GOOGLE_LOGIN_ENABLED=True`. The authorized
callback must exactly match
`https://<approved-host>/oauth/google/login/callback/`. Never put credentials in
`.env.example`, Git, logs or browser-visible settings. Enabling Google without
both values fails startup. OAuth initiation is CSRF-protected POST and allauth
uses state plus PKCE; matching an existing email does not link accounts.

SMTP is separately opt-in with `ZEMIPRO_CONTACT_DELIVERY_MODE=smtp` and all of
`ZEMIPRO_SMTP_HOST`, `ZEMIPRO_SMTP_PORT`, `ZEMIPRO_SMTP_USERNAME`,
`ZEMIPRO_SMTP_PASSWORD`, `ZEMIPRO_EMAIL_FROM`. Incomplete configuration fails
startup. Real Google/SMTP validation requires separate owner approval, public
HTTPS/domain configuration and provider credentials; it is not performed by
local or CI tests.

## Test commands

```bash
cd zemipro_web
python manage.py check
python manage.py test core.tests.test_environment_settings
python manage.py test
python -m pip check
```

Each `python` above must be the Python of the newly created virtual
environment. Test DB privileges must allow creation and deletion of a
**synthetic** test database. `pytest` and CI are handled in 01.3.

For the reusable Codex Cloud/Linux PostgreSQL 17 + Docker + browser workflow,
use `./scripts/shared_test_env.sh verify` followed by `browser`; see
[`docs/SHARED_TEST_ENVIRONMENT.md`](../docs/SHARED_TEST_ENVIRONMENT.md). The
launcher uses a separate loopback-only Compose project and never removes its
persistent volumes in `stop` mode.

## Secret policy and Docker warning

- Commit only placeholder `.env.example`; never commit `.env`, secret
  keys, service-account JSON, DB dumps, local media or private logs.
- `.gitignore` protects Git; `zemipro_web/.dockerignore` additionally
  excludes local secrets and data from the existing Docker build context.
- Separate dev and staging Compose files now provide PostgreSQL 17 health checks
  and persistent volumes. Staging HTTPS and disaster recovery are **not yet
  accepted**. See [01.4 Docker/staging](../docs/STAGE_01_DOCKER_STAGING.md)
  and [01.5 backup/restore](../docs/STAGE_01_LOGGING_BACKUP.md).
  Do not deploy to the current VPS without explicit owner permission.
- Historical credentials must be revoked by the owner before production;
  deleting their files from Git HEAD does not revoke credentials.

## First public pilot: Ashdod only (Stage 02, 2026-11-12)

- Default `core/config/base.py` sets `ZEMIPRO_PILOT_CITY_SLUG='ashdod'` for development/staging/production. It is deliberately not overridable via a production `.env`. Technical PostgreSQL seed still has 25 cities to preserve ID/FK and future expansion; only Ashdod is selectable for current public forms, pages and new service interactions.
- Synthetic `DJANGO_ENV=test` retains generalized multi-city tests. Focused `test_stage02_ashdod_pilot` enables the real pilot setting explicitly; CI Chromium uses test-only `ZEMIPRO_TEST_ASHDOD_ONLY=1`. The test-only switch does not change production defaults.
- Latest automatic code proof: [Django CI #43170333703](https://github.com/maxim9362/zemiPro_site_django/actions/runs/43170333703) (11/11 targeted, 162/162 full, Chrome 45/45); [Docker smoke #43170341760](https://github.com/maxim9362/zemiPro_site_django/actions/runs/43170341760) SUCCESS. Native Hebrew/editorial, real devices, public HTTPS and other release gates remain open; no deployment permitted.

