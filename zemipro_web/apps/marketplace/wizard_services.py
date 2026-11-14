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
    Order, OrderQuestionnaireAnswer, OrderQuestionnaireAnswerArchive,
    OrderStatusEvent, ServiceQuestionnaire, Subcategory,
)
from .order_lifecycle import transition_order_status
from .wizard_forms import active_categories, active_services
from .wizard_ui import wizard_copy
from .order_quota import consume_order_quota
from .order_events import emit_order_event


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


def start_order_wizard(*, actor, form, token, invite_worker_id=None):
    """Create a single owner-bound draft, even across repeated/racing submissions."""
    ensure_wizard_owner(actor)
    if not form.is_valid():
        raise ValueError('Invalid service selection.')
    try:
        key = uuid.UUID(str(token))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError('Invalid wizard token.') from exc

    if invite_worker_id is not None:
        from apps.accounts.client_favorites import public_worker_queryset
        requested_worker = public_worker_queryset().filter(
            pk=invite_worker_id, skills=form.cleaned_data['category'],
            services=form.cleaned_data['subcategory'],
        ).exclude(user_id=actor.pk).first()
        if requested_worker is None:
            raise ValueError('Selected specialist does not offer this service.')
    with transaction.atomic():
        existing = Order.objects.select_for_update().filter(wizard_token=key).first()
        if existing is not None:
            if existing.client_id != actor.pk or (
                (existing.wizard_data or {}).get('invite_worker_id') != invite_worker_id
            ):
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
                consume_order_quota(actor, 'create')
                order = Order.objects.create(
                    client_id=actor.pk,
                    category_id=values['category_id'],
                    subcategory_id=values['subcategory_id'],
                    city=city, address='', description='',
                    status=Order.Status.DRAFT, wizard_token=key,
                    wizard_data={
                        'steps': {'1': values},
                        **({'invite_worker_id': invite_worker_id}
                           if invite_worker_id is not None else {}),
                    },
                )
                source = OrderStatusEvent.objects.create(
                    order=order, actor_id=actor.pk, previous_status='',
                    new_status=Order.Status.DRAFT,
                    reason=OrderStatusEvent.Reason.CREATED,
                )
                emit_order_event(order, 'order_created', source.operation_key)
        except IntegrityError:
            existing = Order.objects.select_for_update().get(wizard_token=key)
            if existing.client_id != actor.pk or (
                (existing.wizard_data or {}).get('invite_worker_id') != invite_worker_id
            ):
                raise PermissionDenied(wizard_copy()['not_eligible']) from None
            return existing
        return order


def save_order_wizard_step(*, order_id, actor, step, form, uploads=(),
                           photo_visibility='private', public_consent=False):
    """Persist one validated step; changing service invalidates later answers."""
    if step < 1 or step > 7:
        raise ValueError('Invalid step.')
    ensure_wizard_owner(actor)
    if not form.is_valid():
        raise ValueError('Invalid form.')
    values = _step_data(form, step)
    # Normalization is expensive: do it before acquiring PostgreSQL locks.
    clean_images = []
    if step == 6 and uploads:
        from .attachment_services import validate_order_photo_batch
        clean_images = validate_order_photo_batch(uploads)
    with transaction.atomic():
        order = get_owner_wizard(order_id, actor, for_update=True)
        if order is None or order.status != Order.Status.DRAFT:
            raise PermissionDenied(wizard_copy()['not_eligible'])
        existing = dict((order.wizard_data or {}).get('steps') or {})
        if step > _next_step(existing):
            raise ValueError(wizard_copy()['incomplete'])
        # Any changed or repeated wizard step invalidates prior final consent.
        # A withdrawn/reopened order must be explicitly confirmed again.
        existing.pop('8', None)
        if step == 1:
            previous = existing.get('1')
            if previous != values:
                existing = {}
                order.wizard_data = {'steps': {}}
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

        if existing.get(str(step)) != values:
            consume_order_quota(actor, 'wizard')
        existing[str(step)] = values
        order.wizard_data = {**(order.wizard_data or {}), 'steps': existing}
        order.save(update_fields=['wizard_data', 'updated_at'])
        if step == 6 and clean_images:
            from .attachment_services import store_photos_on_locked_order
            store_photos_on_locked_order(
                order, actor=actor, cleaned=clean_images,
                visibility=photo_visibility, public_consent=public_consent,
            )
        return order


def wizard_initial(order, step):
    state = order.wizard_data or {}
    values = state.get('steps', {}).get(str(step)) or state.get('prefill', {}).get(str(step), {})
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
    # Persist a canonical, language-independent source key; presentation is
    # localized in wizard_summary and Django templates at render time.
    return 'Договорная'


def wizard_summary(order):
    """Only for owner-authenticated draft pages; no public serializer."""
    steps = order.wizard_data.get('steps', {})
    t = wizard_copy()
    place = steps.get('3', {})
    budget = steps.get('5')
    if not budget:
        budget_text = t['not_set']
    elif budget['price_type'] == 'negotiable':
        budget_text = t['negotiable']
    else:
        budget_text = _budget_label(budget)
    return [
        (t['service'], order.subcategory.localized_name if order.subcategory else t['not_set']),
        (t['city'], order.city.localized_name),
        (t['mode'], t.get(place.get('mode'), t['not_set'])),
        (t['area'], place.get('area') or t['not_set']),
        (t['date'], steps.get('4', {}).get('preferred_date') or t['no_date']),
        (t['urgency'], t.get(steps.get('4', {}).get('urgency'), t['not_set'])),
        (t['price_type'], budget_text),
        (t['description'], steps.get('6', {}).get('description') or t['not_set']),
    ]


def validate_wizard_status_publication(order):
    """Required invariant for ANY service-layer draft → published transition.

    The canonical wizard materializes structured fields and the questionnaire
    snapshot before requesting a status transition. Direct calls may not skip
    those checks or publish a partially saved draft.
    """
    data = (order.wizard_data or {}).get('steps', {})
    if (
        not isinstance(data, dict)
        or _next_step(data) != 8
        or not order.wizard_token
        or data.get('8') != {'confirm': True}
    ):
        # Step 8 is set only by the validated confirmation service.
        # Seven complete inputs alone must never authorize direct publication.
        raise ValueError(wizard_copy()['incomplete'])
    try:
        selection = data['1']
        place = data['3']
        schedule = data['4']
        price = data['5']
        question = data['2']
        description = data['6']['description']
        contact = data['7']
        if (
            not active_categories().filter(pk=selection['category_id']).exists()
            or not active_services(selection['category_id']).filter(
                pk=selection['subcategory_id'],
            ).exists()
        ):
            raise ValueError(wizard_copy()['no_service'])
        if (order.category_id != selection['category_id']
                or order.subcategory_id != selection['subcategory_id']
                or order.city_id != place['city_id']
                or not get_public_cities().filter(pk=place['city_id']).exists()
                or not city_is_public(order.city)):
            raise ValueError(wizard_copy()['incomplete'])
        service = Subcategory.objects.get(pk=order.subcategory_id)
        mode = place['mode']
        if (mode not in ('onsite', 'online')
                or (service.work_mode != 'both' and mode != service.work_mode)
                or order.work_mode != mode
                or order.approximate_area != place['area']):
            raise ValueError(wizard_copy()['incomplete'])
        from .wizard_forms import validate_approximate_area
        validate_approximate_area(place['area'])
        preferred = (
            date.fromisoformat(schedule['preferred_date'])
            if schedule['preferred_date'] else None
        )
        if (preferred and preferred < timezone.localdate()) or (
            order.preferred_date != preferred
            or schedule['urgency'] not in ('normal', 'soon', 'urgent')
            or order.urgency != schedule['urgency']
        ):
            raise ValueError(wizard_copy()['incomplete'])
        kind = price['price_type']
        if kind not in ('fixed', 'range', 'negotiable'):
            raise ValueError(wizard_copy()['incomplete'])
        if order.price_kind != kind or order.price != _budget_label(price):
            raise ValueError(wizard_copy()['incomplete'])
        lo = Decimal(price['amount_min']) if price['amount_min'] else None
        hi = Decimal(price['amount_max']) if price['amount_max'] else None
        if (
            (kind == 'negotiable' and (lo is not None or hi is not None))
            or (kind == 'fixed' and (lo is None or hi is not None))
            or (kind == 'range' and (lo is None or hi is None or hi < lo))
            or (lo is not None and lo < 0)
            or (hi is not None and hi < 0)
            or order.amount_min_ils != lo
            or order.amount_max_ils != hi
        ):
            raise ValueError(wizard_copy()['incomplete'])
        if (order.description != description
                or (not description.strip() and not question['answers'])
                or not contact['chat_only']
                or order.customer_name != contact['display_name']):
            raise ValueError(wizard_copy()['incomplete'])
        current = ServiceQuestionnaire.objects.filter(
            service_id=service.pk,
        ).first()
        version_id = current.published_version_id if current else None
        if question['version_id'] != version_id:
            raise ValueError(wizard_copy()['changed'])
        snapshot = OrderQuestionnaireAnswer.objects.filter(order=order).first()
        if version_id is None:
            if question['answers'] or snapshot is not None:
                raise ValueError(wizard_copy()['incomplete'])
        else:
            if (snapshot is None or snapshot.version_id != version_id
                    or snapshot.answers != question['answers']):
                raise ValueError(wizard_copy()['incomplete'])
            from .wizard_forms import QuestionsStepForm
            bound = {'questionnaire_version': str(version_id)}
            for key, value in question['answers'].items():
                if isinstance(value, bool):
                    value = 'true' if value else 'false'
                bound['q_' + key] = value
            form = QuestionsStepForm(data=bound, service_id=service.pk)
            if not form.is_valid() or form.questionnaire_answers != question['answers']:
                raise ValueError(wizard_copy()['incomplete'])
    except (KeyError, TypeError, AttributeError, ArithmeticError, OverflowError) as exc:
        raise ValueError(wizard_copy()['incomplete']) from exc


def publish_order_wizard(*, order_id, actor, confirmation_form=None):
    """Validate final confirmation and saved wizard before atomic publication."""
    ensure_wizard_owner(actor)
    from .wizard_forms import ConfirmStepForm
    if (
        not isinstance(confirmation_form, ConfirmStepForm)
        or not confirmation_form.is_bound
        or not confirmation_form.is_valid()
        or confirmation_form.cleaned_data.get('confirm') is not True
    ):
        raise ValueError(wizard_copy()['incomplete'])
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
        price_data = steps['5']
        order.price = _budget_label(price_data)
        order.price_kind = price_data['price_type']
        order.amount_min_ils = (
            Decimal(price_data['amount_min'])
            if order.price_kind in ('fixed', 'range') else None
        )
        order.amount_max_ils = (
            Decimal(price_data['amount_max'])
            if order.price_kind == 'range' else None
        )
        order.preferred_date = (
            date.fromisoformat(preferred) if preferred else None
        )
        order.urgency = steps['4']['urgency']
        order.work_mode = place['mode']
        order.approximate_area = place['area']
        order.description = steps['6']['description']
        order.customer_name = steps['7']['display_name']
        # Private phone/address are shared voluntarily in Stage 07 chat only.
        # Never overwrite legacy private contacts on re-publication.
        # Fresh and duplicated drafts already have empty contact fields.
        order.save(update_fields=[
            'category', 'subcategory', 'city', 'price', 'price_kind',
            'amount_min_ils', 'amount_max_ils', 'preferred_date', 'urgency',
            'work_mode', 'approximate_area', 'description',
            'customer_name', 'updated_at',
        ])
        saved_answer = OrderQuestionnaireAnswer.objects.select_for_update().filter(
            order=order,
        ).first()
        if saved_answer and (
            version is None
            or saved_answer.version_id != version.pk
            or saved_answer.answers != questions['answers']
        ):
            # Never modify an immutable historical snapshot in place. Archive
            # the previous private value before installing the new current one.
            OrderQuestionnaireAnswerArchive.objects.create(
                order=order, version_id=saved_answer.version_id,
                schema_snapshot=saved_answer.schema_snapshot,
                answers=saved_answer.answers,
            )
            saved_answer.delete()
            saved_answer = None
        if version and saved_answer is None:
            OrderQuestionnaireAnswer.objects.create(
                order=order, version=version,
                schema_snapshot=version.schema,
                answers=questions['answers'],
            )
        # Record final confirmation in the same transaction as publication.
        # No direct draft → published transition can omit this evidence.
        order.wizard_data = {
            **(order.wizard_data or {}),
            'steps': {**steps, '8': {'confirm': True}},
        }
        order.save(update_fields=['wizard_data', 'updated_at'])
        order = transition_order_status(
            order, Order.Status.PUBLISHED, actor=actor,
        )
        return order, True
