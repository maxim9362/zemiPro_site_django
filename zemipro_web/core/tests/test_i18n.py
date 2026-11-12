"""Stage 02.3: Django gettext, language switch, forms, locale-safe content."""
import ast
import gettext
import re
from pathlib import Path

from django.conf import settings
from django.test import TestCase
from django.urls import reverse
from django.utils import translation

from apps.accounts.forms import ClientProfileForm, WorkerProfileForm
from apps.locations.models import City
from apps.marketplace.forms import OrderCreateForm
from apps.marketplace.models import Category, Order, Subcategory
from apps.marketplace.tests.factories import make_user
from apps.notifications.models import Notification


class TrilingualInterfaceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.city = City.objects.create(
            slug='i18n-ashdod', name_ru='Ашдод',
            name_en='Ashdod', name_he='אשדוד',
        )
        cls.category = Category.objects.create(
            slug='i18n-plumbing', name_ru='Сантехника',
            name_en='Plumbing', name_he='אינסטלציה',
        )
        cls.service = Subcategory.objects.create(
            category=cls.category, slug='i18n-leak',
            name_ru='Устранение течи', name_en='Leak repair',
            name_he='תיקון נזילה',
        )
        cls.owner = make_user('i18n-owner')

    def test_home_catalog_city_and_signup_page_translate_across_languages(self):
        expected = {
            'ru': ('Категории', 'Категории услуг', 'Города', 'Регистрация', 'ltr'),
            'en': ('Categories', 'Service categories', 'Cities', 'Register', 'ltr'),
            'he': ('קטגוריות', 'קטגוריות שירותים', 'ערים', 'הרשמה', 'rtl'),
        }
        for lang, (nav, heading, cities, register, direction) in expected.items():
            with self.subTest(language=lang):
                urls = [
                    reverse('marketplace:home'),
                    reverse('marketplace:categories_list'),
                    reverse('marketplace:cities_list'),
                    reverse('accounts:register'),
                ]
                responses = [
                    self.client.get(url, HTTP_ACCEPT_LANGUAGE=lang) for url in urls
                ]
                for response in responses:
                    self.assertEqual(response.status_code, 200)
                    self.assertContains(
                        response, f'<html lang="{lang}" dir="{direction}">'
                    )
                    self.assertContains(response, nav)
                    self.assertContains(response, cities)
                self.assertContains(responses[0], heading)
                self.assertContains(responses[0], {'ru': 'Найдите мастера по ремонту в Израиле', 'en': 'Find a professional in Israel', 'he': 'מצאו איש מקצוע בישראל'}[lang])
                self.assertContains(responses[-1], register)

    def test_set_language_preserves_path_query_and_changes_cookie(self):
        current = reverse(
            'marketplace:category_detail', args=[self.category.slug]
        ) + '?city=i18n-ashdod&page=2'
        switch = self.client.post(reverse('set_language'), {
            'language': 'he', 'next': current,
        })
        self.assertEqual(switch.status_code, 302)
        self.assertEqual(switch['Location'], current)
        self.assertEqual(
            switch.cookies[settings.LANGUAGE_COOKIE_NAME].value, 'he'
        )
        page = self.client.get(current)
        self.assertContains(page, '<html lang="he" dir="rtl">')
        self.assertContains(page, 'אינסטלציה')
        self.assertContains(page, 'אשדוד')

        self.client.post(reverse('set_language'), {
            'language': 'en', 'next': current,
        })
        page = self.client.get(current)
        self.assertContains(page, '<html lang="en" dir="ltr">')
        self.assertContains(page, 'Plumbing')

    def test_set_language_disallows_external_redirect(self):
        response = self.client.post(reverse('set_language'), {
            'language': 'he', 'next': 'https://unsafe.example.invalid/login',
        })
        self.assertNotIn('unsafe.example.invalid', response.get('Location', ''))

    def test_translated_form_choices_labels_and_validation(self):
        with translation.override('he'):
            form = OrderCreateForm()
            self.assertEqual(str(form.fields['city'].label), 'עיר')
            self.assertEqual(str(form.fields['category'].label), 'קטגוריה')
            self.assertIn('אשדוד', str(form['city']))
            self.assertIn('אינסטלציה', str(form['category']))
            self.assertEqual(
                str(ClientProfileForm().fields['city'].label), 'עיר'
            )
            self.assertIn(
                'אשדוד', str(WorkerProfileForm()['service_cities'])
            )
            invalid = OrderCreateForm({
                'customer_name': 'Example',
                'customer_phone': '0501234567',
                'category': self.category.pk,
                'city': self.city.pk,
                'address': 'Safe address',
                'description': 'Too short',
            })
            self.assertFalse(invalid.is_valid())
            self.assertIn('התיאור חייב להכיל לפחות 30 תווים', str(
                invalid.errors['description']
            ))

    def test_complaint_reason_choice_labels_translate_without_changing_values(self):
        from apps.moderation.forms import ComplaintForm

        with translation.override('he'):
            form = ComplaintForm()
            options = list(form.fields['reason'].choices)
            self.assertIn(('spam', 'ספאם'), options)
            self.assertIn(('fraud', 'הונאה'), options)
            self.assertEqual(str(form.fields['reason'].label), 'סיבת הדיווח')

    def test_subcategory_json_returns_localized_name_without_private_data(self):
        url = reverse('marketplace:api_subcategories', args=[self.category.pk])
        for lang, expected in (
            ('ru', 'Устранение течи'),
            ('en', 'Leak repair'),
            ('he', 'תיקון נזילה'),
        ):
            with self.subTest(lang=lang):
                response = self.client.get(url, HTTP_ACCEPT_LANGUAGE=lang)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    response.json(), [{'id': self.service.pk, 'name': expected}]
                )
        self.assertEqual(self.client.post(url).status_code, 404)

    def test_user_entered_content_is_not_translated_or_rewritten(self):
        order = Order.objects.create(
            client=self.owner, category=self.category, city=self.city,
            description='Customer-written English text remains verbatim.',
            address='Private address example',
            price='Договорная',
        )
        self.client.force_login(self.owner)
        response = self.client.get(
            reverse('marketplace:order_detail', args=[order.pk]),
            HTTP_ACCEPT_LANGUAGE='he',
        )
        self.assertContains(response, 'Customer-written English text remains verbatim.')
        self.assertContains(response, 'dir="auto"')
        order.refresh_from_db()
        self.assertEqual(order.description, 'Customer-written English text remains verbatim.')
        self.assertEqual(order.price, 'Договорная')

    def test_known_notification_localizes_without_rewriting_database(self):
        order = Order.objects.create(
            client=self.owner, category=self.category, city=self.city,
            address='Private address', description='Long synthetic request',
        )
        notice = Notification.objects.create(
            recipient=self.owner, title='Новый отклик',
            message=f'Мастер откликнулся на вашу заявку №{order.pk}.',
            notification_type=Notification.Type.NEW_RESPONSE,
            related_order=order,
        )
        with translation.override('he'):
            self.assertEqual(notice.localized_title, 'תגובה חדשה')
            self.client.force_login(self.owner)
            listing = self.client.get(
                reverse('notifications:notification_list'),
                HTTP_ACCEPT_LANGUAGE='he',
            )
            self.assertContains(listing, 'תגובה חדשה')
            self.assertContains(listing, 'איש מקצוע הגיב')
            self.assertIn(str(order.pk), notice.localized_message)
            self.assertIn('איש מקצוע', notice.localized_message)
        notice.refresh_from_db()
        self.assertEqual(notice.title, 'Новый отклик')
        self.assertIn('Мастер откликнулся', notice.message)

    def test_compiled_mo_catalogs_exactly_match_editable_po_sources(self):
        root = Path(settings.BASE_DIR) / 'locale'
        for language in ('en', 'he'):
            with self.subTest(language=language):
                folder = root / language / 'LC_MESSAGES'
                po = (folder / 'django.po').read_text(encoding='utf-8')
                with (folder / 'django.mo').open('rb') as handle:
                    compiled = gettext.GNUTranslations(handle)
                entries = re.findall(
                    r'^msgid (".*")\nmsgstr (".*")',
                    po, flags=re.MULTILINE,
                )
                self.assertGreaterEqual(len(entries), 200)
                for source, translated in entries:
                    key = ast.literal_eval(source)
                    if key:
                        self.assertEqual(
                            compiled.gettext(key), ast.literal_eval(translated),
                            f'{language}: {key}',
                        )

    def test_rtl_mobile_css_has_logical_properties_and_isolated_user_content(self):
        css = (Path(settings.BASE_DIR) / 'static/css/style.css').read_text(
            encoding='utf-8'
        )
        self.assertIn('html[dir="rtl"]', css)
        self.assertIn('padding-inline-start', css)
        self.assertIn('margin-inline-start', css)
        self.assertIn('@media (max-width: 390px)', css)
        self.assertIn('unicode-bidi: plaintext', css)
