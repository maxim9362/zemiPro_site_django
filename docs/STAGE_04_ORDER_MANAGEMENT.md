# ZemiPro 04.5 — управление заказом и события изменений

## Owner-only lifecycle and URLs

- `GET/POST /orders/<id>/edit/`: change normalized budget (ILS), future date, urgency, online/on-site compatible with service, approximate area and description while a request is `published`/`in_discussion` and no worker has been assigned. Authenticated persisted owner checked in service and HTTP. Category/service change after publication is **not** part of this inline form; withdraw without responses and use the wizard if the service must change. No exact address or phone accepted in this form.
- `POST /orders/<id>/withdraw/`: `published|in_discussion → draft` only if no worker **and no existing responses**. This is checked again inside `transition_order_status` row lock. On legacy orders, a new wizard token and prefill are created; historical strings are preserved. Any order with responses should be cancelled rather than withdrawn, because responses must not disappear silently.
- `POST /orders/<id>/duplicate/`: create one new private draft per UUID operation key, with selected compatible service (if still active), proposed budget/time/area/description **as prefill only**, and no worker, phone, exact address or photos. Replays return the existing draft. Changing to a different service invalidates old prefill.
- Existing `POST /orders/<id>/cancel/` can cancel owner drafts/available/assigned/in-progress/disputed statuses permitted by the lifecycle. Completed/cancelled/expired remain terminal and cannot be edited. `POST /orders/<id>/complete/` still requires in-progress and owner. `OrderStatusEvent` records each actual state transition once.
- `GET /client/dashboard/` displays drafts and separate owner-only bounded/paginated active, in-progress, completed and cancelled/expired groups. No public URLs to draft data or direct private contact content. The owner detail page displays a chronological status/edit/copy history. Staff/worker/stranger get no owner audit timeline.

## Append-only data

`marketplace.0012_order_management_events` is additive. `OrderManagementEvent` has `order`, `actor`, `action=edited|duplicated`, `changed_fields` (whitelisted field names, **never values or free text**), optional target order for a duplicate, unique `(order,operation_key)` and timestamp; PostgreSQL trigger rejects UPDATE/DELETE. It provides a repeat-safe audit and can later drive Stage 04.7 domain delivery. A distinct, private `OrderQuestionnaireAnswerArchive` records exact historical version, schema and answer JSON when an owner re-publishes with changed questionnaire answers; DB trigger also enforces append-only. No current snapshots or legacy rows are wiped by the migration.

## Concurrency and privacy

Services lock the affected `Order` row via `SELECT ... FOR UPDATE`, re-check persisted owner state and read the current status. Duplicate and edit use operation keys. A duplicate never copies private files or exposure consent; a withdrawn order is not a public record. Conditions are safe/structured and bounded; no raw customer input is kept in audit events. If a response already exists, withdraw is rejected; this is a deliberate business rule until 04.6 concurrency hardening.

## Verification and future gate

Isolated PostgreSQL migrations/immutable-trigger tests, end-to-end HTTP owner rights and blocked/foreign paths, rollback, drafts pagination, edit/noop/duplicate idempotency, rerun questionnaire snapshots, old legacy price/address preservation, full Django suite, RU/EN/HE and Ashdod-only browser checks. Stage 04.6 still owns stricter concurrency/rate limits; 04.7 owns event delivery to notifications/analytics. Independent Codex Cloud and physical mobile review are separate gates after all 04.x.

## Verified acceptance — 2026-11-12

- Verified code SHA: `f325df96d707cd0cb6d3092f5289caabfd08fd13`. [Isolated CI #43293526168](https://github.com/maxim9362/zemiPro_site_django/actions/runs/43293526168) **SUCCESS**; Django **318/318 PASS**, clean PostgreSQL 17.11 migration `0012`, `makemigrations --check`, Ruff, system checks, RU/EN/HE headless Chrome common smoke **45/45**, Ashdod-only **13/13**.
- New PostgreSQL triggers protect both owner management events and private archived questionnaire snapshots against UPDATE/DELETE. History and source order survive duplicate/edit/withdraw/re-publish workflows; no raw PII stored in management-event logs.
- Separate interactive browser E2E for new management forms, real-mobile acceptance, independent Codex Cloud and the one final Stage 04 PR remain pending. Deployment and live migrations are explicitly outside the scope.
