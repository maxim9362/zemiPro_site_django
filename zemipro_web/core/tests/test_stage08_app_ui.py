"""Stage 08.4 UI tests; only isolated synthetic Django data."""
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import ClientProfile
from apps.locations.models import City
from apps.marketplace.models import Category, Order, Subcategory
from apps.marketplace.tests.factories import make_order, make_user, make_worker_profile


class AppShellSourceTests(SimpleTestCase):
    def test_app_styles_are_scoped_and_support_mobile_wizard(self):
        base = Path(settings.BASE_DIR)
        css = (base / 'static/css/app-pages.css').read_text(encoding='utf-8')
        html = (base / 'templates/pages/app_base.html').read_text(encoding='utf-8')
        for selector in (
            '.app-dashboard', '.app-page-header', '.app-panel',
            '.app-offer-grid', '.zw-steps', '.zw-error-summary',
            '@media(max-width:480px)', 'prefers-reduced-motion',
        ):
            with self.subTest(selector=selector):
                self.assertIn(selector, css)
        self.assertIn("extends 'base.html'", html)
        self.assertIn('app-pages.css', html)

    def test_wizard_warns_without_browser_storage_of_private_inputs(self):
        root = Path(settings.BASE_DIR)
        js = (root / 'static/js/wizard-navigation.js').read_text(encoding='utf-8')
        template = (root / 'templates/pages/order_wizard.html').read_text(
            encoding='utf-8'
        )
        for snippet in (
            'data-wizard-back', 'data-unsaved-warning',
            'request.POST.photo_visibility', 'request.POST.public_photo_consent',
            'role="alert"', '<progress',
        ):
            with self.subTest(snippet=snippet):
                self.assertIn(snippet, template)
        self.assertNotIn('<style>', template)
        self.assertIn('window.confirm(', js)
        self.assertIn('name="action" value="back"', template)
        self.assertIn("name=\"action\" value=\"{% if is_new_wizard %}", template)
        for secret_storage in ('localStorage.', 'sessionStorage.', 'innerHTML'):
            self.assertNotIn(secret_storage, js)


@override_settings(ZEMIPRO_PILOT_CITY_SLUG='ashdod')
class AccountWorkflowUITests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.city = City.objects.create(
            slug='ashdod', name_ru='Ашдод', name_en='Ashdod', name_he='אשדוד'
        )
        cls.other_city = City.objects.create(
            slug='haifa', name_ru='Хайфа', name_en='Haifa', name_he='חיפה'
        )
        cls.category = Category.objects.create(
            slug='stage08-app-category', name_ru='Тестовые услуги',
            name_en='Sample services', name_he='שירותים לבדיקה',
            work_mode='onsite',
        )
        cls.service = Subcategory.objects.create(
            category=cls.category, slug='stage08-app-service',
            name_ru='Работа мастера', name_en='Professional work',
            name_he='עבודת בעל מקצוע', work_mode='onsite',
        )
        cls.owner = make_user('stage08-app-owner')
        cls.worker = make_user('stage08-app-worker')
        cls.stranger = make_user('stage08-app-stranger')
        cls.owner_profile = ClientProfile.objects.create(
            user=cls.owner, city=cls.city, contact='OWNER_PRIVATE_ACCOUNT_VALUE'
        )
        cls.other_profile = ClientProfile.objects.create(
            user=cls.stranger, city=cls.city,
            contact='STRANGER_PRIVATE_ACCOUNT_VALUE',
        )
        cls.worker_profile = make_worker_profile(
            cls.worker, city=cls.city, category=cls.category,
        )

    def test_guest_auth_pages_work_in_all_languages(self):
        paths = (
            reverse('accounts:login'), reverse('accounts:register'),
            reverse('accounts:password_reset'),
        )
        for lang, direction in (('ru', 'ltr'), ('en', 'ltr'), ('he', 'rtl')):
            for path in paths:
                with self.subTest(lang=lang, path=path):
                    page = self.client.get(path, HTTP_ACCEPT_LANGUAGE=lang)
                    self.assertEqual(page.status_code, 200)
                    self.assertContains(
                        page, f'<html lang="{lang}" dir="{direction}">'
                    )
                    self.assertContains(page, 'app-pages.css')
                    self.assertContains(page, 'app-panel')
                    self.assertNotContains(page, 'STRANGER_PRIVATE_ACCOUNT_VALUE')

    def test_registration_error_is_visible_and_form_remains_bound(self):
        page = self.client.post(reverse('accounts:register'), {})
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'role="alert"')
        self.assertContains(page, 'app-panel')
        self.assertContains(page, 'name="username"')

    def test_client_profile_validation_keeps_user_values(self):
        self.client.force_login(self.owner)
        page = self.client.post(reverse('accounts:client_profile'), {
            'city': self.other_city.pk, 'contact': 'A private draft contact',
        })
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'A private draft contact')
        self.assertContains(page, 'role="alert"')
        self.assertNotContains(page, 'STRANGER_PRIVATE_ACCOUNT_VALUE')
        self.assertEqual(
            ClientProfile.objects.get(user=self.owner).city_id, self.city.pk
        )

    def test_client_dashboard_is_private_and_has_navigation_landmarks(self):
        self.client.force_login(self.owner)
        page = self.client.get(reverse('marketplace:client_dashboard'))
        self.assertEqual(page.status_code, 200)
        for text in ('app-dashboard', 'id="client-profile"',
                     'id="client-invitations"', 'app-pages.css'):
            self.assertContains(page, text)
        self.assertNotContains(page, 'STRANGER_PRIVATE_ACCOUNT_VALUE')

    def test_worker_forms_and_dashboard_keep_original_actions(self):
        self.client.force_login(self.worker)
        profile = self.client.get(reverse('accounts:worker_profile'))
        dashboard = self.client.get(reverse('marketplace:worker_dashboard'))
        portfolio = self.client.get(reverse('accounts:worker_portfolio'))
        for page in (profile, dashboard, portfolio):
            self.assertEqual(page.status_code, 200)
            self.assertContains(page, 'app-pages.css')
        self.assertContains(profile, 'name="action" value="save"')
        self.assertContains(profile, 'name="action" value="publish"')
        self.assertContains(dashboard, 'id="worker-matches"')
        self.assertContains(dashboard, 'id="worker-responses"')
        self.assertContains(portfolio, 'enctype="multipart/form-data"')

    def test_wizard_invalid_start_keeps_state_and_valid_start_creates_draft(self):
        self.client.force_login(self.owner)
        start = reverse('marketplace:order_wizard_start')
        page = self.client.get(start)
        self.assertEqual(page.status_code, 200)
        token = page.context['token']
        invalid = self.client.post(start, {
            'action': 'start', 'token': token,
            'category': self.category.pk, 'subcategory': '',
        })
        self.assertEqual(invalid.status_code, 200)
        self.assertContains(invalid, 'zw-error-summary')
        self.assertContains(invalid, 'role="alert"')
        self.assertContains(invalid, 'name="category"')
        self.assertContains(invalid, 'wizard-navigation.js')
        self.assertFalse(Order.objects.filter(client=self.owner).exists())
        created = self.client.post(start, {
            'action': 'start', 'token': token,
            'category': self.category.pk, 'subcategory': self.service.pk,
        })
        self.assertEqual(created.status_code, 302)
        draft = Order.objects.get(client=self.owner)
        self.assertEqual(draft.status, Order.Status.DRAFT)
        wizard = self.client.get(
            reverse('marketplace:order_wizard_edit', args=[draft.pk])
        )
        self.assertEqual(wizard.status_code, 200)
        self.assertContains(wizard, '<progress')
        self.assertContains(wizard, 'zw-steps__done')

    def test_invalid_wizard_place_step_preserves_typed_area(self):
        self.client.force_login(self.owner)
        start = reverse('marketplace:order_wizard_start')
        token = self.client.get(start).context['token']
        created = self.client.post(start, {
            'action': 'start', 'token': token,
            'category': self.category.pk, 'subcategory': self.service.pk,
        })
        self.assertEqual(created.status_code, 302)
        draft = Order.objects.get(client=self.owner)
        edit = reverse('marketplace:order_wizard_edit', args=[draft.pk])
        self.assertEqual(self.client.post(edit + '?step=2', {
            'action': 'next', 'questionnaire_version': '',
        }).status_code, 302)
        invalid = self.client.post(edit + '?step=3', {
            'action': 'next', 'city': self.other_city.pk,
            'mode': 'onsite', 'area': 'North synthetic area',
        })
        self.assertEqual(invalid.status_code, 200)
        self.assertContains(invalid, 'North synthetic area')
        self.assertContains(invalid, 'zw-error-summary')
        self.assertIn('city', invalid.context['form'].errors)
        draft.refresh_from_db()
        self.assertEqual(draft.status, Order.Status.DRAFT)
        self.assertNotIn('3', draft.wizard_data.get('steps', {}))

    def test_wizard_save_and_back_persists_current_step_without_js(self):
        self.client.force_login(self.owner)
        start = reverse('marketplace:order_wizard_start')
        token = self.client.get(start).context['token']
        self.assertEqual(self.client.post(start, {
            'action': 'start', 'token': token,
            'category': self.category.pk, 'subcategory': self.service.pk,
        }).status_code, 302)
        draft = Order.objects.get(client=self.owner)
        edit = reverse('marketplace:order_wizard_edit', args=[draft.pk])
        self.assertEqual(self.client.post(edit + '?step=2', {
            'action': 'next', 'questionnaire_version': '',
        }).status_code, 302)
        self.assertEqual(self.client.post(edit + '?step=3', {
            'action': 'next', 'city': self.city.pk,
            'mode': 'onsite', 'area': 'City center',
        }).status_code, 302)
        saved_back = self.client.post(edit + '?step=4', {
            'action': 'back', 'urgency': 'urgent', 'preferred_date': '',
        })
        self.assertEqual(saved_back.status_code, 302)
        self.assertTrue(saved_back['Location'].endswith('?step=3'))
        draft.refresh_from_db()
        self.assertEqual(draft.wizard_data['steps']['4']['urgency'], 'urgent')
        revisit = self.client.get(edit + '?step=4')
        self.assertEqual(revisit.status_code, 200)
        self.assertEqual(revisit.context['form'].initial['urgency'], 'urgent')
        self.assertEqual(self.client.post(edit + '?step=4', {
            'action': 'back', 'urgency': '',
        }).status_code, 200)
        draft.refresh_from_db()
        self.assertEqual(draft.wizard_data['steps']['4']['urgency'], 'urgent')

    def test_offer_form_and_private_order_detail_keep_server_rights(self):
        order = make_order(
            client=self.owner, category=self.category, city=self.city,
            status=Order.Status.PUBLISHED,
            description='OWNER_ONLY_EXAMPLE_PRIVATE_DETAILS',
        )
        self.client.force_login(self.worker)
        form = self.client.get(reverse('marketplace:order_respond', args=[order.pk]))
        self.assertEqual(form.status_code, 200)
        self.assertContains(form, 'app-pages.css')
        self.assertContains(form, 'name="operation_key"')
        self.assertContains(form, 'name="price_kind"')
        self.client.force_login(self.owner)
        owner = self.client.get(reverse('marketplace:order_detail', args=[order.pk]))
        self.assertEqual(owner.status_code, 200)
        self.assertContains(owner, 'app-workflow')
        self.assertContains(owner, 'OWNER_ONLY_EXAMPLE_PRIVATE_DETAILS')
        self.client.force_login(self.stranger)
        stranger = self.client.get(reverse('marketplace:order_detail', args=[order.pk]))
        self.assertEqual(stranger.status_code, 200)
        self.assertNotContains(stranger, 'OWNER_ONLY_EXAMPLE_PRIVATE_DETAILS')
