# Stage 03.7 — Telegram-free Django identity and fail-closed migration

**Status:** `CODE_IMPLEMENTED / CI_VERIFIED` on code SHA `6f58ac77` ([GitHub Django CI #43203817702](https://github.com/maxim9362/zemiPro_site_django/actions/runs/43203817702) **SUCCESS**, 241/241 Django, 45/45 Chrome, 12/12 Ashdod-only). Full stage 03 still `IN_PROGRESS / STAGE_REVIEW_PENDING`; [Stage 03 PR #9](https://github.com/maxim9362/zemiPro_site_django/pull/9) is Draft/NOT_MERGED, based on Stage 02 branch. Stage 02 PR #8 is also Draft/NOT_MERGED. No merge or production operation.

## Actual runtime

- Existing Stage 00 eliminated the old Telegram bot and admin-bot source from the development branch. The current Django site registers/logs in users using its own Django sessions and confirmed email/phone authentication. Contact verification uses the existing non-bot providers (real delivery gated); in-app notifications use PostgreSQL, not Telegram.
- The only remaining Telegram-specific **live** Django model/admin references were the optional `User.telegram_id` field and its admin display/search/form fields. Those references are removed, with no changes to `User.role`, `User.active_role`, contact verification or existing user primary keys. Initial migration `accounts.0001_initial` is historical and must remain unchanged.
- No bot-specific settings, Django routes, Telegram webhook, aiogram dependency, Telegram signup or Telegram notifications are added. Former bot infrastructure outside the Django tree is not altered.

## Safe database migration

- `accounts.0010_remove_legacy_telegram_id` depends on `accounts.0009_worker_portfolio` and runs PostgreSQL-only, under Django's normal atomic migration transaction.
- The first operation locks `accounts_user` with `ACCESS EXCLUSIVE` within that transaction and checks that **all** legacy Telegram IDs are NULL. This serializes the check with the schema change; if even one non-null ID exists, it aborts **before** `RemoveField`. No production or user data is exported, reassigned, replaced, nulled or removed by the preflight. The lock can block other DB reads/writes until migration commit; stage/production maintenance windows and lock observation are essential.
- The subsequent `RemoveField` is reversible as a schema operation, reintroducing a nullable column. Reversal **does not restore deleted information**; the preflight guarantees only NULL values would be dropped in the first place. Operators must never bypass the guard or use bulk-null updates to force success. An approved snapshot/backup and a data-retention/legal decision are prerequisites for production if populated historical values are found.
- Before any production deployment: verify isolated restored snapshot, non-null count, migration duration and lock impact; secure backup, test restore, confirm compatibility with external clients/integrations, schedule a maintenance window and obtain specific owner permission. Do **not** run `manage.py migrate` on a live DB merely because this migration exists on GitHub.

## Testing and gates

- `apps.accounts.tests.test_stage03_no_telegram` covers login/register, ORM/Admin absence of the obsolete field, in-app notifications, bot login/webhook URLs returning 404, and forged Telegram identifier ignored.
- `apps.accounts.tests.test_stage03_telegram_migration` exercises the real migration against a disposable PostgreSQL **test** database with one synthetic non-null legacy ID, tests failure without loss, then verifies successful application only after clearing that one synthetic fixture.
- Required CI gates: full Django tests, migration graph consistency, clean database migration, PostgreSQL behavior, Ruff, Ashdod-only 12 tests, 45 Chrome mobile RU/EN/HE cases and stricter staging/production configuration checks; full CI verified on code SHA `6f58ac77`, including synthetic data-preservation migration negative test; independent Codex review and production gates remain open.
- Independent Codex Cloud review, Stage 02 unmerged dependency, operator acceptance, legal data retention, real contact delivery, native Hebrew/device tests and all public Ashdod launch gates remain OPEN. This code is not a live release or official Stage 03 acceptance.
