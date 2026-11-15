"""Stage 09 public SEO smoke in real Chromium with synthetic PostgreSQL data.

Viewport checks are desktop Chromium emulation, not physical-device proof.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright


PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")

BASE_URL = os.environ.get("ZEMIPRO_TEST_BASE_URL", "http://127.0.0.1:8770")
OUT = Path("artifacts/stage09-seo-browser")
LANGUAGES = ("ru", "en", "he")
VIEWPORTS = ((320, 568), (390, 844), (768, 900), (1440, 1000))
PRIVATE_SENTINEL = "private-stage09-browser@example.invalid"


def bootstrap() -> str:
    import django

    django.setup()
    from django.conf import settings
    from django.contrib.auth import get_user_model
    from django.utils import timezone

    from apps.accounts.models import WorkerProfile
    from apps.locations.models import City
    from apps.marketplace.models import Category, Subcategory
    from apps.seo.models import SeoContentPage

    database = settings.DATABASES["default"]
    if settings.ENVIRONMENT != "test" or database["HOST"] not in {
        "127.0.0.1",
        "localhost",
    }:
        raise RuntimeError("Stage 09 browser fixtures require isolated test PostgreSQL")

    city, _ = City.objects.update_or_create(
        slug="ashdod",
        defaults={
            "name_ru": "Ашдод",
            "name_en": "Ashdod",
            "name_he": "אשדוד",
            "is_active": True,
        },
    )
    category, _ = Category.objects.update_or_create(
        slug="stage09-browser-repair",
        defaults={
            "name_ru": "Отделка для браузерной проверки",
            "name_en": "Browser fixture finishing",
            "name_he": "גימור לבדיקת דפדפן",
            "description": "Проверяемая синтетическая категория для Ашдода.",
            "description_en": "A reviewed synthetic category for Ashdod.",
            "description_he": "קטגוריה סינתטית שנבדקה עבור אשדוד.",
            "is_active": True,
        },
    )
    service, _ = Subcategory.objects.update_or_create(
        category=category,
        slug="stage09-browser-painting",
        defaults={
            "name_ru": "Покраска для браузерной проверки",
            "name_en": "Browser fixture painting",
            "name_he": "צביעה לבדיקת דפדפן",
            "description_ru": "Синтетическая услуга без цен и рекламных обещаний.",
            "description_en": "A synthetic service without prices or marketing claims.",
            "description_he": "שירות סינתטי ללא מחירים או הבטחות שיווקיות.",
            "is_active": True,
        },
    )
    users = get_user_model().objects
    author, _ = users.get_or_create(
        username="stage09-browser-author",
        defaults={"email": "stage09-browser-author@example.invalid"},
    )
    reviewer, _ = users.get_or_create(
        username="stage09-browser-reviewer",
        defaults={
            "email": "stage09-browser-reviewer@example.invalid",
            "is_staff": True,
        },
    )
    for user in (author, reviewer):
        user.is_active = True
        user.is_blocked = False
        user.email_verification_required = False
        user.save(update_fields=["is_active", "is_blocked", "email_verification_required"])
    if not reviewer.is_staff:
        reviewer.is_staff = True
        reviewer.save(update_fields=["is_staff"])

    worker, _ = WorkerProfile.objects.get_or_create(user=author)
    worker.city = city
    worker.display_name = "Stage09 Safe Painter"
    worker.description = "Synthetic public profile with no personal contact details."
    worker.pricing_details = "Terms are agreed through a protected order."
    worker.contact = PRIVATE_SENTINEL
    worker.is_published = True
    worker.save()
    worker.skills.add(category)
    worker.services.add(service)

    now = timezone.now()
    localized = {
        "ru": ("Проверенная покраска в Ашдоде", "Как выбрать исполнителя"),
        "en": ("Reviewed painting in Ashdod", "How to choose a specialist"),
        "he": ("צביעה שנבדקה באשדוד", "איך לבחור בעל מקצוע"),
    }
    for language, (title, topic) in localized.items():
        SeoContentPage.objects.update_or_create(
            page_type=SeoContentPage.PageType.SERVICE_CITY,
            language=language,
            section=None,
            category=None,
            service=service,
            city=city,
            defaults={
                "topic": topic,
                "title": title,
                "meta_description": (
                    f"{title}: synthetic reviewed catalog information for the Ashdod "
                    "pilot, without invented prices, ratings or guarantees."
                ),
                "summary": (
                    f"{title}. This reviewed summary describes the protected request "
                    "flow and uses only synthetic catalog facts."
                ),
                "body": (
                    f"{title}. This reviewed browser fixture explains how a visitor can "
                    "compare the visible service scope and continue to a protected order. "
                    "It contains no invented price, rating, guarantee, licence or personal "
                    f"contact. Language marker: {language}. All records are synthetic and "
                    "exist only in the isolated PostgreSQL test database."
                ),
                "source_facts": "Synthetic Stage 09 browser fixtures only.",
                "status": SeoContentPage.Status.PUBLISHED,
                "quality_approved": True,
                "author": author,
                "reviewer": reviewer,
                "reviewed_at": now,
                "published_at": now,
            },
        )
    return (
        "/{lang}/services/stage09-browser-repair/"
        "stage09-browser-painting/ashdod/"
    )


def launch_browser(playwright):
    executable = (
        shutil.which("google-chrome")
        or shutil.which("google-chrome-stable")
        or shutil.which("chromium")
        or shutil.which("chromium-browser")
    )
    if executable:
        return playwright.chromium.launch(executable_path=executable, headless=True), executable
    return playwright.chromium.launch(channel="chrome", headless=True), "chrome-channel"


def assert_public_page(page, *, language: str, path: str, width: int) -> None:
    response = page.goto(BASE_URL + path, wait_until="networkidle", timeout=30_000)
    if response is None or response.status != 200:
        raise AssertionError(f"{language}/{width}: HTTP {response and response.status}")
    direction = "rtl" if language == "he" else "ltr"
    html = page.locator("html")
    if (html.get_attribute("lang"), html.get_attribute("dir")) != (language, direction):
        raise AssertionError(f"{language}/{width}: wrong language/direction")
    if page.locator('meta[name="robots"][content="noindex,follow"]').count():
        raise AssertionError(f"{language}/{width}: eligible page unexpectedly noindex")
    canonical = page.locator('link[rel="canonical"]').get_attribute("href")
    if canonical != BASE_URL + path:
        raise AssertionError(f"{language}/{width}: bad canonical {canonical}")
    alternates = set(page.locator('link[rel="alternate"]').evaluate_all(
        "nodes => nodes.map(node => node.hreflang)"
    ))
    if alternates != {"ru", "en", "he", "x-default"}:
        raise AssertionError(f"{language}/{width}: bad hreflang {alternates}")
    if page.locator("h1").count() != 1 or not page.locator(".breadcrumbs").count():
        raise AssertionError(f"{language}/{width}: semantic heading/breadcrumb missing")
    markup = page.locator('script[type="application/ld+json"]').text_content()
    graph = json.loads(markup)["@graph"]
    graph_types = {item["@type"] for item in graph}
    if not {"WebPage", "BreadcrumbList", "Service"}.issubset(graph_types):
        raise AssertionError(f"{language}/{width}: incomplete JSON-LD {graph_types}")
    visible = page.locator("body").inner_text()
    html_source = page.content()
    if PRIVATE_SENTINEL in visible or PRIVATE_SENTINEL in html_source:
        raise AssertionError(f"{language}/{width}: private contact leaked")
    metrics = page.evaluate(
        """() => ({doc: document.documentElement.scrollWidth,
                    body: document.body.scrollWidth, inner: window.innerWidth})"""
    )
    if max(metrics["doc"], metrics["body"]) > metrics["inner"] + 2:
        raise AssertionError(f"{language}/{width}: horizontal overflow {metrics}")


def main() -> None:
    path_template = bootstrap()
    OUT.mkdir(parents=True, exist_ok=True)
    cases = 0
    screenshots = 0
    with sync_playwright() as playwright:
        browser, executable = launch_browser(playwright)
        try:
            for language in LANGUAGES:
                path = path_template.format(lang=language)
                context = browser.new_context(locale=language)
                page = context.new_page()
                for width, height in VIEWPORTS:
                    page.set_viewport_size({"width": width, "height": height})
                    assert_public_page(
                        page, language=language, path=path, width=width,
                    )
                    cases += 1
                    if width in {320, 1440}:
                        page.screenshot(
                            path=str(OUT / f"{language}-{width}.png"), full_page=True,
                        )
                        screenshots += 1
                page.goto(BASE_URL + path, wait_until="networkidle")
                page.keyboard.press("Tab")
                if "skip-link" not in (page.locator(":focus").get_attribute("class") or ""):
                    raise AssertionError(f"{language}: keyboard skip link is not first focus")
                context.close()

                no_js = browser.new_context(
                    locale=language,
                    java_script_enabled=False,
                    viewport={"width": 320, "height": 568},
                )
                fallback = no_js.new_page()
                assert_public_page(
                    fallback, language=language, path=path, width=320,
                )
                if not fallback.locator('a[href*="/orders/new/"]').count():
                    raise AssertionError(f"{language}: no-JS order fallback missing")
                cases += 1
                no_js.close()

            technical = browser.new_page()
            robots = technical.goto(BASE_URL + "/robots.txt", wait_until="networkidle")
            if robots is None or robots.status != 200 or "Disallow: /knowledge/" not in technical.content():
                raise AssertionError("robots.txt is not the Stage 09 allowlist policy")
            cases += 1
            sitemap = technical.goto(BASE_URL + "/sitemap.xml", wait_until="networkidle")
            source = technical.content()
            if sitemap is None or sitemap.status != 200 or "stage09-browser-painting" not in source:
                raise AssertionError("eligible Stage 09 page missing from sitemap")
            if PRIVATE_SENTINEL in source:
                raise AssertionError("private contact leaked into sitemap")
            cases += 1
        finally:
            browser.close()

    result = {
        "status": "PASS",
        "browser": executable,
        "cases": cases,
        "languages": list(LANGUAGES),
        "viewports": [list(viewport) for viewport in VIEWPORTS],
        "javascript_disabled_cases": len(LANGUAGES),
        "screenshots": screenshots,
        "physical_devices": "NOT_RUN",
    }
    (OUT / "result.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print("STAGE09_SEO_BROWSER_PASS", json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
