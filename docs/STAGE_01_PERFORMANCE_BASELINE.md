# ZemiPro — 01.6: performance, cache, errors, mobile and abuse baseline

**Status: CODE_AND_SYNTHETIC_CI_PASS / REPRESENTATIVE_BENCHMARK_NOT_RUN.** No unexecuted SQL timings,
latencies, worker RSS, device layouts or CI checks are presented as successes.

## SQL query improvements and reproducible checks

- City listing uses `prefetch_related('skills')` for all worker cards,
  avoiding one skills query per worker.
- Category listing joins `city`/`user` with stable rating/PK order.
- Worker profile prefetches skills once across metadata and page content.
- Worker dashboard order listings join city/category and order by stable
  `city_priority, -created_at, -pk`.
- Client dashboard aggregates `Count('responses')` in one queryset for open
  orders rather than an independent SQL COUNT per order. Historical orders
  remain visible: pagination is a separate UX decision (no silent truncation).

On an isolated PostgreSQL with synthetic fixtures only, from `zemipro_web/`:

```bash
python manage.py test apps.marketplace.tests.test_query_scaling
python manage.py test core.tests.test_performance_safety
python manage.py test
```

The new tests compare query counts for **1 vs 9** worker cards/orders.
Expected: no more than **one additional SQL query**. Worker-profile
test cap = 8, worker dashboard cap = 12 in its synthetic fixture.
These are regression expectations, **not measurements**.

For acceptance, record actual SQL counts, p50/p95 HTTP latency, DB time,
HTML response bytes and Gunicorn RSS (before/after 100 repeat requests)
at 10, 100 and 1000 synthetic entities on a separately authorized,
isolated staging host. Provisional *targets*, not achieved SLOs:
list-page p95 under 750ms with 100 workers; under 12 SQL queries per page
with synthetic fixture; no upward RSS trend after 100 requests.
Use local/private performance traces: never upload SQL logs with user data.

## Cache and generic error pages

`DynamicHtmlNoStoreMiddleware` sets `Cache-Control:
private, no-store, max-age=0` for dynamically rendered HTML, including
private pages and error HTML. No public catalog response is stored by a
shared CDN, because the shared header can depend on authentication and
notification counts. Static files are served separately by the webserver.

Minimal standalone `404.html` and `500.html` cannot render user
data or stack traces; their viewport meta tag works without database.
Test both with `DEBUG=False`.

## Sensitive endpoint rate limits

`SensitivePostThrottleMiddleware` checks POST on exact paths:
`/accounts/login/` = **12 / 5 minutes / source IP**;
`/accounts/register/` = **6 / 15 minutes / source IP**.
Exceeding limit returns 429 + `Retry-After`. Cache/backend errors or
invalid source IP return 503 rather than silently opening the route.
IP addresses are hashed with HMAC-SHA256 and a Django secret; they are
never written as plain text to the cache key or framework logs.
`X-Forwarded-For` is not accepted from clients. In staging Caddy
overwrites `X-Real-IP` with `{remote_host}`, and Django trusts it only
when `ZEMIPRO_TRUST_X_REAL_IP=true` on an internal network that cannot be
accessed directly. Reverify if Cloudflare or upstream topology changes.

**Review fix (ZP-01-003):** POST counters are now stored in the
existing isolated PostgreSQL, with one atomic `INSERT ... ON CONFLICT ...
RETURNING` query per attempt. All workers share a counter, so the old
per-process LocMemCache bypass no longer applies. The migration
`accounts.0003_sensitive_post_counter` creates only an opaque HMAC key,
count and expiry; no raw IP, password or customer data are stored.
A dedicated command `prune_sensitive_post_counters` removes counters
expired over 24 hours ago. Enable housekeeping on an authorized host
only; this is not auto-deployed. Fixed-window boundaries, rotating IPs,
shared NATs, and large botnet traffic remain risk scenarios. Distributed
staging concurrency and edge/WAF false-positive checks are still required
before production. No Redis or paid service was added.

## Narrow-screen and accessibility baseline

Existing Django templates already include viewport and 768px CSS rules.
This change adds an incremental max-width:480px fallback for wrapping
header/navigation, 1-column grids, forms, filters and long text.
It does **not** replace the four separately approved frontend designs.
Screenshots and hands-on browser/device QA at 320/360/375/390/768px
remain `NOT_RUN`. Check focus, keyboard navigation, clipped buttons,
RTL in Hebrew, RU/EN/HE errors, and privacy of public pages.
Complete three-language/RTL frontend adaptation belongs to its own
stage and remains a prelaunch acceptance requirement.

## Evidence to capture before acceptance

| Gate | Status |
| --- | --- |
| Code changes to N+1 sites and sorting | PASS (Codex review and tests) |
| 1-vs-9 query count regressions on PostgreSQL | PASS (Codex 75/75 suite) |
| Full Django/CI/migration suite on commit c2e159f | PASS (GitHub Actions run #9) |
| p50/p95, DB time, Gunicorn memory RSS | NOT_RUN |
| Real 320px/mobile and Hebrew RTL inspection | NOT_RUN |
| Django safe 404/500/cache tests | PASS (Codex repeat review) |
| Multi-worker and reverse-proxy throttle behavior | NOT_RUN |
| Atomic PostgreSQL counter model and migration | PASS (Codex repeat review) |
| Distributed multiworker staging acceptance | NOT_RUN |
| VPS/DNS/Cloudflare/production | NOT_TOUCHED |

After 01.6 implementation, all six Stage 01 code substages exist on
`stage-01-development`, but Stage 01 **is not DONE**.
Owner must separately authorize independent Codex review, final stage PR,
and merge/deployment. No automatic production actions.

### Isolated GitHub runner measurement (NOT an SLO)
[Stage 01 smoke run #1](https://github.com/maxim9362/zemiPro_site_django/actions/runs/43028406371)
completed 100 sequential `/categories/` localhost HTTPS requests on an
**empty catalog**: p50 **15.5 ms**, p95 **16.6 ms**. No 100/1000-worker
fixture, remote connection, real mobile browser or RSS trend was measured,
so the representative performance gate remains **NOT_RUN**.
