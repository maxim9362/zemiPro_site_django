# Stage 05.6 — PostgreSQL search baseline and UX gate

Status: MEASUREMENTS_PENDING_CI. Values are not invented.

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

To be filled from the completed successful GitHub Actions run. Search logs for
STAGE05_SEARCH_BASELINE. Record the SHA, run ID, query count and p50 (ms) for
all five scenarios; never fabricate a synthetic throughput figure.

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
