"""Reusable Django choice fields that render localized catalog/city labels."""
from django import forms


class LocalizedModelChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return getattr(obj, 'localized_name', None) or str(obj)


class LocalizedModelMultipleChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, obj):
        return getattr(obj, 'localized_name', None) or str(obj)
