"""Stage 05.3 — explainable, deterministic organic directory ranking.

The score is a relevance score, NEVER a user rating, quality guarantee, paid
position or claimed experience. Only public, persisted facts contribute.
No profile editing, order transitions or third-party search engine is involved.

Algorithm v1 (points; order for ties: real review count, profile PK):
* explicitly requested service +40; category +25; matched keyword +8..16
* service in chosen area +10..17, remote-only match +6
* self-reported available +12, limited +6, unavailable +0
* profile fields: explicit services +4, public portfolio +2,
  optional numeric starting price +2, working hours +2
* genuine stored reviews: 1–2 -> max 5, 3+ -> max 10
"""
import logging

from django.db.models import (
    Case, Exists, F, IntegerField, OuterRef, Q, Value, When,
)
from django.utils.translation import gettext as _

from apps.accounts.models import WorkerPortfolioPhoto, WorkerProfile

RANKING_VERSION = 'directory-v1'
LOGGER = logging.getLogger('zemipro')


def _constant(value):
    return Value(value, output_field=IntegerField())


def _score_when(*cases):
    return Case(*cases, default=_constant(0), output_field=IntegerField())


def add_directory_scores(workers, *, category, service, query, city,
                         neighborhood, mode):
    """Annotate one PostgreSQL QuerySet without a per-worker SQL loop."""
    workers = workers.annotate(
        rank_service=_constant(40 if service else 25 if category else 0),
    )

    if query:
        # Alias names are created only by the keyword filter in directory_search.
        keyword = _score_when(
            When(searchable_display_name__icontains=query, then=_constant(16)),
            When(_search_service_text=True, then=_constant(12)),
            When(_search_category_text=True, then=_constant(8)),
        )
    else:
        keyword = _constant(0)
    workers = workers.annotate(rank_keyword=keyword)

    if city is None:
        zone = _constant(0)
    elif mode == 'online' or (
        (service is not None and service.work_mode == 'online')
        or (service is None and category is not None
            and category.work_mode == 'online')
    ):
        zone = _constant(6)
    else:
        zones = WorkerProfile.service_cities.through.objects.filter(
            workerprofile_id=OuterRef('pk'),
        )
        workers = workers.alias(
            _ranking_any_zone=Exists(zones),
            _ranking_selected_city=Exists(zones.filter(city_id=city.pk)),
        )
        if neighborhood is not None:
            areas = WorkerProfile.service_neighborhoods.through.objects.filter(
                workerprofile_id=OuterRef('pk'),
                neighborhood__city_id=city.pk,
            )
            workers = workers.alias(
                _ranking_area_restricted=Exists(areas),
                _ranking_selected_area=Exists(areas.filter(
                    neighborhood_id=neighborhood.pk,
                )),
            )
            local_zone = _score_when(
                When(_ranking_selected_area=True, then=_constant(17)),
                When(_ranking_selected_city=True,
                     _ranking_area_restricted=False, then=_constant(14)),
                When(_ranking_any_zone=False, city_id=city.pk,
                     _ranking_area_restricted=False, then=_constant(10)),
            )
        else:
            local_zone = _score_when(
                When(_ranking_selected_city=True, then=_constant(14)),
                When(_ranking_any_zone=False, city_id=city.pk,
                     then=_constant(10)),
            )
        # A profile outside the onsite area may still be a legitimate online
        # match when no mode was selected. Do not award an onsite-zone score.
        if mode == 'onsite':
            zone = local_zone
        else:
            zone = Case(
                When(Q(_ranking_selected_city=True) |
                     Q(_ranking_any_zone=False, city_id=city.pk),
                     then=local_zone),
                When(offers_remote=True, then=_constant(6)),
                default=_constant(0), output_field=IntegerField(),
            )
            if neighborhood is not None:
                # An explicitly configured OTHER neighborhood must not receive
                # a city-local bonus just because the city is served.
                zone = _score_when(
                    When(_ranking_selected_area=True, then=_constant(17)),
                    When(_ranking_selected_city=True,
                         _ranking_area_restricted=False, then=_constant(14)),
                    When(_ranking_any_zone=False, city_id=city.pk,
                         _ranking_area_restricted=False,
                         then=_constant(10)),
                    When(offers_remote=True, then=_constant(6)),
                )
    workers = workers.annotate(rank_zone=zone)

    workers = workers.annotate(
        rank_availability=_score_when(
            When(availability=WorkerProfile.Availability.AVAILABLE,
                 then=_constant(12)),
            When(availability=WorkerProfile.Availability.LIMITED,
                 then=_constant(6)),
        ),
    )

    explicit_services = WorkerProfile.services.through.objects.filter(
        workerprofile_id=OuterRef('pk'), subcategory__is_active=True,
        subcategory__category__is_active=True,
    ).filter(
        Q(subcategory__category__section__isnull=True)
        | Q(subcategory__category__section__is_active=True)
    )
    photo = WorkerPortfolioPhoto.objects.filter(
        worker_id=OuterRef('pk'), is_public=True,
    )
    workers = workers.alias(
        _ranking_has_explicit_service=Exists(explicit_services),
        _ranking_has_public_photo=Exists(photo),
    )
    workers = workers.annotate(
        rank_profile=(
            _score_when(
                When(_ranking_has_explicit_service=True, then=_constant(4)),
            )
            + _score_when(
                When(_ranking_has_public_photo=True, then=_constant(2)),
            )
            + _score_when(
                When(starting_price_ils__isnull=False, then=_constant(2)),
            )
            + _score_when(
                When(~Q(working_hours=''), then=_constant(2)),
            )
        ),
    )

    # Both count and rating are based on actual Rating rows, already annotated
    # in directory_search. A worker without reviews is NEVER given 5 stars.
    workers = workers.annotate(
        rank_reviews=_score_when(
            When(review_count__gte=3, avg_rating__gte=4, then=_constant(10)),
            When(review_count__gte=3, avg_rating__gte=3, then=_constant(7)),
            When(review_count__gte=3, then=_constant(4)),
            When(review_count__gte=1, avg_rating__gte=4, then=_constant(5)),
            When(review_count__gte=1, then=_constant(2)),
        ),
    )
    return workers.annotate(
        rank_score=(
            F('rank_service') + F('rank_keyword') + F('rank_zone')
            + F('rank_availability') + F('rank_profile') + F('rank_reviews')
        ),
    )


def explain_public_rank(worker, *, category=None, service=None, query='',
                        city=None):
    """Per-page explanation using *only* selected public facts and annotations.

    Returns short stable codes for the audit log and localized descriptions for
    UI. No raw query, description, phone, address or user identity is returned.
    """
    reasons = []
    if service and worker.rank_service:
        reasons.append(('service', _('Указана выбранная услуга')))
    elif category and worker.rank_service:
        reasons.append(('category', _('Работает по выбранной категории')))
    if query and worker.rank_keyword:
        reasons.append(('keyword', _('Совпадение по поисковому запросу')))
    if city and worker.rank_zone >= 10:
        reasons.append(('local_area', _('Обслуживает выбранную зону')))
    elif city and worker.rank_zone == 6:
        reasons.append(('remote', _('Предлагает подходящую онлайн-услугу')))
    if worker.availability == WorkerProfile.Availability.AVAILABLE:
        reasons.append(('available', _('Принимает заявки по данным анкеты')))
    elif worker.availability == WorkerProfile.Availability.LIMITED:
        reasons.append(('limited', _('Ограниченная доступность по данным анкеты')))
    if worker.rank_profile:
        reasons.append(('profile', _('Указаны дополнительные сведения об услугах')))
    if worker.review_count:
        reasons.append(('reviews', _('Есть отзывы пользователей')))
    return reasons


def ranking_audit_rows(page, *, params, city):
    """Bounded, privacy-safe journal entries for this *paginated* response."""
    if not params or (params['sort'] or 'relevance') != 'relevance':
        return []
    entries = []
    for position, worker in enumerate(page.object_list, 1):
        reasons = explain_public_rank(
            worker, category=params['category'], service=params['service'],
            query=params['q'], city=city,
        )
        worker.rank_reasons = [message for _, message in reasons]
        entries.append({
            'worker_profile_id': worker.pk,  # Public card ID, not user ID.
            'position': (page.number - 1) * page.paginator.per_page + position,
            'score': worker.rank_score,
            'service': worker.rank_service,
            'keyword': worker.rank_keyword,
            'area': worker.rank_zone,
            'availability': worker.rank_availability,
            'profile': worker.rank_profile,
            'reviews': worker.rank_reviews,
            'reasons': [code for code, _ in reasons],
        })
    if entries:
        LOGGER.info(
            'directory_ranking_page',
            extra={
                'ranking_version': RANKING_VERSION,
                'ranking_sort': 'relevance',
                'ranking_rows': entries,
            },
        )
    return entries
