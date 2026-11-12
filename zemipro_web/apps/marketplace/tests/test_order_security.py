from django.db import IntegrityError, transaction
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User, WorkerProfile
from apps.locations.models import City
from apps.marketplace.models import Category, Order, Response
from apps.marketplace.services import create_response, get_available_orders_for_worker


class OrderSecurityTests(TestCase):
    def setUp(self):
        self.city = City.objects.create(
            name_ru='Ашдод', name_en='Ashdod', name_he='אשדוד', slug='ashdod'
        )
        self.category = Category.objects.create(
            name_ru='Сантехника', slug='plumbing'
        )
        self.owner = User.objects.create_user(username='owner', password='test-pass-1')
        self.other = User.objects.create_user(username='other', password='test-pass-2')
        self.worker = User.objects.create_user(username='worker', password='test-pass-3')
        self.staff = User.objects.create_user(
            username='staff', password='test-pass-4', is_staff=True
        )
        self.staff.user_permissions.add(Permission.objects.get(
            content_type__app_label='moderation', codename='review_complaints',
        ))
        self.unprivileged_staff = User.objects.create_user(
            username='unprivileged-staff', password='test-pass-5', is_staff=True,
        )
        self.worker_profile = WorkerProfile.objects.create(
            user=self.worker, city=self.city, display_name=self.worker.username,
            description='Synthetic published professional profile for CI.',
            pricing_details='Negotiable', spoken_languages=['ru'], is_published=True,
        )
        self.worker_profile.skills.add(self.category)
        self.other_worker_profile = WorkerProfile.objects.create(
            user=self.other, city=self.city, display_name=self.other.username,
            description='Synthetic published professional profile for CI.',
            pricing_details='Negotiable', spoken_languages=['ru'], is_published=True,
        )
        self.other_worker_profile.skills.add(self.category)
        self.owner_worker_profile = WorkerProfile.objects.create(
            user=self.owner, city=self.city, display_name=self.owner.username,
            description='Synthetic published professional profile for CI.',
            pricing_details='Negotiable', spoken_languages=['ru'], is_published=True,
        )
        self.owner_worker_profile.skills.add(self.category)
        self.private_order = Order.objects.create(
            client=self.owner,
            worker=self.worker,
            category=self.category,
            city=self.city,
            address='Herzl 45, apartment 9',
            customer_name='Private Customer',
            customer_phone='+972-50-111-2233',
            description=(
                'Call +972-50-111-2233 and come to Herzl 45, apartment 9 '
                'to inspect the plumbing.'
            ),
            price='900 ₪',
            status=Order.Status.IN_PROGRESS,
        )

    def test_anonymous_user_cannot_open_or_submit_create_form(self):
        create_url = reverse('marketplace:order_create')

        response = self.client.get(create_url)
        self.assertRedirects(response, f'{reverse("accounts:login")}?next={create_url}')

        response = self.client.post(create_url, {
            'customer_name': 'Anonymous',
            'customer_phone': '+972501234567',
            'category': self.category.pk,
            'city': self.city.pk,
            'address': 'Secret anonymous address',
            'description': 'This anonymous order must never be created by the backend.',
            'price': '100',
        })
        self.assertRedirects(response, f'{reverse("accounts:login")}?next={create_url}')
        self.assertFalse(Order.objects.filter(address='Secret anonymous address').exists())

    def test_authenticated_create_always_assigns_request_user_as_owner(self):
        self.client.force_login(self.other)
        response = self.client.post(reverse('marketplace:order_create'), {
            'customer_name': 'Registered Customer',
            'customer_phone': '+972501234567',
            'category': self.category.pk,
            'city': self.city.pk,
            'address': 'Registered owner address',
            'description': 'A sufficiently detailed description for a registered order.',
            'price': '250',
        })

        created = Order.objects.get(address='Registered owner address')
        self.assertRedirects(response, reverse('marketplace:order_detail', args=[created.pk]))
        self.assertEqual(created.client, self.other)

    def test_order_owner_is_required_at_database_level(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Order.objects.create(
                    client=None,
                    category=self.category,
                    city=self.city,
                    address='Invalid ownerless order',
                    description='This row must be rejected by the database constraint.',
                )

    def test_anonymous_user_cannot_view_order_by_id(self):
        url = reverse('marketplace:order_detail', args=[self.private_order.pk])

        response = self.client.get(url)
        self.assertRedirects(response, f'{reverse("accounts:login")}?next={url}')

    def test_unassigned_worker_sees_safe_order_fields_without_free_text(self):
        url = reverse('marketplace:order_detail', args=[self.private_order.pk])

        self.client.force_login(self.other)
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.category.name_ru)
        self.assertContains(response, self.city.name_ru)
        self.assertContains(response, self.private_order.price)
        self.assertContains(
            response, 'Подробности будут доступны назначенному исполнителю.'
        )
        self.assertNotContains(response, self.private_order.description)
        self.assertNotContains(response, self.private_order.address)
        self.assertNotContains(response, self.private_order.customer_phone)
        self.assertNotContains(response, self.private_order.customer_name)

    def test_private_details_visible_to_owner_assignee_and_authorized_staff(self):
        url = reverse('marketplace:order_detail', args=[self.private_order.pk])

        for user in (self.owner, self.worker, self.staff):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, self.private_order.address)
                self.assertContains(response, self.private_order.customer_phone)
                self.assertContains(response, self.private_order.description)

    def test_unprivileged_staff_sees_only_safe_order_fields(self):
        self.client.force_login(self.unprivileged_staff)
        response = self.client.get(reverse(
            'marketplace:order_detail', args=[self.private_order.pk],
        ))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.private_order.address)
        self.assertNotContains(response, self.private_order.customer_phone)
        self.assertNotContains(response, self.private_order.description)

    def test_unrelated_user_cannot_manage_order_by_guessing_id(self):
        order = Order.objects.create(
            client=self.owner,
            category=self.category,
            city=self.city,
            address='Another private address',
            description='Another sufficiently detailed description for permission tests.',
        )
        cancel_url = reverse('marketplace:order_cancel', args=[order.pk])

        self.client.force_login(self.other)
        response = self.client.post(cancel_url)
        self.assertEqual(response.status_code, 404)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.PUBLISHED)

        self.client.force_login(self.owner)
        response = self.client.post(cancel_url)
        self.assertRedirects(response, reverse('marketplace:order_detail', args=[order.pk]))
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELLED)

    def test_unrelated_user_cannot_accept_complete_or_review_order(self):
        pending_order = Order.objects.create(
            client=self.owner,
            category=self.category,
            city=self.city,
            address='Pending private address',
            description='Pending order used to verify accept-response permissions.',
        )
        response = Response.objects.create(order=pending_order, worker=self.worker)
        completed_order = Order.objects.create(
            client=self.owner,
            worker=self.worker,
            category=self.category,
            city=self.city,
            address='Completed private address',
            description='Completed order used to verify review permissions.',
            status=Order.Status.COMPLETED,
        )
        self.client.force_login(self.other)

        accept = self.client.post(reverse(
            'marketplace:order_accept_response',
            args=[pending_order.pk, response.pk],
        ))
        complete = self.client.post(reverse(
            'marketplace:order_complete', args=[self.private_order.pk]
        ))
        review = self.client.get(reverse(
            'marketplace:rating_create', args=[completed_order.pk]
        ))

        self.assertEqual(accept.status_code, 404)
        self.assertEqual(complete.status_code, 404)
        self.assertEqual(review.status_code, 404)
        pending_order.refresh_from_db()
        self.private_order.refresh_from_db()
        self.assertEqual(pending_order.status, Order.Status.PUBLISHED)
        self.assertEqual(self.private_order.status, Order.Status.IN_PROGRESS)

    def test_potential_worker_pages_do_not_disclose_address_before_assignment(self):
        available_order = Order.objects.create(
            client=self.owner,
            category=self.category,
            city=self.city,
            address='Hidden until assignment',
            description='A visible job summary that contains no private location details.',
        )
        self.client.force_login(self.worker)

        dashboard = self.client.get(reverse('marketplace:worker_dashboard'))
        self.assertEqual(dashboard.status_code, 200)
        self.assertContains(dashboard, available_order.price)
        self.assertNotContains(dashboard, available_order.description)
        self.assertNotContains(dashboard, available_order.address)

        respond = self.client.get(reverse('marketplace:order_respond', args=[available_order.pk]))
        self.assertEqual(respond.status_code, 200)
        self.assertContains(respond, available_order.price)
        self.assertNotContains(respond, available_order.description)
        self.assertNotContains(respond, available_order.address)

    def test_user_cannot_respond_to_own_order_through_view_or_service(self):
        own_order = Order.objects.create(
            client=self.owner,
            category=self.category,
            city=self.city,
            address='Owner private address',
            description='Owner private description with phone +972-50-999-8877.',
        )
        self.assertNotIn(
            own_order,
            list(get_available_orders_for_worker(self.owner_worker_profile)),
        )

        self.client.force_login(self.owner)
        response = self.client.post(
            reverse('marketplace:order_respond', args=[own_order.pk]),
            {'message': 'Trying to respond to myself'},
        )

        self.assertRedirects(
            response,
            reverse('marketplace:order_detail', args=[own_order.pk]),
        )
        self.assertFalse(
            Response.objects.filter(order=own_order, worker=self.owner).exists()
        )
        with self.assertRaisesMessage(
            ValueError, 'Нельзя откликнуться на собственную заявку.'
        ):
            create_response(own_order, self.owner, 'Direct service call')
