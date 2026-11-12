"""Stage 04.5 server-authorized order management; no hidden client privileges."""
import uuid

from django import forms
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone

from apps.locations.services import city_is_public, get_public_cities

from .models import (
    Order, OrderManagementEvent, OrderQuestionnaireAnswer, OrderStatusEvent,
    Response,
)
from .order_lifecycle import transition_order_status
from .wizard_forms import validate_approximate_area
from .wizard_services import ensure_wizard_owner
from .wizard_ui import wizard_copy
from .order_quota import consume_order_quota


def _operation_key(value):
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError('Invalid order operation key.') from exc


def owner_order(order_id, actor, *, lock=False):
    """Never trust an Order instance or HTTP-supplied client ID for mutation."""
    ensure_wizard_owner(actor)
    qs = Order.objects.select_for_update() if lock else Order.objects
    order = qs.filter(pk=order_id, client_id=actor.pk).first()
    if order is None:
        raise PermissionDenied('Нет права управлять заявкой.')
    return order


class OrderEditForm(forms.Form):
    """Safe, bounded edits to existing published conditions before assignment."""

    price_kind = forms.ChoiceField()
    amount_min_ils = forms.DecimalField(
        max_digits=9, decimal_places=2, min_value=0, required=False,
    )
    amount_max_ils = forms.DecimalField(
        max_digits=9, decimal_places=2, min_value=0, required=False,
    )
    preferred_date = forms.DateField(
        required=False, widget=forms.DateInput(attrs={'type': 'date'}),
    )
    urgency = forms.ChoiceField()
    work_mode = forms.ChoiceField()
    approximate_area = forms.CharField(max_length=80, required=False)
    description = forms.CharField(
        required=False, max_length=4000,
        widget=forms.Textarea(attrs={'rows': 5}),
    )

    def __init__(self, *args, order, **kwargs):
        super().__init__(*args, **kwargs)
        self.order = order
        t = wizard_copy()
        self.fields['price_kind'].label = t['price_type']
        self.fields['amount_min_ils'].label = t['amount_min']
        self.fields['amount_max_ils'].label = t['amount_max']
        self.fields['preferred_date'].label = t['date']
        self.fields['urgency'].label = t['urgency']
        self.fields['work_mode'].label = t['mode']
        self.fields['approximate_area'].label = t['area']
        self.fields['description'].label = t['description']
        kinds = [
            ('negotiable', t['negotiable']),
            ('fixed', t['fixed']),
            ('range', t['range']),
        ]
        if order.price_kind == Order.PriceKind.LEGACY:
            kinds.insert(0, ('legacy', order.price))
        self.fields['price_kind'].choices = kinds
        self.fields['urgency'].choices = [
            ('legacy', t['not_set']),
            ('normal', t['normal']), ('soon', t['soon']), ('urgent', t['urgent']),
        ]
        service_mode = (
            order.subcategory.work_mode if order.subcategory_id
            else order.category.work_mode
        )
        modes = [('onsite', t['onsite']), ('online', t['online'])]
        if service_mode != 'both':
            modes = [x for x in modes if x[0] == service_mode]
        if order.work_mode == Order.WorkMode.LEGACY:
            modes.insert(0, ('legacy', t['not_set']))
        self.fields['work_mode'].choices = modes
        if not self.is_bound:
            self.initial = {
                'price_kind': order.price_kind,
                'amount_min_ils': order.amount_min_ils,
                'amount_max_ils': order.amount_max_ils,
                'preferred_date': order.preferred_date,
                'urgency': order.urgency,
                'work_mode': order.work_mode,
                'approximate_area': order.approximate_area,
                'description': order.description,
            }

    def clean_approximate_area(self):
        return validate_approximate_area(self.cleaned_data.get('approximate_area', ''))

    def clean_preferred_date(self):
        value = self.cleaned_data.get('preferred_date')
        if value and value < timezone.localdate():
            raise forms.ValidationError(wizard_copy()['date'])
        return value

    def clean(self):
        data = super().clean()
        kind = data.get('price_kind')
        lo, hi = data.get('amount_min_ils'), data.get('amount_max_ils')
        if kind == 'legacy':
            if lo is not None or hi is not None:
                self.add_error('amount_min_ils', wizard_copy()['price_type'])
        elif kind == 'negotiable':
            if lo is not None or hi is not None:
                self.add_error('amount_min_ils', wizard_copy()['price_type'])
        elif kind == 'fixed':
            if lo is None:
                self.add_error('amount_min_ils', wizard_copy()['amount_min'])
            if hi is not None:
                self.add_error('amount_max_ils', wizard_copy()['amount_max'])
        elif kind == 'range':
            if lo is None:
                self.add_error('amount_min_ils', wizard_copy()['amount_min'])
            if hi is None or (lo is not None and hi < lo):
                self.add_error('amount_max_ils', wizard_copy()['amount_max'])
        if not (data.get('description') or '').strip():
            if not OrderQuestionnaireAnswer.objects.filter(order=self.order).exists():
                self.add_error('description', wizard_copy()['no_description'])
        return data


def _edit_price(data, old_price):
    kind = data['price_kind']
    if kind == 'legacy':
        return old_price
    if kind == 'negotiable':
        return 'Договорная'
    if kind == 'fixed':
        return f"{data['amount_min_ils']:.2f} ₪"
    return f"{data['amount_min_ils']:.2f}–{data['amount_max_ils']:.2f} ₪"


EDIT_FIELDS = (
    'price_kind', 'amount_min_ils', 'amount_max_ils', 'preferred_date',
    'urgency', 'work_mode', 'approximate_area', 'description',
)


@transaction.atomic
def edit_published_order(*, order_id, actor, data, operation_key):
    """Revalidate while holding the order row lock; audit field NAMES only."""
    op = _operation_key(operation_key)
    order = owner_order(order_id, actor, lock=True)
    previous = OrderManagementEvent.objects.filter(
        order=order, operation_key=op,
    ).first()
    if previous:
        if previous.action != OrderManagementEvent.Action.EDITED:
            raise ValueError('Operation key already used.')
        return order, False
    if order.status not in (Order.Status.PUBLISHED, Order.Status.IN_DISCUSSION):
        raise ValueError('Нельзя редактировать заявку после назначения мастера.')
    if order.worker_id:
        raise ValueError('Нельзя редактировать заявку после назначения мастера.')
    form = OrderEditForm(data=data, order=order)
    if not form.is_valid():
        return form, False

    values = form.cleaned_data
    changed = []
    for field in EDIT_FIELDS:
        if getattr(order, field) != values[field]:
            changed.append(field)
            setattr(order, field, values[field])
    updated_price = _edit_price(values, order.price)
    if updated_price != order.price:
        order.price = updated_price
        changed.append('price')
    if not changed:
        return order, False

    consume_order_quota(actor, 'edit')
    # Preserve current wizard values for any later allowed withdrawal/edit.
    if order.wizard_token and (order.wizard_data or {}).get('steps'):
        steps = dict(order.wizard_data['steps'])
        if '3' in steps and values['work_mode'] != 'legacy':
            steps['3'] = {**steps['3'], 'mode': values['work_mode'],
                          'area': values['approximate_area']}
        if '4' in steps:
            steps['4'] = {
                'preferred_date': values['preferred_date'].isoformat()
                if values['preferred_date'] else '',
                'urgency': values['urgency'] if values['urgency'] != 'legacy' else 'normal',
            }
        if '5' in steps and values['price_kind'] != 'legacy':
            steps['5'] = {
                'price_type': values['price_kind'],
                'amount_min': str(values['amount_min_ils'])
                if values['amount_min_ils'] is not None else '',
                'amount_max': str(values['amount_max_ils'])
                if values['amount_max_ils'] is not None else '',
            }
        if '6' in steps:
            steps['6'] = {'description': values['description']}
        order.wizard_data = {**order.wizard_data, 'steps': steps}
        changed.append('wizard_data')
    order.save(update_fields=list(set(changed + ['updated_at'])))
    # No description, address, phone, neighborhood text, price values, or
    # private questionnaire answers are copied to the audit event.
    OrderManagementEvent.objects.create(
        order=order, actor_id=actor.pk,
        action=OrderManagementEvent.Action.EDITED,
        changed_fields=[x for x in changed if x != 'wizard_data'],
        operation_key=op,
    )
    return order, True


def _duplicate_prefill(original):
    """Never copy phone/address, files or direct assignment to a new draft."""
    steps = (original.wizard_data or {}).get('steps') or {}
    place = {
        'city_id': original.city_id,
        'mode': original.work_mode if original.work_mode != 'legacy' else 'onsite',
        'area': original.approximate_area,
    }
    schedule = {
        'preferred_date': original.preferred_date.isoformat()
        if original.preferred_date and original.preferred_date >= timezone.localdate() else '',
        'urgency': original.urgency if original.urgency != 'legacy' else 'normal',
    }
    budget = {
        'price_type': original.price_kind if original.price_kind != 'legacy' else 'negotiable',
        'amount_min': str(original.amount_min_ils) if original.amount_min_ils is not None else '',
        'amount_max': str(original.amount_max_ils) if original.amount_max_ils is not None else '',
    }
    existing_answer = OrderQuestionnaireAnswer.objects.filter(order=original).first()
    return {
        '2': {'answers': dict(existing_answer.answers) if existing_answer else
              dict(steps.get('2', {}).get('answers', {}))},
        '3': place, '4': schedule, '5': budget,
        '6': {'description': original.description[:4000]},
        '7': {'display_name': original.customer_name[:120]},
    }


@transaction.atomic
def duplicate_order(*, order_id, actor, operation_key):
    """Exactly one private draft per idempotent operation, no cloned contacts."""
    op = _operation_key(operation_key)
    source = owner_order(order_id, actor, lock=True)
    existing = OrderManagementEvent.objects.filter(
        order=source, operation_key=op,
    ).first()
    if existing:
        if (existing.action != OrderManagementEvent.Action.DUPLICATED
                or existing.target_order_id is None):
            raise ValueError('Operation key already used.')
        return existing.target_order, False

    if not city_is_public(source.city):
        # Old out-of-pilot orders can still be duplicated, but new drafts must
        # select an available city and never re-publish the foreign one.
        city = get_public_cities().order_by('pk').first()
    else:
        city = source.city
    if city is None:
        raise ValueError(wizard_copy()['no_city'])

    from .wizard_forms import active_services
    valid_service = (
        source.subcategory_id is not None and active_services(
            source.category_id,
        ).filter(pk=source.subcategory_id).exists()
    )
    if valid_service:
        first = {'category_id': source.category_id,
                 'subcategory_id': source.subcategory_id}
        steps = {'1': first}
    else:
        # Service selection is required for old category-only orders.
        steps = {}
    consume_order_quota(actor, 'create')
    clone = Order.objects.create(
        client_id=actor.pk, category_id=source.category_id,
        subcategory_id=source.subcategory_id if valid_service else None,
        city=city, status=Order.Status.DRAFT, wizard_token=uuid.uuid4(),
        address='', customer_phone='', customer_name='',
        description='', price='Договорная',
        wizard_data={'steps': steps, 'prefill': _duplicate_prefill(source)},
    )
    OrderStatusEvent.objects.create(
        order=clone, actor_id=actor.pk,
        previous_status='', new_status=Order.Status.DRAFT,
        reason=OrderStatusEvent.Reason.CREATED,
    )
    OrderManagementEvent.objects.create(
        order=source, actor_id=actor.pk,
        action=OrderManagementEvent.Action.DUPLICATED,
        changed_fields=[], target_order=clone, operation_key=op,
    )
    return clone, True


@transaction.atomic
def withdraw_order(*, order_id, actor, operation_key):
    """Withdraw a request to an owner-only draft, only before any response."""
    op = _operation_key(operation_key)
    order = owner_order(order_id, actor, lock=True)
    event = OrderStatusEvent.objects.filter(
        order=order, operation_key=op,
    ).first()
    if event:
        if event.new_status != Order.Status.DRAFT:
            raise ValueError('Operation key already used.')
        return order, False
    if order.status not in (Order.Status.PUBLISHED, Order.Status.IN_DISCUSSION):
        raise ValueError('Заявку нельзя снять с публикации.')
    if order.worker_id or Response.objects.filter(order=order).exists():
        raise ValueError('При наличии откликов используйте отмену заявки.')
    # If this is a legacy order, make it resumable without publishing its
    # precise address/phone or duplicating an existing visible order.
    if not order.wizard_token:
        order.wizard_token = uuid.uuid4()
        order.wizard_data = {
            'steps': {}, 'prefill': _duplicate_prefill(order),
        }
        order.save(update_fields=['wizard_token', 'wizard_data', 'updated_at'])
    result = transition_order_status(
        order.pk, Order.Status.DRAFT, actor=actor, operation_key=op,
    )
    return result, True


def management_timeline(order):
    """Merged deterministic owner-only lifecycle and management history."""
    events = [
        {'when': e.occurred_at, 'id': e.pk, 'kind': 'status',
         'summary': e.get_new_status_display(), 'changed': ()}
        for e in order.status_events.all()
    ]
    events += [
        {'when': e.occurred_at, 'id': e.pk, 'kind': 'management',
         'summary': e.get_action_display(), 'changed': e.changed_fields}
        for e in order.management_events.all()
    ]
    return sorted(events, key=lambda e: (e['when'], e['kind'], e['id']))
