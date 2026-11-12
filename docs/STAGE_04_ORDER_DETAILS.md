# ZemiPro 04.4 — Price, date, location and protected order images

## Data changes (additive and lossless)

- `Order.price`: existing string **unchanged** on migrations and old direct POSTs. New wizard continues storing a readable ILS label. `price_kind=legacy` for all existing rows; their textual price is never inferred or rounded, even if it looks numeric.
- New `Order.price_kind`: `legacy|negotiable|fixed|range`; `amount_min_ils` and `amount_max_ils` (decimal 9,2, ILS only). Fixed has one amount, range has both ascending amounts, negotiable has none. `legacy` has no forced interpretation.
- New `Order.preferred_date` (nullable local calendar date), `urgency=legacy|normal|soon|urgent`, `work_mode=legacy|onsite|online`, `approximate_area` (max 80, blank by default). Exact `Order.address` remains existing strictly private data, never shown in the public list or to a selected worker automatically.
- New `OrderAttachment`: order and uploading user, server-generated private `file_key`, SHA-256 of normalized bytes, byte size, `visibility`, consent timestamp for public, creation timestamp. Unique normalized content per order/visibility. Existing order/status rows are untouched. The new migration is `marketplace.0011_order_details_and_attachments`.

## Media ingestion / limits

Reuse `apps.accounts.portfolio.sanitize_portfolio_image()` and `private_portfolio_storage()`. Reject images over **5 MiB**, unsupported extensions or MIME, actual content type mismatches, animated frames, corrupt/truncated formats, decoding bombs and over **12MP**. Generate JPEG renditions max 1600px on each side without original filename, metadata or EXIF. Maximum **5** files per order; duplicates of identical normalized content/visibility are idempotent. Files are stored under `ZEMIPRO_PRIVATE_MEDIA_ROOT/order-attachments/{random_uuid}.jpg`; this must be outside `MEDIA_ROOT` and `STATIC_ROOT`. Never expose the directory via static hosting or Cloudflare/CDN.

The response route `GET /orders/photos/<id>/` checks every read independently (404 on denial or invalid/missing key), sets `Content-Type: image/jpeg`, `Cache-Control: private, no-store`, `X-Content-Type-Options: nosniff`, sandbox CSP and `X-Robots-Tag: noindex`. The private storage key is never given to the browser. Explicit owner-only, POST+CSRF image deletion at `/orders/photos/<id>/delete/` also revokes consent; file cleanup is scheduled on database transaction commit.

## Disclosure

- `private` by default: only owner, plus authorized complaint-moderation staff who satisfy current account checks.
- `assignee`: only owner, authorized moderator and the **selected worker** after publication, only if the owner explicitly chose this visibility when uploading. Selecting a worker on its own never unlocks private photos.
- `public`: opt-in visibility plus a distinct user consent checkbox. The image stays private until the order becomes published; subsequently any viewer with the unguessable/order-linked download URL may access it, so the UI warns against uploading PII visibly embedded in photos.
- In all cases, exact address, phone, raw order description and private questionnaire answers remain hidden from everyone but the owner/authorized moderator until voluntarily shared in future private chat.

## Operational requirements

No antivirus scanner or automated visual PII detector is included. Image decode/re-encode and restrictive MIME/type/size boundaries reduce active-content and metadata risks but cannot guarantee an image depicts no sensitive information. **Do not deploy public uploads** until an operator has set up private persistent storage, filesystem permissions, backups, restore and media retention/abuse response. No deployment/real DB migration, app integration, email/SMS, payment or DNS change is part of 04.4.

## Test gate

Isolated PostgreSQL 17 migration and `makemigrations --check`, new 04.4 unit/integration tests (fixed/range/negotiable, restored legacy, uploaded corrupt/oversize/unsupported/animation, metadata stripping, draft-owner/staff/assignee/public visibility, CSRF and unauthorized deletes, duplicates, media root guard, locale and safe order view), existing Stage 04.1–04.3 regressions, Ashdod-only and headless Chrome mobile/RTL. Independent Codex Cloud review and in-browser end-to-end wizard photo UX acceptance are part of the final Stage 04 review after 04.7.

**Draft photo access:** even an explicitly marked public photo remains inaccessible to anonymous users and selected workers until publication; owner and active, granularly authorized moderation staff can review the draft image. Authorization is checked against current persisted user flags on every request.

**Database price integrity:** migration `0011` also adds `order_structured_price_valid`, enforcing null bounds for legacy/negotiable, a nonnegative single amount for fixed, and nonnegative ascending non-null bounds for range. This prevents API/direct ORM writes from persisting contradictory combinations; no historical text data are converted.

## Stage 04.4 code/CI verification (2026-11-12)

- [GitHub Actions #43287699309](https://github.com/maxim9362/zemiPro_site_django/actions/runs/43287699309): **SUCCESS**, code commit `dad73d19dc9a74dc86c8b8c33296f3178b8e6618`.
- Django **306/306 PASS**, isolated PostgreSQL 17.11 migration `0011`/integrity constraint and `makemigrations --check` PASS, existing Ashdod-only **13/13 PASS** and shared mobile/RTL Chrome **45/45 PASS**. The browser suite is not an end-to-end automated traversal of the new step-6 attachment UI.
- Security-specific regressions cover private JPEG image metadata stripping, invalid file types, oversized uploads, animation, five-file limit and idempotent duplicates, draft/assignee/public visibility, explicit public consent, blocked/other accounts, owner deletion and revocation, private filesystem root and lossless historical orders.
- **Remaining deployment prerequisite:** physically provision persistent private media volume, permissions, backups, cleanup/restore policy and confirm Nginx/Cloudflare do not serve these files directly. No malware engine or detection of phone numbers/addresses visible **inside image pixels** is included. This substage marks code and isolated CI as verified, **not production-ready media activation**.
