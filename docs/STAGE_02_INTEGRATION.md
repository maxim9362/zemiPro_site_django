# Stage 02.6: integration and mobile RTL acceptance

Status: IMPLEMENTED / QA_PENDING. Branch stage-02-catalog-localization; Draft PR #8.
All seeds, schema checks, browser registration and order tests use isolated, disposable PostgreSQL in GitHub Actions. Never run these commands on production.

## Automated matrix

1. Catalog seed (12 sections, 19 categories, 88 services), geography (6 districts, 25 pilot cities, 4 aliases), optional demo questionnaires (4 drafts/versions), plus duplicate collision rejection.
2. Create one synthetic order with a published questionnaire; repeat all three seeds and assert PK/FK stability, admin edits preserved, old answer/schema snapshots unchanged and no new questionnaire versions.
3. RU/EN/HE path/slug consistency, menu/form rendering and text direction, language switching with query parameters, canonical/hreflang via existing regression suites, and private-answer non-disclosure.
4. Playwright headless Chrome viewport checks at widths 320, 360, 375, 390 and 768 for catalogs, cities and authenticated order form across RU/EN/HE. Assert computed direction, navigation, horizontal overflow and LTR telephone field. Capture screenshots in the GitHub Actions artifact.
5. Complete Django/PostgreSQL tests, Django migrations consistency, Ruff, isolated Docker smoke and independent Codex final review on the exact current PR commit.

## Explicit manual gates

- CI viewport emulation is not proof of actual Android/iPhone hardware behavior. Download and inspect screenshot artifact for clipping, menus, mixed-script fields and form usability; if device unavailable mark physical testing NOT_RUN.
- Native Hebrew proofreading of catalog, city labels and demo questionnaire options; 11 new categories are editorial proposals, 25 cities are a pilot subset rather than official national coverage.
- Localized catalog indexing remains disabled by design; production/real staging DNS, VPS, live PostgreSQL, secrets and public rollout are not part of this acceptance.
- Earlier Stage 00/01 production gates remain open. Do not merge PR #8 without explicit owner permission.

Once Actions and independent Codex run, record SHA, run links, pass/fail counts and any remaining blockers before claiming completion.
