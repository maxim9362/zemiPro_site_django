"""Stage 14.11 secure external-worker registration links and data minimization."""
from datetime import timedelta
from urllib.parse import urlparse
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db import DatabaseError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import WorkerProfile
from apps.knowledge import invite_services
from apps.knowledge.models import ExternalWorkerInvite
from apps.marketplace.tests.factories import make_user


@override_settings(ZEMIPRO_EXTERNAL_WORKER_INVITES_ENABLED=True)
class Stage14ExternalInviteTests(TestCase):
    def setUp(self):
        self.inviter = make_user('s14-external-inviter')

    def create(self):
        return invite_services.create_invite(actor=self.inviter)

    def test_only_digest_and_aggregate_counts_are_persisted(self):
        invite, token = self.create()
        self.assertNotEqual(invite.token_digest, token)
        self.assertNotIn(token, invite.token_digest)
        names = {field.name for field in ExternalWorkerInvite._meta.fields}
        self.assertFalse(names & {
            'email', 'phone', 'recipient', 'contact', 'claimed_by', 'user_agent', 'ip',
        })
        self.assertEqual(invite.opened_count, 0)
        self.assertEqual(invite.claimed_count, 0)

    def test_manual_create_page_has_copy_and_fixed_facebook_share(self):
        self.client.force_login(self.inviter)
        response = self.client.post(reverse('knowledge:external_invite_create'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-copy-invite')
        self.assertContains(response, 'Facebook / Messenger')
        invite_url = response.context['invite_url']
        self.assertEqual(urlparse(invite_url).netloc, 'testserver')
        self.assertNotContains(response, 'name="email"')
        self.assertNotContains(response, 'name="phone"')
        facebook = self.client.get(response.context['facebook_url'])
        self.assertEqual(facebook.status_code, 302)
        self.assertTrue(facebook['Location'].startswith(
            'https://www.facebook.com/sharer/sharer.php?',
        ))

    def test_landing_and_real_registration_count_without_fake_profile(self):
        invite, token = self.create()
        landing = self.client.get(reverse('knowledge_invites:landing', args=[token]))
        self.assertRedirects(
            landing, reverse('accounts:register') + '?worker_invite=1',
            fetch_redirect_response=False,
        )
        invite.refresh_from_db()
        self.assertEqual(invite.opened_count, 1)
        registration = self.client.get(reverse('accounts:register'))
        self.assertContains(registration, 'самостоятельно зарегистрироваться как мастер')
        response = self.client.post(reverse('accounts:register'), {
            'username': 's14-genuine-new-worker',
            'email': 's14-genuine-worker@example.invalid',
            'password1': 'SafeSyntheticPassword-2026!',
            'password2': 'SafeSyntheticPassword-2026!',
        })
        self.assertEqual(response.status_code, 302)
        invite.refresh_from_db()
        self.assertEqual(invite.claimed_count, 1)
        self.assertIsNotNone(invite.claimed_at)
        new_user = get_user_model().objects.get(username='s14-genuine-new-worker')
        self.assertFalse(WorkerProfile.objects.filter(user=new_user).exists())
        self.assertFalse(hasattr(invite, 'claimed_by'))
        self.client.logout()
        self.assertEqual(self.client.get(reverse(
            'knowledge_invites:landing', args=[token],
        )).status_code, 404)

    def test_invalid_expired_and_disabled_links_fail_closed(self):
        invite, token = self.create()
        expired_token = 'x' * 43
        ExternalWorkerInvite.objects.create(
            inviter=self.inviter, token_digest=invite_services._digest(expired_token),
            expires_at=timezone.now() - timedelta(seconds=1),
        )
        self.assertEqual(self.client.get('/join/worker/not-a-valid-token/').status_code, 404)
        self.assertEqual(self.client.get(reverse(
            'knowledge_invites:landing', args=[expired_token],
        )).status_code, 404)
        with override_settings(ZEMIPRO_EXTERNAL_WORKER_INVITES_ENABLED=False):
            self.assertEqual(self.client.get(reverse(
                'knowledge_invites:landing', args=[token],
            )).status_code, 404)

    def test_invite_audit_identity_cannot_be_changed_or_deleted(self):
        invite, _ = self.create()
        with self.assertRaises(DatabaseError), transaction.atomic():
            ExternalWorkerInvite.objects.filter(pk=invite.pk).update(
                inviter=make_user('s14-forged-inviter'),
            )
        with self.assertRaises(DatabaseError), transaction.atomic():
            ExternalWorkerInvite.objects.filter(pk=invite.pk).delete()

    def test_attribution_failure_never_breaks_account_registration(self):
        invite, token = self.create()
        self.client.get(reverse('knowledge_invites:landing', args=[token]))
        with patch(
            'apps.knowledge.invite_services.claim_invite_from_session',
            side_effect=RuntimeError('synthetic metrics failure'),
        ):
            response = self.client.post(reverse('accounts:register'), {
                'username': 's14-registration-survives-metrics',
                'email': 'survives-metrics@example.invalid',
                'password1': 'SafeSyntheticPassword-2026!',
                'password2': 'SafeSyntheticPassword-2026!',
            })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(get_user_model().objects.filter(
            username='s14-registration-survives-metrics',
        ).exists())
        self.assertIn('_auth_user_id', self.client.session)
        invite.refresh_from_db()
        self.assertEqual(invite.claimed_count, 0)

    @override_settings(ZEMIPRO_EXTERNAL_WORKER_INVITES_ENABLED=False)
    def test_flag_blocks_creation_and_public_landing(self):
        self.client.force_login(self.inviter)
        self.assertEqual(self.client.get(reverse(
            'knowledge:external_invite_create',
        )).status_code, 404)
        with self.assertRaises(PermissionDenied):
            self.create()
