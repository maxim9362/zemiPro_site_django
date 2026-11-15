from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError, connection, transaction
from django.test import TestCase, TransactionTestCase, override_settings

from apps.locations.models import City
from apps.marketplace.models import Category
from apps.seo.models import SeoContentPage, SeoContentRevision, SeoLegacyUrl
from apps.seo.services import approve_content, publish_content, revise_content, unpublish_content


class Stage09SeoModelTests(TestCase):
    def setUp(self):
        self.author = get_user_model().objects.create_user(username='seo-author')
        self.reviewer = get_user_model().objects.create_user(
            username='seo-reviewer', is_staff=True,
        )
        self.category = Category.objects.create(
            slug='stage09-cleaning', name_ru='Уборка', name_en='Cleaning',
            name_he='ניקיון', description='Описание', description_en='Description',
            description_he='תיאור',
        )
        self.page = SeoContentPage.objects.create(
            page_type=SeoContentPage.PageType.CATEGORY,
            language='ru', category=self.category, topic='Уборка в Ашдоде',
            title='Уборка в Ашдоде',
            meta_description='Проверенное описание услуги для безопасного выбора исполнителя в Ашдоде.',
            summary='Как выбрать подходящую услугу и оформить заявку без раскрытия контактов.',
            body=(
                'Полезный редакционный текст без цен, отзывов и выдуманной статистики. '
                'Он объясняет границы услуги, рекомендует описывать задачу через защищённую '
                'заявку и предлагает сравнивать только реальные опубликованные анкеты.'
            ),
            source_facts='Актуальный Django-каталог; редакционная проверка.',
            status=SeoContentPage.Status.DRAFT, author=self.author,
        )
        self.grant(self.author, 'change_seocontentpage')

    def grant(self, user, *codenames):
        user.user_permissions.add(*Permission.objects.filter(codename__in=codenames))
        user.refresh_from_db()

    @override_settings(ZEMIPRO_PILOT_CITY_SLUG='ashdod')
    def test_only_exact_ashdod_landing_is_allowed(self):
        other_city = City.objects.create(
            slug='tel-aviv-stage09', name_ru='Тель-Авив', name_en='Tel Aviv',
            name_he='תל אביב',
        )
        page = SeoContentPage(
            page_type=SeoContentPage.PageType.CITY, language='ru', city=other_city,
            topic='Other', title='Other', meta_description='Other', summary='Other',
            body='Distinct editorial content.', source_facts='Synthetic test fact.',
            author=self.author,
        )
        with self.assertRaises(ValidationError):
            page.full_clean()

    def test_duplicate_language_content_is_rejected(self):
        duplicate = SeoContentPage(
            page_type=SeoContentPage.PageType.CATEGORY, language='ru',
            category=Category.objects.create(slug='stage09-other', name_ru='Другое'),
            topic='Different topic', title=self.page.title,
            meta_description='Different meta', summary=self.page.summary,
            body=self.page.body, source_facts='Synthetic test fact.', author=self.author,
        )
        with self.assertRaises(ValidationError):
            duplicate.full_clean()

    def test_editorial_cas_review_publish_and_unpublish(self):
        revised = revise_content(
            page_id=self.page.pk, actor=self.author, expected_version=1,
            changes={
                'status': SeoContentPage.Status.REVIEW,
                'summary': 'Reviewed summary with sufficient editorial context for approval.',
            },
        )
        self.assertEqual(revised.version, 2)
        self.assertEqual(revised.revisions.count(), 1)
        with self.assertRaises(ValidationError):
            revise_content(
                page_id=self.page.pk, actor=self.author, expected_version=1,
                changes={'summary': 'stale'},
            )

        self.grant(
            self.reviewer, 'change_seocontentpage',
            'review_seo_content', 'publish_seo_content',
        )
        approved = approve_content(
            page_id=self.page.pk, actor=self.reviewer, expected_version=2,
        )
        self.assertEqual(approved.status, SeoContentPage.Status.APPROVED)
        published = publish_content(
            page_id=self.page.pk, actor=self.reviewer, expected_version=3,
        )
        self.assertEqual(published.status, SeoContentPage.Status.PUBLISHED)
        self.assertIsNotNone(published.published_at)
        withdrawn = unpublish_content(
            page_id=self.page.pk, actor=self.reviewer, expected_version=4,
        )
        self.assertEqual(withdrawn.status, SeoContentPage.Status.APPROVED)
        self.assertIsNone(withdrawn.published_at)
        self.assertEqual(withdrawn.revisions.count(), 4)

    def test_substantive_edits_revoke_review_and_publication(self):
        self.grant(
            self.reviewer, 'change_seocontentpage',
            'review_seo_content', 'publish_seo_content',
        )
        submitted = revise_content(
            page_id=self.page.pk, actor=self.author, expected_version=1,
            changes={'status': SeoContentPage.Status.REVIEW},
        )
        approved = approve_content(
            page_id=self.page.pk, actor=self.reviewer,
            expected_version=submitted.version,
        )
        changed = revise_content(
            page_id=self.page.pk, actor=self.author,
            expected_version=approved.version,
            changes={'body': self.page.body + ' Новая редакция требует новой проверки.'},
        )
        self.assertEqual(changed.status, SeoContentPage.Status.DRAFT)
        self.assertFalse(changed.quality_approved)
        self.assertIsNone(changed.reviewer)
        self.assertIsNone(changed.reviewed_at)
        with self.assertRaises(ValidationError):
            publish_content(
                page_id=self.page.pk, actor=self.reviewer,
                expected_version=changed.version,
            )

        resubmitted = revise_content(
            page_id=self.page.pk, actor=self.author,
            expected_version=changed.version,
            changes={'status': SeoContentPage.Status.REVIEW},
        )
        reapproved = approve_content(
            page_id=self.page.pk, actor=self.reviewer,
            expected_version=resubmitted.version,
        )
        published = publish_content(
            page_id=self.page.pk, actor=self.reviewer,
            expected_version=reapproved.version,
        )
        changed_live = revise_content(
            page_id=self.page.pk, actor=self.reviewer,
            expected_version=published.version,
            changes={'summary': self.page.summary + ' Изменённый публичный текст.'},
        )
        self.assertEqual(changed_live.status, SeoContentPage.Status.DRAFT)
        self.assertFalse(changed_live.quality_approved)
        self.assertIsNone(changed_live.reviewer)
        self.assertIsNone(changed_live.published_at)

    def test_unprivileged_actor_cannot_edit_another_page(self):
        stranger = get_user_model().objects.create_user(username='seo-stranger')
        with self.assertRaises(PermissionDenied):
            revise_content(
                page_id=self.page.pk, actor=stranger, expected_version=1,
                changes={'summary': 'not allowed'},
            )

    def test_legacy_redirect_fails_closed(self):
        row = SeoLegacyUrl(
            path='/master/example/', decision=SeoLegacyUrl.Decision.REDIRECT,
            target_path='/master/example/', evidence_source='Synthetic evidence.',
        )
        with self.assertRaises(ValidationError):
            row.full_clean()

    def test_active_legacy_decision_must_be_deactivated_before_edit(self):
        self.grant(self.reviewer, 'approve_legacy_url')
        row = SeoLegacyUrl.objects.create(
            path='/master/stage09-active-lock/',
            decision=SeoLegacyUrl.Decision.GONE,
            evidence_source='Synthetic removal evidence.',
        )
        from apps.seo.legacy import activate_legacy_url, deactivate_legacy_url

        activate_legacy_url(row_id=row.pk, actor=self.reviewer)
        row.refresh_from_db()
        row.decision = SeoLegacyUrl.Decision.NOT_FOUND
        with self.assertRaises(ValidationError):
            row.save()
        deactivate_legacy_url(row_id=row.pk, actor=self.reviewer)
        row.refresh_from_db()
        row.decision = SeoLegacyUrl.Decision.NOT_FOUND
        row.save()
        self.assertEqual(row.decision, SeoLegacyUrl.Decision.NOT_FOUND)
        row.target_path = 'https://attacker.example/'
        with self.assertRaises(ValidationError):
            row.full_clean()
        row.target_path = '/ru/categories/stage09-cleaning/'
        row.is_active = True
        with self.assertRaises(ValidationError):
            row.full_clean()


class Stage09RevisionDatabaseTests(TransactionTestCase):
    reset_sequences = True

    def test_revision_update_and_delete_are_blocked_by_postgresql(self):
        author = get_user_model().objects.create_user(username='seo-db-author')
        category = Category.objects.create(slug='seo-db-category', name_ru='DB category')
        page = SeoContentPage.objects.create(
            page_type='category', language='ru', category=category, topic='DB topic',
            title='DB title', meta_description='DB description', summary='DB summary',
            body='Unique DB revision body.', source_facts='Synthetic DB source.',
            author=author,
        )
        revision = SeoContentRevision.objects.create(
            page=page, version=1, snapshot={'title': page.title}, created_by=author,
        )
        with self.assertRaises(DatabaseError), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    'UPDATE seo_seocontentrevision SET version = 2 WHERE id = %s',
                    [revision.pk],
                )
        with self.assertRaises(DatabaseError), transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    'DELETE FROM seo_seocontentrevision WHERE id = %s', [revision.pk],
                )
        self.assertTrue(SeoContentRevision.objects.filter(pk=revision.pk, version=1).exists())
