from .services import get_unread_count


def notifications_counter(request):
    """Контекстный процессор — количество непрочитанных уведомлений."""
    if request.user.is_authenticated:
        return {'unread_notifications_count': get_unread_count(request.user)}
    return {'unread_notifications_count': 0}
