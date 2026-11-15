"""Stage 07.7: synthetic customer/worker journeys across stages 04-07.

These tests intentionally use the real Stage 04 order service, Stage 05 invitation
service, Stage 06 assignment/agreement/work services, and Stage 07 chat,
notification, review, complaint and appeal endpoints.
"""
from uuid import uuid4

from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied
from django.db.models import Avg, Count
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.marketplace.agreement_services import (
    decide_agreement_change, effective_agreement, propose_agreement_change,
)
from apps.marketplace.chat_services import (
    list_messages, open_conversation, send_message,
)
from apps.marketplace.invitation_services import create_invitation, act_on_invitation
from apps.marketplace.models import (
    Order, OrderAgreementDecision, OrderWorkEvent, Rating, RatingReply,
    Response,
)
from apps.marketplace.offer_services import submit_offer
from apps.marketplace.services import create_order, accept_response
from apps.marketplace.tests.factories import (
    make_category, make_city, make_user, make_worker_profile,
)
from apps.marketplace.work_services import (
    confirm_work_result, report_work_problem, start_work, submit_work_result,
)
from apps.moderation.case_services import (
    decide_appeal, decide_complaint, file_appeal, submit_complaint,
)
from apps.moderation.models import Complaint, ComplaintAppeal, ModerationEvent
from apps.notifications.models import Notification


@override_settings(ZEMIPRO_PILOT_CITY_SLUG='ashdod',
                   ZEMIPRO_GEMINI_TRANSLATION_ENABLED=False)
class Stage07JourneyTests(TestCase):
    def setUp(self):
        self.city = make_city('ashdod', name_ru='Ашдод')
        self.other_city = make_city('haifa', name_ru='Хайфа')
        self.category = make_category('stage07-repair')
        self.client_user = make_user('stage07-journey-client')
        self.worker = make_user('stage07-journey-worker')
        self.stranger = make_user('stage07-journey-stranger')
        self.profile = make_worker_profile(
            self.worker, city=self.city, category=self.category,
        )
        self.moderator = make_user('stage07-journey-moderator', is_staff=True)
        permission = Permission.objects.get(
            content_type=ContentType.objects.get_for_model(ModerationEvent),
            codename='review_complaints',
        )
        self.moderator.user_permissions.add(permission)

    def publish(self):
        token = uuid4()
        params = dict(
            client=self.client_user, category=self.category, city=self.city,
            address='SYNTHETIC_PRIVATE_TEST_ADDRESS',
            description='Synthetic request without private real-world data',
            price='Договорная', submission_key=token, return_created=True,
        )
        order, created = create_order(**params)
        self.assertTrue(created)
        replay, created = create_order(**params)
        self.assertFalse(created)
        self.assertEqual(replay.pk, order.pk)
        self.assertEqual(order.status, Order.Status.PUBLISHED)
        return order

    def test_scenario_a_order_offer_chat_agreement_completion_review_reply(self):
        order = self.publish()
        offer, created = submit_offer(
            order=order, actor=self.worker, message='Synthetic offer',
            data={
                'price_kind': 'fixed', 'amount_min_ils': '220.00',
                'estimated_timeline': 'Two days',
                'terms': 'Initial test agreement',
            },
            operation_key=uuid4(),
        )
        self.assertTrue(created)
        self.assertEqual(offer.status, Response.Status.SENT)

        self.client.force_login(self.client_user)
        open_url = reverse('marketplace:chat_open', args=[offer.pk])
        self.assertEqual(self.client.post(open_url).status_code, 302)
        conversation, created = open_conversation(
            response_id=offer.pk, actor=self.worker,
        )
        self.assertFalse(created)
        message_key = uuid4()
        first, created = send_message(
            conversation_id=conversation.pk, actor=self.worker,
            body='Hello, the job is possible', client_nonce=message_key,
        )
        self.assertTrue(created)
        again, created = send_message(
            conversation_id=conversation.pk, actor=self.worker,
            body='Hello, the job is possible', client_nonce=message_key,
        )
        self.assertFalse(created)
        self.assertEqual(first.pk, again.pk)
        second, created = send_message(
            conversation_id=conversation.pk, actor=self.client_user,
            body='Please confirm the timeline', client_nonce=uuid4(),
        )
        self.assertTrue(created)
        self.assertEqual(
            [m.pk for m in list_messages(
                conversation_id=conversation.pk, actor=self.client_user,
            )],
            [first.pk, second.pk],
        )
        self.client.force_login(self.stranger)
        self.assertEqual(self.client.get(reverse(
            'marketplace:chat_thread', args=[conversation.pk],
        )).status_code, 403)

        accept_response(offer, actor=self.client_user)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.ASSIGNED)
        self.assertEqual(order.worker_id, self.worker.pk)
        self.assertEqual(effective_agreement(order).number, 1)
        proposed, created = propose_agreement_change(
            order_id=order.pk, actor=self.client_user,
            base_version=1, operation_key=uuid4(),
            note='Synthetic adjusted terms',
            data={
                'price_kind': 'fixed', 'amount_min_ils': '250.00',
                'estimated_timeline': 'Three days',
                'terms': 'Revised synthetic terms',
            },
        )
        self.assertTrue(created)
        decision, accepted = decide_agreement_change(
            agreement_id=proposed.pk, actor=self.worker,
            action='accept', operation_key=uuid4(),
        )
        self.assertTrue(accepted)
        self.assertEqual(decision.result, OrderAgreementDecision.Result.ACCEPTED)
        self.assertEqual(effective_agreement(order).number, 2)

        _, started = start_work(
            order_id=order.pk, actor=self.worker, operation_key=uuid4(),
        )
        self.assertTrue(started)
        _, submitted = submit_work_result(
            order_id=order.pk, actor=self.worker, operation_key=uuid4(),
        )
        self.assertTrue(submitted)
        _, completed = confirm_work_result(
            order_id=order.pk, actor=self.client_user, operation_key=uuid4(),
        )
        self.assertTrue(completed)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.COMPLETED)
        self.assertEqual(order.work_events.count(), 3)

        self.client.force_login(self.client_user)
        review_url = reverse('marketplace:rating_create', args=[order.pk])
        self.assertEqual(self.client.post(review_url, {
            'rating': 5, 'review_text': 'Synthetic job completed well',
        }).status_code, 302)
        self.assertEqual(self.client.post(review_url, {
            'rating': 1, 'review_text': 'Forged second rating',
        }).status_code, 302)
        rating = Rating.objects.get(order=order)
        self.assertEqual(rating.rating, 5)
        self.assertEqual(rating.client_id, self.client_user.pk)
        self.client.force_login(self.worker)
        reply_url = reverse('marketplace:rating_reply', args=[rating.pk])
        self.assertEqual(self.client.post(reply_url, {
            'body': 'Thank you for your verified review',
        }).status_code, 302)
        self.assertTrue(RatingReply.objects.filter(rating=rating).exists())
        stats = Rating.objects.filter(worker=self.worker).aggregate(
            avg=Avg('rating'), count=Count('pk'),
        )
        self.assertEqual(stats, {'avg': 5.0, 'count': 1})
        self.assertEqual(
            Notification.objects.filter(
                related_order=order, recipient=self.client_user,
                dedupe_key__startswith='review.reply.',
            ).count(), 1,
        )

    def test_scenario_b_invite_accept_chat_dispute_moderator_appeal(self):
        order = self.publish()
        invitation, created = create_invitation(
            actor=self.client_user, order_id=order.pk, worker_id=self.profile.pk,
        )
        self.assertTrue(created)
        retry, created = create_invitation(
            actor=self.client_user, order_id=order.pk, worker_id=self.profile.pk,
        )
        self.assertFalse(created)
        self.assertEqual(retry.pk, invitation.pk)
        accepted_invite, changed = act_on_invitation(
            actor=self.worker, invitation_id=invitation.pk, action='accept',
        )
        self.assertTrue(changed)
        self.assertEqual(accepted_invite.status, 'accepted')
        response = Response.objects.get(order=order, worker=self.worker)
        conversation, created = open_conversation(
            response_id=response.pk, actor=self.worker,
        )
        self.assertTrue(created)
        worker_message, created = send_message(
            conversation_id=conversation.pk, actor=self.worker,
            body='Accepted your invitation', client_nonce=uuid4(),
        )
        self.assertTrue(created)
        send_message(
            conversation_id=conversation.pk, actor=self.client_user,
            body='Let us agree to the work', client_nonce=uuid4(),
        )
        accept_response(response, actor=self.client_user)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.ASSIGNED)
        _, changed = start_work(
            order_id=order.pk, actor=self.worker, operation_key=uuid4(),
        )
        self.assertTrue(changed)
        dispute_key = uuid4()
        _, changed = report_work_problem(
            order_id=order.pk, actor=self.client_user,
            problem_code=OrderWorkEvent.ProblemCode.QUALITY,
            operation_key=dispute_key,
        )
        self.assertTrue(changed)
        _, replay = report_work_problem(
            order_id=order.pk, actor=self.client_user,
            problem_code=OrderWorkEvent.ProblemCode.QUALITY,
            operation_key=dispute_key,
        )
        self.assertFalse(replay)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.DISPUTED)
        dispute = Complaint.objects.get(target_order=order)

        # A message report also reaches the same staff queue with secure access.
        reported = submit_complaint(
            actor=self.client_user, reason=Complaint.Reason.INAPPROPRIATE,
            message='Synthetic message report',
            target_message_id=worker_message.pk,
        )
        self.assertEqual(reported.target_user_id, self.worker.pk)
        self.client.force_login(self.stranger)
        self.assertEqual(self.client.get(reverse(
            'moderation:queue',
        )).status_code, 403)
        self.client.force_login(self.moderator)
        self.assertEqual(self.client.get(reverse(
            'moderation:queue',
        )).status_code, 200)
        resolved = decide_complaint(
            actor=self.moderator, complaint_id=dispute.pk,
            approve=True, note='Reviewed synthetic dispute',
        )
        self.assertEqual(resolved.status, Complaint.Status.RESOLVED)
        appeal, created = file_appeal(
            actor=self.client_user, complaint_id=dispute.pk,
            reason='Synthetic appeal on review outcome',
        )
        self.assertTrue(created)
        decision = decide_appeal(
            actor=self.moderator, appeal_id=appeal.pk, accept=False,
        )
        self.assertEqual(decision.status, ComplaintAppeal.Status.REJECTED)
        self.assertTrue(dispute.audit_events.filter(
            action=ModerationEvent.Action.APPEAL_REJECTED,
        ).exists())
        self.assertEqual(Complaint.objects.filter(
            target_order=order,
        ).count(), 1)

    def test_rtl_ashdod_only_permissions_and_ai_disabled(self):
        other = dict(
            client=self.client_user, category=self.category,
            city=self.other_city, address='SYNTHETIC_NO_REAL_ADDRESS',
            description='Out of pilot geographic scope',
            submission_key=uuid4(),
        )
        with self.assertRaises(ValueError):
            create_order(**other)
        order = self.publish()
        response, _ = submit_offer(
            order=order, actor=self.worker, message='Synthetic offer',
            data={'price_kind': 'negotiable'},
        )
        conversation, _ = open_conversation(
            response_id=response.pk, actor=self.client_user,
        )
        message, _ = send_message(
            conversation_id=conversation.pk, actor=self.worker,
            body='Hello there', client_nonce=uuid4(),
        )
        self.client.force_login(self.client_user)
        from apps.marketplace.translation_services import (
            TranslationUnavailable, translate_message,
        )
        with self.assertRaises(TranslationUnavailable):
            translate_message(
                message_id=message.pk, actor=self.client_user,
                target_language='he', consent=True,
            )
        for language, direction in [('ru', 'ltr'), ('en', 'ltr'), ('he', 'rtl')]:
            result = self.client.get(
                reverse('marketplace:chat_thread', args=[conversation.pk]),
                HTTP_ACCEPT_LANGUAGE=language,
            )
            self.assertEqual(result.status_code, 200)
            self.assertContains(result, f'lang="{language}"')
            self.assertContains(result, f'dir="{direction}"')
            self.assertContains(result, 'Hello there')
        self.worker.is_blocked = True
        self.worker.save(update_fields=['is_blocked'])
        with self.assertRaises(PermissionDenied):
            send_message(
                conversation_id=conversation.pk, actor=self.worker,
                body='Blocked attempt', client_nonce=uuid4(),
            )
        self.assertEqual(order.city.slug, 'ashdod')
