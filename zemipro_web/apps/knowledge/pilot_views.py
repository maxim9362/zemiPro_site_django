"""Closed Stage14.4 pilot controls; do not expose an owner GO/NO-GO switch."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from .pilot_forms import PilotConsentForm, PilotSelectionForm
from .pilot_services import (
    consent_to_pilot, deselect_from_pilot, pilot_author_status,
    pilot_readiness, select_for_pilot, selection_candidates,
    withdraw_from_pilot,
)
from .services import ArticleConflict


@login_required
@require_http_methods(['GET', 'POST'])
@never_cache
def consent_view(request):
    # A previously enrolled author may revoke even when rollout is disabled.
    try:
        enrollment = pilot_author_status(request.user)
    except PermissionDenied:
        raise Http404 from None
    if request.method == 'POST':
        form = PilotConsentForm(request.POST)
        if not form.is_valid():
            return HttpResponseBadRequest(_('Некорректное действие пилота.'))
        try:
            if form.cleaned_data['action'] == 'consent':
                consent_to_pilot(
                    request.user, confirmed=form.cleaned_data['confirmed'],
                )
                messages.success(request, _('Согласие на пилот подтверждено.'))
            else:
                withdraw_from_pilot(request.user)
                messages.success(request, _('Участие в пилоте прекращено.'))
        except ArticleConflict as exc:
            form.add_error(None, str(exc))
        else:
            return redirect('knowledge:pilot_consent')
    else:
        form = PilotConsentForm()
    return render(request, 'knowledge/pilot_consent.html', {
        'enrollment': enrollment,
        'form': form,
        'seo_noindex': True,
    }, status=400 if form.non_field_errors() else 200)


@login_required
@require_http_methods(['GET', 'POST'])
@never_cache
def moderation_view(request):
    # Owner-disabled public flags never remove the staff emergency stop.
    try:
        snapshot = pilot_readiness(request.user)
    except PermissionDenied:
        raise Http404 from None
    if request.method == 'POST':
        form = PilotSelectionForm(request.POST)
        if not form.is_valid():
            return HttpResponseBadRequest(_('Некорректное действие модерации.'))
        try:
            if form.cleaned_data['action'] == 'select':
                select_for_pilot(
                    request.user, article_id=form.cleaned_data['article_id'],
                    expected_version=form.cleaned_data['expected_version'],
                )
                messages.success(request, _('Статья допущена в пилот.'))
            else:
                deselect_from_pilot(
                    request.user, article_id=form.cleaned_data['article_id'],
                )
                messages.success(request, _('Статья удалена из пилота.'))
        except ArticleConflict as exc:
            form.add_error(None, str(exc))
        else:
            return redirect('knowledge:pilot_moderation')
    else:
        form = PilotSelectionForm()
    return render(request, 'knowledge/pilot_moderation.html', {
        'form': form,
        'pilot': snapshot,
        'articles': selection_candidates(request.user),
        'seo_noindex': True,
    }, status=400 if form.non_field_errors() else 200)
