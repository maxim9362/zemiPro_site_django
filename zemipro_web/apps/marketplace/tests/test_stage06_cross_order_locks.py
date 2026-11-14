from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch
from django.test import TransactionTestCase, Client
from django.db import close_old_connections, connections, connection
from django.urls import reverse
from apps.marketplace.tests.factories import (
    make_user,
    make_city,
    make_category,
    make_order,
    make_worker_profile,
)
from apps.marketplace.offer_services import submit_offer
from apps.marketplace import services


class CrossOrder(TransactionTestCase):
    def test_concurrent_different_orders(self):
        city = make_city()
        cat = make_category()
        owner = make_user("cross-owner")
        ws = [make_user("cross-w1"), make_user("cross-w2")]
        for w in ws:
            make_worker_profile(w, city=city, category=cat)
        orders = [make_order(client=owner, city=city, category=cat) for _ in range(2)]
        offers = []
        for o in orders:
            offers.append(
                [
                    submit_offer(
                        order=o,
                        actor=w,
                        message="Synthetic",
                        data={"price_kind": "fixed", "amount_min_ils": "100"},
                    )[0]
                    for w in ws
                ]
            )
        barrier = Barrier(2)
        original = services.transition_order_status

        def transition(*args, **kwargs):
            barrier.wait(timeout=10)
            return original(*args, **kwargs)

        def choose(i):
            close_old_connections()
            try:
                with connection.cursor() as c:
                    c.execute("SET statement_timeout='15s'")
                client = Client()
                client.force_login(owner)
                return client.post(
                    reverse(
                        "marketplace:order_accept_response", args=[orders[i].pk, offers[i][i].pk]
                    )
                ).status_code
            finally:
                connections.close_all()

        with patch("apps.marketplace.services.transition_order_status", side_effect=transition):
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(choose, range(2)))
        self.assertEqual(results, [302, 302])
        from apps.marketplace.models import Response, OrderAgreementVersion
        from apps.notifications.models import Notification

        for i, order in enumerate(orders):
            order.refresh_from_db()
            self.assertEqual(order.worker_id, ws[i].pk)
            self.assertEqual(Response.objects.filter(order=order, status="accepted").count(), 1)
            self.assertEqual(OrderAgreementVersion.objects.filter(order=order).count(), 1)
            self.assertEqual(Notification.objects.filter(related_order=order).count(), 2)
