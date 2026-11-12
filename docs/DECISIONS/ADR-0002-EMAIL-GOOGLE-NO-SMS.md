# ADR-0002 — Email/password + Google sign-in, no SMS

**Date:** 2026-11-12. **Decision:** owner requested SMS removal after Stage 03 PR #9 merged. Implement as a single post-merge branch/PR; do not rewrite Stage 03 history.

## Accepted behaviour
- New local registrations require email, username and password; phone is not requested. Existing username/password accounts remain valid and can be recovered via **previously verified email**.
- Existing phone fields remain in PostgreSQL and optional client/worker contact profiles; they are **never** a verified identity or reset channel for new requests. Never delete historical contact data automatically.
- Delete phone OTP/phone recovery routes and forms; explicitly reject phone channel in service layer even if invoked directly. Never send SMS or configure a paid SMS provider.
- Email proof uses the existing six-digit, 10-minute, five-guess mechanism, now email-only; delivery default `disabled`. For real delivery, owner must approve/configure verified sender with generic SMTP transport, secrets outside Git and `ZEMIPRO_CONTACT_DELIVERY_MODE=smtp`. No live email was sent during implementation.
- Google OAuth uses pinned `django-allauth[socialaccount]==65.22.0` on a separate `/oauth/` URL prefix; local login/signup remains Django-native under `/accounts/`. Allauth's own local-account flows disabled by `SOCIALACCOUNT_ONLY=True`.
- `ZEMIPRO_GOOGLE_LOGIN_ENABLED=false` by default. When explicitly enabled, both `ZEMIPRO_GOOGLE_CLIENT_ID` and `ZEMIPRO_GOOGLE_CLIENT_SECRET` are mandatory, loaded from server environment. Google callback: **https://zemipro.co.il/oauth/google/login/callback/** (only if production domain/HTTPS has been approved and DNS is correctly configured).
- Google authorization uses CSRF POST to initiate, state verification handled by allauth, OAuth PKCE, email/profile scopes only, no offline refresh token, no token storage, verified provider email required, and `SOCIALACCOUNT_EMAIL_AUTHENTICATION=False`. No automatic matching/linking of existing local accounts solely on email. Existing users should later get explicit authenticated Google-linking UX, with reauthentication and conflict protections before release.
- Blocked/inactive linked users cannot sign in with Google. Never grant worker or staff privileges through Google data. Unverified/duplicate email social signups are denied instead of shadowing existing identity.

## Deployment and test gates
- Never set Google/SMPP credentials in Git, CI logs or user-visible documentation. Do not enable Google on live site until owner approval.
- Add provider credentials and verify Google OAuth consent screen, authorized redirect, HTTPS, state/PKCE, account creation, repeat login, blocked users, and explicit link conflict under controlled staging.
- Verify real email receipt/retry, provider rate limits, bounce handling and email delivery before public signups; configure off-host secrets and monitor deliverability. Complete email verification gating before public release.
- No production DB migration or live user data cleanup is permitted in this PR. New allauth schema migrations run only in isolated CI; production rollback and backup still require separate owner GO.
- Native HE/RU/EN review and physical smartphone tests remain public-release gates.
