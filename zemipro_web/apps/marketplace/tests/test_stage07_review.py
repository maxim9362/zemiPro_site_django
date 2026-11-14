"""07.4: verified review, worker answer, score immutability and safe display."""
from django.core.exceptions import PermissionDenied
from django.db import DatabaseError, IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse

from apps.marketplace.models import Order, Rating, RatingReply, RatingAuditEvent
from apps.marketplace.review_services import ReviewConflict, submit_review_reply
from apps.marketplace.tests.factories import make_category, make_city, make_order, make_user


class Stage07ReviewTests(TestCase):
    def setUp(self):
        city = make_city()
        category = make_category()
        self.owner = make_user('stage07-rev-owner')
        self.worker = make_user('stage07-rev-worker')
        self.other = make_user('stage07-rev-other')
        self.order = make_order(
            client=self.owner, category=category, city=city,
            status=Order.Status.COMPLETED, worker=self.worker,
        )
        self.rating = Rating.objects.create(
            order=self.order, worker=self.worker, client=self.owner,
            rating=5, review_text='Synthetic verified service',
        )
        self.url = reverse('marketplace:rating_reply', args=[self.rating.pk])

    def test_worker_reply_once_and_public_projection(self):
        reply, created = submit_review_reply(
            rating_id=self.rating.pk, actor=self.worker,
            body='Synthetic reply, call me at +972501234567',
        )
        self.assertTrue(created)
        self.assertEqual(RatingReply.objects.count(), 1)
        self.assertNotIn('+972501234567', reply.public_text)
        self.assertEqual(RatingAuditEvent.objects.get(rating=self.rating).score, 5)
        self.assertEqual(self.owner.notifications.count(), 1)
        again, created = submit_review_reply(
            rating_id=self.rating.pk, actor=self.worker,
            body='Synthetic reply, call me at +972501234567',
        )
        self.assertFalse(created)
        self.assertEqual(again.pk, reply.pk)
        with self.assertRaises(ReviewConflict):
            submit_review_reply(
                rating_id=self.rating.pk, actor=self.worker,
                body='Different duplicate reply',
            )
        self.client.force_login(self.owner)
        order_view = self.client.get(
            reverse('marketplace:order_detail', args=[self.order.pk]),
        )
        self.assertEqual(order_view.status_code, 200)
        self.assertNotContains(order_view, '+972501234567')

    def test_only_selected_active_worker_can_reply(self):
        for actor in (self.owner, self.other):
            with self.assertRaises(PermissionDenied):
                submit_review_reply(
                    rating_id=self.rating.pk, actor=actor, body='Forged reply',
                )
        self.worker.is_blocked = True
        self.worker.save(update_fields=['is_blocked'])
        with self.assertRaises(PermissionDenied):
            submit_review_reply(
                rating_id=self.rating.pk, actor=self.worker,
                body='Blocked reply',
            )
        self.assertFalse(RatingReply.objects.exists())

    def test_http_csrf_owner_and_no_score_edit(self):
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(self.url, {
            'body': 'Fake reply',
        }).status_code, 403)
        self.client.force_login(self.worker)
        self.assertEqual(self.client.post(self.url, {
            'body': 'Verified synthetic response',
        }).status_code, 302)
        self.assertEqual(RatingReply.objects.count(), 1)
        with self.assertRaises(DatabaseError), transaction.atomic():
            Rating.objects.filter(pk=self.rating.pk).update(
                review_text='Unapproved changed review',
            )
        with self.assertRaises(DatabaseError), transaction.atomic():
            Rating.objects.filter(pk=self.rating.pk).update(
                public_review_text_snapshot='Untrusted public injection',
            )
        with self.assertRaises(DatabaseError), transaction.atomic():
            Rating.objects.filter(pk=self.rating.pk).update(rating=1)
        self.rating.refresh_from_db()
        self.assertEqual(self.rating.rating, 5)
        with self.assertRaises(DatabaseError), transaction.atomic():
            RatingReply.objects.filter(rating=self.rating).update(body='Tampered')

    def test_illegal_rating_score_and_noncompleted_reply(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.rating.rating = 0
            Rating.objects.create(
                order=make_order(
                    client=self.owner, category=self.order.category, city=self.order.city,
                    status=Order.Status.COMPLETED, worker=self.worker,
                ),
                client=self.owner, worker=self.worker, rating=0,
            )
        self.order.status = Order.Status.DISPUTED
        self.order.save(update_fields=['status'])
        with self.assertRaises(PermissionDenied):
            submit_review_reply(
                rating_id=self.rating.pk, actor=self.worker, body='Not completed',
            )
