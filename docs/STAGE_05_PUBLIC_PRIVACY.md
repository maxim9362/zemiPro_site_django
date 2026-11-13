# Stage 05 — public content snapshot architecture

Status: `IMPLEMENTED / SELF_VERIFIED / INDEPENDENT_REVIEW_REQUIRED`.

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

- Model `save()` and `save(update_fields=...)` rebuild snapshots.
- Supported `bulk_create`/`bulk_update` rebuild snapshots.
- `WorkerProfile.objects.update()` touching source fields invalidates the
  projection and removes the row from public querysets until a normal rebuild.
- User email/phone changes rebuild the related profile projection.
- Portfolio captions and public review text have independent snapshots.
- Forward migrations `accounts.0021_public_content_snapshots` and
  `marketplace.0016_rating_public_snapshot` backfill snapshots without changing
  raw text, PK/FK, publication status, users or orders.

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
