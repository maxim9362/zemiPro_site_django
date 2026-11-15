"""Stage 14.7 anonymous aggregate metrics for controlled rollout.

No request, user, IP, user-agent, cookie, query or session identifier is
accepted by this API or stored in the schema.
"""
from django.conf import settings
from django.db import DatabaseError, IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from .models import KnowledgeDailyMetric


def record(source, event, source_object_id=None):
    if not getattr(settings, 'ZEMIPRO_KNOWLEDGE_ROLLOUT_METRICS_ENABLED', False):
        return False
    if source not in KnowledgeDailyMetric.Source.values:
        return False
    if event not in KnowledgeDailyMetric.Event.values:
        return False
    if source_object_id is not None and (
        type(source_object_id) is not int or source_object_id < 1
    ):
        return False
    key = {
        'day': timezone.localdate(), 'source': source,
        'source_object_id': source_object_id, 'event': event,
    }
    try:
        with transaction.atomic():
            changed = KnowledgeDailyMetric.objects.filter(**key).update(total=F('total') + 1)
            if not changed:
                try:
                    with transaction.atomic():
                        KnowledgeDailyMetric.objects.create(total=1, **key)
                except IntegrityError:
                    KnowledgeDailyMetric.objects.filter(**key).update(
                        total=F('total') + 1,
                    )
        return True
    except DatabaseError:
        # Metrics can never make a knowledge page unavailable.
        return False
