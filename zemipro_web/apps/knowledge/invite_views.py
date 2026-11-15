"""Stage 14.11 manual external-worker invite pages and safe landing."""
from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods

from . import invite_services


@login_required
@never_cache
@require_http_methods(['GET', 'POST'])
def create_invite(request):
    try:
        invite_services._enabled()
    except PermissionDenied as exc:
        raise Http404 from exc
    context = {'seo_noindex': True}
    if request.method == 'POST':
        invite, token = invite_services.create_invite(actor=request.user)
        path = reverse('knowledge_invites:landing', args=[token])
        context.update({
            'invite': invite,
            'invite_url': request.build_absolute_uri(path),
            'facebook_url': reverse('knowledge:external_invite_facebook', args=[token]),
        })
    response = render(request, 'knowledge/external_invite.html', context)
    response['Cache-Control'] = 'private, no-store'
    return response


@require_GET
@never_cache
def landing(request, token):
    try:
        invite = invite_services.open_invite(token)
    except PermissionDenied as exc:
        raise Http404 from exc
    invite_services.remember_invite(request, invite)
    return redirect(reverse('accounts:register') + '?worker_invite=1')


@login_required
@require_GET
@never_cache
def facebook_share(request, token):
    try:
        invite_services._enabled()
    except PermissionDenied as exc:
        raise Http404 from exc
    digest = invite_services._digest(token)
    from .models import ExternalWorkerInvite
    from django.utils import timezone
    if not ExternalWorkerInvite.objects.filter(
        token_digest=digest, inviter=request.user, expires_at__gt=timezone.now(),
        claimed_count=0,
    ).exists():
        raise Http404
    invite_url = request.build_absolute_uri(
        reverse('knowledge_invites:landing', args=[token]),
    )
    target = 'https://www.facebook.com/sharer/sharer.php?' + urlencode({'u': invite_url})
    response = redirect(target)
    response['Cache-Control'] = 'private, no-store'
    response['Referrer-Policy'] = 'no-referrer'
    return response
