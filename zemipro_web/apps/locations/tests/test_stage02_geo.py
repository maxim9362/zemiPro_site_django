"""Stage 02.2: stable Israeli city identities and multi-city service zones."""
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.urls import reverse
from django.utils.translation import override

from apps.accounts.forms import WorkerProfileForm
from apps.accounts.models import WorkerProfile
from apps.accounts.services import create_or_update_worker_profile
from apps.locations.models import City, CityAlias, District
from apps.marketplace.models import Category, Order
from apps.marketplace.services import get_available_orders_for_worker
from apps.marketplace.tests.factories import make_city, make_order, make_user


class Stage02GeographySeedTests(TestCase):
    def run_seed(self, *args):
        call_command('seed_israel_cities', *args, stdout=StringIO())

    def test_plan_does_not_touch_database_and_check_fails_before_seed(self):
        self.run_seed('--plan')
        self.assertEqual(District.objects.count(), 0)
        self.assertEqual(City.objects.count(), 0)
        self.assertEqual(CityAlias.objects.count(), 0)
        with self.assertRaises(CommandError):
            self.run_seed('--check')

    def test_seed_is_reentrant_and_preserves_primary_keys(self):
        self.run_seed()
        self.assertEqual(District.objects.count(), 6)
        self.assertEqual(City.objects.count(), 25)
        self.assertEqual(CityAlias.objects.count(), 4)
        keys = {
            'districts': list(District.objects.order_by('slug').values_list('slug', 'pk')),
            'cities': list(City.objects.order_by('slug').values_list('slug', 'pk')),
            'aliases': list(CityAlias.objects.order_by('slug').values_list('slug', 'city_id')),
        }
        self.run_seed('--check')
        self.run_seed()
        self.run_seed('--check')
        self.assertEqual(
            keys['districts'], list(District.objects.order_by('slug').values_list('slug', 'pk'))
        )
        self.assertEqual(
            keys['cities'], list(City.objects.order_by('slug').values_list('slug', 'pk'))
        )
        self.assertEqual(
            keys['aliases'],
            list(CityAlias.objects.order_by('slug').values_list('slug', 'city_id')),
        )
        self.assertFalse(City.objects.filter(name_en='').exists())
        self.assertFalse(City.objects.filter(name_he='').exists())
        self.assertEqual(
            CityAlias.objects.get(slug='petah-tiqwa').city.slug, 'petah-tikva',
        )

    def test_existing_city_ids_slugs_admin_edit_and_order_relation_survive(self):
        city = City.objects.create(
            slug='ashdod', name_ru='Ашдод редакция', is_active=False,
            name_en='Our Ashdod',
        )
        client = make_user('geo-client')
        category = Category.objects.create(slug='geo-cleaning', name_ru='Уборка')
        order = make_order(client=client, category=category, city=city)
        old = (city.pk, order.pk, order.city_id)
        self.run_seed()
        city.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(old, (city.pk, order.pk, order.city_id))
        self.assertEqual(city.slug, 'ashdod')
        self.assertEqual(city.name_ru, 'Ашдод редакция')
        self.assertEqual(city.name_en, 'Our Ashdod')
        self.assertFalse(city.is_active)
        self.assertEqual(city.district.slug, 'south')
        self.run_seed()
        city.refresh_from_db()
        self.assertFalse(city.is_active)
        self.assertEqual(city.name_en, 'Our Ashdod')

    def test_district_conflict_fails_closed_and_rolls_back_all_writes(self):
        conflicting = City.objects.create(
            slug='ashdod', name_ru='Ashdod Test',
            district=District.objects.create(slug='custom', name_ru='Custom'),
        )
        before = City.objects.count()
        with self.assertRaisesMessage(CommandError, 'different district'):
            self.run_seed()
        conflicting.refresh_from_db()
        self.assertEqual(conflicting.district.slug, 'custom')
        self.assertEqual(District.objects.count(), 1)
        self.assertEqual(City.objects.count(), before)

    def test_alias_shadowing_a_real_city_aborts_atomically(self):
        City.objects.create(slug='petah-tiqwa', name_ru='Another city')
        with self.assertRaisesMessage(CommandError, 'Alias conflicts'):
            self.run_seed()
        self.assertEqual(District.objects.count(), 0)
        self.assertEqual(CityAlias.objects.count(), 0)

    def test_corrupt_manifest_detected_before_writes(self):
        from apps.locations.management.commands import seed_israel_cities as module
        with patch.object(module, 'CITIES', [*module.CITIES, module.CITIES[0]]):
            with self.assertRaisesMessage(CommandError, 'Duplicate city slug'):
                self.run_seed()
        self.assertFalse(City.objects.exists())

    def test_hebrew_and_english_district_names(self):
        self.run_seed()
        ashkelon = City.objects.get(slug='ashkelon')
        with override('he'):
            self.assertEqual(ashkelon.localized_name, 'אשקלון')
            self.assertEqual(ashkelon.district.localized_name, 'הדרום')
        with override('en'):
            self.assertEqual(ashkelon.localized_name, 'Ashkelon')
            self.assertEqual(ashkelon.district.localized_name, 'Southern')


class Stage02WorkerServiceZonesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ashdod = make_city(slug='qa-ashdod')
        cls.ashkelon = make_city(slug='qa-ashkelon')
        cls.netanya = make_city(slug='qa-netanya')
        cls.owner = make_user('geo-owner')
        cls.worker = make_user('geo-worker')
        cls.profile = WorkerProfile.objects.create(user=cls.worker, city=cls.ashdod)
        cls.repair = Category.objects.create(
            slug='geo-repair', name_ru='Ремонт', work_mode='onsite',
        )
        cls.remote = Category.objects.create(
            slug='geo-tutoring', name_ru='Репетиторство', work_mode='both',
        )
        cls.profile.skills.add(cls.repair, cls.remote)

    def test_legacy_worker_uses_home_city_if_no_explicit_zones(self):
        city_url = lambda c: reverse('marketplace:city_detail', args=[c.slug])
        self.assertContains(self.client.get(city_url(self.ashdod)), 'geo-worker')
        self.assertNotContains(self.client.get(city_url(self.ashkelon)), 'geo-worker')

    def test_explicit_multiple_service_cities_filter_city_and_category(self):
        self.profile.service_cities.set([self.ashkelon, self.netanya])
        self.assertNotContains(self.client.get(
            reverse('marketplace:city_detail', args=[self.ashdod.slug])
        ), 'geo-worker')
        for city in (self.ashkelon, self.netanya):
            city_page = self.client.get(reverse('marketplace:city_detail', args=[city.slug]))
            repair_page = self.client.get(
                reverse('marketplace:category_detail', args=[self.repair.slug]),
                {'city': city.slug},
            )
            self.assertContains(city_page, 'geo-worker')
            self.assertContains(repair_page, 'geo-worker')

    def test_online_worker_matches_remote_category_not_local_repair(self):
        self.profile.service_cities.set([self.ashkelon])
        self.profile.offers_remote = True
        self.profile.save(update_fields=['offers_remote'])
        repair_page = self.client.get(
            reverse('marketplace:category_detail', args=[self.repair.slug]),
            {'city': self.netanya.slug},
        )
        remote_page = self.client.get(
            reverse('marketplace:category_detail', args=[self.remote.slug]),
            {'city': self.netanya.slug},
        )
        self.assertNotContains(repair_page, 'geo-worker')
        self.assertContains(remote_page, 'geo-worker')
        self.assertContains(self.client.get(
            reverse('marketplace:city_detail', args=[self.netanya.slug])
        ), 'geo-worker')

    def test_worker_form_accepts_selected_city_ids_and_rejects_unknown(self):
        valid = {
            'city': self.ashdod.pk,
            'contact': 'synthetic contact',
            'description': 'I can help with household and online tasks.',
            'skills': [self.remote.pk],
            'service_cities': [self.ashkelon.pk, self.netanya.pk],
            'offers_remote': 'on',
        }
        form = WorkerProfileForm(valid, instance=self.profile)
        self.assertTrue(form.is_valid(), form.errors.as_json())
        create_or_update_worker_profile(self.worker, form.cleaned_data)
        self.profile.refresh_from_db()
        self.assertEqual(
            set(self.profile.service_cities.values_list('pk', flat=True)),
            {self.ashkelon.pk, self.netanya.pk},
        )
        self.assertTrue(self.profile.offers_remote)
        self.assertEqual(self.profile.city_id, self.ashdod.pk)

        invalid = {**valid, 'service_cities': ['999999999']}
        form = WorkerProfileForm(invalid, instance=self.profile)
        self.assertFalse(form.is_valid())
        self.assertIn('service_cities', form.errors)

        inappropriate = {**valid, 'skills': [self.repair.pk]}
        form = WorkerProfileForm(inappropriate, instance=self.profile)
        self.assertFalse(form.is_valid())

    def test_order_feed_uses_service_zones_and_remote_work_mode(self):
        a = make_order(client=self.owner, category=self.repair, city=self.ashdod)
        b = make_order(client=self.owner, category=self.repair, city=self.ashkelon)
        c = make_order(client=self.owner, category=self.remote, city=self.netanya)
        self.assertEqual(
            set(get_available_orders_for_worker(self.profile).values_list('pk', flat=True)),
            {a.pk},
        )
        self.profile.service_cities.set([self.ashkelon])
        self.assertEqual(
            set(get_available_orders_for_worker(self.profile).values_list('pk', flat=True)),
            {b.pk},
        )
        self.profile.offers_remote = True
        self.profile.save(update_fields=['offers_remote'])
        self.assertEqual(
            set(get_available_orders_for_worker(self.profile).values_list('pk', flat=True)),
            {b.pk, c.pk},
        )
        self.profile.service_cities.clear()
        self.profile.offers_remote = False
        self.profile.save(update_fields=['offers_remote'])
        self.assertEqual(
            set(get_available_orders_for_worker(self.profile).values_list('pk', flat=True)),
            {a.pk},
        )

    def test_city_selection_uses_stable_id_and_unknown_slug_is_empty(self):
        url = reverse('marketplace:category_detail', args=[self.repair.slug])
        response = self.client.get(url, {'city': 'does-not-exist'})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'geo-worker')
        choices = WorkerProfileForm().fields['service_cities'].queryset
        self.assertIn(self.ashkelon, choices)
