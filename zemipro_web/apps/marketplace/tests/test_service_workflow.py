"""Focused business-service happy path and negative authorization tests."""

from django.contrib.auth.models import AnonymousUser, Permission
from django.test import TestCase

from apps.marketplace.models import Order, Response
from apps.marketplace.services import (
    accept_response,
    can_view_private_order_details,
    cancel_order,
    complete_order,
    create_order,
    create_response,
)

from .factories import (
    make_category,
    make_city,
    make_order,
    make_user,
    make_worker_profile,
)


class ServiceWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.city = make_city()
        cls.category = make_category()
        cls.owner = make_user('ci-owner')
        cls.worker = make_user('ci-worker')
        cls.unrelated = make_user('ci-unrelated')
        cls.staff = make_user('ci-staff', is_staff=True)
        cls.staff.user_permissions.add(Permission.objects.get(
            content_type__app_label='moderation', codename='review_complaints',
        ))
        make_worker_profile(cls.worker, city=cls.city, category=cls.category)

    def test_registered_customer_to_accepted_worker_to_completed_order(self):
        order = create_order(
            client=self.owner,
            category=self.category,
            city=self.city,
            address='Synthetic project site',
            description='Synthetic test booking for a service',
        )
        self.assertEqual(order.client_id, self.owner.pk)
        self.assertEqual(order.status, Order.Status.PUBLISHED)

        response = create_response(order, self.worker, 'Synthetic availability')
        self.assertEqual(response.status, Response.Status.PENDING)

        accepted = accept_response(response)
        order.refresh_from_db()
        accepted.refresh_from_db()
        self.assertEqual(order.status, Order.Status.IN_PROGRESS)
        self.assertEqual(order.worker_id, self.worker.pk)
        self.assertEqual(accepted.status, Response.Status.ACCEPTED)

        complete_order(order)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.COMPLETED)

    def test_unverified_new_account_cannot_bypass_gate_via_service(self):
        self.owner.email_verification_required = True
        self.owner.save(update_fields=['email_verification_required'])
        with self.assertRaisesMessage(ValueError, 'Аккаунт недоступен'):
            create_order(
                client=self.owner,
                category=self.category,
                city=self.city,
                address='Must not be created',
                description='Direct service bypass must remain blocked.',
            )
        self.assertFalse(Order.objects.filter(address='Must not be created').exists())

    def test_guest_cannot_create_order_from_service(self):
        with self.assertRaisesMessage(ValueError, 'требуется авторизация'):
            create_order(
                client=AnonymousUser(),
                category=self.category,
                city=self.city,
                address='Synthetic',
                description='Test order',
            )
        self.assertEqual(Order.objects.count(), 0)

    def test_duplicate_response_is_blocked(self):
        order = make_order(
            client=self.owner, category=self.category, city=self.city
        )
        create_response(order, self.worker, 'First synthetic response')
        with self.assertRaisesMessage(ValueError, 'Вы уже откликались'):
            create_response(order, self.worker, 'Duplicate synthetic response')
        self.assertEqual(Response.objects.filter(order=order).count(), 1)

    def test_assigned_worker_owner_and_staff_can_view_private_order(self):
        order = make_order(
            client=self.owner, worker=self.worker,
            category=self.category, city=self.city,
        )
        for user in (self.owner, self.worker, self.staff):
            with self.subTest(username=user.username):
                self.assertTrue(can_view_private_order_details(user, order))
        self.assertFalse(can_view_private_order_details(self.unrelated, order))
        self.assertFalse(can_view_private_order_details(AnonymousUser(), order))

    def test_cancel_order_persists_cancelled_status(self):
        order = make_order(
            client=self.owner, category=self.category, city=self.city
        )
        cancel_order(order)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELLED)

    def test_cannot_respond_to_completed_order(self):
        order = make_order(
            client=self.owner,
            category=self.category,
            city=self.city,
            status=Order.Status.COMPLETED,
        )
        with self.assertRaisesMessage(ValueError, 'уже не в статусе'):
            create_response(order, self.worker, 'Too late')
        self.assertFalse(Response.objects.filter(order=order).exists())
