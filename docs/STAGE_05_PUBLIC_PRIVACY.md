# Stage 05 — public content snapshot architecture

Status: `IMPLEMENTED / VERIFIED / INDEPENDENT_REVIEW_PERFORMED / MERGE_PENDING`.

## Security boundary

User-entered profile, portfolio and review text is private source data. Public
HTML, SEO, directory search, invitations, favorites and dashboards must read
only persisted, versioned snapshots. Runtime regex replacement is defence in
depth, not the storage-to-public security boundary.

`apps/accounts/public_snapshot_v1.py` is frozen for migration reproducibility.
It canonicalizes bounded percent/HTML encodings and Unicode, rejects contact
signals, checks composition across profile fields and compares public tokens
with private `contact`, email and phone identifiers. A detected contact hides
the complete affected field. A cross-field/private-identifier correlation
hides all free-text profile projections. Raw values are never deleted.

`public_content_safe` means that a current safe-to-render snapshot exists; it
does not assert that the private raw source was approved. New publication uses
the stricter `publication_issue()` gate. Historical rows may remain listed
with unsafe fields replaced by `[…]`, while their contact fragments are absent
from keyword search.

## Write paths

- Model `save()` and `save(update_fields=...)` rebuild snapshots inside one
  database transaction. Partial saves combine only submitted source fields
  with the locked persisted row; they never trust stale in-memory values for
  the remaining contact/public fields.
- Supported `bulk_create`/`bulk_update` lock `User` then `WorkerProfile`,
  re-read persisted identity/source fields and rebuild snapshots atomically.
- `WorkerProfile.objects.update()` touching source fields invalidates the
  projection and removes the row from public querysets until a normal rebuild.
- Normal User email/phone saves re-read the persisted pair and rebuild the
  related projection atomically. QuerySet update/bulk_update atomically
  invalidate the projection; a later supported profile save may rebuild it.
- Portfolio captions and public review text have independent snapshots.
- Forward migrations `accounts.0021_public_content_snapshots` and
  `marketplace.0016_rating_public_snapshot` backfill snapshots without changing
  raw text, PK/FK, publication status, users or orders.
- State-only migration `accounts.0022_user_safe_runtime_manager` records the
  runtime manager contract without changing a database table or user data.

## Search and matching

Free-form descriptions are not keyword-indexed. Search uses the safe display
name snapshot and administered RU/EN/HE categories/services. Exact service,
category, work mode and service zone are checked both when listing available
orders and transactionally before creating a response.

## Limits

No finite local detector proves that arbitrary natural language cannot convey
a contact. The architecture limits that residual risk by separating raw and
public data, hiding whole suspicious fields, excluding descriptions from
search, and requiring explicit publication validation. Stronger guarantees
would require product-level structured-only text or human moderation. No
external AI/moderation service is introduced by Stage 05.

The conservative detector rejects domain-shaped tokens, URI syntax, encoded
forms and contact-labelled identifiers. Narrow allowlists preserve common
dotted technology names and abbreviations only as prose; URL query, fragment,
path and contact-intent contexts still fail closed. One- or two-character
private identifiers are not treated as meaningful correlation keys. A
three-character key is compared only as an exact public display-name token;
longer identifiers are checked across the whole public projection.

## Verification (2026-11-13)

An implementation agent completed the root-cause remediation and a separate
read-only reviewer then exercised fresh adversarial contact combinations,
write paths and PostgreSQL concurrency. The independent pass found no open
CRITICAL, HIGH or blocking MEDIUM issue. On the resulting tree, the isolated
PostgreSQL 17 checks passed: 21/21 focused snapshot tests, 474/474 full Django
tests, clean migrations, `makemigrations --check`, Django checks, Ruff,
compileall and dependency checks. Chromium emulation passed 180/180 RU/EN/HE
cases at 320/360/375/390/768/1440 px. This is technical evidence, not merge or
production approval; physical-device and release-infrastructure gates remain
open.
