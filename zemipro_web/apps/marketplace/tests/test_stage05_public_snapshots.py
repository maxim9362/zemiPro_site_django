"""Root-cause regressions for Stage 05 public snapshots and matching."""
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import override

from apps.accounts.client_favorites import public_worker_queryset
from apps.accounts.forms import RatingCreateForm, WorkerProfileForm
from apps.accounts.models import (
    ClientProfile,
    WorkerPortfolioPhoto,
    WorkerProfile,
)
from apps.accounts.public_text import (
    build_profile_snapshot,
    contact_shaped_query,
    contains_public_contact,
)
from apps.accounts.services import publication_issue
from apps.locations.models import City
from apps.marketplace.models import Category, Order, Rating, Subcategory
from apps.marketplace.services import create_response, get_available_orders_for_worker
from apps.marketplace.tests.factories import make_order, make_user


@override_settings(ZEMIPRO_PILOT_CITY_SLUG='ashdod')
class PublicSnapshotSecurityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.city = City.objects.create(
            slug='ashdod', name_ru='Ашдод', name_en='Ashdod', name_he='אשדוד',
        )
        cls.category = Category.objects.create(
            slug='snapshot-repair', name_ru='Ремонт', name_en='Repair',
            name_he='תיקונים', work_mode='both',
        )
        cls.service = Subcategory.objects.create(
            category=cls.category, slug='snapshot-pipes', name_ru='Трубы',
            name_en='Pipes', name_he='צינורות', work_mode='both',
        )
        cls.other_service = Subcategory.objects.create(
            category=cls.category, slug='snapshot-walls', name_ru='Стены',
            name_en='Walls', name_he='קירות', work_mode='onsite',
        )
        cls.other_category = Category.objects.create(
            slug='snapshot-garden', name_ru='Сад', name_en='Garden',
            name_he='גינה', work_mode='onsite',
        )
        cls.owner = make_user('snapshot-owner')
        ClientProfile.objects.create(user=cls.owner, city=cls.city)
        cls.worker_user = make_user('snapshot-worker')
        cls.worker = WorkerProfile.objects.create(
            user=cls.worker_user, city=cls.city, is_published=True,
            display_name='Signal Electric',
            description='Mobile phone repair and electrical work in Ashdod.',
            pricing_details='Call-out fee is 100 ILS',
            working_hours='09:00-17:00', spoken_languages=['ru', 'en', 'he'],
        )
        cls.worker.skills.add(cls.category)
        cls.worker.services.add(cls.service)

    def test_threat_matrix_is_blocked_without_false_positive_examples(self):
        blocked = (
            'john-at-example-dot-com',
            'john⟦at⟧example⟦dot⟧com',
            't_e_l_e_g_r_a_m contacthandle',
            'telegraм contacthandle',
            'john аt example dоt com',
            'тг://contacthandle',
            '//1.2.3.4/contacthandle',
            'zero five zero seven six five four three two one',
            'ноль пять ноль семь шесть пять четыре три два один',
            '05:07-06:05 04',
        )
        for value in blocked:
            with self.subTest(value=value):
                self.assertTrue(contains_public_contact(
                    value, allow_work_hours=value.startswith('05:'),
                ))
        for value in (
            'Signal Electric', 'DM Cleaning', 'Mail Boxes Etc.',
            'React.js developer', 'Mobile phone repair in Ashdod',
            'Call-out fee is 100 ILS',
        ):
            with self.subTest(value=value):
                self.assertFalse(contains_public_contact(value))
        self.assertFalse(contact_shaped_query('2026'))
        self.assertFalse(contact_shaped_query('ISO 9001'))

    def test_cross_field_and_private_identifier_correlation_fail_closed(self):
        self.assertIsNone(build_profile_snapshot(
            display_name='Expert 05076',
            description='54321 synthetic repair services',
            pricing_details='Quotation after inspection',
            working_hours='09:00-17:00',
        ))
        self.worker.contact = '@signal-electric-private'
        self.worker.display_name = 'signal-electric-private'
        self.worker.save(update_fields=['contact', 'display_name'])
        self.worker.refresh_from_db()
        self.assertTrue(self.worker.public_content_safe)
        self.assertEqual(self.worker.public_display_name, '[…]')
        self.assertEqual(self.worker.searchable_display_name, '')
        self.assertIsNotNone(publication_issue(self.worker))
        self.assertTrue(public_worker_queryset().filter(pk=self.worker.pk).exists())

    def test_private_identity_change_rebuilds_snapshot(self):
        self.worker_user.email = 'signal.electric@example.test'
        self.worker_user.save(update_fields=['email'])
        self.worker.refresh_from_db()
        self.assertTrue(self.worker.public_content_safe)
        self.assertEqual(self.worker.public_display_name, '[…]')
        self.assertEqual(self.worker.searchable_display_name, '')

    def test_bulk_raw_edit_fails_closed_and_cannot_change_search(self):
        WorkerProfile.objects.filter(pk=self.worker.pk).update(
            display_name='john-at-example-dot-com',
            description='t_e_l_e_g_r_a_m contacthandle',
        )
        self.worker.refresh_from_db()
        self.assertEqual(self.worker.public_display_name, '[…]')
        self.assertNotIn('john-at', self.worker.public_display_name)
        self.assertFalse(public_worker_queryset().filter(pk=self.worker.pk).exists())
        for language in ('ru', 'en', 'he'):
            with override(language):
                response = self.client.get(
                    reverse('catalog_i18n:worker_directory'),
                    {'q': 'contacthandle'}, HTTP_ACCEPT_LANGUAGE=language,
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context['page_obj'].paginator.count, 0)

    def test_forms_review_and_portfolio_use_public_snapshots(self):
        profile_form = WorkerProfileForm(instance=self.worker, data={
            'provider_type': self.worker.provider_type,
            'display_name': 'john-at-example-dot-com',
            'city': self.city.pk,
            'description': 'Synthetic repair description for Ashdod.',
            'pricing_details': 'Quotation after inspection',
            'availability': self.worker.availability,
            'working_hours': '09:00-17:00',
        })
        self.assertFalse(profile_form.is_valid())
        review_form = RatingCreateForm(data={
            'rating': 5, 'review_text': 't_e_l_e_g_r_a_m contacthandle',
        })
        self.assertFalse(review_form.is_valid())

        photo = WorkerPortfolioPhoto.objects.create(
            worker=self.worker,
            file_key='worker-portfolio/' + 'e' * 32 + '.jpg',
            caption='Synthetic completed repair', is_public=True,
            rights_confirmed_at=timezone.now(),
        )
        # WorkerPortfolioPhoto has no supported bulk text edit; its persisted
        # snapshot remains the only public representation.
        WorkerPortfolioPhoto.objects.filter(pk=photo.pk).update(
            caption='john-at-example-dot-com',
        )
        photo.refresh_from_db()
        self.assertEqual(photo.public_caption, 'Synthetic completed repair')

        order = make_order(
            client=self.owner, worker=self.worker_user,
            category=self.category, subcategory=self.service, city=self.city,
            status=Order.Status.COMPLETED,
        )
        rating = Rating.objects.create(
            order=order, worker=self.worker_user, client=self.owner,
            rating=5, review_text='Synthetic review without contact.',
        )
        Rating.objects.filter(pk=rating.pk).update(
            review_text='john-at-example-dot-com',
        )
        rating.refresh_from_db()
        self.assertEqual(
            rating.public_review_text, 'Synthetic review without contact.',
        )
        response = self.client.get(reverse(
            'marketplace:worker_public_profile', args=[self.worker.pk],
        ))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'john-at-example-dot-com')

    def test_exact_service_category_zone_and_mode_gate_responses(self):
        valid = make_order(
            client=self.owner, category=self.category, subcategory=self.service,
            city=self.city, work_mode=Order.WorkMode.ONSITE,
        )
        wrong_service = make_order(
            client=self.owner, category=self.category,
            subcategory=self.other_service, city=self.city,
            work_mode=Order.WorkMode.ONSITE,
        )
        wrong_category = make_order(
            client=self.owner, category=self.other_category, city=self.city,
            work_mode=Order.WorkMode.ONSITE,
        )
        available = get_available_orders_for_worker(self.worker)
        self.assertTrue(available.filter(pk=valid.pk).exists())
        self.assertFalse(available.filter(pk=wrong_service.pk).exists())
        self.assertFalse(available.filter(pk=wrong_category.pk).exists())
        for order in (wrong_service, wrong_category):
            with self.subTest(order=order.pk), self.assertRaisesMessage(
                ValueError, 'не соответствует услугам',
            ):
                create_response(order, self.worker_user)
        self.client.force_login(self.worker_user)
        for order in (wrong_service, wrong_category):
            url = reverse('marketplace:order_respond', args=[order.pk])
            with self.subTest(http_order=order.pk):
                self.assertEqual(self.client.get(url).status_code, 404)
                self.assertEqual(
                    self.client.post(url, {'message': 'Crafted response'}).status_code,
                    404,
                )
