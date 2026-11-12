# ZemiPro shared isolated test environment

**Status (2026-11-12):** `READY / CODEX_CLOUD_VERIFIED / SYNTHETIC_DATA_ONLY`.
This is a reusable verification layer over the existing Django project and
`docker-compose.django.yml`; it is not another application, CI system or
deployment configuration.

## Safety boundary

- Python 3.12, the repository's pinned Django dependencies and PostgreSQL 17 are used.
- Compose project `zemipro-shared-test` binds only `127.0.0.1:18000` (web) and
  `127.0.0.1:15433` (database). Its named volumes have the same project prefix.
- Credentials, accounts, database content and browser input are synthetic. No
  production/VPS/DNS/Cloudflare connection is made.
- `stop` runs Compose `down --remove-orphans` for this exact project and does
  **not** pass `--volumes`. The PostgreSQL/static/media volumes therefore survive
  an ordinary stop/start. Deleting them always requires a separate explicit action.
- Backup/restore verification creates and removes only the exact temporary database
  `zemipro_restore_check` inside the isolated PostgreSQL container. It does not
  establish an off-host backup or recovery policy.
- A managed runner may provide `SSL_CERT_FILE`. The launcher passes that CA to pip
  as an optional BuildKit secret. It is not copied into an image layer. Standard
  Docker builds remain unchanged when no private CA is needed.

Before the first run, inspect `docker ps -a` and `docker volume ls` if the daemon is
shared. The launcher refuses a custom Compose project name unless it starts with
`zemipro-shared-`.

## One-command workflow

From the repository root:

```bash
cd zemipro_web
./scripts/shared_test_env.sh start
./scripts/shared_test_env.sh verify
./scripts/shared_test_env.sh browser
./scripts/shared_test_env.sh report
./scripts/shared_test_env.sh stop
```

Modes:

| Mode | Action |
|---|---|
| `start` | Checks tools, builds/starts the existing dev Compose stack, waits for readiness, migrates and idempotently seeds catalog/geography/questionnaires. |
| `verify` | Calls `start` if necessary, then runs the complete non-browser Stage 00–02 verification once and writes evidence. |
| `browser` | Uses actual headless Chromium against the running HTTP site, checks RU/EN/HE at 320/360/375/390/768/1440 px and writes screenshots. |
| `report` | Rebuilds `artifacts/shared-test-env/report.md` from the saved status file. |
| `stop` | Stops only `zemipro-shared-test`; preserves all named volumes. |

The ports and local paths can be changed without editing Python:

```bash
ZEMIPRO_TEST_WEB_PORT=28000 \
ZEMIPRO_TEST_DB_PORT=25433 \
ZEMIPRO_TEST_PROJECT=zemipro-shared-next \
./scripts/shared_test_env.sh verify
```

`ZEMIPRO_TEST_ARTIFACT_DIR`, `ZEMIPRO_TEST_VENV` and
`ZEMIPRO_BUILD_CA_FILE` are also supported. Do not point these variables at
production resources or reuse real credentials.

## Automated verification contract

`verify` performs:

1. pinned dependency installation and `pip check`;
2. Python compile and Ruff;
3. development/staging Compose rendering and shell syntax;
4. Django system check, model/migration consistency and applied-migration check;
5. offline production `check --deploy` with synthetic settings;
6. a current-tree high-confidence secret/prohibited-file check and rejection of
   Telegram/Flask/SQLite runtime imports/dependencies;
7. repeatable catalog `12/19/88`, geography `6/25/4` and questionnaire `4/4`
   seeds;
8. normal container restart with migration/catalog/city count persistence;
9. synthetic PostgreSQL custom-format dump, SHA-256/`pg_restore --list`, isolated
   restore and migration-count comparison;
10. one full Django suite through Coverage. The existing `.coveragerc` measures
    `apps.marketplace.services`, not whole-project coverage.

The full Django suite already contains authorization, registration/login,
anonymous-order rejection, owner/worker access, private address/phone and
questionnaire-answer protection, own-order response rejection, concurrent worker
selection, pagination/error handling, migration constraints, seed PK/FK/order
preservation, immutable questionnaire versions, RU/EN/HE routes, SEO
noindex/canonical/hreflang and legacy URL tests.

`browser` opens the home page, catalog, section, category, service, city list,
city detail, login, registration and authenticated order form. It asserts HTTP
success, document/CSS direction, menu/forms, language switch with query retention,
LTR telephone input, mixed-script input, JavaScript/request failures and horizontal
overflow. Screenshots are captured for home/catalog/order in each language and
width. These are desktop Chromium viewport emulations, **not physical Android or
iPhone tests**.

Generated files are intentionally ignored by Git:

```text
zemipro_web/artifacts/shared-test-env/report.md
zemipro_web/artifacts/shared-test-env/logs/
zemipro_web/artifacts/shared-test-env/screenshots/
zemipro_web/artifacts/shared-test-env/browser-result.json
```

## Verified baseline: Stage 00–02

Verification against code baseline `632226b3e24601b4eb469172667ab89b21d6fe6a`
and the shared-environment changes in its working branch produced:

- PostgreSQL `17.11`; 34 migrations; non-root Django container user;
- Ruff, compile, pip, Django/system/migration/deploy checks: PASS;
- repeat seeds: `12/19/88`, `6/25/4`, `4/4` with no duplicate rows: PASS;
- normal full Compose restart: migration/section/city counts `34:12:25`
  preserved;
- synthetic same-host dump/checksum/restore: PASS;
- full Django suite: **151/151 PASS**;
- targeted service-layer coverage: **94.0%**;
- Chromium: **180/180 cases PASS**, 54 screenshots, no unexpected HTTP/JS
  errors or horizontal overflow;
- screenshot sample visually inspected for RU/EN/HE mobile and desktop: no
  clipping found. Native Hebrew editorial correctness was not accepted by this
  technical review.

The isolated daemon reported rootless mode without cgroups. Therefore staging
memory-limit enforcement is `NOT_RUN` here even though the Compose values render.
Production-like public TLS, trusted DNS, alert delivery and off-host backup are
also outside this environment.

| Stage | Code | Migrations | Tests | UI | Security | Manual/external gates | Verdict |
|---|---|---|---|---|---|---|---|
| 00 | PASS | PASS | PASS | NOT_RUN | PASS for current tree | credential provider revocation; return to 00.4 before Stage 08 | `CORE_VERIFIED / FOLLOW_UP_REQUIRED` |
| 01 | PASS | PASS | 151/151 PASS | Chromium PASS | authorization/privacy/deploy checks PASS | public trusted staging, off-host backup, delivered alert, branch protection, physical HE devices, memory enforcement | `LOCAL_VERIFIED / EXTERNAL_GATES_OPEN` |
| 02 | PASS | PASS | integration included in 151/151 | 180/180 Chromium PASS | privacy and SEO guards PASS | native HE/editorial catalog review, CBS national coverage, physical devices, final owner screenshot approval | `CODE_VERIFIED / MANUAL_GATES_OPEN` |

## Adding later stages

Stage 03 and later should add their unit/integration tests to the normal Django
test discovery and add only genuinely new browser paths/assertions to
`shared_browser_smoke.py`. The common launcher should continue to run the whole
project once. Keep targeted tests in GitHub Actions for fast diagnosis, but do not
create a second workflow or duplicate the existing Compose definitions merely to
use this tool.

This environment is evidence for local isolated behavior only. Merge, deployment,
live database migration and public activation remain separate owner decisions.

## Ashdod-only application policy after the original baseline (2026-11-12)

- Development/staging/production default to `ZEMIPRO_PILOT_CITY_SLUG='ashdod'` (not an environment switch). Only Ashdod is available to public city/worker/order/profile flows; 25 internal city rows remain unchanged.
- Broad historical synthetic multi-city tests keep their behavior under `DJANGO_ENV=test`. Focused `test_stage02_ashdod_pilot` explicitly enables the pilot policy; CI headless Chrome sets `ZEMIPRO_TEST_ASHDOD_ONLY=1` and checks a single city in the city list/order form.
- New code SHA `28133a2f`: CI #43170333703 passed 11/11 targeted, 162/162 full and 45/45 CI Chrome. **The earlier shared-environment 180/180 browser cases have NOT been rerun on this new SHA**; use `./scripts/shared_test_env.sh verify` and `browser` for fresh evidence when required.

