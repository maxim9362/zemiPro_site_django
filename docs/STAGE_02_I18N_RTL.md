# ZemiPro — Stage 02.3: i18n and RTL implementation

**State:** `IMPLEMENTED / CI_PENDING / MOBILE_VISUAL_PENDING`
**Branch:** `stage-02-catalog-localization`, shared Draft PR #8, no merge.

## Runtime design

Django 5.2 `LocaleMiddleware` and `LOCALE_PATHS` use original Russian
`msgid` strings; English and Hebrew editable `.po` and compiled `.mo`
files ship with the repo. All principal Django HTML pages (public catalogs,
city and worker lists, request creation/detail, auth/profile forms, worker
and client dashboards, notification and report pages) have translation tags.

The header uses a **CSRF-protected POST to Django's `set_language`** with
a hidden `next=request.get_full_path`; language cookie selects the user
interface language and keeps the same request URL and query string. This
does not introduce language prefixes or canonical/hreflang changes; these
belong to 02.4 after an SEO migration review. No production URL is changed.

Forms use lazy Django translation and `LocalizedModelChoiceField` so the
same category/city ID appears with appropriate RU/EN/HE labels. A public
bounded subcategory JSON endpoint is localized; its client uses `Option`
instead of injecting API-provided names into `innerHTML`.

System-generated notification events display localized text by type and
related order ID, without changing older persisted notification bodies.
Custom system notifications remain as originally written. Personal
descriptions/order text are **not translated automatically**, per
REQ-I18N-005. The original budget token remains stored as `Договорная`
for backward compatibility, and is translated only in the UI.

## RTL baseline

`<html lang="he" dir="rtl">` is set server-side. CSS includes logical
inline padding/margins, header/navigation adjustments, wrapping at 768px
and 390px, left-to-right phone/email/budget inputs, and automatic direction
for user-generated text. This is a CSS **baseline**, not a claim that
screenshots/physical devices have been visually inspected.

## Verification

GitHub Actions on **isolated PostgreSQL**, never the production database:

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test core.tests.test_i18n
python manage.py test
```

The test also checks localized moderation reason choices without changing stored identifiers. It should cover RU/EN/HE headings/menus, HTML language/direction,
page/query retention and cookie via `set_language`, external redirect
blocking, localized city/category form choices, Hebrew validation errors,
safe JSON, original content preservation, localized notification details,
and static RTL CSS selectors.

**Remaining acceptance gates:** CI + Docker PASS for this HEAD; native
Hebrew proofreading across all critical flows, real 320/360/375/390/768
mobile screenshots (including mixed-script phone/budget/email), a further
audit of hard-coded text in remaining Python error flows and outbound
system notifications. Full visual/mobile verification can be conducted
in 02.6 with owner approval, but not silently labelled PASS.

Do not edit the four approved frontend HTML reference files. No VPS,
Cloudflare, DNS, real user migration, production deploy or PR merge.
