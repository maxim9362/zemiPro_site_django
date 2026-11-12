from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.utils.translation import gettext as _

from apps.notifications.services import create_notification
from django.core.exceptions import PermissionDenied
from .forms import ComplaintForm
from .services import create_complaint


@login_required
def complaint_create_view(request):
    if not request.user.is_active or request.user.is_blocked:
        raise PermissionDenied
    target_user_id = request.GET.get('user')
    target_order_id = request.GET.get('order')
    target_rating_id = request.GET.get('rating')

    target_user = None
    target_order = None
    target_rating = None

    if target_user_id:
        from apps.accounts.models import User
        target_user = get_object_or_404(User, pk=target_user_id)
    if target_order_id:
        from apps.marketplace.models import Order
        target_order = get_object_or_404(Order, pk=target_order_id)
    if target_rating_id:
        from apps.marketplace.models import Rating
        target_rating = get_object_or_404(Rating, pk=target_rating_id)

    if request.method == 'POST':
        form = ComplaintForm(request.POST)
        if form.is_valid():
            complaint = create_complaint(
                reporter=request.user,
                reason=form.cleaned_data['reason'],
                message=form.cleaned_data['message'],
                target_user=target_user,
                target_order=target_order,
                target_rating=target_rating,
            )

            from apps.accounts.models import User
            admins = User.objects.filter(is_staff=True, is_active=True)
            for admin in admins:
                create_notification(
                    recipient=admin,
                    title='Новая жалоба',
                    message=f'Поступила жалоба от {request.user}. Причина: {complaint.get_reason_display()}',
                    notification_type='system',
                )

            messages.success(request, _('Жалоба отправлена. Спасибо!'))
            return redirect('marketplace:home')
    else:
        form = ComplaintForm()

    return render(request, 'moderation/complaint_create.html', {
        'form': form,
        'target_user': target_user,
        'target_order': target_order,
        'target_rating': target_rating,
    })
