# ZemiPro — Stage 02.1: Django catalog hierarchy and seed

**Status:** `IMPLEMENTED / CI_PENDING / LOCAL_VERIFICATION_PENDING`; all work lives on
`stage-02-catalog-localization`. This is **not** a production deployment.

## Scope and source of truth

Based on `docs/TECHNICAL_SPEC.md` `REQ-CAT-001–004`:
- **Section → Category → Subcategory/service** represented by
  `ServiceSection`, `Category`, `Subcategory`; stable database IDs and slugs,
  not translation-dependent identifiers.
- RU/EN/HE names, descriptions, SEO title/description fields and work modes
  (onsite/online/both) are stored in Django models and editable in Admin.
- The dynamic order questionnaire is *not* implemented here; it belongs to
  02.5. Deep unlimited nesting and localized public URLs are likewise later work.
- All existing category and subcategory records are retained by additive
  `0005_catalog_hierarchy`; `Category.section` starts **nullable** to avoid
  rewriting any previously stored relationship.
- Existing orders, responses, worker skills, category IDs and slugs are
  preserved. No operation connects to or imports Telegram/PSEO/SQLite data.
- The 12 section labels are taken directly from REQ-CAT-002. The 8 pre-existing
  repair categories and 56 services/slugs remain as the Django baseline.
  **11 additional sample categories / 32 services** are authored from scratch
  to cover other sections. These names/translations are a **proposed initial
  taxonomy, not yet final editorial or legal approval**; review before public
  rollout. Content expands via Admin without code changes.
- Admin can manually disable categories, modify labels, SEO metadata,
  ordering or work modes; subsequent safe seeding does **not** undo those edits.
  New categorization collisions fail closed. No data removal or re-parenting.

## Operator commands (ONLY an approved isolated local/test PostgreSQL)

From `zemipro_web/` with the correct `DJANGO_ENV`, check the database target
before running any write operation:

```bash
python manage.py makemigrations --check --dry-run
python manage.py migrate --plan
python manage.py migrate --noinput
python manage.py seed_service_catalog --plan
python manage.py seed_service_catalog
python manage.py seed_service_catalog --check
python manage.py seed_service_catalog --check
```

- `--plan` validates source data and counts **without touching the DB**.
- Default command is explicit/manual, atomic and idempotent; never auto-runs
  from a migration, Docker entrypoint, or GitHub CI against any live DB.
- `--check` reads the existing seeded DB and fails when required seed entries
  or translations are missing; no writes.
- Expected baseline when run on an initially empty isolated DB:
  12 sections, 19 categories (8 existing Django repair slugs), 88 subcategories
  (56 existing + 32 sample services).
- This catalog is not a claim that all regulated specialist services are
  legally reviewed, available or validated. Do not auto-publish a marketing
  promise of availability.

## Verification and acceptance

```bash
python -m ruff check apps/marketplace core
python manage.py makemigrations --check --dry-run
python manage.py test apps.marketplace.tests.test_stage02_catalog
python manage.py test
```

Target regressions:
1. Repeated legacy `seed_repair_categories` does not mutate its own global
   manifest and does not overwrite existing labels.
2. `seed_service_catalog` is deterministic with no duplicate slugs, stable IDs
   and no deleted orders/worker references, even after repeated execution.
3. Existing Admin changes (`is_active`, custom name, sort order) survive.
4. Three-language display/fallback; inactive section hides its children from
   public catalog and order form; pre-existing unassigned categories stay visible.
5. Correct migration state on clean and existing synthetic PostgreSQL 17
   databases. Zero legacy imports.

**Still pending:** independent local Windows/Docker Codex verification,
editorial approval of new taxonomy and native-speaking review of Hebrew
translations. Full translated interface and RTL UX is Stage 02.3; public
localized URLs are Stage 02.4; no PR or merge until Stage 02 completion.

The separate four approved frontend HTML mockups are **not edited**.
No production/VPS/DNS/Cloudflare/data-import operations are authorized.
