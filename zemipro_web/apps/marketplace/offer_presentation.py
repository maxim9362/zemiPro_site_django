"""Only a request's owner sees offer comparisons and real aggregated ratings."""
from django.db.models import Avg, Count

from apps.accounts.models import WorkerProfile
from .models import Rating
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
