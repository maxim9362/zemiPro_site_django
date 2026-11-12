"""Validated, bounded, language-aware service question schemas (Stage 02.5)."""
import re

from django.core.exceptions import ValidationError
from django.utils.translation import get_language


KEY = re.compile(r'[a-z][a-z0-9_]{0,39}\Z')
TYPES = {'text', 'single', 'multiple', 'number', 'date', 'boolean'}
CHOICE_TYPES = {'single', 'multiple'}


def localized_label(names):
    code = (get_language() or 'ru').split('-')[0]
    return names.get(code) or names.get('ru', '')


def validate_question_schema(schema):
    """Reject malformed admin JSON before publishing. No code/eval/HTML allowed."""
    if not isinstance(schema, list) or len(schema) > 20:
        raise ValidationError('Schema must be a list of up to 20 questions.')
    seen = {}
    for i, question in enumerate(schema):
        if not isinstance(question, dict) or set(question) - {
            'key', 'type', 'labels', 'required', 'options', 'depends_on',
        }:
            raise ValidationError(f'Question {i}: unknown fields')
        key = question.get('key')
        kind = question.get('type')
        labels = question.get('labels')
        if not isinstance(key, str) or not KEY.fullmatch(key) or key in seen:
            raise ValidationError(f'Question {i}: invalid or duplicate key')
        if kind not in TYPES or type(question.get('required')) is not bool:
            raise ValidationError(f'Question {key}: type/required invalid')
        if not isinstance(labels, dict) or set(labels) != {'ru', 'en', 'he'}:
            raise ValidationError(f'Question {key}: RU/EN/HE labels required')
        if any(
            not isinstance(s, str) or not s.strip() or len(s) > 160
            for s in labels.values()
        ):
            raise ValidationError(f'Question {key}: invalid translated label')
        options = question.get('options', [])
        if kind in CHOICE_TYPES:
            if not isinstance(options, list) or not 2 <= len(options) <= 20:
                raise ValidationError(f'Question {key}: 2-20 options required')
            option_keys = set()
            for option in options:
                if not isinstance(option, dict) or set(option) != {'value', 'labels'}:
                    raise ValidationError(f'Question {key}: invalid option')
                val, names = option['value'], option['labels']
                if (
                    not isinstance(val, str) or not KEY.fullmatch(val)
                    or val in option_keys or not isinstance(names, dict)
                    or set(names) != {'ru', 'en', 'he'}
                    or any(
                        not isinstance(s, str) or not s.strip() or len(s) > 120
                        for s in names.values()
                    )
                ):
                    raise ValidationError(f'Question {key}: invalid option value/label')
                option_keys.add(val)
        elif options:
            raise ValidationError(f'Question {key}: options not permitted')
        condition = question.get('depends_on')
        if condition is not None:
            if (
                not isinstance(condition, dict)
                or set(condition) != {'key', 'equals'}
                or condition['key'] not in seen
            ):
                raise ValidationError(f'Question {key}: invalid dependency')
            previous = seen[condition['key']]
            if previous['type'] == 'single':
                allowed = {item['value'] for item in previous['options']}
                if condition['equals'] not in allowed:
                    raise ValidationError(f'Question {key}: unknown dependency option')
            elif previous['type'] == 'boolean':
                if type(condition['equals']) is not bool:
                    raise ValidationError(f'Question {key}: boolean dependency expected')
            else:
                raise ValidationError(f'Question {key}: only single/boolean dependencies')
            # One level of dependencies prevents invisible required grandchildren.
            if previous.get('depends_on'):
                raise ValidationError(f'Question {key}: chained dependencies unsupported')
        seen[key] = question
    return schema


def is_question_visible(question, answers):
    condition = question.get('depends_on')
    if not condition:
        return True
    return answers.get(condition['key']) == condition['equals']
