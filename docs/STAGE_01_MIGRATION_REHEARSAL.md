# ZemiPro — 01.2: PostgreSQL migrations and data-preserving rehearsal

**Scope:** isolated PostgreSQL only. Implementation work branch:
`stage-01-development`. This is a verification procedure, **not** a completed
runtime test and **not** authorization to operate production databases.

## Confirmed code review

- One Django ORM and one PostgreSQL transaction database per environment.
- Existing migrations are retained unchanged. `accounts.0001/0002` use the
  split sequence required by the custom user / profile / marketplace dependency.
- `marketplace.0003_require_order_owner` rejects existing null owners before
  changing the `Order.client` FK to `PROTECT` and non-null.
- `Category.slug` and `City.slug` are unique, `Subcategory(category,slug)`
  and `Response(order,worker)` each have a database uniqueness constraint,
  and `Order` already declares its filtering indexes.
- `Order.client/category/city` use `PROTECT`; nullable worker/subcategory
  use `SET_NULL`. Profile and response relationships using `CASCADE` and
  review/notification/moderation retention are **not changed** in this
  foundational stage: any behavioral policy changes require separate approval.
- New `marketplace.0004_status_constraints` and
  `moderation.0002_status_constraint` enforce the existing Django TextChoices
  through PostgreSQL CHECK constraints. They first count unrecognized
  statuses using the migration connection alias and **fail before any write**
  if data is incompatible. No statuses are rewritten, no rows are deleted,
  and no user data is imported.

## Isolation gate before running commands

1. Create a **fresh** local PostgreSQL instance/service dedicated to tests,
   with no external/shared production data or volumes. Verify the target host,
   port, cluster, user, and DB name *out of band*. A familiar name such as
   `localhost` or `db` is **not** evidence of isolation.
2. Use separate synthetic credentials, a non-production role, and an empty
   database such as `zemipro_fixture_01_2`. Never reuse production secrets.
3. Create an isolated Python 3.12 environment with the project requirements.
   Use `DJANGO_ENV=development`, and set `DB_NAME`, `DB_USER`,
   `DB_PASSWORD`, `DB_HOST` and `DB_PORT` to the verified test instance.
4. Verify the connection is the intended isolated instance before *any*
   `migrate` or test command. Stop immediately if uncertain.

## Clean-database rehearsal (commands from `zemipro_web/`)

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py migrate --plan
python manage.py migrate --noinput
python manage.py migrate --check
python manage.py showmigrations accounts marketplace locations moderation notifications analytics
python manage.py migrate --noinput
python manage.py test apps.marketplace.tests.test_schema_constraints
```

Use the Python executable in the project virtual environment, not an unrelated
system Python. `manage.py test` uses the test profile and the dedicated
`test_zemipro_db`, which Django may create/destroy. **Never execute it
against a server where this name could contain real data.**

Verify:
- no unplanned migration files or conflicting graph leaves;
- both new CHECK constraints and existing FK/UNIQUE constraints exist;
- second `migrate` makes no new changes;
- clean test data counts are as expected and no real data is present;
- negative tests reject invalid status strings at PostgreSQL level.

## Restored **synthetic** database rehearsal

Use the guarded, previously tested snapshot utility
`scripts/stage00_pg_snapshot.py` (see `docs/STAGE_00_BACKUP_RESTORE.md`).
It accepts only `zemipro_fixture_*` source and `zemipro_restore_*`
destination names on local loopback. Create the target database in advance
and leave it empty. Archives belong in a protected folder **outside Git**.

For an upgrade rehearsal, create a synthetic DB at the previous migration
heads (including `marketplace.0003` and `moderation.0001`), populate only
invented users/categories/orders/responses/complaints, then take the backup.
Verify the backup and restore it to a **new**, empty isolated database.
Point Django at the restored copy, check migration plan, apply 01.2 migrations,
and run `migrate --check` and `makemigrations --check --dry-run`.

Before and after migration compare counts of `accounts_user`,
`marketplace_category`, `marketplace_subcategory`, `marketplace_order`,
`marketplace_response`, `marketplace_rating`,
`locations_city`, `notifications_notification`,
`moderation_complaint`, `analytics_global_stats`, and
`analytics_category_stats`. Also compare representative IDs, FK targets,
unique-key validity, and status sets. If any count or identity changes
unexpectedly, record `FAIL` and stop; never autofix or delete records.

**Negative rehearsal:** in a throwaway pre-01.2 synthetic database, place
an invalid string into an existing status column, then attempt migration
01.2. It must stop without modifying the data. Restore a clean snapshot
before continuing. Never introduce invalid values into any real database.

## Legacy policy and rollback

The owner explicitly rejected import of Telegram, PSEO/Flask and SQLite data.
There is **no** legacy-user migration plan or source-ID mapping. The only
retained continuity is existing Django migration history and a separate
legacy-URL inventory for stage 08.

CHECK constraints can be removed with a controlled reverse migration in an
isolated copy; this only reverses the added constraints, not the earlier
`Order.client` owner-safety migration. For real deployments, protect data
with a verified backup/restore plan and separately authorize changes; never
automatically revert schema or restore onto production.

**Current verification:** prior stage 00 independently verified 27 applied
Django migrations and synthetic PostgreSQL backup/restore. That evidence
predates the Django 5.2 runtime change and these new migrations and **cannot
substitute for a fresh 01.2 runtime run**. Status remains `NOT_RUN` until
new commands and results are recorded.
