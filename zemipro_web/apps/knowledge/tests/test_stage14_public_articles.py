"""Stage 14.3: synthetic public articles, SEO, privacy and RTL regression tests."""
import json
import re
from unittest.mock import patch

from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import override

from apps.accounts.models import WorkerProfile
from apps.knowledge import services
from apps.knowledge.models import (
    ExpertArticle, ExpertArticleDecision, ExpertArticleImage,
    ExpertArticleReport,
)
from apps.knowledge.public_seo import sitemap_candidates
from apps.marketplace.models import Category, Order, ServiceSection
from apps.marketplace.tests.factories import (
    make_category, make_city, make_user, make_worker_profile,
)
from apps.knowledge.tests.test_stage14_authoring import BODY, TITLE, png_upload


@override_settings(
    ZEMIPRO_KNOWLEDGE_AUTHORING_ENABLED=True,
    ZEMIPRO_KNOWLEDGE_ARTICLES_ENABLED=True,
)
class Stage14PublicArticleTests(TestCase):
    def setUp(self):
        self.city = make_city(slug='ashdod', name_ru='Synthetic Ashdod')
        self.category = make_category(slug='s14-advice')
        self.category.name_en = 'Synthetic advice'
        self.category.name_he = 'עצות בדיקה'
        self.category.save(update_fields=['name_en', 'name_he'])
        self.writer = make_user('s14-public-author')
        self.reader = make_user('s14-public-reader')
        self.moderator = make_user('s14-public-moderator', is_staff=True)
        self.moderator.user_permissions.add(
            Permission.objects.get(codename='moderate_expert_articles'),
        )
        self.worker = make_worker_profile(
            self.writer, city=self.city, category=self.category,
        )

    def publish(self, *, title=TITLE, body=BODY, category=None,
                language='ru', image=False, kind='original', group=None):
        category = category or self.category
        article = services.create_article(
            actor=self.writer, title=title,
            excerpt='Synthetic reviewed summary', body=body,
            category_id=category.pk, language=language, rights_confirmed=True,
        )
        if group:
            ExpertArticle.objects.filter(pk=article.pk).update(
                translation_group=group, translation_kind=kind,
            )
            article.refresh_from_db()
        if image:
            services.add_article_image(
                actor=self.writer, article_id=article.pk, upload=png_upload(),
                caption='Synthetic non-identifying illustration',
                rights_confirmed=True, expected_version=article.content_version,
            )
            article.refresh_from_db()
        services.submit_article(
            actor=self.writer, article_id=article.pk,
            expected_version=article.content_version, rights_confirmed=True,
        )
        article.refresh_from_db()
        result = services.decide_article(
            actor=self.moderator, article_id=article.pk,
            expected_version=article.content_version, approve=True,
            content_reviewed=True, media_reviewed=image,
        )
        return result

    @staticmethod
    def article_path(article):
        with override(article.language):
            return reverse('knowledge_public:article_detail', kwargs={
                'slug': article.slug,
            })

    def test_feature_disabled_fails_closed_without_leaking_navigation(self):
        article = self.publish()
        with override_settings(ZEMIPRO_KNOWLEDGE_ARTICLES_ENABLED=False):
            self.assertEqual(self.client.get(
                reverse('knowledge_public:article_list'),
            ).status_code, 404)
            self.assertEqual(self.client.get(self.article_path(article)).status_code, 404)
            self.assertNotContains(self.client.get('/'), 'advice/', status_code=200)
            self.assertFalse(sitemap_candidates().exists())

    def test_approved_original_visible_to_guest_with_safe_profile_and_order(self):
        article = self.publish()
        listing = self.client.get('/ru/advice/')
        self.assertEqual(listing.status_code, 200)
        self.assertContains(listing, article.public_title)
        self.assertContains(listing, self.article_path(article))
        self.assertContains(listing, 'Советы мастеров')
        self.assertNotContains(listing, 's14-public-author@example')
        detail = self.client.get(self.article_path(article))
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, article.public_body)
        self.assertContains(detail, reverse(
            'marketplace:worker_public_profile', args=[self.worker.pk],
        ))
        self.assertContains(detail, reverse('marketplace:order_wizard_start'))
        self.assertContains(detail, 'Публикация статьи не повышает рейтинг')
        self.assertNotContains(detail, 'license verified')
        self.assertEqual(Order.objects.count(), 0)

    def test_unapproved_unreviewed_and_hidden_versions_are_not_public(self):
        approved = self.publish()
        draft = services.create_article(
            actor=self.writer, title='PRIVATE SYNTHETIC DRAFT',
            body='Private source not approved and must not leak to public search.',
            category_id=self.category.pk, rights_confirmed=True,
        )
        self.assertEqual(self.client.get(self.article_path(draft)).status_code, 404)
        listing = self.client.get('/ru/advice/?q=PRIVATE')
        self.assertNotContains(listing, 'PRIVATE')
        self.assertContains(listing, 'Найдено статей: 0')
        self.assertEqual(self.client.get(self.article_path(approved)).status_code, 200)
        ExpertArticle.objects.filter(pk=approved.pk).update(
            title='RAW PRIVATE TITLE; not in safe snapshot',
            body='RAW PRIVATE BODY; not in safe snapshot',
        )
        response = self.client.get(self.article_path(approved))
        self.assertContains(response, approved.public_body)
        self.assertNotContains(response, 'RAW PRIVATE BODY')
        self.assertNotContains(response, 'RAW PRIVATE TITLE')

    def test_forged_published_snapshots_without_approval_evidence_are_not_visible(self):
        article = services.create_article(
            actor=self.writer, title=TITLE, body=BODY,
            category_id=self.category.pk, rights_confirmed=True,
        )
        ExpertArticle.objects.filter(pk=article.pk).update(
            status='published', public_content_safe=True,
            public_title='FORGED PUBLIC TITLE',
            public_body='FORGED PUBLIC BODY',
            approved_version=article.content_version,
            published_at=timezone.now(),
            moderated_by=self.moderator,
        )
        self.assertFalse(ExpertArticleDecision.objects.filter(article=article).exists())
        self.assertEqual(self.client.get(self.article_path(article)).status_code, 404)
        self.assertNotContains(self.client.get('/ru/advice/'), 'FORGED PUBLIC TITLE')

    def test_mismatched_approved_version_hides_article(self):
        article = self.publish()
        ExpertArticle.objects.filter(pk=article.pk).update(
            content_version=article.content_version + 1,
        )
        self.assertEqual(self.client.get(self.article_path(article)).status_code, 404)

    def test_revoked_author_or_category_is_hidden_immediately(self):
        article = self.publish()
        path = self.article_path(article)
        self.writer.is_blocked = True
        self.writer.save(update_fields=['is_blocked'])
        self.assertEqual(self.client.get(path).status_code, 404)
        self.writer.is_blocked = False
        self.writer.save(update_fields=['is_blocked'])
        self.writer.email_verification_required = True
        self.writer.save(update_fields=['email_verification_required'])
        self.assertEqual(self.client.get(path).status_code, 404)
        self.writer.email_verification_required = False
        self.writer.save(update_fields=['email_verification_required'])
        self.worker.is_published = False
        self.worker.save(update_fields=['is_published'])
        self.assertEqual(self.client.get(path).status_code, 404)
        self.worker.is_published = True
        self.worker.save(update_fields=['is_published'])
        other_city = make_city(slug='s14-other-city')
        self.worker.city = other_city
        self.worker.save(update_fields=['city'])
        self.assertEqual(self.client.get(path).status_code, 404)
        self.worker.city = self.city
        self.worker.save(update_fields=['city'])
        self.worker.skills.remove(self.category)
        self.assertEqual(self.client.get(path).status_code, 404)
        self.worker.skills.add(self.category)
        self.category.is_active = False
        self.category.save(update_fields=['is_active'])
        self.assertEqual(self.client.get(path).status_code, 404)

    def test_inactive_parent_section_hides_article(self):
        article = self.publish()
        section = ServiceSection.objects.create(
            slug='s14-off-section', name_ru='Synthetic archived section', is_active=False,
        )
        self.category.section = section
        self.category.save(update_fields=['section'])
        self.assertEqual(self.client.get(self.article_path(article)).status_code, 404)

    def test_topic_category_and_language_filters_are_scoped_and_safe(self):
        ru = self.publish()
        extra = make_category(slug='s14-other-topic', name_ru='Synthetic extra')
        self.worker.skills.add(extra)
        en = self.publish(title='Synthetic plumbing maintenance details',
                          category=extra, language='en')
        listing = self.client.get('/ru/advice/', {'category': str(self.category.pk)})
        self.assertContains(listing, ru.public_title)
        self.assertNotContains(listing, en.public_title)
        listing = self.client.get('/en/advice/', {'language': 'en'})
        self.assertContains(listing, en.public_title)
        self.assertNotContains(listing, ru.public_title)
        listing = self.client.get('/he/advice/', {'q': 'PlUmBiNg'})
        self.assertContains(listing, en.public_title)
        self.assertNotContains(listing, ru.public_title)

    def test_search_invalid_contacts_and_unknown_fields_never_echo_private_input(self):
        self.publish()
        for params in (
            {'q': 'call +972501234567'},
            {'q': 'person@example.com'},
            {'q': 'a' * 81},
            {'category': '900000'},
            {'language': 'xx'},
        ):
            response = self.client.get('/ru/advice/', params)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'Проверьте параметры поиска')
            self.assertContains(response, 'Найдено статей: 0')
            self.assertNotContains(response, 'person@example.com')
            self.assertNotContains(response, '+972501234567')

    def test_cross_language_link_uses_article_original_locale(self):
        article = self.publish()
        listing = self.client.get('/en/advice/')
        self.assertContains(listing, self.article_path(article))
        self.assertEqual(self.client.get(
            '/en/advice/' + article.slug + '/',
        ).status_code, 404)
        self.assertEqual(self.client.get(self.article_path(article)).status_code, 200)

    def test_hebrew_unicode_slug_and_rtl_and_mobile_css(self):
        article = self.publish(
            title='בדיקת בטיחות מזגנים בבית', language='he',
        )
        path = self.article_path(article)
        self.assertTrue(path.startswith('/he/advice/'))
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'lang="he"')
        self.assertContains(response, 'dir="rtl"')
        self.assertContains(response, 'knowledge-public.css')
        self.assertContains(response, article.public_title)
        self.assertEqual(self.client.get('/ru/advice/').status_code, 200)

    def test_only_approved_images_are_public_and_jpeg_no_cache(self):
        article = self.publish(image=True)
        image = article.images.get()
        path = reverse('knowledge_public:article_image', args=[image.pk])
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'image/jpeg')
        self.assertEqual(response['Cache-Control'], 'private, no-store, max-age=0')
        self.assertIn('nosniff', response['X-Content-Type-Options'])
        self.assertIn(b'\xff\xd8', response.content[:2])
        self.assertNotIn(b'Exif', response.content)
        with override_settings(ZEMIPRO_KNOWLEDGE_ARTICLES_ENABLED=False):
            self.assertEqual(self.client.get(path).status_code, 404)
        ExpertArticleImage.objects.filter(pk=image.pk).update(approved_version=None)
        self.assertEqual(self.client.get(path).status_code, 404)

    def test_image_cannot_outlive_article_publication(self):
        article = self.publish(image=True)
        image = article.images.get()
        url = reverse('knowledge_public:article_image', args=[image.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        services.archive_article(
            actor=self.writer, article_id=article.pk,
            expected_version=article.content_version,
        )
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.get(self.article_path(article)).status_code, 404)

    def test_article_and_query_urls_are_noindex_with_canonical_metadata(self):
        article = self.publish()
        path = self.article_path(article)
        detail = self.client.get(path + '?some_filter=1')
        self.assertContains(detail, 'name="robots" content="noindex,follow"')
        self.assertContains(
            detail,
            'rel="canonical" href="http://testserver' + path + '"',
        )
        self.assertContains(detail, 'application/ld+json')
        self.assertContains(detail, 'https://schema.org')
        listing = self.client.get('/ru/advice/?q=synthetic')
        self.assertContains(listing, 'noindex,follow')
        self.assertContains(
            listing, 'rel="canonical" href="http://testserver/ru/advice/"',
        )
        self.assertNotContains(listing, '<script type="application/ld+json">')

    def test_article_schema_has_real_data_only_and_cannot_break_script(self):
        article = self.publish()
        path = self.article_path(article)
        result = self.client.get(path).content.decode()
        match = re.search(r'<script type="application/ld\+json">(.+?)</script>', result)
        self.assertIsNotNone(match)
        payload = json.loads(match.group(1))
        self.assertEqual(payload['@type'], 'Article')
        self.assertEqual(payload['author']['name'], self.worker.public_display_name)
        self.assertEqual(payload['headline'], article.public_title)
        self.assertNotIn('aggregateRating', payload)
        ExpertArticle.objects.filter(pk=article.pk).update(
            public_title='Synthetic <script>alert("XSS")</script>',
        )
        response = self.client.get(path)
        self.assertNotContains(response, '<script>alert("XSS")</script>')
        self.assertContains(response, '&lt;script&gt;')
        match = re.search(
            r'<script type="application/ld\+json">(.+?)</script>',
            response.content.decode(),
        )
        self.assertIsNotNone(match)
        self.assertIn('\\u003cscript\\u003e', match.group(1))

    def test_human_translation_has_only_approved_hreflang(self):
        original = self.publish(language='ru')
        english = self.publish(
            title='Synthetic English reviewed advice', language='en',
            kind='human', group=original.translation_group,
        )
        response = self.client.get(self.article_path(english))
        self.assertContains(response, 'Human-reviewed translation')
        self.assertContains(response, 'hreflang="en"')
        self.assertContains(response, 'hreflang="ru"')
        self.assertContains(response, self.article_path(original))
        self.assertContains(response, (
            'rel="canonical" href="http://testserver' +
            self.article_path(english) + '"'
        ))
        self.assertEqual(sitemap_candidates().count(), 2)

    def test_machine_translation_noindex_canonical_original_no_jsonld(self):
        original = self.publish(language='ru')
        machine = self.publish(
            title='סיכום בדיקה מלאכותי', language='he',
            kind='machine', group=original.translation_group,
        )
        response = self.client.get(self.article_path(machine))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'תרגום מכונה')
        self.assertContains(response, self.article_path(original))
        self.assertContains(response, (
            'rel="canonical" href="http://testserver' +
            self.article_path(original) + '"'
        ))
        self.assertNotContains(response, 'application/ld+json')
        self.assertNotContains(response, 'hreflang="he"')
        self.assertEqual(sitemap_candidates().count(), 1)

    def test_sidebar_author_and_category_are_real_profile_links(self):
        article = self.publish()
        response = self.client.get(self.article_path(article))
        self.assertContains(response, reverse(
            'catalog_i18n:category_detail', kwargs={'slug': self.category.slug},
        ))
        profile_url = reverse('marketplace:worker_public_profile', args=[self.worker.pk])
        self.assertContains(response, profile_url)
        profile = self.client.get(profile_url)
        self.assertContains(profile, 'Статьи специалиста')
        self.assertContains(profile, article.public_title)
        with override_settings(ZEMIPRO_KNOWLEDGE_ARTICLES_ENABLED=False):
            self.assertNotContains(self.client.get(profile_url), article.public_title)

    def test_report_submission_works_when_authoring_is_off(self):
        article = self.publish()
        with override_settings(ZEMIPRO_KNOWLEDGE_AUTHORING_ENABLED=False):
            self.client.force_login(self.reader)
            report = self.client.get(reverse(
                'knowledge:article_report', args=[article.pk],
            ))
            self.assertEqual(report.status_code, 200)
            result = self.client.post(
                reverse('knowledge:article_report', args=[article.pk]), {
                    'reason': 'dangerous', 'message': 'Synthetic safety complaint for review.',
                },
            )
            self.assertEqual(result.status_code, 302)
            self.assertEqual(result['Location'], self.article_path(article))
            self.assertEqual(ExpertArticleReport.objects.count(), 1)
            self.client.force_login(self.moderator)
            self.assertEqual(self.client.get(
                reverse('knowledge:moderation_queue'),
            ).status_code, 200)
            case = ExpertArticleReport.objects.get()
            decision = self.client.post(
                reverse('knowledge:report_decision', args=[case.pk]), {
                    'action': 'remove', 'note': 'Removed after review of unsafe advice',
                },
            )
            self.assertEqual(decision.status_code, 302)
            self.assertEqual(self.client.get(self.article_path(article)).status_code, 404)

    def test_unauthorized_report_stays_private_and_does_not_create_order(self):
        article = self.publish()
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(self.client.get(reverse(
            'knowledge:article_report', args=[article.pk],
        )).status_code, 302)
        self.assertEqual(self.client.get(self.article_path(article)).status_code, 200)
        self.assertEqual(Order.objects.count(), 0)

    def test_pagination_is_bounded_and_has_stable_query_links(self):
        with patch('apps.knowledge.services._charge', return_value=None):
            for i in range(13):
                self.publish(title=f'Synthetic reviewed advice number {i} for Ashdod')
        response = self.client.get('/ru/advice/', {
            'q': 'Synthetic', 'category': str(self.category.pk), 'page': '2',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['page_obj'].paginator.count, 13)
        self.assertEqual(response.context['page_obj'].number, 2)
        self.assertContains(response, 'page=1')
        self.assertContains(response, 'category=')

    def test_all_public_urls_are_get_only_and_do_not_create_orders(self):
        article = self.publish()
        list_url = reverse('knowledge_public:article_list')
        detail_url = self.article_path(article)
        self.assertEqual(self.client.post(list_url).status_code, 405)
        self.assertEqual(self.client.post(detail_url).status_code, 405)
        self.assertEqual(Order.objects.count(), 0)
        response = self.client.get(detail_url)
        self.assertContains(response, reverse('marketplace:order_wizard_start'))
        self.assertEqual(Order.objects.count(), 0)
