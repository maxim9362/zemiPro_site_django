# Stage 04.2 — Order creation wizard (implementation contract)

## Routes and compatibility

- `GET/POST /orders/new/`: registered customer starts a new order draft after selecting a valid active category and concrete subcategory. Per-session UUID is used for the first insert; the database enforces unique `wizard_token` on the Order row. Replayed first-step POST is rejected.
- `GET/POST /orders/<id>/wizard/?step=1..8`: authenticated owner resumes a draft or updates one previously completed step. A newer step is inaccessible until all earlier steps have been stored. Original precise addresses and personal phones are never collected here.
- `GET /orders/<id>/` for a draft: only the owner may follow a redirect to the wizard; everyone else gets 404. No public/worker feeds of drafts.
- Existing `GET/POST /orders/create/` remains functional temporarily to avoid breaking Stage 02/03 legacy consumers. All product CTA links now use `/orders/new/`. The service boundaries/legacy endpoint will be converged in Stage 04.3.

## Steps and persisted data

1. Active category/subcategory; create `Order(status='draft', client=owner)` with empty legacy required text fields (not visible publicly).
2. Published service questionnaire version plus whitelisted conditional answers, using the already existing Stage 02.5 dynamic form helpers.
3. Active Ashdod city, online/on-site delivery mode compatible with the selected service and approximate area (not an exact address).
4. Optional future date and urgency.
5. Negotiable, fixed or range ILS amount (provisionally text at publish and private wizard data).
6. Optional description; at least description or questionnaire answers is required to publish. Photos remain a **04.4 secure attachment** task and are not accepted by this form.
7. Preferred display name and explicit private-chat-only contact setting. No phone number or address input or implicit disclosure to other workers.
8. Preview, explicit confirmation, atomic draft-to-published transition and immutable event; exactly one questionnaire snapshot for the selected published version.

Persisted payload is private `Order.wizard_data = {'steps': {'1': {...}, ... '7': {...}}}`; never put it in unauthenticated JSON, public pages or logs. `wizard_token` is UUID and nullable for old orders. A changed service clears later steps to avoid mixing answers. This data is **transitional**; Stage 04.4 will normalize price, date, area and attachments without erasing the original answers. The stage 04.1 append-only `OrderStatusEvent` records creation and publication. More detailed order change history is Stage 04.5; event delivery is Stage 04.7.

## Authorization and transaction boundaries

- Persisted account checks: authenticated, active, unblocked and no outstanding email verification requirement; user identity must match `Order.client_id` on every direct service call.
- Read-only draft lists are owner-only; guessable order IDs never authorize a read or write.
- Every step is a server-side Django Form; no reliance on JS validation. The final publication rechecks all completed steps, questionnaire version, active service, dates and the live Ashdod-only city restriction.
- PostgreSQL `select_for_update` protects draft writes and publication, a unique token prevents double initial insertion, and `transition_order_status` guarantees one published transition event. No external email/SMS/payment integration. The only notification at publication is the existing in-app notification helper.

## Checks and unfulfilled parts

- Run targeted `test_stage04_wizard` and then full GitHub Django CI (clean PostgreSQL migrations, model consistency, Ruff/compile, RU/EN/HE Chromium mobile, Ashdod pilot tests).
- Stage 04.4 still owns image uploads, secure file validation/storage, formal price and appointment/location fields. Stage 04.3 owns the final convergence of legacy and wizard routes and creating-owner idempotency for all entrypoints. No existing historical rows, user records or live data may be modified by these additions.
