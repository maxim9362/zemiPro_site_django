"""07.4: owner-only response to a verified review."""
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest
from django.shortcuts import redirect
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from .review_services import ReviewConflict, submit_review_reply


@login_required
@require_POST
@never_cache
def rating_reply_view(request, rating_id):
    try:
        reply, _ = submit_review_reply(
            rating_id=rating_id, actor=request.user,
            body=request.POST.get('body'),
        )
    except ReviewConflict as exc:
        return HttpResponseBadRequest(str(exc))
    return redirect('marketplace:order_detail', pk=reply.rating.order_id)
