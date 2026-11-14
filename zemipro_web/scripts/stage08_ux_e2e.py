"""Stage 08.7: authentic browser journeys on disposable Django/PostgreSQL only.

Screenshots are synthetic snapshots for subsequent visual inspection.
This is not manual physical-phone or screen-reader certification.
"""
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import django
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from stage08_mobile_a11y_smoke import fixtures as stage08_fixture

BASE = "http://127.0.0.1:8769"
OUT = Path("artifacts/stage08-ux-e2e")
LANGS = ("ru", "en", "he")
_DB_THREAD = ThreadPoolExecutor(max_workers=1, thread_name_prefix="stage08-orm")


def db_call(fn):
    """Keep Django ORM outside Playwright's active asyncio event-loop thread.

    The single test-only DB worker runs operations sequentially. No async-unsafe
    environment override or server-side permission exception is introduced.
    """
    return _DB_THREAD.submit(fn).result()



def bootstrap():
    django.setup()
    from django.conf import settings
    if settings.ENVIRONMENT != "test" or os.getenv("ZEMIPRO_TEST_ASHDOD_ONLY") != "1":
        raise RuntimeError("Stage08.7 browser acceptance requires test-only Ashdod database")
    sessions, seeded = stage08_fixture()
    from django.contrib.auth import get_user_model
    from apps.accounts.models import WorkerProfile
    from apps.locations.services import get_public_cities
    from apps.marketplace.models import Category, Subcategory, Order
    from apps.marketplace.tests.factories import make_order
    users = {
        role: get_user_model().objects.get(username="stage08_6_browser_" + role)
        for role in ("client", "worker", "moderator")
    }
    cat, _ = Category.objects.get_or_create(
        slug="stage08-7-chrome-category",
        defaults={
            "name_ru": "Тестовые работы", "name_en": "Test work",
            "name_he": "עבודת בדיקה", "work_mode": "onsite",
        },
    )
    service, _ = Subcategory.objects.get_or_create(
        category=cat, slug="stage08-7-chrome-service",
        defaults={
            "name_ru": "Мелкий ремонт", "name_en": "Small repairs",
            "name_he": "תיקונים קטנים", "work_mode": "onsite",
        },
    )
    worker = WorkerProfile.objects.get(user=users["worker"])
    worker.skills.add(cat)
    worker.services.add(service)
    city = get_public_cities().get(slug="ashdod")
    completed = make_order(
        client=users["client"], category=cat, city=city,
        worker=users["worker"], status=Order.Status.COMPLETED,
        description="Synthetic already completed fixture",
    )
    return sessions, seeded, users, cat.pk, service.pk, city.pk, completed.pk


def context_for(browser, lang, session, cookie_name):
    ctx = browser.new_context(
        locale=lang, viewport={"width": 390, "height": 844},
        device_scale_factor=1, is_mobile=True, has_touch=True,
    )
    if session:
        ctx.add_cookies([{"name": cookie_name, "value": session, "url": BASE}])
    return ctx


def visit(page, path, *, allowed=(200,)):
    result = page.goto(BASE + path, wait_until="domcontentloaded", timeout=30000)
    if not result or result.status not in allowed:
        raise AssertionError(f"Unexpected GET {path}: HTTP {result and result.status}")
    return result


def layout(page, label, lang, role):
    expected = "rtl" if lang == "he" else "ltr"
    el = page.locator("html")
    if el.get_attribute("lang") != lang or el.get_attribute("dir") != expected:
        raise AssertionError(f"{lang}/{role}/{label}: wrong language or direction")
    widths = page.evaluate("""() => ({
      doc: document.documentElement.scrollWidth,
      body: document.body.scrollWidth,
      view: window.innerWidth
    })""")
    if max(widths["doc"], widths["body"]) > widths["view"] + 2:
        screenshot(page, f"OVERFLOW-{lang}-{role}-{label}")
        raise AssertionError(f"{lang}/{role}/{label}: horizontal overflow {widths}")
    if page.locator("h1").count() != 1:
        raise AssertionError(f"{lang}/{role}/{label}: expected one h1")


def screenshot(page, filename):
    OUT.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(OUT / (filename + ".png")), full_page=True,
                    animations="disabled")


def post_click(page, form_selector, button_selector='button[type="submit"]'):
    form = page.locator(form_selector)
    if form.count() != 1:
        raise AssertionError(f"Expected one form: {form_selector}, got {form.count()}")
    form.locator(button_selector).click()
    page.wait_for_load_state("domcontentloaded")


def create_published_request(page, lang, category_id, service_id, city_id):
    from apps.marketplace.models import Order
    visit(page, "/orders/new/")
    layout(page, "wizard-new", lang, "client")
    screenshot(page, f"{lang}-client-wizard-start")
    page.locator('select[name="category"]').select_option(str(category_id))
    page.locator(f'select[name="subcategory"] option[value="{service_id}"]').wait_for(
        state="attached", timeout=12000
    )
    page.locator('select[name="subcategory"]').select_option(str(service_id))
    post_click(page, ".zw-panel > form", 'button[name="action"][value="start"]')
    if "/wizard/" not in page.url:
        raise AssertionError("Wizard draft not created after choosing the service")
    order_id = int(page.url.split("/orders/")[1].split("/")[0])
    order = db_call(lambda: Order.objects.get(pk=order_id))
    if order.status != Order.Status.DRAFT:
        raise AssertionError("Wizard should persist a private draft first")
    if page.locator(".zw-panel h2").count() != 1:
        raise AssertionError("Wizard must show current step heading")

    # Step 2: service-specific questionnaire can be skipped when not configured.
    post_click(page, ".zw-panel > form", 'button[name="action"][value="next"]')
    if "step=3" not in page.url:
        raise AssertionError(f"Wizard did not advance to location: {page.url}")
    page.locator('select[name="city"]').select_option(str(city_id))
    page.locator('select[name="mode"]').select_option("onsite")
    page.locator('input[name="area"]').fill("Central Ashdod synthetic area")
    post_click(page, ".zw-panel > form", 'button[name="action"][value="back"]')
    if "step=2" not in page.url:
        raise AssertionError("Save-and-go-back did not return to step 2")
    post_click(page, ".zw-panel > form", 'button[name="action"][value="next"]')
    if page.locator('input[name="area"]').input_value() != "Central Ashdod synthetic area":
        raise AssertionError("Back navigation lost saved location")
    post_click(page, ".zw-panel > form", 'button[name="action"][value="next"]')

    page.locator('select[name="urgency"]').select_option("normal")
    post_click(page, ".zw-panel > form", 'button[name="action"][value="next"]')
    page.locator('select[name="price_type"]').select_option("negotiable")
    post_click(page, ".zw-panel > form", 'button[name="action"][value="next"]')
    page.locator('textarea[name="description"]').fill(
        f"Synthetic stage08 browser job for {lang}; no phone or address"
    )
    screenshot(page, f"{lang}-client-wizard-description")
    post_click(page, ".zw-panel > form", 'button[name="action"][value="next"]')
    page.locator('input[name="display_name"]').fill("Sample Client")
    page.locator('input[name="chat_ack"]').check()
    post_click(page, ".zw-panel > form", 'button[name="action"][value="next"]')
    if page.locator('input[name="confirm"]').count() != 1:
        raise AssertionError("Final preview consent missing")
    layout(page, "wizard-review", lang, "client")
    screenshot(page, f"{lang}-client-wizard-confirm")
    page.locator('input[name="confirm"]').check()
    post_click(page, ".zw-panel > form", 'button[name="action"][value="publish"]')
    db_call(order.refresh_from_db)
    if order.status != Order.Status.PUBLISHED or order.city_id != city_id:
        raise AssertionError("Publishing did not persist the Ashdod-only order")
    if f"/orders/{order_id}/" not in page.url:
        raise AssertionError("Published order did not link to details")
    layout(page, "published-order", lang, "client")
    screenshot(page, f"{lang}-client-published-order")
    return order_id


def submit_worker_offer(page, lang, order_id):
    from apps.marketplace.models import Response
    visit(page, f"/orders/{order_id}/")
    layout(page, "worker-order", lang, "worker")
    visit(page, f"/orders/{order_id}/respond/")
    form = page.locator("form.form").filter(
        has=page.locator('input[name="amount_min_ils"]')
    )
    if form.count() != 1:
        raise AssertionError("Worker cannot access a matching order's offer form")
    form.locator('textarea[name="message"]').fill(
        f"Synthetic offer for {lang}, estimate after discussion"
    )
    form.locator('select[name="price_kind"]').select_option("fixed")
    form.locator('input[name="amount_min_ils"]').fill("125")
    form.locator('input[name="estimated_timeline"]').fill("Two days")
    form.locator('textarea[name="terms"]').fill("Synthetic conditions, no personal data")
    screenshot(page, f"{lang}-worker-offer-filled")
    form.locator('button[type="submit"]').click()
    page.wait_for_load_state("domcontentloaded")
    if f"/orders/{order_id}/" not in page.url:
        raise AssertionError(f"Offer POST did not return to order: {page.url}")
    offer = db_call(lambda: Response.objects.select_related('worker').get(order_id=order_id))
    if offer.worker.username != "stage08_6_browser_worker":
        raise AssertionError("Offer attributed to wrong worker")
    return offer.pk


def owner_accept_and_chat(page, worker_page, order_id, offer_id):
    from apps.marketplace.models import Order, Conversation, Message
    visit(page, f"/orders/{order_id}/")
    if page.locator(".response-item").count() != 1:
        raise AssertionError("Owner cannot compare worker offer")
    screenshot(page, "ru-client-offer-comparison")
    post_click(
        page, f'form[action="/chat/open/{offer_id}/"]',
    )
    if "/chat/" not in page.url:
        raise AssertionError("Chat did not open from private offer")
    conversation = db_call(lambda: Conversation.objects.get(response_id=offer_id))
    visit(page, f"/chat/{conversation.pk}/")
    layout(page, "chat-thread", "ru", "client")
    page.locator('textarea[name="body"]').fill(
        "Synthetic private message from order owner"
    )
    screenshot(page, "ru-client-chat")
    post_click(page, ".comm-chat-form")
    if not db_call(lambda: Message.objects.filter(
        conversation=conversation, body="Synthetic private message from order owner"
    ).exists()):
        raise AssertionError("Chat message was not persisted")
    visit(page, f"/orders/{order_id}/")
    post_click(page, f'form[action="/orders/{order_id}/responses/{offer_id}/accept/"]')
    order = db_call(lambda: Order.objects.get(pk=order_id))
    if order.status != Order.Status.ASSIGNED:
        raise AssertionError("Worker was not selected after owner POST")
    screenshot(page, "ru-client-assigned-order")
    visit(worker_page, f"/chat/{conversation.pk}/")
    if worker_page.locator(".comm-chat-form").count() != 1:
        raise AssertionError("Assigned worker has no private chat composer")
    worker_page.locator('textarea[name="body"]').fill(
        "Synthetic private reply from selected worker"
    )
    post_click(worker_page, ".comm-chat-form")
    if not db_call(lambda: Message.objects.filter(
        conversation=conversation, sender__username="stage08_6_browser_worker",
        body="Synthetic private reply from selected worker",
    ).exists()):
        raise AssertionError("Selected worker reply was not persisted")
    return conversation.pk


def report_message(client, moderator, chat_id):
    from apps.marketplace.models import Message
    from apps.moderation.models import Complaint
    message = db_call(lambda: Message.objects.filter(conversation_id=chat_id).order_by("-pk").first())
    visit(client, f"/chat/{chat_id}/")
    report = client.locator(f'a.comm-report-link[href*="message={message.pk}"]')
    if report.count() != 1:
        raise AssertionError("Message report link is not discoverable")
    report.click()
    client.wait_for_load_state("domcontentloaded")
    if "/moderation/complaint/" not in client.url:
        raise AssertionError("Message report did not open complaint form")
    client.locator('select[name="reason"]').select_option("other")
    client.locator('textarea[name="message"]').fill(
        "Synthetic complaint about the private message"
    )
    screenshot(client, "ru-client-complaint")
    post_click(client, "form.comm-form")
    case = db_call(lambda: Complaint.objects.filter(
        target_message_id=message.pk
    ).order_by("-pk").first())
    if case is None:
        raise AssertionError("Participant complaint was not stored")
    visit(moderator, "/moderation/queue/")
    if str(case.pk) not in moderator.locator("#pending-complaints").inner_text():
        # The heading has a count, but the case is in the same section.
        if not moderator.locator(f'form[action="/moderation/queue/{case.pk}/decision/"]').count():
            raise AssertionError("Authorized moderator cannot find pending case")
    screenshot(moderator, "ru-moderator-queue")
    decision = moderator.locator(f'form[action="/moderation/queue/{case.pk}/decision/"]')
    if decision.count() != 1:
        raise AssertionError("Moderator decision action missing")
    decision.locator('button[name="action"][value="resolve"]').click()
    moderator.wait_for_load_state("domcontentloaded")
    db_call(case.refresh_from_db)
    if case.status != Complaint.Status.RESOLVED:
        raise AssertionError("Moderator decision did not persist")
    visit(client, f"/moderation/complaint/{case.pk}/appeal/")
    client.locator('textarea[name="reason"]').fill(
        "Synthetic appeal on the moderator outcome"
    )
    post_click(client, "form.comm-form")
    db_call(case.refresh_from_db)
    appeal = db_call(lambda: getattr(case, "appeal", None))
    if appeal is None:
        raise AssertionError("Owner appeal was not persisted")
    visit(moderator, "/moderation/queue/")
    appeal_form = moderator.locator(
        f'form[action="/moderation/appeals/{appeal.pk}/decision/"]'
    )
    if appeal_form.count() != 1:
        raise AssertionError("Moderator appeal action missing")
    appeal_form.locator('button[name="action"][value="reject"]').click()
    moderator.wait_for_load_state("domcontentloaded")
    db_call(case.refresh_from_db)
    if db_call(lambda: case.appeal.status) != "rejected":
        raise AssertionError("Moderator appeal outcome not persisted")


def main():
    sessions, seeded, users, category_id, service_id, city_id, completed_id = bootstrap()
    from django.conf import settings
    count = 0
    with sync_playwright() as playwright:
        opts = {"headless": True}
        executable = os.getenv("PLAYWRIGHT_EXECUTABLE_PATH")
        if executable:
            opts["executable_path"] = executable
        else:
            opts["channel"] = os.getenv("PLAYWRIGHT_CHANNEL", "chrome")
        browser = playwright.chromium.launch(**opts)
        try:
            for lang in LANGS:
                guest_ctx = context_for(browser, lang, None, settings.SESSION_COOKIE_NAME)
                client_ctx = context_for(
                    browser, lang, sessions["client"], settings.SESSION_COOKIE_NAME
                )
                worker_ctx = context_for(
                    browser, lang, sessions["worker"], settings.SESSION_COOKIE_NAME
                )
                mod_ctx = context_for(
                    browser, lang, sessions["moderator"], settings.SESSION_COOKIE_NAME
                )
                try:
                    guest = guest_ctx.new_page()
                    client = client_ctx.new_page()
                    worker = worker_ctx.new_page()
                    moderator = mod_ctx.new_page()
                    for path in ("/", f"/{lang}/workers/"):
                        visit(guest, path)
                        layout(guest, path, lang, "guest")
                    screenshot(guest, f"{lang}-guest-directory")
                    order_id = create_published_request(
                        client, lang, category_id, service_id, city_id
                    )
                    count += 8
                    offer_id = submit_worker_offer(worker, lang, order_id)
                    count += 2
                    visit(client, f"/orders/{order_id}/")
                    if client.locator(".response-item").count() != 1:
                        raise AssertionError("Owner cannot see worker offer comparison")
                    screenshot(client, f"{lang}-client-offer-comparison")
                    count += 1
                    # Only the Russian pass runs the full chat/moderation/review chain.
                    if lang == "ru":
                        chat_id = owner_accept_and_chat(client, worker, order_id, offer_id)
                        count += 4
                        visit(moderator, f"/chat/{chat_id}/", allowed=(403,))
                        if "Synthetic private message from order owner" in moderator.content():
                            raise AssertionError("Moderator got participant-only chat")
                        count += 1
                        report_message(client, moderator, chat_id)
                        count += 4
                        visit(client, f"/orders/{completed_id}/review/")
                        screenshot(client, "ru-client-review-form")
                        client.locator('input[name="rating"]').fill("5")
                        client.locator('textarea[name="review_text"]').fill(
                            "Synthetic completion feedback without personal contact"
                        )
                        post_click(client, "form.form")
                        from apps.marketplace.models import Rating, RatingReply
                        rating = db_call(lambda: Rating.objects.get(order_id=completed_id))
                        visit(worker, f"/orders/{completed_id}/")
                        reply = worker.locator(f'form[action="/reviews/{rating.pk}/reply/"]')
                        if reply.count() != 1:
                            raise AssertionError("Selected worker cannot reply to public review")
                        reply.locator('textarea[name="body"]').fill(
                            "Thank you for the confirmed review"
                        )
                        reply.locator('button[type="submit"]').click()
                        worker.wait_for_load_state("domcontentloaded")
                        if not db_call(lambda: RatingReply.objects.filter(rating=rating).exists()):
                            raise AssertionError("Review reply did not persist")
                        count += 2
                finally:
                    guest_ctx.close()
                    client_ctx.close()
                    worker_ctx.close()
                    mod_ctx.close()
        finally:
            browser.close()
    print(f"STAGE_08_7_E2E_PASS {count} synthetic browser milestones")


if __name__ == "__main__":
    main()
