"""Stage 08.3: trilingual Ashdod public UX and privacy regressions."""
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils.translation import override

from apps.accounts.models import WorkerProfile
from apps.locations.models import City
from apps.marketplace.models import Category, ServiceSection, Subcategory
from apps.marketplace.tests.factories import make_user


class PublicUIStylesTests(SimpleTestCase):
    def test_public_css_is_scoped_responsive_and_reduced_motion_aware(self):
        base = Path(settings.BASE_DIR)
        css = (base / 'static/css/public-pages.css').read_text(encoding='utf-8')
        page_base = (
            base / 'templates/pages/public_base.html'
        ).read_text(encoding='utf-8')
        for required in (
            '.public-hero', '.public-search-form', '.public-result-grid',
            '.public-profile__overview', '.public-category-grid',
            '@media (max-width: 640px)', 'prefers-reduced-motion',
            'minmax(min(100%',
        ):
            with self.subTest(selector=required):
                self.assertIn(required, css)
        self.assertIn('public-pages.css', page_base)
        self.assertIn("extends 'base.html'", page_base)

    def test_public_css_does_not_replace_base_design_system(self):
        base = (Path(settings.BASE_DIR) / 'templates/base.html').read_text(
            encoding='utf-8'
        )
        self.assertIn('design-system.css', base)
        self.assertIn('{% block page_styles %}', base)
        self.assertIn('id="main-content"', base)


@override_settings(ZEMIPRO_PILOT_CITY_SLUG='ashdod')
class PublicUIStage08Tests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ashdod = City.objects.create(
            slug='ashdod', name_ru='Ашдод', name_en='Ashdod', name_he='אשדוד'
        )
        cls.other_city = City.objects.create(
            slug='ashkelon', name_ru='Ашкелон',
            name_en='Ashkelon', name_he='אשקלון',
        )
        cls.section = ServiceSection.objects.create(
            slug='repairs-083',
            name_ru='Домашний ремонт', name_en='Home repairs',
            name_he='תיקוני בית',
            description_ru='Сервисный раздел ремонта',
            description_en='Home repair services',
            description_he='שירותי תיקון לבית',
        )
        cls.category = Category.objects.create(
            section=cls.section, slug='plumbing-083',
            name_ru='Сантехнические работы', name_en='Plumbing work',
            name_he='עבודות אינסטלציה', description='Работы сантехника в доме.',
            description_en='Home plumbing service',
            description_he='שירותי אינסטלציה בבית', work_mode='onsite',
        )
        cls.service = Subcategory.objects.create(
            category=cls.category, slug='faucet-083',
            name_ru='Установка крана', name_en='Faucet installation',
            name_he='התקנת ברז',
            description_ru='Замена крана и сантехнический монтаж.',
            description_en='Faucet replacement and installation',
            description_he='התקנה והחלפה של ברזים',
        )
        cls.worker_user = make_user('public083worker')
        cls.worker = WorkerProfile.objects.create(
            user=cls.worker_user, city=cls.ashdod,
            display_name='Clear Home Plumber',
            description='Professional repairs of sinks and water fixtures.',
            pricing_details='Pricing depends on the agreed project.',
            contact='0503456789', spoken_languages=['ru', 'en'],
            starting_price_ils=Decimal('190.00'), is_published=True,
        )
        cls.worker.skills.add(cls.category)
        cls.worker.services.add(cls.service)
        cls.off_user = make_user('public083offpilot')
        cls.off_worker = WorkerProfile.objects.create(
            user=cls.off_user, city=cls.other_city,
            display_name='Outside Pilot Worker',
            description='Professional work outside of the pilot area.',
            pricing_details='Negotiable', is_published=True,
        )
        cls.off_worker.skills.add(cls.category)

    def test_home_makes_ashdod_and_two_paths_clear_in_all_languages(self):
        expected = {
            'ru': ('ltr', 'Пока работаем только в Ашдоде'),
            'en': ('ltr', 'Currently serving Ashdod only'),
            'he': ('rtl', 'הפיילוט פועל באשדוד בלבד'),
        }
        for lang, (direction, label) in expected.items():
            with self.subTest(language=lang):
                response = self.client.get(
                    reverse('marketplace:home'), HTTP_ACCEPT_LANGUAGE=lang,
                )
                self.assertEqual(response.status_code, 200)
                self.assertContains(
                    response, f'<html lang="{lang}" dir="{direction}">'
                )
                self.assertContains(response, label)
                self.assertContains(response, 'public-hero__actions')
                self.assertContains(
                    response, reverse('marketplace:worker_directory')
                )
                self.assertContains(
                    response, reverse('marketplace:order_wizard_start')
                )
                self.assertContains(response, 'public-pages.css')
                self.assertNotContains(
                    response, 'Опишите задачу, выберите категорию и укажите адрес'
                )

    def test_catalog_section_category_and_service_routes_remain_localized(self):
        for lang, category_name in (
            ('ru', 'Сантехнические работы'),
            ('en', 'Plumbing work'),
            ('he', 'עבודות אינסטלציה'),
        ):
            with self.subTest(language=lang), override(lang):
                listing = self.client.get(
                    reverse('catalog_i18n:categories_list'),
                    HTTP_ACCEPT_LANGUAGE=lang,
                )
                section = self.client.get(
                    reverse('catalog_i18n:section_detail', args=[self.section.slug]),
                    HTTP_ACCEPT_LANGUAGE=lang,
                )
                category = self.client.get(
                    reverse('catalog_i18n:category_detail', args=[self.category.slug]),
                    HTTP_ACCEPT_LANGUAGE=lang,
                )
                service = self.client.get(
                    reverse('catalog_i18n:service_detail', kwargs={
                        'category_slug': self.category.slug,
                        'service_slug': self.service.slug,
                    }), HTTP_ACCEPT_LANGUAGE=lang,
                )
                for response in (listing, section, category, service):
                    self.assertEqual(response.status_code, 200)
                    self.assertContains(response, category_name)
                    self.assertContains(response, 'public-pages.css')
                self.assertContains(
                    category, reverse('marketplace:worker_public_profile',
                                      args=[self.worker.pk])
                )
                self.assertContains(service, f'?service={self.service.pk}')
                self.assertContains(service, 'noindex,follow')

    def test_public_cities_and_profiles_stay_ashdod_only(self):
        listing = self.client.get(reverse('marketplace:cities_list'))
        self.assertEqual(listing.status_code, 200)
        self.assertContains(listing, 'Сейчас ZemiPro работает только в Ашдоде.')
        self.assertContains(listing, 'Ашдод')
        self.assertNotContains(listing, 'Ашкелон')
        self.assertEqual(
            self.client.get(reverse('marketplace:city_detail',
                                    args=[self.other_city.slug])).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(reverse('marketplace:worker_public_profile',
                                    args=[self.off_worker.pk])).status_code,
            404,
        )

    def test_category_and_city_get_filters_preserve_page_and_access(self):
        category_url = reverse(
            'marketplace:category_detail', args=[self.category.slug],
        )
        matched = self.client.get(category_url, {'city': 'ashdod'})
        self.assertEqual(matched.status_code, 200)
        self.assertContains(matched, 'id="category-city-filter"')
        self.assertContains(matched, 'Clear Home Plumber')
        self.assertContains(matched, 'name="city"')
        self.assertNotContains(matched, 'Outside Pilot Worker')
        invalid = self.client.get(category_url, {'city': 'ashkelon'})
        self.assertEqual(invalid.status_code, 200)
        self.assertContains(invalid, 'ui-empty-state')
        self.assertNotContains(invalid, 'Clear Home Plumber')
        city = self.client.get(
            reverse('marketplace:city_detail', args=[self.ashdod.slug]),
            {'category': self.category.slug},
        )
        self.assertContains(city, 'id="city-category-filter"')
        self.assertContains(city, 'Clear Home Plumber')
        self.assertNotContains(city, 'Outside Pilot Worker')

    def test_directory_sort_and_advanced_fields_work_without_javascript(self):
        url = reverse('marketplace:worker_directory')
        response = self.client.get(url, {'sort': 'price_asc'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<details class="public-search-form__extra"')
        self.assertContains(response, 'name="sort"')
        self.assertContains(response, 'value="price_asc"')
        self.assertContains(response, 'Clear Home Plumber')
        self.assertContains(response, '190')
        self.assertNotContains(response, '0503456789')
        self.assertNotContains(response, 'Outside Pilot Worker')
        self.assertContains(response, 'Сбросить фильтры')
        by_service = self.client.get(url, {'service': self.service.pk})
        self.assertContains(by_service, 'Clear Home Plumber')
        bad = self.client.get(url, {'price_from': '900', 'price_to': '100'})
        self.assertEqual(bad.status_code, 200)
        self.assertContains(bad, 'role="alert"')
        self.assertContains(bad, 'ui-empty-state')
        self.assertNotContains(bad, 'Clear Home Plumber')

    def test_public_profile_actions_remain_private_and_server_owned(self):
        url = reverse('marketplace:worker_public_profile', args=[self.worker.pk])
        guest = self.client.get(url)
        self.assertEqual(guest.status_code, 200)
        self.assertContains(guest, 'Clear Home Plumber')
        self.assertContains(guest, 'public-profile__overview')
        self.assertContains(guest, 'Примеры работ')
        self.assertContains(guest, 'Отзывы')
        self.assertContains(guest, 'noindex,follow')
        self.assertContains(
            guest, reverse('marketplace:worker_invitation_select',
                           args=[self.worker.pk])
        )
        self.assertContains(guest, '?worker=' + str(self.worker.pk))
        self.assertNotContains(guest, '0503456789')
        self.assertNotContains(guest, 'public083worker')
        self.assertNotContains(guest, 'action="add"')
        client_user = make_user('public083customer')
        self.client.force_login(client_user)
        authenticated = self.client.get(url)
        self.assertContains(authenticated, 'name="action" value="add"')
        self.assertContains(authenticated, 'Пожаловаться на пользователя')
        self.client.force_login(self.worker_user)
        own = self.client.get(url)
        self.assertNotContains(own, 'name="action" value="add"')
        self.assertNotContains(own, '?worker=' + str(self.worker.pk))
