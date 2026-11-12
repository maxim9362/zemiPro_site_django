# Stage 02.6: integration and mobile RTL acceptance

Status (2026-11-12): CI_VERIFIED / CODE_REVIEW_PASS / SHARED_ENV_VERIFIED / ASHDOD_ONLY_PILOT_APPROVED / ASHDOD_SCOPE_CI_VERIFIED / NEW_SCOPE_CODEX_REVIEW_PENDING / MANUAL_GATES_OPEN. Branch stage-02-catalog-localization; Draft PR #8.
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
- Independent Codex re-review of `cad90a071a169a9d70d99629422ff852db610e7c`: **`CODE_REVIEW_PASS`**. `ZP-02-001 FIXED`, `ZP-02-002 FIXED`, new blockers: none. Targeted local checks covered 16/16 SEO cases, Ruff, Django system/migration checks, legacy links/canonical/hreflang and private contact marker. Unchanged full suite and Chrome were not re-run locally.
- The reviewed exact HEAD `cad90a071` also has [Django CI #43162656220](https://github.com/maxim9362/zemiPro_site_django/actions/runs/43162656220) **SUCCESS** (full 151/151, SEO 16/16, Chrome 45/45, targeted coverage 94.0%) and [isolated Docker smoke #43162656363](https://github.com/maxim9362/zemiPro_site_django/actions/runs/43162656363) **SUCCESS**.
- Reusable isolated environment verification on application baseline `632226b3`: Python 3.12.14 / PostgreSQL 17.11 / existing Docker Compose, clean 34 migrations, repeated seeds and PK/FK/order/questionnaire regressions, normal restart persistence, synthetic checksum dump/restore, full **151/151 PASS**, targeted service coverage **94.0%**. Real headless Chromium checked **180/180** page/language/viewport combinations (320/360/375/390/768/1440), generated 54 screenshots and a RU/EN/HE mobile/desktop sample was visually inspected without clipping. See `docs/SHARED_TEST_ENVIRONMENT.md`. Physical devices and native Hebrew editorial quality remain unverified.
- **Not Stage 02 DONE:** native Hebrew and category/city/questionnaire content review, official nationwide CBS coverage, physical Android/iPhone, original screenshot artifact final UX approval and Stage 08 legacy URL inventory remain open. Off-host backup, real alert delivery, credential rotation, branch protection and publicly trusted staging HTTPS are not verified. **PR #8 remains Draft / NOT_MERGED**, no production/deploy authorization.

## Approved pilot geography and unchanged release gates (2026-11-12)

- **Owner decision:** the technical acceptance boundary for Stage 02 is the existing **25-city pilot** (`6 districts / 25 cities / 4 aliases`), with stable PK/FK, seeds and previously verified automated scenarios. This accepts the limited **scope**, not the quality of all translated content or a real release.
- **Deferred obligation, not waived:** the **official complete CBS Israel locality registry**, alias/name/translation reconciliation and safe data expansion remain **`DEFERRED / REQUIRED_BEFORE_NATIONWIDE_ROLLOUT`**. Do not represent this as nationally complete; do not silently extend coverage or create synthetic supply outside supported locations.
- **Still OPEN before public 25-city pilot:** Hebrew native editorial sign-off for UI and names; approval of 11 added categories, 25 city translations, 4 demo questionnaire texts; physical Android/iPhone checks (`NOT_RUN`); original screenshot and final mobile/RTL UX owner approval. Existing browser checks (CI 45/45 and shared Chromium 180/180) remain validated **emulations only**.
- **Security/infrastructure remain OPEN for corresponding deployment/release:** off-host backup, delivered alert, legacy credential rotation, branch protection, publicly trusted staging HTTPS and authorized DNS/Cloudflare/VPS/production actions. Legacy SEO URL inventory remains mandatory before Stage 08. These are not converted into `PASS` or silently declared `DEFERRED` by the city-scope decision.
- **Stage 02 status remains `CODE_VERIFIED / SHARED_ENV_VERIFIED / MANUAL_GATES_OPEN`, not `DONE`.** Draft PR #8 must not be marked ready, merged or deployed without a new explicit owner instruction.

## Superseding owner clarification: FIRST PILOT = ASHDOD ONLY (2026-11-12)

- The previous 25-city pilot approval is **superseded**, not another supported release scope. Public pilot geography is **Ashdod only**. The existing 25-city seed/6 districts/4 aliases remain *technical test/reference data*; no mass deletion or PK/FK changes authorized.
- **Historical owner-decision checkpoint (before code was written):** current views/forms use active cities, so add and verify **server-side** Ashdod-only allowlist for public city list/details (legacy and RU/EN/HE routes), city selectors, order create/update and worker search/service areas/API as applicable. Other-city direct access must not advertise availability or accept an order. Avoid merely masking frontend controls. Existing migrations/seed counts and legacy contracts must remain intact unless consciously revised with tests. A future CI + focused independent review is required; previous 151/151 and 180/180 counts verify the older wider-scope behavior, not the new pilot restriction.
- Only Ashdod city-name/transliteration requires pilot geography content review now; other city content is for future expansion. Hebrew translations of shared UI, proposed categories and four demo questionnaires still need qualified review. Physical Android/iPhone, owner UX approval, trusted HTTPS staging, backup/alerts/secrets, branch protection and Stage 08 legacy SEO inventory remain open. Full CBS registry remains required before nationwide rollout.
- **Do not mark Stage 02 DONE or merge PR #8.** The newer server-side implementation and new-scope QA evidence are recorded below; no deployment authorization.

## Current Ashdod-only code and acceptance verification (2026-11-12)

- Application commits `43c0b561` + `28133a2f` implement Ashdod-only public service area with central Django query/form/service guards. All 25 seed city records/PK/FK persist. Direct non-Ashdod city pages/aliases, order/post/profile/worker-response endpoints are rejected or hidden; Ashdod continues to work. Existing historical private orders remain protected and readable by owners.
- CI on exact code SHA `28133a2f`: [Django CI #43170333703](https://github.com/maxim9362/zemiPro_site_django/actions/runs/43170333703) SUCCESS, **11/11** new tests, **162/162** full, **45/45** Chrome, **94.7% targeted service coverage**. [Docker smoke #43170341760](https://github.com/maxim9362/zemiPro_site_django/actions/runs/43170341760) SUCCESS.
- The first browser run `43c0b561` failed because synthetic test settings intentionally include full geography; fixed with a **test-only** pilot-mode switch for CI Chromium, not with a production bypass. Production and development default to Ashdod.
- New-scope independent Codex review PENDING. The earlier 180-case shared browser screenshots and 151-test baseline pertain to earlier code; manual HE, Android/iPhone, owner UX approval and external release/backup/alert/secret/staging gates remain OPEN. No Stage 02 DONE, PR merge, or deployment.

