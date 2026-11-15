"""Explicit opt-in email delivery of already persisted notifications."""
from django.core.management.base import BaseCommand
from apps.notifications.domain_services import process_email_outbox


class Command(BaseCommand):
    help = 'Stage 07: process bounded notification email outbox (disabled by default).'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=20)

    def handle(self, *args, **options):
        result = process_email_outbox(limit=options['limit'])
        self.stdout.write('stage07_notification_worker ' + str(result))
