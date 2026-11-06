# ZemiPro

ZemiPro is a Django/PostgreSQL marketplace for services in Israel. The active
web application is in [`zemipro_web`](zemipro_web/); the repository root also
contains the legacy Telegram bot, which has a separate dependency set and is
not required to run Django.

## Django quick start

The supported runtime is Python **3.12.14** (Python 3.12.x is compatible). All
Django dependencies are exactly pinned in `zemipro_web/requirements.txt`.

### Linux

```bash
cd zemipro_web
python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
# Start/configure local PostgreSQL, then:
.venv/bin/python manage.py migrate
.venv/bin/python manage.py runserver
```

### Windows PowerShell

```powershell
cd zemipro_web
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
# Start/configure local PostgreSQL, then:
.venv\Scripts\python.exe manage.py migrate
.venv\Scripts\python.exe manage.py runserver
```

The copied `.env` is ready for the documented local PostgreSQL defaults. Change
only environment values when your local database differs; Python source edits
are not required.

Run all Django tests with the environment's Python:

```bash
# Linux
.venv/bin/python manage.py test

# Windows PowerShell
.venv\Scripts\python.exe manage.py test
```

`manage.py test` automatically selects the isolated `test` configuration.

Detailed setup, environment variables, Windows/Linux commands, and deployment
configuration checks are documented in
[`zemipro_web/DJANGO_SETUP.md`](zemipro_web/DJANGO_SETUP.md).

## Configuration environments

Set `DJANGO_ENV` to one of:

- `development` — local defaults, `DEBUG=True`, HTTP allowed;
- `test` — isolated test behavior selected automatically by `manage.py test`;
- `staging` — production-like HTTPS defaults and explicit credentials;
- `production` — strict secret/host/database validation and secure HTTPS defaults.

Local `.env` files, keys, credentials, dumps, media, virtual environments, and
IDE settings are ignored by Git. Commit only `.env.example` placeholders.

## Project governance

Development stages and verified status are tracked in `docs/ROADMAP.md` and
`docs/PROGRESS.md`. Follow `AGENTS.md` before changing code or infrastructure.
