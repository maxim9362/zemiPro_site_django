"""Stage 05.4: private, transactional invitations to EXISTING orders.

Order creation, worker responses and assignment remain the Stage 04 services.
An invitation cannot assign a worker or grant access to private order fields.
"""
from datetime import timedelta

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.accounts.client_favorites import public_worker_queryset
from apps.accounts.models import User, WorkerProfile
from apps.notifications.services import create_notification
from apps.locations.services import get_public_cities

from .invitation_ui import invitation_copy
from .models import Order, OrderInvitation, Response
from .order_management import owner_order
from .order_quota import consume_order_quota
from .services import create_response, workers_serving_city

MAX_ORDER_INVITATIONS = 5
MAX_WORKER_INVITATIONS_PER_DAY = 10
INVITATION_LIFETIME = timedelta(days=7)


class InvitationConflict(ValueError):
    """Safe error without order data, personal contacts or worker identity."""


def worker_matches_order(worker_id, order):
    """Reuse the Stage 05.2 SQL matcher and publication gate, never trust form IDs."""
    if (order.status != Order.Status.PUBLISHED or order.worker_id is not None
            or order.city_id is None):
        return False
    mode = order.work_mode if order.work_mode in ('onsite', 'online') else None
    workers = workers_serving_city(
        public_worker_queryset(), order.city, category=order.category,
        service=order.subcategory, mode=mode,
    ).exclude(availability=WorkerProfile.Availability.UNAVAILABLE)
    return workers.filter(pk=worker_id).exists()


def invitable_orders(user, worker, *, limit=40):
    """Bounded owner-only order picker; each option is revalidated on POST."""
    if (not user.is_authenticated or not User.objects.filter(
        pk=user.pk, is_active=True, is_blocked=False,
        email_verification_required=False,
    ).exists()):
        return []
    orders = Order.objects.filter(
        client_id=user.pk, worker__isnull=True, status=Order.Status.PUBLISHED,
        city__in=get_public_cities(), category__in=worker.skills.all(),
    ).filter(
        Q(subcategory__isnull=True) | Q(subcategory__in=worker.services.all()),
    ).select_related('city', 'category', 'subcategory').order_by('-created_at', '-pk')[:limit]
    return [order for order in orders if worker_matches_order(worker.pk, order)]


def _notice(recipient, key, order, *, title_key='notice_state_title'):
    c = invitation_copy(getattr(recipient, 'preferred_language', 'ru'))
    create_notification(
        recipient=recipient, title=c[title_key],
        message=c[key].format(number=order.pk),
        notification_type='system', related_order=order,
    )


@transaction.atomic
def create_invitation(*, actor, order_id, worker_id):
    """Lock order first, then worker. Unique(order, worker) protects racing taps."""
    order = owner_order(order_id, actor, lock=True)
    if order.status != Order.Status.PUBLISHED or order.worker_id is not None:
        raise InvitationConflict('Order no longer accepts invitations.')
    worker = WorkerProfile.objects.select_for_update().select_related('user').filter(
        pk=worker_id,
    ).first()
    if worker is None:
        raise InvitationConflict('Worker is unavailable.')
    if worker.user_id == actor.pk:
        raise PermissionDenied('Cannot invite yourself.')
    existing = OrderInvitation.objects.filter(order=order, worker=worker).first()
    if existing is not None:
        return existing, False
    if not worker_matches_order(worker.pk, order):
        raise InvitationConflict('Service or region does not match.')
    if Response.objects.filter(order=order, worker_id=worker.user_id).exists():
        raise InvitationConflict('Worker has already responded.')
    # Quota row serializes concurrent invitations by this customer, including
    # invitations to different orders and worker profiles.
    consume_order_quota(actor, 'invite')
    if OrderInvitation.objects.filter(order=order).count() >= MAX_ORDER_INVITATIONS:
        raise InvitationConflict('Order invitation limit reached.')
    if OrderInvitation.objects.filter(
        worker=worker, created_at__gte=timezone.now() - timedelta(days=1),
    ).count() >= MAX_WORKER_INVITATIONS_PER_DAY:
        raise InvitationConflict('Specialist invitation limit reached.')
    invitation = OrderInvitation.objects.create(
        order=order, client_id=actor.pk, worker=worker,
        expires_at=timezone.now() + INVITATION_LIFETIME,
    )
    _notice(worker.user, 'notice_received', order, title_key='notice_title')
    return invitation, True


@transaction.atomic
def act_on_invitation(*, actor, invitation_id, action):
    """Only client withdraws; only invited specialist accepts or declines.

    Lock order before invitation, mirroring the Stage 04 response lifecycle.
    Failed/duplicate transitions do not create a second response/notification.
    """
    if action not in ('accept', 'decline', 'withdraw'):
        raise InvitationConflict('Unknown action.')
    if not getattr(actor, 'is_authenticated', False):
        raise PermissionDenied('Login required.')
    order_id = OrderInvitation.objects.filter(pk=invitation_id).values_list(
        'order_id', flat=True,
    ).first()
    if order_id is None:
        raise PermissionDenied('Invitation unavailable.')
    order = Order.objects.select_for_update().select_related(
        'category', 'subcategory', 'city',
    ).get(pk=order_id)
    invite = OrderInvitation.objects.select_for_update().select_related(
        'worker__user', 'order', 'client',
    ).get(pk=invitation_id, order=order)
    if (not User.objects.filter(
        pk=actor.pk, is_active=True, is_blocked=False,
        email_verification_required=False,
    ).exists()):
        raise PermissionDenied('Account unavailable.')
    if action == 'withdraw':
        if order.client_id != actor.pk or invite.client_id != actor.pk:
            raise PermissionDenied('Not your invitation.')
    elif invite.worker.user_id != actor.pk:
        raise PermissionDenied('Not your invitation.')

    target = {
        'accept': OrderInvitation.Status.ACCEPTED,
        'decline': OrderInvitation.Status.DECLINED,
        'withdraw': OrderInvitation.Status.WITHDRAWN,
    }[action]
    if invite.status == target:
        return invite, False
    if invite.status != OrderInvitation.Status.PENDING:
        raise InvitationConflict('Invitation was already resolved.')
    current = invite.effective_status
    if current == OrderInvitation.Status.PENDING and not worker_matches_order(
        invite.worker_id, order,
    ):
        current = OrderInvitation.Status.UNAVAILABLE
    if current != OrderInvitation.Status.PENDING:
        invite.status = current
        invite.save(update_fields=['status', 'updated_at'])
        return invite, False
    if action == 'accept':
        response = Response.objects.filter(
            order=order, worker_id=actor.pk,
        ).first()
        if response is None:
            create_response(order, actor, message='')
            _notice(order.client, 'notice_received', order, title_key='notice_state_title')
        elif response.status != Response.Status.PENDING:
            raise InvitationConflict('Existing response no longer eligible.')
    invite.status = target
    invite.save(update_fields=['status', 'updated_at'])
    if action == 'decline':
        _notice(order.client, 'notice_declined', order)
    elif action == 'withdraw':
        _notice(invite.worker.user, 'notice_withdrawn', order)
    return invite, True
