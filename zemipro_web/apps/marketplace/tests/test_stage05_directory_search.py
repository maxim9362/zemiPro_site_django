"""Stage 05.1 — synthetic PostgreSQL directory/filter regressions."""
from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.translation import override

from apps.accounts.models import WorkerProfile
from apps.locations.models import City
from apps.marketplace.models import Category, Rating, Subcategory
from apps.marketplace.tests.factories import make_order, make_user


@override_settings(ZEMIPRO_PILOT_CITY_SLUG='ashdod')
class WorkerDirectorySearchTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.city = City.objects.create(
            slug='ashdod', name_ru='Ашдод', name_en='Ashdod', name_he='אשדוד',
        )
        cls.other_city = City.objects.create(
            slug='ashkelon', name_ru='Ашкелон', name_en='Ashkelon',
            name_he='אשקלון',
        )
        cls.plumbing = Category.objects.create(
            slug='qa-stage05-plumbing', name_ru='Сантехника',
            name_en='Plumbing', name_he='אינסטלציה', work_mode='onsite',
        )
        cls.legal = Category.objects.create(
            slug='qa-stage05-legal', name_ru='Юридические консультации',
            name_en='Legal advice', name_he='ייעוץ משפטי', work_mode='both',
        )
        cls.faucets = Subcategory.objects.create(
            category=cls.plumbing, slug='faucets', name_ru='Замена смесителей',
            name_en='Faucets', name_he='ברזים', work_mode='onsite',
        )
        cls.pipes = Subcategory.objects.create(
            category=cls.plumbing, slug='pipes', name_ru='Замена труб',
            name_en='Pipes', name_he='צינורות', work_mode='onsite',
        )
        cls.consulting = Subcategory.objects.create(
            category=cls.legal, slug='consulting', name_ru='Консультации онлайн',
            name_en='Online consultations', name_he='ייעוץ', work_mode='both',
        )
        cls.client_user = make_user('directory-client')
        cls.plumber_user = make_user(
            'directory-plumber', email='private-stage05@example.invalid',
            phone='+972500000051',
        )
        cls.plumber = WorkerProfile.objects.create(
            user=cls.plumber_user, city=cls.city,
            display_name='Real Plumbing Expert',
            contact='NEVER_PUBLIC_PHONE_051',
            description='Work with faucets in local homes, synthetic only.',
            pricing_details='Pricing depends on the job',
            starting_price_ils=Decimal('150.00'),
            spoken_languages=['ru', 'he'],
            availability='available', is_published=True,
        )
        cls.plumber.skills.add(cls.plumbing)
        cls.plumber.services.add(cls.faucets)

        cls.legacy_user = make_user('directory-category-only')
        cls.category_only = WorkerProfile.objects.create(
            user=cls.legacy_user, city=cls.city,
            display_name='Category only profile',
            description='Legacy category without a confirmed concrete service.',
            pricing_details='From 10 (unverified free text)',
            spoken_languages=['en'], is_published=True,
        )
        cls.category_only.skills.add(cls.plumbing)

        cls.online_user = make_user('directory-online')
        cls.online = WorkerProfile.objects.create(
            user=cls.online_user, city=cls.city,
            display_name='Online Advice',
            description='Remote service in legal consultations via web.',
            pricing_details='Ask for quotation',
            starting_price_ils=Decimal('250.00'),
            spoken_languages=['he', 'en'],
            availability='limited', offers_remote=True, is_published=True,
        )
        cls.online.skills.add(cls.legal)
        cls.online.services.add(cls.consulting)
        # Public in Ashdod online, but does NOT serve Ashdod onsite.
        cls.online.service_cities.add(cls.other_city)

        cls.blocked_user = make_user('directory-blocked', is_blocked=True)
        cls.blocked = WorkerProfile.objects.create(
            user=cls.blocked_user, city=cls.city,
            display_name='BLOCKED_05_PROFILE',
            description='Blocked synthetic card never published to directory.',
            pricing_details='Some text', spoken_languages=['ru'],
            is_published=True,
        )
        cls.blocked.skills.add(cls.plumbing)

        cls.offpilot_user = make_user('directory-offpilot')
        cls.offpilot = WorkerProfile.objects.create(
            user=cls.offpilot_user, city=cls.other_city,
            display_name='OFFPILOT_05_PROFILE',
            description='Outside Ashdod coverage, test only.',
            pricing_details='Some text', spoken_languages=['ru'],
            is_published=True, offers_remote=True,
        )
        cls.offpilot.skills.add(cls.legal)

        cls.draft_user = make_user('directory-draft')
        cls.draft = WorkerProfile.objects.create(
            user=cls.draft_user, city=cls.city,
            display_name='DRAFT_05_PROFILE',
            description='Private unpublished draft, no public search.',
            pricing_details='Some text', spoken_languages=['ru'],
            is_published=False,
        )
        cls.draft.skills.add(cls.plumbing)

        cls.real_order = make_order(
            client=cls.client_user, category=cls.plumbing, city=cls.city,
        )
        Rating.objects.create(
            order=cls.real_order, worker=cls.plumber_user,
            client=cls.client_user, rating=5, review_text='Synthetic review',
        )

    def get_workers(self, params=None):
        response = self.client.get(
            reverse('marketplace:worker_directory'), params or {},
        )
        self.assertEqual(response.status_code, 200)
        return response, list(response.context['page_obj'].object_list)

    def test_public_directory_only_published_pilot_workers(self):
        response, workers = self.get_workers()
        self.assertCountEqual(
            [worker.pk for worker in workers],
            [self.plumber.pk, self.category_only.pk, self.online.pk],
        )
        self.assertContains(response, 'Real Plumbing Expert')
        for secret in (
            'NEVER_PUBLIC_PHONE_051', 'private-stage05@example.invalid',
            '+972500000051', 'BLOCKED_05_PROFILE',
            'OFFPILOT_05_PROFILE', 'DRAFT_05_PROFILE',
        ):
            self.assertNotContains(response, secret)
        self.assertContains(response, 'name="robots" content="noindex,follow"')

    def test_service_requires_explicit_worker_selection(self):
        _, workers = self.get_workers({'category': self.plumbing.pk})
        self.assertCountEqual(
            [worker.pk for worker in workers],
            [self.plumber.pk, self.category_only.pk],
        )
        _, exact = self.get_workers({'service': self.faucets.pk})
        self.assertEqual([worker.pk for worker in exact], [self.plumber.pk])
        _, none = self.get_workers({'service': self.pipes.pk})
        self.assertEqual(none, [])

    def test_all_filters_combine_with_real_rating_and_price(self):
        query = {
            'category': self.plumbing.pk, 'service': self.faucets.pk,
            'q': 'faucets', 'city': self.city.pk, 'language': 'he',
            'mode': 'onsite', 'price_from': '140', 'price_to': '160',
            'min_rating': '4.5', 'availability': 'available',
        }
        _, workers = self.get_workers(query)
        self.assertEqual([worker.pk for worker in workers], [self.plumber.pk])
        self.assertEqual(workers[0].review_count, 1)
        self.assertEqual(workers[0].avg_rating, 5)
        query['price_to'] = '100'
        response, workers = self.get_workers(query)
        self.assertFalse(response.context['form'].is_valid())
        self.assertEqual(workers, [])

    def test_online_cannot_leak_into_onsite_zone(self):
        base = {'category': self.legal.pk, 'service': self.consulting.pk}
        _, online = self.get_workers({**base, 'mode': 'online'})
        self.assertEqual([worker.pk for worker in online], [self.online.pk])
        _, onsite = self.get_workers({**base, 'mode': 'onsite'})
        self.assertEqual(onsite, [])
        _, plumber_remote = self.get_workers({
            'service': self.faucets.pk, 'mode': 'online',
        })
        self.assertEqual(plumber_remote, [])

    def test_missing_numeric_price_is_not_inferred_from_text(self):
        _, matched = self.get_workers({
            'category': self.plumbing.pk, 'price_to': '200',
        })
        self.assertEqual([worker.pk for worker in matched], [self.plumber.pk])
        _, sorted_workers = self.get_workers({
            'category': self.plumbing.pk, 'sort': 'price_asc',
        })
        self.assertEqual(
            [worker.pk for worker in sorted_workers],
            [self.plumber.pk, self.category_only.pk],
        )

    def test_actual_reviews_only(self):
        _, rated = self.get_workers({'min_rating': '4.0'})
        self.assertEqual([worker.pk for worker in rated], [self.plumber.pk])
        _, workers = self.get_workers({'sort': 'rating'})
        self.assertEqual(workers[0].pk, self.plumber.pk)
        self.assertIsNone(workers[1].avg_rating)
        self.assertEqual(workers[1].review_count, 0)

    def test_keyword_language_availability_and_no_unexpected_substring(self):
        _, found = self.get_workers({
            'q': 'ייעוץ', 'language': 'he', 'availability': 'limited',
        })
        self.assertEqual([worker.pk for worker in found], [self.online.pk])
        _, found = self.get_workers({'q': 'pipes'})
        self.assertEqual(found, [])
        _, found = self.get_workers({'language': 'en'})
        self.assertCountEqual(
            [w.pk for w in found], [self.category_only.pk, self.online.pk],
        )

    def test_malformed_and_offpilot_queries_fail_closed(self):
        invalids = (
            {'city': self.other_city.pk},
            {'category': self.plumbing.pk, 'service': self.consulting.pk},
            {'q': 'X' * 101},
            {'price_from': '-1'},
            {'price_to': 'not-number'},
            {'min_rating': '9'},
            {'sort': 'unknown'},
            {'mode': 'teleport'},
            {'language': 'xx'},
        )
        for params in invalids:
            with self.subTest(params=params):
                response, workers = self.get_workers(params)
                self.assertFalse(response.context['form'].is_valid())
                self.assertEqual(workers, [])
        response, workers = self.get_workers({'q': 'NO_MATCH_05'})
        self.assertEqual(workers, [])
        self.assertContains(response, reverse('marketplace:order_wizard_start'))

    def test_pagination_sorting_and_query_string_allowlist(self):
        for index in range(13):
            user = make_user(f'directory-page-{index:02}')
            profile = WorkerProfile.objects.create(
                user=user, city=self.city,
                display_name=f'Page Worker {index:02}',
                description='Synthetic populated pagination profile for test.',
                pricing_details='Negotiable',
                spoken_languages=['ru'], is_published=True,
            )
            profile.skills.add(self.plumbing)
        filters = {'category': self.plumbing.pk, 'sort': 'name'}
        first, page1 = self.get_workers(filters)
        second, page2 = self.get_workers({**filters, 'page': '2'})
        self.assertEqual(first.context['page_obj'].paginator.count, 15)
        self.assertEqual(len(page1), 10)
        self.assertEqual(len(page2), 5)
        self.assertFalse(set(w.pk for w in page1) & set(w.pk for w in page2))
        self.assertContains(first, 'page=2')
        self.assertIn('category=', first.context['pagination_query'])
        invalid_page, _ = self.get_workers({**filters, 'page': 'oops'})
        self.assertEqual(invalid_page.context['page_obj'].number, 1)
        response, _ = self.get_workers({**filters, 'secret': 'DO_NOT_ECHO'})
        self.assertNotIn('DO_NOT_ECHO', response.content.decode())

    def test_locales_and_safe_get_only(self):
        for locale, direction in (('ru', 'ltr'), ('en', 'ltr'), ('he', 'rtl')):
            with self.subTest(locale=locale), override(locale):
                url = reverse('catalog_i18n:worker_directory')
                response = self.client.get(url, HTTP_ACCEPT_LANGUAGE=locale)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, f'dir="{direction}"')
                self.assertContains(response, 'Real Plumbing Expert')
        self.assertEqual(
            self.client.post(reverse('marketplace:worker_directory')).status_code,
            405,
        )
