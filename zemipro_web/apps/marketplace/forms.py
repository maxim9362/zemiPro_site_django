from django import forms
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from core.forms import LocalizedModelChoiceField

from apps.locations.models import City
from apps.locations.services import get_public_cities
from .models import Category, Order, Response, Subcategory
from .questionnaire_forms import attach_questions, normalize_question_answers


class OrderCreateForm(forms.ModelForm):
    """Форма создания заявки на ремонт."""

    customer_name = forms.CharField(
        max_length=120,
        label=_('Ваше имя'),
        widget=forms.TextInput(attrs={
            'placeholder': _('Иван'),
        }),
    )
    customer_phone = forms.CharField(
        max_length=30, required=False,
        label=_('Телефон'),
        widget=forms.TextInput(attrs={
            'placeholder': '+972-XX-XXX-XXXX',
        }),
    )
    category = LocalizedModelChoiceField(
        queryset=Category.objects.filter(is_active=True).filter(
            Q(section__isnull=True) | Q(section__is_active=True)
        ),
        label=_('Категория'),
        empty_label=_('Выберите категорию'),
    )
    subcategory = LocalizedModelChoiceField(
        queryset=Subcategory.objects.none(),
        label=_('Подкатегория'),
        required=False,
        empty_label=_('— Не выбрана —'),
    )
    city = LocalizedModelChoiceField(
        queryset=City.objects.filter(is_active=True),
        label=_('Город'),
        empty_label=_('Выберите город'),
    )
    address = forms.CharField(
        max_length=255, required=False,
        label=_('Адрес'),
        widget=forms.TextInput(attrs={
            'placeholder': _('Адрес'),
        }),
    )
    description = forms.CharField(
        label=_('Описание задачи'),
        widget=forms.Textarea(attrs={
            'rows': 5,
            'placeholder': _('Подробно опишите задачу (минимум 30 символов)'),
        }),
    )
    price = forms.CharField(
        max_length=50,
        required=False,
        label=_('Бюджет'),
        widget=forms.TextInput(attrs={
            'placeholder': _('500 ₪ или Договорная'),
        }),
    )

    class Meta:
        model = Order
        fields = [
            'customer_name', 'customer_phone',
            'category', 'subcategory', 'city',
            'address', 'description', 'price',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set per instance: override_settings in pilot regression tests must work
        # even though the model field was declared at module import time.
        self.fields['city'].queryset = get_public_cities()
        if 'category' in self.data:
            try:
                cat_id = int(self.data.get('category'))
                self.fields['subcategory'].queryset = Subcategory.objects.filter(
                    category_id=cat_id, is_active=True, category__is_active=True
                )
            except (ValueError, TypeError):
                pass
        elif self.initial.get('category'):
            self.fields['subcategory'].queryset = Subcategory.objects.filter(
                category=self.initial['category'], is_active=True,
            )
        self.fields['questionnaire_version'] = forms.IntegerField(
            required=False, widget=forms.HiddenInput,
        )
        service_id = (
            self.data.get('subcategory') if self.is_bound
            else self.initial.get('subcategory')
        )
        try:
            attach_questions(self, int(service_id) if service_id else None)
        except (TypeError, ValueError):
            attach_questions(self, None)
        if self.active_questionnaire_version and not self.is_bound:
            self.initial['questionnaire_version'] = self.active_questionnaire_version.pk
        for item in self.questionnaire_questions:
            item['field'] = self[item['name']]

    def clean(self):
        values = super().clean()
        subcategory, category = values.get('subcategory'), values.get('category')
        if subcategory is not None and category is not None:
            if subcategory.category_id != category.pk:
                self.add_error('subcategory', _('Подуслуга не относится к выбранной категории.'))
        self.questionnaire_answers = normalize_question_answers(self)
        return values


    def clean_description(self):
        desc = self.cleaned_data.get('description', '')
        if len(desc) < 30:
            raise forms.ValidationError(_('Описание должно содержать минимум 30 символов.'))
        return desc

    def clean_customer_phone(self):
        phone = self.cleaned_data.get('customer_phone', '')
        if phone and len(phone) < 7:
            raise forms.ValidationError(_('Введите корректный номер телефона (минимум 7 символов).'))
        return phone

    def clean_price(self):
        price = self.cleaned_data.get('price', '').strip()
        if not price:
            return 'Договорная'
        return price


class ResponseCreateForm(forms.ModelForm):
    """Форма отклика мастера на заявку."""

    class Meta:
        model = Response
        fields = ['message']
        widgets = {
            'message': forms.Textarea(attrs={
                'rows': 4,
                'placeholder': _('Напишите короткое сообщение клиенту: когда сможете приехать, опыт, ориентировочная цена.'),
                'maxlength': 1000,
            }),
        }
        labels = {
            'message': _('Сообщение клиенту'),
        }
