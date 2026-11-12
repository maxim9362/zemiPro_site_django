from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest
from django.contrib.auth import views as auth_views
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST
from django.shortcuts import render, redirect
from django.utils.translation import gettext as _

from .forms import (
    ClientProfileForm, RegistrationForm, WorkerProfileForm,
    RequestContactVerificationForm, ConfirmContactVerificationForm,
    SafeAuthenticationForm, VerifiedPasswordResetForm,
)
from .verification import request_contact_verification, confirm_contact_verification
from .services import (
    create_or_update_client_profile, get_client_profile,
    create_or_update_worker_profile, get_worker_profile, select_active_role,
)


def register_view(request):
    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('accounts:client_profile')
    else:
        form = RegistrationForm()
    return render(request, 'accounts/register.html', {'form': form})


@login_required
def client_profile_view(request):
    profile = get_client_profile(request.user)

    if request.method == 'POST':
        form = ClientProfileForm(request.POST, instance=profile)
        if form.is_valid():
            create_or_update_client_profile(request.user, form.cleaned_data)
            messages.success(request, _('Профиль клиента сохранён.'))
            return redirect('marketplace:client_dashboard')
    else:
        initial = {}
        if profile:
            initial = {
                'city': profile.city,
                'contact': profile.contact,
            }
        form = ClientProfileForm(initial=initial)

    return render(request, 'accounts/client_profile.html', {'form': form, 'profile': profile})


@login_required
def worker_profile_view(request):
    profile = get_worker_profile(request.user)

    if request.method == 'POST':
        form = WorkerProfileForm(request.POST, instance=profile)
        if form.is_valid():
            create_or_update_worker_profile(request.user, form.cleaned_data)
            messages.success(request, _('Профиль мастера сохранён.'))
            return redirect('marketplace:worker_dashboard')
    else:
        initial = {}
        if profile:
            initial = {
                'city': profile.city,
                'contact': profile.contact,
                'description': profile.description,
                'skills': profile.skills.all(),
                'service_cities': profile.service_cities.all(),
                'offers_remote': profile.offers_remote,
                'receive_notifications': profile.receive_notifications,
            }
        form = WorkerProfileForm(initial=initial)

    return render(request, 'accounts/worker_profile.html', {'form': form, 'profile': profile})


@login_required
@require_POST
def switch_role_view(request):
    """Switch active cabinet via an authenticated, CSRF-protected POST."""
    role = request.POST.get('role')
    try:
        select_active_role(request.user, role)
    except ValueError:
        return HttpResponseBadRequest(_('Недопустимая роль.'))

    if role == request.user.ActiveRole.WORKER:
        if get_worker_profile(request.user) is None:
            return redirect('accounts:worker_profile')
        return redirect('marketplace:worker_dashboard')
    if get_client_profile(request.user) is None:
        return redirect('accounts:client_profile')
    return redirect('marketplace:client_dashboard')

class SafeLoginView(auth_views.LoginView):
    template_name = 'accounts/login.html'
    authentication_form = SafeAuthenticationForm


class VerifiedPasswordResetView(auth_views.PasswordResetView):
    template_name = 'accounts/password_reset.html'
    email_template_name = 'accounts/password_reset_email.txt'
    subject_template_name = 'accounts/password_reset_subject.txt'
    form_class = VerifiedPasswordResetForm
    success_url = reverse_lazy('accounts:password_reset_done')


@login_required
def contact_verification_view(request):
    """Never reveal the verification code in a response."""
    return render(request, 'accounts/contact_verification.html', {
        'request_form': RequestContactVerificationForm(),
        'confirm_form': ConfirmContactVerificationForm(),
    })


@login_required
@require_POST
def request_verification_view(request):
    form = RequestContactVerificationForm(request.POST)
    if form.is_valid():
        try:
            delivered = request_contact_verification(
                request.user, form.cleaned_data['channel'],
            )
        except ValueError:
            messages.error(request, _('Не удалось отправить код подтверждения.'))
        else:
            if delivered:
                messages.success(request, _('Код подтверждения отправлен.'))
            else:
                messages.error(request, _('Доставка подтверждений пока недоступна.'))
    else:
        messages.error(request, _('Проверьте способ подтверждения.'))
    return redirect('accounts:contact_verification')


@login_required
@require_POST
def confirm_verification_view(request):
    form = ConfirmContactVerificationForm(request.POST)
    if form.is_valid() and confirm_contact_verification(
        request.user, form.cleaned_data['channel'], form.cleaned_data['code'],
    ):
        messages.success(request, _('Контакт подтверждён.'))
    else:
        messages.error(request, _('Неверный или просроченный код.'))
    return redirect('accounts:contact_verification')
