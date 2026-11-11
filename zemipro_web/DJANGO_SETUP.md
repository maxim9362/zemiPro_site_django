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
