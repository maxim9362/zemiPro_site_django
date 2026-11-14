"""Isolated Stage 07 upgrade/rollback rehearsal with synthetic Stage 06 rows."""
import os
import sys
from pathlib import Path

import django

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    django.setup()
    from django.conf import settings
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor

    if settings.ENVIRONMENT != 'test' or connection.vendor != 'postgresql':
        raise RuntimeError('Stage 07 rehearsal requires isolated PostgreSQL test mode')
    if settings.DATABASES['default']['HOST'] not in (
        'localhost', '127.0.0.1', 'db', 'postgres',
    ):
        raise RuntimeError('Refusing remote database migration')

    executor = MigrationExecutor(connection)
    original_leaves = executor.loader.graph.leaf_nodes()
    baseline = [
        ('marketplace', '0019_stage06_work_events'),
        ('notifications', '0002_order_event_deduplication'),
        ('moderation', '0004_protect_complaint_reporter'),
    ]
    identities = {}
    try:
        executor.migrate(baseline)
        older = executor.loader.project_state(baseline).apps
        User = older.get_model('accounts', 'User')
        City = older.get_model('locations', 'City')
        Category = older.get_model('marketplace', 'Category')
        Order = older.get_model('marketplace', 'Order')
        Response = older.get_model('marketplace', 'Response')
        Rating = older.get_model('marketplace', 'Rating')
        Complaint = older.get_model('moderation', 'Complaint')
        Notification = older.get_model('notifications', 'Notification')

        city = City.objects.filter(slug='ashdod').first()
        category = Category.objects.filter(is_active=True).first()
        if city is None or category is None:
            raise AssertionError('Synthetic seeded city and category required')
        client = User.objects.create(username='stage07_legacy_customer')
        worker = User.objects.create(username='stage07_legacy_worker')
        order = Order.objects.create(
            client=client, worker=worker, category=category, city=city,
            address='Synthetic legacy location',
            description='Synthetic pre-Stage07 request',
            status='completed',
        )
        response = Response.objects.create(
            order=order, worker=worker, status='accepted',
        )
        rating = Rating.objects.create(
            order=order, worker=worker, client=client,
            rating=4, review_text='Synthetic historic review',
        )
        complaint = Complaint.objects.create(
            reporter=client, target_user=worker, target_order=order,
            reason='other', message='Synthetic historic complaint',
        )
        notice = Notification.objects.create(
            recipient=worker, related_order=order,
            notification_type='review_created',
            title='Synthetic notice', message='Synthetic historic notice',
        )
        identities = {
            'client': client.pk, 'worker': worker.pk, 'order': order.pk,
            'response': response.pk, 'rating': rating.pk,
            'complaint': complaint.pk, 'notice': notice.pk,
        }
    finally:
        executor = MigrationExecutor(connection)
        executor.migrate(original_leaves)

    from apps.marketplace.models import Order, Response, Rating
    from apps.notifications.models import Notification
    from apps.moderation.models import Complaint
    from apps.marketplace.models import MessageTranslation, Conversation
    assert Order.objects.get(pk=identities['order']).client_id == identities['client']
    assert Response.objects.get(pk=identities['response']).worker_id == identities['worker']
    assert Rating.objects.get(pk=identities['rating']).rating == 4
    assert Complaint.objects.get(pk=identities['complaint']).target_message_id is None
    assert Notification.objects.get(pk=identities['notice']).dedupe_key is None
    assert MessageTranslation.objects.count() == 0
    assert Conversation.objects.count() == 0
    print('STAGE_07_UPGRADE_REHEARSAL_PASS historical rows preserved; rollback/reapply successful')


if __name__ == '__main__':
    main()
