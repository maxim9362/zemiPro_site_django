"""Stage 14.9 voluntary sharing of an already-public worker profile."""
from urllib.parse import urlencode

from django.conf import settings
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from apps.accounts.client_favorites import public_worker_queryset


@require_GET
@never_cache
def facebook_share(request, worker_id):
    if not getattr(settings, 'ZEMIPRO_PROFILE_SHARING_ENABLED', False):
        raise Http404
    worker = get_object_or_404(public_worker_queryset(), pk=worker_id)
    public_path = reverse('marketplace:worker_public_profile', args=[worker.pk])
    public_url = request.build_absolute_uri(public_path)
    target = 'https://www.facebook.com/sharer/sharer.php?' + urlencode({'u': public_url})
    response = redirect(target)
    response['Cache-Control'] = 'private, no-store'
    response['Referrer-Policy'] = 'no-referrer'
    return response
