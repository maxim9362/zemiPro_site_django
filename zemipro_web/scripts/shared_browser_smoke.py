"""Real Chromium smoke for the reusable isolated ZemiPro environment.

Viewport checks are emulation in a desktop browser, never physical-device proof.
"""
from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import Page, sync_playwright


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
        phone = page.locator('input[name="customer_phone"]')
        phone.fill("050-123-4567")
        if phone.evaluate("node => getComputedStyle(node).direction") != "ltr":
            raise AssertionError(f"{lang}/{width}: telephone field is not LTR")
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


def register(page: Page, lang: str) -> None:
    suffix = f"{int(time.time() * 1000)}_{lang}"
    page.goto(BASE_URL + "/accounts/register/", wait_until="networkidle")
    page.locator('input[name="username"]').fill(f"shared_browser_{suffix}")
    page.locator('input[name="password1"]').fill("SyntheticSharedSample!84")
    page.locator('input[name="password2"]').fill("SyntheticSharedSample!84")
    form = page.locator("form").filter(has=page.locator('input[name="password1"]'))
    with page.expect_navigation(timeout=20_000):
        form.locator('button[type="submit"]').click()
    if "/accounts/register/" in page.url:
        raise AssertionError(f"{lang}: registration did not authenticate")


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
                register(page, lang)
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
