"""Real Chromium smoke for the reusable isolated ZemiPro environment.

Viewport checks are emulation in a desktop browser, never physical-device proof.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import Page, sync_playwright


PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

BASE_URL = os.environ.get("ZEMIPRO_TEST_BASE_URL", "http://127.0.0.1:18000")
OUT = Path(os.environ.get("ZEMIPRO_TEST_SCREENSHOT_DIR", "artifacts/shared-test-env/screenshots"))
WIDTHS = (320, 360, 375, 390, 768, 1440)
LANGUAGES = ("ru", "en", "he")
PATHS = (
    ("home", "/"),
    ("catalog", "/{lang}/categories/"),
    ("section", "/{lang}/sections/repairs/"),
    ("category", "/{lang}/categories/plumbing/"),
    ("service", "/{lang}/services/plumbing/leak-repair/"),
    ("cities", "/{lang}/cities/"),
    ("city", "/{lang}/cities/ashdod/"),
    ("login", "/accounts/login/"),
    ("register", "/accounts/register/"),
    ("order", "/orders/create/"),
)
SCREENSHOT_PAGES = {"home", "catalog", "order"}
OUT.mkdir(parents=True, exist_ok=True)


def browser_launch(playwright):
    chrome = shutil.which("google-chrome") or shutil.which("google-chrome-stable")
    chromium = shutil.which("chromium") or shutil.which("chromium-browser")
    if chrome:
        return playwright.chromium.launch(executable_path=chrome, headless=True), chrome
    if chromium:
        return playwright.chromium.launch(executable_path=chromium, headless=True), chromium
    return playwright.chromium.launch(channel="chrome", headless=True), "chrome-channel"


def assert_page(page: Page, lang: str, label: str, path: str, width: int) -> None:
    response = page.goto(BASE_URL + path.format(lang=lang), wait_until="networkidle", timeout=30_000)
    if response is None or response.status >= 400:
        raise AssertionError(f"{lang}/{width}/{label}: HTTP {response and response.status}")

    direction = "rtl" if lang == "he" else "ltr"
    html = page.locator("html")
    actual = (html.get_attribute("lang"), html.get_attribute("dir"))
    if actual != (lang, direction):
        raise AssertionError(f"{lang}/{width}/{label}: html={actual}")
    metrics = page.evaluate(
        """() => ({
            doc: document.documentElement.scrollWidth,
            body: document.body.scrollWidth,
            inner: window.innerWidth,
            direction: getComputedStyle(document.documentElement).direction
        })"""
    )
    if metrics["direction"] != direction:
        raise AssertionError(f"{lang}/{width}/{label}: direction={metrics}")
    if max(metrics["doc"], metrics["body"]) > metrics["inner"] + 2:
        page.screenshot(path=str(OUT / f"OVERFLOW-{lang}-{label}-{width}.png"), full_page=True)
        raise AssertionError(f"{lang}/{width}/{label}: horizontal overflow={metrics}")
    if not page.locator(".nav a").count():
        raise AssertionError(f"{lang}/{width}/{label}: navigation missing")

    if label in {"login", "register", "order"} and not page.locator("form").count():
        raise AssertionError(f"{lang}/{width}/{label}: form missing")
    if label == "cities":
        cards = page.locator(".cities-grid a.city-card")
        if cards.count() != 1 or not urlparse(cards.first.get_attribute("href")).path.endswith("/cities/ashdod/"):
            raise AssertionError(f"{lang}/{width}: pilot city list is not Ashdod-only")
    if label == "order":
        selected_cities = page.locator('select[name="city"] option').evaluate_all(
            "options => options.filter(option => option.value).map(option => option.value)"
        )
        if len(selected_cities) != 1:
            raise AssertionError(f"{lang}/{width}: order form must offer exactly Ashdod")
        if not page.locator("#order-form").is_visible():
            raise AssertionError(f"{lang}/{width}: authenticated order form missing")
        if page.locator('input[name="customer_phone"], input[name="address"]').count():
            raise AssertionError(f"{lang}/{width}: legacy form leaked private contact input")
        if not page.locator('a[href="/orders/new/"]').count():
            raise AssertionError(f"{lang}/{width}: expected wizard link")
        page.locator('textarea[name="description"]').fill(
            "בדיקה mixed text 12345 — synthetic only"
        )

    if label in SCREENSHOT_PAGES:
        screenshot = page.screenshot(path=str(OUT / f"{lang}-{label}-{width}.png"), full_page=True)
        screenshot_width = int.from_bytes(screenshot[16:20], "big")
        if screenshot_width > width + 2:
            raise AssertionError(
                f"{lang}/{width}/{label}: screenshot width {screenshot_width} exceeds viewport"
            )


def bootstrap_verified_user(lang: str) -> tuple[str, str]:
    """Create only a synthetic test-DB user; never usable in other settings."""
    import django

    django.setup()
    from django.conf import settings
    from django.contrib.auth import get_user_model
    from django.utils import timezone

    database = settings.DATABASES['default']
    shared_loopback = (
        settings.ENVIRONMENT == "development"
        and database['HOST'] in {'127.0.0.1', 'localhost'}
        and database['NAME'] == 'zemipro_shared'
    )
    if settings.ENVIRONMENT != "test" and not shared_loopback:
        raise RuntimeError("Browser fixture creation requires an isolated test database")
    username = f"shared_browser_{lang}"
    password = "SyntheticSharedSample!84"
    user, _ = get_user_model().objects.get_or_create(
        username=username,
        defaults={"email": f"shared_{lang}@example.invalid"},
    )
    user.email = f"shared_{lang}@example.invalid"
    user.email_verified_at = timezone.now()
    user.email_verification_required = False
    user.set_password(password)
    user.save(update_fields=[
        "email", "email_verified_at", "email_verification_required", "password",
    ])
    return username, password


def login(page: Page, lang: str, credentials: tuple[str, str]) -> None:
    username, password = credentials
    # Verify the public registration contract separately from the fixture login.
    page.goto(BASE_URL + "/accounts/register/", wait_until="networkidle")
    if not page.locator('input[name="email"]').count():
        raise AssertionError(f"{lang}: email registration field missing")
    if page.locator('input[name="phone"]').count():
        raise AssertionError(f"{lang}: retired phone registration field present")
    if page.get_by_text("Google", exact=False).count():
        raise AssertionError(f"{lang}: Google button present while OAuth is disabled")

    page.goto(BASE_URL + "/accounts/login/", wait_until="networkidle")
    page.locator('input[name="username"]').fill(username)
    page.locator('input[name="password"]').fill(password)
    form = page.locator("form").filter(has=page.locator('input[name="password"]'))
    with page.expect_navigation(timeout=20_000):
        form.locator('button[type="submit"]').click()
    if "/accounts/login/" in page.url:
        raise AssertionError(f"{lang}: verified synthetic login failed")


def verify_language_switch(page: Page, source: str, target: str) -> None:
    page.goto(BASE_URL + f"/{source}/categories/?city=ashdod", wait_until="networkidle")
    with page.expect_navigation(timeout=20_000):
        page.locator("#language-choice").select_option(target)
    parsed = urlparse(page.url)
    if not parsed.path.startswith(f"/{target}/categories/") or parsed.query != "city=ashdod":
        raise AssertionError(f"language switch did not preserve resource/query: {page.url}")


def main() -> None:
    cases = 0
    errors: list[str] = []
    console_errors: list[str] = []
    http_errors: list[tuple[int, str]] = []
    request_failures: list[str] = []
    credentials = {lang: bootstrap_verified_user(lang) for lang in LANGUAGES}
    with sync_playwright() as playwright:
        browser, executable = browser_launch(playwright)
        try:
            for lang in LANGUAGES:
                context = browser.new_context(
                    locale=lang,
                    viewport={"width": 390, "height": 844},
                    is_mobile=True,
                    has_touch=True,
                    device_scale_factor=1,
                )
                page = context.new_page()

                def collect_console(message) -> None:
                    if message.type == "error":
                        console_errors.append(message.text)

                def collect_response(response) -> None:
                    if response.status >= 400:
                        http_errors.append((response.status, response.url))

                page.on("console", collect_console)
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.on("response", collect_response)
                page.on("requestfailed", lambda request: request_failures.append(request.url))
                login(page, lang, credentials[lang])
                for width in WIDTHS:
                    height = 900 if width < 1000 else 1000
                    page.set_viewport_size({"width": width, "height": height})
                    for label, path in PATHS:
                        assert_page(page, lang, label, path, width)
                        cases += 1
                context.close()

            switch_context = browser.new_context(locale="ru", viewport={"width": 390, "height": 844})
            switch_page = switch_context.new_page()
            verify_language_switch(switch_page, "ru", "he")
            switch_context.close()
        finally:
            browser.close()

    allowed_resource_gaps = [
        item for item in http_errors if urlparse(item[1]).path == "/favicon.ico" and item[0] == 404
    ]
    unexpected_http = [item for item in http_errors if item not in allowed_resource_gaps]
    generic_resource_errors = [
        message for message in console_errors if message.startswith("Failed to load resource:")
    ]
    unexpected_console = [message for message in console_errors if message not in generic_resource_errors]
    if errors or unexpected_console or unexpected_http or request_failures:
        raise AssertionError(
            f"browser errors={errors}; console errors={unexpected_console}; "
            f"HTTP errors={unexpected_http}; request failures={request_failures}"
        )
    result = {
        "status": "PASS",
        "browser": executable,
        "cases": cases,
        "languages": list(LANGUAGES),
        "widths": list(WIDTHS),
        "physical_device": "NOT_RUN",
        "screenshots": len(list(OUT.glob("*.png"))),
        "known_non_blocking_resource_gaps": sorted(set(allowed_resource_gaps)),
    }
    (OUT.parent / "browser-result.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print("SHARED_BROWSER_PASS", json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
