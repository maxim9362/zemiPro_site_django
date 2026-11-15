"""14.4 — bounded aggregate pilot observations and verified order attribution.

Pageviews and link redirects are raw counters, NOT unique visitors or leads.
Only a successfully published marketplace order is a verified attributed request.
Deduplication uses a server-secret HMAC, never a customer/order FK or PII.
"""
import time
import hashlib
import hmac

from django.conf import settings
from django.db import DatabaseError, IntegrityError, transaction
from django.db.models import F, Sum
from django.utils import timezone

from apps.marketplace.models import Order
from .models import (
    ArticlePilotDailyMetric, ArticlePilotOrderAttribution,
)
from .public_content import public_articles


SESSION_KEY = 'knowledge_article_pilot_ref'
MAX_AGE_SECONDS = 2 * 60 * 60
KINDS = {
    'article_view': 'article_views',
    'profile_click': 'profile_clicks',
    'order_click': 'order_clicks',
}


def metrics_on():
    return bool(
        settings.ZEMIPRO_KNOWLEDGE_ARTICLES_ENABLED
        and getattr(settings, 'ZEMIPRO_KNOWLEDGE_PILOT_METRICS_ENABLED', False)
    )


def record_metric(article, kind):
    """Atomic daily F() increment with unique row; never save request metadata."""
    if not metrics_on() or kind not in KINDS:
        return False
    if not public_articles().filter(pk=article.pk).exists():
        return False
    column = KINDS[kind]
    day = timezone.localdate()
    with transaction.atomic():
        row, _ = ArticlePilotDailyMetric.objects.get_or_create(
            article_id=article.pk, day=day,
        )
        ArticlePilotDailyMetric.objects.filter(pk=row.pk).update(
            **{column: F(column) + 1},
        )
    return True


def start_order_ref(request, article):
    """Mark one referral in Django's existing server-side session."""
    if not metrics_on():
        return False
    if not public_articles().filter(pk=article.pk).exists():
        return False
    request.session[SESSION_KEY] = {
        'article_id': article.pk, 'article_version': article.content_version,
        'created_at': int(time.time()),
    }
    return True


def _valid_ref(ref):
    if not isinstance(ref, dict):
        return False
    if (type(ref.get('article_id')) is not int
            or type(ref.get('article_version')) is not int
            or type(ref.get('created_at')) is not int):
        return False
    age = int(time.time()) - ref['created_at']
    return bool(
        ref['article_id'] > 0 and ref['article_version'] > 0
        and 0 <= age <= MAX_AGE_SECONDS
    )


def bind_started_order(request, order):
    """Bind to this exact *draft*; an unrelated order cannot claim the referral."""
    if not metrics_on():
        return False
    ref = request.session.get(SESSION_KEY)
    if not _valid_ref(ref) or order.status != Order.Status.DRAFT:
        request.session.pop(SESSION_KEY, None)
        return False
    if (order.client_id != getattr(request.user, 'pk', None)
            or not public_articles().filter(
                pk=ref['article_id'], content_version=ref['article_version'],
            ).exists()):
        request.session.pop(SESSION_KEY, None)
        return False
    ref['draft_order_id'] = order.pk
    request.session[SESSION_KEY] = ref
    return True


def record_published_order(request, order):
    """One row per real PUBLISHED order; never a draft or anonymous link click."""
    if not metrics_on():
        return False
    ref = request.session.pop(SESSION_KEY, None)
    if (not _valid_ref(ref)
            or type(ref.get('draft_order_id')) is not int
            or ref['draft_order_id'] != order.pk
            or order.client_id != getattr(request.user, 'pk', None)
            or order.status != Order.Status.PUBLISHED):
        return False
    article = public_articles().filter(
        pk=ref['article_id'], content_version=ref['article_version'],
    ).first()
    if article is None:
        return False
    digest = hmac.new(
        settings.SECRET_KEY.encode('utf-8'),
        f'knowledge-pilot-order:{order.pk}'.encode('ascii'),
        hashlib.sha256,
    ).hexdigest()
    try:
        _, created = ArticlePilotOrderAttribution.objects.get_or_create(
            order_digest=digest, defaults={'article': article},
        )
        return created
    except IntegrityError:
        return False


def safe_record_metric(article, kind):
    try:
        return record_metric(article, kind)
    except DatabaseError:
        # An analytics outage must not break the core public reading flow.
        return False


def safe_bind_started_order(request, order):
    try:
        return bind_started_order(request, order)
    except DatabaseError:
        return False


def safe_record_published_order(request, order):
    try:
        return record_published_order(request, order)
    except DatabaseError:
        return False


def pilot_summary():
    """Staff-only totals; do not invent activity while flags are off."""
    aggregate = ArticlePilotDailyMetric.objects.aggregate(
        raw_article_views=Sum('article_views'),
        raw_profile_clicks=Sum('profile_clicks'),
        raw_order_clicks=Sum('order_clicks'),
    )
    # Recorded only after the underlying order reached PUBLISHED.
    # Historical counter: cancellation after publication does not erase a fact.
    real_requests = ArticlePilotOrderAttribution.objects.count()
    return {
        'raw_article_views': aggregate['raw_article_views'] or 0,
        'raw_profile_clicks': aggregate['raw_profile_clicks'] or 0,
        'raw_order_clicks': aggregate['raw_order_clicks'] or 0,
        'real_attributed_published_orders': real_requests,
        'observed_data_present': bool(
            aggregate['raw_article_views'] or aggregate['raw_profile_clicks']
            or aggregate['raw_order_clicks'] or real_requests
        ),
    }
