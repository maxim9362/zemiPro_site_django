# Stage 03.2 — Account contacts, verification and password recovery

**First public geography:** Ashdod ONLY. **Environment:** existing Django 5.2 / PostgreSQL; no independent authentication service. **Stage:** implementation complete, verification by CI pending at initial commit.

## Contracts and security boundary

- One `accounts.User` keeps the username/password login contract and existing client/worker OneToOne profiles. Registration adds optional email/phone with at least one required and no automatic verification. Contact input never authenticates or grants a profile permission; existing `active_role` remains a UI preference. Legacy users with no contact are preserved.
- The Israeli telephone canonicalizer accepts local 0, international `+972`, `00972` and `972` plus common spaces, punctuation and dashes; stores a normalized +972 E.164 value. Invalid/wrong-country numbers fail at form/service validation.
- `ContactChallenge` stores a per-user/channel HMAC token fingerprint and HMAC destination digest, no raw code. Max 10 minutes, five incorrect attempts, cooldown 60 seconds and consumed on successful confirmation. A separate DB-unique `VerifiedContact.fingerprint` prevents different accounts from claiming the same proven identity, including concurrent claims.
- `ContactDeliveryEvent` records accepted/unavailable/failed outcomes, channel and opaque destination digest, no code or raw contact. The client gets only a generic status; never expose verification codes in HTML, API or logs.
- Recovery uses Django built-in one-time reset tokens and the dedicated `VerifiedPasswordResetForm`. Only matching **currently verified** email fingerprints for active/unblocked users with usable passwords can get a reset link. Generic completion response does not disclose account existence. New sessions for `is_blocked` users are rejected. Django password validation applies to recovery. CSRF is required and logout uses POST.
- Shared PostgreSQL `SensitivePostThrottleMiddleware` already protects registration/login and now protects verification send/confirm and reset POST requests. It fails closed on DB outage or invalid client address and stores only HMAC IP-window hashes. Do not trust arbitrary forwarded IP headers.

## Mock-only delivery and pending integration

- Default settings `ZEMIPRO_CONTACT_DELIVERY_MODE='disabled'` and Django dummy `EMAIL_BACKEND` guarantee no email/SMS is sent by this implementation in a normal running service. **This is not production email/SMS readiness.**
- In isolated `ENVIRONMENT='test'`, explicit `ZEMIPRO_CONTACT_DELIVERY_MODE='test-email'` uses Django locmem; phone SMS calls are patched by test mocks. No real phone, SMTP credentials, external API or billing provider is used.
- Before public launch configure owner-approved, audited delivery transports; verify real email and SMS receipt, bounce/retry, secrets storage, rate limits, privacy and recovery from a real device. If either channel has no approved provider, do not advertise it as operational or claim its verification was tested in production.
- **Secret key rotation caveat:** verified fingerprints and code HMACs currently derive from `SECRET_KEY`. Changing it without coordinated migration deliberately fails closed for old claims/recovery; the release plan must preserve or securely reissue verified claims. Never print a key to create a migration.
- Legacy imported email/phone fields are **not automatically marked verified** by migration `0006`. Reverification is required before password recovery through those addresses. Existing password logins are not affected.
- Any user-initiated contact-edit feature in Stage 03.3 must revoke or recompute the verification flag and verified identity safely; editing contact must never transfer a verified claim to an unverified new value.

## QA and gates

- Test isolated PostgreSQL migrations, contact normalization, token expiry and replay, brute-force limit, CSRF/auth, known/unknown reset responses, email/SMS adapter mocks, delivery record privacy, blocked login and existing 03.1/Stage 02 regressions.
- RU/EN/HE text is present for the new pages in `django.po` and compiled `django.mo`; human Hebrew/content review remains a deferred mandatory release gate.
- No changes to production, VPS, DNS, Cloudflare, real data, PR #8 or public publication. One Stage 03 branch, one final PR after 03.7, independent Codex review at stage close.
