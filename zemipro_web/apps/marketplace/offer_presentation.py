"""Only a request's owner sees offer comparisons and real aggregated ratings."""
from decimal import Decimal

from django.db.models import Avg, Count

from apps.accounts.models import WorkerProfile
from .models import Rating, Response
from .offer_ui import offer_copy


def selected_worker_public_name(order):
    """Use the canonical privacy-safe profile projection, never User.__str__."""
    copy = offer_copy()
    if order.worker_id is None:
        return copy['unavailable']
    profile = WorkerProfile.objects.filter(
        user_id=order.worker_id, is_published=True,
    ).first()
    return (profile.public_display_name if profile else '') or copy['unavailable']


OFFER_SORT_CHOICES = ('newest', 'oldest', 'price_asc', 'price_desc', 'rating_desc')
OFFER_STATUS_CHOICES = ('all', 'active', *Response.Status.values)
ACTIVE_OFFER_STATUSES = frozenset({
    Response.Status.PENDING, Response.Status.SENT,
    Response.Status.VIEWED, Response.Status.NEGOTIATING,
})


def validated_offer_options(status_filter, sort):
    """Reject unrecognized filter/sort keys without changing ownership scope."""
    return (
        status_filter if status_filter in OFFER_STATUS_CHOICES else 'all',
        sort if sort in OFFER_SORT_CHOICES else 'newest',
    )


def filter_and_sort_offer_cards(cards, *, status_filter='all', sort='newest'):
    """Owner-only in-memory projection; negotiation prices always sort last."""
    status_filter, sort = validated_offer_options(status_filter, sort)
    if status_filter == 'active':
        cards = [
            card for card in cards if card['response'].status in ACTIVE_OFFER_STATUSES
        ]
    elif status_filter != 'all':
        cards = [card for card in cards if card['response'].status == status_filter]
    if sort == 'newest':
        return sorted(
            cards, key=lambda card: (
                card['response'].created_at, card['response'].pk,
            ), reverse=True,
        )
    if sort == 'oldest':
        return sorted(
            cards, key=lambda card: (
                card['response'].created_at, card['response'].pk,
            ),
        )
    if sort in ('price_asc', 'price_desc'):
        descending = sort == 'price_desc'
        def price_key(card):
            response = card['response']
            value = (
                response.amount_min_ils if response.price_kind in (
                    Response.PriceKind.FIXED, Response.PriceKind.RANGE,
                ) else None
            )
            return (
                value is None,
                (-value if descending else value) if value is not None else Decimal('0'),
                response.pk,
            )
        return sorted(cards, key=price_key)
    # Rating is real aggregate review data; unknown ratings go last.
    return sorted(cards, key=lambda card: (
        card['rating'] is None,
        -card['rating'] if card['rating'] is not None else 0,
        -card['rating_count'],
        card['response'].pk,
    ))


def owner_offer_filter_context(*, status_filter='all', sort='newest'):
    status_filter, sort = validated_offer_options(status_filter, sort)
    copy = offer_copy()
    return {
        'offer_status_selected': status_filter,
        'offer_sort_selected': sort,
        'offer_status_options': [
            {'value': status, 'label': copy.get(status, status)}
            for status in OFFER_STATUS_CHOICES
        ],
        'offer_sort_options': [
            {'value': value, 'label': copy[f'sort_{value}']}
            for value in OFFER_SORT_CHOICES
        ],
    }


def owner_offer_cards(order, responses):
    """Caller must check persisted order ownership before invoking."""
    rows = list(responses)
    worker_ids = {row.worker_id for row in rows}
    profiles = {
        item.user_id: item for item in WorkerProfile.objects.filter(
            user_id__in=worker_ids, is_published=True,
        )
    }
    ratings = {
        row['worker']: row for row in Rating.objects.filter(
            worker_id__in=worker_ids,
        ).values('worker').annotate(
            avg=Avg('rating'), count=Count('pk'),
        )
    }
    copy = offer_copy()
    cards = []
    for response in rows:
        profile = profiles.get(response.worker_id)
        rating = ratings.get(response.worker_id)
        if response.price_kind == response.PriceKind.FIXED:
            price = f'{response.amount_min_ils} ₪'
        elif response.price_kind == response.PriceKind.RANGE:
            price = f'{response.amount_min_ils}–{response.amount_max_ils} ₪'
        elif response.price_kind == response.PriceKind.METHOD:
            price = response.pricing_method
        else:
            price = copy['negotiable']
        cards.append({
            'response': response,
            'worker_name': profile.public_display_name if profile else copy['unavailable'],
            'profile_id': profile.pk if profile else None,
            'price': price,
            'rating': round(rating['avg'], 1) if rating and rating['avg'] is not None else None,
            'rating_count': rating['count'] if rating else 0,
            'status_label': copy.get(response.status, response.status),
        })
    return cards
