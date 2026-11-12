# Stage 03.2 — Account contacts, verification and password recovery

**First public geography:** Ashdod ONLY. **Environment:** existing Django 5.2 / PostgreSQL; no independent authentication service. **Stage:** `CODE_IMPLEMENTED / CI_VERIFIED` on SHA `d6982384`; **real SMS/email transport `NOT_CONFIGURED`** until public-release approval.

## Contracts and security boundary

- One `accounts.User` keeps the username/password login contract and existing client/worker OneToOne profiles. Registration adds optional email/phone with at least one required and no automatic verification. Login supports username, **verified matching email or verified +972 phone**, always with the password. An unverified contact cannot be used to select a different user's identity; duplicate unverified input is provisional until a single DB-unique verified contact claim exists. Contact input never grants a profile permission; existing `active_role` remains a UI preference. Legacy users with no contact retain username login.
- The Israeli telephone canonicalizer accepts local 0, international `+972`, `00972` and `972` plus common spaces, punctuation and dashes; stores a normalized +972 E.164 value. Invalid/wrong-country numbers fail at form/service validation.
- `ContactChallenge` stores a per-user/channel HMAC token fingerprint and HMAC destination digest, no raw code. Max 10 minutes, five incorrect attempts, cooldown 60 seconds and consumed on successful confirmation. A separate DB-unique `VerifiedContact.fingerprint` prevents different accounts from claiming the same proven identity, including concurrent claims.
- `ContactDeliveryEvent` records accepted/unavailable/failed outcomes, channel and opaque destination digest, no code or raw contact. The client gets only a generic status; never expose verification codes in HTML, API or logs.
- Auth aliases resolve by HMAC-verification claim, current stored contact and verification timestamp; neither case-insensitive email nor normalized phone is ever used to select an account unless proven. Users may continue to log in by username. Sensitive account names are not exposed back in failed form values.
- Phone-only recovery uses the existing opaque challenge table with a **purpose-separated password-reset HMAC**. An anonymous request requires the existing username and previously verified +972 number but returns the same public confirmation message for unknown/mismatched accounts. After a mocked SMS is delivered to the verified number, the user supplies an OTP plus a new password. The service checks the verified contact claim, 10-minute expiry, five guesses, CSRF and PostgreSQL request throttling, invokes Django password validators, updates the password hash and deletes the one-use challenge. Existing sessions are invalidated. A standard contact-verification code cannot reset a password.
- Recovery uses Django built-in one-time reset tokens and the dedicated `VerifiedPasswordResetForm`. Only matching **currently verified** email fingerprints for active/unblocked users with usable passwords can get a reset link. Generic completion response does not disclose account existence. New sessions for `is_blocked` users are rejected. Django password validation applies to recovery. CSRF is required and logout uses POST.
- Shared PostgreSQL `SensitivePostThrottleMiddleware` already protects registration/login and now protects verification send/confirm and reset POST requests. It fails closed on DB outage or invalid client address and stores only HMAC IP-window hashes. Do not trust arbitrary forwarded IP headers.

## Mock-only delivery and pending integration

- Default settings `ZEMIPRO_CONTACT_DELIVERY_MODE='disabled'` and Django dummy `EMAIL_BACKEND` guarantee no email/SMS is sent by this implementation in a normal running service. **This is not production email/SMS readiness.**
- In isolated `ENVIRONMENT='test'`, explicit `ZEMIPRO_CONTACT_DELIVERY_MODE='test-email'` uses Django locmem; phone OTP and phone-only recovery SMS calls are patched by test mocks. No real phone, SMTP credentials, external API or billing provider is used.
- Before public launch configure owner-approved, audited delivery transports; verify real email and SMS receipt, bounce/retry, secrets storage, rate limits, privacy and recovery from a real device. If either channel has no approved provider, do not advertise it as operational or claim its verification was tested in production.
- **Secret key rotation caveat:** verified fingerprints and code HMACs currently derive from `SECRET_KEY`. Changing it without coordinated migration deliberately fails closed for old claims/recovery; the release plan must preserve or securely reissue verified claims. Never print a key to create a migration.
- Legacy imported email/phone fields are **not automatically marked verified** by migration `0006`. Reverification is required before password recovery through those addresses. Existing password logins are not affected.
- Any user-initiated contact-edit feature in Stage 03.3 must revoke or recompute the verification flag and verified identity safely; editing contact must never transfer a verified claim to an unverified new value.

## QA and gates

- Test isolated PostgreSQL migrations, contact normalization, token expiry and replay, brute-force limit, CSRF/auth, known/unknown reset responses, email/SMS adapter mocks, delivery record privacy, blocked login and existing 03.1/Stage 02 regressions.
- RU/EN/HE text is present for the new pages in `django.po` and compiled `django.mo`; human Hebrew/content review remains a deferred mandatory release gate.
- No changes to production, VPS, DNS, Cloudflare, real data, PR #8 or public publication. One Stage 03 branch, one final PR after 03.7, independent Codex review at stage close.

## Final Stage 03.2 CI evidence

- [Django CI #43186353804](https://github.com/maxim9362/zemiPro_site_django/actions/runs/43186353804): **SUCCESS**, full **188/188** Django tests, 45/45 synthetic Chrome mobile cases in RU/EN/HE, 12/12 Ashdod city boundary tests, fresh isolated PostgreSQL migrations and seed, Ruff/static checks and production-settings sanity PASS. Scope of the 94.7% coverage figure is solely `marketplace.services`.
- Code commits: `d5e1a331` (registration, email/phone proof, generic reset), `53db447d` (verified contact login aliases), `d6982384` (purpose-separated phone-only password recovery); intermediate test/CSS/translation fixes in same Stage 03 branch. This is **test-only proof**, not evidence of actual email or SMS delivery.
- Operational release gate **STILL OPEN**: provider credentials, real delivery and receipt, bounces/retries, safe provider quotas, contact storage/retention and manual Hebrew/content/device acceptance. SMTP is dummy and SMS disabled by default; do not enable any real transport or launch publicly without separate owner permission.

## Independent final review correction

- Login now tries the literal username before resolving a verified email/phone alias. A historical username equal to another account's verified contact therefore remains usable, while the verified owner can still use the same text with its own password. The regression proves both identities select only the account matching the submitted password.
- Independent isolated PostgreSQL 17 result on the reviewed tree: all Stage 03 contact/auth tests and the complete 244-test Django suite PASS. Real SMS/SMTP delivery remains disabled and is not claimed as tested.

## Post-merge revision (2026-11-12, Draft PR #10)

Owner superseded the original dual-email/SMS authentication decision: **email/password plus Google OAuth; no SMS**. See `docs/DECISIONS/ADR-0002-EMAIL-GOOGLE-NO-SMS.md`. The original Stage 03.2 implementation evidence above is historical, not the current intended login policy. New registration now requires email; the phone remains an optional private contact, never a login or recovery channel. The Google and SMTP transports are disabled by default pending owner-controlled credentials and staging verification. This does not reverse Stage 03 PR #9 merge or authorize production migrations.
