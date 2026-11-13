"""Fail-closed public text and structured-search regressions for Stage 05.

All values are synthetic.  These tests intentionally bypass normal forms in a
few places to model historical rows and direct database imports.
"""
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import override

from apps.accounts.forms import (
    PortfolioEditForm,
    PortfolioUploadForm,
    WorkerProfileForm,
)
from apps.accounts.models import ClientProfile, WorkerPortfolioPhoto, WorkerProfile
from apps.accounts.portfolio import (
    PortfolioError,
    add_own_portfolio_photo,
    update_own_portfolio_photo,
)
from apps.accounts.public_text import (
    contact_shaped_query,
    contains_public_contact,
    redact_public_contact,
    searchable_public_text,
)
from apps.accounts.services import publication_issue, set_worker_publication
from apps.locations.models import City
from apps.marketplace.models import Category, OrderInvitation, Subcategory
from apps.marketplace.tests.factories import make_order, make_user


@override_settings(ZEMIPRO_PILOT_CITY_SLUG='ashdod')
class ContactPolicyV6Tests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.city = City.objects.create(
            slug='ashdod', name_ru='Ашдод', name_en='Ashdod', name_he='אשדוד',
        )
        cls.category = Category.objects.create(
            slug='v6-repair', name_ru='Ремонт', name_en='Repair',
            name_he='תיקונים', work_mode='onsite',
        )
        cls.service = Subcategory.objects.create(
            category=cls.category, slug='v6-pipes', name_ru='Трубы',
            name_en='Pipes', name_he='צינורות', work_mode='onsite',
        )
        cls.client_user = make_user('v6-client')
        ClientProfile.objects.create(user=cls.client_user, city=cls.city)
        cls.worker_user = make_user('v6-worker')
        cls.worker = WorkerProfile.objects.create(
            user=cls.worker_user, city=cls.city, is_published=True,
            display_name='Reliable Pipe Service',
            description='Synthetic repair of pipes and fixtures in Ashdod.',
            pricing_details='Quotation after inspection',
            working_hours='Sunday–Thursday, 09:00–17:00',
            spoken_languages=['ru', 'en', 'he'],
        )
        cls.worker.skills.add(cls.category)
        cls.worker.services.add(cls.service)
        cls.photo = WorkerPortfolioPhoto.objects.create(
            worker=cls.worker,
            file_key='worker-portfolio/' + 'd' * 32 + '.jpg',
            caption='Synthetic completed repair', is_public=True,
            rights_confirmed_at=timezone.now(),
        )
        cls.order = make_order(
            client=cls.client_user, category=cls.category,
            subcategory=cls.service, city=cls.city, work_mode='onsite',
            address='PRIVATE_V6_ADDRESS', customer_phone='PRIVATE_V6_PHONE',
        )

    def test_additional_contact_classes_hide_the_complete_field(self):
        vectors = (
            '050x7654321',
            '0a5a0a7a6a5a4a3a2a1',
            '050 phone 7654321',
            '050 номер 7654321',
            '050 טלפון 7654321',
            '050-7654',
            'telegram contacthandle',
            'instagram contacthandle',
            't g : / / contacthandle',
            'telegram : //contacthandle',
            'example {dot} com',
            'john {at} example {dot} com',
            'john собака example точка com',
            'john שטרודל example נקודה com',
            'j o h n @ example.com',
            'Call 050%252525252525252525252F7654321',
        )
        for value in vectors:
            with self.subTest(value=value):
                self.assertTrue(contains_public_contact(value))
                self.assertEqual(redact_public_contact(value), '[…]')
                self.assertEqual(searchable_public_text(value), '')

    def test_safe_text_and_hours_are_not_partially_rewritten(self):
        safe = (
            'Reliable Pipe Service',
            'Synthetic repair service in Ashdod',
            'Quotation after inspection',
            'Repair version 2.0 in 2026',
        )
        for value in safe:
            with self.subTest(value=value):
                self.assertFalse(contains_public_contact(value))
                self.assertEqual(redact_public_contact(value), value)
        hours = 'Sunday–Thursday, 09:00–17:00'
        self.assertFalse(contains_public_contact(hours, allow_work_hours=True))
        self.assertEqual(
            redact_public_contact(hours, allow_work_hours=True),
            'Sunday-Thursday, 09:00-17:00',
        )
        self.assertTrue(contains_public_contact('Phone 050:7654321'))
        self.assertTrue(contains_public_contact(
            '09:00-17:00 and 050:7654321', allow_work_hours=True,
        ))

    def test_forms_and_direct_services_share_one_policy(self):
        base = {
            'display_name': 'Reliable Pipe Service', 'city': self.city.pk,
            'description': 'Synthetic repair of pipes and fixtures in Ashdod.',
            'pricing_details': 'Quotation after inspection',
            'working_hours': 'Sunday–Thursday, 09:00–17:00',
            'skills': [self.category.pk], 'services': [self.service.pk],
            'spoken_languages': ['ru'],
        }
        cases = (
            ('display_name', 'Service 050x7654321'),
            ('description', 'telegram contacthandle'),
            ('description', 'john собака example точка com'),
            ('pricing_details', '050 номер 7654321'),
            ('working_hours', '09:00-17:00 and 050:7654321'),
        )
        for field, value in cases:
            with self.subTest(field=field, value=value):
                form = WorkerProfileForm(
                    data={**base, field: value}, instance=self.worker,
                )
                self.assertFalse(form.is_valid())
                self.assertIn(field, form.errors)
                WorkerProfile.objects.filter(pk=self.worker.pk).update(
                    **{field: value}, is_published=False,
                )
                self.worker.refresh_from_db()
                self.assertIsNotNone(publication_issue(self.worker))
                with self.assertRaises(ValueError):
                    set_worker_publication(self.worker_user, True)
                WorkerProfile.objects.filter(pk=self.worker.pk).update(
                    **{field: base[field]}, is_published=True,
                )
                self.worker.refresh_from_db()

    def test_stale_import_cannot_leak_to_html_seo_or_private_surfaces(self):
        # Supported QuerySet.update() edits fail closed until a snapshot is
        # rebuilt through Model.save/service publication.
        WorkerProfile.objects.filter(pk=self.worker.pk).update(
            display_name='Service 050x7654321',
            description='telegram contacthandle',
            pricing_details='john {at} example {dot} com',
            working_hours='09:00-17:00 and 050:7654321',
            public_content_safe=True,
        )
        WorkerPortfolioPhoto.objects.filter(pk=self.photo.pk).update(
            caption='instagram editcontact 050 номер 7654321',
        )
        self.worker.refresh_from_db()
        self.photo.refresh_from_db()

        profile_url = reverse(
            'marketplace:worker_public_profile', args=[self.worker.pk],
        )
        secrets = (
            '050x7654321', 'contacthandle', 'john',
            'editcontact', '7654321',
        )
        for language in ('ru', 'en', 'he'):
            with override(language):
                response = self.client.get(
                    profile_url, HTTP_ACCEPT_LANGUAGE=language,
                )
                self.assertEqual(response.status_code, 404)
                for secret in secrets:
                    self.assertNotContains(response, secret, status_code=404)

        self.client.force_login(self.client_user)
        invite_url = reverse(
            'marketplace:worker_invitation_select', args=[self.worker.pk],
        )
        self.assertEqual(self.client.post(
            invite_url, {'order_id': self.order.pk},
        ).status_code, 404)
        self.assertEqual(OrderInvitation.objects.count(), 0)
        favorite_url = reverse(
            'marketplace:toggle_favorite_worker', args=[self.worker.pk],
        )
        self.assertEqual(self.client.post(
            favorite_url, {'action': 'add'},
        ).status_code, 404)
        for url in (reverse('marketplace:client_dashboard'),):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            for secret in secrets:
                self.assertNotContains(response, secret)

    def test_unsafe_historical_profile_is_removed_from_public_surfaces(self):
        WorkerProfile.objects.filter(pk=self.worker.pk).update(
            description='Call 050x7654321',
            searchable_display_name='Reliable Pipe Service',
            searchable_description='Call 050x7654321',
            public_content_safe=False,
        )
        for language in ('ru', 'en', 'he'):
            with override(language):
                directory = reverse('catalog_i18n:worker_directory')
                for query in ('4321', '7654321', 'Call'):
                    response = self.client.get(
                        directory, {'q': query}, HTTP_ACCEPT_LANGUAGE=language,
                    )
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.context['page_obj'].paginator.count, 0)
                normal = self.client.get(
                    directory, {'q': 'Reliable'}, HTTP_ACCEPT_LANGUAGE=language,
                )
                self.assertEqual(normal.context['page_obj'].paginator.count, 0)
        profile = self.client.get(reverse(
            'marketplace:worker_public_profile', args=[self.worker.pk],
        ))
        self.assertEqual(profile.status_code, 404)
        self.assertNotContains(profile, '050x7654321', status_code=404)

    def test_search_uses_safe_name_and_curated_services_not_description(self):
        self.worker.refresh_from_db()
        self.assertTrue(self.worker.public_content_safe)
        self.assertEqual(self.worker.searchable_description, '')
        directory = reverse('marketplace:worker_directory')
        expected = {
            'Reliable': 1,
            'Pipes': 1,
            'Repair': 1,
            'fixtures': 0,
        }
        for query, count in expected.items():
            with self.subTest(query=query):
                response = self.client.get(directory, {'q': query})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context['page_obj'].paginator.count, count)

    def test_contact_queries_include_short_numeric_oracles(self):
        for query in (
            '4321', '050-7654', '050x7654321', 'telegram contacthandle',
            'john {at} example {dot} com',
        ):
            with self.subTest(query=query):
                self.assertTrue(contact_shaped_query(query))
        for query in ('Reliable', 'Pipe repair', 'Ashdod'):
            self.assertFalse(contact_shaped_query(query))

    def test_model_save_and_update_fields_refresh_the_safety_gate(self):
        self.worker.refresh_from_db()
        self.assertTrue(self.worker.public_content_safe)
        self.worker.pricing_details = '050x7654321'
        self.worker.save(update_fields=['pricing_details'])
        self.worker.refresh_from_db()
        self.assertTrue(self.worker.public_content_safe)
        self.assertIsNotNone(publication_issue(self.worker))
        self.assertEqual(self.worker.public_pricing_details, '[…]')
        self.worker.pricing_details = 'Quotation after inspection'
        self.worker.save(update_fields=['pricing_details'])
        self.worker.refresh_from_db()
        self.assertTrue(self.worker.public_content_safe)
        self.assertEqual(self.worker.searchable_description, '')

    def test_portfolio_forms_and_services_reject_new_vectors(self):
        examples = (
            '050x7654321', 'telegram editcontact',
            'john собака example точка com',
        )
        for caption in examples:
            with self.subTest(caption=caption):
                edit = PortfolioEditForm(data={
                    'caption': caption, 'sort_order': '1', 'is_public': 'on',
                })
                upload = PortfolioUploadForm(data={
                    'caption': caption, 'rights_confirmed': 'on',
                }, files={
                    'image': SimpleUploadedFile('synthetic.png', b'not read'),
                })
                self.assertFalse(edit.is_valid())
                self.assertFalse(upload.is_valid())
                with self.assertRaises(PortfolioError):
                    update_own_portfolio_photo(
                        self.worker_user, self.photo.pk, caption=caption,
                        sort_order=1, is_public=True,
                    )
                with self.assertRaises(PortfolioError):
                    add_own_portfolio_photo(
                        self.worker_user, None, caption=caption,
                        sort_order=1, is_public=True, rights_confirmed=True,
                    )
