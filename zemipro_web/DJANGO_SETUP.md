# ZemiPro Django — reproducible environment setup

This guide covers substage **01.1** only: installing and selecting Django
environments on Windows and Linux. PostgreSQL migrations, Docker/staging
deployment, backups, and CI are handled by later substages.

## Supported runtime

- Python: **3.12.14** (the project supports Python 3.12.x)
- Django: **5.1.15**
- Database: PostgreSQL
- Dependency lock: `requirements.txt` contains exact versions and platform
  markers. Do not install the root bot `requirements.txt` for Django work.

The repository `.python-version` pins the verified Python patch release for
tools such as pyenv. When changing Python or a dependency pin, run the full
Django test suite and `python -m pip check` in a clean virtual environment.

## Prerequisites

1. Install Python 3.12 and PostgreSQL.
2. Create a local PostgreSQL database and user matching `.env`, or adjust the
   environment values for your local installation.
3. Run commands from `zemipro_web`.

No source-code edits are needed to select an environment or database.

## Linux setup

```bash
cd zemipro_web
python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
.venv/bin/python manage.py migrate
.venv/bin/python manage.py seed_repair_categories
.venv/bin/python manage.py seed_israel_cities
.venv/bin/python manage.py runserver
```

## Windows PowerShell setup

```powershell
cd zemipro_web
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.venv\Scripts\python.exe manage.py migrate
.venv\Scripts\python.exe manage.py seed_repair_categories
.venv\Scripts\python.exe manage.py seed_israel_cities
.venv\Scripts\python.exe manage.py runserver
```

For Windows `cmd.exe`, activate with `.venv\Scripts\activate.bat` or keep using
the explicit `.venv\Scripts\python.exe` commands above.

The development server is available at `http://127.0.0.1:8000/`.

## Environment selection

`core.settings` selects a configuration from `DJANGO_ENV`; WSGI, ASGI, and
`manage.py` keep their existing `DJANGO_SETTINGS_MODULE=core.settings` contract.

| `DJANGO_ENV` | Purpose | Defaults |
| --- | --- | --- |
| `development` | Local Windows/Linux work | Debug enabled, localhost hosts, HTTP cookies |
| `test` | Automated tests | Debug disabled, local email, no HTTPS redirect |
| `staging` | Production-like verification | Explicit secret/hosts/database, HTTPS, secure cookies, short HSTS |
| `production` | Live configuration | Explicit secret/hosts/database, HTTPS, secure cookies, one-year HSTS |

Running `python manage.py test` selects `test` automatically unless
`DJANGO_ENV` was explicitly supplied.

## Environment variables

Start from `.env.example`. The local development values are safe placeholders;
the file itself contains no production credentials.

| Variable | Development | Staging/production |
| --- | --- | --- |
| `DJANGO_ENV` | Defaults to `development` | Required operational choice |
| `DJANGO_SECRET_KEY` | Development-only fallback allowed | Required, random, at least 50 characters |
| `DJANGO_DEBUG` | Optional, defaults to `True` | Ignored; always `False` |
| `DJANGO_ALLOWED_HOSTS` | Defaults to localhost | Required explicit hosts; `*` rejected |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Optional comma-separated HTTPS origins | Set when deployment origins require it |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST` | Local defaults available | Required; common placeholder passwords rejected |
| `DB_PORT` | Defaults to `5432` | Defaults to `5432` |

Staging and production enable `SECURE_SSL_REDIRECT`, secure session/CSRF
cookies, and HSTS by default. The corresponding `DJANGO_SECURE_*` variables can
override infrastructure-specific values. Set
`DJANGO_TRUST_X_FORWARDED_PROTO=True` only behind a trusted proxy that replaces
the `X-Forwarded-Proto` header.

Production defaults include HSTS subdomains and preload. Confirm that every
subdomain is HTTPS-ready before deployment; no production deployment is
performed by this setup guide.

## Tests and checks

Linux:

```bash
.venv/bin/python manage.py test
.venv/bin/python manage.py check
.venv/bin/python -m pip check
```

Windows PowerShell:

```powershell
.venv\Scripts\python.exe manage.py test
.venv\Scripts\python.exe manage.py check
.venv\Scripts\python.exe -m pip check
```

Validate a staging or production configuration without deploying it:

```bash
DJANGO_ENV=production python manage.py check --deploy
```

PowerShell equivalent:

```powershell
$env:DJANGO_ENV = 'production'
python manage.py check --deploy
```

Supply all required production variables before that command. It performs
configuration checks only and does not migrate or contact a production database.

## Secret and local-file policy

- Never commit `.env`, private keys, service-account files, database dumps,
  media, credentials, or production values.
- `.gitignore` excludes local environment files, virtual environments, IDE
  configuration, secrets directories, dumps, and generated Django data.
- Commit safe variable names and placeholders only in `.env.example`.
- Rotate any credential that has ever appeared in Git history; removing a file
  from the current tree does not erase history.
