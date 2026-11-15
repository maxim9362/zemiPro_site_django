"""Stage 14.8 personal recommendations, distinct from verified order reviews."""
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.client_favorites import public_worker_queryset

from .models import (
    KnowledgeQAReport, PersonalRecommendation, PersonalRecommendationReport,
    PersonalRecommendationRevision,
)
from .qa_services import QAConflict, _active_user, _charge, _text


def _enabled():
    if not getattr(settings, 'ZEMIPRO_PERSONAL_RECOMMENDATIONS_ENABLED', False):
        raise PermissionDenied('Personal recommendations are not enabled.')


def _moderator(actor):
    user = _active_user(actor)
    if not user.is_staff or not user.has_perm(
        'knowledge.moderate_personal_recommendations',
    ):
        raise PermissionDenied('Recommendation moderator permission required.')
    return user


def _worker(worker_id, *, lock=True):
    workers = public_worker_queryset()
    if lock:
        workers = workers.select_for_update()
    worker = workers.filter(
        pk=worker_id, city__slug='ashdod', city__is_active=True,
    ).first()
    if worker is None:
        raise PermissionDenied('Professional is unavailable.')
    return worker


def _revision(item, actor, action):
    item.content_version += 1
    item.save()
    PersonalRecommendationRevision.objects.create(
        recommendation=item, actor=actor, version=item.content_version,
        action=action, status_snapshot=item.status, body=item.body,
    )


def _hide(item):
    item.public_body = ''
    item.public_content_safe = False
    item.approved_version = None
    item.published_at = None


def public_recommendations(*, worker_id=None):
    if not getattr(settings, 'ZEMIPRO_PERSONAL_RECOMMENDATIONS_ENABLED', False):
        return PersonalRecommendation.objects.none()
    worker_ids = public_worker_queryset().filter(
        city__slug='ashdod', city__is_active=True,
    ).values('pk')
    result = PersonalRecommendation.objects.filter(
        worker_id__in=worker_ids, status=PersonalRecommendation.Status.PUBLISHED,
        public_content_safe=True, approved_version__isnull=False,
        published_at__isnull=False, experience_confirmed_at__isnull=False,
        author__is_active=True, author__is_blocked=False,
        author__email_verification_required=False,
    ).select_related('worker')
    return result.filter(worker_id=worker_id) if worker_id else result


@transaction.atomic
def create_recommendation(*, actor, worker_id, language, body,
                          experience_confirmed=False):
    _enabled()
    user = _active_user(actor)
    worker = _worker(worker_id)
    if worker.user_id == user.pk:
        raise PermissionDenied('Self-recommendation is not allowed.')
    if language not in ('ru', 'en', 'he') or experience_confirmed is not True:
        raise QAConflict('Confirm real personal experience and language.')
    body = _text(body, minimum=30, maximum=4000, field='recommendation')
    _charge(user, 'question')
    try:
        item = PersonalRecommendation(
            author=user, worker=worker, language=language, body=body,
            experience_confirmed_at=timezone.now(),
        )
        _revision(item, user, 'created')
    except IntegrityError as exc:
        raise QAConflict('You already recommended this professional.') from exc
    return item


@transaction.atomic
def edit_recommendation(*, actor, recommendation_id, expected_version, body,
                        experience_confirmed=False):
    _enabled()
    user = _active_user(actor)
    item = PersonalRecommendation.objects.select_for_update().filter(
        pk=recommendation_id,
    ).first()
    if item is None or item.author_id != user.pk:
        raise PermissionDenied('Recommendation is unavailable.')
    if item.content_version != expected_version or item.status not in (
        PersonalRecommendation.Status.DRAFT, PersonalRecommendation.Status.REJECTED,
    ):
        raise QAConflict('Recommendation changed or cannot be edited.')
    if experience_confirmed is not True:
        raise QAConflict('Confirm real personal experience.')
    item.body = _text(body, minimum=30, maximum=4000, field='recommendation')
    item.experience_confirmed_at = timezone.now()
    item.status = PersonalRecommendation.Status.DRAFT
    _hide(item)
    _charge(user, 'edit')
    _revision(item, user, 'edited')
    return item


@transaction.atomic
def submit_recommendation(*, actor, recommendation_id, expected_version):
    _enabled()
    user = _active_user(actor)
    item = PersonalRecommendation.objects.select_for_update().filter(
        pk=recommendation_id,
    ).first()
    if item is None or item.author_id != user.pk:
        raise PermissionDenied('Recommendation is unavailable.')
    if item.content_version != expected_version or item.status not in (
        PersonalRecommendation.Status.DRAFT, PersonalRecommendation.Status.REJECTED,
    ):
        raise QAConflict('Recommendation changed or cannot be submitted.')
    if item.experience_confirmed_at is None:
        raise QAConflict('Personal experience confirmation is required.')
    _worker(item.worker_id)
    _text(item.body, minimum=30, maximum=4000, field='recommendation')
    item.status = PersonalRecommendation.Status.PENDING
    item.submitted_at = timezone.now()
    _hide(item)
    _revision(item, user, 'submitted')
    return item


@transaction.atomic
def moderate_recommendation(*, actor, recommendation_id, expected_version,
                            approve, note=''):
    _enabled()
    moderator = _moderator(actor)
    item = PersonalRecommendation.objects.select_for_update().filter(
        pk=recommendation_id,
    ).first()
    if item is None:
        raise PermissionDenied('Recommendation is unavailable.')
    if item.author_id == moderator.pk:
        raise PermissionDenied('Cannot moderate own recommendation.')
    if item.content_version != expected_version or item.status != 'pending':
        raise QAConflict('Recommendation is no longer awaiting moderation.')
    if type(approve) is not bool:
        raise QAConflict('Invalid moderation decision.')
    now = timezone.now()
    if approve:
        _worker(item.worker_id)
        from apps.accounts.public_text import prepare_public_text
        body = prepare_public_text(item.body)
        if not body:
            raise QAConflict('Recommendation contains unsafe public content.')
        item.public_body = body
        item.public_content_safe = True
        item.approved_version = item.content_version + 1
        item.published_at = now
        item.status = PersonalRecommendation.Status.PUBLISHED
        action = 'approved'
    else:
        if not isinstance(note, str) or len(note.strip()) < 10:
            raise QAConflict('A rejection reason is required.')
        item.status = PersonalRecommendation.Status.REJECTED
        _hide(item)
        action = 'rejected'
    item.moderated_by = moderator
    item.moderated_at = now
    _revision(item, moderator, action)
    return item


@transaction.atomic
def report_recommendation(*, actor, recommendation_id, reason, message):
    _enabled()
    user = _active_user(actor)
    item = public_recommendations().select_for_update().filter(
        pk=recommendation_id,
    ).first()
    if item is None:
        raise PermissionDenied('Recommendation is unavailable.')
    if item.author_id == user.pk or item.worker.user_id == user.pk:
        raise PermissionDenied('Cannot report your own related recommendation.')
    if reason not in KnowledgeQAReport.Reason.values:
        raise QAConflict('Invalid report reason.')
    message = _text(message, minimum=10, maximum=2000, field='report details')
    _charge(user, 'report')
    try:
        return PersonalRecommendationReport.objects.create(
            recommendation=item, reporter=user, reason=reason, message=message,
        )
    except IntegrityError as exc:
        raise QAConflict('Report already filed.') from exc
