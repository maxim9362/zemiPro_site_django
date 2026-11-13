"""ZP-05-006/007: full contact concealment and search-oracle regressions.

Synthetic usernames, numbers and domains only. No production data.
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
class ContactPolicyV5Tests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.city = City.objects.create(
            slug='ashdod', name_ru='Ашдод',
            name_en='Ashdod', name_he='אשדוד',
        )
        cls.category = Category.objects.create(
            slug='v5-plumbing', name_ru='Ремонт',
            name_en='Repair', name_he='תיקונים', work_mode='onsite',
        )
        cls.service = Subcategory.objects.create(
            category=cls.category, slug='v5-pipes',
            name_ru='Трубы', name_en='Pipes', name_he='צינורות',
            work_mode='onsite',
        )
        cls.client_user = make_user('v5-test-client')
        ClientProfile.objects.create(user=cls.client_user, city=cls.city)
        cls.worker_user = make_user('v5-test-worker')
        # Historical public profile may contain data the current form rejects.
        cls.worker = WorkerProfile.objects.create(
            user=cls.worker_user, city=cls.city, is_published=True,
            display_name='Service 050------7654321',
            description='Call 050      7654321 or x://contacthandle. Contact john at example dot com.',
            pricing_details='Quotation in person',
            working_hours='Sunday–Thursday, 09:00–17:00',
            spoken_languages=['ru', 'en', 'he'],
        )
        cls.worker.skills.add(cls.category)
        cls.worker.services.add(cls.service)
        cls.photo = WorkerPortfolioPhoto.objects.create(
            worker=cls.worker,
            file_key='worker-portfolio/' + 'c' * 32 + '.jpg',
            caption='Edited x://editcontact 050------7654321',
            is_public=True, rights_confirmed_at=timezone.now(),
        )
        cls.order = make_order(
            client=cls.client_user, category=cls.category,
            subcategory=cls.service, city=cls.city,
            work_mode='onsite',
            address='PRIVATE_V5_ORDER_ADDRESS',
            customer_phone='PRIVATE_V5_ORDER_PHONE',
        )

    def assert_no_contact(self, response):
        for secret in (
            '050------7654321', '050      7654321', '050/7654321',
            'x://contacthandle', 'x://editcontact',
            'contacthandle', 'editcontact', 'john at example dot com',
            'john @ example.com', 'example.com',
        ):
            self.assertNotContains(response, secret)

    def test_all_independent_contact_vectors_redact_full_identifier(self):
        vectors = (
            '050------7654321',
            '050      7654321',
            'x://contacthandle',
            'Edited x://editcontact 050------7654321',
            '050%25252525252F7654321',
            'Contact john at example dot com',
            'Contact john @ example.com',
            'john!doe@example.com',
            '050־7654321',
            '050,7654321',
            'tg://resolve?domain=contacthandle',
            't[.]me/contacthandle',
        )
        for source in vectors:
            with self.subTest(source=source):
                self.assertTrue(contains_public_contact(source))
                output = searchable_public_text(source)
                self.assertNotIn('7654321', output)
                self.assertNotIn('contacthandle', output)
                self.assertNotIn('editcontact', output)
                self.assertNotIn('john', output)
                self.assertNotIn('example.com', output)
                self.assertIn('[…]', redact_public_contact(source))
        self.assertEqual(searchable_public_text('Contact john at example dot com'), 'Contact')
        self.assertEqual(searchable_public_text('Contact john @ example.com'), 'Contact')
        self.assertEqual(searchable_public_text('Call 050      7654321'), 'Call')
        self.assertEqual(normalize_public_text('050%25252525252F7654321'), '050/7654321')

    def test_contact_queries_rejected_and_normal_words_remain_searchable(self):
        for query in (
            '050------7654321', '050      7654321',
            '050%25252525252F7654321',
            'x://contacthandle', 'john at example dot com',
            'john @ example.com',
        ):
            with self.subTest(query=query):
                self.assertTrue(contact_shaped_query(query))
        for text in ('Service', 'Repair', 'Pipe repair version 2.0'):
            with self.subTest(text=text):
                self.assertFalse(contact_shaped_query(text))

    def test_no_full_or_partial_search_oracle_in_all_locales(self):
        probes = (
            '6543', '7654321', 'contacthandle', 'editcontact',
            'john', 'john at example dot com', 'john @ example.com',
            '050------7654321', 'x://contacthandle',
            '050%25252525252F7654321',
        )
        for lang in ('ru', 'en', 'he'):
            with override(lang):
                url = reverse('catalog_i18n:worker_directory')
                for query in probes:
                    with self.subTest(lang=lang, query=query):
                        result = self.client.get(
                            url, {'q': query}, HTTP_ACCEPT_LANGUAGE=lang,
                        )
                        self.assertEqual(result.status_code, 200)
                        self.assertEqual(result.context['page_obj'].paginator.count, 0)
                for word in ('Service', 'Call', 'Ремонт'):
                    with self.subTest(lang=lang, safe=word):
                        result = self.client.get(
                            url, {'q': word}, HTTP_ACCEPT_LANGUAGE=lang,
                        )
                        self.assertEqual(result.status_code, 200)
                        self.assertEqual(result.context['page_obj'].paginator.count, 1)
                        self.assert_no_contact(result)

    def test_html_seo_portfolio_invitation_dashboard_and_favorites_no_contact(self):
        profile_url = reverse(
            'marketplace:worker_public_profile', args=[self.worker.pk],
        )
        for lang in ('ru', 'en', 'he'):
            with override(lang):
                page = self.client.get(profile_url, HTTP_ACCEPT_LANGUAGE=lang)
                self.assertEqual(page.status_code, 200)
                self.assertContains(page, '<title>')
                self.assertContains(page, 'name="description"')
                self.assertContains(page, 'Service')
                self.assertContains(page, 'Edited')
                self.assert_no_contact(page)

        self.client.force_login(self.client_user)
        invite = reverse(
            'marketplace:worker_invitation_select', args=[self.worker.pk],
        )
        self.assertEqual(self.client.post(invite, {'order_id': self.order.pk}).status_code, 302)
        self.assertEqual(OrderInvitation.objects.count(), 1)
        favorite = reverse('marketplace:toggle_favorite_worker', args=[self.worker.pk])
        self.assertEqual(self.client.post(favorite, {'action': 'add'}).status_code, 302)
        for lang in ('ru', 'en', 'he'):
            with override(lang):
                picker = self.client.get(invite, HTTP_ACCEPT_LANGUAGE=lang)
                dashboard = self.client.get(
                    reverse('marketplace:client_dashboard'),
                    HTTP_ACCEPT_LANGUAGE=lang,
                )
                self.assertEqual(picker.status_code, 200)
                self.assertEqual(dashboard.status_code, 200)
                self.assert_no_contact(picker)
                self.assert_no_contact(dashboard)

    def test_public_form_rejects_phone_uri_obfuscated_mail(self):
        base = {
            'display_name': 'Safe Repair Service',
            'city': self.city.pk,
            'description': 'Synthetic public plumbing repair service.',
            'pricing_details': 'Price after consultation',
            'working_hours': 'Sunday–Thursday, 09:00–17:00',
            'skills': [self.category.pk], 'services': [self.service.pk],
            'spoken_languages': ['ru'],
        }
        cases = (
            ('display_name', 'Service 050------7654321'),
            ('description', 'Call 050      7654321'),
            ('description', 'Contact x://contacthandle'),
            ('description', 'Contact john at example dot com'),
            ('description', 'Contact john @ example.com'),
            ('description', 'Call 050%25252525252F7654321'),
            ('pricing_details', 'Quote by 050------7654321'),
            ('working_hours', 'Call 050      7654321'),
        )
        for field, value in cases:
            with self.subTest(field=field, value=value):
                form = WorkerProfileForm(data={**base, field: value}, instance=self.worker)
                self.assertFalse(form.is_valid())
                self.assertIn(field, form.errors)
                self.worker.refresh_from_db()
        normal = WorkerProfileForm(data=base, instance=self.worker)
        self.assertTrue(normal.is_valid(), normal.errors)

    def test_direct_publication_service_rejects_unvalidated_input(self):
        defaults = {
            'display_name': 'Safe Repair Service',
            'description': 'Synthetic public plumbing repair service.',
            'pricing_details': 'Price after consultation',
            'working_hours': 'Sunday–Thursday, 09:00–17:00',
        }
        cases = (
            ('display_name', 'Service 050------7654321'),
            ('description', 'Call 050      7654321'),
            ('description', 'Contact x://contacthandle'),
            ('description', 'Contact john at example dot com'),
            ('description', 'Contact john @ example.com'),
            ('pricing_details', 'Quote by 050------7654321'),
            ('working_hours', 'Call 050      7654321'),
        )
        for field, value in cases:
            with self.subTest(field=field, value=value):
                params = {**defaults, field: value}
                WorkerProfile.objects.filter(pk=self.worker.pk).update(**params)
                self.worker.refresh_from_db()
                self.assertIsNotNone(publication_issue(self.worker))
                with self.assertRaises(ValueError):
                    set_worker_publication(self.worker_user, True)

    def test_portfolio_forms_http_and_direct_services_block_contacts(self):
        examples = (
            'Edited x://editcontact 050------7654321',
            'Call 050      7654321',
            'Contact john @ example.com',
        )
        self.client.force_login(self.worker_user)
        for caption in examples:
            with self.subTest(caption=caption):
                form = PortfolioEditForm(data={
                    'caption': caption, 'sort_order': '1', 'is_public': 'on',
                })
                self.assertFalse(form.is_valid())
                self.assertIn('caption', form.errors)
                upload = PortfolioUploadForm(data={
                    'caption': caption, 'rights_confirmed': 'on',
                }, files={
                    'image': SimpleUploadedFile('synthetic.png', b'invalid bytes unused'),
                })
                self.assertFalse(upload.is_valid())
                self.assertIn('caption', upload.errors)
                response = self.client.post(
                    reverse('accounts:worker_portfolio_edit', args=[self.photo.pk]),
                    {'caption': caption, 'sort_order': '1', 'is_public': 'on'},
                )
                self.assertEqual(response.status_code, 400)
                with self.assertRaises(PortfolioError):
                    update_own_portfolio_photo(
                        self.worker_user, self.photo.pk,
                        caption=caption, sort_order=1, is_public=True,
                    )
                with self.assertRaises(PortfolioError):
                    add_own_portfolio_photo(
                        self.worker_user, None, caption=caption,
                        sort_order=1, is_public=True, rights_confirmed=True,
                    )
        self.photo.refresh_from_db()
        self.assertEqual(self.photo.caption, 'Edited x://editcontact 050------7654321')

    def test_0019_forward_migration_rescrubs_existing_search_only(self):
        originals = (
            self.worker.pk, self.worker.user_id, self.order.pk,
            self.worker.display_name, self.worker.description,
        )
        WorkerProfile.objects.filter(pk=self.worker.pk).update(
            searchable_display_name='Service 050------7654321',
            searchable_description=(
                'Call 050      7654321 or x://contacthandle. '
                'Contact john at example dot com.'
            ),
        )
        migration = import_module('apps.accounts.migrations.0019_contact_policy_v5_rescrub')
        migration.rescrub_public_search(apps, SimpleNamespace(connection=connection))
        self.worker.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(
            (self.worker.pk, self.worker.user_id, self.order.pk,
             self.worker.display_name, self.worker.description),
            originals,
        )
        self.assertEqual(self.worker.searchable_display_name, 'Service')
        self.assertEqual(self.worker.searchable_description, 'Call or Contact .')

    def test_model_save_update_fields_keeps_search_and_html_safe(self):
        self.worker.display_name = 'New 050------7654321'
        self.worker.save(update_fields=['display_name'])
        self.worker.description = 'Repair john @ example.com and x://contacthandle'
        self.worker.save(update_fields=['description'])
        self.worker.refresh_from_db()
        self.assertEqual(self.worker.searchable_display_name, 'New')
        self.assertEqual(self.worker.searchable_description, 'Repair and')
        self.assertEqual(self.worker.public_display_name, 'New […]')
