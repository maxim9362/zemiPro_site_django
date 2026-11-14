"""Stage 07 Chromium chat/RTL smoke on isolated, seeded PostgreSQL only."""
import os
import sys
from pathlib import Path

import django
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

BASE = 'http://127.0.0.1:8767'
OUT = Path('artifacts/stage07-chat-mobile')


def fixtures():
    django.setup()
    from django.conf import settings
    from django.contrib.auth import get_user_model
    from django.contrib.sessions.backends.db import SessionStore
    from django.db.models import Q
    from apps.accounts.models import WorkerProfile
    from apps.locations.services import get_public_cities
    from apps.marketplace.chat_services import open_conversation, send_message
    from apps.marketplace.models import Category, Order, Response
    from uuid import uuid4

    if settings.ENVIRONMENT != 'test':
        raise RuntimeError('Use isolated test database only')
    city = get_public_cities().first()
    category = Category.objects.filter(
        is_active=True, work_mode__in=('onsite', 'both'),
    ).filter(Q(section__isnull=True) | Q(section__is_active=True)).first()
    if city is None or city.slug != 'ashdod' or category is None:
        raise AssertionError('Ashdod-only test seed is required')
    users = {}
    sessions = {}
    for role in ('customer', 'worker', 'outsider', 'moderator'):
        user, _ = get_user_model().objects.get_or_create(
            username='stage07_ci_browser_' + role,
        )
        user.is_staff = role == 'moderator'
        user.is_active = True
        user.is_blocked = False
        user.email_verification_required = False
        user.set_unusable_password()
        user.save(update_fields=[
            'is_active', 'is_blocked', 'email_verification_required', 'password', 'is_staff',
        ])
        if role == 'moderator':
            from django.contrib.auth.models import Permission
            user.user_permissions.add(Permission.objects.get(
                content_type__app_label='moderation', codename='review_complaints',
            ))
        session = SessionStore()
        session['_auth_user_id'] = str(user.pk)
        session['_auth_user_backend'] = 'django.contrib.auth.backends.ModelBackend'
        session['_auth_user_hash'] = user.get_session_auth_hash()
        session.save()
        users[role] = user
        sessions[role] = session.session_key
    profile, _ = WorkerProfile.objects.update_or_create(
        user=users['worker'],
        defaults={
            'city': city,
            'is_published': True,
            'availability': WorkerProfile.Availability.AVAILABLE,
            'display_name': 'Synthetic QA specialist',
            'description': 'Synthetic QA profile',
            'pricing_details': 'Negotiable',
            'spoken_languages': ['ru', 'en', 'he'],
        },
    )
    profile.skills.add(category)
    order = Order.objects.create(
        client=users['customer'], category=category, city=city,
        address='Synthetic QA location', description='Synthetic QA order',
    )
    response = Response.objects.create(
        order=order, worker=users['worker'], status=Response.Status.SENT,
    )
    conversation, _ = open_conversation(
        response_id=response.pk, actor=users['customer'],
    )
    send_message(
        conversation_id=conversation.pk, actor=users['worker'],
        body='Synthetic stored QA message', client_nonce=uuid4(),
    )
    return conversation.pk, sessions


def check(page, *, lang, role, width, conversation_id):
    page.set_viewport_size({'width': width, 'height': 844})
    response = page.goto(BASE + '/chat/' + str(conversation_id) + '/',
                         wait_until='domcontentloaded')
    if role == 'outsider':
        if response.status != 403 or 'Synthetic stored QA message' in page.content():
            raise AssertionError('Third-party chat access was not denied')
        return
    if response.status != 200:
        raise AssertionError('Authorized chat request failed')
    page.locator('#chat-log').wait_for(state='visible')
    expected_dir = 'rtl' if lang == 'he' else 'ltr'
    html = page.locator('html')
    if html.get_attribute('lang') != lang or html.get_attribute('dir') != expected_dir:
        raise AssertionError('Language/direction mismatch')
    if 'Synthetic stored QA message' not in page.locator('#chat-log').inner_text():
        raise AssertionError('Original message absent')
    if page.locator('form[action*="/translate/"]').count() < 1:
        raise AssertionError('Translation form missing')
    dimensions = page.evaluate('''() => ({
        width: innerWidth,
        document: document.documentElement.scrollWidth,
        body: document.body.scrollWidth
    })''')
    if max(dimensions['document'], dimensions['body']) > dimensions['width'] + 2:
        raise AssertionError('Chat view overflows mobile viewport')
    if width == 390:
        OUT.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(OUT / f'{lang}-{role}.png'), full_page=True)
        test_text = f'Synthetic persisted post {lang} {role}'
        page.locator('textarea[name="body"]').fill(test_text)
        page.locator('form').filter(
            has=page.locator('textarea[name="body"]'),
        ).locator('button[type="submit"]').click()
        page.wait_for_load_state('domcontentloaded')
        page.reload(wait_until='domcontentloaded')
        if test_text not in page.locator('#chat-log').inner_text():
            raise AssertionError('Chat post lost after reload')
        poll = page.request.get(
            BASE + f'/chat/{conversation_id}/poll/?after=0',
        )
        if poll.status != 200 or not poll.json()['messages']:
            raise AssertionError('Message reconnect/poll failed')


def main():
    conversation_id, sessions = fixtures()
    from django.conf import settings
    counter = 0
    with sync_playwright() as playwright:
        opts = {'headless': True}
        executable = os.environ.get('PLAYWRIGHT_EXECUTABLE_PATH')
        if executable:
            opts['executable_path'] = executable
        else:
            opts['channel'] = os.environ.get('PLAYWRIGHT_CHANNEL', 'chrome')
        browser = playwright.chromium.launch(**opts)
        try:
            for lang in ('ru', 'en', 'he'):
                for role in ('customer', 'worker', 'outsider'):
                    context = browser.new_context(
                        locale=lang,
                        viewport={'width': 390, 'height': 844},
                        is_mobile=True, has_touch=True, device_scale_factor=1,
                    )
                    context.add_cookies([{
                        'name': settings.SESSION_COOKIE_NAME,
                        'value': sessions[role], 'url': BASE,
                    }])
                    page = context.new_page()
                    for width in (320, 390, 768):
                        check(page, lang=lang, role=role, width=width,
                              conversation_id=conversation_id)
                        counter += 1
                    context.close()
                for role, path, expected in (
                    ('customer', '/notifications/preferences/',
                     {'ru': 'Настройки уведомлений', 'en': 'Notification settings', 'he': 'הגדרות התראות'}),
                    ('worker', '/notifications/preferences/',
                     {'ru': 'Настройки уведомлений', 'en': 'Notification settings', 'he': 'הגדרות התראות'}),
                    ('moderator', '/moderation/queue/',
                     {'ru': 'Очередь модерации', 'en': 'Moderation queue', 'he': 'תור לבדיקה'}),
                ):
                    context = browser.new_context(locale=lang, viewport={'width': 320, 'height': 844})
                    context.add_cookies([{'name': settings.SESSION_COOKIE_NAME,
                                         'value': sessions[role], 'url': BASE}])
                    page = context.new_page()
                    response = page.goto(BASE + path, wait_until='domcontentloaded')
                    if response.status != 200 or expected[lang] not in page.locator('h1').inner_text():
                        raise AssertionError('Stage07 settings/moderation localization failed')
                    if page.evaluate('document.documentElement.scrollWidth > innerWidth + 2'):
                        raise AssertionError('Stage07 settings/moderation mobile overflow')
                    counter += 1
                    context.close()
                # Server-rendered send/read must also work without JavaScript.
                context = browser.new_context(locale=lang, java_script_enabled=False,
                                              viewport={'width': 320, 'height': 844})
                context.add_cookies([{'name': settings.SESSION_COOKIE_NAME,
                                     'value': sessions['customer'], 'url': BASE}])
                page = context.new_page()
                check(page, lang=lang, role='customer', width=390,
                      conversation_id=conversation_id)
                page.locator('form[action$="/read/"] button').click()
                page.wait_for_url(BASE + f'/chat/{conversation_id}/')
                receipt = page.request.get(BASE + f'/chat/{conversation_id}/poll/?after=0')
                me = int(page.locator('#chat-log').get_attribute('data-me'))
                if receipt.status != 200 or any(
                        not item['read'] for item in receipt.json()['messages']
                        if item['sender_id'] != me):
                    raise AssertionError('No-JavaScript read receipt was not persisted')
                counter += 1
                context.close()
        finally:
            browser.close()
    print(f'STAGE_07_BROWSER_PASS {counter} synthetic browser cases')


if __name__ == '__main__':
    main()
