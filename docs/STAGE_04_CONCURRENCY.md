# ZemiPro — Stage 04.6: transactional quotas and concurrency

## Verified architecture / REUSE

- Reuse `Order.wizard_token` uniqueness, `OrderStatusEvent.operation_key`, `OrderManagementEvent.operation_key`, `OrderAttachment.content_sha256` and `transaction.atomic` / `select_for_update`. No parallel duplicate API, no background worker or Redis.
- New `OrderWriteQuota(owner, kind, bucket_start, used)` unique constraint. Every charge is part of the same PostgreSQL transaction as the order mutation. A rejected, rolled-back or idempotently replayed write does **not** consume quota.
- Initial server caps: create **25/day**, wizard step saves **120/hour**, edit **60/hour**, new sanitized photos **30/day**, non-noop lifecycle state transitions **60/hour**, worker responses **50/day**. Windows aligned to UTC midnight/hour boundaries, independent of user's device clock or IP. Configured centrally in `apps.marketplace.order_quota.ORDER_WRITE_LIMITS` (not externally adjustable by untrusted request headers).
- A quota hit raises `OrderQuotaExceeded` with bounded `retry_after`; web entrypoints return **429**, `Retry-After`, no-store and RU/EN/HE text. Service calls fail closed. Existing old legacy paths are covered because they use the same central services.
- A limit on successful mutations does not replace network-level firewalls, request-body-size caps, CAPTCHA or a full per-IP rate limiter. The existing authentication middleware still handles sensitive login/signup attempts.

## Race and permission boundaries

- Worker responses lock the fresh current order row and re-check `published` under that lock before insert; acceptance/withdraw/cancel also use it, eliminating the stale-order pending response race. Non-owner, blocked or unverified accounts stay denied.
- All owner photo deletion paths now acquire order row lock *before* attachment row lock, in the same order as upload and publication; invalid paths and guessed IDs fail closed.
- Parallel publication is single-winner: one status transition and no double questionnaire snapshot; repeat status is a no-op. Existing unique indices guard duplicate worker responses / images / order tokens in PostgreSQL.
- This stage does not perform real migrations or configure production volumes. Monitoring, 429 feedback and quota retention/cleanup are future operational concerns; limit values should be revisited only with production usage evidence and owner approval.

## Test plan / pending verification

Synthetic PostgreSQL 17 with parallel thread/connection tests for response-vs-accept, publish-vs-publish and quota serialization; targeted HTTP 429/CSRF/IDOR, image safety and replay, rollback, no-op quota; full Django suite + compile/Ruff/migrations + Ashdod-only and existing mobile/RTL smoke. Stage 04.7 may build a distinct durable notification/analytics outbox on top of these exactly-once mutations.

## Completed CI (2026-11-12)

[GitHub Actions #43296466886](https://github.com/maxim9362/zemiPro_site_django/actions/runs/43296466886): **SUCCESS** on code SHA `38b8c4007498660716e257fe17eb991748027379`. Django **328/328 PASS**, clean PostgreSQL 17.11 migration 0013, model consistency/Ruff/compile, Ashdod **13/13** and standard mobile/RTL Chrome **45/45**. The browser smoke is not a full interactive E2E of the new admin/order forms. Rate thresholds are initial caps, not statistical anti-bot detection.
