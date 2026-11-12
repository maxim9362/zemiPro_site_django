"""Stage 02.6 integration tests on disposable PostgreSQL only."""
from copy import deepcopy
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.urls import reverse
from django.utils.translation import override

from apps.locations.models import City, CityAlias, District
from apps.marketplace.models import (
    Category, Order, OrderQuestionnaireAnswer, QuestionnaireVersion,
    ServiceQuestionnaire, ServiceSection, Subcategory,
)
from apps.marketplace.tests.factories import make_user


def seed(*args):
    call_command(*args, stdout=StringIO())


class Stage02IntegratedAcceptanceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        seed('seed_service_catalog')
        seed('seed_israel_cities')
        seed('seed_demo_questionnaires', '--publish')
        cls.owner = make_user('stage02-integration-owner')
        cls.other = make_user('stage02-integration-other')

    def test_three_seed_manifests_link_and_publish_expected_count(self):
        self.assertEqual(
            (ServiceSection.objects.count(), Category.objects.count(),
             Subcategory.objects.count()), (12, 19, 88),
        )
        self.assertEqual(
            (District.objects.count(), City.objects.count(),
             CityAlias.objects.count()), (6, 25, 4),
        )
        self.assertEqual(
            (ServiceQuestionnaire.objects.count(),
             QuestionnaireVersion.objects.count()), (4, 4),
        )
        for questionnaire in ServiceQuestionnaire.objects.select_related(
            'service', 'published_version',
        ):
            self.assertIsNotNone(questionnaire.published_version_id)
            self.assertEqual(
                questionnaire.published_version.questionnaire_id, questionnaire.pk,
            )
            self.assertEqual(questionnaire.published_version.number, 1)

    def test_seed_round_trip_keeps_order_ids_admin_text_and_answer_snapshot(self):
        category = Category.objects.get(slug='plumbing')
        service = Subcategory.objects.get(category=category, slug='leak-repair')
        city = City.objects.get(slug='ashdod')
        version = ServiceQuestionnaire.objects.get(service=service).published_version
        self.client.force_login(self.owner)
        result = self.client.post(reverse('marketplace:order_create'), {
            'customer_name': 'Synthetic Stage 02 Customer',
            'customer_phone': '0501234567',
            'category': str(category.pk),
            'subcategory': str(service.pk),
            'city': str(city.pk),
            'address': 'STAGE02_PRIVATE_ADDRESS',
            'description': 'Synthetic fixture request for a pipe leak in the kitchen.',
            'price': '',
            'questionnaire_version': str(version.pk),
            'q_issue': 'pipe',
            'q_urgent': 'true',
            'q_access': 'STAGE02_PRIVATE_ANSWER',
        }, HTTP_ACCEPT_LANGUAGE='he')
        self.assertEqual(result.status_code, 302)
        order = Order.objects.get(client=self.owner)
        answer = OrderQuestionnaireAnswer.objects.get(order=order)
        initial_schema = deepcopy(answer.schema_snapshot)
        before_ids = {
            'sections': list(ServiceSection.objects.order_by('slug').values_list('slug', 'pk')),
            'categories': list(Category.objects.order_by('slug').values_list('slug', 'pk')),
            'services': list(Subcategory.objects.order_by('category_id', 'slug').values_list(
                'category_id', 'slug', 'pk',
            )),
            'cities': list(City.objects.order_by('slug').values_list('slug', 'pk')),
            'versions': list(QuestionnaireVersion.objects.order_by('pk').values_list('pk', flat=True)),
        }
        category.name_en = 'Admin edited plumbing label'
        category.save(update_fields=['name_en'])
        city.name_he = 'עיר בעריכת מנהל'
        city.save(update_fields=['name_he'])

        seed('seed_service_catalog')
        seed('seed_service_catalog', '--check')
        seed('seed_israel_cities')
        seed('seed_israel_cities', '--check')
        seed('seed_demo_questionnaires', '--publish')
        seed('seed_demo_questionnaires', '--check')

        actual_ids = {
            'sections': list(ServiceSection.objects.order_by('slug').values_list('slug', 'pk')),
            'categories': list(Category.objects.order_by('slug').values_list('slug', 'pk')),
            'services': list(Subcategory.objects.order_by('category_id', 'slug').values_list(
                'category_id', 'slug', 'pk',
            )),
            'cities': list(City.objects.order_by('slug').values_list('slug', 'pk')),
            'versions': list(QuestionnaireVersion.objects.order_by('pk').values_list('pk', flat=True)),
        }
        self.assertEqual(before_ids, actual_ids)
        category.refresh_from_db()
        city.refresh_from_db()
        order.refresh_from_db()
        answer.refresh_from_db()
        self.assertEqual(category.name_en, 'Admin edited plumbing label')
        self.assertEqual(city.name_he, 'עיר בעריכת מנהל')
        self.assertEqual(
            (order.pk, order.category_id, order.subcategory_id, order.city_id, answer.version_id),
            (answer.order_id, category.pk, service.pk, city.pk, version.pk),
        )
        self.assertEqual(answer.schema_snapshot, initial_schema)
        self.assertEqual(answer.answers['access'], 'STAGE02_PRIVATE_ANSWER')
        self.assertEqual(order.price, 'Договорная')

        self.client.force_login(self.other)
        public = self.client.get(
            reverse('marketplace:order_detail', args=[order.pk]),
            HTTP_ACCEPT_LANGUAGE='en',
        )
        self.assertEqual(public.status_code, 200)
        self.assertNotContains(public, 'STAGE02_PRIVATE_ADDRESS')
        self.assertNotContains(public, 'STAGE02_PRIVATE_ANSWER')

    def test_three_languages_keep_menu_forms_paths_and_entity_identity(self):
        category = Category.objects.get(slug='plumbing')
        service = Subcategory.objects.get(category=category, slug='leak-repair')
        city = City.objects.get(slug='ashdod')
        for language, direction in (('ru', 'ltr'), ('en', 'ltr'), ('he', 'rtl')):
            with self.subTest(language=language), override(language):
                urls = [
                    reverse('catalog_i18n:categories_list'),
                    reverse('catalog_i18n:cities_list'),
                    reverse('catalog_i18n:category_detail', args=[category.slug]),
                    reverse('catalog_i18n:service_detail', kwargs={
                        'category_slug': category.slug, 'service_slug': service.slug,
                    }),
                    reverse('catalog_i18n:city_detail', args=[city.slug]),
                    reverse('accounts:register'),
                ]
                for url in urls:
                    response = self.client.get(url, HTTP_ACCEPT_LANGUAGE=language)
                    self.assertEqual(response.status_code, 200, url)
                    self.assertContains(
                        response, f'<html lang="{language}" dir="{direction}">',
                    )
                    self.assertContains(response, 'id="language-choice"')
                response = self.client.get(urls[2], HTTP_ACCEPT_LANGUAGE=language)
                self.assertEqual(response.context['category'].pk, category.pk)
                response = self.client.get(urls[3], HTTP_ACCEPT_LANGUAGE=language)
                self.assertEqual(response.context['service'].pk, service.pk)
                self.assertContains(response, f'hreflang="{language}"')
                response = self.client.get(urls[4], HTTP_ACCEPT_LANGUAGE=language)
                self.assertEqual(response.context['city'].pk, city.pk)

        switched = self.client.post(reverse('set_language'), {
            'language': 'en',
            'next': '/he/categories/plumbing/?city=ashdod&page=2',
        })
        self.assertEqual(switched.status_code, 302)
        self.assertEqual(
            switched['Location'], '/en/categories/plumbing/?city=ashdod&page=2',
        )

    def test_invalid_catalog_and_city_alias_collision_cannot_write(self):
        from apps.locations.management.commands import seed_israel_cities as geo
        from apps.marketplace.management.commands import seed_service_catalog as catalog

        before = (
            ServiceSection.objects.count(), Category.objects.count(),
            Subcategory.objects.count(), District.objects.count(),
            City.objects.count(), CityAlias.objects.count(),
        )
        with patch.object(catalog, 'NEW_CATEGORIES', [
            *catalog.NEW_CATEGORIES, catalog.NEW_CATEGORIES[0],
        ]):
            with self.assertRaises(CommandError):
                seed('seed_service_catalog')
        with patch.object(geo, 'ALIASES', [*geo.ALIASES, ('ashdod', 'ashdod')]):
            with self.assertRaises(CommandError):
                seed('seed_israel_cities')
        self.assertEqual(before, (
            ServiceSection.objects.count(), Category.objects.count(),
            Subcategory.objects.count(), District.objects.count(),
            City.objects.count(), CityAlias.objects.count(),
        ))
