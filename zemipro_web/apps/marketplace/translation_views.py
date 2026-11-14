"""Private, explicit translation request with original always available."""
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from .translation_services import (
    TranslationUnavailable, _message_for_user, translate_message,
)


@login_required
@require_POST
@never_cache
def chat_translate_view(request, message_id):
    message = _message_for_user(message_id, request.user)
    try:
        result, _ = translate_message(
            message_id=message_id, actor=request.user,
            target_language=request.POST.get('target_language'),
            consent=request.POST.get('consent') == 'yes',
        )
    except TranslationUnavailable:
        return render(
            request, 'pages/chat_translation.html',
            {'message': message, 'translation': None, 'unavailable': True},
            status=503,
        )
    return render(request, 'pages/chat_translation.html', {
        'message': message, 'translation': result, 'unavailable': False,
    })
