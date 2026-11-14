# ZemiPro — Stage 06: offers, assignment, agreements and execution

Status: **IMPLEMENTED / INDEPENDENT_REVIEW_PENDING / NOT_DEPLOYED**.
Branch: \`stage-06-offers-assignment\` (one final Draft PR). Pilot: **Ashdod only**.
Dependencies: stages 04 and 05, especially safe public profiles and private order projections.

## 06.1 Offer contract

- \`Response\` retains legacy \`pending/cancelled\` values and the original unique
  \`(order, worker)\` constraint; it adds \`sent/viewed/negotiating/accepted/
  rejected/withdrawn/expired\` and a typed fixed/range/method/negotiable price.
- \`ResponseRevision\` snapshots every service-level submitted, edited,
  withdrawn, rejected, viewed, negotiated and accepted response. PostgreSQL
  rejects any historical UPDATE/DELETE (marketplace migration 0018).
- Order row locks serialize all edits. \`revision\` is optimistic CAS for edits.
  \`operation_key\` permits exact duplicate POST replay, but not changes using
  a reused key. A new response is a private owner/worker interaction; no
  public phone/email or full private order text is exposed.

## 06.2 Comparison

- Only a persisted active/unblocked, verified owner receives the list of all
  offers and the real rating average/count. The worker is identified only by
  \`WorkerProfile.public_display_name\` and the already-published profile URL.
- Non-owners do not receive the comparison payload. A worker only sees their
  own proposal. UI includes server-side CSRF, accessible labels, auto/bidi
  direction for mixed Hebrew/Latin amounts, and RU/EN/HE strings.

## 06.3 Assignment

- \`accept_response\` locks \`Order\` before all \`Response\` rows, validates the
  actual persisted owner, matching category/subcategory/city/online coverage,
  published profile, availability, block/verification state and offer status.
- Exactly one response becomes accepted; other active responses become rejected
  with individual revisions. A replay of the winning choice is a no-op.
- Selected order becomes **ASSIGNED**, not IN_PROGRESS. An accepted invitation
  from stage 05 is never an assignment.
- Assignment + offer revisions + initial agreement + status event commit in a
  single transaction. Notifications are emitted only for the first assignment.

## 06.4 Frozen agreements

- The selected worker's offer becomes agreement version 1. The proposing side
  is the worker; the selecting client explicitly accepts the snapshot.
- A subsequent version captures the proposing party, proposed price/range/
  calculation method, terms, timeline, time and source offer revision. It is
  **pending** until the *other* party accepts or rejects with an immutable
  decision. The last accepted version remains effective in the meantime.
- Append-only database triggers protect all agreement/decision history from
  bulk UPDATE/DELETE, beyond Django model.save() restrictions.

## 06.5 Execution and problem states

- Only the assigned and still-enabled specialist can start (ASSIGNED ->
  IN_PROGRESS) and submit a work result. A work result alone does *not* mark
  the order completed.
- Only the customer can explicitly confirm completion (IN_PROGRESS ->
  COMPLETED); historical direct customer confirmation without a worker portal
  click remains supported. No timeouts or inactivity can auto-complete work.
- Either party can report an issue using a PII-free reason code (timing,
  quality, other), which moves the order to DISPUTED; existing owner
  cancellation and rating services are retained. No chat/moderation stage-07
  implementation is included here.
- \`OrderWorkEvent\` tracks STARTED, RESULT_SUBMITTED, RESULT_CONFIRMED, PROBLEM
  with immutable transactionally recorded audit and unique operation keys.

## 06.6 Security and regression evidence

Existing infrastructure reused: persisted-user gates; stage05 safe public
profile/search snapshots; service-level object permissions; CSRF middleware;
PostgreSQL row locks; \`OrderWriteQuota\` windows for responses/edits/status;
order status events; stage04 cancellation/rating rules.

Synthetic tests:

\`\`\`bash
cd zemipro_web
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py migrate --noinput
python manage.py test apps.marketplace.tests.test_stage06_offers \
  apps.marketplace.tests.test_stage06_comparison \
  apps.marketplace.tests.test_stage06_assignment \
  apps.marketplace.tests.test_stage06_agreements \
  apps.marketplace.tests.test_stage06_work \
  apps.marketplace.tests.test_stage06_security
python manage.py test
ruff check .
\`\`\`

CI also runs isolated PostgreSQL 17 and Chromium stage02 and stage06
browser scripts. Tests never touch production or real orders. Browser smoke
is emulation; actual Android manual acceptance remains a separate gate.

## Independent failure-injection findings and remediation (2026-11-13)

**Initial independent verdict:** `STAGE06_CODE_REVIEW_FAIL` on
`b83b341b811f7e13eac4ae0e4da1758779285d0c`; ZP-06-001 and ZP-06-002
are both blocking MEDIUM (no CRITICAL/HIGH). Independently verified main
remains `82aea1b374c15f2715fe4326c7472f1f2a2f993f`.

The remedy deliberately uses **one outer PostgreSQL transaction**, not a
new queue/outbox, for already local in-app notifications:

- `order_respond_view`: create Response + ResponseRevision + customer
  `new_response` notification in one transaction.
- `order_accept_response_view`: select single winner, save agreement and
  order status audit, then create winner **and every loser** notification in
  that same transaction; a failure at any recipient rolls back all writes.
- `order_work_action_view`: work transition, OrderWorkEvent and the other
  party's in-app notification share the same transaction (start, result,
  problem). Existing owner-completion transaction remains unchanged.
- `propose_agreement_change` and `decide_agreement_change`: create a
  localized, PII-free notice for the counterparty **before the transaction
  commits**, once per new immutable version/decision. Replay of the exact
  operation key returns a no-op without a second notification.
- Existing permission and privacy gates for inactive/blocked/unverified users
  continue to suppress delivery to ineligible accounts; no raw price,
  free-text terms or private contacts are copied into notices.
- No network send is performed; these are database-backed internal
  notifications. Future external push/email requires a separate outbox.

**Code-SHA remediation evidence:** `fa40cb2c2ce58d97e0bcdaee0a118c07854446c6` —
GitHub push #43514415266, PR #43514422280, staging #43514422281 all
SUCCESS; 510/510 Django, PostgreSQL 17 migrations, Ruff and 90+18 Chrome
RU/EN/HE/RTL PASS. This is **not** independent re-review or authorization
to merge/deploy. Final PR HEAD must pass all required GitHub Actions.

**New synthetic regression:** `apps.marketplace.tests.test_stage06_notification_atomicity`.
It injects notification failures at first and second recipients and verifies
full rollback, replay and absence of partially committed histories, quotas
and notifications. It covers all six user-facing action types plus both
agreement change transitions. The independent baseline FAIL remains in force
until a new independent review on the final exact HEAD.

## Second independent audit and remediation (2026-11-14)

A new independent Codex run on `cabab49f` found two blocking MEDIUMs:

- `ZP-06-004`: review POST committed Rating before a separate internal
  notification; an injected notification failure left a persisted review
  without the worker's notice. The PR now locks the Order row in the review
  transaction, serializes duplicate POSTs and writes both records together.
- `ZP-06-005`: selected-worker flash and owner page leaked a private User
  name via `User.__str__`. Both now use the canonical persisted safe
  `WorkerProfile.public_display_name` or a neutral fallback; the worker
  account's private username is never a display fallback.

Codex tested a separate local patch (529/529), but it was not published or
accessible for literal import from the ChatGPT GitHub session. Equivalent
changes and fresh synthetic rollback/race/privacy tests were implemented in
the **same stage-06 Draft PR**, with independent exact-HEAD CI required.

The Stage 06 development plan additionally requires comparison filters/sorts
and moderator routing when a problem is reported. Owner-only server-validated
status filters and newest/oldest/price/rating sorts, RU/EN/HE controls, and
atomic creation of a pending PII-free `moderation.Complaint` now implement
those bounded requirements. No Stage 07 chat or external notifications were
introduced.

**Explicit remaining acceptance questions:** the expiration policy/trigger
for offers is not defined; `expired` is a supported persisted state, but
there is no invented timeout; and full dynamic i18n of every notification
type (including legacy stages) requires a separate evidence-based review.
Physical Android/iPhone checks and an independent review of the new final
SHA remain mandatory before any merge.

## GitHub CI evidence after second review changes

SHA `c36a8652d3b722629693d24c6e782e618c67ea5f`:
[push #43577764683](https://github.com/maxim9362/zemiPro_site_django/actions/runs/43577764683),
[PR Django #43577770047](https://github.com/maxim9362/zemiPro_site_django/actions/runs/43577770047),
[staging #43577769980](https://github.com/maxim9362/zemiPro_site_django/actions/runs/43577769980)
all **SUCCESS**. PostgreSQL 17, full Django **521/521 PASS**, Ruff, model
migration checks, 90 old + 18 Stage06 Chrome mobile/RTL cases PASS.

This is implementation CI evidence, **not** an independent code review of the
new tree or owner permission to merge. Re-review must inspect all second
audit fixes and additions (review atomicity, snapshot privacy, owner sorts,
moderation queue), and verify final PR SHA after this documentation update.

## Independent Codex Cloud review assignment (read-only)

Review the **final SHA** of the single stage-06 Draft PR against the
latest \`main\`. Ignore earlier self-review status. Do not push, merge or deploy.

1. Review lock order and concurrent transactions: competing response
   acceptance, duplicate offer creation, editing while selecting, concurrent
   agreement proposals, simultaneous worker start/owner cancel, and rollback.
2. Try direct service and HTTP bypass of ownership, worker block/unpublish,
   outdated profile/category/city, stale \`Response\` and \`Order\` instances,
   statuses, fake owner confirmation, revoked/rejected offer.
3. Try all privacy oracles: forged query/path, private customer phone/address,
   unverified/blocked owner session, free-text offer terms, personal contact
   masquerading as public worker display name, browser HTML leakage to other
   specialists, no preselection access to private description/photos.
4. Verify immutable source snapshots after concurrent/ORM bulk updates,
   agreement confirmation by the *other* party, operation key reuse and
   uniqueness, migrating historical orders/responses without fake history.
5. Verify quotas, no duplicate notifications, CSRF, RU/EN/HE/RTL, mobile
   overflow, review eligibility after confirmation, and stage04–05 regressions.
6. Run PostgreSQL 17 targeted/full suite, Ruff, Django/migration checks, and
   isolated browser smoke. Report concrete severity, file/line and minimal
   reproduction for any CRITICAL/HIGH/MEDIUM. Do not declare PASS without
   independent evidence. Make no merges or production changes.

Acceptance requires all necessary CI workflows SUCCESS on **the exact final
HEAD**, independently reviewed findings remediated in the same PR, plus the
owner's separate authorization before merge. Deployment is explicitly excluded.
