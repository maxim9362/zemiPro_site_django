"""Stage 14.1 — schema guarantees using synthetic data in an isolated PostgreSQL DB."""
import uuid

from django.conf import settings
from django.db import DatabaseError, IntegrityError, transaction
from django.test import TestCase

from apps.knowledge.models import ExpertArticle, ExpertArticleRevision
from apps.marketplace.tests.factories import (
    make_category, make_city, make_user, make_worker_profile,
)


class KnowledgeArticleSchemaTests(TestCase):
    def setUp(self):
        self.city = make_city(slug='qa-ashdod-s14')
        self.category = make_category(slug='qa-knowledge-s14')
        self.user = make_user('stage14-writer')
        self.worker = make_worker_profile(self.user, city=self.city, category=self.category)
        self.article = ExpertArticle.objects.create(
            author=self.worker, category=self.category,
            slug='qa-safe-synthetic-advice', language='ru',
            title='Synthetic draft', body='No real contacts or personal data.',
        )

    def test_untrusted_draft_is_not_public_and_flags_are_off(self):
        self.assertEqual(self.article.status, ExpertArticle.Status.DRAFT)
        self.assertEqual(self.article.public_title, '')
        self.assertEqual(self.article.public_body, '')
        self.assertFalse(self.article.public_content_safe)
        self.assertIsNone(self.article.approved_version)
        self.assertFalse(settings.ZEMIPRO_KNOWLEDGE_ARTICLES_ENABLED)
        self.assertFalse(settings.ZEMIPRO_KNOWLEDGE_QA_ENABLED)
        self.assertFalse(settings.ZEMIPRO_RECOMMENDATION_REQUESTS_ENABLED)
        # Test settings intentionally disable the city pilot gate for legacy
        # multi-city fixtures. The production Ashdod-only guard is unchanged
        # and separately tested by Stage 02.
        self.assertFalse(settings.ZEMIPRO_PERSONAL_RECOMMENDATIONS_ENABLED)

    def test_cannot_publish_without_moderated_public_snapshot(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            ExpertArticle.objects.filter(pk=self.article.pk).update(status='published')
        self.article.refresh_from_db()
        self.assertEqual(self.article.status, 'draft')

    def test_database_rejects_unknown_language_and_status(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            ExpertArticle.objects.filter(pk=self.article.pk).update(language='fr')
        with self.assertRaises(IntegrityError), transaction.atomic():
            ExpertArticle.objects.filter(pk=self.article.pk).update(status='unreviewed')

    def test_language_variant_uniqueness(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            ExpertArticle.objects.create(
                author=self.worker, category=self.category, language='ru',
                slug=self.article.slug, title='Another', body='Synthetic',
            )
        with self.assertRaises(IntegrityError), transaction.atomic():
            ExpertArticle.objects.create(
                author=self.worker, category=self.category, language='ru',
                slug='different-slug', translation_group=self.article.translation_group,
                title='Copy', body='Synthetic',
            )
        other = ExpertArticle.objects.create(
            author=self.worker, category=self.category, language='he',
            slug=self.article.slug, translation_group=self.article.translation_group,
            translation_kind=ExpertArticle.TranslationKind.HUMAN,
            title='תוכן בדיקה', body='תוכן בדיקה',
        )
        self.assertEqual(other.language, 'he')

    def test_revision_is_append_only_even_via_queryset(self):
        revision = ExpertArticleRevision.objects.create(
            article=self.article, version=1, actor=self.user,
            action=ExpertArticleRevision.Action.CREATED, status_snapshot='draft',
            title='Synthetic draft', body='Synthetic body',
        )
        with self.assertRaises(DatabaseError), transaction.atomic():
            ExpertArticleRevision.objects.filter(pk=revision.pk).update(body='Modified')
        with self.assertRaises(DatabaseError), transaction.atomic():
            ExpertArticleRevision.objects.filter(pk=revision.pk).delete()
        self.assertEqual(ExpertArticleRevision.objects.count(), 1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ExpertArticleRevision.objects.create(
                article=self.article, version=1, actor=self.user,
                action='edited', status_snapshot='draft',
                title='Duplicate revision', body='Synthetic body',
            )

    def test_revised_content_is_not_an_order_or_rated_review(self):
        self.assertFalse(any(
            field.related_model and field.related_model._meta.label in {
                'marketplace.Order', 'marketplace.Rating',
            }
            for field in ExpertArticle._meta.fields
        ))
        self.assertEqual(
            ExpertArticle.objects.filter(translation_group=uuid.uuid4()).count(), 0,
        )
        self.assertIn(
            ('moderate_expert_articles', 'Can moderate expert articles'),
            ExpertArticle._meta.permissions,
        )
