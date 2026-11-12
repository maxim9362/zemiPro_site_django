from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.db import close_old_connections, connections
from django.test import TransactionTestCase, skipUnlessDBFeature

from apps.accounts.models import User
from apps.locations.models import City
from apps.marketplace.models import Category, Order, Response
from apps.marketplace.services import accept_response


class ConcurrentResponseAcceptanceTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.owner = User.objects.create_user(username='concurrent-owner')
        self.worker_one = User.objects.create_user(username='worker-one')
        self.worker_two = User.objects.create_user(username='worker-two')
        self.city = City.objects.create(name_ru='Ашдод', slug='concurrent-ashdod')
        self.category = Category.objects.create(
            name_ru='Сантехника', slug='concurrent-plumbing'
        )
        self.order = Order.objects.create(
            client=self.owner,
            category=self.category,
            city=self.city,
            address='Concurrent test address',
            description='Concurrent selection test order description.',
        )
        self.response_one = Response.objects.create(
            order=self.order, worker=self.worker_one
        )
        self.response_two = Response.objects.create(
            order=self.order, worker=self.worker_two
        )

    @skipUnlessDBFeature('has_select_for_update')
    def test_only_one_parallel_accept_can_assign_worker(self):
        barrier = Barrier(2)

        def accept_in_separate_connection(response_id):
            close_old_connections()
            try:
                response = Response.objects.get(pk=response_id)
                barrier.wait(timeout=5)
                accepted = accept_response(response, actor=self.owner)
                return ('accepted', accepted.worker_id)
            except ValueError as error:
                return ('rejected', str(error))
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(
                accept_in_separate_connection,
                [self.response_one.pk, self.response_two.pk],
            ))

        self.order.refresh_from_db()
        self.response_one.refresh_from_db()
        self.response_two.refresh_from_db()

        self.assertEqual([result[0] for result in results].count('accepted'), 1)
        self.assertEqual([result[0] for result in results].count('rejected'), 1)
        self.assertIn(self.order.worker_id, [self.worker_one.pk, self.worker_two.pk])
        self.assertEqual(self.order.status, Order.Status.IN_PROGRESS)
        self.assertEqual(
            [self.response_one.status, self.response_two.status].count(
                Response.Status.ACCEPTED
            ),
            1,
        )
        self.assertEqual(
            [self.response_one.status, self.response_two.status].count(
                Response.Status.REJECTED
            ),
            1,
        )
