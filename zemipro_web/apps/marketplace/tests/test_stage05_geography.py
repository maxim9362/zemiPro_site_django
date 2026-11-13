"""Stage 05.2: synthetic city/neighborhood and service-mode correctness."""
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.forms import WorkerProfileForm
from apps.accounts.models import WorkerProfile
from apps.accounts.services import publication_issue, create_or_update_worker_profile
from apps.locations.models import City, Neighborhood
from apps.marketplace.directory_search import WorkerDirectoryForm, search_worker_profiles
from apps.marketplace.models import Category, Subcategory
from apps.marketplace.services import workers_serving_city


class AreaAndServiceModeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ashdod = City.objects.create(
            slug='ashdod', name_ru='Ашдод', name_en='Ashdod', name_he='אשדוד',
        )
        cls.ashkelon = City.objects.create(
            slug='ashkelon', name_ru='Ашкелон', name_en='Ashkelon',
            name_he='אשקלון',
        )
        cls.area_a = Neighborhood.objects.create(
            city=cls.ashdod, slug='synthetic-area-a', name_ru='Синтетический район A',
            name_en='Synthetic Area A', name_he='אזור בדיקה א',
        )
        cls.area_b = Neighborhood.objects.create(
            city=cls.ashdod, slug='synthetic-area-b', name_ru='Синтетический район B',
            name_en='Synthetic Area B', name_he='אזור בדיקה ב',
        )
        cls.other_area = Neighborhood.objects.create(
            city=cls.ashkelon, slug='synthetic-area-a', name_ru='Синтетический район C',
        )
        cls.legal = Category.objects.create(
            slug='geo-legal-052', name_ru='Синтетические консультации',
            work_mode='both',
        )
        cls.legal_onsite = Subcategory.objects.create(
            category=cls.legal, slug='only-onsite-052',
            name_ru='Очный приём', work_mode='onsite',
        )
        cls.legal_remote = Subcategory.objects.create(
            category=cls.legal, slug='only-online-052',
            name_ru='Дистанционная консультация', work_mode='online',
        )
        cls.legal_both = Subcategory.objects.create(
            category=cls.legal, slug='both-052',
            name_ru='Услуга в двух форматах', work_mode='both',
        )
        cls.local_worker = cls._worker('geo052-local', cls.ashdod, remote=False)
        cls.local_worker.skills.add(cls.legal)
        cls.local_worker.services.add(cls.legal_onsite, cls.legal_both)
        cls.local_worker.service_cities.add(cls.ashdod)
        cls.local_worker.service_neighborhoods.add(cls.area_a)
        cls.citywide_worker = cls._worker('geo052-citywide', cls.ashdod, remote=False)
        cls.citywide_worker.skills.add(cls.legal)
        cls.citywide_worker.services.add(cls.legal_onsite)
        cls.cross_city_online = cls._worker('geo052-cross-city', cls.ashkelon, remote=True)
        cls.cross_city_online.skills.add(cls.legal)
        cls.cross_city_online.services.add(cls.legal_remote, cls.legal_onsite)
        cls.cross_city_online.service_cities.add(cls.ashkelon)
        cls.ashdod_online = cls._worker('geo052-ashdod-online', cls.ashdod, remote=True)
        cls.ashdod_online.skills.add(cls.legal)
        cls.ashdod_online.services.add(cls.legal_remote, cls.legal_onsite)
        cls.ashdod_online.service_cities.add(cls.ashkelon)

    @classmethod
    def _worker(cls, name, city, *, remote):
        user = get_user_model().objects.create_user(username=name)
        return WorkerProfile.objects.create(
            user=user, city=city, display_name='Synthetic '+name,
            description='Synthetic service specialist for geography checks.',
            pricing_details='Price by agreement', spoken_languages=['ru'],
            is_published=True, offers_remote=remote,
        )

    def search(self, params, *, pilot='ashdod'):
        with override_settings(ZEMIPRO_PILOT_CITY_SLUG=pilot):
            form = WorkerDirectoryForm(params)
            self.assertTrue(form.is_valid(), form.errors)
            return set(search_worker_profiles(form).values_list('pk', flat=True))

    def test_pilot_area_filter_narrows_onsite_not_citywide(self):
        a = self.search({
            'category': self.legal.pk, 'service': self.legal_onsite.pk,
            'city': self.ashdod.pk, 'mode': 'onsite', 'neighborhood': self.area_a.pk,
        })
        b = self.search({
            'service': self.legal_onsite.pk, 'city': self.ashdod.pk,
            'mode': 'onsite', 'neighborhood': self.area_b.pk,
        })
        self.assertEqual(a, {self.local_worker.pk, self.citywide_worker.pk})
        self.assertEqual(b, {self.citywide_worker.pk})
        whole = self.search({
            'service': self.legal_onsite.pk, 'city': self.ashdod.pk, 'mode': 'onsite',
        })
        self.assertIn(self.local_worker.pk, whole)

    def test_online_specialist_outside_selected_area_but_inside_pilot(self):
        params = {
            'service': self.legal_remote.pk, 'city': self.ashdod.pk,
            'neighborhood': self.area_b.pk,
        }
        self.assertEqual(
            self.search({**params, 'mode': 'online'}),
            {self.ashdod_online.pk},
        )
        self.assertEqual(self.search({**params, 'mode': 'onsite'}), set())
        self.assertEqual(self.search(params), {self.ashdod_online.pk})

    def test_exact_onsite_service_never_inherits_online_category_mode(self):
        params = {
            'service': self.legal_onsite.pk, 'city': self.ashdod.pk,
            'neighborhood': self.area_b.pk,
        }
        self.assertEqual(self.search({**params, 'mode': 'online'}), set())
        self.assertNotIn(self.ashdod_online.pk, self.search(params))
        self.assertEqual(
            self.search({**params, 'mode': 'onsite'}),
            {self.citywide_worker.pk},
        )

    def test_remote_worker_in_other_home_city_only_when_pilot_disabled(self):
        params = {
            'service': self.legal_remote.pk,
            'city': self.ashdod.pk, 'mode': 'online',
        }
        self.assertEqual(
            self.search(params), {self.ashdod_online.pk},
        )
        self.assertEqual(
            self.search(params, pilot=None),
            {self.ashdod_online.pk, self.cross_city_online.pk},
        )
        onsite = self.search({
            'service': self.legal_onsite.pk,
            'city': self.ashdod.pk, 'mode': 'onsite',
        }, pilot=None)
        self.assertNotIn(self.cross_city_online.pk, onsite)

    def test_no_invented_neighborhood_and_cross_city_fails_closed(self):
        with override_settings(ZEMIPRO_PILOT_CITY_SLUG='ashdod'):
            invalid = (
                {'city': self.ashdod.pk, 'neighborhood': self.other_area.pk},
                {'city': self.ashdod.pk, 'neighborhood': self.area_b.pk,
                 'service': 'not-a-number'},
            )
            for params in invalid:
                with self.subTest(params=params):
                    form = WorkerDirectoryForm(params)
                    self.assertFalse(form.is_valid())
                    self.assertFalse(search_worker_profiles(form).exists())
            with override_settings(ZEMIPRO_PILOT_CITY_SLUG=None):
                form = WorkerDirectoryForm({
                    'city': self.ashdod.pk, 'neighborhood': self.other_area.pk,
                })
                self.assertFalse(form.is_valid())
                self.assertFalse(search_worker_profiles(form).exists())
            self.assertFalse(workers_serving_city(
                WorkerProfile.objects.all(), self.ashdod,
                neighborhood=self.other_area,
            ).exists())
            self.assertFalse(workers_serving_city(
                WorkerProfile.objects.all(), self.ashkelon,
            ).exists())

    def test_server_rejects_undeclared_service_and_inactive_area(self):
        with override_settings(ZEMIPRO_PILOT_CITY_SLUG=None):
            only_onsite = workers_serving_city(
                WorkerProfile.objects.all(), self.ashdod,
                service=self.legal_onsite, mode='onsite',
                neighborhood=self.area_b,
            )
            self.assertEqual(
                set(only_onsite.values_list('pk', flat=True)),
                {self.citywide_worker.pk},
            )
            self.assertFalse(workers_serving_city(
                WorkerProfile.objects.all(), self.ashdod,
                service=self.legal_both, mode='online',
            ).exists())
        self.area_a.is_active = False
        self.area_a.save(update_fields=['is_active'])
        self.assertFalse(workers_serving_city(
            WorkerProfile.objects.all(), self.ashdod, neighborhood=self.area_a,
        ).exists())

    def test_form_and_owner_service_enforce_area_city_scope(self):
        with override_settings(ZEMIPRO_PILOT_CITY_SLUG='ashdod'):
            profile_form = WorkerProfileForm()
            self.assertEqual(
                set(profile_form.fields['service_neighborhoods'].queryset),
                {self.area_a, self.area_b},
            )
            data = {
                'provider_type': 'individual',
                'display_name': self.local_worker.display_name,
                'city': self.ashdod.pk,
                'description': self.local_worker.description,
                'pricing_details': self.local_worker.pricing_details,
                'spoken_languages': ['ru'],
                'skills': [self.legal.pk],
                'services': [self.legal_onsite.pk],
                'service_cities': [self.ashdod.pk],
                'service_neighborhoods': [self.other_area.pk],
            }
            form = WorkerProfileForm(data, instance=self.local_worker)
            self.assertFalse(form.is_valid())
            self.assertIn('service_neighborhoods', form.errors)
            with self.assertRaises(ValueError):
                create_or_update_worker_profile(
                    self.local_worker.user,
                    {'service_neighborhoods': [self.other_area]},
                )
            self.local_worker.service_neighborhoods.add(self.other_area)
            self.assertIsNotNone(publication_issue(self.local_worker))

    def test_neighborhood_aliases_are_not_confused_between_cities(self):
        self.assertEqual(
            Neighborhood.objects.filter(slug='synthetic-area-a').count(), 2,
        )
        with override_settings(ZEMIPRO_PILOT_CITY_SLUG='ashdod'):
            response = self.client.get(reverse('marketplace:worker_directory'), {
                'city': self.ashdod.pk, 'neighborhood': self.area_a.pk,
                'service': self.legal_onsite.pk, 'mode': 'onsite',
            })
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'geo052-local')
            self.assertNotContains(response, 'geo052-cross-city')
