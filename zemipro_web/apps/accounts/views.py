from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest
from django.db import transaction
from django.core.exceptions import ValidationError, PermissionDenied
from django.conf import settings
from django.utils import translation
from django.contrib.auth import views as auth_views
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST, require_http_methods
from django.shortcuts import render, redirect
from django.utils.translation import gettext as _

from .forms import (
    ClientProfileForm, RegistrationForm, WorkerProfileForm,
    RequestContactVerificationForm, ConfirmContactVerificationForm,
    SafeAuthenticationForm, VerifiedPasswordResetForm,
    PhoneRecoveryRequestForm, PhoneRecoveryConfirmForm,
    ClientSettingsForm,
)
from .verification import (
    request_contact_verification, confirm_contact_verification,
    request_phone_password_recovery, confirm_phone_password_recovery,
)
from .models import PrivacyRequest
from .client_settings import save_client_settings, request_own_privacy_action
from .services import (
    create_or_update_client_profile, get_client_profile,
    create_or_update_worker_profile, get_worker_profile, select_active_role,
    set_worker_publication,
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
    if not request.user.is_active or request.user.is_blocked:
        raise PermissionDenied
    profile = get_worker_profile(request.user)
    form = WorkerProfileForm(
        request.POST if request.method == 'POST' else None, instance=profile,
    )
    if request.method == 'POST':
        action = request.POST.get('action', 'save')
        if action not in ('save', 'publish', 'unpublish'):
            return HttpResponseBadRequest(_('Недопустимый запрос.'))
        if action == 'unpublish':
            set_worker_publication(request.user, False)
            messages.success(request, _('Анкета снята с публикации.'))
            return redirect('accounts:worker_profile')
        if form.is_valid():
            try:
                with transaction.atomic():
                    profile = create_or_update_worker_profile(
                        request.user, form.cleaned_data,
                    )
                    if action == 'publish':
                        set_worker_publication(request.user, True)
            except ValueError as exc:
                form.add_error(None, str(exc))
            else:
                messages.success(
                    request, _('Анкета опубликована.') if action == 'publish'
                    else _('Анкета сохранена.'),
                )
                return redirect('accounts:worker_profile')
    return render(request, 'accounts/worker_profile.html', {
        'form': form, 'profile': profile,
    })


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


@require_http_methods(['GET', 'POST'])
def phone_recovery_view(request):
    """Generic response prevents discovery of a username or phone claim."""
    form = PhoneRecoveryRequestForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        request_phone_password_recovery(
            form.cleaned_data['username'], form.cleaned_data['phone'],
        )
        messages.info(
            request,
            _('Если телефон подтверждён и аккаунт доступен, код будет отправлен.'),
        )
        return redirect('accounts:phone_recovery_confirm')
    return render(request, 'accounts/phone_recovery.html', {'form': form})


@require_http_methods(['GET', 'POST'])
def phone_recovery_confirm_view(request):
    form = PhoneRecoveryConfirmForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        try:
            confirmed = confirm_phone_password_recovery(
                form.cleaned_data['username'], form.cleaned_data['phone'],
                form.cleaned_data['code'], form.cleaned_data['new_password1'],
            )
        except ValidationError as exc:
            form.add_error('new_password1', exc)
        else:
            if confirmed:
                messages.success(request, _('Пароль обновлён.'))
                return redirect('accounts:login')
            messages.error(request, _('Неверный или просроченный код.'))
    return render(request, 'accounts/phone_recovery_confirm.html', {'form': form})


@login_required
@require_http_methods(['GET', 'POST'])
def client_settings_view(request):
    """Only the signed-in user's account/profile/settings; no user-id parameter."""
    if request.user.is_blocked or not request.user.is_active:
        raise PermissionDenied
    profile = get_client_profile(request.user)
    form = ClientSettingsForm(
        request.POST if request.method == 'POST' else None,
        user=request.user, profile=profile,
    )
    if request.method == 'POST' and form.is_valid():
        try:
            save_client_settings(request.user, form.cleaned_data)
        except ValueError:
            form.add_error(None, _('Проверьте данные профиля.'))
        else:
            messages.success(request, _('Настройки сохранены.'))
            response = redirect('accounts:client_settings')
            language = request.user.preferred_language
            translation.activate(language)
            response.set_cookie(
                settings.LANGUAGE_COOKIE_NAME, language,
                max_age=settings.LANGUAGE_COOKIE_AGE,
                secure=settings.SESSION_COOKIE_SECURE,
                samesite='Lax',
            )
            return response
    return render(request, 'accounts/client_settings.html', {
        'form': form,
        'privacy_requests': PrivacyRequest.objects.filter(
            user=request.user,
        )[:20],
    })


@login_required
@require_POST
def client_privacy_request_view(request):
    """Queue export/erasure request for human review; no automatic deletion."""
    try:
        request_own_privacy_action(request.user, request.POST.get('kind'))
    except ValueError:
        return HttpResponseBadRequest(_('Недопустимый запрос.'))
    messages.success(request, _('Запрос принят на рассмотрение.'))
    return redirect('accounts:client_settings')
