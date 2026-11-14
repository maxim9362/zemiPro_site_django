"""Stage 07.2: minimal server-rendered chat, polling and private JPEG route."""
from uuid import uuid4

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.db.models.query import prefetch_related_objects
from django.http import FileResponse, Http404, HttpResponseBadRequest, JsonResponse
from django.shortcuts import redirect, render
from django.utils import translation
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from .chat_services import (
    ChatConflict, attach_message_image, get_conversation, list_messages,
    mark_messages_read, open_conversation, open_message_image, send_message,
    take_poll_slot,
)
from .models import Conversation, Message


LABELS = {
    'ru': {
        'chats': 'Переписка', 'thread': 'Диалог по заявке',
        'send': 'Отправить', 'message': 'Сообщение',
        'back': 'К диалогам', 'files': 'Прикрепить фото',
        'read': 'Прочитано', 'delivered': 'Доставлено',
        'empty': 'Сообщений пока нет',
        'translate': 'Перевести', 'consent': 'Разрешаю передачу этого текста в Gemini',
        'privacy': 'Не переводите сообщения с личными данными.',
    },
    'en': {
        'chats': 'Messages', 'thread': 'Request conversation',
        'send': 'Send', 'message': 'Message',
        'back': 'Back to conversations', 'files': 'Attach photo',
        'read': 'Read', 'delivered': 'Delivered',
        'empty': 'No messages yet',
        'translate': 'Translate', 'consent': 'I consent to sending this text to Gemini',
        'privacy': 'Do not translate messages containing personal information.',
    },
    'he': {
        'chats': 'שיחות', 'thread': 'שיחה על בקשה',
        'send': 'שליחה', 'message': 'הודעה',
        'back': 'בחזרה לשיחות', 'files': 'צירוף תמונה',
        'read': 'נקרא', 'delivered': 'נמסר',
        'empty': 'אין הודעות עדיין',
        'translate': 'תרגום', 'consent': 'אני מסכים לשליחת הטקסט הזה ל-Gemini',
        'privacy': 'אין לתרגם הודעות עם פרטים אישיים.',
    },
}


def _label():
    language = (translation.get_language() or 'ru').split('-')[0]
    return LABELS.get(language, LABELS['ru'])


def _cursor(raw, *, allow_zero=False):
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ChatConflict('Invalid message cursor.') from exc
    if value < (0 if allow_zero else 1) or value >= 2**63:
        raise ChatConflict('Invalid message cursor.')
    return value


@login_required
@require_GET
@never_cache
def chat_index_view(request):
    from apps.accounts.models import User
    if not User.objects.filter(
        pk=request.user.pk, is_active=True, is_blocked=False,
        email_verification_required=False,
    ).exists():
        raise PermissionDenied
    conversations = Conversation.objects.select_related('response__order').filter(
        Q(response__order__client_id=request.user.pk)
        | Q(response__worker_id=request.user.pk),
    ).order_by('-created_at', '-pk')[:100]
    return render(request, 'pages/chat_index.html', {
        'conversations': conversations, 'copy': _label(),
    })


@login_required
@require_POST
@never_cache
def chat_open_view(request, response_id):
    conversation, _ = open_conversation(response_id=response_id, actor=request.user)
    return redirect('marketplace:chat_thread', conversation_id=conversation.pk)


@login_required
@never_cache
def chat_thread_view(request, conversation_id):
    conversation = get_conversation(conversation_id=conversation_id, actor=request.user)
    error = ''
    if request.method == 'POST':
        try:
            send_message(
                conversation_id=conversation.pk, actor=request.user,
                body=request.POST.get('body'), client_nonce=request.POST.get('client_nonce'),
            )
        except ChatConflict as exc:
            error = str(exc)
        else:
            return redirect('marketplace:chat_thread', conversation_id=conversation.pk)
    elif request.method != 'GET':
        raise Http404
    rows = list_messages(conversation_id=conversation.pk, actor=request.user)
    prefetch_related_objects(rows, 'attachments')
    return render(request, 'pages/chat_thread.html', {
        'conversation': conversation,
        'rows': rows, 'last_id': rows[-1].pk if rows else 0,
        'nonce': str(uuid4()), 'copy': _label(), 'error': error,
        'can_send': (
            conversation.response.status in {'pending', 'sent', 'viewed', 'negotiating', 'accepted'}
            and conversation.response.order.status not in {'draft', 'cancelled', 'expired'}
            and conversation.response.order.worker_id in (None, conversation.response.worker_id)
        ),
    })


@login_required
@require_GET
@never_cache
def chat_poll_view(request, conversation_id):
    try:
        after = _cursor(request.GET.get('after', '0'), allow_zero=True)
        take_poll_slot(conversation_id=conversation_id, actor=request.user)
        conversation = get_conversation(conversation_id=conversation_id, actor=request.user)
    except ChatConflict as exc:
        return HttpResponseBadRequest(str(exc))
    rows = Message.objects.filter(
        conversation=conversation, pk__gt=after,
    ).order_by('pk')[:60]
    return JsonResponse({
        'messages': [{
            'id': m.pk, 'sender_id': m.sender_id, 'body': m.body,
            'created_at': m.created_at.isoformat(), 'read': m.read_at is not None,
        } for m in rows],
    })


@login_required
@require_POST
@never_cache
def chat_read_view(request, conversation_id):
    try:
        through_id = _cursor(request.POST.get('through_id'))
        changed = mark_messages_read(
            conversation_id=conversation_id, actor=request.user, through_id=through_id,
        )
    except ChatConflict as exc:
        return HttpResponseBadRequest(str(exc))
    return JsonResponse({'marked': changed})


@login_required
@require_POST
@never_cache
def chat_image_upload_view(request, message_id):
    try:
        upload = request.FILES.get('image')
        if upload is None:
            raise ChatConflict('An image is required.')
        item, _ = attach_message_image(
            message_id=message_id, actor=request.user, upload=upload,
        )
    except ChatConflict as exc:
        return HttpResponseBadRequest(str(exc))
    return redirect(
        'marketplace:chat_thread', conversation_id=item.message.conversation_id,
    )


@login_required
@require_GET
@never_cache
def chat_attachment_view(request, pk):
    try:
        file = open_message_image(attachment_id=pk, actor=request.user)
    except (PermissionDenied, FileNotFoundError, OSError):
        raise Http404 from None
    response = FileResponse(
        file, content_type='image/jpeg', as_attachment=False, filename='chat-image.jpg',
    )
    response['Cache-Control'] = 'private, no-store, max-age=0'
    response['X-Content-Type-Options'] = 'nosniff'
    response['Content-Security-Policy'] = "default-src 'none'; sandbox"
    response['X-Robots-Tag'] = 'noindex, nofollow, noarchive'
    return response
