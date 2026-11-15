"""Stage 14 RU/EN/HE, RTL, responsive and no-JS Chromium acceptance.

The script refuses non-test settings and creates synthetic Ashdod-only records.
Viewport checks are desktop Chromium emulation, not physical-device proof.
"""
import os
import sys
from pathlib import Path
from uuid import uuid4

import django
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

BASE = 'http://127.0.0.1:8770'
OUT = ROOT / 'artifacts' / 'stage14-knowledge'
PRIVATE_MARKER = 'secretxq@example.invalid'


def fixtures():
    django.setup()
    from django.conf import settings
    from django.contrib.auth import get_user_model
    from django.contrib.auth.models import Permission
    from django.contrib.sessions.backends.db import SessionStore
    from django.urls import reverse

    from apps.accounts.models import WorkerProfile
    from apps.knowledge import qa_services, recommendation_services, request_services
    from apps.locations.models import City
    from apps.marketplace.models import Category

    if settings.ENVIRONMENT != 'test' or settings.DATABASES['default']['HOST'] not in {
        'localhost', '127.0.0.1', '::1', 'db', 'postgres',
    }:
        raise RuntimeError('Stage 14 browser smoke requires isolated test settings')
    required = (
        'ZEMIPRO_KNOWLEDGE_QA_ENABLED',
        'ZEMIPRO_PERSONAL_RECOMMENDATIONS_ENABLED',
        'ZEMIPRO_PROFILE_SHARING_ENABLED',
        'ZEMIPRO_RECOMMENDATION_REQUESTS_ENABLED',
    )
    if not all(getattr(settings, name, False) for name in required):
        raise RuntimeError('Use core.config.stage14_browser explicitly')

    run = uuid4().hex[:10]
    city, _ = City.objects.get_or_create(
        slug='ashdod',
        defaults={'name_ru': 'Ашдод', 'name_en': 'Ashdod', 'name_he': 'אשדוד'},
    )
    category = Category.objects.create(
        slug=f'stage14-browser-{run}', name_ru='Синтетический ремонт',
        name_en='Synthetic repair', name_he='תיקון סינתטי', is_active=True,
    )
    users = {}
    for role in ('asker', 'requester', 'worker', 'recommender', 'moderator'):
        user = get_user_model().objects.create_user(
            username=f'stage14_browser_{run}_{role}',
            email=PRIVATE_MARKER if role == 'worker' else '',
            is_staff=role == 'moderator',
        )
        user.email_verification_required = False
        user.save(update_fields=['email_verification_required'])
        users[role] = user
    users['moderator'].user_permissions.add(*Permission.objects.filter(
        content_type__app_label='knowledge',
        codename__in=(
            'moderate_expert_questions',
            'moderate_personal_recommendations',
            'moderate_recommendation_requests',
        ),
    ))
    profile = WorkerProfile.objects.create(
        user=users['worker'], city=city, is_published=True,
        display_name='Synthetic knowledge specialist',
        description='Synthetic public profile for isolated browser acceptance.',
        pricing_details='Synthetic estimate only', spoken_languages=['ru', 'en', 'he'],
    )
    profile.skills.add(category)

    questions = {}
    requests = {}
    for language in ('ru', 'en', 'he'):
        question = qa_services.create_question(
            actor=users['asker'], category_id=category.pk, language=language,
            title=f'Synthetic {language} safety question',
            body='Which safe maintenance sequence should an Ashdod resident follow?',
        )
        question = qa_services.submit_question(
            actor=users['asker'], question_id=question.pk,
            expected_version=question.content_version,
        )
        question = qa_services.moderate_question(
            actor=users['moderator'], question_id=question.pk,
            expected_version=question.content_version, approve=True,
        )
        answer = qa_services.create_answer(
            actor=users['worker'], question_id=question.pk,
            body='A synthetic specialist answer with no contact details or private data.',
        )
        answer = qa_services.submit_answer(
            actor=users['worker'], answer_id=answer.pk,
            expected_version=answer.content_version,
        )
        qa_services.moderate_answer(
            actor=users['moderator'], answer_id=answer.pk,
            expected_version=answer.content_version, approve=True,
        )
        questions[language] = question.slug

        item = request_services.create_request(
            actor=users['requester'], category_id=category.pk, language=language,
            title=f'Synthetic {language} specialist request',
            body='Please suggest a public Ashdod specialist based on personal experience.',
        )
        item = request_services.moderate_request(
            actor=users['moderator'], request_id=item.pk,
            expected_version=item.content_version, approve=True,
        )
        response = request_services.create_response(
            actor=users['recommender'], request_id=item.pk, worker_id=profile.pk,
            body='I suggest reviewing this synthetic public specialist profile carefully.',
        )
        request_services.moderate_response(
            actor=users['moderator'], response_id=response.pk,
            expected_version=response.content_version, approve=True,
        )
        requests[language] = item.slug

        author = get_user_model().objects.create_user(
            username=f'stage14_browser_{run}_rec_{language}',
        )
        rec = recommendation_services.create_recommendation(
            actor=author, worker_id=profile.pk, language=language,
            body=(
                f'Synthetic {language} personal experience outside ZemiPro; '
                'the specialist explained the work clearly and carefully.'
            ), experience_confirmed=True,
        )
        rec = recommendation_services.submit_recommendation(
            actor=author, recommendation_id=rec.pk,
            expected_version=rec.content_version,
        )
        recommendation_services.moderate_recommendation(
            actor=users['moderator'], recommendation_id=rec.pk,
            expected_version=rec.content_version, approve=True,
        )

    session = SessionStore()
    session['_auth_user_id'] = str(users['asker'].pk)
    session['_auth_user_backend'] = 'django.contrib.auth.backends.ModelBackend'
    session['_auth_user_hash'] = users['asker'].get_session_auth_hash()
    session.save()
    return (
        questions, requests, profile.pk,
        reverse('marketplace:worker_public_profile', args=[profile.pk]),
        session.session_key, settings.SESSION_COOKIE_NAME,
    )


def assert_page(page, path, language, width, marker):
    page.set_viewport_size({'width': width, 'height': 844})
    response = page.goto(BASE + path, wait_until='domcontentloaded')
    if response is None or response.status != 200:
        raise AssertionError(f'{path} returned {response.status if response else "no response"}')
    expected_dir = 'rtl' if language == 'he' else 'ltr'
    html = page.locator('html')
    if html.get_attribute('lang') != language or html.get_attribute('dir') != expected_dir:
        raise AssertionError(f'{path} language/direction mismatch')
    if marker not in page.locator('body').inner_text():
        raise AssertionError(f'{path} expected content missing')
    if PRIVATE_MARKER in page.content():
        raise AssertionError(f'{path} leaked private account data')
    dimensions = page.evaluate('''() => ({
        viewport: innerWidth,
        document: document.documentElement.scrollWidth,
        body: document.body.scrollWidth
    })''')
    if max(dimensions['document'], dimensions['body']) > dimensions['viewport'] + 2:
        raise AssertionError(f'{path} overflows width {width}: {dimensions}')


def main():
    questions, requests, worker_id, profile_path, session_key, cookie_name = fixtures()
    markers = {
        'ru': ('Вопросы и ответы', 'Личные рекомендации', 'Посоветуйте мастера'),
        'en': ('Questions and answers', 'Personal recommendations', 'Recommend a specialist'),
        'he': ('שאלות ותשובות', 'המלצות אישיות', 'המליצו על בעל מקצוע'),
    }
    count = 0
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        options = {'headless': True}
        executable = os.environ.get('PLAYWRIGHT_EXECUTABLE_PATH')
        if executable:
            options['executable_path'] = executable
        else:
            options['channel'] = os.environ.get('PLAYWRIGHT_CHANNEL', 'chrome')
        browser = playwright.chromium.launch(**options)
        try:
            for language in ('ru', 'en', 'he'):
                context = browser.new_context(
                    locale=language, viewport={'width': 390, 'height': 844},
                    is_mobile=True, has_touch=True, device_scale_factor=1,
                )
                context.add_cookies([{
                    'name': cookie_name, 'value': session_key, 'url': BASE,
                }])
                page = context.new_page()
                pages = (
                    (f'/{language}/questions/', markers[language][0]),
                    (f'/{language}/questions/{questions[language]}/', 'Synthetic'),
                    (f'/{language}/recommendations/', markers[language][1]),
                    (f'/{language}/recommend-master/', markers[language][2]),
                    (f'/{language}/recommend-master/{requests[language]}/', 'Synthetic'),
                    (profile_path, 'Synthetic knowledge specialist'),
                )
                for width in (320, 390, 768, 1440):
                    for path, marker in pages:
                        assert_page(page, path, language, width, marker)
                        count += 1
                for path, marker in pages[:3]:
                    assert_page(page, path, language, 390, marker)
                    page.screenshot(
                        path=str(
                            OUT / (
                                f'{language}-390-'
                                f'{path.strip("/").replace("/", "-")}.png'
                            )
                        ),
                        full_page=True,
                    )
                    count += 1
                share = context.request.get(
                    BASE + f'/{language}/share/profile/{worker_id}/facebook/',
                    max_redirects=0,
                )
                if share.status != 302 or not share.headers['location'].startswith(
                    'https://www.facebook.com/sharer/sharer.php?'
                ):
                    raise AssertionError('Explicit Facebook share redirect is unsafe')
                count += 1
                context.close()

                no_js = browser.new_context(
                    locale=language, java_script_enabled=False,
                    viewport={'width': 320, 'height': 568},
                )
                no_js.add_cookies([{
                    'name': cookie_name, 'value': session_key, 'url': BASE,
                }])
                page = no_js.new_page()
                assert_page(page, f'/{language}/questions/', language, 320, markers[language][0])
                assert_page(
                    page, f'/{language}/recommend-master/{requests[language]}/',
                    language, 320, 'Synthetic',
                )
                count += 2
                no_js.close()
        finally:
            browser.close()
    print(f'STAGE_14_BROWSER_PASS {count} synthetic browser checks')


if __name__ == '__main__':
    main()
