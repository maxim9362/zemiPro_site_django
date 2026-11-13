"""Root-cause regressions for Stage 05 public snapshots and matching."""
import threading
from unittest import mock

from django.db import close_old_connections
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import override

from apps.accounts.client_favorites import public_worker_queryset
from apps.accounts.forms import RatingCreateForm, WorkerProfileForm
from apps.accounts.models import (
    ClientProfile,
    SafeUserQuerySet,
    User,
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
            'repair.xyz/contacthandle',
            'contact.example.ai/handle',
            'example.рф/contact',
            'Visit example.xyz for details',
            'Contact example.xyz today',
            'See worker.xyz, available now',
            'worker.xyz?handle=contact',
            'Our repair.xyz offers details',
            'repair.XYZ',
            'repair.technology official',
            'hello.קום',
            'repair . xyz',
            'repair . XYZ',
            'repair . technology',
            'hello . קום',
            'repair (dot) xyz',
            'repair [dot] xyz',
            'repair · xyz',
            'asp.net?u=privatehandle',
            'asp.net#privatehandle',
            'react.js?u=privatehandle',
            'node.js#secret',
            'react . js?u=privatehandle',
            'node . js#secret',
            'asp . net:8080',
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
            'React.js developer', 'We build with React.js every day',
            'Dr. Cohen provides plumbing', 'Node.js applications',
            'ASP.NET developer', 'I use React.js and Node.js daily',
            'U.S. trained technician', 'Ashdod Ltd. Company',
            'Use e.g. synthetic fixtures',
            'Mobile phone repair in Ashdod',
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

    def test_labeled_private_handles_cannot_become_public_identity(self):
        for private_value, public_name in (
            ('Telegram: @uniqueprivatehandle', 'uniqueprivatehandle'),
            ('WhatsApp @secretworker', 'secretworker'),
            ('contact: @ashdodexpert', 'ashdodexpert'),
        ):
            with self.subTest(private_value=private_value):
                self.worker.contact = private_value
                self.worker.display_name = public_name
                self.worker.description = 'Synthetic repair services in Ashdod.'
                self.worker.save()
                self.worker.refresh_from_db()
                self.assertEqual(self.worker.public_display_name, '[…]')
                self.assertEqual(self.worker.searchable_display_name, '')
                self.assertNotContains(
                    self.client.get(reverse(
                        'marketplace:worker_public_profile',
                        args=[self.worker.pk],
                    )),
                    public_name,
                )
        self.worker.contact = '@secret2026'
        self.worker.display_name = 'secret'
        self.worker.save()
        self.worker.refresh_from_db()
        self.assertEqual(self.worker.public_display_name, '[…]')
        self.assertEqual(self.worker.searchable_display_name, '')
        for private_value, public_name in (
            ('@abc', 'abc'),
            ('TG: @xyz', 'xyz'),
            ('abc@example.invalid', 'abc'),
            ('Contact: bob', 'bob'),
            ('Instagram: bob', 'bob'),
            ('Telegram: bob', 'bob'),
            ('TG: xyz', 'xyz'),
            ('Телеграм: боб', 'боб'),
            ('טלגרם: אבי', 'אבי'),
        ):
            with self.subTest(short_private=private_value):
                snapshot = build_profile_snapshot(
                    display_name=public_name,
                    description='Synthetic repair services in Ashdod.',
                    pricing_details='Quotation after inspection',
                    working_hours='09:00-17:00',
                    private_values=(private_value,),
                )
                self.assertIsNone(snapshot)
        for private_value, description in (
            ('a@example.invalid', 'A skilled professional with a decade of experience.'),
            ('it@example.invalid', 'We repair it quickly.'),
            ('@the', 'The service is available in Ashdod.'),
            ('@pro', 'Professional repair for synthetic fixtures.'),
            ('info@example.invalid', 'More info about our repair services.'),
            ('service@example.invalid', 'Professional repair service.'),
            ('support@example.invalid', 'We support household repairs.'),
            ('admin@example.invalid', 'Property administration service.'),
            ('office@example.invalid', 'Office renovation in Ashdod.'),
        ):
            with self.subTest(short_private_false_positive=private_value):
                snapshot = build_profile_snapshot(
                    display_name='Ashdod Repair Specialist',
                    description=description,
                    pricing_details='Quotation after inspection',
                    working_hours='09:00-17:00',
                    private_values=(private_value,),
                )
                self.assertIsNotNone(snapshot)
        self.assertIsNotNone(build_profile_snapshot(
            display_name='favorite-worker',
            description='Synthetic professional profile for favorites.',
            pricing_details='Negotiable',
            working_hours='',
            private_values=('HIDDEN-WORKER-CONTACT',),
        ))

    def test_private_contact_labels_do_not_block_legitimate_service_words(self):
        for private_value, description in (
            (
                'Phone: +972 50 765 4321',
                'Mobile phone repair specialist with ten years experience.',
            ),
            (
                'Email: owner@example.invalid',
                'Professional email setup and server configuration service.',
            ),
        ):
            with self.subTest(private_value=private_value):
                snapshot = build_profile_snapshot(
                    display_name='Ashdod Technical Service',
                    description=description,
                    pricing_details='Quotation after inspection',
                    working_hours='09:00-17:00',
                    private_values=(private_value,),
                )
                self.assertIsNotNone(snapshot)

    def test_unsafe_field_cannot_bypass_remaining_field_correlation_checks(self):
        self.worker.contact = '@uniqueprivatehandle'
        self.worker.display_name = 'uniqueprivatehandle'
        self.worker.description = 'Contact john@example.com'
        self.worker.pricing_details = 'Quote 54321'
        self.worker.working_hours = '09:00-17:00'
        self.worker.save()
        self.worker.refresh_from_db()
        self.assertEqual(self.worker.public_display_name, '[…]')
        self.assertEqual(self.worker.searchable_display_name, '')
        for language in ('ru', 'en', 'he'):
            with override(language):
                response = self.client.get(
                    reverse('catalog_i18n:worker_directory'),
                    {'q': 'uniqueprivatehandle'}, HTTP_ACCEPT_LANGUAGE=language,
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context['page_obj'].paginator.count, 0)
        profile = self.client.get(reverse(
            'marketplace:worker_public_profile', args=[self.worker.pk],
        ))
        self.assertEqual(profile.status_code, 200)
        self.assertNotContains(profile, 'uniqueprivatehandle')
        self.assertNotContains(profile, 'john@example.com')

    def test_unlisted_tld_url_is_absent_from_html_and_localized_search(self):
        value = 'Visit repair.xyz for contact details'
        self.worker.display_name = value
        self.worker.save(update_fields=['display_name'])
        self.worker.refresh_from_db()
        self.assertEqual(self.worker.public_display_name, '[…]')
        self.assertEqual(self.worker.searchable_display_name, '')
        profile_url = reverse(
            'marketplace:worker_public_profile', args=[self.worker.pk],
        )
        for language in ('ru', 'en', 'he'):
            with override(language):
                profile = self.client.get(
                    profile_url, HTTP_ACCEPT_LANGUAGE=language,
                )
                self.assertEqual(profile.status_code, 200)
                self.assertNotContains(profile, value)
                search = self.client.get(
                    reverse('catalog_i18n:worker_directory'),
                    {'q': value}, HTTP_ACCEPT_LANGUAGE=language,
                )
                self.assertEqual(search.status_code, 200)
                self.assertEqual(search.context['page_obj'].paginator.count, 0)

    def test_private_identity_change_rebuilds_snapshot(self):
        self.worker_user.email = 'signal.electric@example.test'
        self.worker_user.save(update_fields=['email'])
        self.worker.refresh_from_db()
        self.assertTrue(self.worker.public_content_safe)
        self.assertEqual(self.worker.public_display_name, '[…]')
        self.assertEqual(self.worker.searchable_display_name, '')

    def test_normal_identity_save_and_snapshot_rebuild_are_atomic_on_failure(self):
        original_email = self.worker_user.email
        self.worker_user.email = 'atomic-normal@example.invalid'
        with mock.patch.object(
            WorkerProfile,
            '_refresh_public_snapshot',
            side_effect=RuntimeError('synthetic snapshot failure'),
        ), self.assertRaisesRegex(RuntimeError, 'synthetic snapshot failure'):
            self.worker_user.save(update_fields=['email'])
        self.worker_user.refresh_from_db()
        self.assertEqual(self.worker_user.email, original_email)

    def test_profile_save_uses_fresh_locked_private_identity(self):
        # Prime a stale related-object cache, then mutate identity by a
        # supported bulk path before rebuilding the profile.
        self.worker.display_name = 'freshprivatehandle'
        self.worker.save(update_fields=['display_name'])
        self.assertEqual(self.worker.user.email, '')
        User.objects.filter(pk=self.worker_user.pk).update(
            email='freshprivatehandle@example.invalid',
        )
        self.worker.description = 'Updated synthetic repair in Ashdod.'
        self.worker.save(update_fields=['description'])
        self.worker.refresh_from_db()
        self.assertEqual(self.worker.public_display_name, '[…]')
        self.assertEqual(self.worker.searchable_display_name, '')

    def test_partial_profile_save_combines_persisted_contact_before_snapshot(self):
        self.worker.display_name = 'persistedprivatehandle'
        self.worker.save(update_fields=['display_name'])
        stale_profile = WorkerProfile.objects.get(pk=self.worker.pk)
        WorkerProfile.objects.filter(pk=self.worker.pk).update(
            contact='@persistedprivatehandle',
        )
        stale_profile.description = 'Updated synthetic repair services.'
        stale_profile.save(update_fields=['description'])
        stale_profile.refresh_from_db()
        self.assertEqual(stale_profile.contact, '@persistedprivatehandle')
        self.assertEqual(stale_profile.public_display_name, '[…]')
        self.assertEqual(stale_profile.searchable_display_name, '')

    def test_partial_profile_bulk_update_combines_persisted_contact(self):
        self.worker.display_name = 'bulkstoredprivate'
        self.worker.save(update_fields=['display_name'])
        stale_profile = WorkerProfile.objects.get(pk=self.worker.pk)
        WorkerProfile.objects.filter(pk=self.worker.pk).update(
            contact='@bulkstoredprivate',
        )
        stale_profile.description = 'Bulk updated synthetic repair services.'
        WorkerProfile.objects.bulk_update([stale_profile], ['description'])
        stale_profile.refresh_from_db()
        self.assertEqual(stale_profile.contact, '@bulkstoredprivate')
        self.assertEqual(stale_profile.public_display_name, '[…]')
        self.assertEqual(stale_profile.searchable_display_name, '')

    def test_partial_user_save_reloads_other_private_identity_field(self):
        self.worker.display_name = 'newprivatephone'
        self.worker.save(update_fields=['display_name'])
        stale_user = User.objects.get(pk=self.worker_user.pk)
        User.objects.filter(pk=self.worker_user.pk).update(
            phone='newprivatephone',
        )
        stale_user.email = 'unrelated@example.invalid'
        stale_user.save(update_fields=['email'])
        self.worker.refresh_from_db()
        self.assertEqual(self.worker.public_display_name, '[…]')
        self.assertEqual(self.worker.searchable_display_name, '')

    def test_bulk_private_identity_change_invalidates_public_projection(self):
        self.worker.display_name = 'bulkprivateid'
        self.worker.save(update_fields=['display_name'])
        self.worker.refresh_from_db()
        self.assertEqual(self.worker.searchable_display_name, 'bulkprivateid')
        type(self.worker_user).objects.filter(pk=self.worker_user.pk).update(
            email='bulkprivateid@example.invalid',
        )
        self.worker.refresh_from_db()
        self.assertFalse(self.worker.public_content_safe)
        self.assertFalse(public_worker_queryset().filter(pk=self.worker.pk).exists())

    def test_bulk_update_private_identity_invalidates_public_projection(self):
        self.worker.display_name = 'bulkprivatehandle'
        self.worker.save(update_fields=['display_name'])
        self.worker_user.email = 'bulkprivatehandle@example.invalid'
        User.objects.bulk_update(
            (user for user in (self.worker_user,)), ['email'],
        )
        self.worker.refresh_from_db()
        self.assertFalse(self.worker.public_content_safe)
        self.assertFalse(public_worker_queryset().filter(pk=self.worker.pk).exists())

    def test_bulk_identity_update_and_invalidation_are_atomic_on_failure(self):
        original_email = self.worker_user.email
        with mock.patch.object(
            SafeUserQuerySet,
            '_invalidate_profiles',
            side_effect=RuntimeError('synthetic invalidation failure'),
        ), self.assertRaisesRegex(RuntimeError, 'synthetic invalidation failure'):
            User.objects.filter(pk=self.worker_user.pk).update(
                email='atomic-private@example.invalid',
            )
        self.worker_user.refresh_from_db()
        self.worker.refresh_from_db()
        self.assertEqual(self.worker_user.email, original_email)
        self.assertTrue(self.worker.public_content_safe)

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

    def test_bulk_update_rebuilds_safe_snapshot_without_self_invalidation(self):
        self.worker.display_name = 'Updated Ashdod Specialist'
        self.worker.description = 'Updated synthetic repair services in Ashdod.'
        WorkerProfile.objects.bulk_update(
            [self.worker], ['display_name', 'description'],
        )
        self.worker.refresh_from_db()
        self.assertTrue(self.worker.public_content_safe)
        self.assertEqual(
            self.worker.public_display_name, 'Updated Ashdod Specialist',
        )
        self.assertEqual(
            self.worker.searchable_display_name, 'Updated Ashdod Specialist',
        )
        self.assertTrue(public_worker_queryset().filter(pk=self.worker.pk).exists())

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


@override_settings(ZEMIPRO_PILOT_CITY_SLUG='ashdod')
class BulkIdentityAtomicityPostgresTests(TransactionTestCase):
    """Prove no committed stale projection window during bulk identity edits."""

    def test_concurrent_reader_sees_old_pair_then_invalidated_new_identity(self):
        city = City.objects.create(
            slug='atomic-ashdod', name_ru='Ашдод',
            name_en='Ashdod', name_he='אשדוד',
        )
        user = make_user('atomic-worker')
        profile = WorkerProfile.objects.create(
            user=user, city=city, is_published=True,
            display_name='atomicprivatehandle',
            description='Synthetic repair services in Ashdod.',
            working_hours='09:00-17:00',
        )
        entered_invalidation = threading.Event()
        allow_commit = threading.Event()
        errors = []
        original_invalidate = SafeUserQuerySet._invalidate_profiles

        def paused_invalidation(queryset, user_ids):
            entered_invalidation.set()
            if not allow_commit.wait(timeout=10):
                raise TimeoutError('concurrent test release timed out')
            return original_invalidate(queryset, user_ids)

        def change_identity():
            close_old_connections()
            try:
                with mock.patch.object(
                    SafeUserQuerySet,
                    '_invalidate_profiles',
                    new=paused_invalidation,
                ):
                    User.objects.filter(pk=user.pk).update(
                        email='atomicprivatehandle@example.invalid',
                    )
            except Exception as exc:  # pragma: no cover - asserted below
                errors.append(exc)
            finally:
                close_old_connections()

        thread = threading.Thread(target=change_identity)
        thread.start()
        self.assertTrue(entered_invalidation.wait(timeout=10))
        try:
            # The update and invalidation share one transaction, so a second
            # connection cannot observe the new identity with the old snapshot.
            user.refresh_from_db()
            profile.refresh_from_db()
            self.assertEqual(user.email, '')
            self.assertTrue(profile.public_content_safe)
        finally:
            allow_commit.set()
            thread.join(timeout=10)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        user.refresh_from_db()
        profile.refresh_from_db()
        self.assertEqual(user.email, 'atomicprivatehandle@example.invalid')
        self.assertFalse(profile.public_content_safe)

    def test_profile_bulk_rebuild_serializes_with_private_identity_update(self):
        city = City.objects.create(
            slug='atomic-bulk-ashdod', name_ru='Ашдод',
            name_en='Ashdod', name_he='אשדוד',
        )
        user = make_user('atomic-bulk-worker')
        profile = WorkerProfile.objects.create(
            user=user, city=city, is_published=True,
            display_name='Initial Synthetic Worker',
            description='Synthetic repair services in Ashdod.',
            working_hours='09:00-17:00',
        )
        entered_invalidation = threading.Event()
        allow_identity_commit = threading.Event()
        profile_finished = threading.Event()
        errors = []
        original_invalidate = SafeUserQuerySet._invalidate_profiles

        def paused_invalidation(queryset, user_ids):
            entered_invalidation.set()
            if not allow_identity_commit.wait(timeout=10):
                raise TimeoutError('identity release timed out')
            return original_invalidate(queryset, user_ids)

        def change_identity():
            close_old_connections()
            try:
                with mock.patch.object(
                    SafeUserQuerySet,
                    '_invalidate_profiles',
                    new=paused_invalidation,
                ):
                    User.objects.filter(pk=user.pk).update(
                        email='newprivateid@example.invalid',
                    )
            except Exception as exc:  # pragma: no cover - asserted below
                errors.append(exc)
            finally:
                close_old_connections()

        def rebuild_profile():
            close_old_connections()
            try:
                profile.display_name = 'newprivateid'
                WorkerProfile.objects.bulk_update([profile], ['display_name'])
            except Exception as exc:  # pragma: no cover - asserted below
                errors.append(exc)
            finally:
                profile_finished.set()
                close_old_connections()

        identity_thread = threading.Thread(target=change_identity)
        identity_thread.start()
        self.assertTrue(entered_invalidation.wait(timeout=10))
        profile_thread = threading.Thread(target=rebuild_profile)
        profile_thread.start()
        # The profile rebuild must wait on the same User row lock.
        self.assertFalse(profile_finished.wait(timeout=0.5))
        allow_identity_commit.set()
        identity_thread.join(timeout=10)
        profile_thread.join(timeout=10)
        self.assertFalse(identity_thread.is_alive())
        self.assertFalse(profile_thread.is_alive())
        self.assertEqual(errors, [])
        profile.refresh_from_db()
        user.refresh_from_db()
        self.assertEqual(user.email, 'newprivateid@example.invalid')
        self.assertTrue(profile.public_content_safe)
        self.assertEqual(profile.public_display_name, '[…]')
        self.assertEqual(profile.searchable_display_name, '')
