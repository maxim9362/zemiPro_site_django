from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordResetForm, UserCreationForm
from django.contrib.auth import authenticate
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from core.forms import LocalizedModelChoiceField, LocalizedModelMultipleChoiceField

from apps.locations.models import City
from apps.locations.services import get_public_cities
from apps.marketplace.models import Category, Rating
from .models import ClientProfile, User, WorkerProfile, VerifiedContact
from .verification import contact_fingerprint, normalize_israeli_phone


class RegistrationForm(UserCreationForm):
    """Username/password remain primary; neither unverified contact is login."""

    email = forms.EmailField(
        label=_('Email'), required=False, max_length=254,
    )
    phone = forms.CharField(
        label=_('Телефон'), required=False, max_length=20,
        help_text=_('Номер телефона Израиля с кодом +972'),
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username', 'email', 'phone')

    def clean_email(self):
        return self.cleaned_data.get('email', '').strip().casefold()

    def clean_phone(self):
        value = self.cleaned_data.get('phone', '').strip()
        if not value:
            return ''
        try:
            return normalize_israeli_phone(value)
        except ValueError as exc:
            raise ValidationError(_('Некорректный израильский номер телефона.')) from exc

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get('email') and not cleaned.get('phone'):
            raise ValidationError(_('Укажите email или телефон для подтверждения.'))
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.phone = self.cleaned_data['phone'] or None
        if commit:
            user.save()
        return user


def resolve_login_identifier(value):
    """Only a *verified* matching contact can serve as a login alias.

    Unverified/different-user contacts cannot choose an account. The input
    falls back to an ordinary username for backwards compatibility.
    """
    value = value.strip()
    channel = None
    candidate = ''
    if '@' in value:
        channel = 'email'
        candidate = value.casefold()
    else:
        try:
            candidate = normalize_israeli_phone(value)
        except ValueError:
            return value
        channel = 'phone'
    claim = VerifiedContact.objects.select_related('user').filter(
        channel=channel, fingerprint=contact_fingerprint(channel, candidate),
    ).first()
    if claim is None:
        return value
    claimed_user = claim.user
    verified = (
        claimed_user.email_verified_at if channel == 'email'
        else claimed_user.phone_verified_at
    )
    stored = (
        (claimed_user.email or '').strip().casefold()
        if channel == 'email' else claimed_user.phone
    )
    return claimed_user.get_username() if verified and stored == candidate else value


class SafeAuthenticationForm(AuthenticationForm):
    """Username, verified email or verified +972 phone; never unverified aliases."""

    username = forms.CharField(
        max_length=254, label=_('Имя пользователя, email или телефон'),
    )

    def clean(self):
        username = self.cleaned_data.get('username')
        password = self.cleaned_data.get('password')
        if username is not None and password:
            # Keep the original submitted identifier in cleaned_data so failed
            # login forms cannot disclose the resolved account username.
            self.user_cache = authenticate(
                self.request, username=resolve_login_identifier(username),
                password=password,
            )
            if self.user_cache is None:
                raise self.get_invalid_login_error()
            self.confirm_login_allowed(self.user_cache)
        return self.cleaned_data

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if user.is_blocked:
            raise ValidationError(
                _('Аккаунт недоступен.'), code='inactive',
            )


class VerifiedPasswordResetForm(PasswordResetForm):
    """Never send a recovery link to an email the user has not proved."""

    def get_users(self, email):
        normalized = email.strip().casefold()
        digest = contact_fingerprint('email', normalized)
        accounts = get_user_model()._default_manager.filter(
            email__iexact=normalized, email_verified_at__isnull=False,
            is_active=True, is_blocked=False,
        )
        for user in accounts:
            if (
                user.has_usable_password()
                and VerifiedContact.objects.filter(
                    user=user, channel='email', fingerprint=digest,
                ).exists()
            ):
                yield user


class RequestContactVerificationForm(forms.Form):
    channel = forms.ChoiceField(
        choices=(('email', _('Email')), ('phone', _('Телефон'))),
        label=_('Способ подтверждения'),
    )


class ConfirmContactVerificationForm(RequestContactVerificationForm):
    code = forms.CharField(
        min_length=6, max_length=6,
        label=_('Код подтверждения'),
        widget=forms.TextInput(attrs={
            'autocomplete': 'one-time-code', 'inputmode': 'numeric',
            'pattern': '[0-9]{6}',
        }),
    )

    def clean_code(self):
        value = self.cleaned_data['code']
        if len(value) != 6 or not value.isascii() or not value.isdigit():
            raise ValidationError(_('Введите шестизначный код.'))
        return value


class ClientProfileForm(forms.ModelForm):
    """Форма профиля клиента."""

    city = LocalizedModelChoiceField(
        queryset=City.objects.filter(is_active=True),
        label=_('Город'),
        empty_label=_('Выберите город'),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['city'].queryset = get_public_cities()

    class Meta:
        model = ClientProfile
        fields = ['city', 'contact']
        labels = {'contact': _('Контакт для связи')}
        widgets = {
            'contact': forms.TextInput(attrs={
                'placeholder': _('+972-XX-XXX-XXXX или @username'),
            }),
        }


class WorkerProfileForm(forms.ModelForm):
    """Save an owner-controlled draft; publishing requires separate validation."""

    city = LocalizedModelChoiceField(
        queryset=City.objects.filter(is_active=True),
        label=_('Город'),
        empty_label=_('Выберите город'), required=False,
    )
    skills = LocalizedModelMultipleChoiceField(
        queryset=Category.objects.filter(is_active=True).filter(
            Q(section__isnull=True) | Q(section__is_active=True)
        ),
        label=_('Категории работ'), required=False,
        widget=forms.CheckboxSelectMultiple,
    )

    service_cities = LocalizedModelMultipleChoiceField(
        queryset=City.objects.filter(is_active=True).order_by('name_ru', 'pk'),
        label=_('Города обслуживания (можно выбрать несколько)'),
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )
    offers_remote = forms.BooleanField(
        required=False,
        label=_('Выполняю подходящие услуги онлайн'),
    )

    spoken_languages = forms.MultipleChoiceField(
        choices=(('ru', _('Русский')), ('en', _('Английский')),
                 ('he', _('Иврит'))),
        required=False, widget=forms.CheckboxSelectMultiple,
        label=_('Языки общения'),
    )

    class Meta:
        model = WorkerProfile
        fields = [
            'provider_type', 'display_name', 'city', 'contact', 'description',
            'skills', 'service_cities', 'offers_remote', 'spoken_languages',
            'pricing_details', 'availability', 'working_hours',
            'receive_notifications',
        ]
        labels = {
            'contact': _('Контакт для связи'),
            'description': _('Описание услуг'),
            'receive_notifications': _('Получать уведомления о новых заявках'),
        }
        widgets = {
            'contact': forms.TextInput(attrs={
                'placeholder': _('+972-XX-XXX-XXXX или @username'),
            }),
            'description': forms.Textarea(attrs={
                'rows': 4,
                'placeholder': _('Опишите ваш опыт, инструменты, особенности работы (минимум 20 символов)'),
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        cities = get_public_cities()
        self.fields['city'].queryset = cities
        self.fields['service_cities'].queryset = cities
        if self.instance.pk is None:
            self.fields['spoken_languages'].initial = ['ru']

    def clean(self):
        data = super().clean()
        if data.get('offers_remote'):
            skills = data.get('skills')
            if skills is not None and not skills.filter(
                work_mode__in=('online', 'both')
            ).exists():
                raise forms.ValidationError(
                    _('Для онлайн-работы выберите хотя бы одну услугу с онлайн-форматом.')
                )
        return data

    def clean_display_name(self):
        return self.cleaned_data.get('display_name', '').strip()

    def clean_description(self):
        return self.cleaned_data.get('description', '').strip()

    def clean_pricing_details(self):
        return self.cleaned_data.get('pricing_details', '').strip()


class RatingCreateForm(forms.ModelForm):
    """Форма отзыва на мастера."""

    class Meta:
        model = Rating
        fields = ['rating', 'review_text']
        widgets = {
            'rating': forms.NumberInput(attrs={
                'min': 1, 'max': 5, 'style': 'width: 80px;',
            }),
            'review_text': forms.Textarea(attrs={
                'rows': 4,
                'placeholder': _('Расскажите о качестве работы (необязательно)'),
            }),
        }
        labels = {
            'rating': _('Оценка (от 1 до 5)'),
            'review_text': _('Текст отзыва'),
        }

class PhoneRecoveryRequestForm(forms.Form):
    """Phone-only users may recover with their proven +972 phone and username."""

    username = forms.CharField(max_length=150, label=_('Имя пользователя'))
    phone = forms.CharField(max_length=20, label=_('Телефон'))

    def clean_phone(self):
        try:
            return normalize_israeli_phone(self.cleaned_data['phone'])
        except ValueError as exc:
            raise ValidationError(_('Некорректный израильский номер телефона.')) from exc


class PhoneRecoveryConfirmForm(PhoneRecoveryRequestForm):
    code = forms.CharField(
        min_length=6, max_length=6, label=_('Код подтверждения'),
        widget=forms.TextInput(attrs={'autocomplete': 'one-time-code',
                                      'inputmode': 'numeric', 'pattern': '[0-9]{6}'}),
    )
    new_password1 = forms.CharField(
        label=_('Новый пароль'), widget=forms.PasswordInput,
    )
    new_password2 = forms.CharField(
        label=_('Повторите пароль'), widget=forms.PasswordInput,
    )

    def clean(self):
        data = super().clean()
        if data.get('new_password1') != data.get('new_password2'):
            raise ValidationError(_('Пароли не совпадают.'))
        code = data.get('code', '')
        if not code.isascii() or not code.isdigit():
            self.add_error('code', _('Введите шестизначный код.'))
        return data

class ClientSettingsForm(forms.Form):
    """Edit only own User + ClientProfile data; no role/permission fields."""

    first_name = forms.CharField(
        max_length=150, required=False, label=_('Имя'),
    )
    last_name = forms.CharField(
        max_length=150, required=False, label=_('Фамилия'),
    )
    email = forms.EmailField(
        max_length=254, required=False, label=_('Email'),
    )
    phone = forms.CharField(
        max_length=20, required=False, label=_('Телефон'),
    )
    preferred_language = forms.ChoiceField(
        choices=(('ru', 'Русский'), ('en', 'English'), ('he', 'עברית')),
        label=_('Предпочитаемый язык'),
    )
    city = LocalizedModelChoiceField(
        queryset=City.objects.none(), required=False,
        label=_('Город'), empty_label=_('Выберите город'),
    )
    contact = forms.CharField(
        max_length=100, required=False, label=_('Контакт для связи'),
    )
    receive_optional_updates = forms.BooleanField(
        required=False,
        label=_('Получать дополнительные уведомления'),
    )

    def __init__(self, *args, user, profile, **kwargs):
        if (not args or args[0] is None) and 'initial' not in kwargs:
            kwargs['initial'] = {
                'first_name': user.first_name,
                'last_name': user.last_name,
                'email': user.email,
                'phone': user.phone,
                'preferred_language': user.preferred_language,
                'city': profile.city if profile else None,
                'contact': profile.contact if profile else '',
                'receive_optional_updates': (
                    profile.receive_optional_updates if profile else True
                ),
            }
        super().__init__(*args, **kwargs)
        self.owner = user
        self.fields['city'].queryset = get_public_cities()

    def clean_email(self):
        return self.cleaned_data.get('email', '').strip().casefold()

    def clean_phone(self):
        raw = self.cleaned_data.get('phone', '').strip()
        if not raw:
            return ''
        try:
            return normalize_israeli_phone(raw)
        except ValueError as exc:
            raise ValidationError(_('Некорректный израильский номер телефона.')) from exc

    def clean(self):
        result = super().clean()
        if (
            'email' in result and 'phone' in result
            and not result.get('email') and not result.get('phone')
            and (self.owner.email or self.owner.phone)
        ):
            raise ValidationError(
                _('Оставьте хотя бы один способ восстановления доступа.')
            )
        return result
