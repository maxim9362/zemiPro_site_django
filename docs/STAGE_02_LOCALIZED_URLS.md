# Stage 02.4 — additive multilingual public catalog routes

**State:** `IMPLEMENTED / QA_PENDING / NO_DEPLOY`. Single Stage 02 branch and Draft PR #8.
No production URL rewrite, DNS/PSEO migration, sitemap/robots changes or merge.

## Route contract

| Entity | Existing legacy path, preserved | New RU/EN/HE path suffix |
|---|---|---|
| Category list | `/categories/` | `/{lang}/categories/` |
| Category | `/categories/<slug>/` | `/{lang}/categories/<slug>/` |
| City list | `/cities/` | `/{lang}/cities/` |
| City | `/cities/<slug>/` | `/{lang}/cities/<slug>/` |
| Service section | No existing Django route | `/{lang}/sections/<slug>/` |
| Concrete subcategory/service | No existing Django route | `/{lang}/services/<category_slug>/<service_slug>/` |

`{lang}` = `ru`, `en`, `he`. Names are `catalog_i18n:*`
(Django `i18n_patterns(prefix_default_language=True)`); legacy
`marketplace:*`, existing accounts/order/auth API, and unprefixed
`/i18n/setlang/` continue unchanged.

A specific `ServiceSection`, `Category`, `Subcategory` and `City`
retain their database primary keys and canonical slugs across translations.
Localized names/descriptions are properties of those same models. Service URL
includes both category slug and service slug because service slugs are unique
**per category**, not globally. Inactive/deleted sections, categories, cities
and services return 404.

Known `CityAlias.slug` records redirect only **prefixed** city URLs using
a 301 to the current language's canonical `City.slug` (preserve query parameters).
Unknown aliases 404. `LegacySafeLocaleMiddleware` explicitly preserves
legacy unprefixed 404 responses: Django's stock `LocaleMiddleware` would
otherwise auto-redirect a 404 to `/<language>/...` if the new pattern
happened to resolve. Existing language activation and Vary/
Content-Language semantics are preserved. This does **not** authorize redirecting legacy/PSEO URLs:
those need a verified per-URL equivalence migration at Stage 08.

## SEO and safety

Only new language-prefixed catalog pages receive an absolute, query-free
canonical and three reciprocal hreflang alternate tags. URLs are generated
by Django reverse under `translation.override`; the host is taken from
Django's validated request host (not hardcoded `zemipro.co.il`).

**Indexing is OFF by default:** `ZEMIPRO_CATALOG_INDEXING_ENABLED=False`.
All new pages render `<meta name="robots" content="noindex,follow">` unless
this explicitly controlled setting is enabled **and** the page is materially
indexable. Filtered/paginated pages, empty city/category pages, missing
translation/name coverage, and pages without service-level supply continue
to be noindex. `service_detail` is noindex even if the flag is enabled:
category-level worker membership is not evidence a worker offers that exact
subcategory, and must not be advertised otherwise.

No automatic PSEO 301/308, no rewriting of production public paths, no
creation of thin invented SEO claims, no access to private order/user fields.
Existing production website, Cloudflare and its indexation remain unchanged
because no deployment is performed.

## Verification

On the isolated CI PostgreSQL runner:
```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test apps.marketplace.tests.test_stage02_i18n_urls
python manage.py test core.tests.test_i18n
python manage.py test
```

Targeted 02.4 regression tests cover 6 route types × 3 languages,
same entity keys, canonical and hreflang, safe language switch retaining
query, legacy 200 without redirects, known alias 301 only on prefixed path,
invalid/disabled 404, noindex and explicit index flag, internal links and
protection of private worker contacts.

**Acceptance not yet claimed:** GitHub Django CI and disposable Docker
staging smoke on exact head; real mobile RTL at 320/360/375/390/768,
human review of Hebrew, verified legacy PSEO URL inventory before any
live migration. Final stage 02 independent verification is 02.6.

## 02.4 CI fix: source-language URL resolution (2026-11-12)

The first [Django CI #43155090437](https://github.com/maxim9362/zemiPro_site_django/actions/runs/43155090437)
reported nine tests: **2 FAIL / 12 ERROR** within the new 02.4
multilingual route suite. Earlier steps, including ten 02.3 i18n tests,
passed, and the accompanying [Docker smoke #43155090449](https://github.com/maxim9362/zemiPro_site_django/actions/runs/43155090449)
was successful. These are NOT full-suite PASS results for 02.4.

Root causes: tests called `resolve('/en/...')` after leaving the
`translation.override('en')` block; Django resolves `i18n_patterns`
according to the active language. The test now resolves while that
language is active. Separately, Django's default `set_language`
may leave a `/he/...` redirect unchanged when the POST to unprefixed
`/i18n/setlang/` occurs without a Hebrew cookie. New
`core.i18n_views.safe_set_language` validates `next` as an allowed local
URL, temporarily activates its source language, then delegates to
Django's built-in `set_language` for cookie/redirect semantics.
External URL fallback remains guarded by Django. The original
legacy unprefixed 404 redirect was addressed in
`LegacySafeLocaleMiddleware`.

**Gate:** repeat targeted 02.4 tests, 02.3 tests, full Django suite and
Docker smoke on the corrected exact HEAD; no release before success.

## Verified CI result (2026-11-12)

- Source code SHA `8d7427d4641c82283861ad5ea9fdc0fc1952e3b5`.
- [Django CI #43155367524](https://github.com/maxim9362/zemiPro_site_django/actions/runs/43155367524): **SUCCESS**, targeted 02.4 URL suite `9/9 PASS`, 02.3 i18n `10/10 PASS`, complete Django suite `125/125 PASS`, Ruff and migration consistency PASS, service-layer coverage 94.0%.
- [Staging smoke #43155367578](https://github.com/maxim9362/zemiPro_site_django/actions/runs/43155367578): **SUCCESS**, temporary isolated Docker runner.
- `02.4 CODE_DONE / CI_VERIFIED`. This is technical acceptance for additive URLs **only**, not authorization to index, migrate legacy PSEO, or release publicly. Mobile RTL and editorial Hebrew remain open with 02.3/02.6.
