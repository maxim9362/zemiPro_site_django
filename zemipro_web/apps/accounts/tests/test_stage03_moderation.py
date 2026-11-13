"""Stage 03.6 permission, moderation, privacy and append-only audit regressions.

All users, contacts, work orders and complaints here are synthetic.
"""
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied
from django.db import DatabaseError, transaction
from django.db.models.deletion import ProtectedError
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils.translation import override

from apps.accounts.admin import PrivacyRequestAdmin, UserAdmin
from apps.accounts.models import ClientProfile, PrivacyRequest, WorkerProfile
from apps.accounts.services import select_active_role
from apps.locations.models import City
from apps.marketplace.models import Category, Order, Response, Rating
from apps.marketplace.admin import OrderAdmin, ResponseAdmin, RatingAdmin
from apps.marketplace.services import (
    accept_response, can_view_private_order_details, create_order,
    create_response,
)
from apps.moderation.admin import ComplaintAdmin, ModerationEventAdmin
from apps.moderation.models import Complaint, ModerationEvent
from apps.moderation.services import (
    block_user, dismiss_complaint,
    resolve_complaint, review_privacy_request, unblock_user,
)


@override_settings(ZEMIPRO_PILOT_CITY_SLUG='ashdod')
class ModerationAndPermissionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.city = City.objects.create(
            slug='ashdod', name_ru='Ашдод',
            name_en='Ashdod', name_he='אשדוד',
        )
        cls.category = Category.objects.create(
            slug='moderation-synthetic', name_ru='Синтетическая услуга',
        )

    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user(
            username='stage036-owner', password='Synthetic-Owner-9362',
        )
        self.worker = User.objects.create_user(
            username='stage036-worker', password='Synthetic-Worker-9362',
        )
        self.other = User.objects.create_user(
            username='stage036-other', password='Synthetic-Other-9362',
        )
        self.staff = User.objects.create_user(
            username='stage036-moderator', is_staff=True,
            password='Synthetic-Moderator-9362',
        )
        self.root = User.objects.create_superuser(
            username='stage036-root', email='root@example.invalid',
            password='Synthetic-Root-9362',
        )
        ClientProfile.objects.create(user=self.owner, city=self.city)
        self.profile = WorkerProfile.objects.create(
            user=self.worker, city=self.city, display_name='Synthetic Worker',
            description='Synthetic complete worker with published services.',
            pricing_details='Negotiable', spoken_languages=['ru'],
            is_published=True,
        )
        self.profile.skills.add(self.category)
        self.order = Order.objects.create(
            client=self.owner, worker=None, category=self.category,
            city=self.city,
            address='PRIVATE_SYNTHETIC_ADDRESS_036',
            description='PRIVATE_SYNTHETIC_DESCRIPTION_036',
        )
        self.response = Response.objects.create(
            order=self.order, worker=self.worker,
            message='Synthetic worker response',
        )
        self.complaint = Complaint.objects.create(
            reporter=self.owner, target_user=self.worker,
            reason=Complaint.Reason.SPAM, message='Synthetic complaint',
        )
        self.request = PrivacyRequest.objects.create(
            user=self.owner, kind=PrivacyRequest.Kind.EXPORT,
        )

    def grant(self, *codenames):
        qs = Permission.objects.filter(
            content_type__app_label='moderation', codename__in=codenames,
        )
        self.assertEqual(qs.count(), len(codenames))
        self.staff.user_permissions.add(*qs)
        # Django caches permissions after has_perm; use fresh object.
        self.staff = get_user_model().objects.get(pk=self.staff.pk)
        return self.staff

    def test_blocked_signed_in_session_denied_across_private_endpoints(self):
        self.client.force_login(self.owner)
        get_user_model().objects.filter(pk=self.owner.pk).update(is_blocked=True)
        checks = (
            ('get', reverse('marketplace:order_detail', args=[self.order.pk]), None),
            ('get', reverse('marketplace:client_dashboard'), None),
            ('get', reverse('notifications:notification_list'), None),
            ('get', reverse('accounts:client_settings'), None),
            ('get', reverse('moderation:complaint_create'), None),
            ('post', reverse('marketplace:order_create'), {
                'address': 'BLOCKED_ATTEMPT', 'description': 'Blocked attempt',
                'category': self.category.pk, 'city': self.city.pk,
            }),
            ('post', reverse('accounts:switch_role'), {'role': 'worker'}),
            ('post', reverse('accounts:client_privacy_request'), {'kind': 'delete'}),
        )
        for method, url, data in checks:
            with self.subTest(url=url):
                response = getattr(self.client, method)(
                    url, data or {},
                ) if method == 'post' else self.client.get(url)
                self.assertEqual(response.status_code, 403)
                self.assertNotContains(response, self.order.address,
                                       status_code=403)
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(PrivacyRequest.objects.count(), 1)
        self.owner.refresh_from_db()
        self.assertEqual(self.owner.active_role, 'client')

    def test_blocked_service_layer_refuses_new_order_or_response(self):
        self.owner.is_blocked = True
        self.owner.save(update_fields=['is_blocked'])
        with self.assertRaises(ValueError):
            create_order(
                self.owner, self.category, self.city,
                'Synthetic blocked new address', 'Blocked order request',
            )
        self.assertFalse(can_view_private_order_details(self.owner, self.order))
        self.worker.is_blocked = True
        self.worker.save(update_fields=['is_blocked'])
        with self.assertRaises(ValueError):
            create_response(self.order, self.worker, 'Blocked response')
        self.assertFalse(can_view_private_order_details(self.worker, self.order))
        self.assertEqual(Response.objects.filter(order=self.order).count(), 1)

    def test_anonymous_and_unprivileged_staff_cannot_moderate(self):
        for actor in (None, self.owner, self.staff):
            with self.subTest(actor=str(actor)):
                with self.assertRaises(PermissionDenied):
                    block_user(self.worker, actor=actor)
                with self.assertRaises(PermissionDenied):
                    resolve_complaint(self.complaint, actor=actor)
                with self.assertRaises(PermissionDenied):
                    review_privacy_request(self.request, actor=actor)
        self.worker.refresh_from_db()
        self.assertFalse(self.worker.is_blocked)
        self.assertEqual(ModerationEvent.objects.count(), 0)
        self.assertEqual(self.complaint.status, Complaint.Status.PENDING)

    def test_staff_moderation_is_granular_and_immutable(self):
        actor = self.grant('moderate_accounts', 'review_complaints')
        self.assertTrue(block_user(self.worker, actor=actor, complaint=self.complaint))
        self.assertFalse(block_user(self.worker, actor=actor))
        self.worker.refresh_from_db()
        self.assertTrue(self.worker.is_blocked)
        self.assertFalse(self.worker.is_active)
        self.assertEqual(self.order.status, Order.Status.PUBLISHED)
        self.assertTrue(Response.objects.filter(pk=self.response.pk).exists())
        with self.assertRaises(ValueError):
            accept_response(self.response, actor=self.owner)
        self.assertTrue(unblock_user(self.worker, actor=actor))
        self.worker.refresh_from_db()
        self.assertTrue(self.worker.is_active)
        self.assertFalse(self.worker.is_blocked)
        self.assertFalse(unblock_user(self.worker, actor=actor))
        resolve_complaint(self.complaint, actor=actor)
        self.complaint.refresh_from_db()
        self.assertEqual(self.complaint.status, Complaint.Status.RESOLVED)
        with self.assertRaises(ValueError):
            dismiss_complaint(self.complaint, actor=actor)
        events = list(ModerationEvent.objects.order_by('pk'))
        self.assertEqual([e.action for e in events], [
            ModerationEvent.Action.BLOCK,
            ModerationEvent.Action.UNBLOCK,
            ModerationEvent.Action.RESOLVE,
        ])
        self.assertTrue(all(e.actor_id == actor.pk for e in events))
        self.assertEqual(events[-1].complaint_id, self.complaint.pk)
        self.assertEqual(Order.objects.get(pk=self.order.pk).address,
                         'PRIVATE_SYNTHETIC_ADDRESS_036')
        self.assertFalse(any(
            field.name in ('email', 'phone', 'address', 'message', 'note')
            for field in ModerationEvent._meta.fields
        ))
        with self.assertRaises(DatabaseError):
            with transaction.atomic():
                ModerationEvent.objects.filter(pk=events[0].pk).update(
                    action=ModerationEvent.Action.DISMISS,
                )
        self.assertEqual(ModerationEvent.objects.count(), 3)

    def test_blocked_response_follows_active_russian_english_hebrew(self):
        self.client.force_login(self.owner)
        get_user_model().objects.filter(pk=self.owner.pk).update(is_blocked=True)
        for code, label in (
            ('ru', 'Аккаунт недоступен.'),
            ('en', 'This account is unavailable.'),
            ('he', 'החשבון אינו זמין.'),
        ):
            with self.subTest(code=code), override(code):
                response = self.client.get(
                    reverse('accounts:client_settings'),
                    HTTP_ACCEPT_LANGUAGE=code,
                )
                self.assertContains(response, label, status_code=403)

    def test_stale_staff_object_cannot_bypass_revoked_database_permission(self):
        actor = self.grant('moderate_accounts')
        self.assertTrue(actor.has_perm('moderation.moderate_accounts'))
        get_user_model().objects.filter(pk=actor.pk).update(is_staff=False)
        with self.assertRaises(PermissionDenied):
            block_user(self.worker, actor=actor)
        self.assertFalse(ModerationEvent.objects.exists())
        self.worker.refresh_from_db()
        self.assertFalse(self.worker.is_blocked)

    def test_blocked_session_can_browse_only_public_catalog(self):
        self.client.force_login(self.owner)
        get_user_model().objects.filter(pk=self.owner.pk).update(is_blocked=True)
        self.assertEqual(self.client.get(reverse('marketplace:home')).status_code, 200)
        self.assertEqual(self.client.get(reverse(
            'marketplace:category_detail', args=[self.category.slug],
        )).status_code, 200)
        self.assertEqual(self.client.get(reverse(
            'marketplace:order_detail', args=[self.order.pk],
        )).status_code, 403)

    def test_no_moderator_can_block_staff_superuser_or_self(self):
        actor = self.grant('moderate_accounts')
        for target in (actor, self.root):
            with self.subTest(target=target.username):
                with self.assertRaises(PermissionDenied):
                    block_user(target, actor=actor)
        with self.assertRaises(PermissionDenied):
            block_user(actor, actor=self.root)
        self.assertFalse(ModerationEvent.objects.exists())

    def test_privacy_review_is_not_export_or_erasure(self):
        actor = self.grant('review_privacy_requests')
        item = review_privacy_request(self.request, actor=actor)
        self.assertEqual(item.status, PrivacyRequest.Status.PROCESSING)
        self.assertIsNotNone(item.reviewed_at)
        with self.assertRaises(ValueError):
            review_privacy_request(item, actor=actor, reject=True)
        self.assertEqual(ModerationEvent.objects.count(), 1)
        event = ModerationEvent.objects.get()
        self.assertEqual(event.action, ModerationEvent.Action.PRIVACY_REVIEW)
        self.assertEqual(event.privacy_request_id, item.pk)
        self.assertEqual(event.actor_id, actor.pk)
        self.assertTrue(get_user_model().objects.filter(pk=self.owner.pk).exists())
        self.assertTrue(Order.objects.filter(pk=self.order.pk).exists())
        other = PrivacyRequest.objects.create(
            user=self.other, kind=PrivacyRequest.Kind.DELETE,
        )
        rejected = review_privacy_request(other, actor=actor, reject=True)
        self.assertEqual(rejected.status, PrivacyRequest.Status.REJECTED)
        self.assertTrue(get_user_model().objects.filter(pk=self.other.pk).exists())
        self.assertEqual(PrivacyRequest.objects.filter(
            status=PrivacyRequest.Status.COMPLETED,
        ).count(), 0)

    def test_role_switch_does_not_grant_moderation(self):
        select_active_role(self.owner, 'worker')
        self.owner.refresh_from_db()
        self.assertFalse(self.owner.is_staff)
        with self.assertRaises(PermissionDenied):
            block_user(self.worker, actor=self.owner)
        self.client.force_login(self.owner)
        self.assertEqual(self.client.post(
            reverse('accounts:switch_role'), {'role': 'admin'},
        ).status_code, 400)
        self.assertEqual(ModerationEvent.objects.count(), 0)

    def test_delete_user_with_history_is_protected(self):
        with self.assertRaises(ProtectedError):
            self.worker.delete()
        with self.assertRaises(ProtectedError):
            self.owner.delete()
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(Response.objects.count(), 1)
        self.assertEqual(Complaint.objects.count(), 1)
        self.assertEqual(PrivacyRequest.objects.count(), 1)

    def test_complaint_owner_set_by_session_not_forged_post_id(self):
        self.client.force_login(self.other)
        url = reverse('moderation:complaint_create') + f'?user={self.owner.pk}'
        self.assertRedirects(self.client.post(url, {
            'reason': Complaint.Reason.SPAM, 'message': 'Synthetic report',
            'reporter': self.root.pk, 'target_user': self.worker.pk,
        }), reverse('marketplace:home'))
        created = Complaint.objects.latest('pk')
        self.assertEqual(created.reporter_id, self.other.pk)
        self.assertEqual(created.target_user_id, self.owner.pk)
        self.assertNotEqual(created.reporter_id, self.root.pk)

    def test_admin_actions_and_status_fields_are_permission_guarded(self):
        site = AdminSite()
        factory = RequestFactory()
        req = factory.get('/admin/')
        req.user = self.staff
        mod = ComplaintAdmin(Complaint, site)
        privacy = PrivacyRequestAdmin(PrivacyRequest, site)
        self.assertNotIn('action_block_target', mod.get_actions(req))
        self.assertNotIn('action_resolve', mod.get_actions(req))
        self.assertNotIn('mark_processing', privacy.get_actions(req))
        req.user = self.grant(
            'moderate_accounts', 'review_complaints', 'review_privacy_requests',
        )
        self.assertIn('action_block_target', mod.get_actions(req))
        self.assertIn('action_resolve', mod.get_actions(req))
        self.assertIn('mark_processing', privacy.get_actions(req))
        self.assertIn('status', privacy.get_readonly_fields(req))
        self.assertIn('admin_note', mod.get_readonly_fields(req))
        user_admin = UserAdmin(get_user_model(), site)
        self.assertFalse(user_admin.has_delete_permission(req))
        self.assertIn('is_blocked', user_admin.get_readonly_fields(req))
        self.assertIn('is_staff', user_admin.get_readonly_fields(req))
        self.assertFalse(user_admin.has_change_permission(req, self.owner))
        for model, admin_class in (
            (Order, OrderAdmin),
            (Response, ResponseAdmin),
            (Rating, RatingAdmin),
        ):
            with self.subTest(model=model.__name__):
                record_admin = admin_class(model, site)
                self.assertFalse(record_admin.has_change_permission(req))
                self.assertFalse(record_admin.has_delete_permission(req))
                self.assertFalse(record_admin.has_add_permission(req))
        audit_admin = ModerationEventAdmin(ModerationEvent, site)
        self.assertFalse(audit_admin.has_add_permission(req))
        self.assertFalse(audit_admin.has_change_permission(req))
        self.assertFalse(audit_admin.has_delete_permission(req))

    def test_admin_changelist_cannot_be_used_by_non_staff(self):
        self.client.force_login(self.owner)
        changelist = reverse('admin:moderation_complaint_changelist')
        self.assertEqual(self.client.post(changelist, {
            'action': 'action_block_target',
            '_selected_action': [self.complaint.pk],
        }).status_code, 302)
        self.worker.refresh_from_db()
        self.assertFalse(self.worker.is_blocked)
        self.assertEqual(ModerationEvent.objects.count(), 0)

    def test_review_permission_does_not_imply_block_permission(self):
        actor = self.grant('review_complaints')
        resolve_complaint(self.complaint, actor=actor)
        with self.assertRaises(PermissionDenied):
            block_user(self.worker, actor=actor)
        self.worker.refresh_from_db()
        self.assertFalse(self.worker.is_blocked)
        self.assertEqual(ModerationEvent.objects.count(), 1)
