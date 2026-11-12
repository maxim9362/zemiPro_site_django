# Stage 02.6: integration and mobile RTL acceptance

Status (2026-11-12): TECHNICAL_IMPLEMENTATION_COMPLETE / ASHDOD_SCOPE_CI_VERIFIED / OWNER_APPROVED_RELEASE_GATE_DEFERRAL / NEW_SCOPE_CODEX_REVIEW_PENDING / PR_DRAFT. Branch stage-02-catalog-localization; Draft PR #8.
All seeds, schema checks, browser registration and order tests use isolated, disposable PostgreSQL in GitHub Actions. Never run these commands on production.

## Automated matrix

1. Catalog seed (12 sections, 19 categories, 88 services), **technical geography registry** (6 districts, 25 stored cities, 4 aliases; **Ashdod is the only public pilot city**), optional demo questionnaires (4 drafts/versions), plus duplicate collision rejection.
2. Create one synthetic order with a published questionnaire; repeat all three seeds and assert PK/FK stability, admin edits preserved, old answer/schema snapshots unchanged and no new questionnaire versions.
3. RU/EN/HE path/slug consistency, menu/form rendering and text direction, language switching with query parameters, canonical/hreflang via existing regression suites, and private-answer non-disclosure.
4. Playwright headless Chrome viewport checks at widths 320, 360, 375, 390 and 768 for catalogs, cities and authenticated order form across RU/EN/HE. Assert computed direction, navigation, horizontal overflow and LTR telephone field. Capture screenshots in the GitHub Actions artifact.
5. Complete Django/PostgreSQL tests, Django migrations consistency, Ruff, isolated Docker smoke and independent Codex final review on the exact current PR commit.

## Explicit manual gates

- CI viewport emulation is not proof of actual Android/iPhone hardware behavior. Download and inspect screenshot artifact for clipping, menus, mixed-script fields and form usability; if device unavailable mark physical testing NOT_RUN.
- Native Hebrew proofreading of catalog, **Ashdod city labels** and demo questionnaire options; 11 new categories require editorial approval. The other 24 cities are technical data, not launch regions; the complete CBS registry is for later nationwide expansion.
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

## Historical multi-city proposal — SUPERSEDED by Ashdod-only (2026-11-12)

- **Historical decision only — superseded:** an earlier 25-city pilot was considered; the later owner instruction sets **Ashdod ONLY** as the actual public pilot. The 6 districts/25 city records/4 aliases stay as technical fixtures for PK/FK and seed regressions, not an approved multi-city release.
- **Deferred obligation, not waived:** the **official complete CBS Israel locality registry**, alias/name/translation reconciliation and safe data expansion remain **`DEFERRED / REQUIRED_BEFORE_NATIONWIDE_ROLLOUT`**. Do not represent this as nationally complete; do not silently extend coverage or create synthetic supply outside supported locations.
- **Still OPEN before public Ashdod-only pilot:** native Hebrew approval of visible UI, category and Ashdod translations; 11 new categories, four demo questionnaire texts; physical Android/iPhone checks (`NOT_RUN`), screenshot and mobile/RTL UX owner approval. CI browsers are **emulations only**; 180-case shared Chromium evidence is from a prior code SHA.
- **Security/infrastructure remain OPEN for corresponding deployment/release:** off-host backup, delivered alert, legacy credential rotation, branch protection, publicly trusted staging HTTPS and authorized DNS/Cloudflare/VPS/production actions. Legacy SEO URL inventory remains mandatory before Stage 08. These are not converted into `PASS` or silently declared `DEFERRED` by the city-scope decision.
- **Stage 02 status remains `ASHDOD_SCOPE_CI_VERIFIED / NEW_SCOPE_CODEX_REVIEW_PENDING / MANUAL_GATES_OPEN`, not `DONE`.** Draft PR #8 must not be marked ready, merged or deployed without a new explicit owner instruction.

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

## Final code SHA `f21444d7` (2026-11-12)

- Last application polish removes the obsolete Tel Aviv address placeholder from the Ashdod-only order form (uses existing localized “Адрес”). One extra positive UX regression added.
- [Django CI #43171013111](https://github.com/maxim9362/zemiPro_site_django/actions/runs/43171013111): **SUCCESS**, 12/12 Ashdod-only, 163/163 full Django, 45/45 CI browser, targeted service coverage 94.7%. [Docker smoke #43171022632](https://github.com/maxim9362/zemiPro_site_django/actions/runs/43171022632): **SUCCESS**. The test database still seeds 25 technical cities; actual default public mode is only Ashdod.
- Independent new-code Codex review, qualified Hebrew/content, physical mobile tests, UX owner sign-off, staging/backup/alert/credentials and other release gates remain OPEN. Stage 02 NOT DONE, PR #8 Draft/NOT_MERGED, no deploy.

## Owner decision: shift manual/infra gates to pre-public launch (2026-11-12)

- **Approved:** native Hebrew/visible-content editorial signoff, 11 proposed categories, four demo questionnaires, real Android/iPhone, screenshot/mobile RTL owner acceptance, legacy credential revocation, off-host backup/recovery, real alert delivery, branch protection and trusted staging HTTPS are **required BEFORE first public Ashdod pilot**, but do not block technical implementation acceptance or continued isolated development. All remain `OPEN/NOT_RUN/NOT_VERIFIED` and are NOT waived.
- **Still required BEFORE technical closure of Stage 02:** fresh focused **independent Codex review of the Ashdod-only diff**. Previous CODE_REVIEW_PASS concerns earlier code. After PASS, any necessary fixes and matching CI, owner must separately authorize PR #8 Ready/merge. No Stage 02 formal DONE or public activation yet.
- **Preserved earlier deadlines:** Stage 00.4 and legacy SEO URL inventory before Stage 08; full CBS nationwide register before nationwide rollout. Exact obligations and proof: [Stage 02 Release Gates](STAGE_02_RELEASE_GATES.md).

## Independent final Ashdod-only review (2026-11-12)

- Review of `36cfb996` found one HIGH pilot-boundary bypass: a historical worker based outside Ashdod could set `offers_remote` and appear in an online category, open the response endpoint and call `create_response` for an Ashdod order.
- Fix `3a8e9988` requires the worker profile home city itself to be the configured public pilot city before publication, matching, order-feed access or response creation. It preserves every historical city/profile/order row and adds a regression for HTML GET/POST plus direct services.
- Independent isolated PostgreSQL 17 result after the fix: Ashdod-only 13/13; full Django 164/164; Ruff, system/migration/deploy checks, repeatable seeds, synthetic persistence and backup/restore PASS; targeted `marketplace.services` coverage 95.2%. Real Chromium RU/EN/HE at 320/360/375/390/768/1440 px: 180/180 PASS and 54 screenshots visually sampled. Physical Android/iPhone remain NOT_RUN.
- Current-source GitHub Actions are pending after publication of the documentation commit. The PR remains Draft and all manual/infrastructure release gates remain open.

