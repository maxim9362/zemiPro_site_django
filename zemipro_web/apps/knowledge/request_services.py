"""Stage 14.10 moderated 'recommend a specialist' community domain."""
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.text import slugify

from apps.accounts.client_favorites import public_worker_queryset
from apps.accounts.public_text import prepare_public_text
from apps.marketplace.models import Category

from .models import (
    KnowledgeQAReport, RecommendationRequest, RecommendationRequestReport,
    RecommendationRequestRevision, RecommendationResponse,
    RecommendationResponseRevision,
)
from .qa_services import QAConflict, _active_user, _charge, _text


def _enabled():
    if not getattr(settings, 'ZEMIPRO_RECOMMENDATION_REQUESTS_ENABLED', False):
        raise PermissionDenied('Recommendation requests are not enabled.')


def _moderator(actor):
    user = _active_user(actor)
    if not user.is_staff or not user.has_perm(
        'knowledge.moderate_recommendation_requests',
    ):
        raise PermissionDenied('Recommendation moderator permission required.')
    return user


def _worker(worker_id, category_id, *, lock=True):
    workers = public_worker_queryset()
    if lock:
        workers = workers.select_for_update(of=('self',))
    worker = workers.filter(
        pk=worker_id, city__slug='ashdod', city__is_active=True,
        skills__pk=category_id,
    ).first()
    if worker is None:
        raise PermissionDenied('Professional is unavailable for this category.')
    return worker


def _request_revision(item, actor, action):
    item.content_version += 1
    item.save()
    RecommendationRequestRevision.objects.create(
        request=item, actor=actor, version=item.content_version, action=action,
        status_snapshot=item.status, title=item.title, body=item.body,
    )


def _response_revision(item, actor, action):
    item.content_version += 1
    item.save()
    RecommendationResponseRevision.objects.create(
        response=item, actor=actor, version=item.content_version, action=action,
        status_snapshot=item.status, body=item.body,
    )


def public_requests():
    if not getattr(settings, 'ZEMIPRO_RECOMMENDATION_REQUESTS_ENABLED', False):
        return RecommendationRequest.objects.none()
    return RecommendationRequest.objects.filter(
        status='published', public_content_safe=True,
        approved_version__isnull=False, published_at__isnull=False,
        category__is_active=True, author__is_active=True, author__is_blocked=False,
        author__email_verification_required=False,
    ).select_related('category')


def public_responses(request_item):
    if not getattr(settings, 'ZEMIPRO_RECOMMENDATION_REQUESTS_ENABLED', False):
        return RecommendationResponse.objects.none()
    workers = public_worker_queryset().filter(
        city__slug='ashdod', city__is_active=True,
        skills__pk=request_item.category_id,
    ).values('pk')
    return RecommendationResponse.objects.filter(
        request=request_item, worker_id__in=workers, status='published',
        public_content_safe=True, approved_version__isnull=False,
        published_at__isnull=False, recommender__is_active=True,
        recommender__is_blocked=False,
        recommender__email_verification_required=False,
    ).select_related('worker')


@transaction.atomic
def create_request(*, actor, category_id, language, title, body):
    _enabled()
    user = _active_user(actor)
    category = Category.objects.select_for_update().filter(
        pk=category_id, is_active=True,
    ).first()
    if category is None or language not in ('ru', 'en', 'he'):
        raise QAConflict('Invalid request category or language.')
    title = _text(title, minimum=8, maximum=180, field='request title')
    body = _text(body, minimum=20, maximum=5000, field='request details')
    _charge(user, 'question')
    stem = slugify(title, allow_unicode=True)[:120].strip('-') or 'request'
    item = RecommendationRequest(
        author=user, category=category, language=language,
        slug=f'{stem}-{uuid4().hex[:12]}', title=title, body=body,
    )
    _request_revision(item, user, 'submitted')
    return item


@transaction.atomic
def moderate_request(*, actor, request_id, expected_version, approve, note=''):
    _enabled()
    moderator = _moderator(actor)
    item = RecommendationRequest.objects.select_for_update().filter(pk=request_id).first()
    if item is None:
        raise PermissionDenied('Request is unavailable.')
    if item.author_id == moderator.pk:
        raise PermissionDenied('Cannot moderate own request.')
    if item.content_version != expected_version or item.status != 'pending':
        raise QAConflict('Request is no longer awaiting moderation.')
    now = timezone.now()
    if approve is True:
        title, body = prepare_public_text(item.title), prepare_public_text(item.body)
        if not title or not body:
            raise QAConflict('Request contains unsafe public content.')
        item.public_title, item.public_body = title, body
        item.public_content_safe = True
        item.approved_version = item.content_version + 1
        item.published_at = now
        item.status = 'published'
        action = 'approved'
    elif approve is False:
        if not isinstance(note, str) or len(note.strip()) < 10:
            raise QAConflict('A rejection reason is required.')
        item.status = 'rejected'
        item.public_title = item.public_body = ''
        item.public_content_safe = False
        item.approved_version = None
        item.published_at = None
        action = 'rejected'
    else:
        raise QAConflict('Invalid moderation decision.')
    item.moderated_by = moderator
    item.moderated_at = now
    _request_revision(item, moderator, action)
    return item


@transaction.atomic
def create_response(*, actor, request_id, worker_id, body):
    _enabled()
    user = _active_user(actor)
    item = RecommendationRequest.objects.select_for_update().filter(
        pk=request_id, status='published', public_content_safe=True,
    ).first()
    if item is None:
        raise PermissionDenied('Request is unavailable.')
    if item.author_id == user.pk:
        raise PermissionDenied('Request author cannot answer their own request.')
    worker = _worker(worker_id, item.category_id)
    if worker.user_id == user.pk:
        raise PermissionDenied('Self-promotion is not allowed.')
    body = _text(body, minimum=20, maximum=3000, field='recommendation response')
    _charge(user, 'answer')
    try:
        response = RecommendationResponse(
            request=item, recommender=user, worker=worker, body=body,
        )
        _response_revision(response, user, 'submitted')
    except IntegrityError as exc:
        raise QAConflict('This response or professional was already suggested.') from exc
    return response


@transaction.atomic
def moderate_response(*, actor, response_id, expected_version, approve, note=''):
    _enabled()
    moderator = _moderator(actor)
    request_id = RecommendationResponse.objects.filter(
        pk=response_id,
    ).values_list('request_id', flat=True).first()
    if request_id is None:
        raise PermissionDenied('Response is unavailable.')
    request_item = RecommendationRequest.objects.select_for_update().get(pk=request_id)
    item = RecommendationResponse.objects.select_for_update().filter(
        pk=response_id, request=request_item,
    ).first()
    if item.recommender_id == moderator.pk:
        raise PermissionDenied('Cannot moderate own response.')
    if item.content_version != expected_version or item.status != 'pending':
        raise QAConflict('Response is no longer awaiting moderation.')
    now = timezone.now()
    if approve is True:
        _worker(item.worker_id, request_item.category_id)
        body = prepare_public_text(item.body)
        if not body:
            raise QAConflict('Response contains unsafe public content.')
        item.public_body = body
        item.public_content_safe = True
        item.approved_version = item.content_version + 1
        item.published_at = now
        item.status = 'published'
        action = 'approved'
    elif approve is False:
        if not isinstance(note, str) or len(note.strip()) < 10:
            raise QAConflict('A rejection reason is required.')
        item.status = 'rejected'
        item.public_body = ''
        item.public_content_safe = False
        item.approved_version = None
        item.published_at = None
        action = 'rejected'
    else:
        raise QAConflict('Invalid moderation decision.')
    item.moderated_by = moderator
    item.moderated_at = now
    _response_revision(item, moderator, action)
    return item


@transaction.atomic
def report_content(*, actor, request_id=None, response_id=None, reason, message):
    _enabled()
    user = _active_user(actor)
    if (request_id is None) == (response_id is None):
        raise QAConflict('Choose one report target.')
    if reason not in KnowledgeQAReport.Reason.values:
        raise QAConflict('Invalid report reason.')
    message = _text(message, minimum=10, maximum=2000, field='report details')
    if request_id:
        target = public_requests().select_for_update().filter(pk=request_id).first()
        owner_id = target.author_id if target else None
        kwargs = {'request_id': request_id}
    else:
        target = RecommendationResponse.objects.select_for_update().filter(
            pk=response_id, status='published', public_content_safe=True,
        ).first()
        if target is not None and not public_responses(target.request).filter(
            pk=target.pk,
        ).exists():
            target = None
        owner_id = target.recommender_id if target else None
        kwargs = {'response_id': response_id}
    if target is None:
        raise PermissionDenied('Content is unavailable.')
    if owner_id == user.pk:
        raise PermissionDenied('Cannot report your own content.')
    _charge(user, 'report')
    try:
        return RecommendationRequestReport.objects.create(
            reporter=user, reason=reason, message=message, **kwargs,
        )
    except IntegrityError as exc:
        raise QAConflict('Report already filed.') from exc


@transaction.atomic
def decide_report(*, actor, report_id, remove):
    _enabled()
    moderator = _moderator(actor)
    target = RecommendationRequestReport.objects.filter(pk=report_id).values(
        'request_id', 'response_id',
    ).first()
    if target is None:
        raise PermissionDenied('Report is unavailable.')
    model = RecommendationRequest if target['request_id'] else RecommendationResponse
    content = model.objects.select_for_update().get(
        pk=target['request_id'] or target['response_id'],
    )
    owner_id = (
        content.author_id if isinstance(content, RecommendationRequest)
        else content.recommender_id
    )
    if owner_id == moderator.pk:
        raise PermissionDenied('Cannot decide a report about own content.')
    report = RecommendationRequestReport.objects.select_for_update().get(pk=report_id)
    if report.status != 'pending' or type(remove) is not bool:
        raise QAConflict('Report is already resolved.')
    if remove:
        content.status = 'archived'
        content.public_content_safe = False
        content.approved_version = None
        content.published_at = None
        if isinstance(content, RecommendationRequest):
            content.public_title = ''
            content.public_body = ''
            _request_revision(content, moderator, 'archived')
        else:
            content.public_body = ''
            _response_revision(content, moderator, 'archived')
        report.status = 'removed'
    else:
        report.status = 'dismissed'
    report.handled_by = moderator
    report.handled_at = timezone.now()
    report.save(update_fields=['status', 'handled_by', 'handled_at'])
    return report
