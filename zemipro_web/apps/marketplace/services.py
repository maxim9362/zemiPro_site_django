from django.db import transaction
from django.db.models import Case, Exists, IntegerField, OuterRef, Q, Value, When

from apps.accounts.models import User, WorkerProfile
from apps.locations.services import city_is_public, get_public_cities, public_city_slug
from .models import Category, Order, OrderStatusEvent, Response
from .order_lifecycle import transition_order_status


def can_view_private_order_details(user, order):
    """Allow private data to parties or explicitly authorized moderation staff."""
    if not user.is_authenticated or not user.is_active or user.is_blocked:
        return False
    # Read persisted moderation state, never rely on a stale User instance.
    stored = User.objects.filter(
        pk=user.pk, is_active=True, is_blocked=False,
        email_verification_required=False,
    ).first()
    if stored is None:
        return False
    authorized_staff = (
        stored.is_staff
        and stored.has_perm('moderation.review_complaints')
    )
    # A selected worker never gains the client's address, phone or raw
    # descriptions automatically. Such details are voluntary in private chat.
    return bool(authorized_staff or order.client_id == stored.pk)


def create_order(
    client, category, city, address, description, price='Договорная',
    subcategory=None, *, customer_name='', customer_phone='',
    questionnaire_version=None, questionnaire_answers=None,
    submission_key=None, return_created=False,
):
    """Create a published order once, with persisted owner authorization.

    Modern clients supply a stable UUID submission_key. Legacy clients without
    a key are deduplicated for 15 minutes using a keyed digest and a PostgreSQL
    transaction-level advisory lock. The digest contains no readable contacts.
    """
    import hashlib
    import hmac
    import json
    import uuid
    from datetime import timedelta

    from django.conf import settings
    from django.core.exceptions import PermissionDenied
    from django.db import IntegrityError, connection
    from django.utils import timezone

    if client is None or not getattr(client, 'is_authenticated', False):
        raise ValueError('Для создания заявки требуется авторизация.')
    if not User.objects.filter(
        pk=client.pk, is_active=True, is_blocked=False,
        email_verification_required=False,
    ).exists():
        raise ValueError('Аккаунт недоступен.')
    if not city_is_public(city):
        raise ValueError('Город пока не обслуживается.')
    if not Category.objects.filter(
        pk=category.pk, is_active=True,
    ).filter(Q(section__isnull=True) | Q(section__is_active=True)).exists():
        raise ValueError('Услуга недоступна.')
    if subcategory is not None and (
        subcategory.category_id != category.pk
        or not subcategory.is_active
    ):
        raise ValueError('Услуга недоступна.')
    if questionnaire_version is not None and (
        subcategory is None
        or questionnaire_version.questionnaire.service_id != subcategory.pk
    ):
        raise ValueError('Анкета не соответствует услуге.')
    try:
        key = uuid.UUID(str(submission_key)) if submission_key else None
    except (TypeError, ValueError, AttributeError) as error:
        raise ValueError('Неверный ключ подачи заявки.') from error
    fingerprint = json.dumps(
        [client.pk, category.pk, subcategory.pk if subcategory else None,
         city.pk, address, description, price, customer_name, customer_phone,
         questionnaire_version.pk if questionnaire_version else None,
         questionnaire_answers or {}],
        sort_keys=True, ensure_ascii=False, separators=(',', ':'),
    )
    digest = hmac.new(
        settings.SECRET_KEY.encode('utf-8'), fingerprint.encode('utf-8'),
        hashlib.sha256,
    ).hexdigest()
    with transaction.atomic():
        # A blocked account cannot win a race via a stale in-memory User.
        if not User.objects.filter(
            pk=client.pk, is_active=True, is_blocked=False,
            email_verification_required=False,
        ).exists():
            raise ValueError('Аккаунт недоступен.')
        if key is None:
            # Serializes *all* no-token duplicates with identical payloads
            # across Django workers and processes attached to PostgreSQL.
            lock = int.from_bytes(bytes.fromhex(digest[:16]), 'big', signed=True)
            if connection.vendor != 'postgresql':
                raise RuntimeError('Order submission guard requires PostgreSQL.')
            with connection.cursor() as cursor:
                cursor.execute('SELECT pg_advisory_xact_lock(%s)', [lock])
            original = Order.objects.filter(
                client_id=client.pk, submission_digest=digest,
                created_at__gte=timezone.now() - timedelta(minutes=15),
            ).order_by('-created_at', '-pk').first()
        else:
            original = Order.objects.select_for_update().filter(
                wizard_token=key,
            ).first()
            if original and (
                original.client_id != client.pk or original.submission_digest != digest
            ):
                raise PermissionDenied('Ключ подачи заявки уже использован.')
        if original:
            return (original, False) if return_created else original

        # A direct service call cannot bypass mandatory category questions.
        if subcategory is not None:
            from .models import ServiceQuestionnaire
            q = ServiceQuestionnaire.objects.select_for_update().filter(
                service_id=subcategory.pk,
            ).first()
            current_version_id = q.published_version_id if q else None
            supplied_id = questionnaire_version.pk if questionnaire_version else None
            if current_version_id != supplied_id:
                raise ValueError('Анкета услуги изменилась.')
            if current_version_id is not None:
                from .wizard_forms import QuestionsStepForm
                supplied = {
                    'questionnaire_version': str(current_version_id),
                }
                for answer_key, answer_value in (questionnaire_answers or {}).items():
                    if isinstance(answer_value, bool):
                        answer_value = 'true' if answer_value else 'false'
                    supplied['q_' + answer_key] = answer_value
                validated = QuestionsStepForm(data=supplied, service_id=subcategory.pk)
                if (not validated.is_valid()
                        or validated.questionnaire_answers != questionnaire_answers):
                    raise ValueError('Некорректные ответы на вопросы услуги.')

        def insert():
            order = Order.objects.create(
                client_id=client.pk, category=category, city=city,
                subcategory=subcategory, address=address,
                description=description, price=price,
                customer_name=customer_name, customer_phone=customer_phone,
                wizard_token=key, submission_digest=digest,
            )
            OrderStatusEvent.objects.create(
                order=order, actor_id=client.pk, previous_status='',
                new_status=order.status, reason=OrderStatusEvent.Reason.CREATED,
            )
            if questionnaire_version is not None:
                from .models import OrderQuestionnaireAnswer
                OrderQuestionnaireAnswer.objects.create(
                    order=order, version=questionnaire_version,
                    schema_snapshot=questionnaire_version.schema,
                    answers=questionnaire_answers or {},
                )
            return order

        if key is not None:
            try:
                # Inner savepoint lets an identical concurrent POST recover
                # from the unique constraint without aborting the transaction.
                with transaction.atomic():
                    order = insert()
            except IntegrityError:
                order = Order.objects.select_for_update().get(wizard_token=key)
                if order.client_id != client.pk or order.submission_digest != digest:
                    raise PermissionDenied('Ключ подачи заявки уже использован.') from None
                return (order, False) if return_created else order
        else:
            order = insert()
        return (order, True) if return_created else order



def workers_serving_city(queryset, city, *, category=None):
    """Apply explicit zones, home city fallback, and online opt-in.

    EXISTS subqueries prevent duplicate workers; no out-of-pilot geography is
    exposed even by a crafted category/city query or remote-service flag.
    """
    if not city_is_public(city):
        return queryset.none()
    if public_city_slug():
        # Remote work is a delivery mode, not a way to publish a historical
        # profile whose home city is outside the owner-approved pilot.
        queryset = queryset.filter(city=city)
    through = WorkerProfile.service_cities.through
    zones = through.objects.filter(workerprofile_id=OuterRef('pk'))
    serving = zones.filter(city_id=city.pk)
    queryset = queryset.alias(
        _has_explicit_zones=Exists(zones),
        _serves_selected_city=Exists(serving),
    )
    allowed = (
        Q(_serves_selected_city=True)
        | Q(_has_explicit_zones=False, city_id=city.pk)
    )
    if category is not None:
        if category.work_mode in ('online', 'both'):
            allowed |= Q(offers_remote=True)
    else:
        online_categories = Category.objects.filter(
            workers__pk=OuterRef('pk'), is_active=True,
            work_mode__in=('online', 'both'),
        ).filter(Q(section__isnull=True) | Q(section__is_active=True))
        queryset = queryset.alias(
            _has_remote_skill=Exists(online_categories)
        )
        allowed |= Q(offers_remote=True, _has_remote_skill=True)
    return queryset.filter(allowed)


def get_available_orders_for_worker(worker_profile):
    """New orders only in selected zones or eligible opted-in online skills."""
    if (not worker_profile.is_published
            or not User.objects.filter(
                pk=worker_profile.user_id, is_active=True, is_blocked=False,
                email_verification_required=False,
            ).exists()
            or worker_profile.availability == WorkerProfile.Availability.UNAVAILABLE
            or (public_city_slug() and not city_is_public(worker_profile.city))):
        return Order.objects.none()
    skills = worker_profile.skills.filter(is_active=True).filter(
        Q(section__isnull=True) | Q(section__is_active=True)
    )
    if not skills.exists():
        return Order.objects.none()

    base_qs = Order.objects.select_related('category', 'city').filter(
        status=Order.Status.PUBLISHED, category__in=skills,
        city__in=get_public_cities(),
    ).exclude(client_id=worker_profile.user_id)

    # A worker without an explicit area inherits only the historical home city;
    # no default nationwide visibility for new or legacy profiles.
    zones = worker_profile.service_cities.filter(is_active=True)
    zone_filter = Q(city__in=zones)
    if not worker_profile.service_cities.exists() and worker_profile.city_id:
        zone_filter = Q(city_id=worker_profile.city_id)
    if worker_profile.offers_remote:
        zone_filter |= Q(category__work_mode__in=('online', 'both'))

    return base_qs.filter(zone_filter).annotate(
        city_priority=Case(
            When(city_id=worker_profile.city_id, then=Value(0)),
            default=Value(1), output_field=IntegerField(),
        )
    ).order_by('city_priority', '-created_at', '-pk')

def create_response(order, worker_user, message=''):
    """Создать отклик мастера на заказ."""
    if not hasattr(worker_user, 'worker_profile'):
        raise ValueError('Пользователь не является мастером.')
    if not User.objects.filter(
        pk=worker_user.pk, is_active=True, is_blocked=False,
        email_verification_required=False,
    ).exists():
        raise ValueError('Аккаунт недоступен.')

    if public_city_slug() and not city_is_public(worker_user.worker_profile.city):
        raise ValueError('Профиль мастера находится вне пилотного города.')

    if not city_is_public(order.city):
        raise ValueError('Город пока не обслуживается.')

    if order.client_id == worker_user.pk:
        raise ValueError('Нельзя откликнуться на собственную заявку.')

    if order.status != Order.Status.PUBLISHED:
        raise ValueError('Заказ уже не в статусе «В обработке».')

    worker_profile = worker_user.worker_profile
    if (not worker_profile.is_published or worker_profile.user.is_blocked
            or not worker_profile.user.is_active
            or worker_profile.availability == WorkerProfile.Availability.UNAVAILABLE):
        raise ValueError('Анкета мастера не опубликована или недоступна.')

    existing = Response.objects.filter(order=order, worker=worker_user).first()
    if existing:
        raise ValueError('Вы уже откликались на этот заказ.')

    response = Response.objects.create(
        order=order,
        worker=worker_user,
        message=message,
    )
    return response


def accept_response(response, *, actor):
    """Accept one response only when the persisted order owner requested it."""
    from django.core.exceptions import PermissionDenied

    with transaction.atomic():
        order = Order.objects.select_for_update().get(pk=response.order_id)
        if (
            not getattr(actor, 'is_authenticated', False)
            or order.client_id != actor.pk
            or not User.objects.filter(
                pk=actor.pk, is_active=True, is_blocked=False,
                email_verification_required=False,
            ).exists()
        ):
            raise PermissionDenied('Нет права назначать исполнителя.')
        if order.status != Order.Status.PUBLISHED:
            raise ValueError('Исполнитель для этой заявки уже выбран.')

        locked_response = Response.objects.select_for_update().select_related(
            'worker'
        ).get(pk=response.pk, order=order)
        if locked_response.status != Response.Status.PENDING:
            raise ValueError('Этот отклик уже обработан.')
        if (not locked_response.worker.is_active or locked_response.worker.is_blocked
                or locked_response.worker.email_verification_required):
            raise ValueError('Исполнитель недоступен.')

        locked_response.status = Response.Status.ACCEPTED
        locked_response.save(update_fields=['status', 'updated_at'])

        Response.objects.filter(
            order=order
        ).exclude(
            pk=locked_response.pk
        ).update(status=Response.Status.REJECTED)

        order.worker = locked_response.worker
        order.save(update_fields=['worker', 'updated_at'])
        # Preserve current UX: selection immediately starts work, but
        # record two distinct domain transitions under the same row lock.
        transition_order_status(
            order.pk, Order.Status.ASSIGNED, actor=actor,
            reason=OrderStatusEvent.Reason.WORKER_ASSIGNED,
        )
        transition_order_status(
            order.pk, Order.Status.IN_PROGRESS, actor=actor,
            reason=OrderStatusEvent.Reason.WORK_STARTED,
        )
        locked_response.order = order
    return locked_response


def complete_order(order, *, actor):
    """Complete an order only for the authenticated, persisted owner."""
    return transition_order_status(
        order, Order.Status.COMPLETED, actor=actor,
    )


def cancel_order(order, *, actor):
    """Cancel an order only for the authenticated, persisted owner."""
    return transition_order_status(
        order, Order.Status.CANCELLED, actor=actor,
    )
