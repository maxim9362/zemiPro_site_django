"""Stage 14.5 Q&A domain, PostgreSQL integrity and authorization checks."""
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied
from django.db import DatabaseError, IntegrityError, transaction
from django.test import TestCase, override_settings

from apps.knowledge import qa_services
from apps.knowledge.models import (
    ExpertAnswerRevision, ExpertQuestionRevision,
    HelpfulVote, KnowledgeQAReport,
)
from apps.marketplace.tests.factories import (
    make_category, make_city, make_user, make_worker_profile,
)


TITLE = 'How should synthetic equipment be inspected safely?'
QUESTION = 'What sequence should be followed before routine synthetic maintenance begins?'
ANSWER = (
    'Disconnect the equipment, read the manufacturer instructions and use '
    'the correct protective equipment before inspecting any component.'
)


@override_settings(ZEMIPRO_KNOWLEDGE_QA_ENABLED=True)
class Stage14QADomainTests(TestCase):
    def setUp(self):
        self.city = make_city(slug='ashdod', name_ru='Synthetic Ashdod')
        self.category = make_category(slug='s14-qa-category')
        self.asker = make_user('s14-qa-asker')
        self.other = make_user('s14-qa-other')
        self.expert_user = make_user('s14-qa-expert')
        self.expert = make_worker_profile(
            self.expert_user, city=self.city, category=self.category,
        )
        self.staff = make_user('s14-qa-moderator', is_staff=True)
        self.staff.user_permissions.add(
            Permission.objects.get(codename='moderate_expert_questions'),
        )

    def published_question(self):
        question = qa_services.create_question(
            actor=self.asker, category_id=self.category.pk, language='ru',
            title=TITLE, body=QUESTION,
        )
        question = qa_services.submit_question(
            actor=self.asker, question_id=question.pk,
            expected_version=question.content_version,
        )
        return qa_services.moderate_question(
            actor=self.staff, question_id=question.pk,
            expected_version=question.content_version, approve=True,
        )

    def published_answer(self):
        question = self.published_question()
        answer = qa_services.create_answer(
            actor=self.expert_user, question_id=question.pk, body=ANSWER,
        )
        answer = qa_services.submit_answer(
            actor=self.expert_user, answer_id=answer.pk,
            expected_version=answer.content_version,
        )
        answer = qa_services.moderate_answer(
            actor=self.staff, answer_id=answer.pk,
            expected_version=answer.content_version, approve=True,
        )
        return question, answer

    def test_question_and_answer_use_moderated_public_snapshots(self):
        question, answer = self.published_answer()
        self.assertEqual(question.public_title, TITLE)
        self.assertEqual(answer.public_body, ANSWER)
        self.assertEqual(question.content_version, 3)
        self.assertEqual(answer.content_version, 3)
        self.assertEqual(qa_services.public_questions().get().pk, question.pk)
        self.assertEqual(qa_services.public_answers(question).get().pk, answer.pk)
        self.assertFalse(hasattr(question, 'order_id'))
        self.assertFalse(hasattr(answer, 'rating_id'))

    def test_idor_and_live_account_state_are_enforced(self):
        question = qa_services.create_question(
            actor=self.asker, category_id=self.category.pk, language='en',
            title=TITLE, body=QUESTION,
        )
        with self.assertRaises(PermissionDenied):
            qa_services.edit_question(
                actor=self.other, question_id=question.pk,
                expected_version=question.content_version, title=TITLE,
                body=QUESTION, category_id=self.category.pk,
            )
        self.asker.is_blocked = True
        self.asker.save(update_fields=['is_blocked'])
        with self.assertRaises(PermissionDenied):
            qa_services.submit_question(
                actor=self.asker, question_id=question.pk,
                expected_version=question.content_version,
            )

    def test_contacts_html_and_stale_versions_fail_without_partial_history(self):
        for value in ('Call +972501234567 now please', '<script>alert(1)</script>'):
            with self.subTest(value=value), self.assertRaises(qa_services.QAConflict):
                qa_services.create_question(
                    actor=self.asker, category_id=self.category.pk, language='ru',
                    title=TITLE, body=value,
                )
        question = qa_services.create_question(
            actor=self.asker, category_id=self.category.pk, language='ru',
            title=TITLE, body=QUESTION,
        )
        with self.assertRaises(qa_services.QAConflict):
            qa_services.edit_question(
                actor=self.asker, question_id=question.pk, expected_version=0,
                title=TITLE, body=QUESTION, category_id=self.category.pk,
            )
        self.assertEqual(question.revisions.count(), 1)

    def test_only_published_ashdod_worker_can_answer(self):
        question = self.published_question()
        with self.assertRaises(PermissionDenied):
            qa_services.create_answer(
                actor=self.other, question_id=question.pk, body=ANSWER,
            )
        self.expert.city = make_city(slug='s14-outside-city')
        self.expert.save(update_fields=['city'])
        with self.assertRaises(PermissionDenied):
            qa_services.create_answer(
                actor=self.expert_user, question_id=question.pk, body=ANSWER,
            )

    def test_one_answer_per_worker_and_one_accepted_answer(self):
        question, answer = self.published_answer()
        with self.assertRaises(qa_services.QAConflict):
            qa_services.create_answer(
                actor=self.expert_user, question_id=question.pk, body=ANSWER,
            )
        accepted = qa_services.accept_answer(
            actor=self.asker, question_id=question.pk, answer_id=answer.pk,
        )
        self.assertTrue(accepted.is_accepted)
        self.assertTrue(qa_services.accept_answer(
            actor=self.asker, question_id=question.pk, answer_id=answer.pk,
        ).is_accepted)
        with self.assertRaises(PermissionDenied):
            qa_services.accept_answer(
                actor=self.other, question_id=question.pk, answer_id=answer.pk,
            )

    def test_hidden_worker_answer_cannot_be_accepted(self):
        question, answer = self.published_answer()
        self.expert_user.is_blocked = True
        self.expert_user.save(update_fields=['is_blocked'])
        with self.assertRaises(PermissionDenied):
            qa_services.accept_answer(
                actor=self.asker, question_id=question.pk, answer_id=answer.pk,
            )
        answer.refresh_from_db()
        self.assertFalse(answer.is_accepted)

    def test_helpful_vote_is_idempotent_and_self_vote_is_denied(self):
        _, answer = self.published_answer()
        qa_services.set_helpful(actor=self.other, answer_id=answer.pk, helpful=True)
        qa_services.set_helpful(actor=self.other, answer_id=answer.pk, helpful=True)
        self.assertEqual(HelpfulVote.objects.count(), 1)
        qa_services.set_helpful(actor=self.other, answer_id=answer.pk, helpful=False)
        self.assertEqual(HelpfulVote.objects.count(), 0)
        with self.assertRaises(PermissionDenied):
            qa_services.set_helpful(
                actor=self.expert_user, answer_id=answer.pk, helpful=True,
            )

    def test_helpful_vote_rejects_mismatched_or_hidden_parent_question(self):
        question, answer = self.published_answer()
        other_question = self.published_question()
        with self.assertRaises(PermissionDenied):
            qa_services.set_helpful(
                actor=self.other, answer_id=answer.pk, helpful=True,
                question_id=other_question.pk,
            )
        question.status = 'archived'
        question.save(update_fields=['status', 'updated_at'])
        with self.assertRaises(PermissionDenied):
            qa_services.set_helpful(
                actor=self.other, answer_id=answer.pk, helpful=True,
                question_id=question.pk,
            )
        self.assertFalse(HelpfulVote.objects.exists())

    def test_reports_are_unique_and_moderation_removal_is_atomic(self):
        question, _ = self.published_answer()
        report = qa_services.report_content(
            actor=self.other, question_id=question.pk,
            reason='dangerous', message='This synthetic advice needs review.',
        )
        with self.assertRaises(qa_services.QAConflict):
            qa_services.report_content(
                actor=self.other, question_id=question.pk,
                reason='dangerous', message='This synthetic advice needs review.',
            )
        report = qa_services.decide_report(
            actor=self.staff, report_id=report.pk, remove=True,
        )
        question.refresh_from_db()
        self.assertEqual(report.status, KnowledgeQAReport.Status.REMOVED)
        self.assertEqual(question.status, 'archived')
        self.assertFalse(question.public_content_safe)

    def test_database_constraints_and_append_only_revisions(self):
        question, answer = self.published_answer()
        with self.assertRaises(DatabaseError), transaction.atomic():
            ExpertQuestionRevision.objects.filter(question=question).update(body='forged')
        with self.assertRaises(DatabaseError), transaction.atomic():
            ExpertAnswerRevision.objects.filter(answer=answer).delete()
        with self.assertRaises(IntegrityError), transaction.atomic():
            HelpfulVote.objects.create(answer=answer, voter=self.other)
            HelpfulVote.objects.create(answer=answer, voter=self.other)

    @override_settings(ZEMIPRO_KNOWLEDGE_QA_ENABLED=False)
    def test_feature_flag_fails_closed_for_reads_and_writes(self):
        self.assertFalse(qa_services.public_questions().exists())
        with self.assertRaises(PermissionDenied):
            qa_services.create_question(
                actor=self.asker, category_id=self.category.pk, language='ru',
                title=TITLE, body=QUESTION,
            )
