from django import forms

from apps.locations.models import City
from apps.marketplace.models import Category, Rating
from .models import ClientProfile, WorkerProfile


class ClientProfileForm(forms.ModelForm):
    """Форма профиля клиента."""

    city = forms.ModelChoiceField(
        queryset=City.objects.filter(is_active=True),
        label='Город',
        empty_label='Выберите город',
    )

    class Meta:
        model = ClientProfile
        fields = ['city', 'contact']
        widgets = {
            'contact': forms.TextInput(attrs={
                'placeholder': '+972-XX-XXX-XXXX или @username',
            }),
        }


class WorkerProfileForm(forms.ModelForm):
    """Форма профиля мастера."""

    city = forms.ModelChoiceField(
        queryset=City.objects.filter(is_active=True),
        label='Город',
        empty_label='Выберите город',
    )
    skills = forms.ModelMultipleChoiceField(
        queryset=Category.objects.filter(is_active=True),
        label='Категории работ',
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = WorkerProfile
        fields = ['city', 'contact', 'description', 'skills', 'receive_notifications']
        widgets = {
            'contact': forms.TextInput(attrs={
                'placeholder': '+972-XX-XXX-XXXX или @username',
            }),
            'description': forms.Textarea(attrs={
                'rows': 4,
                'placeholder': 'Опишите ваш опыт, инструменты, особенности работы (минимум 20 символов)',
            }),
        }

    def clean_description(self):
        desc = self.cleaned_data.get('description', '')
        if len(desc) < 20:
            raise forms.ValidationError('Описание должно содержать минимум 20 символов.')
        return desc


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
                'placeholder': 'Расскажите о качестве работы (необязательно)',
            }),
        }
        labels = {
            'rating': 'Оценка (от 1 до 5)',
            'review_text': 'Текст отзыва',
        }
