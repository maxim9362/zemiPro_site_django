"""Stage 04.2 wizard persistence and publication, without external side effects."""
from datetime import date
from decimal import Decimal
import uuid

from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.locations.services import city_is_public, get_public_cities

from .models import (
    Category, Order, OrderQuestionnaireAnswer, OrderStatusEvent,
    ServiceQuestionnaire, Subcategory,
)
from .order_lifecycle import transition_order_status
from .wizard_forms import active_categories, active_services
from .wizard_ui import wizard_copy


def ensure_wizard_owner(user):
    """Persisted, not stale-session, authorization for every wizard write."""
    if not getattr(user, 'is_authenticated', False):
        raise PermissionDenied(wizard_copy()['not_eligible'])
    if not User.objects.filter(
        pk=user.pk, is_active=True, is_blocked=False,
        email_verification_required=False,
    ).exists():
        raise PermissionDenied(wizard_copy()['not_eligible'])


def get_owner_wizard(order_id, user, *, for_update=False):
    ensure_wizard_owner(user)
    query = Order.objects
    if for_update:
        query = query.select_for_update()
    # No access to drafts owned by another account, even if IDs are guessed.
    return query.filter(pk=order_id, client_id=user.pk, wizard_token__isnull=False).first()


def _step_data(form, step):
    d = form.cleaned_data
    if step == 1:
        return {'category_id': d['category'].pk, 'subcategory_id': d['subcategory'].pk}
    if step == 2:
        return {
            'version_id': (
                form.active_questionnaire_version.pk
                if form.active_questionnaire_version else None
            ),
            'answers': form.questionnaire_answers,
        }
    if step == 3:
        return {'city_id': d['city'].pk, 'mode': d['mode'], 'area': d['area']}
    if step == 4:
        return {
            'preferred_date': d['preferred_date'].isoformat() if d['preferred_date'] else '',
            'urgency': d['urgency'],
        }
    if step == 5:
        return {
            'price_type': d['price_type'],
            'amount_min': str(d['amount_min']) if d['amount_min'] is not None else '',
            'amount_max': str(d['amount_max']) if d['amount_max'] is not None else '',
        }
    if step == 6:
        return {'description': d['description']}
    if step == 7:
        return {'display_name': d['display_name'], 'chat_only': bool(d['chat_ack'])}
    raise ValueError('Unsupported wizard step.')


def _next_step(steps):
    for number in range(1, 8):
        if str(number) not in steps:
            return number
    return 8


def wizard_max_step(order):
    return _next_step(order.wizard_data.get('steps', {}))


def start_order_wizard(*, actor, form, token):
    """Create a single owner-bound draft, even across repeated/racing submissions."""
    ensure_wizard_owner(actor)
    if not form.is_valid():
        raise ValueError('Invalid service selection.')
    try:
        key = uuid.UUID(str(token))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError('Invalid wizard token.') from exc

    with transaction.atomic():
        existing = Order.objects.select_for_update().filter(wizard_token=key).first()
        if existing is not None:
            if existing.client_id != actor.pk:
                raise PermissionDenied(wizard_copy()['not_eligible'])
            return existing
        city = get_public_cities().order_by('pk').first()
        if city is None:
            raise ValueError(wizard_copy()['no_city'])
        values = _step_data(form, 1)
        try:
            # Savepoint makes a parallel duplicate token safe without aborting
            # the outer transaction (PostgreSQL unique index).
            with transaction.atomic():
                order = Order.objects.create(
                    client_id=actor.pk,
                    category_id=values['category_id'],
                    subcategory_id=values['subcategory_id'],
                    city=city, address='', description='',
                    status=Order.Status.DRAFT, wizard_token=key,
                    wizard_data={'steps': {'1': values}},
                )
                OrderStatusEvent.objects.create(
                    order=order, actor_id=actor.pk, previous_status='',
                    new_status=Order.Status.DRAFT,
                    reason=OrderStatusEvent.Reason.CREATED,
                )
        except IntegrityError:
            existing = Order.objects.select_for_update().get(wizard_token=key)
            if existing.client_id != actor.pk:
                raise PermissionDenied(wizard_copy()['not_eligible']) from None
            return existing
        return order


def save_order_wizard_step(*, order_id, actor, step, form):
    """Persist one validated step; changing service invalidates later answers."""
    if step < 1 or step > 7:
        raise ValueError('Invalid step.')
    ensure_wizard_owner(actor)
    if not form.is_valid():
        raise ValueError('Invalid form.')
    values = _step_data(form, step)
    with transaction.atomic():
        order = get_owner_wizard(order_id, actor, for_update=True)
        if order is None or order.status != Order.Status.DRAFT:
            raise PermissionDenied(wizard_copy()['not_eligible'])
        existing = dict((order.wizard_data or {}).get('steps') or {})
        if step > _next_step(existing):
            raise ValueError(wizard_copy()['incomplete'])
        if step == 1:
            previous = existing.get('1')
            if previous != values:
                existing = {}
                order.category_id = values['category_id']
                order.subcategory_id = values['subcategory_id']
                order.save(update_fields=['category', 'subcategory', 'updated_at'])
        elif step == 2:
            # Confirm that the questionnaire still belongs to the selected service.
            template = ServiceQuestionnaire.objects.filter(
                service_id=order.subcategory_id,
            ).first()
            current = template.published_version_id if template else None
            if values['version_id'] != current:
                raise ValueError(wizard_copy()['changed'])
        elif step == 3:
            if not city_is_public(form.cleaned_data['city']):
                raise ValueError(wizard_copy()['no_city'])
            order.city_id = values['city_id']
            order.save(update_fields=['city', 'updated_at'])

        existing[str(step)] = values
        order.wizard_data = {'steps': existing}
        order.save(update_fields=['wizard_data', 'updated_at'])
        return order


def wizard_initial(order, step):
    values = (order.wizard_data or {}).get('steps', {}).get(str(step), {})
    if step == 1:
        return {
            'category': values.get('category_id', order.category_id),
            'subcategory': values.get('subcategory_id', order.subcategory_id),
        }
    if step == 2:
        return values.get('answers', {})
    if step == 3:
        return {
            'city': values.get('city_id', order.city_id),
            'mode': values.get('mode', 'onsite'),
            'area': values.get('area', ''),
        }
    if step == 4:
        return {
            'preferred_date': values.get('preferred_date', ''),
            'urgency': values.get('urgency', 'normal'),
        }
    if step == 5:
        return {
            'price_type': values.get('price_type', 'negotiable'),
            'amount_min': values.get('amount_min', ''),
            'amount_max': values.get('amount_max', ''),
        }
    if step == 6:
        return {'description': values.get('description', '')}
    if step == 7:
        return {'display_name': values.get('display_name', ''), 'chat_ack': True}
    return {}


def _budget_label(values):
    kind = values['price_type']
    if kind == 'fixed':
        return f"{Decimal(values['amount_min']):.2f} ₪"
    if kind == 'range':
        return (f"{Decimal(values['amount_min']):.2f}"
                f"–{Decimal(values['amount_max']):.2f} ₪")
    return 'Договорная'


def wizard_summary(order):
    """Only for owner-authenticated draft pages; no public serializer."""
    steps = order.wizard_data.get('steps', {})
    t = wizard_copy()
    place = steps.get('3', {})
    return [
        (t['service'], order.subcategory.localized_name if order.subcategory else t['not_set']),
        (t['city'], order.city.localized_name),
        (t['mode'], t.get(place.get('mode'), t['not_set'])),
        (t['area'], place.get('area') or t['not_set']),
        (t['date'], steps.get('4', {}).get('preferred_date') or t['no_date']),
        (t['urgency'], t.get(steps.get('4', {}).get('urgency'), t['not_set'])),
        (t['price_type'], _budget_label(steps['5']) if '5' in steps else t['not_set']),
        (t['description'], steps.get('6', {}).get('description') or t['not_set']),
    ]


def publish_order_wizard(*, order_id, actor):
    """Verify all saved steps before atomically publishing exactly once."""
    ensure_wizard_owner(actor)
    with transaction.atomic():
        order = get_owner_wizard(order_id, actor, for_update=True)
        if order is None:
            raise PermissionDenied(wizard_copy()['not_eligible'])
        if order.status == Order.Status.PUBLISHED:
            return order, False
        if order.status != Order.Status.DRAFT:
            raise ValueError(wizard_copy()['incomplete'])
        steps = (order.wizard_data or {}).get('steps', {})
        if _next_step(steps) != 8:
            raise ValueError(wizard_copy()['incomplete'])

        chosen = steps['1']
        if not active_categories().filter(pk=chosen['category_id']).exists():
            raise ValueError(wizard_copy()['no_service'])
        if not active_services(chosen['category_id']).filter(
            pk=chosen['subcategory_id'],
        ).exists():
            raise ValueError(wizard_copy()['no_service'])
        place = steps['3']
        city = get_public_cities().filter(pk=place['city_id']).first()
        if city is None or not city_is_public(city):
            raise ValueError(wizard_copy()['no_city'])
        service = Subcategory.objects.get(pk=chosen['subcategory_id'])
        if service.work_mode != 'both' and place['mode'] != service.work_mode:
            raise ValueError(wizard_copy()['incomplete'])
        preferred = steps['4'].get('preferred_date', '')
        if preferred and date.fromisoformat(preferred) < timezone.localdate():
            raise ValueError(wizard_copy()['incomplete'])

        questionnaire = ServiceQuestionnaire.objects.select_related(
            'published_version',
        ).filter(service_id=service.pk).first()
        version = questionnaire.published_version if questionnaire else None
        questions = steps['2']
        if questions['version_id'] != (version.pk if version else None):
            raise ValueError(wizard_copy()['changed'])
        if not steps['6']['description'].strip() and not questions['answers']:
            raise ValueError(wizard_copy()['no_description'])
        if not steps['7'].get('chat_only'):
            raise ValueError(wizard_copy()['incomplete'])

        order.category_id = chosen['category_id']
        order.subcategory_id = service.pk
        order.city = city
        order.price = _budget_label(steps['5'])
        order.description = steps['6']['description']
        order.customer_name = steps['7']['display_name']
        # Private phone/address are shared voluntarily in Stage 07 chat only.
        order.customer_phone = ''
        order.address = ''
        order.save(update_fields=[
            'category', 'subcategory', 'city', 'price', 'description',
            'customer_name', 'customer_phone', 'address', 'updated_at',
        ])
        if version:
            OrderQuestionnaireAnswer.objects.create(
                order=order, version=version,
                schema_snapshot=version.schema,
                answers=questions['answers'],
            )
        order = transition_order_status(
            order, Order.Status.PUBLISHED, actor=actor,
        )
        return order, True
