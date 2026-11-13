"""Stage 05.6 synthetic PostgreSQL query, SEO and latency baseline.

Timings are observations, not acceptance thresholds; synthetic CI only.
"""
import json
from statistics import median
from time import perf_counter

from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils.translation import override

from apps.accounts.models import User, WorkerProfile
from apps.locations.models import City
from apps.marketplace.directory_search import WorkerDirectoryForm, search_worker_profiles
from apps.marketplace.models import Category, Subcategory


@override_settings(ZEMIPRO_PILOT_CITY_SLUG='ashdod')
class Stage05SearchBaselineTests(TestCase):
    WORKERS = 300

    @classmethod
    def setUpTestData(cls):
        cls.city = City.objects.create(
            slug='ashdod', name_ru='Ашдод', name_en='Ashdod', name_he='אשדוד',
        )
        cls.category = Category.objects.create(
            slug='perf-056-category', name_ru='Ремонт', name_en='Repair',
            name_he='תיקונים', work_mode='both',
        )
        cls.service = Subcategory.objects.create(
            category=cls.category, slug='perf-056-service',
            name_ru='Консультация', name_en='Consultation',
            name_he='ייעוץ', work_mode='both',
        )
        users = User.objects.bulk_create([
            User(username=f'perf-056-user-{i:04}', password='!')
            for i in range(cls.WORKERS)
        ], batch_size=400)
        profiles = WorkerProfile.objects.bulk_create([
            WorkerProfile(
                user_id=user.pk, city=cls.city, is_published=True,
                display_name=f'Synthetic Specialist {i:04}',
                description='Synthetic directory benchmark service description.',
                pricing_details='Quotation on request',
                starting_price_ils=100 + (i % 125),
                spoken_languages=['ru', 'he'], offers_remote=bool(i % 2),
            )
            for i, user in enumerate(users)
        ], batch_size=400)
        skills = WorkerProfile.skills.through
        services = WorkerProfile.services.through
        skills.objects.bulk_create([
            skills(workerprofile_id=p.pk, category_id=cls.category.pk)
            for p in profiles
        ], batch_size=400)
        services.objects.bulk_create([
            services(workerprofile_id=p.pk, subcategory_id=cls.service.pk)
            for p in profiles
        ], batch_size=400)

    def test_no_n_plus_one_when_growing_from_20_to_300_workers(self):
        ids = list(WorkerProfile.objects.order_by('pk').values_list('pk', flat=True))
        WorkerProfile.objects.filter(pk__in=ids[20:]).update(is_published=False)
        url = reverse('marketplace:worker_directory')
        params = {'service': self.service.pk}
        with CaptureQueriesContext(connection) as small:
            response = self.client.get(url, params)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['page_obj'].object_list), 10)
        WorkerProfile.objects.filter(pk__in=ids[20:]).update(is_published=True)
        with CaptureQueriesContext(connection) as large:
            response = self.client.get(url, params)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['page_obj'].object_list), 10)
        self.assertEqual(response.context['page_obj'].paginator.count, self.WORKERS)
        self.assertLessEqual(len(large), len(small) + 2)
        self.assertLessEqual(len(large), 30)

    def test_measured_postgres_baseline_and_explain(self):
        self.assertEqual(connection.vendor, 'postgresql')
        scenarios = {
            'unfiltered': {},
            'complex': {
                'category': str(self.category.pk),
                'service': str(self.service.pk), 'city': str(self.city.pk),
                'language': 'ru', 'mode': 'online',
                'availability': 'available', 'price_to': '200',
                'sort': 'relevance',
            },
            'keyword': {'q': 'Synthetic', 'sort': 'rating'},
            'empty': {'q': 'IMPOSSIBLE_SEARCH_056'},
            'invalid': {'language': 'invalid-locale'},
        }
        samples = {}
        for case, params in scenarios.items():
            url = reverse('marketplace:worker_directory')
            self.client.get(url, params)  # warm-up
            timings, counts, results = [], [], []
            for _ in range(3):
                start = perf_counter()
                with CaptureQueriesContext(connection) as queries:
                    response = self.client.get(url, params)
                timings.append((perf_counter() - start) * 1000)
                counts.append(len(queries))
                self.assertEqual(response.status_code, 200)
                results.append(response.context['page_obj'].paginator.count)
            self.assertEqual(len(set(counts)), 1)
            self.assertEqual(len(set(results)), 1)
            self.assertLessEqual(counts[0], 30)
            if case in ('empty', 'invalid'):
                self.assertEqual(results[0], 0)
            samples[case] = {
                'query_count': counts[0],
                'latency_p50_ms': round(median(timings), 2),
                'result_count': results[0],
            }

        form = WorkerDirectoryForm(scenarios['complex'])
        self.assertTrue(form.is_valid(), form.errors)
        plan = search_worker_profiles(form).explain(format='TEXT', analyze=False)
        self.assertTrue(plan.strip())
        with connection.cursor() as cursor:
            indexes = connection.introspection.get_constraints(
                cursor, 'accounts_worker_profile',
            )
        self.assertIn('worker_public_search_idx', indexes)
        report = {
            'database': 'isolated synthetic PostgreSQL',
            'postgres_major': connection.pg_version // 10000,
            'workers': self.WORKERS,
            'page_size': 10,
            'samples_per_scenario': 3,
            'explain_root': plan.splitlines()[0].strip()[:140],
            'explain_has_index_scan': 'Index Scan' in plan or 'Index Only Scan' in plan,
            'scenarios': samples,
        }
        print('STAGE05_SEARCH_BASELINE ' + json.dumps(
            report, sort_keys=True, ensure_ascii=True,
        ), flush=True)

    def test_stable_pagination_and_invalid_parameters(self):
        url = reverse('marketplace:worker_directory')
        params = {'service': str(self.service.pk), 'sort': 'price_asc'}
        first = self.client.get(url, params)
        second = self.client.get(url, {**params, 'page': '2'})
        again = self.client.get(url, params)
        ids1 = [p.pk for p in first.context['page_obj'].object_list]
        ids2 = [p.pk for p in second.context['page_obj'].object_list]
        self.assertEqual(len(ids1), 10)
        self.assertEqual(len(ids2), 10)
        self.assertEqual(ids1, [p.pk for p in again.context['page_obj'].object_list])
        self.assertFalse(set(ids1) & set(ids2))
        self.assertContains(second, f'service={self.service.pk}')
        self.assertContains(second, 'sort=price_asc')
        invalid = self.client.get(url, {'service': 'bogus', 'city': '999999'})
        self.assertEqual(invalid.context['page_obj'].paginator.count, 0)
        self.assertContains(invalid, 'aria-invalid="true"')
        self.assertContains(invalid, 'noindex,follow')

    def test_canonical_hreflang_and_noindex_never_mass_indexes(self):
        for lang in ('ru', 'en', 'he'):
            with self.subTest(lang=lang), override(lang):
                path = reverse('catalog_i18n:worker_directory')
                response = self.client.get(
                    path, {'service': self.service.pk, 'page': '2'},
                    HTTP_ACCEPT_LANGUAGE=lang,
                )
                self.assertContains(response, 'name="robots" content="noindex,follow"')
                self.assertContains(
                    response, f'<link rel="canonical" href="http://testserver{path}">',
                )
                self.assertContains(response, f'<html lang="{lang}"')
                for alt in ('ru', 'en', 'he'):
                    self.assertContains(response, f'hreflang="{alt}"')
                self.assertNotContains(
                    response, 'canonical" href="http://testserver' + path + '?',
                )
        legacy = self.client.get(
            reverse('marketplace:worker_directory'),
            {'q': 'never_match', 'page': '9999999999'},
        )
        self.assertContains(legacy, '<link rel="canonical" href="http://testserver/workers/">')
        self.assertContains(legacy, 'noindex,follow')
