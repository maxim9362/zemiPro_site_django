# Stage 02.6: integration and mobile RTL acceptance

Status (2026-11-12): CI_VERIFIED / TARGETED_CODEX_RECHECK_PENDING / MANUAL_GATES_OPEN. Branch stage-02-catalog-localization; Draft PR #8.
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

## Current verification and acceptance state (2026-11-12)

- Original Codex independent review on SHA `127a9d7e3ea8039f093d85e34bd184c365486587` found `ZP-02-001` (MEDIUM/BLOCKER, missing EN/HE SEO noindex) and `ZP-02-002` (stale QA documentation); verdict `CHANGES_REQUIRED` **for that SHA**.
- Fix commit `067da9da669a9c66645404b1ec293cada1144f74`: SEO noindex now checks all displayed names and required descriptions in RU/EN/HE; default indexing still disabled and normal Russian display fallback unchanged. Seven regression tests added.
- [GitHub Django CI #43162334570](https://github.com/maxim9362/zemiPro_site_django/actions/runs/43162334570): **SUCCESS**, targeted SEO `16/16`, Stage 02.6 integration `4/4`, RU/EN/HE locale `10/10`, Chrome emulation `45/45`, **full Django `151/151` PASS**; migration consistency, Ruff and isolated seed roundtrips PASS, service-only coverage **94.0%**.
- [Disposable Docker staging smoke #43162342520](https://github.com/maxim9362/zemiPro_site_django/actions/runs/43162342520): **SUCCESS** on the same fix commit.
- Next: Codex should independently confirm only corrected `ZP-02-001` and linked acceptance docs against the new HEAD, without re-running unrelated unchanged areas. The correction has **not** received its own independent Codex verdict yet.
- Outstanding manual gates and earlier Stage 00/01 infrastructure follow-ups remain as listed above; CI cannot substitute for native Hebrew sign-off or physical devices. **PR #8 remains Draft, no merge or deployment**.
