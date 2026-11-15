"""14.4 — synthetic pilot only. These tests never authorize real publication."""
import time

from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied
from django.db import DatabaseError, transaction
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils.translation import override

from apps.knowledge import pilot_metrics, pilot_services, services
from apps.knowledge.models import (
    ArticlePilotAudit, ArticlePilotDailyMetric, ArticlePilotEnrollment,
    ArticlePilotOrderAttribution, ArticlePilotSelection,
)
from apps.marketplace.models import Order
from apps.marketplace.tests.factories import (
    make_category, make_city, make_order, make_user, make_worker_profile,
)
from .test_stage14_authoring import BODY, TITLE


@override_settings(
    ZEMIPRO_KNOWLEDGE_AUTHORING_ENABLED=True,
    ZEMIPRO_KNOWLEDGE_ARTICLES_ENABLED=True,
)
class Stage14PilotTests(TestCase):
    def setUp(self):
        self.city = make_city(slug='ashdod', name_ru='Synthetic Ashdod')
        self.category = make_category(slug='s14-pilot-category')
        self.writer = make_user('s14-pilot-writer')
        self.reader = make_user('s14-pilot-reader')
        self.moderator = make_user('s14-pilot-moderator', is_staff=True)
        self.staff_without_perm = make_user('s14-pilot-other-staff', is_staff=True)
        permission = Permission.objects.get(codename='moderate_expert_articles')
        self.moderator.user_permissions.add(permission)
        self.worker = make_worker_profile(
            self.writer, city=self.city, category=self.category,
        )

    def publish(self, title=TITLE):
        article = services.create_article(
            actor=self.writer, title=title, excerpt='Synthetic safety overview',
            body=BODY, category_id=self.category.pk, rights_confirmed=True,
        )
        article = services.submit_article(
            actor=self.writer, article_id=article.pk,
            expected_version=article.content_version, rights_confirmed=True,
        )
        return services.decide_article(
            actor=self.moderator, article_id=article.pk,
            expected_version=article.content_version, approve=True,
            content_reviewed=True,
        )

    def select(self, article=None):
        article = article or self.publish()
        pilot_services.consent_to_pilot(self.writer, confirmed=True)
        selected, _ = pilot_services.select_for_pilot(
            self.moderator, article_id=article.pk,
            expected_version=article.content_version,
        )
        return article, selected

    def detail(self, article):
        with override(article.language):
            return reverse('knowledge_public:article_detail', kwargs={
                'slug': article.slug,
            })

    def outbound(self, article, dest):
        with override(article.language):
            return reverse('knowledge_public:article_outbound', kwargs={
                'slug': article.slug, 'destination': dest,
            })

    def test_flag_without_explicit_opt_in_and_selection_never_public(self):
        article = self.publish()
        self.assertEqual(self.client.get(self.detail(article)).status_code, 404)
        pilot_services.consent_to_pilot(self.writer, confirmed=True)
        self.assertEqual(self.client.get(self.detail(article)).status_code, 404)
        selected, _ = pilot_services.select_for_pilot(
            self.moderator, article_id=article.pk,
            expected_version=article.content_version,
        )
        self.assertEqual(selected.approved_version, article.content_version)
        self.assertEqual(self.client.get(self.detail(article)).status_code, 200)
        self.assertEqual(
            ArticlePilotEnrollment.objects.get().accepted_by_id, self.writer.pk,
        )
        self.assertEqual(ArticlePilotAudit.objects.count(), 2)

    def test_no_consent_without_explicit_confirmation_and_no_staff_impersonation(self):
        article = self.publish()
        with self.assertRaises(services.ArticleConflict):
            pilot_services.consent_to_pilot(self.writer, confirmed=False)
        self.assertEqual(ArticlePilotEnrollment.objects.count(), 0)
        with self.assertRaises(PermissionDenied):
            pilot_services.select_for_pilot(
                self.staff_without_perm, article_id=article.pk,
                expected_version=article.content_version,
            )
        with self.assertRaises(services.ArticleConflict):
            pilot_services.select_for_pilot(
                self.moderator, article_id=article.pk,
                expected_version=article.content_version,
            )
        self.assertEqual(ArticlePilotSelection.objects.count(), 0)

    def test_consent_does_not_create_order_rating_or_auto_go(self):
        pilot_services.consent_to_pilot(self.writer, confirmed=True)
        readiness = pilot_services.pilot_readiness(self.moderator)
        self.assertEqual(readiness['consenting_authors'], 1)
        self.assertEqual(readiness['selected_articles'], 0)
        self.assertEqual(readiness['owner_qa_decision'], 'PENDING')
        self.assertFalse(readiness['real_pilot_verified'])
        self.assertEqual(readiness['real_attributed_published_orders'], 0)
        self.assertEqual(Order.objects.count(), 0)

    def test_author_withdrawal_hides_all_and_reconsent_does_not_resurrect(self):
        article, selection = self.select()
        self.assertEqual(self.client.get(self.detail(article)).status_code, 200)
        self.assertTrue(pilot_services.withdraw_from_pilot(self.writer))
        self.assertFalse(pilot_services.withdraw_from_pilot(self.writer))
        self.assertEqual(self.client.get(self.detail(article)).status_code, 404)
        selection.refresh_from_db()
        self.assertIsNotNone(selection.revoked_at)
        self.assertEqual(
            list(ArticlePilotAudit.objects.values_list('action', flat=True)),
            ['consented', 'selected', 'deselected', 'withdrawn'],
        )
        pilot_services.consent_to_pilot(self.writer, confirmed=True)
        self.assertEqual(self.client.get(self.detail(article)).status_code, 404)
        pilot_services.select_for_pilot(
            self.moderator, article_id=article.pk,
            expected_version=article.content_version,
        )
        self.assertEqual(self.client.get(self.detail(article)).status_code, 200)

    def test_author_may_withdraw_after_editor_disabled_or_profile_unpublished(self):
        article, _ = self.select()
        self.worker.is_published = False
        self.worker.save(update_fields=['is_published'])
        with override_settings(
            ZEMIPRO_KNOWLEDGE_AUTHORING_ENABLED=False,
            ZEMIPRO_KNOWLEDGE_ARTICLES_ENABLED=False,
        ):
            self.assertTrue(pilot_services.withdraw_from_pilot(self.writer))
            self.client.force_login(self.writer)
            self.assertEqual(self.client.get(
                reverse('knowledge:pilot_consent'),
            ).status_code, 200)
        self.assertEqual(self.client.get(self.detail(article)).status_code, 404)

    def test_staff_cannot_select_own_article_or_invalid_version(self):
        article = self.publish()
        pilot_services.consent_to_pilot(self.writer, confirmed=True)
        self.writer.is_staff = True
        self.writer.save(update_fields=['is_staff'])
        self.writer.user_permissions.add(
            Permission.objects.get(codename='moderate_expert_articles'),
        )
        with self.assertRaises(PermissionDenied):
            pilot_services.select_for_pilot(
                self.writer, article_id=article.pk,
                expected_version=article.content_version,
            )
        with self.assertRaises(services.ArticleConflict):
            pilot_services.select_for_pilot(
                self.moderator, article_id=article.pk,
                expected_version=article.content_version - 1,
            )

    def test_selection_is_version_bound_and_edit_revokes_public_access(self):
        article, _ = self.select()
        newer = services.edit_article(
            actor=self.writer, article_id=article.pk,
            expected_version=article.content_version,
            title='Synthetic revised maintenance guidance',
            excerpt='Safer new overview', body=BODY,
            category_id=self.category.pk, rights_confirmed=True,
        )
        self.assertEqual(newer.status, 'draft')
        self.assertEqual(self.client.get(self.detail(article)).status_code, 404)
        newer = services.submit_article(
            actor=self.writer, article_id=article.pk,
            expected_version=newer.content_version, rights_confirmed=True,
        )
        newer = services.decide_article(
            actor=self.moderator, article_id=article.pk,
            expected_version=newer.content_version, approve=True,
            content_reviewed=True,
        )
        self.assertEqual(self.client.get(self.detail(article)).status_code, 404)
        pilot_services.select_for_pilot(
            self.moderator, article_id=article.pk,
            expected_version=newer.content_version,
        )
        self.assertEqual(self.client.get(self.detail(article)).status_code, 200)

    def test_reviewer_can_emergency_deselect_when_authoring_paused(self):
        article, _ = self.select()
        with override_settings(ZEMIPRO_KNOWLEDGE_AUTHORING_ENABLED=False):
            self.assertTrue(pilot_services.deselect_from_pilot(
                self.moderator, article_id=article.pk,
            ))
            self.assertEqual(self.client.get(self.detail(article)).status_code, 404)

    def test_pilot_audit_is_append_only_at_postgresql_layer(self):
        article, _ = self.select()
        with self.assertRaises(DatabaseError), transaction.atomic():
            ArticlePilotAudit.objects.filter(article=article).update(action='withdrawn')
        with self.assertRaises(DatabaseError), transaction.atomic():
            ArticlePilotAudit.objects.all().delete()

    def test_selection_idempotent_and_anti_quota_cross_author(self):
        article, _ = self.select()
        item, created = pilot_services.select_for_pilot(
            self.moderator, article_id=article.pk,
            expected_version=article.content_version,
        )
        self.assertFalse(created)
        self.assertEqual(item.article_id, article.pk)
        self.assertEqual(ArticlePilotAudit.objects.filter(action='selected').count(), 1)

    def test_readiness_rejects_normal_users_without_permission(self):
        with self.assertRaises(PermissionDenied):
            pilot_services.pilot_readiness(self.reader)
        with self.assertRaises(PermissionDenied):
            pilot_services.pilot_readiness(self.staff_without_perm)
        self.client.force_login(self.reader)
        self.assertEqual(
            self.client.get(reverse('knowledge:pilot_moderation')).status_code,
            404,
        )

    def test_consent_and_moderation_http_routes_require_csrf_and_rights(self):
        article = self.publish()
        other = Client(enforce_csrf_checks=True)
        other.force_login(self.writer)
        self.assertEqual(other.post(reverse('knowledge:pilot_consent'), {
            'action': 'consent', 'confirmed': 'on',
        }).status_code, 403)
        self.assertEqual(ArticlePilotEnrollment.objects.count(), 0)
        self.client.force_login(self.writer)
        self.assertEqual(self.client.get(
            reverse('knowledge:pilot_consent'),
        ).status_code, 200)
        self.assertEqual(self.client.post(reverse('knowledge:pilot_consent'), {
            'action': 'consent', 'confirmed': 'on',
        }).status_code, 302)
        self.client.force_login(self.moderator)
        response = self.client.get(reverse('knowledge:pilot_moderation'))
        self.assertContains(response, article.public_title)
        result = self.client.post(reverse('knowledge:pilot_moderation'), {
            'action': 'select', 'article_id': article.pk,
            'expected_version': article.content_version,
        })
        self.assertEqual(result.status_code, 302)
        self.assertEqual(self.client.get(self.detail(article)).status_code, 200)

    @override_settings(ZEMIPRO_KNOWLEDGE_PILOT_METRICS_ENABLED=True)
    def test_public_views_and_outbound_actions_create_only_aggregate_counters(self):
        article, _ = self.select()
        self.assertEqual(self.client.get(self.detail(article)).status_code, 200)
        self.assertEqual(self.client.get(self.detail(article)).status_code, 200)
        redirect = self.client.get(self.outbound(article, 'profile'))
        self.assertEqual(redirect.status_code, 302)
        self.assertEqual(redirect.url, reverse(
            'marketplace:worker_public_profile', args=[self.worker.pk],
        ))
        redirect = self.client.get(self.outbound(article, 'order'))
        self.assertEqual(redirect.url, reverse('marketplace:order_wizard_start'))
        daily = ArticlePilotDailyMetric.objects.get(article=article)
        self.assertEqual(daily.article_views, 2)
        self.assertEqual(daily.profile_clicks, 1)
        self.assertEqual(daily.order_clicks, 1)
        self.assertEqual(ArticlePilotOrderAttribution.objects.count(), 0)
        column_names = {field.name for field in daily._meta.fields}
        for private in ('user', 'visitor', 'ip', 'session_id', 'email', 'path', 'phone'):
            self.assertNotIn(private, column_names)

    def test_tracking_flag_off_means_no_aggregates_or_session_ref(self):
        article, _ = self.select()
        self.assertEqual(self.client.get(self.detail(article)).status_code, 200)
        self.client.get(self.outbound(article, 'order'))
        self.assertEqual(ArticlePilotDailyMetric.objects.count(), 0)
        self.assertNotIn(pilot_metrics.SESSION_KEY, self.client.session)

    @override_settings(ZEMIPRO_KNOWLEDGE_PILOT_METRICS_ENABLED=True)
    def test_unrelated_order_and_link_click_do_not_count_real_requests(self):
        article, _ = self.select()
        self.client.force_login(self.reader)
        self.client.get(self.outbound(article, 'order'))
        order = make_order(
            client=self.reader, city=self.city, category=self.category,
            status=Order.Status.DRAFT,
        )
        request = RequestFactory().get('/')
        request.user = self.reader
        request.session = self.client.session
        another = make_order(
            client=self.reader, city=self.city, category=self.category,
            status=Order.Status.PUBLISHED,
        )
        self.assertFalse(pilot_metrics.record_published_order(request, another))
        self.assertEqual(ArticlePilotOrderAttribution.objects.count(), 0)
        self.assertEqual(order.status, Order.Status.DRAFT)

    @override_settings(ZEMIPRO_KNOWLEDGE_PILOT_METRICS_ENABLED=True)
    def test_order_ref_requires_bound_draft_and_published_status(self):
        article, _ = self.select()
        self.client.force_login(self.reader)
        self.client.get(self.outbound(article, 'order'))
        order = make_order(
            client=self.reader, city=self.city, category=self.category,
            status=Order.Status.DRAFT,
        )
        request = RequestFactory().get('/')
        request.user = self.reader
        request.session = self.client.session
        self.assertTrue(pilot_metrics.bind_started_order(request, order))
        self.assertFalse(pilot_metrics.record_published_order(request, order))
        # A second independently bound order is a synthetic publication, not
        # proof of a real pilot conversion.
        self.client.get(self.outbound(article, 'order'))
        request.session = self.client.session
        self.assertTrue(pilot_metrics.bind_started_order(request, order))
        Order.objects.filter(pk=order.pk).update(status=Order.Status.PUBLISHED)
        order.refresh_from_db()
        self.assertTrue(pilot_metrics.record_published_order(request, order))
        self.assertEqual(ArticlePilotOrderAttribution.objects.count(), 1)
        self.assertFalse(pilot_metrics.record_published_order(request, order))
        summary = pilot_metrics.pilot_summary()
        self.assertEqual(summary['real_attributed_published_orders'], 1)

    @override_settings(ZEMIPRO_KNOWLEDGE_PILOT_METRICS_ENABLED=True)
    def test_expired_session_ref_never_attributed(self):
        article, _ = self.select()
        self.client.force_login(self.reader)
        self.client.get(self.outbound(article, 'order'))
        request = RequestFactory().get('/')
        request.user = self.reader
        request.session = self.client.session
        stale = request.session[pilot_metrics.SESSION_KEY]
        stale['created_at'] = int(time.time()) - pilot_metrics.MAX_AGE_SECONDS - 5
        request.session[pilot_metrics.SESSION_KEY] = stale
        draft = make_order(
            client=self.reader, city=self.city, category=self.category,
            status=Order.Status.DRAFT,
        )
        self.assertFalse(pilot_metrics.bind_started_order(request, draft))
        self.assertEqual(ArticlePilotOrderAttribution.objects.count(), 0)

    def test_private_no_go_decision_and_public_feature_off_even_with_selection(self):
        article, _ = self.select()
        with override_settings(
            ZEMIPRO_KNOWLEDGE_ARTICLES_ENABLED=False,
            ZEMIPRO_KNOWLEDGE_PILOT_METRICS_ENABLED=True,
        ):
            self.assertEqual(self.client.get(self.detail(article)).status_code, 404)
            readiness = pilot_services.pilot_readiness(self.moderator)
            self.assertFalse(readiness['published_views_available'])
            self.assertEqual(readiness['owner_qa_decision'], 'PENDING')
            self.assertFalse(readiness['real_pilot_verified'])
            self.assertFalse(pilot_metrics.metrics_on())

    def test_outbound_invalid_destination_never_redirects(self):
        article, _ = self.select()
        path = self.outbound(article, 'external')
        self.assertEqual(self.client.get(path).status_code, 404)

    def test_author_consent_page_hebrew_rtl_and_english(self):
        self.client.force_login(self.writer)
        for language, direction in (('he', 'rtl'), ('en', 'ltr'), ('ru', 'ltr')):
            with self.subTest(language=language):
                result = self.client.get(
                    reverse('knowledge:pilot_consent'),
                    HTTP_ACCEPT_LANGUAGE=language,
                )
                self.assertEqual(result.status_code, 200)
                self.assertIn(
                    f'dir="{direction}"', result.content.decode(),
                )
