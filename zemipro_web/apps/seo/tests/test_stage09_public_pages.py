from django.test import TestCase, override_settings
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import override

from apps.accounts.models import WorkerProfile
from apps.locations.models import City
from apps.marketplace.models import Category, Subcategory
from apps.marketplace.tests.factories import make_user
from apps.seo.models import SeoContentPage
from apps.seo.models import SeoLegacyUrl
from apps.seo.legacy import activate_legacy_url, deactivate_legacy_url


@override_settings(
    ZEMIPRO_PILOT_CITY_SLUG='ashdod',
    ZEMIPRO_CATALOG_INDEXING_ENABLED=True,
)
class Stage09PublicPageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.city = City.objects.create(
            slug='ashdod', name_ru='Ашдод', name_en='Ashdod', name_he='אשדוד',
        )
        cls.other_city = City.objects.create(
            slug='jerusalem-stage09', name_ru='Иерусалим',
            name_en='Jerusalem', name_he='ירושלים',
        )
        cls.category = Category.objects.create(
            slug='stage09-home-repair', name_ru='Домашний ремонт',
            name_en='Home repair', name_he='תיקוני בית',
            description='Проверенные услуги для дома.',
            description_en='Reviewed home services.',
            description_he='שירותי בית שנבדקו.',
        )
        cls.service = Subcategory.objects.create(
            category=cls.category, slug='stage09-wall-painting',
            name_ru='Покраска стен', name_en='Wall painting', name_he='צביעת קירות',
            description_ru='Подготовка и покраска стен.',
            description_en='Wall preparation and painting.',
            description_he='הכנה וצביעת קירות.',
        )
        cls.reviewer = make_user('stage09-page-reviewer', is_staff=True)
        cls.worker = WorkerProfile.objects.create(
            user=make_user('stage09-public-worker'), city=cls.city,
            display_name='Safe Painter',
            description='Public description without personal contacts.',
            contact='private-stage09@example.test', pricing_details='By agreement',
            is_published=True,
        )
        cls.worker.skills.add(cls.category)
        cls.worker.services.add(cls.service)
        now = timezone.now()
        for language, suffix in (('ru', 'RU'), ('en', 'EN'), ('he', 'HE')):
            SeoContentPage.objects.create(
                page_type=SeoContentPage.PageType.SERVICE_CITY,
                language=language, service=cls.service, city=cls.city,
                topic=f'Editorial topic {suffix}', title=f'Editorial title {suffix}',
                meta_description=f'Editorial description {suffix}',
                summary=f'Editorial summary {suffix}',
                body=f'Useful reviewed catalog content {suffix}.',
                source_facts='Synthetic catalog fixtures only.',
                status=SeoContentPage.Status.PUBLISHED, quality_approved=True,
                author=cls.reviewer, reviewer=cls.reviewer, reviewed_at=now,
                published_at=now,
            )

    def localized(self, language, name, **kwargs):
        with override(language):
            return reverse(f'catalog_i18n:{name}', kwargs=kwargs)

    def test_service_city_and_profile_work_in_all_languages_and_rtl(self):
        for language in ('ru', 'en', 'he'):
            service_url = self.localized(
                language, 'service_city_detail',
                category_slug=self.category.slug, service_slug=self.service.slug,
                city_slug=self.city.slug,
            )
            response = self.client.get(service_url)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, f'Editorial title {language.upper()}')
            self.assertContains(response, self.worker.public_display_name)
            self.assertNotContains(response, 'private-stage09@example.test')
            self.assertContains(
                response,
                f'<html lang="{language}" dir="{"rtl" if language == "he" else "ltr"}">',
            )
            self.assertNotContains(response, 'noindex,follow')
            self.assertContains(response, 'class="breadcrumbs"')
            profile_url = self.localized(
                language, 'worker_public_profile', pk=self.worker.pk,
            )
            profile = self.client.get(profile_url)
            self.assertEqual(profile.status_code, 200)
            self.assertNotContains(profile, 'private-stage09@example.test')
            self.assertContains(profile, f'hreflang="{language}"')

    def test_nonpilot_city_and_thin_page_fail_closed(self):
        blocked = self.localized(
            'ru', 'service_city_detail', category_slug=self.category.slug,
            service_slug=self.service.slug, city_slug=self.other_city.slug,
        )
        self.assertEqual(self.client.get(blocked).status_code, 404)
        self.worker.services.clear()
        page = self.client.get(self.localized(
            'ru', 'service_city_detail', category_slug=self.category.slug,
            service_slug=self.service.slug, city_slug=self.city.slug,
        ))
        self.assertContains(page, 'noindex,follow')
        self.assertNotContains(page, self.worker.public_display_name)

    def test_legacy_profile_remains_noindex_and_localized_profile_is_canonical(self):
        legacy = self.client.get(reverse(
            'marketplace:worker_public_profile', args=[self.worker.pk],
        ))
        self.assertContains(legacy, 'noindex,follow')
        localized = self.localized('en', 'worker_public_profile', pk=self.worker.pk)
        page = self.client.get(localized)
        self.assertContains(
            page, f'<link rel="canonical" href="http://testserver{localized}">',
        )

    def test_editorial_copy_is_escaped_not_rendered_as_html(self):
        content = SeoContentPage.objects.get(
            page_type=SeoContentPage.PageType.SERVICE_CITY,
            service=self.service, city=self.city, language='ru',
        )
        content.body = '<script>window.stage09Xss = true</script> Safe text.'
        content.save()
        page = self.client.get(self.localized(
            'ru', 'service_city_detail', category_slug=self.category.slug,
            service_slug=self.service.slug, city_slug=self.city.slug,
        ))
        self.assertNotContains(page, '<script>window.stage09Xss')
        self.assertContains(page, '&lt;script&gt;window.stage09Xss')

    def test_technical_metadata_is_truthful_and_script_safe(self):
        content = SeoContentPage.objects.get(
            page_type=SeoContentPage.PageType.SERVICE_CITY,
            service=self.service, city=self.city, language='ru',
        )
        content.meta_description = '</script><script>window.schemaXss=true</script>'
        content.save()
        page = self.client.get(self.localized(
            'ru', 'service_city_detail', category_slug=self.category.slug,
            service_slug=self.service.slug, city_slug=self.city.slug,
        ))
        self.assertContains(page, 'property="og:title"')
        self.assertContains(page, 'type="application/ld+json"')
        self.assertContains(page, '"@type":"Service"')
        self.assertContains(page, '"@type":"BreadcrumbList"')
        self.assertNotContains(page, '<script>window.schemaXss')
        self.assertNotContains(page, 'AggregateRating')
        self.assertNotContains(page, '"price"')
        self.assertNotContains(page, 'private-stage09@example.test')

    def test_sitemap_and_robots_include_only_eligible_public_urls(self):
        sitemap = self.client.get(reverse('seo_sitemap'))
        self.assertEqual(sitemap.status_code, 200)
        self.assertEqual(sitemap['Content-Type'], 'application/xml; charset=utf-8')
        for language in ('ru', 'en', 'he'):
            self.assertContains(sitemap, self.localized(
                language, 'service_city_detail', category_slug=self.category.slug,
                service_slug=self.service.slug, city_slug=self.city.slug,
            ))
            self.assertContains(sitemap, self.localized(
                language, 'worker_public_profile', pk=self.worker.pk,
            ))
        self.assertContains(sitemap, 'hreflang="x-default"')
        self.assertNotContains(sitemap, self.other_city.slug)
        self.assertNotContains(sitemap, 'private-stage09@example.test')
        robots = self.client.get(reverse('seo_robots'))
        self.assertContains(robots, 'Disallow: /admin/')
        self.assertContains(robots, 'Disallow: /knowledge/')
        self.assertContains(robots, 'Sitemap: http://testserver/sitemap.xml')

    @override_settings(ZEMIPRO_CATALOG_INDEXING_ENABLED=False)
    def test_indexing_switch_fails_closed(self):
        robots = self.client.get(reverse('seo_robots'))
        self.assertContains(robots, 'Disallow: /')
        sitemap = self.client.get(reverse('seo_sitemap'))
        self.assertNotContains(sitemap, '<url>')

    def grant_legacy_approval(self):
        self.reviewer.user_permissions.add(Permission.objects.get(
            codename='approve_legacy_url',
        ))
        self.reviewer.refresh_from_db()

    def test_legacy_registry_is_seeded_review_only(self):
        seeded = SeoLegacyUrl.objects.filter(
            evidence_source__contains='Stage09.1 external HTTP/GSC pending',
        )
        self.assertEqual(seeded.count(), 21)
        self.assertFalse(seeded.filter(is_active=True).exists())
        self.assertFalse(seeded.exclude(decision=SeoLegacyUrl.Decision.REVIEW).exists())
        with override_settings(ZEMIPRO_LEGACY_REDIRECTS_ENABLED=True):
            for row in seeded.exclude(path='/'):
                with self.subTest(path=row.path):
                    self.assertEqual(self.client.get(row.path).status_code, 404)

    def test_exact_legacy_redirect_activation_and_rollback(self):
        target = self.localized(
            'ru', 'service_city_detail', category_slug=self.category.slug,
            service_slug=self.service.slug, city_slug=self.city.slug,
        )
        row = SeoLegacyUrl.objects.create(
            path='/master/stage09-exact/', page_type='service_page',
            decision=SeoLegacyUrl.Decision.REDIRECT, target_path=target,
            evidence_source='Synthetic HTTP and GSC evidence for isolated tests.',
        )
        with self.assertRaises(PermissionDenied):
            activate_legacy_url(row_id=row.pk, actor=self.worker.user)
        self.grant_legacy_approval()
        activate_legacy_url(row_id=row.pk, actor=self.reviewer)
        with override_settings(ZEMIPRO_LEGACY_REDIRECTS_ENABLED=True):
            response = self.client.get(row.path + '?utm_source=legacy')
            self.assertEqual(response.status_code, 301)
            self.assertEqual(response['Location'], target)
            self.assertEqual(self.client.get('/master/not-registered/').status_code, 404)
            self.assertEqual(self.client.post(row.path).status_code, 405)
        deactivate_legacy_url(row_id=row.pk, actor=self.reviewer)
        with override_settings(ZEMIPRO_LEGACY_REDIRECTS_ENABLED=True):
            self.assertEqual(self.client.get(row.path).status_code, 404)
        row.refresh_from_db()
        row.redirect_status = SeoLegacyUrl.RedirectStatus.PERMANENT_REDIRECT
        row.save()
        activate_legacy_url(row_id=row.pk, actor=self.reviewer)
        with override_settings(ZEMIPRO_LEGACY_REDIRECTS_ENABLED=True):
            self.assertEqual(self.client.get(row.path).status_code, 308)

    def test_legacy_feature_flag_and_chain_validation_fail_closed(self):
        self.grant_legacy_approval()
        gone = SeoLegacyUrl.objects.create(
            path='/master/stage09-gone/', decision=SeoLegacyUrl.Decision.GONE,
            evidence_source='Synthetic removal evidence.',
        )
        activate_legacy_url(row_id=gone.pk, actor=self.reviewer)
        self.assertEqual(self.client.get(gone.path).status_code, 404)
        with override_settings(ZEMIPRO_LEGACY_REDIRECTS_ENABLED=True):
            self.assertEqual(self.client.get(gone.path).status_code, 410)
        chain = SeoLegacyUrl.objects.create(
            path='/master/stage09-chain/', decision=SeoLegacyUrl.Decision.REDIRECT,
            target_path=gone.path, evidence_source='Synthetic evidence.',
        )
        with self.assertRaises(ValidationError):
            activate_legacy_url(row_id=chain.pk, actor=self.reviewer)
