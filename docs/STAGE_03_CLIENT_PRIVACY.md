# Stage 03.3 — Client profile, private settings, favorites and privacy requests

**Pilot:** Ashdod ONLY. Existing Django 5.2 and PostgreSQL; no independent service.
**Implementation state:** code prepared; CI evidence to be recorded separately.

## Contracts

1. The account remains one `accounts.User`. An authenticated owner can edit their own first/last name, email/phone, preferred interface language RU/EN/HE and `ClientProfile` city, optional contact and optional-update preference. Existing `role`, `active_role`, worker profiles, orders and passwords are not modified by this form. The save service does not accept a target user ID; the form contains no privileges.
2. The server validates city via `city_is_public` (Ashdod). Email is normalized to lowercase and Israeli phone to canonical `+972` using Stage 03.2 validation. On *actual* contact change, revoke the old channel's verified claims and code challenge and clear its timestamp in the same transaction under a User row lock. Verified claims for unchanged contacts remain intact. New contact must be independently confirmed before being usable as a login alias or password-recovery destination. Do not remove the final recovery contact from a registered account.
3. Language selection is validated against RU/EN/HE, saved to the user and applied as a language cookie on the redirect; it does not alter public i18n URLs or the working RTL implementation. The optional-notifications flag concerns future nonessential external sends; in-app transactional/order notifications are preserved. No unconfigured SMS/email is switched on.
4. `FavoriteWorker` stores user-private bookmarks for active visible workers only, using server-side pilot filtering. Add/remove is authenticated POST/CSRF, unique by client and worker. A user cannot favorite their own account. No favorites are visible in public SEO or other people's dashboards. Bookmarks are not reviews or endorsements.
5. `PrivacyRequest` lets an authenticated owner *request* `export` or `delete`; repeated pending requests are idempotent and DB-unique. Owner can view only own request statuses, without exposed administrative metadata, related accounts or private files. Actual export, erasure/anonymization, verification of requester identity, preservation of contractual records, retention/legal exceptions, secure delivery and SLA require an independently approved workflow; **no automatic personal-data transfer or cascade delete**. An admin may review statuses; no bot or external notification is sent by request creation.

## Tests and gate

- New migration `0007_client_privacy` adds nullable-free user/client preference defaults, a private pending request workflow and unique favorites. Existing 03.1/03.2 tables and seeds are untouched.
- Negative tests exercise no-login, bad CSRF, forged owner ID, block status, non-Ashdod city, invalid locale, changed contact revocation, unrelated worker and order preservation, request idempotence, invisible foreign records, favorite isolation and prohibited nonpilot workers.
- User-selected RU/EN/HE strings are included in compiled catalogs; human Hebrew signoff and real Android/iPhone remain mandatory pre-public release gates. Real fulfillment of access/erasure requests also requires an approved legal/privacy process.
- This technical substage must be separately CI-verified before marking Stage 03.3 complete. No current authorization to merge PR #8, create Stage 03 final PR early, change live systems or start public launch.
