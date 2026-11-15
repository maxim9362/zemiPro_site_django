from django import forms

from .models import SeoContentPage, SeoLegacyUrl


class SeoContentPageForm(forms.ModelForm):
    expected_version = forms.IntegerField(widget=forms.HiddenInput, required=False)

    class Meta:
        model = SeoContentPage
        fields = (
            'page_type', 'language', 'section', 'category', 'service', 'city',
            'topic', 'title', 'meta_description', 'summary', 'body', 'source_facts',
        )


class SeoContentEditForm(forms.ModelForm):
    expected_version = forms.IntegerField(widget=forms.HiddenInput)

    class Meta:
        model = SeoContentPage
        fields = (
            'topic', 'title', 'meta_description', 'summary', 'body', 'source_facts',
        )


class SeoLegacyUrlForm(forms.ModelForm):
    class Meta:
        model = SeoLegacyUrl
        fields = (
            'path', 'page_type', 'decision', 'target_path', 'redirect_status',
            'evidence_source',
        )
