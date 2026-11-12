from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest, FileResponse, Http404
from django.db import transaction
from django.core.exceptions import PermissionDenied
from django.conf import settings
from django.utils import translation
from django.contrib.auth import views as auth_views
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST, require_http_methods
from django.shortcuts import render, redirect, get_object_or_404
from django.utils.translation import gettext as _

from .forms import (
    ClientProfileForm, RegistrationForm, WorkerProfileForm,
    RequestContactVerificationForm, ConfirmContactVerificationForm,
    SafeAuthenticationForm, VerifiedPasswordResetForm,
    ClientSettingsForm, PortfolioUploadForm, PortfolioEditForm,
)
from .verification import (
    request_contact_verification, confirm_contact_verification,
)
from .models import PrivacyRequest, WorkerPortfolioPhoto
from .client_settings import save_client_settings, request_own_privacy_action
from .client_favorites import public_worker_queryset
from .portfolio import (
    PortfolioError, add_own_portfolio_photo, update_own_portfolio_photo,
    delete_own_portfolio_photo, owner_portfolio, portfolio_storage_key,
    private_portfolio_storage,
)
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
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            return redirect('accounts:client_profile')
    else:
        form = RegistrationForm()
    return render(request, 'accounts/register.html', {
        'form': form,
        'google_login_enabled': settings.ZEMIPRO_GOOGLE_LOGIN_ENABLED,
    })


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
            if profile is None:
                return HttpResponseBadRequest(_('Сначала заполните профиль мастера.'))
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

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        data['google_login_enabled'] = settings.ZEMIPRO_GOOGLE_LOGIN_ENABLED
        return data


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


def _portfolio_owner(request):
    if not request.user.is_authenticated or request.user.is_blocked or not request.user.is_active:
        raise PermissionDenied
    profile = get_worker_profile(request.user)
    if profile is None:
        return None
    return profile


@login_required
@require_http_methods(['GET'])
def worker_portfolio_view(request):
    profile = _portfolio_owner(request)
    if profile is None:
        return redirect('accounts:worker_profile')
    return render(request, 'accounts/worker_portfolio.html', {
        'profile': profile, 'photos': owner_portfolio(request.user),
        'upload_form': PortfolioUploadForm(),
    })


@login_required
@require_POST
def worker_portfolio_add_view(request):
    profile = _portfolio_owner(request)
    if profile is None:
        return redirect('accounts:worker_profile')
    form = PortfolioUploadForm(request.POST, request.FILES)
    if form.is_valid():
        try:
            add_own_portfolio_photo(
                request.user, form.cleaned_data['image'],
                caption=form.cleaned_data['caption'],
                sort_order=form.cleaned_data['sort_order'] or 0,
                is_public=form.cleaned_data['is_public'],
                rights_confirmed=form.cleaned_data['rights_confirmed'],
            )
        except PortfolioError as exc:
            form.add_error('image', str(exc))
        else:
            messages.success(request, _('Фотография добавлена.'))
            return redirect('accounts:worker_portfolio')
    return render(request, 'accounts/worker_portfolio.html', {
        'profile': profile, 'photos': owner_portfolio(request.user),
        'upload_form': form,
    }, status=400)


@login_required
@require_POST
def worker_portfolio_edit_view(request, pk):
    _portfolio_owner(request)
    form = PortfolioEditForm(request.POST)
    if not form.is_valid():
        return HttpResponseBadRequest(_('Некорректные данные фотографии.'))
    try:
        update_own_portfolio_photo(
            request.user, pk,
            caption=form.cleaned_data['caption'],
            sort_order=form.cleaned_data['sort_order'],
            is_public=form.cleaned_data['is_public'],
        )
    except PortfolioError:
        return HttpResponseBadRequest(_('Некорректные данные фотографии.'))
    messages.success(request, _('Фотография обновлена.'))
    return redirect('accounts:worker_portfolio')


@login_required
@require_POST
def worker_portfolio_delete_view(request, pk):
    _portfolio_owner(request)
    try:
        delete_own_portfolio_photo(request.user, pk)
    except PortfolioError:
        raise Http404 from None
    messages.success(request, _('Фотография удалена.'))
    return redirect('accounts:worker_portfolio')


@require_http_methods(['GET'])
def worker_portfolio_image_view(request, pk):
    """Stream a normalized JPEG only to owner or via explicit public consent."""
    photo = get_object_or_404(
        WorkerPortfolioPhoto.objects.select_related('worker__user'), pk=pk,
    )
    is_owner = bool(
        request.user.is_authenticated
        and request.user.pk == photo.worker.user_id
        and request.user.is_active and not request.user.is_blocked
    )
    is_visible = (
        photo.is_public and public_worker_queryset().filter(
            pk=photo.worker_id,
        ).exists()
    )
    if not is_owner and not is_visible:
        raise Http404
    try:
        key = portfolio_storage_key(photo)
        image_file = private_portfolio_storage().open(key, 'rb')
    except (PortfolioError, OSError, FileNotFoundError):
        raise Http404 from None
    response = FileResponse(
        image_file, content_type='image/jpeg',
        as_attachment=False, filename='work-photo.jpg',
    )
    response['Cache-Control'] = 'private, no-store'
    response['X-Content-Type-Options'] = 'nosniff'
    response['Content-Security-Policy'] = "default-src 'none'; sandbox"
    return response
