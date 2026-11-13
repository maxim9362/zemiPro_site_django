"""Independent ZP-05-001 HIGH and ZP-05-002 MEDIUM negative regressions.

Use only synthetic contacts; old PUBLIC rows may contain contact-bearing data.
Never treat display-only masking as sufficient for keyword matching.
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
    contact_shaped_query, searchable_public_text,
)
from apps.accounts.services import publication_issue, set_worker_publication
from apps.locations.models import City
from apps.marketplace.models import Category, OrderInvitation, Subcategory
from apps.marketplace.tests.factories import make_order, make_user


@override_settings(ZEMIPRO_PILOT_CITY_SLUG='ashdod')
class Stage05ReviewPrivacyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.city = City.objects.create(
            slug='ashdod', name_ru='Ашдод', name_en='Ashdod', name_he='אשדוד',
        )
        cls.category = Category.objects.create(
            slug='review05-plumbing', name_ru='Сантехника',
            name_en='Plumbing', name_he='אינסטלציה', work_mode='onsite',
        )
        cls.service = Subcategory.objects.create(
            category=cls.category, slug='review05-pipe',
            name_ru='Трубы', name_en='Pipes', name_he='צינורות',
            work_mode='onsite',
        )
        cls.client_user = make_user('review05-client')
        ClientProfile.objects.create(user=cls.client_user, city=cls.city)
        cls.worker_user = make_user(
            'review05-worker', email='user-record@example.invalid',
        )
        # Simulates previously published data; it cannot be republished
        # through owner services without removing contact-bearing fields.
        cls.worker = WorkerProfile.objects.create(
            user=cls.worker_user, city=cls.city,
            display_name='Privacy Probe hidden-name@example.invalid',
            description=(
                'Synthetic plumbing jobs; written contact '
                'hidden-contact@example.invalid and +972 50 7654321.'
            ),
            pricing_details='Price on request', spoken_languages=['ru', 'he'],
            contact='PRIVATE_OWNER_CONTACT_NEVER_PUBLIC',
            is_published=True,
        )
        cls.worker.skills.add(cls.category)
        cls.worker.services.add(cls.service)
        cls.order = make_order(
            client=cls.client_user, category=cls.category,
            subcategory=cls.service, city=cls.city,
            work_mode='onsite',
            address='PRIVATE_ORDER_ADDRESS',
            customer_phone='PRIVATE_ORDER_PHONE',
        )

    def assert_no_stored_contact(self, response):
        for marker in (
            'hidden-name@example.invalid', 'hidden-contact@example.invalid',
            '+972 50 7654321', 'user-record@example.invalid',
            'PRIVATE_OWNER_CONTACT_NEVER_PUBLIC',
        ):
            self.assertNotContains(response, marker)

    def test_public_profile_invitation_picker_and_client_dashboard_never_expose_raw_name(self):
        profile_url = reverse(
            'marketplace:worker_public_profile', args=[self.worker.pk],
        )
        page = self.client.get(profile_url)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'Privacy Probe')
        self.assertContains(page, 'name="description"')
        self.assert_no_stored_contact(page)

        self.client.force_login(self.client_user)
        picker_url = reverse('marketplace:worker_invitation_select', args=[self.worker.pk])
        picker = self.client.get(picker_url)
        self.assertEqual(picker.status_code, 200)
        self.assertContains(picker, 'Privacy Probe')
        self.assert_no_stored_contact(picker)

        posted = self.client.post(picker_url, {'order_id': self.order.pk})
        self.assertEqual(posted.status_code, 302)
        self.assertEqual(OrderInvitation.objects.count(), 1)
        dashboard = self.client.get(reverse('marketplace:client_dashboard'))
        self.assertEqual(dashboard.status_code, 200)
        self.assertContains(dashboard, 'Privacy Probe')
        self.assert_no_stored_contact(dashboard)

        invitation = OrderInvitation.objects.get()
        detail = self.client.get(
            reverse('marketplace:invitation_detail', args=[invitation.pk]),
        )
        self.assertEqual(detail.status_code, 200)
        self.assert_no_stored_contact(detail)
        self.assertNotContains(detail, 'PRIVATE_ORDER_ADDRESS')
        self.assertNotContains(detail, 'PRIVATE_ORDER_PHONE')

    def test_raw_contact_and_partial_contact_are_never_keyword_match_predicates(self):
        expected_hidden = (
            'hidden-name@example.invalid',
            'hidden-contact@example.invalid',
            '+972 50 7654321',
            'hidden-name', 'hidden-contact',
            'example.invalid', '7654321', '6543',
        )
        for language in ('ru', 'en', 'he'):
            with override(language):
                url = reverse('catalog_i18n:worker_directory')
                for keyword in expected_hidden:
                    with self.subTest(locale=language, keyword=keyword):
                        response = self.client.get(
                            url, {'q': keyword}, HTTP_ACCEPT_LANGUAGE=language,
                        )
                        self.assertEqual(response.status_code, 200)
                        self.assertEqual(
                            response.context['page_obj'].paginator.count, 0,
                            'Public directory revealed that a hidden contact belongs to a worker.',
                        )
                        self.assertNotContains(response, 'Privacy Probe')

    def test_visible_keywords_still_find_worker_and_rank_without_raw_contact(self):
        url = reverse('marketplace:worker_directory')
        for keyword in ('Privacy', 'Synthetic', 'Сантехника'):
            with self.subTest(keyword=keyword):
                response = self.client.get(url, {'q': keyword})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    list(response.context['page_obj'].object_list)[0].pk,
                    self.worker.pk,
                )
                self.assert_no_stored_contact(response)
        self.assertNotIn('hidden-name', self.worker.searchable_display_name)
        self.assertNotIn('hidden-contact', self.worker.searchable_description)
        self.assertNotIn('7654321', self.worker.searchable_description)

    def test_profile_form_and_publication_service_reject_contacts(self):
        form = WorkerProfileForm(data={
            'display_name': 'Privacy Probe hidden-name@example.invalid',
            'city': self.city.pk,
            'description': 'Synthetic description of tasks and services.',
            'pricing_details': 'Negotiable', 'spoken_languages': ['ru'],
            'skills': [self.category.pk], 'services': [self.service.pk],
        }, instance=self.worker)
        self.assertFalse(form.is_valid())
        self.assertIn('display_name', form.errors)
        # ModelForm validation may update its instance in memory even when
        # invalid; assess the persisted profile, not the mutated object.
        self.worker.refresh_from_db()
        self.assertIsNotNone(publication_issue(self.worker))
        with self.assertRaises(ValueError):
            set_worker_publication(self.worker_user, True)
        self.worker.display_name = 'Privacy Probe'
        self.assertIsNotNone(publication_issue(self.worker))
        self.worker.description = 'Synthetic description of tasks and plumbing work.'
        self.assertIsNone(publication_issue(self.worker))

    def test_legacy_migration_backfills_without_storing_hidden_contact_fragments(self):
        # Bulk writes intentionally simulate older persisted rows that bypass
        # model.save and predate the Stage 05 contact-free columns.
        WorkerProfile.objects.filter(pk=self.worker.pk).update(
            searchable_display_name='DO_NOT_KEEP_A_HIDDEN_NAME',
            searchable_description='DO_NOT_KEEP_HIDDEN_CONTACT',
        )
        migration = import_module('apps.accounts.migrations.0015_contact_free_search')
        migration.backfill(apps, SimpleNamespace(connection=connection))
        self.worker.refresh_from_db()
        self.assertEqual(
            self.worker.searchable_display_name, 'Privacy Probe',
        )
        self.assertIn('Synthetic plumbing jobs', self.worker.searchable_description)
        self.assertNotIn('hidden-contact', self.worker.searchable_description)
        self.assertNotIn('7654321', self.worker.searchable_description)

    def test_updates_sync_contact_free_search_and_partial_queries_do_not_match(self):
        self.worker.display_name = 'Visible Company hidden-new@example.invalid'
        self.worker.save(update_fields=['display_name'])
        self.worker.description = 'Synthetic repairs, 055-76543210, appointment only.'
        self.worker.save(update_fields=['description'])
        self.worker.refresh_from_db()
        self.assertEqual(self.worker.searchable_display_name, 'Visible Company')
        self.assertNotIn('055', self.worker.searchable_description)
        self.assertNotIn('76543210', self.worker.searchable_description)
        self.assertEqual(searchable_public_text('Alpha phone 050 8765432'), 'Alpha phone')
        self.assertTrue(contact_shaped_query('0508765432'))
        self.assertTrue(contact_shaped_query('hidden@example.invalid'))
        self.assertFalse(contact_shaped_query('Privacy'))

    def test_existing_directory_sort_uses_redacted_name_not_hidden_email(self):
        response = self.client.get(
            reverse('marketplace:worker_directory'),
            {'sort': 'name', 'q': 'Privacy'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['page_obj'].paginator.count, 1)
        self.assert_no_stored_contact(response)
