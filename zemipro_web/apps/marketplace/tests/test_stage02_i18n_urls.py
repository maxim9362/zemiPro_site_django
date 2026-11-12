"""Stage 02.4: additive public i18n catalog routes, SEO and legacy safety."""
from django.test import TestCase, override_settings
from django.urls import resolve, reverse
from django.utils.translation import override

from apps.accounts.models import WorkerProfile
from apps.locations.models import City, CityAlias, District
from apps.marketplace.models import Category, ServiceSection, Subcategory
from apps.marketplace.tests.factories import make_user


class CatalogLanguageUrlTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.city = City.objects.create(
            slug='ashdod-test-024', name_ru='Ашдод тест',
            name_en='Ashdod test', name_he='אשדוד בדיקה',
        )
        cls.alias = CityAlias.objects.create(
            slug='ashdod-024-alias', city=cls.city,
        )
        cls.section = ServiceSection.objects.create(
            slug='repair-test-024', name_ru='Ремонт тест',
            name_en='Repair test', name_he='תיקונים בדיקה',
            description_ru='Раздел услуг ремонта',
            description_en='Repair service section',
            description_he='תחום שירותי תיקון',
        )
        cls.category = Category.objects.create(
            section=cls.section, slug='plumbing-test-024',
            name_ru='Сантехника тест', name_en='Plumbing test',
            name_he='אינסטלציה בדיקה',
            description='Ремонт и сантехника.',
            description_en='Repair and plumbing.',
            description_he='תיקונים ואינסטלציה.',
        )
        cls.service = Subcategory.objects.create(
            category=cls.category, slug='leak-test-024',
            name_ru='Устранение течи', name_en='Leak repair',
            name_he='תיקון נזילה',
            description_ru='Устранение протечек.',
            description_en='Fix plumbing leaks.',
            description_he='תיקון דליפות מים.',
        )
        cls.user = make_user('i18n-route-worker')
        cls.worker = WorkerProfile.objects.create(
            user=cls.user, city=cls.city,
            description='A synthetic worker with no private contact published.',
            contact='PRIVATE_024_MARKER',
        )
        cls.worker.skills.add(cls.category)

    def localized(self, language, name, **kwargs):
        with override(language):
            return reverse(f'catalog_i18n:{name}', kwargs=kwargs or None)

    def test_all_six_routes_prefix_correctly_in_three_languages(self):
        routes = [
            ('categories_list', {}),
            ('section_detail', {'slug': self.section.slug}),
            ('category_detail', {'slug': self.category.slug}),
            ('service_detail', {
                'category_slug': self.category.slug,
                'service_slug': self.service.slug,
            }),
            ('cities_list', {}),
            ('city_detail', {'slug': self.city.slug}),
        ]
        for language in ('ru', 'en', 'he'):
            for name, params in routes:
                with self.subTest(language=language, route=name):
                    path = self.localized(language, name, **params)
                    self.assertTrue(path.startswith(f'/{language}/'), path)
                    with override(language):
                        matched = resolve(path)
                    self.assertEqual(
                        matched.view_name, f'catalog_i18n:{name}',
                    )
                    response = self.client.get(
                        path, HTTP_ACCEPT_LANGUAGE='ru',
                    )
                    self.assertEqual(response.status_code, 200)
                    direction = 'rtl' if language == 'he' else 'ltr'
                    self.assertContains(
                        response,
                        f'<html lang="{language}" dir="{direction}">',
                    )
                    self.assertNotContains(response, 'PRIVATE_024_MARKER')
                    self.assertContains(response, f'hreflang="{language}"')
                    self.assertContains(
                        response,
                        f'http://testserver{path}',
                    )

    def test_identical_entity_id_and_slug_across_languages(self):
        for language in ('ru', 'en', 'he'):
            with self.subTest(language=language):
                category = self.client.get(self.localized(
                    language, 'category_detail', slug=self.category.slug,
                ))
                service = self.client.get(self.localized(
                    language, 'service_detail',
                    category_slug=self.category.slug,
                    service_slug=self.service.slug,
                ))
                city = self.client.get(self.localized(
                    language, 'city_detail', slug=self.city.slug,
                ))
                self.assertEqual(category.context['category'].pk, self.category.pk)
                self.assertEqual(service.context['service'].pk, self.service.pk)
                self.assertEqual(city.context['city'].pk, self.city.pk)
                self.assertEqual(
                    service.context['service'].category_id, self.category.pk,
                )

    def test_canonical_and_hreflang_triplet_no_query(self):
        path = self.localized(
            'he', 'category_detail', slug=self.category.slug,
        )
        response = self.client.get(f'{path}?city={self.city.slug}&page=3')
        self.assertContains(
            response,
            f'<link rel="canonical" href="http://testserver{path}">',
        )
        for language in ('ru', 'en', 'he'):
            target = self.localized(
                language, 'category_detail', slug=self.category.slug,
            )
            self.assertContains(
                response,
                f'hreflang="{language}" href="http://testserver{target}"',
            )
        # The query-specific page is not separately indexable.
        self.assertContains(
            response, '<meta name="robots" content="noindex,follow">',
        )
        self.assertNotIn('?city=', response.context['seo_canonical'])

    def test_default_noindex_and_explicit_index_toggle_with_empty_gate(self):
        categories = self.localized('en', 'categories_list')
        response = self.client.get(categories)
        self.assertContains(response, 'noindex,follow')
        with override_settings(ZEMIPRO_CATALOG_INDEXING_ENABLED=True):
            response = self.client.get(categories)
            self.assertNotContains(
                response, '<meta name="robots" content="noindex,follow">',
            )
            target = self.localized(
                'en', 'category_detail', slug=self.category.slug,
            )
            response = self.client.get(target)
            self.assertNotContains(
                response, '<meta name="robots" content="noindex,follow">',
            )
            empty = Category.objects.create(
                slug='empty-024', name_ru='Пусто', name_en='Empty',
                name_he='ריק', description='No professionals registered',
            )
            empty_url = self.localized(
                'en', 'category_detail', slug=empty.slug,
            )
            self.assertContains(
                self.client.get(empty_url),
                '<meta name="robots" content="noindex,follow">',
            )
            service_url = self.localized(
                'en', 'service_detail',
                category_slug=self.category.slug,
                service_slug=self.service.slug,
            )
            # No service-specific professionals: deliberately noindex.
            self.assertContains(
                self.client.get(service_url),
                '<meta name="robots" content="noindex,follow">',
            )

    def test_set_language_translates_prefixed_resource_path_and_query(self):
        original = self.localized(
            'he', 'category_detail', slug=self.category.slug,
        ) + '?city=' + self.city.slug + '&page=2'
        result = self.client.post(reverse('set_language'), {
            'language': 'en',
            'next': original,
        })
        expected = self.localized(
            'en', 'category_detail', slug=self.category.slug,
        ) + '?city=' + self.city.slug + '&page=2'
        self.assertRedirects(result, expected, fetch_redirect_response=False)
        self.assertContains(
            self.client.get(expected), '<html lang="en" dir="ltr">',
        )

    def test_legacy_urls_are_unchanged_without_automatic_301(self):
        self.assertEqual(reverse('marketplace:categories_list'), '/categories/')
        self.assertEqual(reverse('marketplace:cities_list'), '/cities/')
        legacy_category = reverse(
            'marketplace:category_detail', args=[self.category.slug],
        )
        legacy_city = reverse(
            'marketplace:city_detail', args=[self.city.slug],
        )
        for target in (
            '/categories/', '/cities/', legacy_category, legacy_city,
            '/', '/health/live/',
        ):
            with self.subTest(target=target):
                result = self.client.get(target)
                self.assertEqual(result.status_code, 200)
                self.assertNotIn('Location', result.headers)
                self.assertNotContains(result, 'rel="canonical"')
        self.assertEqual(self.client.get('/de/categories/').status_code, 404)
        # Django's default locale 404 redirect must not hijack legacy paths.
        for old_path in (
            '/categories/does-not-exist-024/',
            '/cities/does-not-exist-024/',
        ):
            missing = self.client.get(old_path, HTTP_ACCEPT_LANGUAGE='he')
            self.assertEqual(missing.status_code, 404)
            self.assertNotIn('Location', missing.headers)

    def test_known_city_alias_redirects_only_in_prefixed_catalog(self):
        url = self.localized('he', 'city_detail', slug=self.alias.slug)
        canonical = self.localized('he', 'city_detail', slug=self.city.slug)
        response = self.client.get(url + '?category=' + self.category.slug)
        self.assertEqual(response.status_code, 301)
        self.assertEqual(
            response['Location'], canonical + '?category=' + self.category.slug,
        )
        # Pre-existing unprefixed City path must not gain a new 301.
        self.assertEqual(
            self.client.get('/cities/' + self.alias.slug + '/').status_code,
            404,
        )
        self.assertEqual(
            self.client.get(
                self.localized('ru', 'city_detail', slug='missing-024'),
            ).status_code, 404,
        )

    def test_inactive_section_category_service_and_city_are_404(self):
        city_url = self.localized(
            'en', 'city_detail', slug=self.city.slug,
        )
        service_url = self.localized(
            'en', 'service_detail', category_slug=self.category.slug,
            service_slug=self.service.slug,
        )
        section_url = self.localized(
            'en', 'section_detail', slug=self.section.slug,
        )
        self.section.is_active = False
        self.section.save(update_fields=['is_active'])
        self.assertEqual(self.client.get(section_url).status_code, 404)
        self.assertEqual(self.client.get(service_url).status_code, 404)
        self.city.is_active = False
        self.city.save(update_fields=['is_active'])
        self.assertEqual(self.client.get(city_url).status_code, 404)
        self.assertEqual(self.client.get(
            self.localized('en', 'city_detail', slug=self.alias.slug),
        ).status_code, 404)

    def test_internal_links_keep_language_and_legacy_profile_targets(self):
        catalog = self.client.get(self.localized('he', 'categories_list'))
        self.assertContains(
            catalog,
            self.localized('he', 'section_detail', slug=self.section.slug),
        )
        self.assertContains(
            catalog,
            self.localized('he', 'category_detail', slug=self.category.slug),
        )
        section_page = self.client.get(self.localized(
            'he', 'section_detail', slug=self.section.slug,
        ))
        self.assertContains(section_page, 'אינסטלציה בדיקה')
        category_page = self.client.get(self.localized(
            'he', 'category_detail', slug=self.category.slug,
        ))
        self.assertContains(category_page, self.localized(
            'he', 'service_detail',
            category_slug=self.category.slug, service_slug=self.service.slug,
        ))
        self.assertContains(category_page, '/worker/' + str(self.worker.pk) + '/')

    @override_settings(ZEMIPRO_CATALOG_INDEXING_ENABLED=True)
    def test_complete_translations_can_index_lists_and_supplied_details(self):
        """Opt-in SEO still works for a complete and genuinely supplied page."""
        for language in ('ru', 'en', 'he'):
            with self.subTest(language=language):
                urls = (
                    self.localized(language, 'categories_list'),
                    self.localized(language, 'cities_list'),
                    self.localized(language, 'section_detail', slug=self.section.slug),
                    self.localized(language, 'category_detail', slug=self.category.slug),
                    self.localized(language, 'city_detail', slug=self.city.slug),
                )
                for url in urls:
                    response = self.client.get(url)
                    self.assertEqual(response.status_code, 200)
                    self.assertNotContains(
                        response, '<meta name="robots" content="noindex,follow">',
                    )

    @override_settings(ZEMIPRO_CATALOG_INDEXING_ENABLED=True)
    def test_incomplete_category_name_blocks_list_section_and_detail_indexing(self):
        self.category.name_en = ''
        self.category.save(update_fields=['name_en'])
        for language in ('en', 'he'):
            with self.subTest(language=language):
                urls = (
                    self.localized(language, 'categories_list'),
                    self.localized(language, 'section_detail', slug=self.section.slug),
                    self.localized(language, 'category_detail', slug=self.category.slug),
                    self.localized(language, 'city_detail', slug=self.city.slug),
                )
                for url in urls:
                    response = self.client.get(url)
                    self.assertEqual(response.status_code, 200)
                    self.assertContains(
                        response, '<meta name="robots" content="noindex,follow">',
                    )
        # The ordinary page continues to display a safe Russian fallback.
        response = self.client.get(self.localized('en', 'categories_list'))
        self.assertContains(response, self.category.name_ru)

    @override_settings(ZEMIPRO_CATALOG_INDEXING_ENABLED=True)
    def test_missing_localized_description_blocks_lists_and_details(self):
        self.category.description_he = '   '
        self.category.save(update_fields=['description_he'])
        for language in ('en', 'he'):
            with self.subTest(language=language):
                for url in (
                    self.localized(language, 'categories_list'),
                    self.localized(language, 'section_detail', slug=self.section.slug),
                    self.localized(language, 'category_detail', slug=self.category.slug),
                ):
                    self.assertContains(
                        self.client.get(url),
                        '<meta name="robots" content="noindex,follow">',
                    )
        # Section descriptions are also required; no Russian fallback is indexable.
        self.category.description_he = 'תיקונים ואינסטלציה.'
        self.category.save(update_fields=['description_he'])
        self.section.description_en = ''
        self.section.save(update_fields=['description_en'])
        self.assertContains(
            self.client.get(self.localized(
                'en', 'section_detail', slug=self.section.slug,
            )),
            '<meta name="robots" content="noindex,follow">',
        )

    @override_settings(ZEMIPRO_CATALOG_INDEXING_ENABLED=True)
    def test_incomplete_city_or_district_blocks_visible_location_indexing(self):
        self.city.name_he = ''
        self.city.save(update_fields=['name_he'])
        for language in ('en', 'he'):
            with self.subTest(language=language):
                for url in (
                    self.localized(language, 'cities_list'),
                    self.localized(language, 'city_detail', slug=self.city.slug),
                    self.localized(language, 'category_detail', slug=self.category.slug),
                ):
                    self.assertContains(
                        self.client.get(url),
                        '<meta name="robots" content="noindex,follow">',
                    )
        self.city.name_he = 'אשדוד בדיקה'
        district = District.objects.create(
            slug='seo-incomplete-district',
            name_ru='Округ', name_en='District', name_he='',
        )
        self.city.district = district
        self.city.save(update_fields=['name_he', 'district'])
        self.assertContains(
            self.client.get(self.localized('he', 'cities_list')),
            '<meta name="robots" content="noindex,follow">',
        )
        district.name_he = 'מחוז'
        district.save(update_fields=['name_he'])
        self.assertNotContains(
            self.client.get(self.localized('he', 'cities_list')),
            '<meta name="robots" content="noindex,follow">',
        )

    @override_settings(ZEMIPRO_CATALOG_INDEXING_ENABLED=True)
    def test_missing_service_name_blocks_category_detail_indexing(self):
        self.service.name_he = ''
        self.service.save(update_fields=['name_he'])
        self.assertContains(
            self.client.get(self.localized(
                'en', 'category_detail', slug=self.category.slug,
            )),
            '<meta name="robots" content="noindex,follow">',
        )
        self.assertNotContains(
            self.client.get(self.localized('en', 'cities_list')),
            '<meta name="robots" content="noindex,follow">',
        )

    @override_settings(ZEMIPRO_CATALOG_INDEXING_ENABLED=True)
    def test_unassigned_category_and_filtering_still_follow_indexing_gates(self):
        new = Category.objects.create(
            slug='seo-unassigned-incomplete', name_ru='Новая категория',
            name_en='', name_he='קטגוריה', description='Описание',
            description_en='Description', description_he='תיאור',
        )
        self.assertContains(
            self.client.get(self.localized('en', 'categories_list')),
            '<meta name="robots" content="noindex,follow">',
        )
        self.assertContains(
            self.client.get(self.localized(
                'en', 'category_detail', slug=self.category.slug,
            ) + '?city=' + self.city.slug),
            '<meta name="robots" content="noindex,follow">',
        )
        new.name_en = 'New category'
        new.save(update_fields=['name_en'])
        self.assertNotContains(
            self.client.get(self.localized('en', 'categories_list')),
            '<meta name="robots" content="noindex,follow">',
        )

    @override_settings(ZEMIPRO_CATALOG_INDEXING_ENABLED=True)
    def test_feature_default_and_legacy_routes_remain_unaffected(self):
        legacy = self.client.get('/categories/')
        self.assertEqual(legacy.status_code, 200)
        self.assertNotContains(legacy, 'rel="canonical"')
        self.assertNotContains(
            self.client.get(self.localized('en', 'service_detail',
                category_slug=self.category.slug,
                service_slug=self.service.slug,
            )),
            '<meta name="robots" content="index,follow">',
        )
