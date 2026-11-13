from django.db import transaction
from django.db.models import Case, Exists, IntegerField, OuterRef, Q, Value, When

from apps.accounts.models import User, WorkerProfile
from apps.locations.services import city_is_public, get_public_cities, public_city_slug
from .models import Category, Subcategory, Order, OrderStatusEvent, Response
from .order_lifecycle import transition_order_status
from .order_quota import consume_order_quota
from .order_events import emit_order_event


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
            consume_order_quota(client, 'create')
            order = Order.objects.create(
                client_id=client.pk, category=category, city=city,
                subcategory=subcategory, address=address,
                description=description, price=price,
                customer_name=customer_name, customer_phone=customer_phone,
                wizard_token=key, submission_digest=digest,
            )
            source = OrderStatusEvent.objects.create(
                order=order, actor_id=client.pk, previous_status='',
                new_status=order.status, reason=OrderStatusEvent.Reason.CREATED,
            )
            emit_order_event(order, 'order_created', source.operation_key)
            emit_order_event(order, 'order_published', source.operation_key)
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



def workers_serving_city(
    queryset, city, *, category=None, service=None, mode=None, neighborhood=None,
):
    """Filter public coverage by stable IDs, service mode and city/neighborhood.

    An empty neighborhood selection means the worker serves the entire selected
    city; selecting neighborhoods narrows onsite coverage for that city.
    Remote delivery ignores onsite zones only for explicitly remote-eligible
    services and worker opt-in. Ashdod-only remains a hard server-side gate.
    """
    if not city_is_public(city) or mode not in (None, 'onsite', 'online'):
        return queryset.none()
    if neighborhood is not None and (
        not neighborhood.is_active or neighborhood.city_id != city.pk
    ):
        return queryset.none()
    if service is not None:
        if (not service.is_active or not service.category.is_active
                or (service.category.section_id is not None
                    and not service.category.section.is_active)
                or (category is not None and service.category_id != category.pk)):
            return queryset.none()
        category = service.category
        declared_service = Subcategory.objects.filter(
            pk=service.pk, workers__pk=OuterRef('pk'),
        )
        queryset = queryset.alias(
            _declares_requested_service=Exists(declared_service),
        ).filter(_declares_requested_service=True)
    if category is not None:
        if not Category.objects.filter(
            pk=category.pk, is_active=True,
        ).filter(
            Q(section__isnull=True) | Q(section__is_active=True)
        ).exists():
            return queryset.none()
        # Callers may not omit category membership, even with a forged ID.
        declared_category = Category.objects.filter(
            pk=category.pk, workers__pk=OuterRef('pk'),
        )
        queryset = queryset.alias(
            _declares_requested_category=Exists(declared_category),
        ).filter(_declares_requested_category=True)

    if public_city_slug():
        # Until the owner expands the pilot, a remote-capable non-Ashdod
        # profile must NOT be promoted into public search by its mode.
        queryset = queryset.filter(city=city)

    through = WorkerProfile.service_cities.through
    zones = through.objects.filter(workerprofile_id=OuterRef('pk'))
    queryset = queryset.alias(
        _has_explicit_zones=Exists(zones),
        _serves_selected_city=Exists(zones.filter(city_id=city.pk)),
    )
    onsite = (
        Q(_serves_selected_city=True)
        | Q(_has_explicit_zones=False, city_id=city.pk)
    )
    if neighborhood is not None:
        neighborhood_through = WorkerProfile.service_neighborhoods.through
        areas_for_city = neighborhood_through.objects.filter(
            workerprofile_id=OuterRef('pk'), neighborhood__city_id=city.pk,
        )
        queryset = queryset.alias(
            _has_area_limit=Exists(areas_for_city),
            _covers_neighborhood=Exists(areas_for_city.filter(
                neighborhood_id=neighborhood.pk,
            )),
        )
        onsite &= (
            Q(_has_area_limit=False) | Q(_covers_neighborhood=True)
        )

    onsite_permitted = (
        (category is None or category.work_mode in ('onsite', 'both'))
        and (service is None or service.work_mode in ('onsite', 'both'))
    )
    if category is None:
        onsite_categories = Category.objects.filter(
            workers__pk=OuterRef('pk'),
            is_active=True, work_mode__in=('onsite', 'both'),
        ).filter(
            Q(section__isnull=True) | Q(section__is_active=True)
        )
        queryset = queryset.alias(_has_onsite_skill=Exists(onsite_categories))
        onsite &= Q(_has_onsite_skill=True)
    remote_permitted = (
        (category is None or category.work_mode in ('online', 'both'))
        and (service is None or service.work_mode in ('online', 'both'))
    )
    if category is None and remote_permitted:
        remote_categories = Category.objects.filter(
            workers__pk=OuterRef('pk'),
            is_active=True, work_mode__in=('online', 'both'),
        ).filter(
            Q(section__isnull=True) | Q(section__is_active=True)
        )
        queryset = queryset.alias(_remote_skill=Exists(remote_categories))
        remote = Q(offers_remote=True, _remote_skill=True)
    else:
        remote = Q(offers_remote=True)

    if mode == 'onsite':
        return queryset.filter(onsite) if onsite_permitted else queryset.none()
    if mode == 'online':
        return queryset.filter(remote) if remote_permitted else queryset.none()
    if onsite_permitted and remote_permitted:
        return queryset.filter(onsite | remote)
    if onsite_permitted:
        return queryset.filter(onsite)
    if remote_permitted:
        return queryset.filter(remote)
    return queryset.none()


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
    declared_services = worker_profile.services.filter(
        is_active=True, category__is_active=True,
    )
    base_qs = base_qs.filter(
        Q(subcategory__isnull=True) | Q(subcategory__in=declared_services),
    )

    # A worker without an explicit area inherits only the historical home city;
    # no default nationwide visibility for new or legacy profiles.
    zones = worker_profile.service_cities.filter(is_active=True)
    onsite_zone = Q(city__in=zones)
    if not worker_profile.service_cities.exists() and worker_profile.city_id:
        onsite_zone = Q(city_id=worker_profile.city_id)
    onsite_order = (
        Q(work_mode=Order.WorkMode.ONSITE)
        | Q(
            work_mode=Order.WorkMode.LEGACY,
            category__work_mode__in=('onsite', 'both'),
        )
    )
    zone_filter = onsite_order & onsite_zone
    if worker_profile.offers_remote:
        zone_filter |= (
            Q(work_mode=Order.WorkMode.ONLINE)
            | Q(
                work_mode=Order.WorkMode.LEGACY,
                category__work_mode__in=('online', 'both'),
            )
        )

    return base_qs.filter(zone_filter).annotate(
        city_priority=Case(
            When(city_id=worker_profile.city_id, then=Value(0)),
            default=Value(1), output_field=IntegerField(),
        )
    ).order_by('city_priority', '-created_at', '-pk')

def create_response(order, worker_user, message='', *, offer_data=None, operation_key=None):
    """Serialize worker reply against assignment/cancellation and reply quota."""
    if not getattr(worker_user, 'is_authenticated', False):
        raise ValueError('Для отклика требуется авторизация.')
    with transaction.atomic():
        # Lock the order FIRST, just like acceptance and withdrawal.
        # This prevents inserting PENDING after winner was selected.
        order = Order.objects.select_for_update(of=('self',)).select_related(
            'city', 'category__section', 'subcategory__category__section',
        ).get(pk=order.pk)
        if not User.objects.filter(
            pk=worker_user.pk, is_active=True, is_blocked=False,
            email_verification_required=False,
        ).exists():
            raise ValueError('Аккаунт недоступен.')
        worker_profile = WorkerProfile.objects.select_related('user', 'city').filter(
            user_id=worker_user.pk,
        ).first()
        if worker_profile is None:
            raise ValueError('Пользователь не является мастером.')
        if public_city_slug() and not city_is_public(worker_profile.city):
            raise ValueError('Профиль мастера находится вне пилотного города.')
        if not city_is_public(order.city):
            raise ValueError('Город пока не обслуживается.')
        if order.client_id == worker_user.pk:
            raise ValueError('Нельзя откликнуться на собственную заявку.')
        if order.status != Order.Status.PUBLISHED:
            raise ValueError('Заказ уже не в статусе «В обработке».')
        if (not worker_profile.is_published
                or worker_profile.availability == WorkerProfile.Availability.UNAVAILABLE):
            raise ValueError('Анкета мастера не опубликована или недоступна.')
        mode = (
            order.work_mode
            if order.work_mode in (Order.WorkMode.ONSITE, Order.WorkMode.ONLINE)
            else None
        )
        if not workers_serving_city(
            WorkerProfile.objects.filter(pk=worker_profile.pk),
            order.city, category=order.category,
            service=order.subcategory, mode=mode,
        ).exists():
            raise ValueError('Заявка не соответствует услугам или зоне мастера.')
        if Response.objects.filter(order=order, worker_id=worker_user.pk).exists():
            raise ValueError('Вы уже откликались на этот заказ.')
        from .offer_services import normalize_offer, record_response_revision
        offer = normalize_offer(offer_data) if offer_data is not None else {}
        if len(message) > 1000:
            raise ValueError('Слишком длинное сообщение.')
        consume_order_quota(worker_user, 'response')
        response = Response.objects.create(
            order=order, worker_id=worker_user.pk, message=message,
            status=Response.Status.SENT if offer_data is not None else Response.Status.PENDING,
            **offer,
        )
        record_response_revision(
            response, actor=worker_user, action='submitted', operation_key=operation_key,
        )
        return response


def accept_response(response, *, actor):
    """Atomically select exactly one eligible offer; work starts separately.

    Locks Order before any Response; concurrent selections never both win.
    A replay of the already selected offer is a no-op with no notifications.
    """
    from django.core.exceptions import PermissionDenied
    from .offer_services import ACTIVE_STATUSES, record_response_revision
    from .invitation_services import worker_eligible_for_order

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

        if (order.worker_id == response.worker_id
                and order.status in (Order.Status.ASSIGNED, Order.Status.IN_PROGRESS,
                                     Order.Status.COMPLETED, Order.Status.DISPUTED)
                and Response.objects.filter(
                    pk=response.pk, order=order,
                    status=Response.Status.ACCEPTED,
                ).exists()):
            selected = Response.objects.get(pk=response.pk)
            selected._assignment_created = False
            selected._rejected_worker_ids = ()
            return selected

        if (order.worker_id is not None
                or order.status not in (Order.Status.PUBLISHED, Order.Status.IN_DISCUSSION)):
            raise ValueError('Исполнитель для этой заявки уже выбран.')
        selected = Response.objects.select_for_update().select_related('worker').get(
            pk=response.pk, order=order,
        )
        if selected.status not in ACTIVE_STATUSES:
            raise ValueError('Это предложение уже недоступно.')
        if (not selected.worker.is_active or selected.worker.is_blocked
                or selected.worker.email_verification_required):
            raise ValueError('Исполнитель недоступен.')
        # Serialize profile publication changes with selection; the join
        # above already locks the current worker user along with Response.
        profile = WorkerProfile.objects.select_for_update().filter(
            user_id=selected.worker_id, is_published=True,
        ).first()
        if profile is None or not worker_eligible_for_order(profile.pk, order):
            raise ValueError('Анкета или услуга исполнителя больше недоступна.')

        selected.status = Response.Status.ACCEPTED
        selected.revision += 1
        selected.save(update_fields=['status', 'revision', 'updated_at'])
        record_response_revision(selected, actor=actor, action='accepted')

        rejected_ids = []
        other_offers = Response.objects.select_for_update().filter(
            order=order, status__in=ACTIVE_STATUSES,
        ).exclude(pk=selected.pk).order_by('pk')
        for other in other_offers:
            rejected_ids.append(other.worker_id)
            other.status = Response.Status.REJECTED
            other.revision += 1
            other.save(update_fields=['status', 'revision', 'updated_at'])
            record_response_revision(other, actor=actor, action='rejected')

        order.worker_id = selected.worker_id
        order.save(update_fields=['worker', 'updated_at'])
        # Assignment is not work-start; both are independent audited actions.
        order = transition_order_status(
            order.pk, Order.Status.ASSIGNED, actor=actor,
            reason=OrderStatusEvent.Reason.WORKER_ASSIGNED,
        )
        from .agreement_services import create_initial_agreement
        create_initial_agreement(order, selected, actor=actor)
        selected.order = order
        selected._assignment_created = True
        selected._rejected_worker_ids = tuple(rejected_ids)
        return selected


def complete_order(order, *, actor):
    """Explicit client sign-off with an append-only work event."""
    from .work_services import confirm_work_result
    current, _ = confirm_work_result(
        order_id=order.pk if isinstance(order, Order) else order,
        actor=actor,
    )
    return current


def cancel_order(order, *, actor):
    """Cancel an order only for the authenticated, persisted owner."""
    return transition_order_status(
        order, Order.Status.CANCELLED, actor=actor,
    )
