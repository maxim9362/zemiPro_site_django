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

## Post-review privacy-remediation baseline (separate runner)

After independent review found a contact-search oracle, search and ranking
were switched from raw description/display_name to server-maintained,
contact-free columns. Original pre-remediation numbers above are retained
for traceability, **not** presented as current code measurements.

- Code SHA: `abeebd96e6703e8e9bc2a7aaaf1e2227a97b4348`
- Isolated [GitHub Actions #43406092323](https://github.com/maxim9362/zemiPro_site_django/actions/runs/43406092323): SUCCESS, 404/404 Django; PostgreSQL 17, same 300 synthetic worker fixtures, same five scenarios, three warm-cache sequential samples each.
- `STAGE05_SEARCH_BASELINE` measurements:

| Scenario | SQL queries | p50 (ms) | Matches |
|---|---:|---:|---:|
| Unfiltered | 10 | 77.94 | 300 |
| Complex filters | 14 | 70.26 | 126 |
| Keyword / real-rating sort | 10 | 57.73 | 300 |
| No results | 8 | 74.50 | 0 |
| Invalid parameters | 5 | 17.82 | 0 |

EXPLAIN root: `Sort (cost=193.02..193.02 rows=1 width=4714)`;
an index scan occurs in the plan; this does not establish selection of
`worker_public_search_idx` specifically. Additional negative tests ensure
hidden email and phone substrings are NOT keyword matches.

## Contact-policy v2 remediation baseline (isolated CI)

Independent review ZP-05-003 HIGH led to a second contact-free
keyword normalization pass for `@handles` and slash-delimited phone numbers.
[GitHub CI #43411640036](https://github.com/maxim9362/zemiPro_site_django/actions/runs/43411640036)
SUCCESS on code SHA `40e69324919220df80db87879718b2ab3e545ead`.
Same 300 synthetic published profiles / 10-per-page / PostgreSQL 17 /
single CI runner / three serial post-warmup samples:

| Scenario | SQL query count | p50 (ms) | Matches |
|---|---:|---:|---:|
| Unfiltered | 10 | 109.56 | 300 |
| Complex filters | 14 | 96.34 | 126 |
| Keyword + real-rating sort | 10 | 76.79 | 300 |
| Empty | 8 | 96.93 | 0 |
| Invalid filters | 5 | 25.36 | 0 |

The query-count baseline remained constant; p50 differs across runners
and is not an SLO. Index scan present in EXPLAIN, but a specific worker
index cannot be inferred from that boolean alone. 413 Django tests
(including 9 added privacy checks) and 90 browser emulation cases passed.

## Unicode/contact URL remediation baseline (contact policy v3)

After ZP-05-004 HIGH was independently reproduced, the search copies were
re-scrubbed using NFKC and contact-policy v3. Historical numbers above remain
preserved and are NOT results for the current v3 code.

Code commit `30da440f00f522c807658636bb65f36085ceaf50`:
[GitHub Actions #43418780544](https://github.com/maxim9362/zemiPro_site_django/actions/runs/43418780544)
SUCCESS (423/423 Django; PostgreSQL 17; Ruff; 90 headless Chrome cases).
Same 300 synthetic profiles and five scenarios with three warm-cache
sequential samples. No live data.

| Scenario | SQL queries | p50 (ms) | Results |
|---|---:|---:|---:|
| Unfiltered | 10 | 85.24 | 300 |
| Complex combined filters | 14 | 74.92 | 126 |
| Keyword + real-rating sort | 10 | 57.32 | 300 |
| Empty query | 8 | 75.39 | 0 |
| Invalid filters | 5 | 21.10 | 0 |

Queries have not increased due to v3 on this data; these timings are NOT
production latency guarantees. SQL EXPLAIN still indicates an index scan
somewhere in the query plan, not proof of a specific chosen worker index.
Independent security re-review is REQUIRED before merge.

## Contact-policy v4 remediation baseline (isolated CI only)

ZP-05-005 HIGH required a further forward-only contact-free search
rebuild (accounts.0018). v4 uses Unicode punctuation and IDN/URI filtering
plus phone-digit count. Earlier numbers remain historical; they are not
claimed to measure v4. The working-hours exception is scoped to that
field only; searchable text remains strictly contact-free.

Actual code SHA `6107e85d72441d91226ef565d01c494e2b76640b`;
[GitHub Actions #43431571624](https://github.com/maxim9362/zemiPro_site_django/actions/runs/43431571624)
SUCCESS (433/433 Django, PostgreSQL 17, Ruff, 90 Chrome cases).
Same isolated 300 synthetic published profiles, 10-per-page and three
sequential post-warm-up measurements per scenario:

| Scenario | SQL queries | p50 (ms) | Matches |
|---|---:|---:|---:|
| Unfiltered | 10 | 104.57 | 300 |
| Complex filters | 14 | 92.34 | 126 |
| Keyword + rating sort | 10 | 77.57 | 300 |
| Empty | 8 | 93.09 | 0 |
| Invalid filters | 5 | 22.31 | 0 |

EXPLAIN root: `Sort (cost=626.95..626.96 rows=1 width=4714)`; one
index scan present, not a guarantee of a specific worker index.
These figures are GitHub-runner measurements, not performance SLOs.

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
