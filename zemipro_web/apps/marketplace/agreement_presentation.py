"""Private agreement rendering for the two authorized order parties."""
from apps.accounts.models import User
from .agreement_services import effective_agreement, pending_agreement
from .models import Order, OrderAgreementVersion, Response
from .offer_ui import offer_copy


def private_agreement_context(order, actor):
    empty = {
        'agreement_current': None, 'agreement_pending': None,
        'agreement_history': [], 'agreement_price': '',
        'agreement_actions': (),
    }
    if (not getattr(actor, 'is_authenticated', False)
            or actor.pk not in (order.client_id, order.worker_id)
            or not User.objects.filter(
                pk=actor.pk, is_active=True, is_blocked=False,
                email_verification_required=False,
            ).exists()
            or order.worker_id is None
            or order.status not in (
                Order.Status.ASSIGNED, Order.Status.IN_PROGRESS,
                Order.Status.COMPLETED, Order.Status.CANCELLED,
                Order.Status.DISPUTED,
            )):
        return empty
    active = effective_agreement(order)
    if active is None:
        return empty
    pending = pending_agreement(order)
    copy = offer_copy()
    def describe_price(version):
        if version.price_kind == Response.PriceKind.FIXED:
            return f'{version.amount_min_ils} ₪'
        if version.price_kind == Response.PriceKind.RANGE:
            return f'{version.amount_min_ils}–{version.amount_max_ils} ₪'
        if version.price_kind == Response.PriceKind.METHOD:
            return version.pricing_method
        return copy['negotiable']
    history = []
    for entry in OrderAgreementVersion.objects.filter(order=order).select_related(
        'decision',
    ).order_by('-number'):
        decision = entry.decision if hasattr(entry, 'decision') else None
        history.append({
            'number': entry.number, 'price': describe_price(entry),
            'terms': entry.terms, 'estimated_timeline': entry.estimated_timeline,
            'proposed_at': entry.proposed_at, 'decided_at': (
                decision.decided_at if decision else None
            ),
            'proposer': (
                copy['client_party'] if entry.proposed_by_id == order.client_id
                else copy['worker_party']
            ),
            'decision': copy.get(
                decision.result, decision.result,
            ) if decision else copy['pending_agreement'],
        })
    return {
        'agreement_current': active, 'agreement_pending': pending,
        'agreement_history': history, 'agreement_price': describe_price(active),
        'agreement_actions': (
            ('accept', copy['accept_change']), ('reject', copy['reject_change']),
        ), 'can_change_agreement': order.status in (
            Order.Status.ASSIGNED, Order.Status.IN_PROGRESS,
            Order.Status.DISPUTED,
        ),
    }
