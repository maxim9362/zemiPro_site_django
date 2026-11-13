"""Stage 05.3 deterministic ranking and privacy-focused audit regressions."""
from decimal import Decimal
from unittest.mock import patch

from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import override

from apps.accounts.models import WorkerPortfolioPhoto, WorkerProfile
from apps.locations.models import City, Neighborhood
from apps.marketplace.directory_ranking import (
    RANKING_VERSION, explain_public_rank,
)
from apps.marketplace.directory_search import WorkerDirectoryForm, search_worker_profiles
from apps.marketplace.models import Category, Rating, Subcategory
from apps.marketplace.tests.factories import make_order, make_user


@override_settings(ZEMIPRO_PILOT_CITY_SLUG='ashdod')
class DirectoryRankingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ashdod = City.objects.create(
            slug='ashdod', name_ru='Ашдод', name_en='Ashdod', name_he='אשדוד',
        )
        cls.ashkelon = City.objects.create(
            slug='ashkelon', name_ru='Ашкелон',
        )
        cls.category = Category.objects.create(
            slug='rank-053', name_ru='Тестовая помощь по дому',
            name_en='Synthetic home help', name_he='עזרה בבית',
            work_mode='both',
        )
        cls.service = Subcategory.objects.create(
            category=cls.category, slug='rank-service-053',
            name_ru='Синтетическая установка',
            name_en='Synthetic installation', name_he='התקנה לבדיקה',
            work_mode='both',
        )
        cls.area = Neighborhood.objects.create(
            city=cls.ashdod, slug='synthetic-zone-053',
            name_ru='Синтетический район', name_en='Synthetic area',
            name_he='אזור בדיקה',
        )
        cls.owner = make_user('ranking-review-owner')
        cls.rich = cls.create_worker(
            'Ranking Rich', availability='limited', price='120.00',
            hours='Sunday - Thursday', services=True,
        )
        cls.rich.service_cities.add(cls.ashdod)
        cls.rich.service_neighborhoods.add(cls.area)
        WorkerPortfolioPhoto.objects.create(
            worker=cls.rich, file_key='stage05-ranking-fixture-no-actual-file',
            caption='Synthetic public work', is_public=True,
            rights_confirmed_at=timezone.now(),
        )
        cls.rated = cls.create_worker(
            'Ranking Rated', availability='available', services=True,
        )
        for index in range(3):
            order = make_order(
                client=cls.owner, category=cls.category, city=cls.ashdod,
                description=f'Synthetic order for verified review {index}',
            )
            Rating.objects.create(
                order=order, client=cls.owner, worker=cls.rated.user,
                rating=5, review_text=f'Synthetic historical review {index}',
            )
        cls.unrated = cls.create_worker(
            'Ranking Unrated', availability='available', services=True,
        )
        cls.category_only = cls.create_worker(
            'Ranking Category Only', availability='available', services=False,
        )
        cls.remote = cls.create_worker(
            'Ranking Remote', availability='available', services=True, remote=True,
        )
        cls.remote.service_cities.add(cls.ashkelon)
        cls.unavailable = cls.create_worker(
            'Ranking Not Available', availability='unavailable', services=True,
        )

    @classmethod
    def create_worker(cls, label, *, availability, services, remote=False,
                      price=None, hours=''):
        user = make_user('user-' + label.lower().replace(' ', '-'))
        worker = WorkerProfile.objects.create(
            user=user, city=cls.ashdod, display_name=label,
            description='Synthetic public description; DO_NOT_LOG_ADDRESS_053',
            contact='DO_NOT_LOG_PHONE_053',
            pricing_details='Negotiated by agreement',
            starting_price_ils=Decimal(price) if price is not None else None,
            working_hours=hours, spoken_languages=['he', 'en'],
            availability=availability, offers_remote=remote,
            is_published=True,
        )
        worker.skills.add(cls.category)
        if services:
            worker.services.add(cls.service)
        return worker

    def results(self, params=None):
        form = WorkerDirectoryForm(params or {})
        self.assertTrue(form.is_valid(), form.errors)
        return list(search_worker_profiles(form))

    def test_default_relevance_weights_are_public_and_deterministic(self):
        result = self.results({'service': self.service.pk, 'mode': 'onsite'})
        self.assertEqual(result[0].pk, self.rated.pk)
        self.assertEqual(result[0].rank_service, 40)
        self.assertEqual(result[0].rank_zone, 10)
        self.assertEqual(result[0].rank_profile, 4)
        self.assertEqual(result[0].rank_availability, 12)
        self.assertEqual(result[0].rank_reviews, 10)
        self.assertEqual(result[0].rank_score, 76)
        self.assertNotIn(self.category_only.pk, {item.pk for item in result})
        self.assertNotIn(self.remote.pk, {item.pk for item in result})
        rich = next(item for item in result if item.pk == self.rich.pk)
        self.assertEqual(rich.rank_zone, 14)
        self.assertEqual(rich.rank_profile, 10)
        self.assertEqual(rich.rank_reviews, 0)
        self.assertEqual(rich.rank_score, 70)
        self.assertEqual(result[0].avg_rating, 5)
        self.assertEqual(result[0].review_count, 3)

    def test_zone_priority_respects_specific_neighborhood(self):
        base = {
            'service': self.service.pk, 'city': self.ashdod.pk,
            'neighborhood': self.area.pk, 'mode': 'onsite',
        }
        matching = self.results(base)
        self.assertEqual(
            {row.pk: row.rank_zone for row in matching}[self.rich.pk], 17,
        )
        self.assertEqual(
            {row.pk: row.rank_zone for row in matching}[self.rated.pk], 10,
        )
        remote = self.results({**base, 'mode': 'online'})
        self.assertTrue(all(item.rank_zone == 6 for item in remote))
        self.assertIn(self.remote.pk, {item.pk for item in remote})

    def test_review_bonus_never_invents_user_rating(self):
        result = self.results({'sort': 'relevance'})
        by_id = {item.pk: item for item in result}
        self.assertEqual(by_id[self.rated.pk].rank_reviews, 10)
        self.assertEqual(by_id[self.rated.pk].review_count, 3)
        self.assertEqual(by_id[self.unrated.pk].rank_reviews, 0)
        self.assertEqual(by_id[self.unrated.pk].review_count, 0)
        self.assertIsNone(by_id[self.unrated.pk].avg_rating)
        self.assertEqual(by_id[self.unavailable.pk].rank_availability, 0)
        self.assertLess(
            by_id[self.unavailable.pk].rank_score,
            by_id[self.rated.pk].rank_score,
        )
        reasons = explain_public_rank(
            by_id[self.unrated.pk], city=self.ashdod,
        )
        codes = [code for code, _ in reasons]
        self.assertNotIn('reviews', codes)
        self.assertIn('available', codes)

    def test_one_real_review_has_smaller_bonus_than_three(self):
        one = self.create_worker(
            'Ranking One Review', availability='available', services=True,
        )
        order = make_order(
            client=self.owner, category=self.category, city=self.ashdod,
        )
        Rating.objects.create(
            order=order, client=self.owner, worker=one.user, rating=5,
        )
        rows = {row.pk: row for row in self.results()}
        self.assertEqual(rows[one.pk].rank_reviews, 5)
        self.assertEqual(rows[one.pk].review_count, 1)
        self.assertEqual(rows[self.rated.pk].rank_reviews, 10)

    def test_keyword_category_and_exact_service_scores(self):
        broad = self.results({'category': self.category.pk})
        self.assertTrue(all(item.rank_service == 25 for item in broad))
        exact = self.results({'service': self.service.pk})
        self.assertTrue(all(item.rank_service == 40 for item in exact))
        keyword = self.results({'q': 'Ranking Rated'})
        self.assertEqual([item.pk for item in keyword], [self.rated.pk])
        self.assertEqual(keyword[0].rank_keyword, 16)
        keyword_service = self.results({'q': 'Синтетическая установка'})
        self.assertTrue(keyword_service)
        self.assertTrue(all(item.rank_keyword == 12 for item in keyword_service))

    def test_manual_sorts_and_stable_tie_break(self):
        ids = [item.pk for item in self.results({'service': self.service.pk})]
        tied = self.results({'service': self.service.pk})
        for first, second in zip(tied, tied[1:]):
            if first.rank_score == second.rank_score and first.review_count == second.review_count:
                self.assertLess(first.pk, second.pk)
        self.assertEqual(ids, [i.pk for i in self.results({'service': self.service.pk})])
        twin_a = self.create_worker(
            'Ranking Twin A', availability='available', services=True,
        )
        twin_b = self.create_worker(
            'Ranking Twin B', availability='available', services=True,
        )
        ordered = self.results({'service': self.service.pk})
        positions = {row.pk: i for i, row in enumerate(ordered)}
        self.assertEqual(
            next(row.rank_score for row in ordered if row.pk == twin_a.pk),
            next(row.rank_score for row in ordered if row.pk == twin_b.pk),
        )
        self.assertLess(positions[twin_a.pk], positions[twin_b.pk])
        self.assertEqual(self.results({'sort': 'rating'})[0].pk, self.rated.pk)
        self.assertEqual(self.results({'sort': 'price_asc'})[0].pk, self.rich.pk)
        self.assertEqual(self.results({'sort': 'name'})[0].display_name, 'Ranking Category Only')
        self.assertFalse(WorkerDirectoryForm({'sort': 'paid'}).is_valid())

    def test_audit_emits_only_safe_codes_and_persisted_score_fields(self):
        url = reverse('marketplace:worker_directory')
        with patch('apps.marketplace.directory_ranking.LOGGER.info') as audit:
            response = self.client.get(url, {'q': 'Ranking', 'sort': 'relevance'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(audit.call_count, 1)
        call = audit.call_args
        self.assertEqual(call.args, ('directory_ranking_page',))
        extra = call.kwargs['extra']
        self.assertEqual(extra['ranking_version'], RANKING_VERSION)
        self.assertEqual(extra['ranking_sort'], 'relevance')
        self.assertGreater(len(extra['ranking_rows']), 1)
        expected_keys = {
            'worker_profile_id', 'position', 'score', 'service', 'keyword',
            'area', 'availability', 'profile', 'reviews', 'reasons',
        }
        self.assertTrue(all(set(row) == expected_keys for row in extra['ranking_rows']))
        serialized = repr(extra)
        for marker in (
            'DO_NOT_LOG_PHONE_053', 'DO_NOT_LOG_ADDRESS_053',
            'Ranking Rich', 'ranking-review-owner', 'query', 'email',
        ):
            self.assertNotIn(marker, serialized)
        self.assertContains(response, 'Почему этот специалист в результатах:')
        self.assertNotContains(response, 'DO_NOT_LOG_PHONE_053')
        with patch('apps.marketplace.directory_ranking.LOGGER.info') as silent:
            self.client.get(url, {'sort': 'rating'})
        silent.assert_not_called()

    def test_ranking_is_capped_to_page_and_avoids_n_plus_one(self):
        url = reverse('marketplace:worker_directory')
        with CaptureQueriesContext(connection) as smaller:
            response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        for i in range(9):
            self.create_worker(
                f'Pagination {i:02}', availability='available', services=True,
            )
        with patch('apps.marketplace.directory_ranking.LOGGER.info') as audit:
            with CaptureQueriesContext(connection) as larger:
                first = self.client.get(url)
        self.assertEqual(first.status_code, 200)
        self.assertLessEqual(len(larger), len(smaller) + 2)
        self.assertEqual(len(first.context['page_obj'].object_list), 10)
        self.assertEqual(len(audit.call_args.kwargs['extra']['ranking_rows']), 10)
        second = self.client.get(url, {'page': 2})
        self.assertEqual(second.status_code, 200)
        self.assertEqual(len(second.context['page_obj'].object_list), 5)
        self.assertEqual(
            {p.pk for p in first.context['page_obj']}.intersection(
                {p.pk for p in second.context['page_obj']}
            ),
            set(),
        )

    def test_reasons_are_translated_for_hebrew_and_english(self):
        url = reverse('catalog_i18n:worker_directory')
        for locale, snippet in (
            ('en', 'Why this professional appears in results'),
            ('he', 'מדוע איש המקצוע מופיע בתוצאות'),
        ):
            with self.subTest(language=locale), override(locale):
                response = self.client.get(url, HTTP_ACCEPT_LANGUAGE=locale)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, snippet)
                self.assertNotContains(response, 'DO_NOT_LOG_PHONE_053')
