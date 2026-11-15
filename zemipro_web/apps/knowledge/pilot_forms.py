"""Bounded private forms; authorization and state checks are in pilot_services."""
from django import forms


class PilotConsentForm(forms.Form):
    action = forms.ChoiceField(choices=[
        ('consent', 'consent'), ('withdraw', 'withdraw'),
    ])
    confirmed = forms.BooleanField(required=False)


class PilotSelectionForm(forms.Form):
    action = forms.ChoiceField(choices=[
        ('select', 'select'), ('deselect', 'deselect'),
    ])
    article_id = forms.IntegerField(min_value=1)
    expected_version = forms.IntegerField(min_value=1)
