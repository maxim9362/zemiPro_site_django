"""14.4 — opt-in pilot admission; not a public-launch switch or GO decision.

No access to source articles, user contacts or unapproved materials is exposed.
All actions are server-authorized, versioned and journaled in PostgreSQL.
"""
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone

from apps.accounts.client_favorites import public_worker_queryset
from apps.marketplace.models import Category, Subcategory

from .models import (
    ArticlePilotAudit, ArticlePilotEnrollment, ArticlePilotSelection,
    ExpertArticle, ExpertArticleDecision, ExpertArticleImage,
    ExpertArticleReport,
)
from .services import ArticleConflict, _active_user, _author, _moderator


CONSENT_VERSION = 1
MAX_ARTICLES = 20
MAX_AUTHORS = 6
MAX_CATEGORIES = 4


def _authoring_gate():
    if not settings.ZEMIPRO_KNOWLEDGE_AUTHORING_ENABLED:
        raise PermissionDenied('Article pilot authoring is disabled.')


@transaction.atomic
def consent_to_pilot(actor, *, confirmed=False):
    """Only the owner of an eligible published Ashdod profile may opt in."""
    _authoring_gate()
    if confirmed is not True:
        raise ArticleConflict('Explicit consent is required.')
    user, worker = _author(actor)
    now = timezone.now()
    record = ArticlePilotEnrollment.objects.select_for_update().filter(
        worker=worker,
    ).first()
    if record is not None and record.revoked_at is None:
        if record.accepted_by_id == user.pk and record.consent_version == CONSENT_VERSION:
            return record, False
        raise ArticleConflict('Consent must be renewed by the author.')
    if record is None:
        record = ArticlePilotEnrollment.objects.create(
            worker=worker, accepted_by=user, consent_version=CONSENT_VERSION,
            consented_at=now,
        )
    else:
        record.accepted_by = user
        record.consent_version = CONSENT_VERSION
        record.consented_at = now
        record.revoked_at = None
        record.save(update_fields=[
            'accepted_by', 'consent_version', 'consented_at', 'revoked_at',
            'updated_at',
        ])
    ArticlePilotAudit.objects.create(
        worker=worker, actor=user, action=ArticlePilotAudit.Action.CONSENTED,
    )
    return record, True


@transaction.atomic
def withdraw_from_pilot(actor):
    """Immediate opt-out even if authoring or profile publication was disabled."""
    user = _active_user(actor)
    from apps.accounts.models import WorkerProfile
    worker = WorkerProfile.objects.select_for_update().filter(user_id=user.pk).first()
    if worker is None:
        return False
    record = ArticlePilotEnrollment.objects.select_for_update().filter(
        worker=worker, revoked_at__isnull=True,
    ).first()
    if record is None:
        return False
    now = timezone.now()
    selections = list(
        ArticlePilotSelection.objects.select_for_update().select_related('article')
        .filter(article__author=worker, revoked_at__isnull=True)
        .order_by('article_id'),
    )
    for selection in selections:
        selection.revoked_at = now
        selection.save(update_fields=['revoked_at', 'updated_at'])
        ArticlePilotAudit.objects.create(
            worker=worker, article=selection.article, actor=user,
            action=ArticlePilotAudit.Action.DESELECTED,
            content_version=selection.approved_version,
        )
    record.revoked_at = now
    record.save(update_fields=['revoked_at', 'updated_at'])
    ArticlePilotAudit.objects.create(
        worker=worker, actor=user, action=ArticlePilotAudit.Action.WITHDRAWN,
    )
    return True


def pilot_author_status(actor):
    """Every profile owner can see and withdraw consent, even after closure."""
    user = _active_user(actor, lock=False)
    from apps.accounts.models import WorkerProfile
    worker = WorkerProfile.objects.filter(user_id=user.pk).first()
    if worker is None:
        raise PermissionDenied('Pilot author is unavailable.')
    return ArticlePilotEnrollment.objects.filter(worker=worker).first()


def _moderator_read(actor):
    # Consent/selection can be managed while authoring is open but public
    # reading is disabled. It does not grant any release or Q&A permission.
    # Staff must retain access to revoke pilot admission after a global
    # emergency stop. It is a strictly private permissioned view.
    user = _active_user(actor, lock=False)
    if not user.is_staff or not user.has_perm('knowledge.moderate_expert_articles'):
        raise PermissionDenied('Pilot reviewer permission required.')
    return user


def selection_candidates(actor):
    _moderator_read(actor)
    return (
        ExpertArticle.objects.filter(
            status=ExpertArticle.Status.PUBLISHED,
            public_content_safe=True,
            category__is_active=True,
            author__knowledge_pilot_enrollment__revoked_at__isnull=True,
            author__knowledge_pilot_enrollment__consent_version=CONSENT_VERSION,
        ).select_related('author', 'category').order_by('-moderated_at', '-pk')[:80]
    )


def _eligibility(article):
    if (article.status != ExpertArticle.Status.PUBLISHED
            or not article.public_content_safe
            or article.approved_version != article.content_version
            or article.moderated_by_id is None
            or article.rights_confirmed_at is None):
        raise ArticleConflict('Article is not currently approved.')
    if not ExpertArticleDecision.objects.filter(
        article=article, version=article.content_version,
        kind=ExpertArticleDecision.Kind.APPROVE,
    ).exists():
        raise ArticleConflict('Missing moderator decision.')
    if not public_worker_queryset().filter(
        pk=article.author_id, city__slug='ashdod', skills__pk=article.category_id,
    ).exists():
        raise ArticleConflict('Author is not publicly eligible.')
    category = Category.objects.filter(
        pk=article.category_id, is_active=True,
    ).filter(
        Q(section__isnull=True) |
        __import__('django').db.models.Q(section__is_active=True),
    ).first()
    if category is None:
        raise ArticleConflict('Category is no longer available.')
    if article.subcategory_id and not Subcategory.objects.filter(
        pk=article.subcategory_id, category_id=category.pk, is_active=True,
    ).exists():
        raise ArticleConflict('Service is no longer available.')
    images = ExpertArticleImage.objects.filter(article=article)
    if images.exclude(
        approved_version=article.content_version,
    ).exists() or images.filter(rights_confirmed_at__isnull=True).exists():
        raise ArticleConflict('Article has unapproved images.')


@transaction.atomic
def select_for_pilot(actor, *, article_id, expected_version):
    _authoring_gate()
    reviewer = _moderator(actor)
    article = ExpertArticle.objects.select_for_update().select_related(
        'author',
    ).filter(pk=article_id).first()
    if article is None:
        raise PermissionDenied('Article not available.')
    # Serialize global quota checks across separate article transactions.
    with connection.cursor() as cursor:
        cursor.execute('SELECT pg_advisory_xact_lock(%s)', [1404001])
    if article.author.user_id == reviewer.pk:
        raise PermissionDenied('Cannot select own article.')
    if type(expected_version) is not int or article.content_version != expected_version:
        raise ArticleConflict('Article version changed.')
    _eligibility(article)
    enrollment = ArticlePilotEnrollment.objects.select_for_update().filter(
        worker_id=article.author_id, revoked_at__isnull=True,
        consent_version=CONSENT_VERSION, accepted_by_id=article.author.user_id,
    ).first()
    if enrollment is None:
        raise ArticleConflict('Author has not opted in.')
    selected = ArticlePilotSelection.objects.select_for_update().filter(
        article=article,
    ).first()
    if (selected is not None and selected.revoked_at is None
            and selected.approved_version == article.content_version):
        return selected, False

    # Hold the selected article row while checking limits. All editors of this
    # pilot are serialized through the unique active article selection lock.
    active = ArticlePilotSelection.objects.filter(
        revoked_at__isnull=True, approved_version__gt=0,
    )
    if active.count() >= MAX_ARTICLES:
        raise ArticleConflict('Pilot capacity reached.')
    if (not active.filter(article__author_id=article.author_id).exists()
            and active.values('article__author_id').distinct().count() >= MAX_AUTHORS):
        raise ArticleConflict('Pilot author capacity reached.')
    if (not active.filter(article__category_id=article.category_id).exists()
            and active.values('article__category_id').distinct().count() >= MAX_CATEGORIES):
        raise ArticleConflict('Pilot category capacity reached.')
    now = timezone.now()
    if selected is None:
        selected = ArticlePilotSelection.objects.create(
            article=article, selected_by=reviewer, selected_at=now,
            approved_version=article.content_version,
        )
    else:
        selected.selected_by = reviewer
        selected.selected_at = now
        selected.approved_version = article.content_version
        selected.revoked_at = None
        selected.save(update_fields=[
            'selected_by', 'selected_at', 'approved_version', 'revoked_at', 'updated_at',
        ])
    ArticlePilotAudit.objects.create(
        worker_id=article.author_id, article=article, actor=reviewer,
        action=ArticlePilotAudit.Action.SELECTED,
        content_version=article.content_version,
    )
    return selected, True


@transaction.atomic
def deselect_from_pilot(actor, *, article_id):
    # Emergency removal must remain possible while authoring is paused.
    reviewer = _moderator_read(actor)
    article = ExpertArticle.objects.select_for_update().filter(pk=article_id).first()
    if article is None:
        raise PermissionDenied('Article is unavailable.')
    selection = ArticlePilotSelection.objects.select_for_update().filter(
        article=article, revoked_at__isnull=True,
    ).first()
    if selection is None:
        return False
    selection.revoked_at = timezone.now()
    selection.save(update_fields=['revoked_at', 'updated_at'])
    ArticlePilotAudit.objects.create(
        worker_id=article.author_id, article=article, actor=reviewer,
        action=ArticlePilotAudit.Action.DESELECTED,
        content_version=selection.approved_version,
    )
    return True


def pilot_readiness(actor):
    """Staff-only, factual counts. An automated result can NEVER be Q&A GO."""
    _moderator_read(actor)
    enrollments = ArticlePilotEnrollment.objects.filter(
        revoked_at__isnull=True, consent_version=CONSENT_VERSION,
    )
    selected = ArticlePilotSelection.objects.filter(
        revoked_at__isnull=True,
        approved_version__gt=0,
        article__status=ExpertArticle.Status.PUBLISHED,
    )
    counts = {
        'consenting_authors': enrollments.count(),
        'selected_articles': selected.count(),
        'selected_categories': selected.values('article__category_id').distinct().count(),
        'published_views_available': bool(settings.ZEMIPRO_KNOWLEDGE_ARTICLES_ENABLED),
        'metrics_enabled': bool(
            getattr(settings, 'ZEMIPRO_KNOWLEDGE_PILOT_METRICS_ENABLED', False),
        ),
    }
    from .pilot_metrics import pilot_summary
    counts.update(pilot_summary())
    counts['moderation_decisions'] = ExpertArticleDecision.objects.count()
    counts['pending_reports'] = ExpertArticleReport.objects.filter(
        status=ExpertArticleReport.Status.PENDING,
    ).count()
    counts['owner_qa_decision'] = 'PENDING'
    counts['real_pilot_verified'] = False  # manual evidence, never synthetic inference
    return counts
