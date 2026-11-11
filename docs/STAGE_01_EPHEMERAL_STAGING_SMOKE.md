# Stage 01 — ephemeral staging integration smoke (GitHub Actions)

**Scope:** separate job `Stage 01 isolated staging smoke`, using disposable
GitHub-hosted Ubuntu runner only, no production/DNS/VPS/Cloudflare actions.
**Status on addition:** `IMPLEMENTED / WORKFLOW_NOT_YET_VERIFIED`.
It cannot replace an owner-approved publicly trusted HTTPS staging host.

The workflow sets **synthetic** staging credentials, binds Caddy to
`127.0.0.1:18080` (HTTP) and `127.0.0.1:18443` (HTTPS), and uses
`STAGING_DOMAIN=localhost`. The shell guard aborts outside GitHub Actions
or without this exact loopback setup.

It exercises:
- Docker staging build and service readiness;
- HTTPS with **Caddy's internal localhost certificate only**; `curl --insecure`
  is strictly scoped to this ephemeral localhost and must never be used to
  accept an actual staging/production TLS certificate;
- HTTP redirect, HSTS, Django home, readiness, Caddy-served CSS and 404 media;
- clean migration count before/after PostgreSQL service restart;
- isolated staging custom `pg_dump`, checksum validation, `pg_restore --list`;
- 100 sequential synthetic local `/categories/` responses, p50/p95 measured
  on a hosted runner. **These timing values are not production SLOs**, do not
  represent a realistic 100-worker dataset or physical mobile network, and
  must not be entered as measured real-staging latency.

No schedules, external backups, or external monitoring are activated.
The workflow tears down **only its own disposable Compose project**
without `down -v`. Temporary runner volumes are discarded by GitHub.
Sensitive environment output and container logs are intentionally omitted.

## What it does NOT prove

- Publicly trusted certificate on agreed `staging.*` DNS/host or cloud ingress.
- Privacy or response times under Cloudflare / remote clients.
- Actual off-host encrypted backups with a tested retrieval path.
- Delivered alerts to an owner when readiness fails.
- Github `main` required status checks/branch protection (admin setting).
- Representative load p50/p95/RSS with 100/1000 synthetic workers.
- Browser/device inspection 320px / Hebrew RTL / approved four HTML designs.

Treat `PASS` on this job as *only* isolated smoke verification, not the
Stage 01 `DONE` gate. The approved staging host and name remain to be
chosen and explicitly authorized by the owner.
