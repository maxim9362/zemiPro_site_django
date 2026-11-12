"""Stage 04.6 — transactional PostgreSQL quotas for costly order writes.

Every mutation is charged inside the SAME transaction as the target row.
An idempotent replay or failed transaction consumes no quota.
"""
from datetime import datetime, timedelta, timezone

from django.core.exceptions import PermissionDenied
from django.db import connection, transaction
from django.utils import timezone as django_timezone

from apps.accounts.models import User

from .models import OrderWriteQuota


# Conservative initial limits; do not widen without owner approval.
# window seconds, max units per owner per window.
ORDER_WRITE_LIMITS = {
    'create': (86400, 25),
    'wizard': (3600, 120),
    'edit': (3600, 60),
    'response': (86400, 50),
    'photo': (86400, 30),
    'state': (3600, 60),
}


class OrderQuotaExceeded(ValueError):
    """Safe message; never logs or exposes account data."""

    def __init__(self, retry_after):
        super().__init__('Превышен лимит действий. Повторите позже.')
        self.retry_after = retry_after


def consume_order_quota(actor, kind, *, units=1):
    """Serialize quota via a unique DB row; caller must be in transaction.atomic."""
    if not connection.in_atomic_block:
        raise RuntimeError('Order quota requires an atomic database transaction.')
    if connection.vendor != 'postgresql':
        raise RuntimeError('Order quotas require PostgreSQL.')
    if not getattr(actor, 'is_authenticated', False) or actor.pk is None:
        raise PermissionDenied('Нет доступа к действиям над заказом.')
    if not User.objects.filter(
        pk=actor.pk, is_active=True, is_blocked=False,
        email_verification_required=False,
    ).exists():
        raise PermissionDenied('Аккаунт недоступен.')
    if kind not in ORDER_WRITE_LIMITS or not isinstance(units, int) or not 1 <= units <= 50:
        raise ValueError('Неверный тип операции с заявкой.')
    window, limit = ORDER_WRITE_LIMITS[kind]
    now = django_timezone.now().astimezone(timezone.utc)
    bucket_number = int(now.timestamp()) // window
    beginning = datetime.fromtimestamp(bucket_number * window, tz=timezone.utc)
    retry_after = max(
        1, int((beginning + timedelta(seconds=window) - now).total_seconds()) + 1,
    )

    row, _ = OrderWriteQuota.objects.select_for_update().get_or_create(
        owner_id=actor.pk, kind=kind, bucket_start=beginning,
        defaults={'used': 0},
    )
    if row.used + units > limit:
        raise OrderQuotaExceeded(retry_after=retry_after)
    row.used += units
    row.save(update_fields=['used'])
    return row.used
