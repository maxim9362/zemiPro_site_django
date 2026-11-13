"""ZP-05-004: Unicode and contact-URL negative regressions on synthetic data.

A successful Django suite must catch disclosure via profile, SEO, invitation,
client dashboard AND keyword oracle, not just direct HTML redaction.
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
    contact_shaped_query,
    contains_public_contact,
    normalize_public_text,
    redact_public_contact,
    searchable_public_text,
)
from apps.accounts.services import publication_issue, set_worker_publication
from apps.locations.models import City
from apps.marketplace.models import Category, OrderInvitation, Subcategory
from apps.marketplace.tests.factories import make_order, make_user


@override_settings(ZEMIPRO_PILOT_CITY_SLUG='ashdod')
class UnicodeContactPrivacyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.city = City.objects.create(
            slug='ashdod', name_ru='Ашдод',
            name_en='Ashdod', name_he='אשדוד',
        )
        cls.category = Category.objects.create(
            slug='stage05-unicode-repair', name_ru='Ремонт',
            name_en='Repair', name_he='תיקונים', work_mode='onsite',
        )
        cls.service = Subcategory.objects.create(
            category=cls.category, slug='stage05-unicode-pipe',
            name_ru='Трубы', name_en='Pipes',
            name_he='צינורות', work_mode='onsite',
        )
        cls.client_user = make_user('stage05-unicode-client')
        ClientProfile.objects.create(user=cls.client_user, city=cls.city)
        cls.worker_user = make_user('stage05-unicode-worker')
        cls.worker = WorkerProfile.objects.create(
            user=cls.worker_user, city=cls.city, is_published=True,
            display_name='Service ＠widehandle 050–7654321',
            description=(
                'Synthetic repair service. Contact '
                't.me/contacthandle or 050\u200f-7654321.'
            ),
            contact='PRIVATE_UNICODE_CONTACT',
            pricing_details='Quote after consultation',
            spoken_languages=['ru', 'en', 'he'],
        )
        cls.worker.skills.add(cls.category)
        cls.worker.services.add(cls.service)
        cls.order = make_order(
            client=cls.client_user, category=cls.category,
            subcategory=cls.service, city=cls.city,
            work_mode='onsite', address='PRIVATE_UNICODE_ORDER_ADDRESS',
            customer_phone='PRIVATE_UNICODE_ORDER_PHONE',
        )

    def assert_no_contacts(self, response):
        for leaked in (
            'widehandle', 'contacthandle', '050–7654321',
            '050-7654321', '050/7654321', 't.me/',
            'PRIVATE_UNICODE_CONTACT',
        ):
            self.assertNotContains(response, leaked)

    def test_v3_policy_catches_unicode_bidi_urls_and_obfuscated_email(self):
        cases = {
            'Service ＠widehandle 050–7654321': '[…]',
            'Contact t.me/contacthandle or 050\u200f-7654321.': '[…]',
            'Call 050‑7654321': '[…]',
            'Call 050·7654321': '[…]',
            'Call 050\n7654321': '[…]',
            'Find instagram.com/handle': '[…]',
            'Find https://t.me/handle': '[…]',
            'name [at] example [dot] com': '[…]',
            'name%40example.com': '[…]',
            'name＠example.com': '[…]',
        }
        for source, expected in cases.items():
            with self.subTest(source=source):
                self.assertEqual(redact_public_contact(source), expected)
                self.assertTrue(contains_public_contact(source))
                rendered = searchable_public_text(source)
                for fragment in (
                    'widehandle', 'contacthandle', '7654321',
                    'example', 'instagram.com',
                ):
                    self.assertNotIn(fragment, rendered)
        self.assertEqual(normalize_public_text('050\u200f–7654321'), '050-7654321')

    def test_explicit_contact_queries_fail_closed_but_public_words_work(self):
        for query in (
            '＠widehandle', 't.me/contacthandle',
            'https://instagram.com/handle', '050–7654321',
            '050\u200f-7654321', '050‑7654321',
            '050·7654321', '050\n7654321',
            'name [at] example [dot] com',
        ):
            with self.subTest(query=query):
                self.assertTrue(contact_shaped_query(query))
        for query in ('Service', 'Synthetic', 'Pipe repair version 2.0'):
            self.assertFalse(contact_shaped_query(query))

    def test_localized_full_and_suffix_keyword_oracle_is_closed(self):
        for lang in ('ru', 'en', 'he'):
            with override(lang):
                url = reverse('catalog_i18n:worker_directory')
                for query in (
                    'widehandle', 'contacthandle', '6543', '7654321',
                    '＠widehandle', 't.me/contacthandle',
                    '050–7654321', '050/7654321',
                    'name [at] example [dot] com',
                ):
                    with self.subTest(lang=lang, query=query):
                        r = self.client.get(url, {'q': query}, HTTP_ACCEPT_LANGUAGE=lang)
                        self.assertEqual(r.status_code, 200)
                        self.assertEqual(r.context['page_obj'].paginator.count, 0)
                        # User-typed GET text may be echoed in a form. The
                        # result set is the oracle that must remain empty.
                for word, expected in (
                    ('Service', 0), ('Synthetic', 0), ('Ремонт', 1),
                ):
                    with self.subTest(lang=lang, public_word=word):
                        r = self.client.get(url, {'q': word}, HTTP_ACCEPT_LANGUAGE=lang)
                        self.assertEqual(r.status_code, 200)
                        rows = list(r.context['page_obj'].object_list)
                        self.assertEqual(len(rows), expected)
                        if expected:
                            self.assertEqual(rows[0].pk, self.worker.pk)
                        self.assert_no_contacts(r)

    def test_profile_title_meta_h1_are_safe_in_all_three_languages(self):
        path = reverse('marketplace:worker_public_profile', args=[self.worker.pk])
        for lang in ('ru', 'en', 'he'):
            with override(lang):
                r = self.client.get(path, HTTP_ACCEPT_LANGUAGE=lang)
                self.assertEqual(r.status_code, 200)
                self.assertContains(r, '<title>')
                self.assertContains(r, 'name="description"')
                self.assertContains(r, '<h1>')
                self.assert_no_contacts(r)

    def test_invitation_picker_and_client_dashboard_are_contact_free(self):
        self.client.force_login(self.client_user)
        invite = reverse('marketplace:worker_invitation_select', args=[self.worker.pk])
        for lang in ('ru', 'en', 'he'):
            with override(lang):
                r = self.client.get(invite, HTTP_ACCEPT_LANGUAGE=lang)
                self.assertEqual(r.status_code, 200)
                self.assert_no_contacts(r)
        self.assertEqual(
            self.client.post(invite, {'order_id': self.order.pk}).status_code, 302,
        )
        self.assertEqual(OrderInvitation.objects.count(), 1)
        for lang in ('ru', 'en', 'he'):
            with override(lang):
                page = self.client.get(
                    reverse('marketplace:client_dashboard'),
                    HTTP_ACCEPT_LANGUAGE=lang,
                )
                self.assertEqual(page.status_code, 200)
                self.assert_no_contacts(page)

    def test_form_rejects_each_public_field_using_same_policy(self):
        good = {
            'display_name': 'Synthetic Repair Company',
            'city': self.city.pk,
            'description': 'Synthetic description of repair services.',
            'pricing_details': 'Price on request',
            'working_hours': 'Weekdays',
            'skills': [self.category.pk],
            'services': [self.service.pk],
            'spoken_languages': ['ru'],
        }
        cases = (
            ('display_name', 'Service ＠widehandle'),
            ('description', 'Repair services. Contact t.me/contacthandle.'),
            ('description', 'Repair services. Phone 050\u200f-7654321.'),
            ('pricing_details', 'Quote from instagram.com/handle'),
            ('working_hours', 'Phone 050‑7654321'),
            ('description', 'Contact name [at] example [dot] com'),
        )
        for field, bad_text in cases:
            with self.subTest(field=field, value=bad_text):
                form = WorkerProfileForm(
                    data={**good, field: bad_text}, instance=self.worker,
                )
                self.assertFalse(form.is_valid())
                self.assertIn(field, form.errors)
                self.worker.refresh_from_db()

    def test_direct_service_publication_denies_unicode_contacts(self):
        defaults = {
            'display_name': 'Synthetic Repair Company',
            'description': 'Synthetic description of repair services.',
            'pricing_details': 'Price on request',
            'working_hours': 'Weekdays',
        }
        cases = (
            ('display_name', 'Service ＠widehandle'),
            ('description', 'Repair services. Contact t.me/contacthandle.'),
            ('description', 'Repair services. Phone 050\u200f-7654321.'),
            ('pricing_details', 'Quote from instagram.com/handle'),
            ('working_hours', 'Phone 050·7654321'),
            ('description', 'Contact name [at] example [dot] com'),
        )
        for field, bad_text in cases:
            with self.subTest(field=field, value=bad_text):
                changed = {**defaults, field: bad_text}
                WorkerProfile.objects.filter(pk=self.worker.pk).update(**changed)
                self.worker.refresh_from_db()
                self.assertIsNotNone(publication_issue(self.worker))
                with self.assertRaises(ValueError):
                    set_worker_publication(self.worker_user, True)

    def test_0017_forward_backfill_scrubs_legacy_without_mutating_raw_data(self):
        WorkerProfile.objects.filter(pk=self.worker.pk).update(
            searchable_display_name='Service ＠widehandle 050–7654321',
            searchable_description=(
                'Synthetic repair service. Contact '
                't.me/contacthandle or 050\u200f-7654321.'
            ),
        )
        original_name = self.worker.display_name
        original_description = self.worker.description
        original_worker_id = self.worker.pk
        original_order_id = self.order.pk
        migration = import_module('apps.accounts.migrations.0017_unicode_contact_scrub')
        migration.rescrub_public_search(apps, SimpleNamespace(connection=connection))
        self.worker.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(self.worker.display_name, original_name)
        self.assertEqual(self.worker.description, original_description)
        self.assertEqual(self.worker.pk, original_worker_id)
        self.assertEqual(self.order.pk, original_order_id)
        self.assertEqual(self.worker.searchable_display_name, 'Service')
        self.assertEqual(
            self.worker.searchable_description,
            'Synthetic repair service. Contact or .',
        )

    def test_subsequent_save_and_update_fields_synchronize_safe_search(self):
        self.worker.display_name = 'New ＠freshhandle and 050–7654321'
        self.worker.save(update_fields=['display_name'])
        self.worker.description = 'Repair services t.me/contacthandle and 050\u200f-7654321.'
        self.worker.save(update_fields=['description'])
        self.worker.refresh_from_db()
        self.assertEqual(self.worker.searchable_display_name, '')
        self.assertEqual(self.worker.searchable_description, '')
        self.assertNotIn('contacthandle', self.worker.searchable_description)
        self.assertNotIn('freshhandle', self.worker.searchable_display_name)

    def test_safe_text_and_nfkc_length_do_not_break_search(self):
        safe = 'Pipe repair version 2.0 available in Ashdod'
        self.assertEqual(searchable_public_text(safe), safe)
        self.assertFalse(contains_public_contact(safe))
        self.worker.display_name = 'ﬃ' * 120
        self.worker.save(update_fields=['display_name'])
        self.worker.refresh_from_db()
        self.assertEqual(len(self.worker.searchable_display_name), 120)
