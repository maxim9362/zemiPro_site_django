"""Stage 02: Ashdod-only first-pilot server-side visibility and write gates.

Existing broad-geo tests intentionally use the unrestricted synthetic test
configuration. These cases explicitly enable the actual deployed pilot gate.
"""
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.translation import override

from apps.accounts.forms import ClientProfileForm, WorkerProfileForm
from apps.accounts.services import (
    create_client_profile, create_or_update_client_profile,
    create_or_update_worker_profile,
)
from apps.accounts.models import WorkerProfile
from apps.locations.models import City, CityAlias
from apps.locations.services import city_is_public, get_active_cities, get_public_cities
from apps.marketplace.forms import OrderCreateForm
from apps.marketplace.models import Category, Order, Response
from apps.marketplace.services import (
    create_order, create_response, get_available_orders_for_worker,
    workers_serving_city,
)
from apps.marketplace.tests.factories import make_order, make_user


@override_settings(ZEMIPRO_PILOT_CITY_SLUG='ashdod')
class AshdodPilotPublicAccessTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ashdod = City.objects.create(
            slug='ashdod', name_ru='Ашдод', name_en='Ashdod', name_he='אשדוד',
        )
        cls.other = City.objects.create(
            slug='ashkelon', name_ru='Ашкелон', name_en='Ashkelon',
            name_he='אשקלון',
        )
        cls.alias_ashdod = CityAlias.objects.create(
            slug='ashdod-old', city=cls.ashdod,
        )
        cls.alias_other = CityAlias.objects.create(
            slug='ashkelon-old', city=cls.other,
        )
        cls.category = Category.objects.create(
            slug='plumbing-pilot', name_ru='Ремонт сантехники',
            name_en='Plumbing repair', name_he='תיקון אינסטלציה',
        )
        cls.client_user = make_user('pilot-customer')
        cls.worker_user = make_user('ashdod-pilot-worker')
        cls.other_worker = make_user('other-city-worker')
        cls.worker = WorkerProfile.objects.create(
            user=cls.worker_user, city=cls.ashdod,
            description='Synthetic worker for city-scope verification.',
        )
        cls.worker.skills.add(cls.category)
        cls.off_pilot_worker = WorkerProfile.objects.create(
            user=cls.other_worker, city=cls.other,
            description='Synthetic worker serving only a different city.',
        )
        cls.off_pilot_worker.skills.add(cls.category)

    def payload(self, city):
        return {
            'customer_name': 'Synthetic Client',
            'customer_phone': '0501234567',
            'category': str(self.category.pk),
            'city': str(city.pk),
            'address': 'Synthetic street 11',
            'description': 'Synthetic plumbing request with enough details for validation.',
            'price': 'Договорная',
        }

    def test_public_city_query_and_original_records_preserved(self):
        self.assertEqual(
            list(get_public_cities().values_list('slug', flat=True)), ['ashdod'],
        )
        self.assertEqual(
            list(get_active_cities().values_list('slug', flat=True)), ['ashdod'],
        )
        self.assertTrue(city_is_public(self.ashdod))
        self.assertFalse(city_is_public(self.other))
        self.assertEqual(City.objects.count(), 2)
        self.assertTrue(City.objects.filter(pk=self.other.pk, is_active=True).exists())

    def test_city_list_legacy_and_ru_en_he_shows_only_ashdod(self):
        legacy = self.client.get(reverse('marketplace:cities_list'))
        self.assertEqual(legacy.status_code, 200)
        self.assertEqual(
            list(legacy.context['cities'].values_list('slug', flat=True)), ['ashdod'],
        )
        for language in ('ru', 'en', 'he'):
            with self.subTest(language=language), override(language):
                url = reverse('catalog_i18n:cities_list')
                response = self.client.get(url, HTTP_ACCEPT_LANGUAGE=language)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    list(response.context['cities'].values_list('slug', flat=True)),
                    ['ashdod'],
                )

    def test_direct_urls_and_aliases_outside_ashdod_are_not_public(self):
        self.assertEqual(self.client.get(
            reverse('marketplace:city_detail', args=[self.ashdod.slug]),
        ).status_code, 200)
        self.assertEqual(self.client.get(
            reverse('marketplace:city_detail', args=[self.other.slug]),
        ).status_code, 404)
        for language in ('ru', 'en', 'he'):
            with self.subTest(language=language), override(language):
                allowed = reverse('catalog_i18n:city_detail', args=['ashdod'])
                other = reverse('catalog_i18n:city_detail', args=['ashkelon'])
                alias_allowed = reverse(
                    'catalog_i18n:city_detail', args=[self.alias_ashdod.slug],
                )
                alias_other = reverse(
                    'catalog_i18n:city_detail', args=[self.alias_other.slug],
                )
                self.assertEqual(self.client.get(allowed).status_code, 200)
                self.assertEqual(self.client.get(other).status_code, 404)
                self.assertEqual(self.client.get(alias_other).status_code, 404)
                self.assertRedirects(
                    self.client.get(alias_allowed), allowed,
                    status_code=301, fetch_redirect_response=False,
                )
        self.assertEqual(self.client.get(
            reverse('marketplace:city_detail', args=[self.alias_ashdod.slug]),
        ).status_code, 404)

    def test_category_page_does_not_advertise_out_of_city_workers(self):
        url = reverse('marketplace:category_detail', args=[self.category.slug])
        for query in ({}, {'city': 'ashdod'}, {'city': 'ashkelon'}):
            with self.subTest(query=query):
                response = self.client.get(url, query)
                self.assertEqual(response.status_code, 200)
                names = {
                    profile.user.username
                    for profile in response.context['page_obj'].object_list
                }
                if query.get('city') == 'ashkelon':
                    self.assertEqual(names, set())
                else:
                    self.assertEqual(names, {'ashdod-pilot-worker'})
        self.assertEqual(
            workers_serving_city(
                WorkerProfile.objects.all(), self.other, category=self.category,
            ).count(), 0,
        )
        for language in ('ru', 'en', 'he'):
            with override(language):
                response = self.client.get(
                    reverse('catalog_i18n:category_detail',
                            args=[self.category.slug]),
                )
                names = {
                    profile.user.username
                    for profile in response.context['page_obj'].object_list
                }
                self.assertEqual(names, {'ashdod-pilot-worker'})

    def test_public_worker_profile_blocks_other_city_profiles(self):
        allowed = reverse(
            'marketplace:worker_public_profile', args=[self.worker.pk],
        )
        unavailable = reverse(
            'marketplace:worker_public_profile', args=[self.off_pilot_worker.pk],
        )
        self.assertEqual(self.client.get(allowed).status_code, 200)
        self.assertEqual(self.client.get(unavailable).status_code, 404)

    def test_forms_offer_only_ashdod_including_service_zones(self):
        for form in (ClientProfileForm(), WorkerProfileForm(), OrderCreateForm()):
            self.assertEqual(
                list(form.fields['city'].queryset.values_list('slug', flat=True)),
                ['ashdod'],
            )
        profile_form = WorkerProfileForm()
        self.assertEqual(
            list(profile_form.fields['service_cities'].queryset.values_list(
                'slug', flat=True,
            )), ['ashdod'],
        )
        self.assertFalse(OrderCreateForm(self.payload(self.other)).is_valid())
        self.assertIn('city', OrderCreateForm(self.payload(self.other)).errors)
        self.assertTrue(OrderCreateForm(self.payload(self.ashdod)).is_valid())
        self.assertFalse(ClientProfileForm({
            'city': self.other.pk, 'contact': 'synthetic',
        }).is_valid())
        self.assertIn('city', ClientProfileForm({
            'city': self.other.pk, 'contact': 'synthetic',
        }).errors)
        self.assertFalse(WorkerProfileForm({
            'city': self.ashdod.pk, 'skills': [self.category.pk],
            'service_cities': [self.other.pk],
            'description': 'Synthetic professional profile with enough text.',
            'contact': 'synthetic', 'offers_remote': '',
        }).is_valid())

    def test_order_creation_rejects_forged_other_city_but_accepts_ashdod(self):
        self.client.force_login(self.client_user)
        url = reverse('marketplace:order_create')
        invalid = self.client.post(url, self.payload(self.other))
        self.assertEqual(invalid.status_code, 200)
        self.assertIn('city', invalid.context['form'].errors)
        self.assertEqual(Order.objects.count(), 0)
        valid = self.client.post(url, self.payload(self.ashdod))
        self.assertEqual(valid.status_code, 302)
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(Order.objects.get().city_id, self.ashdod.pk)
        self.assertEqual(Order.objects.get().client_id, self.client_user.pk)

    def test_service_create_order_rejects_other_city(self):
        with self.assertRaisesMessage(ValueError, 'Город пока не обслуживается'):
            create_order(
                self.client_user, self.category, self.other,
                'Synthetic address', 'Synthetic description long enough.',
            )
        self.assertEqual(Order.objects.count(), 0)
        order = create_order(
            self.client_user, self.category, self.ashdod,
            'Synthetic address', 'Synthetic description long enough.',
        )
        self.assertEqual(order.city_id, self.ashdod.pk)

    def test_order_feed_and_direct_responses_block_other_city(self):
        valid = make_order(
            client=self.client_user, category=self.category, city=self.ashdod,
        )
        historic = make_order(
            client=self.client_user, category=self.category, city=self.other,
        )
        self.worker.service_cities.set([self.ashdod, self.other])
        available = get_available_orders_for_worker(self.worker)
        self.assertEqual(list(available.values_list('pk', flat=True)), [valid.pk])
        self.client.force_login(self.worker_user)
        dashboard = self.client.get(reverse('marketplace:worker_dashboard'))
        self.assertEqual(dashboard.status_code, 200)
        self.assertEqual(
            [order.pk for order in dashboard.context['page_obj']], [valid.pk],
        )
        other_url = reverse('marketplace:order_respond', args=[historic.pk])
        self.assertEqual(self.client.get(other_url).status_code, 404)
        self.assertEqual(
            self.client.post(other_url, {'message': 'Forged response'}).status_code,
            404,
        )
        with self.assertRaisesMessage(ValueError, 'Город пока не обслуживается'):
            create_response(historic, self.worker_user, 'Direct crafted response')
        self.assertFalse(Response.objects.filter(order=historic).exists())
        # Existing nonpilot orders must remain readable by their owners.
        self.client.force_login(self.client_user)
        self.assertEqual(self.client.get(
            reverse('marketplace:order_detail', args=[historic.pk]),
        ).status_code, 200)
        self.assertEqual(Order.objects.filter(pk=historic.pk).count(), 1)

    def test_direct_profile_services_reject_out_of_city_without_partial_writes(self):
        other_client = make_user('direct-pilot-client')
        other_worker = make_user('direct-pilot-worker')
        with self.assertRaisesMessage(ValueError, 'Город пока не обслуживается'):
            create_client_profile(other_client, city=self.other)
        with self.assertRaisesMessage(ValueError, 'Город пока не обслуживается'):
            create_or_update_client_profile(
                other_client, {'city': self.other, 'contact': 'synthetic'},
            )
        with self.assertRaisesMessage(ValueError, 'Город обслуживания пока не доступен'):
            create_or_update_worker_profile(other_worker, {
                'city': self.ashdod, 'service_cities': [self.other],
            })
        self.assertFalse(hasattr(other_client, 'client_profile'))
        self.assertFalse(hasattr(other_worker, 'worker_profile'))
        self.assertEqual(
            create_client_profile(other_client, city=self.ashdod).city_id,
            self.ashdod.pk,
        )

    def test_inactive_ashdod_fails_closed(self):
        self.ashdod.is_active = False
        self.ashdod.save(update_fields=['is_active'])
        self.assertFalse(get_public_cities().exists())
        self.assertEqual(self.client.get(
            reverse('marketplace:cities_list'),
        ).context['cities'].count(), 0)
        self.assertEqual(self.client.get(
            reverse('marketplace:city_detail', args=['ashdod']),
        ).status_code, 404)
        self.assertEqual(self.client.get(
            reverse('marketplace:worker_public_profile', args=[self.worker.pk]),
        ).status_code, 404)
        self.assertFalse(OrderCreateForm(self.payload(self.ashdod)).is_valid())
        with self.assertRaisesMessage(ValueError, 'Город пока не обслуживается'):
            create_order(
                self.client_user, self.category, self.ashdod,
                'Synthetic address', 'Synthetic description',
            )
