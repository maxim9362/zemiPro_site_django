"""Stage 14.2 — private article authoring, image ingestion and audited moderation.

All writes are transactional and check live DB identities and object ownership.
The module does not expose published articles: Stage 14.3 implements public
views separately and only behind the currently disabled public feature flag.
"""
import hashlib
import hmac
import re
from datetime import datetime, timezone as utc_timezone
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.text import slugify

from apps.accounts.models import User, WorkerProfile
from apps.accounts.portfolio import PortfolioError, sanitize_portfolio_image
from apps.accounts.public_text import contains_public_contact, prepare_public_text
from apps.locations.models import City
from apps.marketplace.models import Category, Subcategory
from core.middleware import increment_attempt_counter

from .models import (
    ExpertArticle, ExpertArticleDecision, ExpertArticleImage,
    ExpertArticleReport, ExpertArticleRevision,
)


class ArticleConflict(ValueError):
    """Safe error text: no source data, private identities or file names."""


# Durable shared counters in the existing PostgreSQL SensitivePostCounter table.
# (successful mutations; POST abuse is additionally guarded at the IP layer)
_LIMITS = {
    'create': (5, 86400),
    'edit': (30, 3600),
    'submit': (10, 86400),
    'image': (12, 3600),
    'archive': (10, 86400),
    'report': (5, 86400),
}
_HTML_TAG = re.compile(r'<\s*/?\s*[a-z][^>]*>', re.IGNORECASE)


def _enabled():
    # Not configurable via environment; owner GO is still a separate gate.
    if not getattr(settings, 'ZEMIPRO_KNOWLEDGE_AUTHORING_ENABLED', False):
        raise PermissionDenied('Article editor is not enabled.')


def _active_user(actor, *, lock=True):
    if not getattr(actor, 'is_authenticated', False) or not getattr(actor, 'pk', None):
        raise PermissionDenied('Account is unavailable.')
    users = User.objects
    if lock:
        users = users.select_for_update()
    user = users.filter(
        pk=actor.pk, is_active=True, is_blocked=False,
        email_verification_required=False,
    ).first()
    if user is None:
        raise PermissionDenied('Account is unavailable.')
    return user


def _author(actor):
    user = _active_user(actor)
    worker = WorkerProfile.objects.select_for_update().filter(user_id=user.pk).first()
    if not worker or not worker.is_published:
        raise PermissionDenied('Published professional profile required.')
    # The test environment may relax its legacy market pilot gate, but
    # Stage 14 authoring never expands beyond owner-approved Ashdod.
    if not worker.city_id or not City.objects.filter(
        pk=worker.city_id, slug='ashdod', is_active=True,
    ).exists():
        raise PermissionDenied('Article authoring is Ashdod-only.')
    return user, worker


def _moderator(actor):
    user = _active_user(actor)
    if not user.is_staff or not user.has_perm('knowledge.moderate_expert_articles'):
        raise PermissionDenied('Article moderator permission required.')
    return user


def _charge(user, kind):
    limit, window = _LIMITS[kind]
    now = timezone.now()
    bucket = int(now.timestamp() // window)
    digest = hmac.new(
        settings.SECRET_KEY.encode('utf-8'),
        f'knowledge:{user.pk}:{kind}:{bucket}'.encode('utf-8'),
        hashlib.sha256,
    ).hexdigest()
    expires = datetime.fromtimestamp((bucket + 1) * window, tz=utc_timezone.utc)
    if increment_attempt_counter(digest, expires) > limit:
        raise ArticleConflict('Too many article actions. Try later.')


def _draft_text(title, excerpt, body):
    if not all(isinstance(x, str) for x in (title, excerpt, body)):
        raise ArticleConflict('Invalid article fields.')
    title, excerpt, body = (x.strip() for x in (title, excerpt, body))
    if not (1 <= len(title) <= 180 and len(excerpt) <= 400 and len(body) <= 16000):
        raise ArticleConflict('Invalid article length.')
    if any(_HTML_TAG.search(x) or contains_public_contact(x) for x in (
        title, excerpt, body,
    )):
        raise ArticleConflict('Contacts, links and HTML are not allowed in articles.')
    return title, excerpt, body


def _catalog(category_id, subcategory_id, worker):
    category = Category.objects.filter(pk=category_id, is_active=True).first()
    if category is None or not worker.skills.filter(pk=category.pk).exists():
        raise ArticleConflict('Choose an available professional category.')
    subcategory = None
    if subcategory_id:
        subcategory = Subcategory.objects.filter(
            pk=subcategory_id, category=category, is_active=True,
        ).first()
        if subcategory is None:
            raise ArticleConflict('The subcategory does not match the category.')
    return category, subcategory


def _assert_version(article, expected_version):
    if type(expected_version) is not int or expected_version != article.content_version:
        raise ArticleConflict('Article changed. Reload before retrying.')


def _revise(article, actor, action):
    article.content_version += 1
    article.save()
    ExpertArticleRevision.objects.create(
        article=article, actor=actor, version=article.content_version,
        action=action, status_snapshot=article.status,
        title=article.title, excerpt=article.excerpt, body=article.body,
    )


def _hide(article):
    article.public_content_safe = False
    article.public_title = ''
    article.public_excerpt = ''
    article.public_body = ''
    article.approved_version = None
    article.published_at = None
    ExpertArticleImage.objects.filter(article=article).update(
        approved_version=None, public_caption='',
    )


def _editable(article):
    if article.status == ExpertArticle.Status.PENDING_REVIEW:
        raise ArticleConflict('Article is awaiting moderation.')
    if article.status == ExpertArticle.Status.ARCHIVED:
        raise ArticleConflict('Archived articles cannot be edited.')


def _owned_article(worker, article_id):
    article = ExpertArticle.objects.select_for_update().filter(pk=article_id).first()
    if article is None or article.author_id != worker.pk:
        raise PermissionDenied('Article is unavailable.')
    return article


def own_articles(actor):
    """Owner-only source listing, not a public article catalogue."""
    _enabled()
    user = _active_user(actor, lock=False)
    return ExpertArticle.objects.filter(author__user_id=user.pk).order_by('-updated_at')


def own_article(actor, article_id):
    _enabled()
    user = _active_user(actor, lock=False)
    article = ExpertArticle.objects.filter(
        pk=article_id, author__user_id=user.pk,
    ).first()
    if article is None:
        raise PermissionDenied('Article is unavailable.')
    return article


@transaction.atomic
def create_article(*, actor, title, excerpt='', body='', category_id,
                   subcategory_id=None, language='ru', rights_confirmed=False):
    _enabled()
    user, worker = _author(actor)
    title, excerpt, body = _draft_text(title, excerpt, body)
    if language not in ExpertArticle.Language.values:
        raise ArticleConflict('Invalid original language.')
    category, subcategory = _catalog(category_id, subcategory_id, worker)
    _charge(user, 'create')
    slug = (slugify(title, allow_unicode=True)[:120].strip('-') or 'article')
    slug = f'{slug}-{uuid4().hex[:12]}'
    article = ExpertArticle(
        author=worker, category=category, subcategory=subcategory,
        slug=slug, language=language, title=title, excerpt=excerpt, body=body,
        rights_confirmed_at=timezone.now() if rights_confirmed is True else None,
    )
    _revise(article, user, ExpertArticleRevision.Action.CREATED)
    return article


@transaction.atomic
def edit_article(*, actor, article_id, expected_version, title, excerpt, body,
                 category_id, subcategory_id=None, rights_confirmed=False):
    _enabled()
    user, worker = _author(actor)
    article = _owned_article(worker, article_id)
    _assert_version(article, expected_version)
    _editable(article)
    title, excerpt, body = _draft_text(title, excerpt, body)
    category, subcategory = _catalog(category_id, subcategory_id, worker)
    if (title == article.title and excerpt == article.excerpt and body == article.body
            and category.pk == article.category_id
            and (subcategory.pk if subcategory else None) == article.subcategory_id
            and bool(article.rights_confirmed_at) == (rights_confirmed is True)):
        return article
    _charge(user, 'edit')
    article.title, article.excerpt, article.body = title, excerpt, body
    article.category, article.subcategory = category, subcategory
    article.rights_confirmed_at = (
        timezone.now() if rights_confirmed is True else None
    )
    article.status = ExpertArticle.Status.DRAFT
    article.moderated_by_id = None
    article.moderated_at = None
    article.submitted_at = None
    _hide(article)
    _revise(article, user, ExpertArticleRevision.Action.EDITED)
    return article


@transaction.atomic
def submit_article(*, actor, article_id, expected_version, rights_confirmed=False):
    _enabled()
    user, worker = _author(actor)
    article = _owned_article(worker, article_id)
    _assert_version(article, expected_version)
    if article.status not in (
        ExpertArticle.Status.DRAFT, ExpertArticle.Status.REJECTED,
    ):
        raise ArticleConflict('Article cannot be submitted in its current state.')
    if rights_confirmed is not True and article.rights_confirmed_at is None:
        raise ArticleConflict('Confirm the rights to the article before submission.')
    _draft_text(article.title, article.excerpt, article.body)
    if len(article.title) < 8 or len(article.body) < 80:
        raise ArticleConflict('Complete the title and content before submitting.')
    _catalog(article.category_id, article.subcategory_id, worker)
    _charge(user, 'submit')
    if rights_confirmed is True:
        article.rights_confirmed_at = timezone.now()
    article.status = ExpertArticle.Status.PENDING_REVIEW
    article.submitted_at = timezone.now()
    _hide(article)
    _revise(article, user, ExpertArticleRevision.Action.SUBMITTED)
    return article


def _clean_caption(value):
    if not isinstance(value, str):
        raise ArticleConflict('Invalid image caption.')
    value = value.strip()
    if len(value) > 200 or contains_public_contact(value) or _HTML_TAG.search(value):
        raise ArticleConflict('Invalid image caption or private contact.')
    return value


@transaction.atomic
def add_article_image(*, actor, article_id, expected_version, upload,
                      caption='', rights_confirmed=False):
    _enabled()
    user, worker = _author(actor)
    article = _owned_article(worker, article_id)
    _assert_version(article, expected_version)
    if article.status not in (
        ExpertArticle.Status.DRAFT, ExpertArticle.Status.REJECTED,
    ):
        raise ArticleConflict('Edit the article draft before adding images.')
    if rights_confirmed is not True:
        raise ArticleConflict('Confirm the rights to the image.')
    caption = _clean_caption(caption)
    if ExpertArticleImage.objects.filter(article=article).count() >= 3:
        raise ArticleConflict('Only three article images are supported.')
    _charge(user, 'image')
    try:
        data = sanitize_portfolio_image(upload)
    except PortfolioError as exc:
        raise ArticleConflict('Invalid image. Use JPEG, PNG or WebP under 5 MB.') from exc
    image = ExpertArticleImage.objects.create(
        article=article, uploaded_by=user, jpeg_data=data,
        byte_size=len(data), caption=caption, rights_confirmed_at=timezone.now(),
    )
    _revise(article, user, ExpertArticleRevision.Action.EDITED)
    return image


@transaction.atomic
def remove_article_image(*, actor, article_id, image_id, expected_version):
    _enabled()
    user, worker = _author(actor)
    article = _owned_article(worker, article_id)
    _assert_version(article, expected_version)
    if article.status not in (
        ExpertArticle.Status.DRAFT, ExpertArticle.Status.REJECTED,
    ):
        raise ArticleConflict('Edit the article draft before removing images.')
    image = ExpertArticleImage.objects.filter(article=article, pk=image_id).first()
    if image is None:
        raise PermissionDenied('Image is unavailable.')
    _charge(user, 'image')
    image.delete()
    _revise(article, user, ExpertArticleRevision.Action.EDITED)
    return article


@transaction.atomic
def archive_article(*, actor, article_id, expected_version):
    _enabled()
    user, worker = _author(actor)
    article = _owned_article(worker, article_id)
    _assert_version(article, expected_version)
    if article.status == ExpertArticle.Status.ARCHIVED:
        raise ArticleConflict('Article is already archived.')
    _charge(user, 'archive')
    article.status = ExpertArticle.Status.ARCHIVED
    article.moderated_at = timezone.now()
    _hide(article)
    _revise(article, user, ExpertArticleRevision.Action.ARCHIVED)
    return article


def moderation_queue(actor):
    _enabled()
    _moderator_read(actor)
    return ExpertArticle.objects.filter(
        status=ExpertArticle.Status.PENDING_REVIEW,
    ).select_related('author', 'category').order_by('submitted_at', 'pk')[:100]


def report_queue(actor):
    _enabled()
    _moderator_read(actor)
    return ExpertArticleReport.objects.filter(
        status=ExpertArticleReport.Status.PENDING,
    ).select_related('article').order_by('created_at', 'pk')[:100]


def _moderator_read(actor):
    user = _active_user(actor, lock=False)
    if not user.is_staff or not user.has_perm('knowledge.moderate_expert_articles'):
        raise PermissionDenied('Moderator only.')
    return user


def moderation_article(actor, article_id):
    _enabled()
    _moderator_read(actor)
    article = ExpertArticle.objects.filter(pk=article_id).first()
    if article is None:
        raise PermissionDenied('Article is unavailable.')
    return article


def _public_snapshots(article):
    candidates = [
        prepare_public_text(article.title),
        prepare_public_text(article.excerpt),
        prepare_public_text(article.body),
    ]
    if any(v is None for v in candidates):
        raise ArticleConflict('Potential private contacts or links: reject article.')
    if len(candidates[0]) < 8 or len(candidates[2]) < 80:
        raise ArticleConflict('Article is incomplete.')
    if any(_HTML_TAG.search(v) for v in candidates):
        raise ArticleConflict('HTML is not allowed.')
    return candidates


@transaction.atomic
def decide_article(*, actor, article_id, expected_version, approve,
                   content_reviewed=False, media_reviewed=False, note=''):
    _enabled()
    moderator = _moderator(actor)
    article = ExpertArticle.objects.select_for_update().filter(pk=article_id).first()
    if article is None:
        raise PermissionDenied('Article is unavailable.')
    if article.author.user_id == moderator.pk:
        raise PermissionDenied('Cannot moderate own article.')
    _assert_version(article, expected_version)
    if article.status != ExpertArticle.Status.PENDING_REVIEW:
        raise ArticleConflict('Article is no longer awaiting review.')
    if type(approve) is not bool or not isinstance(note, str) or len(note) > 500:
        raise ArticleConflict('Invalid moderation decision.')
    note = note.strip()
    images = list(ExpertArticleImage.objects.select_for_update().filter(
        article=article,
    ).order_by('pk').defer('jpeg_data'))
    now = timezone.now()
    if approve:
        if content_reviewed is not True or (images and media_reviewed is not True):
            raise ArticleConflict('Manual content and image review are required.')
        if article.rights_confirmed_at is None:
            raise ArticleConflict('Author rights confirmation is missing.')
        # An author may lose eligibility between submission and moderation.
        # Approval must fail closed, independently of later public-view filters.
        if not WorkerProfile.objects.filter(
            pk=article.author_id, is_published=True, city__slug='ashdod',
            city__is_active=True, user__is_active=True, user__is_blocked=False,
            user__email_verification_required=False,
            skills__pk=article.category_id,
            public_content_safe=True,
        ).exists() or not Category.objects.filter(
            pk=article.category_id, is_active=True,
        ).exists():
            raise ArticleConflict('Author or category no longer eligible.')
        if article.subcategory_id and not Subcategory.objects.filter(
            pk=article.subcategory_id, category_id=article.category_id, is_active=True,
        ).exists():
            raise ArticleConflict('Service is no longer available.')
        title, excerpt, body = _public_snapshots(article)
        captions = []
        for image in images:
            safe_caption = prepare_public_text(image.caption)
            if safe_caption is None:
                raise ArticleConflict('Unsafe image caption.')
            captions.append(safe_caption)
        article.public_title = title
        article.public_excerpt = excerpt
        article.public_body = body
        article.public_content_safe = True
        article.status = ExpertArticle.Status.PUBLISHED
        article.published_at = now
        article.approved_version = article.content_version + 1
        for image, caption in zip(images, captions):
            image.approved_version = article.approved_version
            image.public_caption = caption
            image.save(update_fields=['approved_version', 'public_caption'])
        action = ExpertArticleRevision.Action.APPROVED
        kind = ExpertArticleDecision.Kind.APPROVE
    else:
        if len(note) < 10:
            raise ArticleConflict('A reason is required when rejecting content.')
        article.status = ExpertArticle.Status.REJECTED
        _hide(article)
        action = ExpertArticleRevision.Action.REJECTED
        kind = ExpertArticleDecision.Kind.REJECT
    article.moderated_by = moderator
    article.moderated_at = now
    _revise(article, moderator, action)
    ExpertArticleDecision.objects.create(
        article=article, moderator=moderator, version=article.content_version,
        kind=kind, reason=note,
    )
    return article


@transaction.atomic
def report_article(*, actor, article_id, reason, message):
    _enabled()
    if not getattr(settings, 'ZEMIPRO_KNOWLEDGE_ARTICLES_ENABLED', False):
        raise PermissionDenied('Public articles are disabled.')
    user = _active_user(actor)
    article = ExpertArticle.objects.select_related('author').filter(
        pk=article_id, status=ExpertArticle.Status.PUBLISHED,
        public_content_safe=True, category__is_active=True,
        author__is_published=True, author__city__slug='ashdod',
        author__city__is_active=True, author__user__is_active=True,
        author__user__is_blocked=False,
    ).first()
    if article is None:
        raise PermissionDenied('Article is unavailable.')
    if not isinstance(message, str) or not 10 <= len(message.strip()) <= 2000:
        raise ArticleConflict('Invalid report description.')
    if reason not in ExpertArticleReport.Reason.values:
        raise ArticleConflict('Invalid report reason.')
    # Private reports must not become a new repository for others' contacts.
    if contains_public_contact(message) or _HTML_TAG.search(message):
        raise ArticleConflict('Contacts, links and HTML are not allowed in reports.')
    if article.author.user_id == user.pk:
        raise PermissionDenied('Cannot report your own article.')
    if ExpertArticleReport.objects.filter(article=article, reporter=user).exists():
        raise ArticleConflict('Report already filed.')
    _charge(user, 'report')
    try:
        return ExpertArticleReport.objects.create(
            article=article, reporter=user, reason=reason, message=message.strip(),
        )
    except IntegrityError as exc:
        raise ArticleConflict('Report already filed.') from exc


@transaction.atomic
def decide_report(*, actor, report_id, remove, note=''):
    _enabled()
    moderator = _moderator(actor)
    # Lock the parent article first, then the report, consistently with articles.
    article_id = ExpertArticleReport.objects.filter(
        pk=report_id,
    ).values_list('article_id', flat=True).first()
    if article_id is None:
        raise PermissionDenied('Report is unavailable.')
    article = ExpertArticle.objects.select_for_update().get(pk=article_id)
    if article.author.user_id == moderator.pk:
        raise PermissionDenied('Cannot decide a report about your own article.')
    report = ExpertArticleReport.objects.select_for_update().get(
        pk=report_id, article=article,
    )
    if report.status != ExpertArticleReport.Status.PENDING:
        raise ArticleConflict('Report already reviewed.')
    if type(remove) is not bool or not isinstance(note, str) or len(note) > 500:
        raise ArticleConflict('Invalid report decision.')
    note = note.strip()
    if remove:
        if len(note) < 10:
            raise ArticleConflict('A removal reason is required.')
        if article.status == ExpertArticle.Status.PUBLISHED:
            article.status = ExpertArticle.Status.ARCHIVED
            article.moderated_by = moderator
            article.moderated_at = timezone.now()
            _hide(article)
            _revise(article, moderator, ExpertArticleRevision.Action.ARCHIVED)
            ExpertArticleDecision.objects.create(
                article=article, moderator=moderator,
                version=article.content_version,
                kind=ExpertArticleDecision.Kind.REMOVE, reason=note,
            )
        report.status = ExpertArticleReport.Status.REMOVED
    else:
        report.status = ExpertArticleReport.Status.DISMISSED
    report.handled_by = moderator
    report.handled_at = timezone.now()
    report.save(update_fields=['status', 'handled_by', 'handled_at'])
    return report
