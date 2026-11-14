"""Stage 08.2: shared template, mobile menu and privacy regressions."""
from pathlib import Path

from django import forms
from django.conf import settings
from django.template.loader import render_to_string
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from apps.accounts.models import WorkerProfile
from apps.locations.models import City
from apps.marketplace.models import Category
from apps.marketplace.tests.factories import make_user


class SharedUISourceTests(SimpleTestCase):
    def test_design_tokens_focus_and_all_order_states(self):
        css = (Path(settings.BASE_DIR) / 'static/css/design-system.css').read_text(
            encoding='utf-8'
        )
        for token in ('--ui-primary:', '--ui-focus:', '--ui-radius:',
                      ':focus-visible', 'prefers-reduced-motion'):
            with self.subTest(token=token):
                self.assertIn(token, css)
        for status in ('draft', 'published', 'in_discussion', 'assigned',
                       'in_progress', 'completed', 'cancelled', 'expired', 'disputed'):
            with self.subTest(status=status):
                self.assertIn('.ui-status--' + status, css)

    def test_mobile_navigation_progressive_keyboard_and_safe_dom(self):
        root = Path(settings.BASE_DIR) / 'static'
        css = (root / 'css/design-system.css').read_text(encoding='utf-8')
        js = (root / 'js/navigation.js').read_text(encoding='utf-8')
        self.assertIn('.has-nav-js .site-nav.nav:not(.is-open)', css)
        self.assertIn("classList.add('has-nav-js')", js)
        self.assertIn('.has-nav-js .site-menu-toggle', css)
        self.assertIn("event.key === 'Escape'", js)
        self.assertIn("setAttribute('aria-expanded'", js)
        self.assertNotIn('innerHTML', js)

    def test_form_partial_and_empty_state_escape_untrusted_inputs(self):
        class Form(forms.Form):
            query = forms.CharField(
                min_length=4, label='Service', help_text='Type a service'
            )

        form = Form({'query': 'x'})
        self.assertFalse(form.is_valid())
        field_html = render_to_string('components/form_field.html', {
            'field': form['query'],
        })
        self.assertIn('Type a service', field_html)
        self.assertIn('role="alert"', field_html)
        html = render_to_string('components/empty_state.html', {
            'empty_title': '<img src=x onerror=alert(1)>',
            'empty_description': 'None',
        })
        self.assertIn('&lt;img', html)
        self.assertNotIn('<img', html)


class SharedUIPageTests(TestCase):
    def test_ru_en_he_shell_and_keyboard_skip(self):
        for lang, direction, skip in (
            ('ru', 'ltr', 'Перейти к содержимому'),
            ('en', 'ltr', 'Skip to main content'),
            ('he', 'rtl', 'דלג לתוכן הראשי'),
        ):
            with self.subTest(language=lang):
                response = self.client.get(
                    reverse('marketplace:home'), HTTP_ACCEPT_LANGUAGE=lang
                )
                self.assertEqual(response.status_code, 200)
                self.assertContains(
                    response, f'<html lang="{lang}" dir="{direction}">'
                )
                for expected in (skip, 'href="#main-content"',
                                 'id="main-content"', 'id="site-menu-toggle"',
                                 'aria-controls="site-navigation"',
                                 'aria-expanded="false"',
                                 'design-system.css', 'navigation.js',
                                 'name="language"', 'name="next"'):
                    self.assertContains(response, expected)

    def test_role_navigation_preserves_post_switch_and_profile(self):
        user = make_user('stage08-nav')
        self.client.force_login(user)
        client = self.client.get(reverse('marketplace:home'))
        self.assertContains(client, 'href="/client/dashboard/"')
        self.assertNotContains(client, 'href="/worker/dashboard/"')
        self.assertContains(client, 'action="/accounts/switch-role/"')
        self.assertNotContains(client, 'href="/moderation/queue/"')
        self.assertContains(client, 'name="role" value="worker"')
        user.active_role = 'worker'
        user.save(update_fields=['active_role'])
        worker = self.client.get(reverse('marketplace:home'))
        self.assertContains(worker, 'href="/worker/dashboard/"')
        self.assertNotContains(worker, 'href="/client/dashboard/"')
        self.assertContains(worker, 'name="role" value="client"')
        self.assertContains(worker, 'href="/accounts/worker/profile/"')

    def test_shared_category_card_renders_home_and_catalog(self):
        category = Category.objects.create(
            slug='stage08-category', name_ru='Тестовая услуга',
            name_en='Test service', name_he='שירות בדיקה',
            description='Safe description', is_active=True,
        )
        for url in (reverse('marketplace:home'),
                    reverse('marketplace:categories_list')):
            with self.subTest(url=url):
                page = self.client.get(url)
                self.assertEqual(page.status_code, 200)
                self.assertContains(page, 'Тестовая услуга')
                self.assertContains(page, 'class="category-card"')
                self.assertContains(page, reverse(
                    'marketplace:category_detail', kwargs={'slug': category.slug}
                ))

    def test_public_worker_card_hides_private_contact(self):
        city = City.objects.create(
            slug='ashdod', name_ru='Ашдод',
            name_en='Ashdod', name_he='אשדוד',
        )
        user = make_user(
            'stage08-card', email='secret-stage08@example.invalid'
        )
        category = Category.objects.create(
            slug='stage08-service', name_ru='Услуги',
            name_en='Services', name_he='שירותים',
        )
        profile = WorkerProfile.objects.create(
            user=user, city=city, display_name='Stage 08 Expert',
            description='Public synthetic skilled worker text.',
            contact='PRIVATE_STAGE08_CONTACT',
            pricing_details='Negotiable', spoken_languages=['ru'],
            is_published=True,
        )
        profile.skills.add(category)
        page = self.client.get(reverse('marketplace:worker_directory'))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'ui-worker-card')
        self.assertContains(page, 'Stage 08 Expert')
        self.assertNotContains(page, 'PRIVATE_STAGE08_CONTACT')
        self.assertNotContains(page, 'secret-stage08@example.invalid')

    def test_empty_directory_shared_component(self):
        page = self.client.get(reverse('marketplace:worker_directory'))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'ui-empty-state')
        self.assertContains(
            page, 'Подходящих опубликованных специалистов пока нет.'
        )
