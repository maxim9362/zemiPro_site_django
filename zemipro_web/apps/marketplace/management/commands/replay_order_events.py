"""Safely replay pending internal order-event consumers (no outbound sends)."""
from django.core.management.base import BaseCommand, CommandError

from apps.marketplace.order_events import replay_pending_order_events


class Command(BaseCommand):
    help = 'Replay local in-app and analytics outbox receipts, no SMS/SMTP/push.'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=100)

    def handle(self, *args, **options):
        limit = options['limit']
        if not 1 <= limit <= 1000:
            raise CommandError('Allowed --limit is 1..1000.')
        processed = replay_pending_order_events(limit=limit)
        self.stdout.write(self.style.SUCCESS(
            f'Processed {processed} local order-event receipts.'
        ))
