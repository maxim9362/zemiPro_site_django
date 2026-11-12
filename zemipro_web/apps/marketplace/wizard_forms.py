"""Bounded, localized server-side forms for stage 04.2 order wizard."""
from datetime import date

from django import forms
from django.db.models import Q
from django.utils import timezone

from apps.locations.models import City
from apps.locations.services import get_public_cities
from core.forms import LocalizedModelChoiceField

from .models import Category, Subcategory
from .questionnaire_forms import attach_questions, normalize_question_answers
from .wizard_ui import wizard_copy


def active_categories():
    return Category.objects.filter(is_active=True).filter(
        Q(section__isnull=True) | Q(section__is_active=True)
    )


def active_services(category_id):
    return Subcategory.objects.filter(
        is_active=True, category__in=active_categories(),
        category_id=category_id,
    )


class ServiceStepForm(forms.Form):
    category = LocalizedModelChoiceField(
        queryset=Category.objects.none(), empty_label='—',
    )
    subcategory = LocalizedModelChoiceField(
        queryset=Subcategory.objects.none(), empty_label='—',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        t = wizard_copy()
        self.fields['category'].label = t['category']
        self.fields['subcategory'].label = t['service']
        self.fields['category'].queryset = active_categories()
        cat_id = self.data.get('category') if self.is_bound else self.initial.get('category')
        try:
            self.fields['subcategory'].queryset = active_services(int(cat_id))
        except (ValueError, TypeError):
            pass

    def clean(self):
        data = super().clean()
        cat, service = data.get('category'), data.get('subcategory')
        if cat and service and cat.pk != service.category_id:
            self.add_error('subcategory', wizard_copy()['no_service'])
        return data


class QuestionsStepForm(forms.Form):
    def __init__(self, *args, service_id, stored_answers=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['questionnaire_version'] = forms.IntegerField(
            required=False, widget=forms.HiddenInput,
        )
        attach_questions(self, service_id)
        if self.active_questionnaire_version and not self.is_bound:
            self.initial['questionnaire_version'] = self.active_questionnaire_version.pk
        for item in self.questionnaire_questions:
            value = (stored_answers or {}).get(item['key'])
            if value is not None and not self.is_bound:
                if isinstance(value, bool):
                    value = 'true' if value else 'false'
                self.initial[item['name']] = value
            item['field'] = self[item['name']]

    def clean(self):
        data = super().clean()
        self.questionnaire_answers = normalize_question_answers(self)
        return data


class PlaceStepForm(forms.Form):
    city = LocalizedModelChoiceField(queryset=City.objects.none(), empty_label='—')
    mode = forms.ChoiceField(choices=())
    area = forms.CharField(max_length=80, required=False)

    def __init__(self, *args, service, **kwargs):
        super().__init__(*args, **kwargs)
        t = wizard_copy()
        self.fields['city'].queryset = get_public_cities()
        self.fields['city'].label = t['city']
        self.fields['area'].label = t['area']
        self.fields['mode'].label = t['mode']
        if service.work_mode == 'onsite':
            choices = [('onsite', t['onsite'])]
        elif service.work_mode == 'online':
            choices = [('online', t['online'])]
        else:
            choices = [('onsite', t['onsite']), ('online', t['online'])]
        self.fields['mode'].choices = choices


class ScheduleStepForm(forms.Form):
    preferred_date = forms.DateField(
        required=False, widget=forms.DateInput(attrs={'type': 'date'}),
    )
    urgency = forms.ChoiceField(choices=())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        t = wizard_copy()
        self.fields['preferred_date'].label = t['date']
        self.fields['urgency'].label = t['urgency']
        self.fields['urgency'].choices = [
            ('normal', t['normal']), ('soon', t['soon']), ('urgent', t['urgent']),
        ]

    def clean_preferred_date(self):
        value = self.cleaned_data.get('preferred_date')
        if value and value < timezone.localdate():
            raise forms.ValidationError(wizard_copy()['date'] + ': ' + str(date.today()))
        return value


class BudgetStepForm(forms.Form):
    price_type = forms.ChoiceField(choices=())
    amount_min = forms.DecimalField(
        max_digits=9, decimal_places=2, min_value=0, required=False,
    )
    amount_max = forms.DecimalField(
        max_digits=9, decimal_places=2, min_value=0, required=False,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        t = wizard_copy()
        for name in ('price_type', 'amount_min', 'amount_max'):
            self.fields[name].label = t[name]
        self.fields['price_type'].choices = [
            ('negotiable', t['negotiable']), ('fixed', t['fixed']),
            ('range', t['range']),
        ]

    def clean(self):
        d = super().clean()
        kind, lower, upper = d.get('price_type'), d.get('amount_min'), d.get('amount_max')
        if kind in ('fixed', 'range') and lower is None:
            self.add_error('amount_min', wizard_copy()['amount_min'])
        if kind == 'range' and (upper is None or (lower is not None and upper < lower)):
            self.add_error('amount_max', wizard_copy()['amount_max'])
        return d


class DescriptionStepForm(forms.Form):
    description = forms.CharField(
        required=False, max_length=4000,
        widget=forms.Textarea(attrs={'rows': 5}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['description'].label = wizard_copy()['description']


class ContactStepForm(forms.Form):
    display_name = forms.CharField(max_length=120, required=False)
    chat_ack = forms.BooleanField(required=True, initial=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        t = wizard_copy()
        self.fields['display_name'].label = t['display_name']
        self.fields['chat_ack'].label = t['chat_ack']


class ConfirmStepForm(forms.Form):
    confirm = forms.BooleanField(required=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['confirm'].label = wizard_copy()['confirm']


STEP_FORMS = {
    1: ServiceStepForm, 2: QuestionsStepForm, 3: PlaceStepForm,
    4: ScheduleStepForm, 5: BudgetStepForm, 6: DescriptionStepForm,
    7: ContactStepForm, 8: ConfirmStepForm,
}
