"""Stage 14.6 HTTP, localization, no-JS and privacy checks."""
from django.contrib.auth.models import Permission
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.knowledge import qa_services
from apps.marketplace.tests.factories import (
    make_category, make_city, make_user, make_worker_profile,
)


@override_settings(
    ZEMIPRO_KNOWLEDGE_QA_ENABLED=True,
    ZEMIPRO_KNOWLEDGE_ROLLOUT_METRICS_ENABLED=True,
)
class Stage14QAInterfaceTests(TestCase):
    def setUp(self):
        self.city = make_city(slug='ashdod', name_ru='Synthetic Ashdod')
        self.category = make_category(slug='s14-ui-qa')
        self.asker = make_user('s14-ui-asker')
        self.expert_user = make_user('s14-ui-expert')
        self.expert = make_worker_profile(
            self.expert_user, city=self.city, category=self.category,
        )
        self.staff = make_user('s14-ui-staff', is_staff=True)
        self.staff.user_permissions.add(
            Permission.objects.get(codename='moderate_expert_questions'),
        )

    def publish(self, *, language='ru'):
        question = qa_services.create_question(
            actor=self.asker, category_id=self.category.pk, language=language,
            title='Synthetic safety question for a qualified specialist',
            body='Which safe synthetic maintenance sequence should a resident follow?',
        )
        question = qa_services.submit_question(
            actor=self.asker, question_id=question.pk,
            expected_version=question.content_version,
        )
        return qa_services.moderate_question(
            actor=self.staff, question_id=question.pk,
            expected_version=question.content_version, approve=True,
        )

    def test_disabled_flag_returns_404_without_leaking_records(self):
        question = self.publish()
        with override_settings(ZEMIPRO_KNOWLEDGE_QA_ENABLED=False):
            self.assertEqual(self.client.get(reverse('knowledge_qa:list')).status_code, 404)
            self.assertEqual(self.client.get(reverse(
                'knowledge_qa:detail', args=[question.slug],
            )).status_code, 404)

    def test_list_search_detail_noindex_and_safe_snapshot_only(self):
        question = self.publish()
        type(question).objects.filter(pk=question.pk).update(
            title='PRIVATE SOURCE MUST NOT LEAK', body='PRIVATE BODY MUST NOT LEAK',
        )
        page = self.client.get(reverse('knowledge_qa:list'), {'q': 'safety'})
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, question.public_title)
        self.assertNotContains(page, 'PRIVATE SOURCE')
        self.assertContains(page, 'noindex,follow')
        detail = self.client.get(reverse('knowledge_qa:detail', args=[question.slug]))
        self.assertContains(detail, question.public_body)
        self.assertNotContains(detail, 'PRIVATE BODY')

    def test_ru_en_he_routes_and_hebrew_rtl(self):
        for language in ('ru', 'en', 'he'):
            self.publish(language=language)
        for prefix, marker in (
            ('/ru/questions/', 'Вопросы и ответы'),
            ('/en/questions/', 'Questions and answers'),
            ('/he/questions/', 'שאלות ותשובות'),
        ):
            response = self.client.get(prefix)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, marker)
        self.assertContains(self.client.get('/he/questions/'), '<html lang="he" dir="rtl">')

    def test_authenticated_no_javascript_create_submits_for_moderation(self):
        self.client.force_login(self.asker)
        response = self.client.post(reverse('knowledge_qa:create'), {
            'title': 'A complete synthetic question title',
            'body': 'A complete synthetic question body for safe manual review.',
            'category': self.category.pk, 'language': 'en',
        })
        self.assertEqual(response.status_code, 302)
        question = self.asker.expert_questions.get()
        self.assertEqual(question.status, 'pending')
        self.assertEqual(question.revisions.count(), 2)

    def test_answer_endpoint_rejects_non_worker_and_accepts_eligible_worker(self):
        question = self.publish()
        self.client.force_login(self.asker)
        response = self.client.post(reverse('knowledge_qa:answer', args=[question.slug]), {
            'body': 'A complete synthetic answer long enough for moderation.',
        })
        self.assertEqual(response.status_code, 403)
        self.client.force_login(self.expert_user)
        response = self.client.post(reverse('knowledge_qa:answer', args=[question.slug]), {
            'body': 'A complete synthetic answer long enough for moderation.',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(question.answers.get().status, 'pending')

    def test_moderation_queue_requires_permission_and_post_csrf(self):
        self.publish()
        self.client.force_login(self.asker)
        self.assertEqual(self.client.get(reverse('knowledge:qa_moderation')).status_code, 403)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse('knowledge:qa_moderation')).status_code, 200)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.staff)
        self.assertEqual(csrf_client.post(reverse(
            'knowledge:qa_moderate_question', args=[999],
        ), {'expected_version': 1, 'action': 'approve'}).status_code, 403)

    def test_contact_shaped_search_is_not_reflected(self):
        response = self.client.get(reverse('knowledge_qa:list'), {'q': '+972501234567'})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, '+972501234567')
        self.assertContains(response, 'Проверьте поисковый запрос')

    def test_detail_and_whitelisted_outbound_routes_record_only_aggregates(self):
        from apps.knowledge.models import KnowledgeDailyMetric

        question = self.publish()
        detail = self.client.get(reverse('knowledge_qa:detail', args=[question.slug]))
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(KnowledgeDailyMetric.objects.get(
            source='question', event='question_view',
        ).total, 1)
        outbound = self.client.get(reverse(
            'knowledge_qa:outbound', kwargs={
                'slug': question.slug, 'destination': 'order',
            },
        ))
        self.assertRedirects(
            outbound, reverse('marketplace:order_wizard_start'),
            fetch_redirect_response=False,
        )
        self.assertEqual(KnowledgeDailyMetric.objects.get(
            source='question', event='order_started',
        ).total, 1)
        self.assertEqual(self.client.get(reverse(
            'knowledge_qa:outbound', kwargs={
                'slug': question.slug, 'destination': 'external',
            },
        )).status_code, 404)
