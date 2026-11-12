"""Publish immutable questionnaire versions and render private historical answers."""
from copy import deepcopy

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max
from django.utils.translation import gettext as _

from .models import QuestionnaireVersion, ServiceQuestionnaire
from .questionnaires import localized_label, validate_question_schema


@transaction.atomic
def publish_questionnaire(questionnaire_id):
    questionnaire = ServiceQuestionnaire.objects.select_for_update().get(pk=questionnaire_id)
    validate_question_schema(questionnaire.draft_schema)
    if not questionnaire.draft_schema:
        raise ValidationError('Cannot publish an empty questionnaire.')
    current = questionnaire.published_version
    if current is not None and current.schema == questionnaire.draft_schema:
        return current, False
    latest = QuestionnaireVersion.objects.filter(
        questionnaire=questionnaire,
    ).aggregate(number=Max('number'))['number'] or 0
    version = QuestionnaireVersion.objects.create(
        questionnaire=questionnaire,
        number=latest + 1,
        schema=deepcopy(questionnaire.draft_schema),
    )
    questionnaire.published_version = version
    questionnaire.full_clean()
    questionnaire.save(update_fields=['published_version', 'updated_at'])
    return version, True


def present_order_answers(snapshot):
    """Display old labels/options from the order snapshot, never a new template."""
    result = []
    for item in snapshot.schema_snapshot:
        key, kind = item['key'], item['type']
        if key not in snapshot.answers:
            continue
        answer = snapshot.answers[key]
        if kind in ('single', 'multiple'):
            options = {o['value']: localized_label(o['labels']) for o in item['options']}
            selected = answer if kind == 'multiple' else [answer]
            pretty = ', '.join(options.get(v, v) for v in selected)
        elif kind == 'boolean':
            pretty = _('Да') if answer else _('Нет')
        else:
            pretty = str(answer)
        result.append({'label': localized_label(item['labels']), 'value': pretty})
    return result
