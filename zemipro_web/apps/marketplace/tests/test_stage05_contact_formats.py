"""Reviewer ZP-05-003 HIGH: bare handles and slash-separated phone privacy.

All values are invented; no production data or outbound messages are used.
"""
from importlib import import_module
from types import SimpleNamespace

from django.apps import apps
from django.db import connection
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.translation import override

from apps.accounts.forms import WorkerProfileForm
from apps.accounts.models import ClientProfile, WorkerProfile
from apps.accounts.public_text import (
    contact_shaped_query, contains_public_contact,
    redact_public_contact, searchable_public_text,
)
from apps.accounts.services import publication_issue, set_worker_publication
from apps.locations.models import City
from apps.marketplace.models import Category, OrderInvitation, Subcategory
from apps.marketplace.tests.factories import make_order, make_user


@override_settings(ZEMIPRO_PILOT_CITY_SLUG='ashdod')
class ContactFormatPrivacyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.city = City.objects.create(
            slug='ashdod', name_ru='Ашдод', name_en='Ashdod', name_he='אשדוד',
        )
        cls.category = Category.objects.create(
            slug='stage05-contact-category',
            name_ru='Ремонт', name_en='Repairs', name_he='תיקונים',
            work_mode='onsite',
        )
        cls.service = Subcategory.objects.create(
            category=cls.category, slug='stage05-contact-service',
            name_ru='Ремонт труб', name_en='Pipe repair', name_he='תיקון צנרת',
            work_mode='onsite',
        )
        cls.client_user = make_user('stage05-contact-client')
        ClientProfile.objects.create(user=cls.client_user, city=cls.city)
        cls.worker_user = make_user('stage05-contact-worker')
        cls.worker = WorkerProfile.objects.create(
            user=cls.worker_user, city=cls.city, is_published=True,
            display_name='Legacy @legacyhandle',
            description='Synthetic repair description. Contact @contacthandle or 050/7654321.',
            pricing_details='Pricing is agreed after the job.',
            spoken_languages=['ru', 'en', 'he'], availability='available',
        )
        cls.worker.skills.add(cls.category)
        cls.worker.services.add(cls.service)
        cls.order = make_order(
            client=cls.client_user, category=cls.category,
            subcategory=cls.service, city=cls.city, work_mode='onsite',
            address='NEVER_PUBLIC_ORDER_ADDRESS',
            customer_phone='NEVER_PUBLIC_ORDER_PHONE',
        )

    def assert_contact_absent(self, response):
        for marker in (
            '@legacyhandle', '@contacthandle',
            '050/7654321',
        ):
            self.assertNotContains(response, marker)

    def test_one_policy_makes_handle_and_slash_number_invisible_and_unsearchable(self):
        sample = 'Legacy @legacyhandle; Contact @contacthandle or 050/7654321.'
        self.assertEqual(
            redact_public_contact(sample),
            'Legacy […]; Contact […] or […].',
        )
        self.assertEqual(searchable_public_text(sample), 'Legacy ; Contact or .')
        self.assertTrue(contains_public_contact(sample))
        for fragment in ('legacyhandle', 'contacthandle', '6543', '7654321'):
            self.assertNotIn(fragment, searchable_public_text(sample))
        for query in ('@legacyhandle', '@contacthandle', '050/7654321'):
            self.assertTrue(contact_shaped_query(query))
        self.assertFalse(contact_shaped_query('repair'))
        self.assertEqual(searchable_public_text('Pipe repair Ashdod'), 'Pipe repair Ashdod')

    def test_all_locale_directory_queries_never_reveal_hidden_suffix_matches(self):
        for lang in ('ru', 'en', 'he'):
            with override(lang):
                url = reverse('catalog_i18n:worker_directory')
                for keyword in (
                    'contacthandle', 'legacyhandle', '6543', '7654321',
                    '@contacthandle', '050/7654321',
                ):
                    with self.subTest(lang=lang, q=keyword):
                        response = self.client.get(
                            url, {'q': keyword}, HTTP_ACCEPT_LANGUAGE=lang,
                        )
                        self.assertEqual(response.status_code, 200)
                        self.assertEqual(
                            response.context['page_obj'].paginator.count, 0,
                            'A hidden handle or phone fragment matched a public profile.',
                        )
                        self.assertNotContains(response, 'Legacy')
                        # A rejected form may echo the submitted value in its
                        # own field; that is not a lookup-derived privacy leak.
                        if '@' not in keyword and '/' not in keyword:
                            self.assert_contact_absent(response)

    def test_public_words_still_search_correctly_in_all_locales(self):
        for lang in ('ru', 'en', 'he'):
            with override(lang):
                url = reverse('catalog_i18n:worker_directory')
                for keyword in ('Legacy', 'Synthetic', 'Repair'):
                    with self.subTest(lang=lang, q=keyword):
                        response = self.client.get(
                            url, {'q': keyword}, HTTP_ACCEPT_LANGUAGE=lang,
                        )
                        self.assertEqual(response.status_code, 200)
                        self.assertEqual(
                            response.context['page_obj'].paginator.count, 1,
                        )
                        self.assert_contact_absent(response)

    def test_profile_seo_invitation_picker_and_client_dashboard_suppress_contacts(self):
        profile_url = reverse('marketplace:worker_public_profile', args=[self.worker.pk])
        for lang in ('ru', 'en', 'he'):
            with override(lang):
                profile = self.client.get(profile_url, HTTP_ACCEPT_LANGUAGE=lang)
                self.assertEqual(profile.status_code, 200)
                self.assertContains(profile, '<title>')
                self.assertContains(profile, 'name="description"')
                self.assertContains(profile, 'Legacy')
                self.assert_contact_absent(profile)

        self.client.force_login(self.client_user)
        picker_url = reverse('marketplace:worker_invitation_select', args=[self.worker.pk])
        picker = self.client.get(picker_url)
        self.assertEqual(picker.status_code, 200)
        self.assertContains(picker, 'Legacy')
        self.assert_contact_absent(picker)
        response = self.client.post(picker_url, {'order_id': self.order.pk})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(OrderInvitation.objects.count(), 1)
        for lang in ('ru', 'en', 'he'):
            with override(lang):
                dashboard = self.client.get(
                    reverse('marketplace:client_dashboard'),
                    HTTP_ACCEPT_LANGUAGE=lang,
                )
                self.assertEqual(dashboard.status_code, 200)
                self.assertContains(dashboard, 'Legacy')
                self.assert_contact_absent(dashboard)

    def test_worker_form_rejects_handles_and_slash_phones_in_each_public_field(self):
        good = {
            'display_name': 'Synthetic Service Company',
            'city': self.city.pk,
            'description': 'Synthetic repair service with published details.',
            'pricing_details': 'Negotiable',
            'working_hours': 'Weekdays on appointment',
            'spoken_languages': ['ru', 'he'],
            'skills': [self.category.pk],
            'services': [self.service.pk],
        }
        cases = (
            ('display_name', 'Repair @legacyhandle'),
            ('description', 'Repair tasks. Contact @contacthandle for details.'),
            ('pricing_details', 'Prices: 050/7654321'),
            ('working_hours', 'Office: 050/7654321'),
        )
        for field, value in cases:
            with self.subTest(field=field):
                form = WorkerProfileForm(
                    data={**good, field: value}, instance=self.worker,
                )
                self.assertFalse(form.is_valid())
                self.assertIn(field, form.errors)
                self.worker.refresh_from_db()

    def test_direct_publication_service_rejects_both_formats(self):
        for field, value in (
            ('display_name', 'Legacy @legacyhandle'),
            ('description', 'Synthetic repair. @contacthandle is my contact.'),
            ('description', 'Synthetic repair. Phone 050/7654321.'),
            ('pricing_details', 'Contact @contacthandle for a quote'),
            ('working_hours', 'Phone 050/7654321 during business hours'),
        ):
            with self.subTest(field=field, value=value):
                values = {
                    'display_name': 'Synthetic Company',
                    'description': 'Synthetic repair service in Ashdod.',
                    'pricing_details': 'Negotiable',
                    'working_hours': 'Weekdays',
                }
                values[field] = value
                WorkerProfile.objects.filter(pk=self.worker.pk).update(**values)
                self.worker.refresh_from_db()
                self.assertIsNotNone(publication_issue(self.worker))
                with self.assertRaises(ValueError):
                    set_worker_publication(self.worker_user, True)

    def test_0016_rescrubs_persisted_contact_copies_without_touching_order_or_profile(self):
        # Simulate real 0015-era search data that omitted two contact formats.
        WorkerProfile.objects.filter(pk=self.worker.pk).update(
            searchable_display_name='Legacy @legacyhandle',
            searchable_description=(
                'Synthetic repair description. Contact @contacthandle or 050/7654321.'
            ),
        )
        before_pk = self.worker.pk
        before_order_pk = self.order.pk
        before_user_pk = self.worker.user_id
        migrate = import_module('apps.accounts.migrations.0016_rescrub_contact_free_search')
        migrate.rescrub_public_search(apps, SimpleNamespace(connection=connection))
        self.worker.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(self.worker.pk, before_pk)
        self.assertEqual(self.worker.user_id, before_user_pk)
        self.assertEqual(self.order.pk, before_order_pk)
        self.assertEqual(
            self.worker.searchable_display_name,
            'Legacy',
        )
        self.assertEqual(
            self.worker.searchable_description,
            'Synthetic repair description. Contact or .',
        )
        self.assertEqual(
            self.worker.display_name, 'Legacy @legacyhandle',
        )
        self.assertIn('050/7654321', self.worker.description)

    def test_subsequent_save_and_update_fields_use_same_frozen_policy(self):
        self.worker.display_name = 'New @freshhandle'
        self.worker.save(update_fields=['display_name'])
        self.worker.description = 'Synthetic repairs 050/7654321 and @newhandle.'
        self.worker.save(update_fields=['description'])
        self.worker.refresh_from_db()
        self.assertEqual(self.worker.searchable_display_name, 'New')
        self.assertEqual(
            self.worker.searchable_description, 'Synthetic repairs and',
        )
        self.assertEqual(self.worker.public_display_name, 'New […]')

    def test_mixed_safe_words_and_non_contact_numbers_remain_searchable(self):
        safe = 'Pipe repair version 2.0 available in Ashdod'
        self.assertEqual(searchable_public_text(safe), safe)
        self.assertFalse(contains_public_contact(safe))
        self.assertNotIn('050/7654321', searchable_public_text(
            'Pipe repair call 050/7654321 for a quote',
        ))

