# ZemiPro · Stage 04.3 — Ownership, private details and request replay

## Authoritative server rules

1. `Order.client` is non-null at the database layer. HTTP creation gets the owner only from `request.user`; `client`/`worker` POST IDs cannot be assigned. The service rechecks the account in PostgreSQL for active, unblocked and email-verification-cleared state. Anonymous POST remains denied.
2. `accept_response(response, actor=user)`, `complete_order(order, actor=user)`, `cancel_order(order, actor=user)` require the **explicit authenticated owner** even when called from Python or a future API. Never infer authorization from `order.client` supplied by an untrusted caller. Statuses are still guarded by `order_lifecycle.transition_order_status`, and acceptance remains atomic.
3. Owner and authorized complaint moderator (active staff + `moderation.review_complaints`) alone see exact address, phone, customer name, free-text description and raw questionnaire answers in the order detail. Assignment alone is **not** consent to reveal a contact/address. The customer may voluntarily disclose to the selected worker in a later private chat. A safe order card can still show category, city and quoted budget.
4. Wizard drafts and `wizard_data` remain accessible only to the persisted owner. Other actors see 404 on draft URLs; guessed IDs are never object permissions. Worker dashboard only filters published service orders.
5. Old `GET/POST /orders/create/` stays accessible solely for pre-existing integrations, with phone/address now optional. New product CTAs point to the 04.2 wizard. Legacy POST uses the same central `create_order` service as all direct callers; new UI does **not** expose address/phone fields.

## Replay contract

- Clients should send a stable UUID `submission_key` for the same operation; it is stored in existing unique `Order.wizard_token`. Reuse with identical payload + owner returns existing order without another status event/notification. Reuse with a changed payload or different owner is forbidden.
- Older POST callers without keys are deduplicated only for a **15-minute window** based on a per-owner keyed HMAC fingerprint. It includes canonical submitted fields (service, location, price, description, optional private contact and questionnaire version/answers). The database stores only `submission_digest` and never raw values in audit logs. PostgreSQL advisory locks protect against concurrent identical writes across processes.
- Exact old payloads beyond the 15-minute window may create a fresh order by design; permanent replay protection requires the stable UUID. Future new API clients must supply operation keys. Normal new wizard already has a unique first-step token and a locked publish step.
- PostgreSQL isolation is mandatory; the no-token legacy dedup service fails closed on non-PostgreSQL engines. Production migration needs owner authorization, restore rehearsal and backup.

## Verification and remaining stages

- Stage 04.3 targets tests for HTTP/session CSRF, privileged/unprivileged staff, worker contact privacy, blocked/unverified accounts, forged IDs, service-layer ownership, questionnaire bypass, repeated identical HTTP and direct calls, parallel race and Ashdod-only.
- Stage 04.4 will formalize structured price/date/location and secure photo uploads. Stage 04.5 adds complete edit/history. Stage 04.6 will harden broader throttle/concurrency/abuse limits; 04.7 adds domain delivery events. Independent Codex Cloud review and full staging/real-device security acceptance remain after 04.7.

## Django Admin and legacy browser privacy regression

The Order, Response and OrderQuestionnaireAnswer Django Admin views require a re-fetched active, unblocked and email-cleared staff identity with `moderation.review_complaints`. Generic model-view access alone does not grant raw order details, response messages, exact contacts or private questionnaire answers. The legacy HTML no longer asks for precise address or phone (while historical POST clients remain supported); both browser smoke scripts now assert their absence. Privacy guidance is localized from the existing RU/EN/HE wizard copy.
