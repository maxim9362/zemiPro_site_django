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

The historic Compose file is **not** staging/production ready; Docker health,
persistence, resources, and real staging are covered by substage **01.4**.
Do not deploy or rebuild a live site from this README.

Project rules: [AGENTS.md](AGENTS.md). Implementation and acceptance status:
[roadmap](docs/ROADMAP.md), [progress](docs/PROGRESS.md).
