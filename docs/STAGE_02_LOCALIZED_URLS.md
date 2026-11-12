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
Unknown aliases 404. This does **not** authorize redirecting legacy/PSEO URLs:
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
