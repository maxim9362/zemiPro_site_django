"""Stage 02.6: mobile browser smoke in isolated CI, NOT physical Android tests."""
from pathlib import Path
import sys

import django
from playwright.sync_api import sync_playwright

PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

BASE = 'http://127.0.0.1:8765'
WIDTHS = (320, 360, 375, 390, 768, 1440)
LANGUAGES = ('ru', 'en', 'he')
SCREENS = ('/{lang}/categories/', '/{lang}/cities/', '/{lang}/workers/', '/worker/{worker_pk}/', '/orders/create/')
OUT = Path('artifacts/stage02-mobile-rtl')
OUT.mkdir(parents=True, exist_ok=True)


def bootstrap_verified_user(lang):
    django.setup()
    from django.conf import settings
    from django.contrib.auth import get_user_model
    from django.utils import timezone

    if settings.ENVIRONMENT != 'test':
        raise RuntimeError('Browser fixture creation requires isolated test settings')
    username = f'stage02_browser_{lang}'
    password = 'SyntheticStage02Sample!84'
    user, _ = get_user_model().objects.get_or_create(
        username=username,
        defaults={'email': f'stage02_{lang}@example.invalid'},
    )
    user.email_verified_at = timezone.now()
    user.email_verification_required = False
    user.set_password(password)
    user.save(update_fields=[
        'email_verified_at', 'email_verification_required', 'password',
    ])
    return username, password


def bootstrap_public_worker():
    """Only synthetic CI DB; show a real published card and its invite CTA."""
    django.setup()
    from django.conf import settings
    from django.contrib.auth import get_user_model
    from django.db.models import Q
    from apps.accounts.models import WorkerProfile
    from apps.locations.services import get_public_cities
    from apps.marketplace.models import Category

    if settings.ENVIRONMENT != 'test':
        raise RuntimeError('Stage 05 browser fixtures require isolated test settings')
    city = get_public_cities().first()
    category = Category.objects.filter(
        is_active=True, work_mode__in=('onsite', 'both'),
    ).filter(Q(section__isnull=True) | Q(section__is_active=True)).first()
    if city is None or category is None:
        raise AssertionError('Stage 05 browser smoke requires seeded pilot city/category')
    owner, _ = get_user_model().objects.get_or_create(
        username='stage05_browser_specialist',
    )
    profile, _ = WorkerProfile.objects.update_or_create(
        user=owner,
        defaults={
            'city': city, 'display_name': 'Synthetic Browser Specialist',
            'description': 'Synthetic public professional card for mobile browser checks.',
            'pricing_details': 'Quotation on request', 'spoken_languages': ['ru', 'en', 'he'],
            'is_published': True, 'availability': 'available',
            'contact': 'PRIVATE_BROWSER_05_CONTACT',
        },
    )
    profile.skills.add(category)
    return profile.pk


def inspect(page, lang, path, width):
    page.goto(BASE + path, wait_until='networkidle', timeout=20000)
    direction = 'rtl' if lang == 'he' else 'ltr'
    html = page.locator('html')
    actual = (html.get_attribute('lang'), html.get_attribute('dir'))
    if actual != (lang, direction):
        raise AssertionError(f'{lang}/{width}/{path}: html={actual}')
    metrics = page.evaluate('''() => ({
        doc: document.documentElement.scrollWidth,
        body: document.body.scrollWidth,
        inner: window.innerWidth,
        direction: getComputedStyle(document.documentElement).direction
    })''')
    if metrics['direction'] != direction:
        raise AssertionError(f'{lang}/{width}/{path}: css={metrics}')
    if max(metrics['doc'], metrics['body']) > metrics['inner'] + 2:
        page.screenshot(path=str(OUT / f'OVERFLOW-{lang}-{width}.png'), full_page=True)
        raise AssertionError(f'{lang}/{width}/{path}: overflow={metrics}')
    if not page.locator('.nav a').count():
        raise AssertionError(f'{lang}/{width}/{path}: no menu')
    if path.endswith('/workers/'):
        if not page.locator('form[role="search"]').is_visible():
            raise AssertionError(f'{lang}/{width}: specialist search form missing')
        if not page.locator('select[name="service"]').count():
            raise AssertionError(f'{lang}/{width}: service selector missing')
        if not page.locator('meta[name="robots"][content="noindex,follow"]').count():
            raise AssertionError(f'{lang}/{width}: directory not protected by noindex')
    if '/worker/' in path:
        if not page.locator('a[href$="/invite/"]').count():
            raise AssertionError(f'{lang}/{width}: profile invite link missing')
        if 'PRIVATE_BROWSER_05_CONTACT' in page.content():
            raise AssertionError(f'{lang}/{width}: private profile contact leaked')
    if path.endswith('/cities/'):
        cards = page.locator('.cities-grid a.city-card')
        if cards.count() != 1 or not cards.first.get_attribute('href').endswith('/cities/ashdod/'):
            raise AssertionError(f'{lang}/{width}: expected only Ashdod public city')
    if path == '/orders/create/':
        city_values = page.locator('select[name="city"] option').evaluate_all(
            'options => options.filter(option => option.value).map(option => option.value)'
        )
        if len(city_values) != 1:
            raise AssertionError(f'{lang}/{width}: order form exposes nonpilot cities')
        if not page.locator('#order-form').is_visible():
            raise AssertionError(f'{lang}/{width}: authenticated order form missing')
        # Stage 04.3 privacy: legacy HTML no longer asks for precise
        # address/phone; callers with old POST integrations stay supported.
        if page.locator('input[name="customer_phone"], input[name="address"]').count():
            raise AssertionError(f'{lang}/{width}: private contact input exposed')
        if not page.locator('a[href="/orders/new/"]').count():
            raise AssertionError(f'{lang}/{width}: wizard link missing')
    if lang == 'he' or width in (320, 390):
        screen = ('order' if 'orders' in path else
                  'specialist' if '/worker/' in path else
                  'workers' if 'workers' in path else
                  'catalog' if 'categories' in path else 'cities')
        screenshot = page.screenshot(
            path=str(OUT / f'{lang}-{screen}-{width}.png'),
            full_page=True,
        )
        # Chrome may enlarge full-page screenshots for overflowing descendants
        # even when documentElement.scrollWidth does not report the overflow.
        screenshot_width = int.from_bytes(screenshot[16:20], 'big')
        if screenshot_width > width + 2:
            raise AssertionError(
                f'{lang}/{width}/{path}: screenshot width {screenshot_width} exceeds viewport'
            )


def main():
    cases = 0
    credentials = {lang: bootstrap_verified_user(lang) for lang in LANGUAGES}
    worker_pk = bootstrap_public_worker()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel='chrome', headless=True)
        try:
            for lang in LANGUAGES:
                username, password = credentials[lang]
                context = browser.new_context(
                    locale=lang, viewport={'width': 390, 'height': 844},
                    is_mobile=True, has_touch=True, device_scale_factor=1,
                )
                page = context.new_page()
                page.goto(BASE + '/accounts/login/', wait_until='networkidle')
                page.locator('input[name="username"]').fill(username)
                page.locator('input[name="password"]').fill(password)
                page.locator('form').filter(
                    has=page.locator('input[name="password"]')
                ).locator('button[type="submit"]').click()
                page.wait_for_url(
                    lambda url: '/accounts/login/' not in url,
                    timeout=15000,
                )
                for width in WIDTHS:
                    page.set_viewport_size({'width': width, 'height': 844})
                    for template in SCREENS:
                        inspect(page, lang, template.format(lang=lang, worker_pk=worker_pk), width)
                        cases += 1
                context.close()
        finally:
            browser.close()
    print(f'STAGE_02_6_BROWSER_PASS {cases} cases in headless Chrome emulation')


if __name__ == '__main__':
    main()
