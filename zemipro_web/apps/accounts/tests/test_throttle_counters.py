"""Synthetic expiry cleanup and privacy invariants for shared POST counters."""
from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import SensitivePostCounter


class CounterRetentionTests(TestCase):
    def test_prune_only_expired_opaque_keys(self):
        old = SensitivePostCounter.objects.create(
            bucket_hash='a' * 64,
            attempts=2,
            expires_at=timezone.now() - timedelta(days=2),
        )
        recent = SensitivePostCounter.objects.create(
            bucket_hash='b' * 64,
            attempts=1,
            expires_at=timezone.now() + timedelta(hours=1),
        )
        output = StringIO()
        call_command('prune_sensitive_post_counters', stdout=output)
        self.assertFalse(SensitivePostCounter.objects.filter(pk=old.pk).exists())
        self.assertTrue(SensitivePostCounter.objects.filter(pk=recent.pk).exists())
        self.assertIn('expired_counter_rows_removed=1', output.getvalue())

    def test_bucket_key_contains_only_opaque_hash(self):
        client = Client()
        response = client.post(
            reverse('accounts:login'),
            {'username': 'sample', 'password': 'synthetic'},
            REMOTE_ADDR='192.0.2.50',
        )
        self.assertEqual(response.status_code, 200)
        record = SensitivePostCounter.objects.get()
        self.assertEqual(len(record.bucket_hash), 64)
        self.assertNotIn('192.0.2.50', record.bucket_hash)
        self.assertNotIn('sample', record.bucket_hash)
