"""Stage 14.7 aggregate analytics, concurrency and kill-switch checks."""
from concurrent.futures import ThreadPoolExecutor

from django.db import close_old_connections
from django.test import TestCase, TransactionTestCase, override_settings

from apps.knowledge import rollout_metrics
from apps.knowledge.models import KnowledgeDailyMetric


class Stage14RolloutDisabledTests(TestCase):
    def test_metrics_fail_closed_and_reject_identity_shaped_inputs(self):
        self.assertFalse(rollout_metrics.record('question', 'question_view', 1))
        self.assertFalse(rollout_metrics.record('visitor', 'question_view', 1))
        self.assertFalse(rollout_metrics.record('question', 'email', 1))
        self.assertFalse(rollout_metrics.record('question', 'question_view', 'user-1'))
        self.assertFalse(KnowledgeDailyMetric.objects.exists())

    def test_schema_has_no_visitor_identity_fields(self):
        names = {field.name for field in KnowledgeDailyMetric._meta.fields}
        self.assertTrue({'day', 'source', 'source_object_id', 'event', 'total'} <= names)
        self.assertFalse(names & {
            'user', 'session', 'ip', 'user_agent', 'email', 'phone', 'query', 'cookie',
        })


@override_settings(ZEMIPRO_KNOWLEDGE_ROLLOUT_METRICS_ENABLED=True)
class Stage14RolloutConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def _record(self, _):
        close_old_connections()
        try:
            return rollout_metrics.record('question', 'question_view', 91)
        finally:
            close_old_connections()

    def test_concurrent_updates_keep_one_aggregate_row(self):
        with ThreadPoolExecutor(max_workers=5) as pool:
            results = list(pool.map(self._record, range(20)))
        self.assertTrue(all(results))
        metric = KnowledgeDailyMetric.objects.get(
            source='question', source_object_id=91, event='question_view',
        )
        self.assertEqual(metric.total, 20)

    def test_each_source_event_pair_is_separate(self):
        rollout_metrics.record('question', 'question_view', 3)
        rollout_metrics.record('question', 'profile_click', 3)
        rollout_metrics.record('article', 'article_view', 3)
        self.assertEqual(KnowledgeDailyMetric.objects.count(), 3)
