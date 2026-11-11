"""Prune *only* expired opaque POST counters; operator-scheduled task."""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.accounts.models import SensitivePostCounter


class Command(BaseCommand):
    help = 'Remove expired opaque POST counter buckets older than 24 hours.'

    def handle(self, *args, **options):
        older_than = timezone.now() - timedelta(days=1)
        removed, _ = SensitivePostCounter.objects.filter(
            expires_at__lt=older_than
        ).delete()
        self.stdout.write(f'expired_counter_rows_removed={removed}')
