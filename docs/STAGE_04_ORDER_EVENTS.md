# ZemiPro — Stage 04.7: durable local event outbox

## Domain events and source of truth

`OrderDomainEvent` is append-only with a PostgreSQL trigger and no fields for contact, address, private description, questionnaire answers or photo keys. Every event records an order ID, one of four safe event kinds, an event-time category/city snapshot, a source operation UUID and a deterministic global UUID5 event key. A unique `(order,kind,source_key)` and unique event key make repeated publication, edit and cancellation idempotent.

The emitter runs **inside the database transaction** that creates the draft, publishes a wizard, creates the legacy one-step order, edits terms, duplicates an order or cancels the order. Legacy one-step creation emits both created and published. Draft creation emits only created; cancelling emits cancelled. Edits emit updated only when the terms actually change. The only caller using this event stream for automatic delivery in Stage 04 is the local view/service flow. No external network side effect is triggered by saving an Order.

## Delivery receipts and exactly-once internal side effects

Each event creates two pending `OrderEventDelivery` rows: `notifications` and `analytics`. Unique `(event,consumer)`; per-receipt `SELECT FOR UPDATE`; delivery and `done` flag commit in one transaction. Replaying `done` returns false and adds no notification or analytics fact. On an exception the transaction rolls back; receipt stays pending and a separate safe error code is recorded, without private details or exception strings.

**Notifications:** only in-app DB rows. A draft-created event produces no message. Publication generates a single owner `order_created` notice; edited published terms notify responding workers `order_updated`, and cancellation notifies respondents/assigned worker. Only active, unblocked, email-cleared recipients are eligible. New `notifications_notification.order_event` is nullable for legacy rows and constrained unique with recipient, providing recipient-level deduplication even after an interrupted replay. Updated-notice title/message localize RU/EN/HE at read time.

**Analytics:** exactly one `OrderAnalyticsFact(event,kind,category,city,occurred_at)` per event; data are coarse, intentionally free of user-content/contacts. It is not GA4 or Google Analytics and does not send tracking beacons or emails. In-app and analytics receipts can be replayed independently.

Manual recovery (in an isolated tested environment or explicitly authorized deployment):
`python manage.py replay_order_events --limit 100`
The command processes bounded pending local receipts only; it does not schedule itself and does not make external requests.

## Tests, scope and deployment gates

Required synthetic PostgreSQL tests: atomic rollback of the source order and events, draft-vs-published semantics, unique emission on replay, duplicate HTTP submit, one notification per recipient, worker update/cancel distribution, blocked recipients, safe event schema, localized updated notices, replay of a failed receipt and parallel delivery races. CI verifies actual migrations `marketplace.0014` and `notifications.0002` plus `makemigrations --check` and full Django regressions.

Legacy pre-04.7 orders are left unchanged and are **not** backfilled into a misleading event history. Production email/SMS/push, scheduled background sender, GA4 and payment integrations remain disabled; future Stage 07 controls their activation. Full Stage 04 acceptance still requires independent Codex Cloud code review, security/RTL browser E2E on new wizard/management screens, production private media readiness and owner approval for the single PR/merge.
