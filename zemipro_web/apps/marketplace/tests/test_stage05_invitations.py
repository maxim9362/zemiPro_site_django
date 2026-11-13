"""Stage 05.4: synthetic invitation state, authorization and lifecycle tests."""
from datetime import timedelta

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.db import IntegrityError, transaction

from apps.accounts.models import WorkerProfile
from apps.locations.models import City
from apps.marketplace.models import (
    Category, Subcategory, Order, OrderInvitation, Response,
)
from apps.marketplace.invitation_services import (
    InvitationConflict, act_on_invitation, create_invitation,
)
from apps.marketplace.tests.factories import make_user, make_order


@override_settings(ZEMIPRO_PILOT_CITY_SLUG='ashdod')
class InvitationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.city = City.objects.create(slug='ashdod', name_ru='Ашдод')
        cls.other_city = City.objects.create(slug='haifa', name_ru='Хайфа')
        cls.category = Category.objects.create(
            slug='invite-repair', name_ru='Ремонт', work_mode='onsite',
        )
        cls.other_category = Category.objects.create(
            slug='invite-cleaning', name_ru='Уборка', work_mode='onsite',
        )
        cls.service = Subcategory.objects.create(
            category=cls.category, slug='invite-pipes', name_ru='Трубы', work_mode='onsite',
        )
        cls.owner = make_user('invitation-owner')
        cls.stranger = make_user('invitation-stranger')
        cls.worker_user = make_user('invitation-worker')
        cls.worker = WorkerProfile.objects.create(
            user=cls.worker_user, city=cls.city, is_published=True,
            display_name='Invited plumber', pricing_details='Negotiable',
            description='Synthetic plumbing profile for test only.',
            spoken_languages=['ru'],
        )
        cls.worker.skills.add(cls.category)
        cls.worker.services.add(cls.service)
        cls.order = make_order(
            client=cls.owner, category=cls.category, subcategory=cls.service,
            city=cls.city, work_mode='onsite', address='PRIVATE_TEST_ADDRESS',
            customer_phone='PRIVATE_TEST_PHONE',
        )

    def invite(self):
        return create_invitation(
            actor=self.owner, order_id=self.order.pk, worker_id=self.worker.pk,
        )

    def test_owner_invite_replay_and_uniqueness(self):
        invitation, created = self.invite()
        self.assertTrue(created)
        again, created = self.invite()
        self.assertFalse(created)
        self.assertEqual(again.pk, invitation.pk)
        self.assertEqual(OrderInvitation.objects.count(), 1)
        self.assertEqual(self.worker_user.notifications.count(), 1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            OrderInvitation.objects.create(
                client=self.owner, order=self.order, worker=self.worker,
                expires_at=timezone.now() + timedelta(days=1),
            )

    def test_accept_creates_response_not_assignment(self):
        invitation, _ = self.invite()
        result, changed = act_on_invitation(
            actor=self.worker_user, invitation_id=invitation.pk, action='accept',
        )
        self.assertTrue(changed)
        self.assertEqual(result.status, 'accepted')
        self.assertEqual(Response.objects.filter(order=self.order, worker=self.worker_user).count(), 1)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.Status.PUBLISHED)
        self.assertIsNone(self.order.worker_id)
        _, again = act_on_invitation(
            actor=self.worker_user, invitation_id=invitation.pk, action='accept',
        )
        self.assertFalse(again)
        self.assertEqual(Response.objects.count(), 1)

    def test_reject_withdraw_and_wrong_actor(self):
        invitation, _ = self.invite()
        with self.assertRaises(Exception):
            act_on_invitation(actor=self.stranger, invitation_id=invitation.pk, action='accept')
        with self.assertRaises(Exception):
            act_on_invitation(actor=self.owner, invitation_id=invitation.pk, action='accept')
        result, changed = act_on_invitation(
            actor=self.worker_user, invitation_id=invitation.pk, action='decline',
        )
        self.assertTrue(changed)
        with self.assertRaises(InvitationConflict):
            act_on_invitation(actor=self.owner, invitation_id=invitation.pk, action='withdraw')
        self.assertEqual(result.status, 'declined')
        self.assertFalse(Response.objects.exists())

    def test_invalid_order_and_service_area_are_rejected(self):
        with self.assertRaises(Exception):
            create_invitation(
                actor=self.stranger, order_id=self.order.pk, worker_id=self.worker.pk,
            )
        with self.assertRaises(Exception):
            create_invitation(
                actor=self.owner, order_id=self.order.pk + 1000, worker_id=self.worker.pk,
            )
        self.worker.services.clear()
        with self.assertRaises(InvitationConflict):
            self.invite()
        self.worker.services.add(self.service)
        self.order.city = self.other_city
        self.order.save(update_fields=['city'])
        with self.assertRaises(InvitationConflict):
            self.invite()

    def test_expires_and_unpublishing_does_not_show_pending(self):
        invitation, _ = self.invite()
        invitation.expires_at = timezone.now() - timedelta(seconds=1)
        invitation.save(update_fields=['expires_at'])
        self.assertEqual(invitation.effective_status, 'expired')
        result, changed = act_on_invitation(
            actor=self.worker_user, invitation_id=invitation.pk, action='accept',
        )
        self.assertFalse(changed)
        self.assertEqual(result.status, 'expired')
        self.assertFalse(Response.objects.exists())

    def test_http_idor_csrf_and_no_private_order_fields(self):
        invitation, _ = self.invite()
        link = reverse('marketplace:invitation_detail', args=[invitation.pk])
        self.assertEqual(self.client.get(link).status_code, 302)
        self.client.force_login(self.stranger)
        self.assertEqual(self.client.get(link).status_code, 404)
        self.assertEqual(self.client.post(
            reverse('marketplace:invitation_action', args=[invitation.pk, 'accept'])
        ).status_code, 404)
        self.client.force_login(self.worker_user)
        res = self.client.get(link)
        self.assertEqual(res.status_code, 200)
        self.assertNotContains(res, 'PRIVATE_TEST_ADDRESS')
        self.assertNotContains(res, 'PRIVATE_TEST_PHONE')
        strict = self.client_class(enforce_csrf_checks=True)
        strict.force_login(self.worker_user)
        self.assertEqual(strict.post(
            reverse('marketplace:invitation_action', args=[invitation.pk, 'accept'])
        ).status_code, 403)

    def test_wizard_prefill_is_safe_and_confirmed_not_auto_created(self):
        self.client.force_login(self.owner)
        r = self.client.get(
            reverse('marketplace:order_wizard_start'), {'worker': self.worker.pk},
        )
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'name="invite_worker"')
        self.assertEqual(OrderInvitation.objects.count(), 0)
        self.assertEqual(
            self.client.get(reverse('marketplace:worker_invitation_select', args=[self.worker.pk])).status_code,
            200,
        )

    def test_own_order_picker_and_confirmation_post(self):
        self.client.force_login(self.owner)
        url = reverse('marketplace:worker_invitation_select', args=[self.worker.pk])
        res = self.client.get(url)
        self.assertContains(res, self.category.name_ru)
        posted = self.client.post(url, {'order_id': self.order.pk})
        self.assertEqual(posted.status_code, 302)
        self.assertEqual(OrderInvitation.objects.count(), 1)
        self.client.force_login(self.stranger)
        self.assertEqual(self.client.post(url, {'order_id': self.order.pk}).status_code, 404)
