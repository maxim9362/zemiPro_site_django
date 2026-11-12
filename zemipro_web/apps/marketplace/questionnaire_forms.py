"""Server-side authoritative dynamic fields from a published questionnaire."""
from django import forms
from django.core.exceptions import ValidationError

from .models import ServiceQuestionnaire
from .questionnaires import is_question_visible, localized_label


def question_field(item):
    kind = item['type']
    label = localized_label(item['labels'])
    args = {'label': label, 'required': False}
    if kind == 'text':
        return forms.CharField(max_length=500, widget=forms.TextInput, **args)
    if kind == 'number':
        return forms.DecimalField(
            max_digits=12, decimal_places=2,
            widget=forms.NumberInput(attrs={'step': '0.01'}), **args,
        )
    if kind == 'date':
        return forms.DateField(
            widget=forms.DateInput(attrs={'type': 'date'}), **args,
        )
    if kind == 'boolean':
        return forms.ChoiceField(
            choices=[('', '—'), ('true', 'Yes'), ('false', 'No')], **args,
        )
    choices = [(o['value'], localized_label(o['labels'])) for o in item['options']]
    if kind == 'single':
        return forms.ChoiceField(choices=[('', '—'), *choices], **args)
    if kind == 'multiple':
        return forms.MultipleChoiceField(
            choices=choices, widget=forms.CheckboxSelectMultiple, **args,
        )
    raise ValidationError('Unsupported questionnaire field type.')


def attach_questions(form, service_id):
    form.questionnaire_version = None
    form.questionnaire_questions = []
    if not service_id:
        return
    questionnaire = ServiceQuestionnaire.objects.select_related(
        'published_version'
    ).filter(service_id=service_id).first()
    if not questionnaire or not questionnaire.published_version_id:
        return
    version = questionnaire.published_version
    form.questionnaire_version = version
    for question in version.schema:
        name = 'q_' + question['key']
        form.fields[name] = question_field(question)
        form.questionnaire_questions.append({
            'key': question['key'], 'name': name, 'question': question,
        })


def normalize_question_answers(form):
    """Conditionally required, whitelist fields/options, and ignore invisible inputs."""
    if not form.questionnaire_version:
        if form.data.get('questionnaire_version'):
            form.add_error(None, 'The selected questionnaire is no longer available.')
        return {}
    supplied = str(form.data.get('questionnaire_version', ''))
    if form.is_bound and supplied != str(form.questionnaire_version.pk):
        form.add_error(None, 'Questionnaire changed; reload and answer current questions.')
        return {}

    answers = {}
    for item in form.questionnaire_questions:
        key, name, question = item['key'], item['name'], item['question']
        if not is_question_visible(question, answers):
            continue
        raw = form.cleaned_data.get(name)
        kind = question['type']
        if raw in (None, '', []):
            if question['required']:
                form.add_error(name, 'This question is required.')
            continue
        if kind == 'number':
            raw = str(raw)
        elif kind == 'date':
            raw = raw.isoformat()
        elif kind == 'boolean':
            raw = raw == 'true'
        answers[key] = raw
    return answers
