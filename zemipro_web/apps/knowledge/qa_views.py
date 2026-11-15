"""Stage 14.6 locale-prefixed, noindex Q&A interface."""
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import get_language
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from apps.accounts.public_text import contact_shaped_query
from apps.marketplace.models import Category

from . import qa_services
from .models import ExpertAnswer, ExpertQuestion, KnowledgeQAReport
from .qa_forms import AnswerForm, ModerationForm, QuestionForm, ReportForm


def _allow():
    try:
        qa_services._enabled()
    except PermissionDenied as exc:
        raise Http404 from exc


def _language():
    language = (get_language() or 'ru').split('-')[0]
    if language not in ('ru', 'en', 'he'):
        raise Http404
    return language


def _detail_url(question):
    return reverse('knowledge_qa:detail', kwargs={'slug': question.slug})


@require_GET
@never_cache
def question_list(request):
    _allow()
    language = _language()
    visible = qa_services.public_questions().filter(language=language)
    query = request.GET.get('q', '').strip()
    category = request.GET.get('category', '').strip()
    invalid = len(query) > 120 or contact_shaped_query(query)
    if invalid:
        visible = visible.none()
        query = ''
    elif query:
        visible = visible.filter(
            Q(public_title__icontains=query) | Q(public_body__icontains=query),
        )
    if category:
        try:
            visible = visible.filter(category_id=int(category))
        except ValueError:
            visible = visible.none()
            invalid = True
            category = ''
    preserved = urlencode({
        key: value for key, value in {'q': query, 'category': category}.items() if value
    })
    page = Paginator(visible.order_by('-published_at', '-pk'), 12).get_page(
        request.GET.get('page'),
    )
    categories = Category.objects.filter(
        pk__in=qa_services.public_questions().values('category_id'), is_active=True,
    ).order_by('sort_order', 'pk').distinct()
    return render(request, 'knowledge/qa_list.html', {
        'page_obj': page, 'categories': categories, 'query': query,
        'selected_category': category, 'invalid_query': invalid,
        'pagination_query': preserved, 'seo_noindex': True,
        'language_switch_next': request.path + ('?' + preserved if preserved else ''),
    })


@require_GET
@never_cache
def question_detail(request, slug):
    _allow()
    question = get_object_or_404(
        qa_services.public_questions(), slug=slug, language=_language(),
    )
    answers = list(qa_services.public_answers(question))
    response = render(request, 'knowledge/qa_detail.html', {
        'question': question, 'answers': answers,
        'answer_form': AnswerForm(), 'report_form': ReportForm(),
        'seo_noindex': True,
    })
    from .rollout_metrics import record
    record('question', 'question_view', question.pk)
    return response


@require_GET
@never_cache
def question_outbound(request, slug, destination, answer_id=None):
    _allow()
    question = get_object_or_404(
        qa_services.public_questions(), slug=slug, language=_language(),
    )
    from .rollout_metrics import record
    if destination == 'profile' and answer_id:
        answer = get_object_or_404(
            qa_services.public_answers(question), pk=answer_id,
        )
        record('question', 'profile_click', question.pk)
        target = reverse('marketplace:worker_public_profile', args=[answer.author_id])
    elif destination == 'order' and answer_id is None:
        record('question', 'order_started', question.pk)
        target = reverse('marketplace:order_wizard_start')
    else:
        raise Http404
    response = redirect(target)
    response['Cache-Control'] = 'private, no-store'
    return response


@login_required
@never_cache
@require_http_methods(['GET', 'POST'])
def question_create(request):
    _allow()
    form = QuestionForm(request.POST or None, initial={'language': _language()})
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            question = qa_services.create_question(
                actor=request.user, category_id=form.cleaned_data['category'].pk,
                language=form.cleaned_data['language'], title=form.cleaned_data['title'],
                body=form.cleaned_data['body'],
            )
            qa_services.submit_question(
                actor=request.user, question_id=question.pk,
                expected_version=question.content_version,
            )
        messages.success(request, 'Question submitted for moderation.')
        return redirect('knowledge_qa:list')
    return render(request, 'knowledge/qa_form.html', {
        'form': form, 'seo_noindex': True,
    })


@login_required
@require_POST
def answer_create(request, slug):
    _allow()
    question = get_object_or_404(
        qa_services.public_questions(), slug=slug, language=_language(),
    )
    form = AnswerForm(request.POST)
    if not form.is_valid():
        raise PermissionDenied('Invalid answer.')
    with transaction.atomic():
        answer = qa_services.create_answer(
            actor=request.user, question_id=question.pk,
            body=form.cleaned_data['body'],
        )
        qa_services.submit_answer(
            actor=request.user, answer_id=answer.pk,
            expected_version=answer.content_version,
        )
    messages.success(request, 'Answer submitted for moderation.')
    return redirect(_detail_url(question))


@login_required
@require_POST
def accept_answer(request, slug, answer_id):
    _allow()
    question = get_object_or_404(ExpertQuestion, slug=slug, language=_language())
    qa_services.accept_answer(
        actor=request.user, question_id=question.pk, answer_id=answer_id,
    )
    return redirect(_detail_url(question))


@login_required
@require_POST
def vote_answer(request, slug, answer_id):
    _allow()
    question = get_object_or_404(ExpertQuestion, slug=slug, language=_language())
    qa_services.set_helpful(
        actor=request.user, answer_id=answer_id,
        helpful=request.POST.get('helpful') == '1',
    )
    return redirect(_detail_url(question))


@login_required
@require_POST
def report_question(request, slug):
    _allow()
    question = get_object_or_404(
        qa_services.public_questions(), slug=slug, language=_language(),
    )
    form = ReportForm(request.POST)
    if not form.is_valid():
        raise PermissionDenied('Invalid report.')
    qa_services.report_content(
        actor=request.user, question_id=question.pk, **form.cleaned_data,
    )
    messages.success(request, 'Report submitted.')
    return redirect(_detail_url(question))


@login_required
@require_POST
def report_answer(request, slug, answer_id):
    _allow()
    question = get_object_or_404(
        qa_services.public_questions(), slug=slug, language=_language(),
    )
    if not ExpertAnswer.objects.filter(pk=answer_id, question=question).exists():
        raise Http404
    form = ReportForm(request.POST)
    if not form.is_valid():
        raise PermissionDenied('Invalid report.')
    qa_services.report_content(
        actor=request.user, answer_id=answer_id, **form.cleaned_data,
    )
    messages.success(request, 'Report submitted.')
    return redirect(_detail_url(question))


def _moderator_read(user):
    current = qa_services._active_user(user, lock=False)
    if not current.is_staff or not current.has_perm(
        'knowledge.moderate_expert_questions',
    ):
        raise PermissionDenied('Moderator only.')
    return current


@login_required
@require_GET
@never_cache
def moderation_queue(request):
    _allow()
    _moderator_read(request.user)
    return render(request, 'knowledge/qa_moderation.html', {
        'questions': ExpertQuestion.objects.filter(status='pending')[:100],
        'answers': ExpertAnswer.objects.filter(status='pending').select_related(
            'question', 'author',
        )[:100],
        'reports': KnowledgeQAReport.objects.filter(status='pending')[:100],
        'seo_noindex': True,
    })


@login_required
@require_POST
def moderate_question(request, question_id):
    form = ModerationForm(request.POST)
    if not form.is_valid():
        raise PermissionDenied('Invalid moderation decision.')
    qa_services.moderate_question(
        actor=request.user, question_id=question_id,
        expected_version=form.cleaned_data['expected_version'],
        approve=form.cleaned_data['action'] == 'approve',
        note=form.cleaned_data['note'],
    )
    return redirect('knowledge:qa_moderation')


@login_required
@require_POST
def moderate_answer(request, answer_id):
    form = ModerationForm(request.POST)
    if not form.is_valid():
        raise PermissionDenied('Invalid moderation decision.')
    qa_services.moderate_answer(
        actor=request.user, answer_id=answer_id,
        expected_version=form.cleaned_data['expected_version'],
        approve=form.cleaned_data['action'] == 'approve',
        note=form.cleaned_data['note'],
    )
    return redirect('knowledge:qa_moderation')


@login_required
@require_POST
def moderate_report(request, report_id):
    action = request.POST.get('action')
    if action not in ('dismiss', 'remove'):
        raise PermissionDenied('Invalid moderation decision.')
    qa_services.decide_report(
        actor=request.user, report_id=report_id, remove=action == 'remove',
    )
    return redirect('knowledge:qa_moderation')
