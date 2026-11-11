from django import forms
from django.utils.translation import gettext_lazy as _
from core.forms import LocalizedModelChoiceField, LocalizedModelMultipleChoiceField
from django.db.models import Q

from apps.locations.models import City
from .models import Category, Order, Response, Subcategory


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
        max_length=30,
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
        max_length=255,
        label=_('Адрес'),
        widget=forms.TextInput(attrs={
            'placeholder': _('Herzl 45, Тель-Авив'),
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
        if 'category' in self.data:
            try:
                cat_id = int(self.data.get('category'))
                self.fields['subcategory'].queryset = Subcategory.objects.filter(
                    category_id=cat_id, is_active=True, category__is_active=True
                )
            except (ValueError, TypeError):
                pass

    def clean_description(self):
        desc = self.cleaned_data.get('description', '')
        if len(desc) < 30:
            raise forms.ValidationError(_('Описание должно содержать минимум 30 символов.'))
        return desc

    def clean_customer_phone(self):
        phone = self.cleaned_data.get('customer_phone', '')
        if len(phone) < 7:
            raise forms.ValidationError(_('Введите корректный номер телефона (минимум 7 символов).'))
        return phone

    def clean_price(self):
        price = self.cleaned_data.get('price', '').strip()
        if not price:
            return _('Договорная')
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
            'message': 'Сообщение клиенту',
        }
