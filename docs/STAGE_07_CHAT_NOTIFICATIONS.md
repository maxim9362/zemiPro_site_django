# ZemiPro — Stage 07: private communications and trust (2026-11-14)

Status: **IMPLEMENTED / LOCALLY_VERIFIED / FINAL_CI_PENDING / NOT_MERGED / NOT_DEPLOYED**.
Scope: Ashdod pilot, RU/EN/HE and Hebrew RTL. Stage 08 visual redesign and
all production operations are excluded.

## Reused architecture

- Order and Response (Stage 04/06), OrderInvitation (Stage 05), staged
  assignment/agreement/completion (Stage 06).
- Rating, safe public review snapshots and server-calculated aggregates.
- apps/notifications in-app Notification and existing order-event deduplication.
- apps/moderation Complaint, audited staff permissions, ModerationEvent and the
  existing Stage 06 work-dispute queue.
- Existing private sanitized JPEG storage and verified-account protections.

No WebSockets, Redis, paid queue or Telegram. Django templates + bounded HTTP
polling are sufficient for the pilot.

## 07.1–07.2: Chat

- One Conversation per Response with **server-derived** customer and specialist.
  No arbitrary recipient IDs; POST-only creation; read and write independently
  check persisted identity, verified email, active/block state, and participants.
- Original Message is PostgreSQL-protected, with monotonic primary key ordering,
  nonce idempotency (conversation/sender/UUID), recipient read timestamps, and
  15 writes/minute per participant/thread. Polling is bounded at 24/minute,
  with a 6-second browser interval and reconnect/reload from the database.
  Older pages are linked explicitly; a CSRF-protected read form also works
  without JavaScript. Polling refreshes receipts and recent private attachments.
- New MessageAttachment JPEG bytes are stored transactionally in PostgreSQL;
  legacy private filesystem images remain readable via the same server-gated
  no-store/noindex route. Outer transaction rollback leaves no orphan file.
  Migration reversal refuses to drop a populated private-image column; export
  and verify those originals and prepare a preserving reverse migration before
  a planned schema downgrade; an automatic lossy downgrade is forbidden. Original filename and EXIF are never exposed.
  Writer may add at most three unique images per message.
- Chat user content is rendered as escaped text, not HTML. Persistent messages
  remain available when AI/external integrations fail.

## 07.3: In-app notifications and optional email

- Domain notification key is unique per recipient. Newly generated messages
  and notices are localized RU/EN/HE to the recipient's preference. Events
  contain no message bodies, private addresses, or contact details.
- Optional in-app notifications may be muted. Mandatory complaint/security
  notices cannot be muted. Notification reads/settings require persisted
  active and verified accounts.
- Email is a separate durable outbox with bounded retries, error codes and a
  dead-letter state. It is inert by default. External email additionally
  requires explicit SMTP configuration and operational enablement; this PR
  neither sends real email nor starts a background worker.
- SMTP delivery is **at-least-once** under process crash; external providers
  cannot guarantee exactly once without their own idempotency support.

## 07.4: Verified reviews

- Customer may create one 1–5 Rating on a completed Order and its selected
  worker; PostgreSQL protects score, ownership, original review and safe
  public snapshot against untracked mutations. Legacy Stage 05 snapshot
  test is retained with the stronger expectation that tampering is rejected.
- Selected specialist may post one PII-safe public RatingReply; append-only
  RatingAuditEvent records new review creation and worker response.
- All visible review text uses saved, fail-closed public projections. Aggregate
  rating comes from actual persisted Ratings, not synthetic stars or votes.

## 07.5: Reports and moderation

- Existing Complaint supports reports on account, eligible order, public
  review and participant-only private message. Unauthorized direct IDs are
  rejected without leaking content.
- Complaint/appeal creation is throttled, reporters use session identity,
  staff queues and decisions require persisted staff permission
  moderation.review_complaints, and decisions are audited.
- One ComplaintAppeal per decided complaint; original reason is immutable.
  Appeals are resolved by authorized moderators and create a notification.
- Existing Stage 06 work-dispute auto-complaints remain in the queue.
  No unapproved automatic bans or moderator bypasses.

## 07.6: Optional machine translation

- MessageTranslation stores a separately authorized target-language result;
  original Message is not replaced. RU/EN/HE results are explicitly labelled
  machine-generated; a "Show original" control is always available.
- A message's text is not submitted to Gemini without explicit user consent.
  Conservative PII filtering blocks contact-shaped, address-related and
  digit-bearing content; attachments, user IDs, order IDs and prior history
  are never submitted. User rate quota is 10/day.
- Gemini adapter uses fixed HTTPS host, bounded timeout, no redirects, a
  server-side API-key header, and safe errors. Provider failure never blocks
  reading/sending original chat messages.
- Default configuration:
  ZEMIPRO_GEMINI_TRANSLATION_ENABLED=false,
  ZEMIPRO_GEMINI_TRANSLATION_API_KEY unset.
  Real provider activation requires separate privacy and operational approval.
  Provider results have only been tested with a synthetic mock, not live Gemini.

## 07.7: Synthetic acceptance and remaining gates

Integrated tests: Stage04 create_order -> Stage06 offer -> Stage07 chat ->
assignment -> bilateral terms -> work completion -> verified review/reply;
Stage05 invitation -> acceptance -> chat -> assignment -> dispute ->
Stage06 complaint queue -> Stage07 moderator decision and appeal.
Negative: IDOR, CSRF, blocked/unverified users, replay, database integrity,
rate limits, provider failures and language/RTL. Synthetic Chromium mobile
smoke on widths 320/390/768 and RU/EN/HE is wired into GitHub Actions,
alongside clean migration, upgrading legacy synthetic rows and rollback.

**Never mark PASS on intent alone.** Final gates:
1. Full Django suite + Stage07 targeted + Stage04–06 regressions SUCCESS.
2. PostgreSQL 17 migrations and upgrade/rollback rehearsal SUCCESS.
3. Ruff, compileall, pip check, Django check, Compose validation SUCCESS.
4. Chromium screenshots/RTL/IDOR and both journeys SUCCESS.
5. Final GitHub CI successful on the exact final SHA.
6. A separate independent review/required approvals and clean normal merge.

Production gates remain separate: credentials rotation, real backup/restore,
private-media persistence and access policy, SMTP/Gemini privacy review,
monitoring, real device checks, and controlled release authorization.
No deployment is part of Stage07 merge.

## Independent reviewer assignment

Review the final PR #16 diff adversarially, independently of its author.
Use only isolated synthetic PostgreSQL 17. Prioritize cross-tenant IDOR,
participant block/unverify races, attachment content and storage, message
nonce/concurrency, SMTP outbox retry/duplicate semantics, complaint and
staff-role escalation, original review and translation immutability, PII
egress to Gemini, CSRF, RU/EN/HE/RTL, and Stage 04–06 regressions.
Record reproducible CRITICAL/HIGH/MEDIUM with file/line and SHA. Audit
approval is not a substitute for GitHub Actions or deployment gates.

## Codex adversarial audit and remediation — 2026-11-14

Audited base: `53e5352afa2495d5ad50592b469835691e50c588`.
Base main: `576ef639e1b5944e333ac2829d47e16f51aa82a0`.
The original implementation was reviewed independently of its author; remediation
and its regression verification were performed by the same Codex agent, not by a
second independent reviewer. No merge or deployment is authorized in this task.

| ID | Severity | Reproduction / root cause | Remediation and regression evidence |
|---|---|---|---|
| ZP-07-001 | MEDIUM | ORM could rebind a Conversation and insert an outsider Message sender | `marketplace.0023`: immutable binding/participants and sender/body guard; `test_stage07_independent` |
| ZP-07-002 | MEDIUM | ORM could erase an existing read timestamp | PostgreSQL monotonic read evidence; independent regression |
| ZP-07-003 | MEDIUM | Enclosing transaction failure left a private JPEG file | Transactional JPEG bytes, legacy read compatibility, safe downgrade guard; independent rollback test |
| ZP-07-004 | MEDIUM | Outbox sent after email verification was revoked | Persisted verification-required gate; injected sender must not be called |
| ZP-07-005 | MEDIUM | Unverified staff could directly call moderator service | Shared persisted moderator gate; service-level regression |
| ZP-07-006 | MEDIUM | ORM could delete appeal or rewrite final decision | `moderation.0006` immutable evidence; delete/update regressions |
| ZP-07-007 | MEDIUM | Only latest 40 messages visible; read receipts and later images did not refresh | Older-page navigation, no-JS read form, polling read/image updates and retry; HTTP + Chromium |
| ZP-07-008 | MEDIUM | Revocation during provider call was not rechecked before returning translation | Reauthorize before storing/returning result; synthetic provider revokes actor |
| ZP-07-009 | MEDIUM | Appeal creation omitted documented quota | Shared transactional quota, replay without another debit; limit and failure-injection tests |
| ZP-07-010 | LOW | Notification pages lacked explicit private cache prohibition | `never_cache` on notification endpoints |
| ZP-07-011 | MEDIUM | Browser awaited network idle while chat polled continuously | DOM readiness + retained functional assertions; reproduced timeout, then 39 browser cases PASS |
| ZP-07-012 | LOW | Persisted unread eligibility added a redundant query: dashboard 15 > 14 | Join eligibility into count; original query threshold unchanged |
| ZP-07-013 | LOW | New chat navigation, notification settings and moderation strings fell back to Russian in EN/HE | Completed PO/MO catalogs, translated status labels, HTTP regression and browser settings/queue checks |

The first five independent baseline cases failed 5/5; three additional appeal/
moderator cases failed 3/3 before remediation. Historical failures are retained
in the external evidence directory, not rewritten as passes. The baseline
GitHub Actions were failing; remote job logs required authentication, so the
exact remote failing step is not claimed from inaccessible logs.

Additional checks include simultaneous message replay/two participants, parallel
outbox workers, message/reply/appeal notification failure with rollback and retry,
source identity updates, and rejection of a lossy schema rollback. New migrations
are forward additions; migrations of stages 01–06 were not rewritten.

New JPEG bytes belong in database backup/restore and capacity planning. External
SMTP remains at-least-once across a crash after acceptance but before database
commit; concurrent workers are serialized, which does not imply exactly-once
external delivery. No real SMTP or Gemini calls were made. Existing Stage04–06
notification contracts remain supported; Stage07 optional preferences govern
Stage07 domain notifications, not historical stored notices.

Local evidence: isolated PostgreSQL 17.12, Python 3.12.14, Django 5.2.19, Ruff
0.17.4, Chromium 155; clean migration and synthetic Stage06 upgrade/rollback PASS;
RU/EN/HE/RTL browser cases: Stage02 90, Stage06 18, Stage07 30 including no-JS.
Local full Django suite: **580/580 PASS, 0 failures/skips**; Stage07 targeted
suite: **56/56 PASS**. Final remote Actions results are recorded against the
final branch SHA in the audit handoff. Never infer final CI success from an earlier SHA.
