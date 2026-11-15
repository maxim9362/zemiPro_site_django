"""Stage 14.8 personal recommendations remain separate, safe and moderated."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied
from django.db import DatabaseError, close_old_connections, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse

from apps.knowledge import recommendation_services
from apps.knowledge.models import PersonalRecommendationRevision
from apps.marketplace.models import Rating
from apps.marketplace.tests.factories import (
    make_category, make_city, make_user, make_worker_profile,
)


BODY = (
    'I personally used this specialist outside ZemiPro for a synthetic repair '
    'and the work was explained clearly and completed carefully.'
)


@override_settings(ZEMIPRO_PERSONAL_RECOMMENDATIONS_ENABLED=True)
class Stage14RecommendationTests(TestCase):
    def setUp(self):
        self.city = make_city(slug='ashdod', name_ru='Synthetic Ashdod')
        self.category = make_category(slug='s14-recommendation')
        self.author = make_user('s14-rec-author')
        self.other = make_user('s14-rec-other')
        self.worker_user = make_user('s14-rec-worker')
        self.worker = make_worker_profile(
            self.worker_user, city=self.city, category=self.category,
        )
        self.staff = make_user('s14-rec-staff', is_staff=True)
        self.staff.user_permissions.add(Permission.objects.get(
            codename='moderate_personal_recommendations',
        ))

    def submitted(self):
        item = recommendation_services.create_recommendation(
            actor=self.author, worker_id=self.worker.pk, language='en', body=BODY,
            experience_confirmed=True,
        )
        return recommendation_services.submit_recommendation(
            actor=self.author, recommendation_id=item.pk,
            expected_version=item.content_version,
        )

    def published(self):
        item = self.submitted()
        return recommendation_services.moderate_recommendation(
            actor=self.staff, recommendation_id=item.pk,
            expected_version=item.content_version, approve=True,
        )

    def test_publish_safe_snapshot_does_not_create_rating_or_order_review(self):
        item = self.published()
        self.assertEqual(item.public_body, BODY)
        self.assertTrue(item.public_content_safe)
        self.assertEqual(Rating.objects.count(), 0)
        self.assertFalse(hasattr(item, 'order_id'))
        self.assertEqual(recommendation_services.public_recommendations().get().pk, item.pk)

    def test_confirmation_self_recommendation_and_duplicate_are_rejected(self):
        with self.assertRaises(recommendation_services.QAConflict):
            recommendation_services.create_recommendation(
                actor=self.author, worker_id=self.worker.pk, language='en', body=BODY,
                experience_confirmed=False,
            )
        with self.assertRaises(PermissionDenied):
            recommendation_services.create_recommendation(
                actor=self.worker_user, worker_id=self.worker.pk, language='en',
                body=BODY, experience_confirmed=True,
            )
        self.submitted()
        with self.assertRaises(recommendation_services.QAConflict):
            recommendation_services.create_recommendation(
                actor=self.author, worker_id=self.worker.pk, language='en', body=BODY,
                experience_confirmed=True,
            )


    def test_contacts_html_wrong_city_and_blocked_author_fail_closed(self):
        for body in ('Call +972501234567 for details about this work', '<b>unsafe</b>' + BODY):
            with self.subTest(body=body), self.assertRaises(
                recommendation_services.QAConflict,
            ):
                recommendation_services.create_recommendation(
                    actor=self.author, worker_id=self.worker.pk, language='en', body=body,
                    experience_confirmed=True,
                )
        self.worker.city = make_city(slug='outside-s14-rec')
        self.worker.save(update_fields=['city'])
        with self.assertRaises(PermissionDenied):
            recommendation_services.create_recommendation(
                actor=self.author, worker_id=self.worker.pk, language='en', body=BODY,
                experience_confirmed=True,
            )

    def test_owner_idor_cas_and_append_only_history(self):
        item = recommendation_services.create_recommendation(
            actor=self.author, worker_id=self.worker.pk, language='en', body=BODY,
            experience_confirmed=True,
        )
        with self.assertRaises(PermissionDenied):
            recommendation_services.edit_recommendation(
                actor=self.other, recommendation_id=item.pk,
                expected_version=item.content_version, body=BODY,
                experience_confirmed=True,
            )
        with self.assertRaises(recommendation_services.QAConflict):
            recommendation_services.edit_recommendation(
                actor=self.author, recommendation_id=item.pk, expected_version=0,
                body=BODY, experience_confirmed=True,
            )
        with self.assertRaises(DatabaseError), transaction.atomic():
            PersonalRecommendationRevision.objects.filter(
                recommendation=item,
            ).update(body='forged')

    def test_report_is_unique_and_related_users_cannot_report(self):
        item = self.published()
        report = recommendation_services.report_recommendation(
            actor=self.other, recommendation_id=item.pk, reason='other',
            message='This synthetic recommendation needs moderation.',
        )
        self.assertEqual(report.reporter_id, self.other.pk)
        with self.assertRaises(recommendation_services.QAConflict):
            recommendation_services.report_recommendation(
                actor=self.other, recommendation_id=item.pk, reason='other',
                message='This synthetic recommendation needs moderation.',
            )
        with self.assertRaises(PermissionDenied):
            recommendation_services.report_recommendation(
                actor=self.worker_user, recommendation_id=item.pk, reason='other',
                message='This synthetic recommendation needs moderation.',
            )
        report = recommendation_services.decide_report(
            actor=self.staff, report_id=report.pk, remove=True,
        )
        item.refresh_from_db()
        self.assertEqual(report.status, 'removed')
        self.assertEqual(item.status, 'archived')
        self.assertFalse(item.public_content_safe)

    def test_http_disabled_flag_no_javascript_submit_and_public_warning(self):
        with override_settings(ZEMIPRO_PERSONAL_RECOMMENDATIONS_ENABLED=False):
            self.assertEqual(self.client.get(reverse(
                'knowledge_recommendations:list',
            )).status_code, 404)
        self.client.force_login(self.author)
        response = self.client.post(reverse(
            'knowledge_recommendations:create', args=[self.worker.pk],
        ), {
            'language': 'ru', 'body': BODY, 'experience_confirmed': 'on',
        })
        self.assertEqual(response.status_code, 302)
        item = self.author.personal_recommendations.get()
        self.assertEqual(item.status, 'pending')
        item = recommendation_services.moderate_recommendation(
            actor=self.staff, recommendation_id=item.pk,
            expected_version=item.content_version, approve=True,
        )
        page = self.client.get('/ru/recommendations/')
        self.assertContains(page, item.public_body)
        self.assertContains(page, 'не отзывы по подтверждённым заказам')
        profile = self.client.get(reverse(
            'marketplace:worker_public_profile', args=[self.worker.pk],
        ))
        self.assertContains(profile, item.public_body)
        self.assertContains(profile, 'Личный опыт вне ZemiPro')

    def test_moderation_requires_dedicated_permission(self):
        item = self.submitted()
        with self.assertRaises(PermissionDenied):
            recommendation_services.moderate_recommendation(
                actor=self.other, recommendation_id=item.pk,
                expected_version=item.content_version, approve=True,
            )

    @override_settings(ZEMIPRO_PERSONAL_RECOMMENDATIONS_ENABLED=False)
    def test_feature_flag_hides_reads_and_writes(self):
        self.assertFalse(recommendation_services.public_recommendations().exists())
        with self.assertRaises(PermissionDenied):
            recommendation_services.create_recommendation(
                actor=self.author, worker_id=self.worker.pk, language='en', body=BODY,
                experience_confirmed=True,
            )


@override_settings(ZEMIPRO_PERSONAL_RECOMMENDATIONS_ENABLED=True)
class Stage14RecommendationConcurrencyTests(TransactionTestCase):
    def setUp(self):
        city = make_city(slug='ashdod', name_ru='Synthetic Ashdod')
        category = make_category(slug='s14-reciprocal-recommendation')
        self.user_a = make_user('s14-reciprocal-a')
        self.user_b = make_user('s14-reciprocal-b')
        self.worker_a = make_worker_profile(
            self.user_a, city=city, category=category,
        )
        self.worker_b = make_worker_profile(
            self.user_b, city=city, category=category,
        )

    def test_reciprocal_recommendations_do_not_deadlock_user_rows(self):
        barrier = Barrier(2)
        original = recommendation_services._active_user

        def synchronized_active_user(actor, *, lock=True):
            user = original(actor, lock=lock)
            barrier.wait(timeout=5)
            return user

        def create(actor, worker_id):
            close_old_connections()
            try:
                item = recommendation_services.create_recommendation(
                    actor=actor, worker_id=worker_id, language='en', body=BODY,
                    experience_confirmed=True,
                )
                return item.pk
            finally:
                close_old_connections()

        with patch.object(
            recommendation_services, '_active_user', synchronized_active_user,
        ), ThreadPoolExecutor(max_workers=2) as pool:
            futures = (
                pool.submit(create, self.user_a, self.worker_b.pk),
                pool.submit(create, self.user_b, self.worker_a.pk),
            )
            results = [future.result(timeout=10) for future in futures]
        self.assertEqual(len(set(results)), 2)
