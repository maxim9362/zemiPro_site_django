"""Stage 14.2: synthetic PostgreSQL security, lifecycle, photo and HTTP checks."""
from io import BytesIO

from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import DatabaseError, transaction
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from PIL import Image

from apps.knowledge import services, pilot_services
from apps.knowledge.models import (
    ExpertArticle, ExpertArticleDecision, ExpertArticleImage,
    ExpertArticleReport, ExpertArticleRevision,
)
from apps.marketplace.tests.factories import (
    make_category, make_city, make_user, make_worker_profile,
)


TITLE = 'Synthetic preventative maintenance advice'
BODY = (
    'Synthetic practical advice for general maintenance only. Inspect the '
    'equipment carefully, follow the supplied manufacturer manual and consult '
    'a qualified professional when work would be unsafe.'
)


def png_upload():
    output = BytesIO()
    Image.new('RGB', (32, 32), (120, 155, 190)).save(output, format='PNG')
    return SimpleUploadedFile(
        'synthetic.png', output.getvalue(), content_type='image/png',
    )


@override_settings(ZEMIPRO_KNOWLEDGE_AUTHORING_ENABLED=True)
class Stage14AuthoringTests(TestCase):
    def setUp(self):
        self.city = make_city(slug='ashdod', name_ru='Synthetic Ashdod')
        self.category = make_category(slug='s14-article-category')
        self.writer = make_user('s14-article-writer')
        self.other = make_user('s14-article-other')
        self.reader = make_user('s14-article-reader')
        self.staff = make_user('s14-article-moderator', is_staff=True)
        perm = Permission.objects.get(codename='moderate_expert_articles')
        self.staff.user_permissions.add(perm)
        self.worker = make_worker_profile(
            self.writer, city=self.city, category=self.category,
        )
        self.other_worker = make_worker_profile(
            self.other, city=self.city, category=self.category,
        )

    def draft(self, **overrides):
        args = {
            'actor': self.writer, 'title': TITLE, 'excerpt': 'Synthetic summary',
            'body': BODY, 'category_id': self.category.pk,
            'language': 'ru', 'rights_confirmed': True,
        }
        args.update(overrides)
        return services.create_article(**args)

    def submitted(self):
        article = self.draft()
        return services.submit_article(
            actor=self.writer, article_id=article.pk,
            expected_version=article.content_version, rights_confirmed=True,
        )

    def approved(self):
        article = self.submitted()
        article = services.decide_article(
            actor=self.staff, article_id=article.pk,
            expected_version=article.content_version,
            approve=True, content_reviewed=True,
        )
        # Stage14.4 now requires separately verified pilot consent/selection.
        pilot_services.consent_to_pilot(self.writer, confirmed=True)
        pilot_services.select_for_pilot(
            self.staff, article_id=article.pk,
            expected_version=article.content_version,
        )
        return article

    def test_new_draft_has_private_content_and_append_only_revision(self):
        article = self.draft()
        self.assertEqual(article.status, 'draft')
        self.assertEqual(article.content_version, 1)
        self.assertFalse(article.public_content_safe)
        self.assertEqual(article.public_body, '')
        self.assertEqual(article.images.count(), 0)
        self.assertEqual(services.own_article(self.writer, article.pk).pk, article.pk)
        self.assertEqual(article.revisions.count(), 1)
        self.assertEqual(article.revisions.first().actor_id, self.writer.pk)
        self.assertEqual(article.revisions.first().action, 'created')
        with self.assertRaises(PermissionDenied):
            services.own_article(self.other, article.pk)

    def test_submit_and_approve_persist_safe_snapshot_and_audit(self):
        article = self.submitted()
        self.assertEqual(article.status, 'pending_review')
        self.assertEqual(article.content_version, 2)
        self.assertFalse(article.public_content_safe)
        self.assertEqual(len(services.moderation_queue(self.staff)), 1)
        article = services.decide_article(
            actor=self.staff, article_id=article.pk,
            expected_version=2, approve=True, content_reviewed=True,
        )
        self.assertEqual(article.status, 'published')
        self.assertEqual(article.public_title, TITLE)
        self.assertEqual(article.public_body, BODY)
        self.assertEqual(article.approved_version, 3)
        self.assertEqual(article.revisions.count(), 3)
        self.assertEqual(article.decisions.get().kind, 'approve')
        self.assertEqual(article.decisions.get().moderator_id, self.staff.pk)
        with self.assertRaises(DatabaseError), transaction.atomic():
            ExpertArticleRevision.objects.filter(article=article).update(body='Forged')
        with self.assertRaises(DatabaseError), transaction.atomic():
            ExpertArticleDecision.objects.filter(article=article).delete()

    def test_contact_obfuscation_and_html_rejected_pre_persistence(self):
        for text in (
            'Reach me at +972501234567, this is the easiest way.',
            'Text me at someone [at] example [dot] com',
            '<script>alert("x")</script>',
            'https://example.invalid/private',
        ):
            with self.subTest(text=text):
                with self.assertRaises(services.ArticleConflict):
                    self.draft(body=text)
        self.assertEqual(ExpertArticle.objects.count(), 0)

    def test_short_draft_allowed_but_submitting_requires_complete_text(self):
        article = self.draft(title='Idea', body='')
        self.assertEqual(article.status, 'draft')
        with self.assertRaises(services.ArticleConflict):
            services.submit_article(
                actor=self.writer, article_id=article.pk,
                expected_version=article.content_version, rights_confirmed=True,
            )
        self.assertEqual(article.revisions.count(), 1)

    def test_client_other_worker_city_and_unpublished_are_denied(self):
        with self.assertRaises(PermissionDenied):
            self.draft(actor=self.reader)
        article = self.draft()
        with self.assertRaises(PermissionDenied):
            services.edit_article(
                actor=self.other, article_id=article.pk,
                expected_version=article.content_version,
                title=TITLE, excerpt='', body=BODY,
                category_id=self.category.pk, rights_confirmed=True,
            )
        foreign_city = make_city(slug='tel-aviv-s14')
        self.worker.city = foreign_city
        self.worker.save(update_fields=['city'])
        with self.assertRaises(PermissionDenied):
            self.draft(title='Outside pilot')
        self.worker.city = self.city
        self.worker.is_published = False
        self.worker.save(update_fields=['city', 'is_published'])
        with self.assertRaises(PermissionDenied):
            self.draft(title='Not published')

    def test_blocked_and_email_unverified_denied_from_live_database(self):
        self.writer.is_blocked = True
        self.writer.save(update_fields=['is_blocked'])
        with self.assertRaises(PermissionDenied):
            self.draft()
        self.writer.is_blocked = False
        self.writer.email_verification_required = True
        self.writer.save(update_fields=['is_blocked', 'email_verification_required'])
        with self.assertRaises(PermissionDenied):
            self.draft()

    def test_stale_edit_and_pending_edit_rejected(self):
        article = self.draft()
        with self.assertRaises(services.ArticleConflict):
            services.edit_article(
                actor=self.writer, article_id=article.pk, expected_version=0,
                title=TITLE, excerpt='', body=BODY,
                category_id=self.category.pk, rights_confirmed=True,
            )
        article = services.submit_article(
            actor=self.writer, article_id=article.pk, expected_version=1,
            rights_confirmed=True,
        )
        with self.assertRaises(services.ArticleConflict):
            services.edit_article(
                actor=self.writer, article_id=article.pk, expected_version=2,
                title=TITLE, excerpt='', body=BODY,
                category_id=self.category.pk, rights_confirmed=True,
            )

    def test_rejection_requires_reason_and_revisions_are_versioned(self):
        article = self.submitted()
        with self.assertRaises(services.ArticleConflict):
            services.decide_article(
                actor=self.staff, article_id=article.pk, expected_version=2,
                approve=True, content_reviewed=False,
            )
        with self.assertRaises(services.ArticleConflict):
            services.decide_article(
                actor=self.staff, article_id=article.pk, expected_version=2,
                approve=False, note='',
            )
        article = services.decide_article(
            actor=self.staff, article_id=article.pk, expected_version=2,
            approve=False, note='Needs stronger factual support',
        )
        self.assertEqual(article.status, 'rejected')
        self.assertEqual(article.decisions.get().reason, 'Needs stronger factual support')
        revised = services.edit_article(
            actor=self.writer, article_id=article.pk,
            expected_version=3, title=TITLE,
            excerpt='More cautious synthetic overview', body=BODY,
            category_id=self.category.pk, rights_confirmed=True,
        )
        self.assertEqual(revised.content_version, 4)
        self.assertEqual(revised.status, 'draft')
        self.assertEqual(revised.revisions.count(), 4)

    def test_moderation_rechecks_author_and_category_current_eligibility(self):
        article = self.submitted()
        self.writer.is_blocked = True
        self.writer.save(update_fields=['is_blocked'])
        with self.assertRaises(services.ArticleConflict):
            services.decide_article(
                actor=self.staff, article_id=article.pk,
                expected_version=2, approve=True, content_reviewed=True,
            )
        self.writer.is_blocked = False
        self.writer.save(update_fields=['is_blocked'])
        self.worker.is_published = False
        self.worker.save(update_fields=['is_published'])
        with self.assertRaises(services.ArticleConflict):
            services.decide_article(
                actor=self.staff, article_id=article.pk,
                expected_version=2, approve=True, content_reviewed=True,
            )
        self.worker.is_published = True
        self.worker.save(update_fields=['is_published'])
        self.category.is_active = False
        self.category.save(update_fields=['is_active'])
        with self.assertRaises(services.ArticleConflict):
            services.decide_article(
                actor=self.staff, article_id=article.pk,
                expected_version=2, approve=True, content_reviewed=True,
            )
        article.refresh_from_db()
        self.assertEqual(article.status, 'pending_review')
        self.assertEqual(article.decisions.count(), 0)

    def test_published_edit_unpublishes_and_stale_review_conflicts(self):
        article = self.approved()
        edited = services.edit_article(
            actor=self.writer, article_id=article.pk,
            expected_version=article.content_version, title=TITLE,
            excerpt='Fresh unreviewed synthetic text', body=BODY + ' New details.',
            category_id=self.category.pk, rights_confirmed=True,
        )
        self.assertEqual(edited.status, 'draft')
        self.assertFalse(edited.public_content_safe)
        self.assertEqual(edited.public_body, '')
        self.assertIsNone(edited.approved_version)
        with self.assertRaises(services.ArticleConflict):
            services.decide_article(
                actor=self.staff, article_id=article.pk, expected_version=3,
                approve=True, content_reviewed=True,
            )

    def test_author_archive_revokes_public_snapshot(self):
        article = self.approved()
        archived = services.archive_article(
            actor=self.writer, article_id=article.pk,
            expected_version=article.content_version,
        )
        self.assertEqual(archived.status, 'archived')
        self.assertEqual(archived.public_title, '')
        self.assertFalse(archived.public_content_safe)
        with self.assertRaises(services.ArticleConflict):
            services.archive_article(
                actor=self.writer, article_id=article.pk,
                expected_version=archived.content_version,
            )

    def test_image_is_normalized_privately_and_transactional(self):
        article = self.draft()
        photo = services.add_article_image(
            actor=self.writer, article_id=article.pk,
            expected_version=article.content_version, upload=png_upload(),
            caption='Synthetic maintenance image', rights_confirmed=True,
        )
        self.assertTrue(bytes(photo.jpeg_data).startswith(b'\xff\xd8'))
        self.assertFalse(photo.public_caption)
        self.assertIsNone(photo.approved_version)
        self.assertEqual(photo.byte_size, len(bytes(photo.jpeg_data)))
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                services.add_article_image(
                    actor=self.writer, article_id=article.pk,
                    expected_version=2, upload=png_upload(),
                    rights_confirmed=True,
                )
                raise RuntimeError('Rollback synthetic transaction')
        self.assertEqual(ExpertArticleImage.objects.filter(article=article).count(), 1)

    def test_invalid_media_and_image_limit(self):
        article = self.draft()
        with self.assertRaises(services.ArticleConflict):
            services.add_article_image(
                actor=self.writer, article_id=article.pk, expected_version=1,
                upload=SimpleUploadedFile(
                    'evil.jpg', b'<script>not a JPEG</script>', content_type='image/jpeg',
                ), rights_confirmed=True,
            )
        for i in range(3):
            article.refresh_from_db()
            services.add_article_image(
                actor=self.writer, article_id=article.pk,
                expected_version=article.content_version, upload=png_upload(),
                rights_confirmed=True,
            )
        article.refresh_from_db()
        with self.assertRaises(services.ArticleConflict):
            services.add_article_image(
                actor=self.writer, article_id=article.pk,
                expected_version=article.content_version,
                upload=png_upload(), rights_confirmed=True,
            )
        self.assertEqual(article.images.count(), 3)

    def test_images_need_explicit_manual_review(self):
        article = self.draft()
        services.add_article_image(
            actor=self.writer, article_id=article.pk,
            expected_version=1, upload=png_upload(), rights_confirmed=True,
        )
        article.refresh_from_db()
        article = services.submit_article(
            actor=self.writer, article_id=article.pk,
            expected_version=article.content_version, rights_confirmed=True,
        )
        with self.assertRaises(services.ArticleConflict):
            services.decide_article(
                actor=self.staff, article_id=article.pk,
                expected_version=article.content_version,
                approve=True, content_reviewed=True, media_reviewed=False,
            )
        article = services.decide_article(
            actor=self.staff, article_id=article.pk,
            expected_version=article.content_version,
            approve=True, content_reviewed=True, media_reviewed=True,
        )
        photo = article.images.get()
        self.assertEqual(photo.approved_version, article.approved_version)
        self.assertFalse(photo.public_caption)

    def test_moderation_staff_permission_and_no_self_approval(self):
        article = self.submitted()
        unauthorized = make_user('s14-staff-no-perm', is_staff=True)
        with self.assertRaises(PermissionDenied):
            services.decide_article(
                actor=unauthorized, article_id=article.pk,
                expected_version=2, approve=True, content_reviewed=True,
            )
        self.writer.is_staff = True
        self.writer.save(update_fields=['is_staff'])
        perm = Permission.objects.get(codename='moderate_expert_articles')
        self.writer.user_permissions.add(perm)
        with self.assertRaises(PermissionDenied):
            services.decide_article(
                actor=self.writer, article_id=article.pk,
                expected_version=2, approve=True, content_reviewed=True,
            )

    @override_settings(ZEMIPRO_KNOWLEDGE_ARTICLES_ENABLED=True)
    def test_report_removal_archives_article_with_audit(self):
        article = self.approved()
        report = services.report_article(
            actor=self.reader, article_id=article.pk,
            reason='dangerous', message='Synthetic safety issue to review.',
        )
        self.assertEqual(report.status, 'pending')
        self.assertEqual(len(services.report_queue(self.staff)), 1)
        result = services.decide_report(
            actor=self.staff, report_id=report.pk, remove=True,
            note='Remove potentially unsafe instructions',
        )
        self.assertEqual(result.status, 'removed')
        article.refresh_from_db()
        self.assertEqual(article.status, 'archived')
        self.assertFalse(article.public_content_safe)
        self.assertEqual(article.decisions.filter(kind='remove').count(), 1)
        with self.assertRaises(services.ArticleConflict):
            services.decide_report(
                actor=self.staff, report_id=report.pk,
                remove=False,
            )

    @override_settings(ZEMIPRO_KNOWLEDGE_ARTICLES_ENABLED=True)
    def test_duplicate_report_dismiss_and_preserve_article(self):
        article = self.approved()
        report = services.report_article(
            actor=self.reader, article_id=article.pk,
            reason='other', message='Synthetic report, please check context.',
        )
        with self.assertRaises(services.ArticleConflict):
            services.report_article(
                actor=self.reader, article_id=article.pk,
                reason='spam', message='Second synthetic report duplicate.',
            )
        result = services.decide_report(
            actor=self.staff, report_id=report.pk, remove=False,
        )
        self.assertEqual(result.status, 'dismissed')
        article.refresh_from_db()
        self.assertEqual(article.status, 'published')

    def test_reports_disabled_and_unauthorized_visibility(self):
        article = self.approved()
        with self.assertRaises(PermissionDenied):
            services.report_article(
                actor=self.reader, article_id=article.pk,
                reason='spam', message='Synthetic spam concern.',
            )
        with override_settings(ZEMIPRO_KNOWLEDGE_ARTICLES_ENABLED=True):
            with self.assertRaises(PermissionDenied):
                services.report_article(
                    actor=self.writer, article_id=article.pk,
                    reason='spam', message='Self report for testing.',
                )

    def test_quota_limits_successful_creations(self):
        for i in range(5):
            self.draft(title=f'Synthetic idea number {i}')
        with self.assertRaises(services.ArticleConflict):
            self.draft(title='Synthetic idea above daily quota')
        self.assertEqual(ExpertArticle.objects.count(), 5)

    def test_hebrew_original_language_does_not_autopublish(self):
        article = self.draft(
            language='he', title='בדיקת מערכת בבית', body=BODY,
        )
        self.assertEqual(article.language, 'he')
        self.assertEqual(article.translation_kind, 'original')
        self.assertFalse(article.public_content_safe)

    def test_private_routes_disabled_by_default(self):
        self.client.force_login(self.writer)
        with override_settings(ZEMIPRO_KNOWLEDGE_AUTHORING_ENABLED=False):
            self.assertEqual(self.client.get(
                reverse('knowledge:my_articles'),
            ).status_code, 404)
            self.assertEqual(self.client.get(
                reverse('knowledge:article_create'),
            ).status_code, 404)

    def test_http_permission_owner_staff_and_hidden_drafts(self):
        article = self.draft()
        edit = reverse('knowledge:article_edit', args=[article.pk])
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(edit).status_code, 404)
        self.client.force_login(self.reader)
        self.assertEqual(self.client.get(
            reverse('knowledge:article_create'),
        ).status_code, 403)
        self.client.force_login(self.writer)
        response = self.client.get(edit)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, TITLE)
        self.assertEqual(response['Cache-Control'], 'private, no-store, max-age=0')
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(
            reverse('knowledge:moderation_queue'),
        ).status_code, 200)
        # Staff without a worker profile is blocked before object lookup.
        # Existing and nonexistent article IDs both give 403: no existence oracle.
        self.assertEqual(self.client.get(edit).status_code, 403)
        self.assertEqual(self.client.get(
            reverse('knowledge:article_edit', args=[article.pk + 12345]),
        ).status_code, 403)

    def test_http_create_submit_and_moderate(self):
        self.client.force_login(self.writer)
        response = self.client.post(reverse('knowledge:article_create'), {
            'title': TITLE, 'excerpt': 'Synthetic overview',
            'body': BODY, 'category': str(self.category.pk),
            'subcategory': '', 'language': 'ru', 'rights_confirmed': 'on',
        })
        self.assertEqual(response.status_code, 302)
        article = ExpertArticle.objects.get()
        self.assertEqual(article.content_version, 1)
        response = self.client.post(reverse('knowledge:article_submit', args=[article.pk]), {
            'expected_version': 1, 'rights_confirmed': 'on',
        })
        self.assertEqual(response.status_code, 302)
        self.client.force_login(self.staff)
        response = self.client.post(
            reverse('knowledge:moderation_article', args=[article.pk]), {
                'expected_version': 2, 'action': 'approve',
                'content_reviewed': 'on',
            },
        )
        self.assertEqual(response.status_code, 302)
        article.refresh_from_db()
        self.assertEqual(article.status, 'published')
        self.assertEqual(article.revisions.count(), 3)

    def test_http_csrf_and_image_idor(self):
        article = self.draft()
        photo = services.add_article_image(
            actor=self.writer, article_id=article.pk,
            expected_version=article.content_version, upload=png_upload(),
            rights_confirmed=True,
        )
        path = reverse('knowledge:article_image_private', args=[photo.pk])
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(path).status_code, 404)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(path).status_code, 200)
        self.assertEqual(self.client.get(path)['Content-Type'], 'image/jpeg')
        self.client.force_login(self.writer)
        self.assertEqual(self.client.get(path).status_code, 200)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.writer)
        self.assertEqual(csrf_client.post(
            reverse('knowledge:article_create'), {
                'title': TITLE, 'body': BODY, 'category': self.category.pk,
                'language': 'ru',
            },
        ).status_code, 403)

    def test_hebrew_and_english_editor_render_rtl_or_ltr(self):
        self.client.force_login(self.writer)
        for language, expected_dir in [('he', 'rtl'), ('en', 'ltr'), ('ru', 'ltr')]:
            with self.subTest(language=language):
                response = self.client.get(
                    reverse('knowledge:article_create'),
                    HTTP_ACCEPT_LANGUAGE=language,
                )
                self.assertEqual(response.status_code, 200)
                self.assertIn(
                    f'dir="{expected_dir}"', response.content.decode(),
                )

    def test_article_report_reason_choices_are_localized(self):
        from django.utils import translation
        from apps.knowledge.forms import ArticleReportForm
        for language, expected in (
            ('en', 'Private information'), ('he', 'מידע אישי'),
            ('ru', 'Персональные данные'),
        ):
            with self.subTest(language=language), translation.override(language):
                form = ArticleReportForm()
                options = dict(form.fields['reason'].choices)
                self.assertEqual(str(options['private']), expected)

    def test_no_public_article_endpoint_is_registered_yet(self):
        from django.urls import NoReverseMatch
        with self.assertRaises(NoReverseMatch):
            reverse('knowledge:article_detail', args=[1])
        self.assertEqual(ExpertArticleReport.objects.count(), 0)
