# ZemiPro

Service marketplace for Israel, built on one existing Django/PostgreSQL codebase in
[`zemipro_web/`](zemipro_web/). No Telegram runtime, Flask/PSEO runtime, SQLite
runtime, or import of legacy user data is supported.

## Local environment (01.1)

Use **Python 3.12.x** (`.python-version`: 3.12.14) and the exact versions in
[`zemipro_web/requirements.txt`](zemipro_web/requirements.txt), including
Django **5.2.19 LTS**. PostgreSQL is the only database backend.

Linux:

```bash
cd zemipro_web
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
# Create the local PostgreSQL role/database and adjust only untracked .env.
.venv/bin/python manage.py migrate
.venv/bin/python manage.py runserver
```

Windows PowerShell:

```powershell
cd zemipro_web
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
# Create the local PostgreSQL role/database and adjust only untracked .env.
.venv\Scripts\python.exe manage.py migrate
.venv\Scripts\python.exe manage.py runserver
```

The development server is local only: http://127.0.0.1:8000/.
No edits to Python source files are needed to configure a local database.

Run checks after configuring a *separate* local test PostgreSQL:

```bash
python manage.py check
python manage.py test
python -m pip check
```

`manage.py test` chooses `DJANGO_ENV=test` and creates a dedicated
`test_zemipro_db` database; remote PostgreSQL hosts are rejected in test mode.

## Environment profiles

`core.settings` selects `DJANGO_ENV=development|test|staging|production`.
Staging/production require an explicit strong secret, allowed hosts, non-placeholder
database credentials, HTTPS redirect and secure cookies. Each environment must
use separate PostgreSQL credentials and physical data. Never use production credentials
for local tests. See [Django setup](zemipro_web/DJANGO_SETUP.md) for full commands,
settings, and safe deployment validation.

## Docker and staging (01.4)

The [development Compose file](zemipro_web/docker-compose.django.yml) binds
the web and PostgreSQL ports to **127.0.0.1** and stores DB/static/media in
separate named volumes. On a verified disposable machine, run from
`zemipro_web/`:

```bash
docker compose -f docker-compose.django.yml config --quiet
docker compose -f docker-compose.django.yml up --build -d
```

A separate [staging Compose](zemipro_web/docker-compose.staging.yml) uses
PostgreSQL 17, Caddy automatic HTTPS, distinct credentials/volumes, and private
media. **Do not deploy staging** until the owner approves a dedicated host,
staging domain, DNS and credentials. Follow the
[01.4 runbook](docs/STAGE_01_DOCKER_STAGING.md); build, HTTPS and persistence
remain unverified until an isolated rehearsal. Do not point any Compose
configuration at production data.

## Continuous integration

The [Django CI workflow](.github/workflows/django-ci.yml) runs on stage-01-development
pushes and PRs targeting main. It uses isolated PostgreSQL 17, Django system/
migration checks, linting, the full test suite and a service coverage gate.
Install additional dev-only tools using
`python -m pip install -r zemipro_web/requirements-ci.txt` from the repository
root (after installing Django runtime requirements). Details and merge-gate
requirements: [01.3 CI acceptance](docs/STAGE_01_CI_ACCEPTANCE.md).

Project rules: [AGENTS.md](AGENTS.md). Implementation and acceptance status:
[roadmap](docs/ROADMAP.md), [progress](docs/PROGRESS.md).
