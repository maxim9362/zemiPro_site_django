"""Stage 02.6: mobile browser smoke in isolated CI, NOT physical Android tests."""
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = 'http://127.0.0.1:8765'
WIDTHS = (320, 360, 375, 390, 768)
LANGUAGES = ('ru', 'en', 'he')
SCREENS = ('/{lang}/categories/', '/{lang}/cities/', '/orders/create/')
OUT = Path('artifacts/stage02-mobile-rtl')
OUT.mkdir(parents=True, exist_ok=True)


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
    if path == '/orders/create/':
        if not page.locator('#order-form').is_visible():
            raise AssertionError(f'{lang}/{width}: authenticated order form missing')
        phone_direction = page.locator('input[name="customer_phone"]').evaluate(
            '(node) => getComputedStyle(node).direction'
        )
        if phone_direction != 'ltr':
            raise AssertionError(f'{lang}/{width}: phone direction={phone_direction}')
    if lang == 'he' or width in (320, 390):
        screen = 'order' if 'orders' in path else (
            'catalog' if 'categories' in path else 'cities'
        )
        page.screenshot(path=str(OUT / f'{lang}-{screen}-{width}.png'), full_page=True)


def main():
    cases = 0
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel='chrome', headless=True)
        try:
            for lang in LANGUAGES:
                context = browser.new_context(
                    locale=lang, viewport={'width': 390, 'height': 844},
                    is_mobile=True, has_touch=True, device_scale_factor=1,
                )
                page = context.new_page()
                page.goto(BASE + '/accounts/register/', wait_until='networkidle')
                page.locator('input[name="username"]').fill(f'stage02_browser_{lang}')
                page.locator('input[name="password1"]').fill('SyntheticStage02Sample!84')
                page.locator('input[name="password2"]').fill('SyntheticStage02Sample!84')
                page.locator('form').filter(
                    has=page.locator('input[name="password1"]')
                ).locator('button[type="submit"]').click()
                page.wait_for_url(
                    lambda url: '/accounts/register/' not in url,
                    timeout=15000,
                )
                for width in WIDTHS:
                    page.set_viewport_size({'width': width, 'height': 844})
                    for template in SCREENS:
                        inspect(page, lang, template.format(lang=lang), width)
                        cases += 1
                context.close()
        finally:
            browser.close()
    print(f'STAGE_02_6_BROWSER_PASS {cases} cases in headless Chrome emulation')


if __name__ == '__main__':
    main()
