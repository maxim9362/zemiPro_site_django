"""Stage 14.5 Q&A domain services.

Questions and answers are moderated knowledge records.  They deliberately have
no relationship to orders, offers, prices or the verified marketplace rating.
Every public value comes from an approved contact-free snapshot.
"""
import hashlib
import hmac
import re
from datetime import datetime, timezone as utc_timezone
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, models, transaction
from django.db.models import Count
from django.utils import timezone
from django.utils.text import slugify

from apps.accounts.client_favorites import public_worker_queryset
from apps.accounts.models import User
from apps.accounts.public_text import contains_public_contact, prepare_public_text
from apps.marketplace.models import Category
from core.middleware import increment_attempt_counter

from .models import (
    ExpertAnswer, ExpertAnswerRevision, ExpertQuestion,
    ExpertQuestionRevision, HelpfulVote, KnowledgeQAReport,
)


class QAConflict(ValueError):
    """A safe domain error which never includes private submitted content."""


_HTML_TAG = re.compile(r'<\s*/?\s*[a-z][^>]*>', re.IGNORECASE)
_LIMITS = {
    'question': (5, 86400),
    'answer': (10, 86400),
    'edit': (30, 3600),
    'vote': (60, 3600),
    'report': (5, 86400),
}


def _enabled():
    if not getattr(settings, 'ZEMIPRO_KNOWLEDGE_QA_ENABLED', False):
        raise PermissionDenied('Knowledge Q&A is not enabled.')


def _active_user(actor, *, lock=True):
    if not getattr(actor, 'is_authenticated', False) or not getattr(actor, 'pk', None):
        raise PermissionDenied('Account is unavailable.')
    users = User.objects.select_for_update() if lock else User.objects
    user = users.filter(
        pk=actor.pk, is_active=True, is_blocked=False,
        email_verification_required=False,
    ).first()
    if user is None:
        raise PermissionDenied('Account is unavailable.')
    return user


def _worker(actor):
    user = _active_user(actor)
    worker = public_worker_queryset().select_for_update(of=('self',)).filter(
        user_id=user.pk, city__slug='ashdod', city__is_active=True,
    ).first()
    if worker is None:
        raise PermissionDenied('Published Ashdod professional profile required.')
    return user, worker


def _moderator(actor):
    user = _active_user(actor)
    if not user.is_staff or not user.has_perm('knowledge.moderate_expert_questions'):
        raise PermissionDenied('Knowledge moderator permission required.')
    return user


def _charge(user, kind):
    limit, window = _LIMITS[kind]
    now = timezone.now()
    bucket = int(now.timestamp() // window)
    digest = hmac.new(
        settings.SECRET_KEY.encode(),
        f'knowledge-qa:{user.pk}:{kind}:{bucket}'.encode(), hashlib.sha256,
    ).hexdigest()
    expires = datetime.fromtimestamp((bucket + 1) * window, tz=utc_timezone.utc)
    if increment_attempt_counter(digest, expires) > limit:
        raise QAConflict('Too many Q&A actions. Try later.')


def _text(value, *, minimum, maximum, field):
    if not isinstance(value, str):
        raise QAConflict(f'Invalid {field}.')
    value = value.strip()
    if not minimum <= len(value) <= maximum:
        raise QAConflict(f'Invalid {field} length.')
    if _HTML_TAG.search(value) or contains_public_contact(value):
        raise QAConflict('Contacts, links and HTML are not allowed.')
    return value


def _question_revision(question, actor, action):
    question.content_version += 1
    question.save()
    ExpertQuestionRevision.objects.create(
        question=question, actor=actor, version=question.content_version,
        action=action, status_snapshot=question.status,
        title=question.title, body=question.body,
    )


def _answer_revision(answer, actor, action):
    answer.content_version += 1
    answer.save()
    ExpertAnswerRevision.objects.create(
        answer=answer, actor=actor, version=answer.content_version,
        action=action, status_snapshot=answer.status, body=answer.body,
    )


def _assert_version(instance, expected_version):
    if type(expected_version) is not int or instance.content_version != expected_version:
        raise QAConflict('Content changed. Reload before retrying.')


def _hide_question(question):
    question.public_title = ''
    question.public_body = ''
    question.public_content_safe = False
    question.approved_version = None
    question.published_at = None


def _hide_answer(answer):
    answer.public_body = ''
    answer.public_content_safe = False
    answer.approved_version = None
    answer.published_at = None
    answer.is_accepted = False


def public_questions():
    if not getattr(settings, 'ZEMIPRO_KNOWLEDGE_QA_ENABLED', False):
        return ExpertQuestion.objects.none()
    return ExpertQuestion.objects.filter(
        status=ExpertQuestion.Status.PUBLISHED, public_content_safe=True,
        approved_version__isnull=False, published_at__isnull=False,
        category__is_active=True, author__is_active=True,
        author__is_blocked=False, author__email_verification_required=False,
    ).select_related('category').annotate(
        published_answer_count=Count(
            'answers', filter=models.Q(answers__status=ExpertAnswer.Status.PUBLISHED),
        ),
    )


def public_answers(question):
    if not getattr(settings, 'ZEMIPRO_KNOWLEDGE_QA_ENABLED', False):
        return ExpertAnswer.objects.none()
    worker_ids = public_worker_queryset().filter(
        city__slug='ashdod', city__is_active=True,
    ).values('pk')
    return ExpertAnswer.objects.filter(
        question=question, status=ExpertAnswer.Status.PUBLISHED,
        public_content_safe=True, approved_version__isnull=False,
        published_at__isnull=False, author_id__in=worker_ids,
    ).select_related('author').annotate(helpful_count=Count('helpful_votes'))


@transaction.atomic
def create_question(*, actor, category_id, language, title, body):
    _enabled()
    user = _active_user(actor)
    category = Category.objects.filter(pk=category_id, is_active=True).first()
    if category is None or language not in ('ru', 'en', 'he'):
        raise QAConflict('Invalid question category or language.')
    title = _text(title, minimum=8, maximum=180, field='question title')
    body = _text(body, minimum=20, maximum=8000, field='question text')
    _charge(user, 'question')
    stem = slugify(title, allow_unicode=True)[:120].strip('-') or 'question'
    question = ExpertQuestion(
        author=user, category=category, language=language,
        slug=f'{stem}-{uuid4().hex[:12]}', title=title, body=body,
    )
    _question_revision(question, user, 'created')
    return question


@transaction.atomic
def edit_question(*, actor, question_id, expected_version, title, body, category_id):
    _enabled()
    user = _active_user(actor)
    question = ExpertQuestion.objects.select_for_update().filter(pk=question_id).first()
    if question is None or question.author_id != user.pk:
        raise PermissionDenied('Question is unavailable.')
    _assert_version(question, expected_version)
    if question.status not in (ExpertQuestion.Status.DRAFT, ExpertQuestion.Status.REJECTED):
        raise QAConflict('Question cannot be edited in its current state.')
    category = Category.objects.filter(pk=category_id, is_active=True).first()
    if category is None:
        raise QAConflict('Invalid question category.')
    question.title = _text(title, minimum=8, maximum=180, field='question title')
    question.body = _text(body, minimum=20, maximum=8000, field='question text')
    question.category = category
    question.status = ExpertQuestion.Status.DRAFT
    _hide_question(question)
    _charge(user, 'edit')
    _question_revision(question, user, 'edited')
    return question


@transaction.atomic
def submit_question(*, actor, question_id, expected_version):
    _enabled()
    user = _active_user(actor)
    question = ExpertQuestion.objects.select_for_update().filter(pk=question_id).first()
    if question is None or question.author_id != user.pk:
        raise PermissionDenied('Question is unavailable.')
    _assert_version(question, expected_version)
    if question.status not in (ExpertQuestion.Status.DRAFT, ExpertQuestion.Status.REJECTED):
        raise QAConflict('Question cannot be submitted in its current state.')
    _text(question.title, minimum=8, maximum=180, field='question title')
    _text(question.body, minimum=20, maximum=8000, field='question text')
    question.status = ExpertQuestion.Status.PENDING
    question.submitted_at = timezone.now()
    _hide_question(question)
    _question_revision(question, user, 'submitted')
    return question


@transaction.atomic
def moderate_question(*, actor, question_id, expected_version, approve, note=''):
    _enabled()
    moderator = _moderator(actor)
    question = ExpertQuestion.objects.select_for_update().filter(pk=question_id).first()
    if question is None:
        raise PermissionDenied('Question is unavailable.')
    if question.author_id == moderator.pk:
        raise PermissionDenied('Cannot moderate own question.')
    _assert_version(question, expected_version)
    if question.status != ExpertQuestion.Status.PENDING or type(approve) is not bool:
        raise QAConflict('Question is no longer awaiting moderation.')
    now = timezone.now()
    if approve:
        title = prepare_public_text(question.title)
        body = prepare_public_text(question.body)
        if not title or not body:
            raise QAConflict('Question contains unsafe public content.')
        question.public_title = title
        question.public_body = body
        question.public_content_safe = True
        question.status = ExpertQuestion.Status.PUBLISHED
        question.published_at = now
        question.approved_version = question.content_version + 1
        action = 'approved'
    else:
        if not isinstance(note, str) or len(note.strip()) < 10:
            raise QAConflict('A rejection reason is required.')
        question.status = ExpertQuestion.Status.REJECTED
        _hide_question(question)
        action = 'rejected'
    question.moderated_by = moderator
    question.moderated_at = now
    _question_revision(question, moderator, action)
    return question


@transaction.atomic
def create_answer(*, actor, question_id, body):
    _enabled()
    user, worker = _worker(actor)
    question = ExpertQuestion.objects.select_for_update().filter(
        pk=question_id, status=ExpertQuestion.Status.PUBLISHED,
        public_content_safe=True,
    ).first()
    if question is None:
        raise PermissionDenied('Question is unavailable.')
    body = _text(body, minimum=20, maximum=12000, field='answer text')
    _charge(user, 'answer')
    try:
        answer = ExpertAnswer(question=question, author=worker, body=body)
        _answer_revision(answer, user, 'created')
    except IntegrityError as exc:
        raise QAConflict('You already answered this question.') from exc
    return answer


@transaction.atomic
def edit_answer(*, actor, answer_id, expected_version, body):
    _enabled()
    user, worker = _worker(actor)
    answer = ExpertAnswer.objects.select_for_update().filter(pk=answer_id).first()
    if answer is None or answer.author_id != worker.pk:
        raise PermissionDenied('Answer is unavailable.')
    _assert_version(answer, expected_version)
    if answer.status not in (ExpertAnswer.Status.DRAFT, ExpertAnswer.Status.REJECTED):
        raise QAConflict('Answer cannot be edited in its current state.')
    answer.body = _text(body, minimum=20, maximum=12000, field='answer text')
    answer.status = ExpertAnswer.Status.DRAFT
    _hide_answer(answer)
    _charge(user, 'edit')
    _answer_revision(answer, user, 'edited')
    return answer


@transaction.atomic
def submit_answer(*, actor, answer_id, expected_version):
    _enabled()
    user, worker = _worker(actor)
    answer = ExpertAnswer.objects.select_for_update().filter(pk=answer_id).first()
    if answer is None or answer.author_id != worker.pk:
        raise PermissionDenied('Answer is unavailable.')
    _assert_version(answer, expected_version)
    if answer.status not in (ExpertAnswer.Status.DRAFT, ExpertAnswer.Status.REJECTED):
        raise QAConflict('Answer cannot be submitted in its current state.')
    _text(answer.body, minimum=20, maximum=12000, field='answer text')
    answer.status = ExpertAnswer.Status.PENDING
    answer.submitted_at = timezone.now()
    _hide_answer(answer)
    _answer_revision(answer, user, 'submitted')
    return answer


@transaction.atomic
def moderate_answer(*, actor, answer_id, expected_version, approve, note=''):
    _enabled()
    moderator = _moderator(actor)
    answer = ExpertAnswer.objects.select_for_update().select_related('author').filter(
        pk=answer_id,
    ).first()
    if answer is None:
        raise PermissionDenied('Answer is unavailable.')
    if answer.author.user_id == moderator.pk:
        raise PermissionDenied('Cannot moderate own answer.')
    _assert_version(answer, expected_version)
    if answer.status != ExpertAnswer.Status.PENDING or type(approve) is not bool:
        raise QAConflict('Answer is no longer awaiting moderation.')
    now = timezone.now()
    if approve:
        if not public_worker_queryset().filter(
            pk=answer.author_id, city__slug='ashdod', city__is_active=True,
        ).exists():
            raise QAConflict('Answer author is no longer publicly eligible.')
        body = prepare_public_text(answer.body)
        if not body:
            raise QAConflict('Answer contains unsafe public content.')
        answer.public_body = body
        answer.public_content_safe = True
        answer.status = ExpertAnswer.Status.PUBLISHED
        answer.published_at = now
        answer.approved_version = answer.content_version + 1
        action = 'approved'
    else:
        if not isinstance(note, str) or len(note.strip()) < 10:
            raise QAConflict('A rejection reason is required.')
        answer.status = ExpertAnswer.Status.REJECTED
        _hide_answer(answer)
        action = 'rejected'
    answer.moderated_by = moderator
    answer.moderated_at = now
    _answer_revision(answer, moderator, action)
    return answer


@transaction.atomic
def accept_answer(*, actor, question_id, answer_id):
    _enabled()
    user = _active_user(actor)
    question = ExpertQuestion.objects.select_for_update().filter(pk=question_id).first()
    if question is None or question.author_id != user.pk:
        raise PermissionDenied('Question is unavailable.')
    if not public_questions().filter(pk=question.pk).exists():
        raise PermissionDenied('Question is unavailable.')
    answer = ExpertAnswer.objects.select_for_update().filter(
        pk=answer_id, question=question, status=ExpertAnswer.Status.PUBLISHED,
        public_content_safe=True,
    ).first()
    if answer is None:
        raise PermissionDenied('Answer is unavailable.')
    if not public_answers(question).filter(pk=answer.pk).exists():
        raise PermissionDenied('Answer is unavailable.')
    if answer.is_accepted:
        return answer
    if ExpertAnswer.objects.filter(question=question, is_accepted=True).exists():
        raise QAConflict('An answer is already accepted.')
    answer.is_accepted = True
    answer.save(update_fields=['is_accepted', 'updated_at'])
    return answer


@transaction.atomic
def set_helpful(*, actor, answer_id, helpful, question_id=None):
    _enabled()
    user = _active_user(actor)
    answer = ExpertAnswer.objects.select_for_update().filter(
        pk=answer_id, status=ExpertAnswer.Status.PUBLISHED,
        public_content_safe=True,
    ).first()
    if answer is None:
        raise PermissionDenied('Answer is unavailable.')
    if question_id is not None and answer.question_id != question_id:
        raise PermissionDenied('Answer is unavailable.')
    if not public_questions().filter(pk=answer.question_id).exists():
        raise PermissionDenied('Answer is unavailable.')
    if not public_answers(answer.question).filter(pk=answer.pk).exists():
        raise PermissionDenied('Answer is unavailable.')
    if answer.author.user_id == user.pk:
        raise PermissionDenied('Cannot vote for your own answer.')
    if type(helpful) is not bool:
        raise QAConflict('Invalid vote state.')
    _charge(user, 'vote')
    if helpful:
        HelpfulVote.objects.get_or_create(answer=answer, voter=user)
    else:
        HelpfulVote.objects.filter(answer=answer, voter=user).delete()
    return helpful


@transaction.atomic
def report_content(*, actor, question_id=None, answer_id=None, reason, message):
    _enabled()
    user = _active_user(actor)
    if (question_id is None) == (answer_id is None):
        raise QAConflict('Choose one report target.')
    if reason not in KnowledgeQAReport.Reason.values:
        raise QAConflict('Invalid report reason.')
    message = _text(message, minimum=10, maximum=2000, field='report details')
    kwargs = {'question_id': question_id} if question_id else {'answer_id': answer_id}
    if question_id:
        target = ExpertQuestion.objects.select_for_update().filter(
            pk=question_id, status='published', public_content_safe=True,
        ).first()
        if target is not None and not public_questions().filter(pk=target.pk).exists():
            target = None
    else:
        target = ExpertAnswer.objects.select_for_update().filter(
            pk=answer_id, status='published', public_content_safe=True,
        ).first()
        if target is not None and not public_answers(target.question).filter(
            pk=target.pk,
        ).exists():
            target = None
    if target is None:
        raise PermissionDenied('Content is unavailable.')
    owner_id = target.author_id if question_id else target.author.user_id
    if owner_id == user.pk:
        raise PermissionDenied('Cannot report your own content.')
    _charge(user, 'report')
    try:
        return KnowledgeQAReport.objects.create(
            reporter=user, reason=reason, message=message, **kwargs,
        )
    except IntegrityError as exc:
        raise QAConflict('Report already filed.') from exc


@transaction.atomic
def decide_report(*, actor, report_id, remove):
    """Resolve one report while locking target before report in a fixed order."""
    _enabled()
    moderator = _moderator(actor)
    target = KnowledgeQAReport.objects.filter(pk=report_id).values(
        'question_id', 'answer_id',
    ).first()
    if target is None:
        raise PermissionDenied('Report is unavailable.')
    if target['question_id']:
        content = ExpertQuestion.objects.select_for_update().get(
            pk=target['question_id'],
        )
    else:
        content = ExpertAnswer.objects.select_for_update().get(pk=target['answer_id'])
    report = KnowledgeQAReport.objects.select_for_update().get(pk=report_id)
    if report.status != KnowledgeQAReport.Status.PENDING or type(remove) is not bool:
        raise QAConflict('Report is already resolved.')
    if remove:
        content.status = 'archived'
        if isinstance(content, ExpertQuestion):
            _hide_question(content)
            _question_revision(content, moderator, 'archived')
        else:
            _hide_answer(content)
            _answer_revision(content, moderator, 'archived')
        report.status = KnowledgeQAReport.Status.REMOVED
    else:
        report.status = KnowledgeQAReport.Status.DISMISSED
    report.handled_by = moderator
    report.handled_at = timezone.now()
    report.save(update_fields=['status', 'handled_by', 'handled_at'])
    return report
