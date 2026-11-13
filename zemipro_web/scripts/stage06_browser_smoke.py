"""Stage 06 owner/worker mobile RTL smoke; only isolated CI with synthetic users."""
from pathlib import Path
import os
import sys

import django
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

BASE = 'http://127.0.0.1:8766'
OUT = Path('artifacts/stage06-mobile-rtl')
WIDTHS = (320, 390, 768)
LANGUAGES = ('ru', 'en', 'he')


def bootstrap():
    django.setup()
    from django.conf import settings
    from django.contrib.auth import get_user_model
    from django.db.models import Q
    from django.utils import timezone
    from apps.accounts.models import WorkerProfile
    from apps.locations.services import get_public_cities
    from apps.marketplace.models import Category, Order
    from apps.marketplace.offer_services import submit_offer

    if settings.ENVIRONMENT != 'test':
        raise RuntimeError('Stage 06 browser smoke refuses any non-test database')
    city = get_public_cities().first()
    category = Category.objects.filter(
        is_active=True, work_mode__in=('onsite', 'both'),
    ).filter(Q(section__isnull=True) | Q(section__is_active=True)).first()
    if city is None or category is None:
        raise AssertionError('Seed an isolated pilot city and category before browser test')
    credentials = {}
    accounts = {}
    for role in ('owner', 'worker1', 'worker2'):
        username = f'stage06_browser_{role}'
        password = 'SyntheticStage06Browser!90'
        account, _ = get_user_model().objects.get_or_create(
            username=username,
            defaults={'email': f'{username}@example.invalid'},
        )
        account.email_verified_at = timezone.now()
        account.email_verification_required = False
        account.set_password(password)
        account.save(update_fields=[
            'email_verified_at', 'email_verification_required', 'password',
        ])
        credentials[role] = (username, password)
        accounts[role] = account
        if role != 'owner':
            profile, _ = WorkerProfile.objects.update_or_create(
                user=account,
                defaults={
                    'city': city,
                    'is_published': True,
                    'availability': WorkerProfile.Availability.AVAILABLE,
                    'display_name': 'Synthetic stage06 specialist ' + role,
                    'description': 'No public client information.',
                    'pricing_details': 'Synthetic fixed price',
                    'spoken_languages': ['ru', 'en', 'he'],
                },
            )
            profile.skills.add(category)
    order = Order.objects.create(
        client=accounts['owner'], category=category, city=city,
        address='PRIVATE_BROWSER_STAGE06_LOCATION',
        description='PRIVATE_BROWSER_STAGE06_DESCRIPTION',
        price='Договорная',
    )
    for i, role in enumerate(('worker1', 'worker2')):
        submit_offer(
            order=order, actor=accounts[role], message='Synthetic sample conditions',
            data={
                'price_kind': 'fixed', 'amount_min_ils': str(100 + i * 50),
                'estimated_timeline': 'Two days', 'terms': 'Synthetic offer terms',
            },
        )
    return order.pk, credentials


def login(page, credentials):
    page.goto(BASE + '/accounts/login/', wait_until='networkidle')
    page.locator('input[name="username"]').fill(credentials[0])
    page.locator('input[name="password"]').fill(credentials[1])
    page.locator('form').filter(
        has=page.locator('input[name="password"]'),
    ).locator('button[type="submit"]').click()
    page.wait_for_url(
        lambda url: '/accounts/login/' not in url,
        timeout=15000,
    )


def inspect(page, *, lang, role, width, order_pk):
    page.set_viewport_size({'width': width, 'height': 844})
    page.goto(BASE + f'/orders/{order_pk}/', wait_until='networkidle')
    html = page.locator('html')
    expect_dir = 'rtl' if lang == 'he' else 'ltr'
    if (html.get_attribute('lang'), html.get_attribute('dir')) != (lang, expect_dir):
        raise AssertionError(f'{lang} HTML direction is wrong')
    if page.locator('.response-item').count() != (2 if role == 'owner' else 0):
        raise AssertionError(f'{lang}/{role}/{width}: incorrect private response visibility')
    body = page.content()
    if 'Synthetic offer terms' not in body and role == 'owner':
        raise AssertionError('Owner cannot view proposal terms')
    if 'Synthetic offer terms' in body and role != 'owner':
        raise AssertionError('Worker can read competing private proposals')
    if role != 'owner' and 'PRIVATE_BROWSER_STAGE06_LOCATION' in body:
        raise AssertionError('Unselected worker received private client address')
    metrics = page.evaluate('''() => ({
        inner: window.innerWidth,
        doc: document.documentElement.scrollWidth,
        body: document.body.scrollWidth
    })''')
    if max(metrics['doc'], metrics['body']) > metrics['inner'] + 2:
        OUT.mkdir(parents=True, exist_ok=True)
        page.screenshot(
            path=str(OUT / f'overflow-{lang}-{role}-{width}.png'),
            full_page=True,
        )
        raise AssertionError(f'Mobile overflow: {lang}/{role}/{width}: {metrics}')
    if role == 'owner' and width == 390:
        OUT.mkdir(parents=True, exist_ok=True)
        page.screenshot(
            path=str(OUT / f'comparison-{lang}.png'), full_page=True,
        )
    if role != 'owner' and width == 390:
        page.goto(BASE + f'/orders/{order_pk}/respond/', wait_until='networkidle')
        if page.locator('input[name="amount_min_ils"]').count() != 1:
            raise AssertionError('Typed offer form is missing')


def main():
    order_pk, credentials = bootstrap()
    count = 0
    with sync_playwright() as driver:
        opts = {'headless': True}
        executable = os.environ.get('PLAYWRIGHT_EXECUTABLE_PATH')
        if executable:
            opts['executable_path'] = executable
        else:
            opts['channel'] = os.environ.get('PLAYWRIGHT_CHANNEL', 'chrome')
        browser = driver.chromium.launch(**opts)
        try:
            for lang in LANGUAGES:
                for role in ('owner', 'worker1'):
                    ctx = browser.new_context(
                        locale=lang,
                        viewport={'width': 390, 'height': 844},
                        is_mobile=True, has_touch=True, device_scale_factor=1,
                    )
                    page = ctx.new_page()
                    login(page, credentials[role])
                    for width in WIDTHS:
                        inspect(
                            page, lang=lang, role=role,
                            width=width, order_pk=order_pk,
                        )
                        count += 1
                    ctx.close()
        finally:
            browser.close()
    print(f'STAGE_06_BROWSER_PASS {count} synthetic mobile/RTL cases')


if __name__ == '__main__':
    main()
