"""ZP-05-005 HIGH: Unicode punctuation, arbitrary messenger URI and IDN leakage.

Synthetic-only end-to-end probes for public profile, SEO, invite, search,
photo captions, migration and direct owner services in RU/EN/HE.
"""
from importlib import import_module
from types import SimpleNamespace

from django.apps import apps
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import override

from apps.accounts.forms import (
    PortfolioEditForm, PortfolioUploadForm, WorkerProfileForm,
)
from apps.accounts.models import (
    ClientProfile, WorkerPortfolioPhoto, WorkerProfile,
)
from apps.accounts.portfolio import (
    PortfolioError, add_own_portfolio_photo, update_own_portfolio_photo,
)
from apps.accounts.public_text import (
    contact_shaped_query, contains_public_contact,
    normalize_public_text, redact_public_contact, searchable_public_text,
)
from apps.accounts.services import publication_issue, set_worker_publication
from apps.locations.models import City
from apps.marketplace.models import Category, OrderInvitation, Subcategory
from apps.marketplace.tests.factories import make_order, make_user


@override_settings(ZEMIPRO_PILOT_CITY_SLUG='ashdod')
class ContactPolicyV4Tests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.city = City.objects.create(
            slug='ashdod', name_ru='Ашдод',
            name_en='Ashdod', name_he='אשדוד',
        )
        cls.category = Category.objects.create(
            slug='v4-plumbing', name_ru='Ремонт',
            name_en='Repair', name_he='תיקונים', work_mode='onsite',
        )
        cls.service = Subcategory.objects.create(
            category=cls.category, slug='v4-pipes',
            name_ru='Трубы', name_en='Pipes',
            name_he='צינורות', work_mode='onsite',
        )
        cls.client_user = make_user('v4-client')
        ClientProfile.objects.create(user=cls.client_user, city=cls.city)
        cls.worker_user = make_user('v4-specialist')
        # Pre-existing legacy profile, not a new publication through the form.
        cls.worker = WorkerProfile.objects.create(
            user=cls.worker_user, city=cls.city, is_published=True,
            display_name='Service 050־7654321',
            description='Contact tg://resolve?domain=contacthandle or t[.]me/otherhandle.',
            pricing_details='Quote by 050,7654321',
            working_hours='Portfolio example.ישראל/contactid',
            spoken_languages=['ru', 'en', 'he'],
        )
        cls.worker.skills.add(cls.category)
        cls.worker.services.add(cls.service)
        cls.photo = WorkerPortfolioPhoto.objects.create(
            worker=cls.worker,
            file_key='worker-portfolio/' + 'b' * 32 + '.jpg',
            caption='Caption 050:7654321 and @ handlecaption',
            is_public=True, rights_confirmed_at=timezone.now(),
        )
        cls.order = make_order(
            client=cls.client_user, category=cls.category,
            subcategory=cls.service, city=cls.city,
            work_mode='onsite',
            address='PRIVATE_V4_ORDER_ADDRESS',
            customer_phone='PRIVATE_V4_ORDER_PHONE',
        )

    def assert_no_contact_fragments(self, response):
        for secret in (
            '050־7654321', '050-7654321', '050,7654321',
            '050:7654321', '050/7654321',
            'contacthandle', 'otherhandle', 'handlecaption',
            'contactid', 'tg://', 't[.]me', 'example.ישראל',
        ):
            self.assertNotContains(response, secret)

    def test_unicode_uri_idn_phone_obfuscation_policy(self):
        examples = (
            '050־7654321',
            '050,7654321',
            '050:7654321',
            '050%25252F7654321',
            '050\u200f-7654321',
            '050‑7654321',
            '050·7654321',
            '050\n7654321',
            '@ contacthandle',
            'tg://resolve?domain=contacthandle',
            't[.]me/otherhandle',
            'instagram.com/contacthandle',
            'example.ישראל/contactid',
            'john!doe@example.com',
            'name [at] example [dot] com',
        )
        for case in examples:
            with self.subTest(case=case):
                self.assertTrue(contains_public_contact(case))
                self.assertEqual(searchable_public_text(case), '')
                self.assertEqual(redact_public_contact(case), '[…]')
        self.assertEqual(normalize_public_text('050־7654321'), '050-7654321')
        self.assertEqual(normalize_public_text('050%25252F7654321'), '050/7654321')

    def test_plain_legal_service_text_is_not_rejected(self):
        safe = (
            'Pipe repair version 2.0 available in Ashdod, weekdays by appointment'
        )
        self.assertEqual(searchable_public_text(safe), safe)
        self.assertFalse(contains_public_contact(safe))
        for word in ('Repair', 'Synthetic', 'Pipe repair version 2.0'):
            self.assertFalse(contact_shaped_query(word))
        for query in (
            '050־7654321', '050,7654321', '050:7654321',
            '050%25252F7654321', 'tg://resolve?domain=contacthandle',
            't[.]me/otherhandle', '@ contacthandle',
        ):
            self.assertTrue(contact_shaped_query(query), query)

    def test_ru_en_he_search_does_not_reveal_full_or_partial_contacts(self):
        probes = (
            '6543', '7654321', 'contacthandle', 'otherhandle', 'contactid',
            'handlecaption', '050־7654321', '050%25252F7654321',
            'tg://resolve?domain=contacthandle',
        )
        for lang in ('ru', 'en', 'he'):
            with override(lang):
                url = reverse('catalog_i18n:worker_directory')
                for query in probes:
                    with self.subTest(lang=lang, query=query):
                        response = self.client.get(url, {'q': query})
                        self.assertEqual(response.status_code, 200)
                        self.assertEqual(response.context['page_obj'].paginator.count, 0)
                for query in ('Service', 'Contact', 'Ремонт'):
                    with self.subTest(lang=lang, public_query=query):
                        response = self.client.get(url, {'q': query})
                        self.assertEqual(response.status_code, 200)
                        self.assertEqual(response.context['page_obj'].paginator.count, 1)
                        self.assert_no_contact_fragments(response)

    def test_public_html_seo_photocaption_picker_and_dashboard_are_safe(self):
        url = reverse('marketplace:worker_public_profile', args=[self.worker.pk])
        for lang in ('ru', 'en', 'he'):
            with override(lang):
                r = self.client.get(url, HTTP_ACCEPT_LANGUAGE=lang)
                self.assertEqual(r.status_code, 200)
                self.assertContains(r, '<title>')
                self.assertContains(r, 'name="description"')
                self.assertContains(r, 'Caption')
                self.assert_no_contact_fragments(r)

        self.client.force_login(self.client_user)
        invite_url = reverse('marketplace:worker_invitation_select', args=[self.worker.pk])
        for lang in ('ru', 'en', 'he'):
            with override(lang):
                picker = self.client.get(invite_url, HTTP_ACCEPT_LANGUAGE=lang)
                self.assertEqual(picker.status_code, 200)
                self.assert_no_contact_fragments(picker)
        self.assertEqual(
            self.client.post(invite_url, {'order_id': self.order.pk}).status_code,
            302,
        )
        self.assertEqual(OrderInvitation.objects.count(), 1)
        for lang in ('ru', 'en', 'he'):
            with override(lang):
                dashboard = self.client.get(
                    reverse('marketplace:client_dashboard'),
                    HTTP_ACCEPT_LANGUAGE=lang,
                )
                self.assertEqual(dashboard.status_code, 200)
                self.assert_no_contact_fragments(dashboard)

    def test_worker_form_and_direct_publication_both_reject(self):
        baseline = {
            'display_name': 'Safe Plumbing Company',
            'city': self.city.pk,
            'description': 'Synthetic public plumbing repair service.',
            'pricing_details': 'Quote after consultation',
            'working_hours': 'Weekdays',
            'skills': [self.category.pk],
            'services': [self.service.pk],
            'spoken_languages': ['ru'],
        }
        cases = (
            ('display_name', 'Service 050־7654321'),
            ('description', 'Contact tg://resolve?domain=contacthandle.'),
            ('description', 'Contact t[.]me/otherhandle.'),
            ('pricing_details', 'Quote by 050,7654321'),
            ('working_hours', 'Portfolio example.ישראל/contactid'),
            ('description', 'Contact john!doe@example.com.'),
        )
        for field, bad in cases:
            with self.subTest(field=field, bad=bad):
                form = WorkerProfileForm(
                    data={**baseline, field: bad}, instance=self.worker,
                )
                self.assertFalse(form.is_valid())
                self.assertIn(field, form.errors)
                self.worker.refresh_from_db()
                update = {
                    'display_name': baseline['display_name'],
                    'description': baseline['description'],
                    'pricing_details': baseline['pricing_details'],
                    'working_hours': baseline['working_hours'],
                }
                update[field] = bad
                WorkerProfile.objects.filter(pk=self.worker.pk).update(**update)
                self.worker.refresh_from_db()
                self.assertIsNotNone(publication_issue(self.worker))
                with self.assertRaises(ValueError):
                    set_worker_publication(self.worker_user, True)

    def test_portfolio_upload_and_edit_forms_reject_captions(self):
        for caption in (
            'Caption 050:7654321 and @ handlecaption',
            'Look at tg://resolve?domain=contacthandle',
            'Example example.ישראל/contactid',
        ):
            with self.subTest(caption=caption):
                upload = PortfolioUploadForm(data={
                    'caption': caption, 'rights_confirmed': 'on',
                }, files={
                    'image': SimpleUploadedFile('example.png', b'not needed for this check'),
                })
                self.assertFalse(upload.is_valid())
                self.assertIn('caption', upload.errors)
                edit = PortfolioEditForm(data={
                    'caption': caption, 'sort_order': 0, 'is_public': 'on',
                })
                self.assertFalse(edit.is_valid())
                self.assertIn('caption', edit.errors)

    def test_portfolio_direct_services_reject_captions_and_keep_old_row(self):
        for caption in (
            'Caption 050:7654321 and @ handlecaption',
            'New photo tg://resolve?domain=contacthandle',
        ):
            with self.subTest(caption=caption):
                with self.assertRaises(PortfolioError):
                    add_own_portfolio_photo(
                        self.worker_user, None,
                        caption=caption, rights_confirmed=True, is_public=True,
                    )
                with self.assertRaises(PortfolioError):
                    update_own_portfolio_photo(
                        self.worker_user, self.photo.pk,
                        caption=caption, sort_order=1, is_public=True,
                    )
                self.photo.refresh_from_db()
                self.assertEqual(
                    self.photo.caption,
                    'Caption 050:7654321 and @ handlecaption',
                )

    def test_0018_forward_data_migration_scrubs_legacy_index(self):
        originals = (self.worker.pk, self.worker.user_id, self.order.pk,
                     self.worker.display_name, self.worker.description)
        WorkerProfile.objects.filter(pk=self.worker.pk).update(
            searchable_display_name='Service 050־7654321',
            searchable_description=(
                'Contact tg://resolve?domain=contacthandle or t[.]me/otherhandle.'
            ),
        )
        migration = import_module('apps.accounts.migrations.0018_strict_contact_rescrub')
        migration.rescrub_public_search(apps, SimpleNamespace(connection=connection))
        self.worker.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(
            (self.worker.pk, self.worker.user_id, self.order.pk,
             self.worker.display_name, self.worker.description),
            originals,
        )
        self.assertEqual(self.worker.searchable_display_name, 'Service')
        self.assertEqual(self.worker.searchable_description, 'Contact or')

    def test_model_save_reindexes_with_bounded_normalized_copy(self):
        self.worker.display_name = 'ﬃ' * 120
        self.worker.save(update_fields=['display_name'])
        self.worker.description = 'Repair 050:7654321 t[.]me/otherhandle'
        self.worker.save(update_fields=['description'])
        self.worker.refresh_from_db()
        self.assertEqual(len(self.worker.searchable_display_name), 120)
        self.assertEqual(self.worker.searchable_description, 'Repair')
        self.assertNotIn('7654321', self.worker.searchable_description)
