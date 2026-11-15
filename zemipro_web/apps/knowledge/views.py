"""Private author and moderator UI; zero public article reads in Stage 14.2."""
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse, HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST, require_http_methods
from django.utils.translation import gettext as _

from . import services
from .access import authoring_profile
from .forms import (
    ArticleActionForm, ArticleDecisionForm, ArticleForm, ArticleImageForm,
    ArticleReportDecisionForm, ArticleReportForm,
)
from .models import ExpertArticle, ExpertArticleImage, ExpertArticleReport


def _feature():
    if not settings.ZEMIPRO_KNOWLEDGE_AUTHORING_ENABLED:
        raise Http404


def _author(request):
    _feature()
    return authoring_profile(request.user)


def _own(request, pk):
    _author(request)
    try:
        return services.own_article(request.user, pk)
    except PermissionDenied:
        raise Http404 from None


def _article_page(request, *, worker, article=None, form=None, upload_form=None,
                  status=200):
    if form is None:
        form = ArticleForm(
            worker=worker, article=article,
            initial={
                'title': article.title if article else '',
                'excerpt': article.excerpt if article else '',
                'body': article.body if article else '',
                'category': article.category_id if article else None,
                'subcategory': article.subcategory_id if article else None,
                'language': article.language if article else 'ru',
                'rights_confirmed': bool(article.rights_confirmed_at) if article else False,
            },
        )
    return render(request, 'knowledge/article_form.html', {
        'form': form,
        'upload_form': upload_form or ArticleImageForm(),
        'article': article,
        'images': (
            article.images.defer('jpeg_data').order_by('created_at', 'pk')
            if article else []
        ),
        'seo_noindex': True,
    }, status=status)


@login_required
@require_GET
@never_cache
def my_articles(request):
    _author(request)
    return render(request, 'knowledge/my_articles.html', {
        'articles': services.own_articles(request.user),
        'seo_noindex': True,
    })


@login_required
@require_http_methods(['GET', 'POST'])
@never_cache
def article_create(request):
    worker = _author(request)
    if request.method == 'GET':
        return _article_page(request, worker=worker)
    form = ArticleForm(request.POST, worker=worker)
    if form.is_valid():
        try:
            article = services.create_article(
                actor=request.user, title=form.cleaned_data['title'],
                excerpt=form.cleaned_data['excerpt'], body=form.cleaned_data['body'],
                category_id=form.cleaned_data['category'].pk,
                subcategory_id=(
                    form.cleaned_data['subcategory'].pk
                    if form.cleaned_data['subcategory'] else None
                ),
                language=form.cleaned_data['language'],
                rights_confirmed=form.cleaned_data['rights_confirmed'],
            )
        except services.ArticleConflict as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, _('Черновик сохранён.'))
            return redirect('knowledge:article_edit', pk=article.pk)
    return _article_page(request, worker=worker, form=form, status=400)


@login_required
@require_http_methods(['GET', 'POST'])
@never_cache
def article_edit(request, pk):
    worker = _author(request)
    article = _own(request, pk)
    if request.method == 'GET':
        return _article_page(request, worker=worker, article=article)
    form = ArticleForm(request.POST, worker=worker, article=article)
    if form.is_valid():
        try:
            services.edit_article(
                actor=request.user, article_id=article.pk,
                expected_version=_version(request),
                title=form.cleaned_data['title'],
                excerpt=form.cleaned_data['excerpt'],
                body=form.cleaned_data['body'],
                category_id=form.cleaned_data['category'].pk,
                subcategory_id=(
                    form.cleaned_data['subcategory'].pk
                    if form.cleaned_data['subcategory'] else None
                ),
                rights_confirmed=form.cleaned_data['rights_confirmed'],
            )
        except services.ArticleConflict as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, _('Черновик обновлён.'))
            return redirect('knowledge:article_edit', pk=article.pk)
    return _article_page(request, worker=worker, article=article,
                         form=form, status=400)


def _version(request):
    try:
        value = int(request.POST.get('expected_version', ''))
        if value < 0 or value >= 2**31:
            raise ValueError
        return value
    except (ValueError, TypeError):
        return -1


@login_required
@require_POST
@never_cache
def article_submit(request, pk):
    article = _own(request, pk)
    form = ArticleActionForm(request.POST)
    if not form.is_valid():
        return HttpResponseBadRequest(_('Некорректные данные отправки.'))
    try:
        services.submit_article(
            actor=request.user, article_id=article.pk,
            expected_version=form.cleaned_data['expected_version'],
            rights_confirmed=form.cleaned_data['rights_confirmed'],
        )
    except services.ArticleConflict as exc:
        return HttpResponseBadRequest(str(exc))
    messages.success(request, _('Статья отправлена на проверку.'))
    return redirect('knowledge:article_edit', pk=pk)


@login_required
@require_POST
@never_cache
def article_archive(request, pk):
    article = _own(request, pk)
    try:
        services.archive_article(
            actor=request.user, article_id=article.pk,
            expected_version=_version(request),
        )
    except services.ArticleConflict as exc:
        return HttpResponseBadRequest(str(exc))
    messages.success(request, _('Статья архивирована.'))
    return redirect('knowledge:my_articles')


@login_required
@require_POST
@never_cache
def article_image_add(request, pk):
    worker = _author(request)
    article = _own(request, pk)
    form = ArticleImageForm(request.POST, request.FILES)
    if form.is_valid():
        try:
            services.add_article_image(
                actor=request.user, article_id=article.pk,
                expected_version=form.cleaned_data['expected_version'],
                upload=form.cleaned_data['image'],
                caption=form.cleaned_data['caption'],
                rights_confirmed=form.cleaned_data['rights_confirmed'],
            )
        except services.ArticleConflict as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, _('Изображение сохранено для модерации.'))
            return redirect('knowledge:article_edit', pk=pk)
    return _article_page(request, worker=worker, article=article,
                         upload_form=form, status=400)


@login_required
@require_POST
@never_cache
def article_image_remove(request, pk, image_id):
    _own(request, pk)
    try:
        services.remove_article_image(
            actor=request.user, article_id=pk, image_id=image_id,
            expected_version=_version(request),
        )
    except PermissionDenied:
        raise Http404 from None
    except services.ArticleConflict as exc:
        return HttpResponseBadRequest(str(exc))
    messages.success(request, _('Изображение удалено из черновика.'))
    return redirect('knowledge:article_edit', pk=pk)


@login_required
@require_GET
@never_cache
def article_image_private(request, image_id):
    _feature()
    image = ExpertArticleImage.objects.select_related(
        'article__author',
    ).filter(pk=image_id).first()
    if image is None:
        raise Http404
    owner = (
        request.user.pk == image.article.author.user_id
        and authoring_profile(request.user).pk == image.article.author_id
    ) if request.user.pk == image.article.author.user_id else False
    if not owner:
        try:
            services._moderator_read(request.user)
        except PermissionDenied:
            raise Http404 from None
    response = HttpResponse(bytes(image.jpeg_data), content_type='image/jpeg')
    response['Cache-Control'] = 'private, no-store'
    response['X-Content-Type-Options'] = 'nosniff'
    response['Content-Security-Policy'] = "default-src 'none'; sandbox"
    response['Content-Disposition'] = 'inline; filename="article-photo.jpg"'
    return response


@login_required
@require_http_methods(['GET', 'POST'])
@never_cache
def article_report(request, pk):
    _feature()
    if not settings.ZEMIPRO_KNOWLEDGE_ARTICLES_ENABLED:
        raise Http404
    article = ExpertArticle.objects.filter(
        pk=pk, status=ExpertArticle.Status.PUBLISHED, public_content_safe=True,
        category__is_active=True, author__is_published=True,
        author__city__slug='ashdod', author__city__is_active=True,
        author__user__is_active=True, author__user__is_blocked=False,
    ).first()
    if article is None:
        raise Http404
    if request.method == 'GET':
        form = ArticleReportForm()
    else:
        form = ArticleReportForm(request.POST)
        if form.is_valid():
            try:
                services.report_article(
                    actor=request.user, article_id=pk,
                    reason=form.cleaned_data['reason'],
                    message=form.cleaned_data['message'],
                )
            except services.ArticleConflict as exc:
                form.add_error(None, str(exc))
            else:
                messages.success(request, _('Жалоба отправлена на проверку.'))
                return redirect('knowledge:my_articles')
    return render(request, 'knowledge/report_form.html', {
        'article': article, 'form': form, 'seo_noindex': True,
    }, status=400 if request.method == 'POST' else 200)


@login_required
@require_GET
@never_cache
def moderation_queue(request):
    _feature()
    return render(request, 'knowledge/moderation_queue.html', {
        'articles': services.moderation_queue(request.user),
        'reports': services.report_queue(request.user),
        'seo_noindex': True,
    })


@login_required
@require_http_methods(['GET', 'POST'])
@never_cache
def moderation_article(request, pk):
    _feature()
    try:
        article = services.moderation_article(request.user, pk)
    except PermissionDenied:
        raise Http404 from None
    if request.method == 'GET':
        form = ArticleDecisionForm(initial={'expected_version': article.content_version})
    else:
        form = ArticleDecisionForm(request.POST)
        if form.is_valid():
            try:
                services.decide_article(
                    actor=request.user, article_id=pk,
                    expected_version=form.cleaned_data['expected_version'],
                    approve=(form.cleaned_data['action'] == 'approve'),
                    content_reviewed=form.cleaned_data['content_reviewed'],
                    media_reviewed=form.cleaned_data['media_reviewed'],
                    note=form.cleaned_data['note'],
                )
            except services.ArticleConflict as exc:
                form.add_error(None, str(exc))
            else:
                messages.success(request, _('Решение записано в историю.'))
                return redirect('knowledge:moderation_queue')
    return render(request, 'knowledge/moderation_article.html', {
        'article': article, 'form': form,
        'images': article.images.defer('jpeg_data').order_by('pk'),
        'seo_noindex': True,
    }, status=400 if request.method == 'POST' else 200)


@login_required
@require_POST
@never_cache
def report_decision(request, pk):
    _feature()
    form = ArticleReportDecisionForm(request.POST)
    if not form.is_valid():
        return HttpResponseBadRequest(_('Некорректное решение.'))
    try:
        services.decide_report(
            actor=request.user, report_id=pk,
            remove=(form.cleaned_data['action'] == 'remove'),
            note=form.cleaned_data['note'],
        )
    except services.ArticleConflict as exc:
        return HttpResponseBadRequest(str(exc))
    messages.success(request, _('Жалоба рассмотрена.'))
    return redirect('knowledge:moderation_queue')
