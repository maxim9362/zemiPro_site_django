# Stage 03.4 — Worker and company profiles / controlled publication

**Status:** `CODE_IMPLEMENTED / CI_VERIFIED` on `ad41a8f7`; [Django CI #43196142104](https://github.com/maxim9362/zemiPro_site_django/actions/runs/43196142104) **SUCCESS**. **Stage 03 overall is still IN_PROGRESS.** First public pilot: **Ashdod only**. Stage 02 PR #8 remains **Draft / NOT_MERGED**.

## Source of truth and lifecycle

- Reuse the existing Django 5.2 `accounts.User` and OneToOne `WorkerProfile` alongside `ClientProfile`. The selected `active_role` only switches the interface, not privileges. No independent identity, authentication, directory or worker database.
- `accounts.0008_worker_publication` is additive and non-destructive: `provider_type` (individual/company), `display_name`, `spoken_languages` (RU/EN/HE list), `pricing_details`, `availability` (available/limited/unavailable), `working_hours`, `is_published`, `published_at`. Existing user IDs, `Order.client`, `Order.worker`, `Response.worker`, skills and city links remain unchanged.
- All previously stored worker profiles are **drafts by default**, `is_published=False`; no historical content is bulk-published by migration. Drafts can be saved without a full public listing. Publishing requires a separate intentional action by their owner. Unpublishing hides the public listing but **does not erase user accounts, order history, ratings or worker profiles**.

## Write and permission contract

- `GET/POST /accounts/worker/profile/` uses Django authentication, server-bound `request.user`, POST/CSRF, `WorkerProfileForm` allowlisted fields, and the transactional `accounts.services` functions; supplied `user_id`/`profile_id`, `is_published`, `is_verified`, roles and staff flags cannot target another identity or grant privileges.
- Blocked/inactive owners cannot save, publish or unpublish. Service obtains PostgreSQL row locks for the acting `User` and own `WorkerProfile`. Workers may switch to the customer dashboard without losing their professional information.
- Before publish, server checks: nonempty public display name, active and supported primary city, no zones outside Ashdod, at least one active category, 20+ characters of description, price or pricing explanation, nonempty unique language codes from `ru/en/he`, valid type/availability, and remote-service compatibility. A previously published profile that loses mandatory fields through the editing service is automatically unpublished; direct publication without a complete profile is rejected.
- `contact` remains an owner-private profile field and is **never** rendered into public search cards or public worker profile. Same for `User.phone`, `User.email` and login name. Business contact disclosure requires later explicit policy approval. No compulsory licenses or documents, and `is_verified` is neither set nor displayed by this feature.

## Public view and geography

- Category and city discovery, direct `/worker/<id>/` pages and saved-worker links use a shared server-side public-worker queryset. Require explicit publication, active/unblocked account, a supported city and public identity fields. Service zones / remote-service eligibility use existing `workers_serving_city` logic. Only **Ashdod** is allowed by the normal first-pilot setting; other technical City rows remain for referential history and future rollout. Unpublished/blocked/off-pilot direct profile URLs return 404.
- Owner dashboard may show its own draft; publishing is separate from switching cabinet. New responses and matching order-feed access require an available published worker. Existing historical order visibility remains governed by its original owner/assignee permissions.
- RU/EN/HE strings are in the existing `django.po` and compiled `django.mo`; the common Django base template supplies `dir=rtl` for Hebrew. These are automated checks, not human approval of Hebrew wording or original design.

## Verification and release gates

- Synthetic PostgreSQL: `accounts.0008` migration, model consistency and seeded catalog/geography/questionnaires; 9 additional role/profile/privacy tests exercise private drafts, companies, publish/unpublish, missing fields, inactive skills, blocked workers, forged IDs, non-Ashdod area, edit-triggered unpublish, CSRF and guest rejection.
- [CI #43196142104](https://github.com/maxim9362/zemiPro_site_django/actions/runs/43196142104) verified **210/210 Django**, **45/45 emulated Chrome RU/EN/HE responsive/RTL cases**, **12/12 Ashdod-only**, lint and clean migration/seed. **93.4% coverage applies ONLY to `marketplace.services`**, not whole Django codebase.
- No tests on physical iPhone/Android, no migration against real customer data, no production enablement, no native Hebrew signoff, no historical credential rotation or infrastructure acceptance in this substage. See `docs/STAGE_02_RELEASE_GATES.md` for all required pre-public Ashdod obligations and deferred focused review of Stage 02. Independent Codex Cloud review of **all** Stage 03 code happens after 03.7; no PR merge without separate owner consent.
