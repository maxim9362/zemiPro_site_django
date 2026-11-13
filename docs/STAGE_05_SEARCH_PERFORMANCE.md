# Stage 05.6 — PostgreSQL search baseline and UX gate

Status: CI_VERIFIED. All values below were captured from a single successful run on isolated synthetic data.

## Isolated dataset and method

- Source: Django test class Stage05SearchBaselineTests.
- Database: CI PostgreSQL 17 (isolated, synthetic, disposable), no production data.
- 300 synthetic published profiles, one Ashdod city, one category, one concrete
  service, two remote-service cohorts and deterministic starting prices.
- 10 workers per page. Warm-up request then three sequential Django test client
  requests per scenario; report SQL query count and measured wall-clock p50.
- Five scenarios: default relevance, multifilter remote, keyword/rating,
  empty results, invalid filters.
- Extra 20-vs-300 query-scaling test for N+1; selected SQL EXPLAIN without
  ANALYZE, verified public-search index; stable pagination and malformed form
  tests. SQL EXPLAIN is diagnostic and is not a load test.
- RU/EN/HE locale and RTL Chrome emulation (320, 360, 375, 390, 768, 1440px)
  covers specialist directory, specialist profile and invitation CTA.

## Actual measurement

Source: GitHub Actions run #43397840288, commit 2aca30fedebd766849818cad68d7f9314714c771,
SUCCESS, PostgreSQL 17, Django 397/397, Ruff, browser 90/90.
Full run: https://github.com/maxim9362/zemiPro_site_django/actions/runs/43397840288

| Scenario | SQL query count | p50 (milliseconds) | Matching workers |
|---|---:|---:|---:|
| Unfiltered relevance | 10 | 81.93 | 300 |
| Combined category/service/city/language/online/availability/price | 14 | 74.73 | 126 |
| Keyword + real-rating sort | 10 | 57.87 | 300 |
| Empty results | 8 | 74.44 | 0 |
| Invalid parameters | 5 | 18.29 | 0 |

Measured: 3 warm-cache serial samples per case after a warm-up GET.
Search pagination: 10 per page. The 20→300 N+1 regression passed.
EXPLAIN root: Sort (cost=656.46..656.47 rows=1 width=4424).
An index scan was observed in the query plan, and the
worker_public_search_idx index exists. This does NOT establish that the
specific worker index was chosen for all paths.
Chrome emulation: 90 page/viewport/language cases, 320–1440px, RU/EN/HE,
RTL, published profile, invitation CTA and search form — PASS.

Source line identifier: STAGE05_SEARCH_BASELINE. These are synthetic
CI observations, not guaranteed response times or SLOs.

## Known limits and interpretation

- Django test client timings exclude network transfer, actual browser paint
  and mobile hardware. A shared GitHub runner is neither a production server
  nor a stable timing environment, and three samples do not prove p95 or p99.
- 300 profiles are a diagnostic set, not a nationwide volume.
- PostgreSQL planner may choose Seq Scan for small synthetic tables even with
  suitable indexes. Existing B-tree and foreign-key indexes are retained.
- Keyword contains searches may require separate trigram/full-text analysis
  when REAL scale evidence warrants it; no search backend, cache, queue or
  PostgreSQL extension was added speculatively.
- Default indexing of directory and filter pages stays OFF, including
  infinite filter permutations and empty pages.
- Browser screenshots are emulator smoke, NOT physical device acceptance.

No live database, secret, VPS, DNS, Cloudflare or deployment touched.
