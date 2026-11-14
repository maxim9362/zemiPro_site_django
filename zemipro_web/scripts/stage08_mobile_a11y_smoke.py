"""Stage 08.6: real Chrome viewport/keyboard smoke; isolated synthetic DB only.

This is not physical-device, screen-reader or independent visual acceptance.
Never connects to production, external APIs or real accounts.
"""
import os
import sys
from pathlib import Path
from uuid import uuid4

import django
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
BASE = "http://127.0.0.1:8768"
OUT = Path("artifacts/stage08-mobile-a11y")
WIDTHS = (320, 390, 768, 1440)
LANGS = ("ru", "en", "he")


def fixtures():
    django.setup()
    from django.conf import settings
    from django.contrib.auth import get_user_model
    from django.contrib.auth.models import Permission
    from django.contrib.contenttypes.models import ContentType
    from django.contrib.sessions.backends.db import SessionStore
    from django.db.models import Q
    from apps.accounts.models import ClientProfile, WorkerProfile
    from apps.locations.services import get_public_cities
    from apps.marketplace.chat_services import open_conversation, send_message
    from apps.marketplace.models import Category, Order, Response
    from apps.moderation.models import ModerationEvent

    if settings.ENVIRONMENT != "test":
        raise RuntimeError("Stage08.6 smoke requires disposable test environment")
    if os.environ.get("ZEMIPRO_TEST_ASHDOD_ONLY") != "1":
        raise RuntimeError("Stage08.6 smoke requires the Ashdod-only test gate")
    city = get_public_cities().first()
    category = Category.objects.filter(
        is_active=True, work_mode__in=("onsite", "both"),
    ).filter(Q(section__isnull=True) | Q(section__is_active=True)).first()
    if city is None or city.slug != "ashdod" or category is None:
        raise AssertionError("Stage08.6 requires synthetic Ashdod and catalog seed")
    User = get_user_model()
    users = {}
    sessions = {}
    for role in ("client", "worker", "moderator"):
        user, _ = User.objects.get_or_create(
            username="stage08_6_browser_" + role,
            defaults={"email": f"stage08_6_{role}@example.invalid"},
        )
        user.is_staff = role == "moderator"
        user.is_active = True
        user.is_blocked = False
        user.email_verification_required = False
        user.set_unusable_password()
        user.save(update_fields=[
            "is_staff", "is_active", "is_blocked",
            "email_verification_required", "password",
        ])
        if role == "moderator":
            perm = Permission.objects.get(
                content_type=ContentType.objects.get_for_model(ModerationEvent),
                codename="review_complaints",
            )
            user.user_permissions.add(perm)
        store = SessionStore()
        store["_auth_user_id"] = str(user.pk)
        store["_auth_user_backend"] = "django.contrib.auth.backends.ModelBackend"
        store["_auth_user_hash"] = user.get_session_auth_hash()
        store.save()
        sessions[role] = store.session_key
        users[role] = user

    ClientProfile.objects.update_or_create(
        user=users["client"],
        defaults={"city": city, "contact": "PRIVATE_STAGE086_CLIENT_CONTACT"},
    )
    profile, _ = WorkerProfile.objects.update_or_create(
        user=users["worker"],
        defaults={
            "city": city,
            "display_name": "QA Ashdod Specialist",
            "description": "Verified synthetic fixture for public layout testing.",
            "pricing_details": "Synthetic estimate after discussion",
            "contact": "PRIVATE_STAGE086_WORKER_CONTACT",
            "spoken_languages": ["ru", "en", "he"],
            "is_published": True,
            "availability": WorkerProfile.Availability.AVAILABLE,
        },
    )
    profile.skills.add(category)
    order = Order.objects.create(
        client=users["client"], category=category, city=city,
        status=Order.Status.PUBLISHED, price="Договорная",
        address="PRIVATE_STAGE086_CLIENT_ADDRESS",
        description="Synthetic 08.6 test request, no real customer data.",
    )
    offer = Response.objects.create(
        order=order, worker=users["worker"], status=Response.Status.SENT,
    )
    convo, _ = open_conversation(response_id=offer.pk, actor=users["client"])
    send_message(
        conversation_id=convo.pk, actor=users["worker"],
        body="Test message with mixed Hebrew עברית and English 12345",
        client_nonce=uuid4(),
    )
    return sessions, {"order": order.pk, "worker": profile.pk, "chat": convo.pk}


def metrics(page):
    return page.evaluate("""() => ({
        screen: window.innerWidth,
        doc: document.documentElement.scrollWidth,
        body: document.body.scrollWidth,
        direction: getComputedStyle(document.documentElement).direction
    })""")


def check_control_labels(page, identity):
    """Native HTML labels or ARIA names for visible form elements."""
    issues = page.evaluate("""() => {
      const els = [...document.querySelectorAll('input,select,textarea')];
      return els.filter(el => el.type !== 'hidden' && el.type !== 'submit' &&
          el.getClientRects().length && !el.disabled &&
          !(el.labels && el.labels.length) &&
          !el.getAttribute('aria-label') &&
          !el.getAttribute('aria-labelledby') &&
          !el.getAttribute('title'))
        .map(el => el.name || el.outerHTML.slice(0, 80)).slice(0, 12);
    }""")
    if issues:
        raise AssertionError(f"{identity}: unlabeled visible form controls: {issues}")


def check_page(page, lang, role, label, path, width):
    page.set_viewport_size({"width": width, "height": 844})
    result = page.goto(BASE + path.format(lang=lang), wait_until="domcontentloaded",
                       timeout=30000)
    identity = f"{lang}/{role}/{width}/{label}"
    if not result or result.status != 200:
        raise AssertionError(f"{identity}: unexpected HTTP {result and result.status}")
    expect = "rtl" if lang == "he" else "ltr"
    html = page.locator("html")
    if (html.get_attribute("lang"), html.get_attribute("dir")) != (lang, expect):
        raise AssertionError(f"{identity}: missing localized document direction")
    size = metrics(page)
    if size["direction"] != expect:
        raise AssertionError(f"{identity}: computed direction={size['direction']}")
    if max(size["doc"], size["body"]) > width + 2:
        OUT.mkdir(parents=True, exist_ok=True)
        page.screenshot(
            path=str(OUT / f"OVERFLOW-{lang}-{role}-{label}-{width}.png"),
            full_page=True,
        )
        raise AssertionError(f"{identity}: horizontal overflow {size}")
    if page.locator("main#main-content").count() != 1:
        raise AssertionError(f"{identity}: main landmark must be unique")
    if page.locator("a.skip-link[href='#main-content']").count() != 1:
        raise AssertionError(f"{identity}: missing skip link")
    if page.locator("h1").count() != 1:
        raise AssertionError(f"{identity}: expected one H1")
    if page.locator("#site-navigation").count() != 1:
        raise AssertionError(f"{identity}: missing nav landmark")

    # An overflowing input or untranslated long select label is a real
    # mobile reflow failure even when the page scroll width is unchanged.
    check_control_labels(page, identity)
    if label == "directory":
        if not page.locator('form[role="search"]').count():
            raise AssertionError(f"{identity}: search missing")
        if not page.locator('select[name="service"]').count():
            raise AssertionError(f"{identity}: service selector missing")
    if label == "wizard" and not page.locator('form button[name="action"]').count():
        raise AssertionError(f"{identity}: resumable wizard controls missing")
    if label == "chat" and not page.locator("#chat-log").count():
        raise AssertionError(f"{identity}: private conversation missing")
    if label == "worker_public":
        if "PRIVATE_STAGE086_WORKER_CONTACT" in page.content():
            raise AssertionError(f"{identity}: worker contact leaked publicly")
    if label in ("home", "directory", "worker_public"):
        if "PRIVATE_STAGE086_CLIENT_CONTACT" in page.content():
            raise AssertionError(f"{identity}: customer contact leaked publicly")
    if label == "worker_dashboard":
        if "PRIVATE_STAGE086_CLIENT_ADDRESS" in page.content():
            raise AssertionError(f"{identity}: customer address leaked to worker")

    if width in (320, 390) and label in ("home", "directory", "wizard", "chat"):
        OUT.mkdir(parents=True, exist_ok=True)
        screenshot = page.screenshot(
            path=str(OUT / f"{lang}-{role}-{label}-{width}.png"),
            full_page=True,
        )
        png_width = int.from_bytes(screenshot[16:20], "big")
        if png_width > width + 2:
            raise AssertionError(f"{identity}: PNG screenshot viewport overflow")

    return identity


def check_keyboard_disclosure(page, lang):
    page.set_viewport_size({"width": 320, "height": 844})
    page.goto(BASE + "/", wait_until="domcontentloaded")
    page.keyboard.press("Tab")
    focused = page.evaluate("""() => document.activeElement.classList.contains('skip-link')""")
    if not focused:
        raise AssertionError(f"{lang}: keyboard Tab must reach skip link first")
    width = page.evaluate("""() => getComputedStyle(document.activeElement).outlineWidth""")
    if float(width.replace("px", "")) < 3:
        raise AssertionError(f"{lang}: visible skip link focus indicator too thin")
    menu = page.locator("#site-menu-toggle")
    if not menu.is_visible():
        raise AssertionError(f"{lang}: mobile menu disclosure missing")
    menu.focus()
    page.keyboard.press("Enter")
    if menu.get_attribute("aria-expanded") != "true":
        raise AssertionError(f"{lang}: Enter did not open menu")
    if not page.locator("#site-navigation").is_visible():
        raise AssertionError(f"{lang}: open navigation not visible")
    if menu.get_attribute("aria-label") != menu.get_attribute("data-close-label"):
        raise AssertionError(f"{lang}: menu label did not announce close")
    page.keyboard.press("Escape")
    if menu.get_attribute("aria-expanded") != "false":
        raise AssertionError(f"{lang}: Escape did not close menu")
    if menu.get_attribute("aria-label") != menu.get_attribute("data-open-label"):
        raise AssertionError(f"{lang}: menu label did not announce open")
    if page.evaluate("document.activeElement.id") != "site-menu-toggle":
        raise AssertionError(f"{lang}: focus not restored to disclosure")


def check_text_resize(page, lang, role, label, path):
    """At 320 CSS pixels, 200% text resize must not create horizontal loss."""
    page.set_viewport_size({"width": 320, "height": 844})
    response = page.goto(BASE + path, wait_until="domcontentloaded", timeout=30000)
    identity = f"{lang}/{role}/{label}/200%-text"
    if response is None or response.status != 200:
        raise AssertionError(f"{identity}: unexpected response")
    size = page.evaluate("""() => {
      document.documentElement.style.fontSize = '200%';
      return {
        root: getComputedStyle(document.documentElement).fontSize,
        inner: window.innerWidth,
        doc: document.documentElement.scrollWidth,
        body: document.body.scrollWidth
      };
    }""")
    if float(size["root"].replace("px", "")) < 30:
        raise AssertionError(f"{identity}: resize did not apply")
    if max(size["doc"], size["body"]) > size["inner"] + 2:
        OUT.mkdir(parents=True, exist_ok=True)
        page.screenshot(
            path=str(OUT / f"TEXT-OVERFLOW-{lang}-{role}-{label}.png"),
            full_page=True,
        )
        raise AssertionError(f"{identity}: horizontal overflow {size}")


def check_without_js(browser, lang, session_name, session_key):
    from django.conf import settings
    context = browser.new_context(
        locale=lang, viewport={"width": 320, "height": 568},
        java_script_enabled=False,
    )
    context.add_cookies([{
        "name": session_name, "value": session_key, "url": BASE,
    }])
    page = context.new_page()
    try:
        home = page.goto(BASE + "/", wait_until="domcontentloaded")
        if home.status != 200 or not page.locator("#site-navigation").is_visible():
            raise AssertionError(f"{lang}: no-JS navigation unavailable")
        if not page.locator('form[action*="/setlang/"] noscript button').count():
            raise AssertionError(f"{lang}: no-JS language control unavailable")
        wizard = page.goto(BASE + "/orders/new/", wait_until="domcontentloaded")
        if wizard.status != 200 or not page.locator('.zw-panel form').count():
            raise AssertionError(f"{lang}: no-JS order wizard unavailable")
        position = page.locator(".site-header").evaluate(
            "(el) => getComputedStyle(el).position"
        )
        if position != "static":
            raise AssertionError(f"{lang}: expanded no-JS header traps short phones")
        submit = page.locator('.zw-panel form button[type="submit"]').first
        submit.scroll_into_view_if_needed()
        submit.click(trial=True, timeout=5000)
        box = submit.bounding_box()
        if box is None or box["y"] < 0 or box["y"] + box["height"] > 568:
            raise AssertionError(f"{lang}: short no-JS viewport cannot reach wizard submit")
        OUT.mkdir(parents=True, exist_ok=True)
        page.screenshot(
            path=str(OUT / f"NOJS-320x568-{lang}-client-wizard.png"),
            full_page=True,
        )
    finally:
        context.close()


def main():
    sessions, ids = fixtures()
    from django.conf import settings
    screens = {
        "guest": (
            ("home", "/"),
            ("catalog", "/{lang}/categories/"),
            ("directory", "/{lang}/workers/"),
            ("worker_public", f"/worker/{ids['worker']}/"),
            ("login", "/accounts/login/"),
            ("register", "/accounts/register/"),
        ),
        "client": (
            ("client_dashboard", "/client/dashboard/"),
            ("wizard", "/orders/new/"),
            ("order_detail", f"/orders/{ids['order']}/"),
            ("chat", f"/chat/{ids['chat']}/"),
            ("notifications", "/notifications/"),
            ("preferences", "/notifications/preferences/"),
            ("complaints", "/moderation/my/"),
        ),
        "worker": (
            ("worker_dashboard", "/worker/dashboard/"),
            ("worker_profile", "/accounts/worker/profile/"),
        ),
        "moderator": (
            ("moderation", "/moderation/queue/"),
        ),
    }
    cases = 0
    with sync_playwright() as playwright:
        opts = {"headless": True}
        executable = os.environ.get("PLAYWRIGHT_EXECUTABLE_PATH")
        if executable:
            opts["executable_path"] = executable
        else:
            opts["channel"] = os.environ.get("PLAYWRIGHT_CHANNEL", "chrome")
        browser = playwright.chromium.launch(**opts)
        try:
            for lang in LANGS:
                for role, paths in screens.items():
                    ctx = browser.new_context(
                        locale=lang, viewport={"width": 390, "height": 844},
                        is_mobile=True, has_touch=True, device_scale_factor=1,
                    )
                    if role != "guest":
                        ctx.add_cookies([{
                            "name": settings.SESSION_COOKIE_NAME,
                            "value": sessions[role], "url": BASE,
                        }])
                    page = ctx.new_page()
                    try:
                        for width in WIDTHS:
                            for label, path in paths:
                                check_page(page, lang, role, label, path, width)
                                cases += 1
                        if role == "guest":
                            for label, path in (
                                ("home", "/"),
                                ("directory", f"/{lang}/workers/"),
                                ("login", "/accounts/login/"),
                            ):
                                check_text_resize(page, lang, role, label, path)
                                cases += 1
                            check_keyboard_disclosure(page, lang)
                            cases += 1
                        elif role == "client":
                            for label, path in (
                                ("wizard", "/orders/new/"),
                                ("chat", f"/chat/{ids['chat']}/"),
                            ):
                                check_text_resize(page, lang, role, label, path)
                                cases += 1
                    finally:
                        ctx.close()
                check_without_js(
                    browser, lang, settings.SESSION_COOKIE_NAME,
                    sessions["client"],
                )
                cases += 1
        finally:
            browser.close()
    print(
        f"STAGE_08_6_BROWSER_PASS {cases} synthetic responsive, keyboard "
        "and RTL cases in Chrome emulation"
    )


if __name__ == "__main__":
    main()
