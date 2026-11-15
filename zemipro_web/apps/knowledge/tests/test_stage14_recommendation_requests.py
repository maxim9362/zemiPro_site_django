"""Stage 14.10 request/suggestion isolation, anti-fraud and moderation."""
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied
from django.db import DatabaseError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.knowledge import request_services
from apps.knowledge.models import (
    RecommendationRequestRevision, RecommendationResponseRevision,
)
from apps.marketplace.models import Order, Rating
from apps.marketplace.tests.factories import (
    make_category, make_city, make_user, make_worker_profile,
)


TITLE = 'Who can recommend a careful synthetic repair specialist?'
BODY = 'I am looking for community experience with a careful specialist in Ashdod.'
RESPONSE = 'I had a positive external experience and suggest reviewing this public profile.'


@override_settings(ZEMIPRO_RECOMMENDATION_REQUESTS_ENABLED=True)
class Stage14RecommendationRequestTests(TestCase):
    def setUp(self):
        self.city = make_city(slug='ashdod', name_ru='Synthetic Ashdod')
        self.category = make_category(slug='s14-request-category')
        self.other_category = make_category(slug='s14-request-other')
        self.author = make_user('s14-request-author')
        self.recommender = make_user('s14-request-recommender')
        self.other = make_user('s14-request-other')
        self.worker_user = make_user('s14-request-worker')
        self.worker = make_worker_profile(
            self.worker_user, city=self.city, category=self.category,
        )
        self.other_worker_user = make_user('s14-request-worker2')
        self.other_worker = make_worker_profile(
            self.other_worker_user, city=self.city, category=self.other_category,
        )
        self.staff = make_user('s14-request-staff', is_staff=True)
        self.staff.user_permissions.add(Permission.objects.get(
            codename='moderate_recommendation_requests',
        ))

    def published_request(self, language='en'):
        item = request_services.create_request(
            actor=self.author, category_id=self.category.pk, language=language,
            title=TITLE, body=BODY,
        )
        return request_services.moderate_request(
            actor=self.staff, request_id=item.pk,
            expected_version=item.content_version, approve=True,
        )

    def published_response(self):
        item = self.published_request()
        response = request_services.create_response(
            actor=self.recommender, request_id=item.pk, worker_id=self.worker.pk,
            body=RESPONSE,
        )
        response = request_services.moderate_response(
            actor=self.staff, response_id=response.pk,
            expected_version=response.content_version, approve=True,
        )
        return item, response

    def test_separate_domain_never_creates_order_rating_or_question(self):
        item, response = self.published_response()
        self.assertEqual(Order.objects.count(), 0)
        self.assertEqual(Rating.objects.count(), 0)
        self.assertFalse(hasattr(item, 'order_id'))
        self.assertFalse(hasattr(response, 'rating_id'))
        self.assertEqual(request_services.public_requests().get().pk, item.pk)
        self.assertEqual(request_services.public_responses(item).get().pk, response.pk)

    def test_self_promotion_requester_response_and_wrong_category_are_denied(self):
        item = self.published_request()
        with self.assertRaises(PermissionDenied):
            request_services.create_response(
                actor=self.worker_user, request_id=item.pk, worker_id=self.worker.pk,
                body=RESPONSE,
            )
        with self.assertRaises(PermissionDenied):
            request_services.create_response(
                actor=self.author, request_id=item.pk, worker_id=self.worker.pk,
                body=RESPONSE,
            )
        with self.assertRaises(PermissionDenied):
            request_services.create_response(
                actor=self.recommender, request_id=item.pk,
                worker_id=self.other_worker.pk, body=RESPONSE,
            )

    def test_duplicate_recommender_and_duplicate_worker_are_blocked(self):
        item = self.published_request()
        request_services.create_response(
            actor=self.recommender, request_id=item.pk, worker_id=self.worker.pk,
            body=RESPONSE,
        )
        with self.assertRaises(request_services.QAConflict):
            request_services.create_response(
                actor=self.recommender, request_id=item.pk, worker_id=self.worker.pk,
                body=RESPONSE,
            )
        with self.assertRaises(request_services.QAConflict):
            request_services.create_response(
                actor=self.other, request_id=item.pk, worker_id=self.worker.pk,
                body=RESPONSE,
            )

    def test_private_contacts_html_and_blocked_accounts_fail(self):
        for body in ('Call +972501234567 about this request', '<script>x</script> safe text'):
            with self.subTest(body=body), self.assertRaises(request_services.QAConflict):
                request_services.create_request(
                    actor=self.author, category_id=self.category.pk, language='en',
                    title=TITLE, body=body,
                )
        self.author.is_blocked = True
        self.author.save(update_fields=['is_blocked'])
        with self.assertRaises(PermissionDenied):
            request_services.create_request(
                actor=self.author, category_id=self.category.pk, language='en',
                title=TITLE, body=BODY,
            )

    def test_revisions_are_append_only(self):
        item, response = self.published_response()
        with self.assertRaises(DatabaseError), transaction.atomic():
            RecommendationRequestRevision.objects.filter(request=item).delete()
        with self.assertRaises(DatabaseError), transaction.atomic():
            RecommendationResponseRevision.objects.filter(response=response).update(
                body='forged',
            )

    def test_reports_are_unique_and_removal_hides_content(self):
        item, _ = self.published_response()
        report = request_services.report_content(
            actor=self.other, request_id=item.pk, reason='other',
            message='This request requires a synthetic moderation review.',
        )
        with self.assertRaises(request_services.QAConflict):
            request_services.report_content(
                actor=self.other, request_id=item.pk, reason='other',
                message='This request requires a synthetic moderation review.',
            )
        request_services.decide_report(actor=self.staff, report_id=report.pk, remove=True)
        item.refresh_from_db()
        self.assertEqual(item.status, 'archived')
        self.assertFalse(item.public_content_safe)

    def test_report_http_queue_and_decision_cover_request_and_response(self):
        item, response = self.published_response()
        self.client.force_login(self.other)
        request_report = self.client.post(reverse(
            'knowledge_requests:report_request', args=[item.slug],
        ), {'reason': 'other', 'message': 'Synthetic request report for moderation.'})
        self.assertEqual(request_report.status_code, 302)
        self.client.force_login(self.author)
        response_report = self.client.post(reverse(
            'knowledge_requests:report_response', args=[item.slug, response.pk],
        ), {'reason': 'other', 'message': 'Synthetic response report for moderation.'})
        self.assertEqual(response_report.status_code, 302)
        reports = list(item.reports.order_by('pk'))
        self.assertEqual(len(reports), 1)
        second = response.reports.get()
        self.client.force_login(self.staff)
        queue = self.client.get(reverse('knowledge:request_moderation'))
        self.assertContains(queue, 'Synthetic request report')
        self.assertContains(queue, 'Synthetic response report')
        self.assertEqual(self.client.post(reverse(
            'knowledge:request_report_moderate', args=[second.pk],
        ), {'action': 'dismiss'}).status_code, 302)
        self.assertEqual(self.client.post(reverse(
            'knowledge:request_report_moderate', args=[reports[0].pk],
        ), {'action': 'remove'}).status_code, 302)
        item.refresh_from_db()
        self.assertEqual(item.status, 'archived')

    def test_no_javascript_http_flow_and_three_locales(self):
        self.client.force_login(self.author)
        response = self.client.post(reverse('knowledge_requests:create'), {
            'title': TITLE, 'body': BODY, 'category': self.category.pk, 'language': 'ru',
        })
        self.assertEqual(response.status_code, 302)
        item = self.author.recommendation_requests.get()
        self.assertEqual(item.status, 'pending')
        for path, marker in (
            ('/ru/recommend-master/', 'Посоветуйте мастера'),
            ('/en/recommend-master/', 'Recommend a specialist'),
            ('/he/recommend-master/', 'המליצו על בעל מקצוע'),
        ):
            page = self.client.get(path)
            self.assertEqual(page.status_code, 200)
            self.assertContains(page, marker)

    @override_settings(ZEMIPRO_RECOMMENDATION_REQUESTS_ENABLED=False)
    def test_flag_fails_closed_for_reads_and_writes(self):
        self.assertFalse(request_services.public_requests().exists())
        self.assertEqual(self.client.get(reverse('knowledge_requests:list')).status_code, 404)
        with self.assertRaises(PermissionDenied):
            request_services.create_request(
                actor=self.author, category_id=self.category.pk, language='en',
                title=TITLE, body=BODY,
            )
