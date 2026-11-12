"""Stage 02.5: safe versioned service questions and immutable order answers."""
from copy import deepcopy
from io import StringIO

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils.translation import override

from apps.locations.models import City
from apps.marketplace.forms import OrderCreateForm
from apps.marketplace.models import (
    Category, Order, OrderQuestionnaireAnswer, QuestionnaireVersion,
    ServiceQuestionnaire, Subcategory,
)
from apps.marketplace.questionnaire_examples import DEMO_QUESTIONNAIRES
from apps.marketplace.questionnaire_services import (
    present_order_answers, publish_questionnaire,
)
from apps.marketplace.questionnaires import validate_question_schema
from apps.marketplace.tests.factories import make_user


class QuestionnaireSchemaTests(TestCase):
    def test_all_four_demos_validate_and_supported_types_covered(self):
        self.assertEqual(len(DEMO_QUESTIONNAIRES), 4)
        types = set()
        for category_slug, service_slug, schema in DEMO_QUESTIONNAIRES:
            self.assertTrue(category_slug and service_slug)
            validate_question_schema(schema)
            types.update(q['type'] for q in schema)
        self.assertEqual(
            types, {'text', 'single', 'multiple', 'number', 'date', 'boolean'},
        )

    def test_reject_duplicate_or_invalid_key_bad_choices_and_future_dependency(self):
        questions = deepcopy(DEMO_QUESTIONNAIRES[0][2])
        for invalid in (
            [questions[0], questions[0]],
            [{**questions[0], 'key': 'not-valid!'}],
            [{**questions[0], 'type': 'python'}],
            [{**questions[0], 'options': []}],
            [{**questions[0], 'depends_on': {'key': 'urgent', 'equals': True}}],
            [{**questions[0], 'labels': {'ru': '<unsafe>', 'en': ''}}],
        ):
            with self.subTest(schema=invalid):
                with self.assertRaises(ValidationError):
                    validate_question_schema(invalid)

    def test_max_questions_and_oversized_labels_are_rejected(self):
        schema = deepcopy(DEMO_QUESTIONNAIRES[0][2])
        with self.assertRaises(ValidationError):
            validate_question_schema([*schema] * 8)
        schema[0]['labels']['he'] = 'x' * 161
        with self.assertRaises(ValidationError):
            validate_question_schema(schema)


class QuestionnaireFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = make_user('qa-025-owner')
        cls.stranger = make_user('qa-025-stranger')
        cls.city = City.objects.create(
            slug='qa025-city', name_ru='Город', name_en='City', name_he='עיר',
        )
        cls.category = Category.objects.create(
            slug='qa025-plumbing', name_ru='Сантехника',
        )
        cls.service = Subcategory.objects.create(
            category=cls.category, slug='qa025-repair',
            name_ru='Устранение течи',
        )
        cls.draft = ServiceQuestionnaire.objects.create(
            service=cls.service,
            draft_schema=deepcopy(DEMO_QUESTIONNAIRES[0][2]),
        )

    def payload(self, version=None, **extra):
        if version is None:
            self.draft.refresh_from_db()
            version = self.draft.published_version_id
        return {
            'customer_name': 'Synthetic Client',
            'customer_phone': '0501234567',
            'category': str(self.category.pk),
            'subcategory': str(self.service.pk),
            'city': str(self.city.pk),
            'address': 'Sensitive synthetic address',
            'description': 'Synthetic long description of a leaking plumbing pipe.',
            'price': 'Договорная',
            'questionnaire_version': str(version),
            'q_issue': 'pipe',
            'q_urgent': 'true',
            'q_access': 'Synthetic safe details',
            **extra,
        }

    def publish(self):
        version, _ = publish_questionnaire(self.draft.pk)
        return version

    def test_draft_is_not_public_and_published_schema_localizes(self):
        api = reverse('marketplace:api_questionnaire', args=[self.service.pk])
        before = self.client.get(api)
        self.assertEqual(before.json(), {'version': None, 'questions': []})
        version = self.publish()
        for language, translated in (
            ('ru', 'Где протечка?'),
            ('en', 'Where is the leak?'),
            ('he', 'איפה הנזילה?'),
        ):
            with self.subTest(language=language):
                response = self.client.get(
                    api, HTTP_ACCEPT_LANGUAGE=language,
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()['version'], version.pk)
                self.assertEqual(response.json()['questions'][0]['label'], translated)
                self.assertNotContains(response, 'Sensitive synthetic address')
        self.assertEqual(self.client.post(api).status_code, 404)

    def test_publish_is_idempotent_then_new_version_preserves_old(self):
        first, inserted = publish_questionnaire(self.draft.pk)
        self.assertTrue(inserted)
        again, inserted = publish_questionnaire(self.draft.pk)
        self.assertFalse(inserted)
        self.assertEqual(again.pk, first.pk)
        self.draft.refresh_from_db()
        edited = deepcopy(self.draft.draft_schema)
        edited[0]['labels']['ru'] = 'Уточните место течи'
        self.draft.draft_schema = edited
        self.draft.full_clean()
        self.draft.save(update_fields=['draft_schema', 'updated_at'])
        second, fresh = publish_questionnaire(self.draft.pk)
        self.assertTrue(fresh)
        self.assertEqual(second.number, 2)
        self.assertEqual(first.number, 1)
        first.refresh_from_db()
        self.assertEqual(first.schema[0]['labels']['ru'], 'Где протечка?')
        self.assertEqual(self.draft.versions.count(), 2)

    def test_published_version_cannot_be_edited_with_model_save(self):
        v = self.publish()
        v.schema[0]['labels']['ru'] = 'Tampered'
        with self.assertRaises(ValidationError):
            v.save()
        self.assertNotEqual(
            QuestionnaireVersion.objects.get(pk=v.pk).schema[0]['labels']['ru'],
            'Tampered',
        )

    def test_valid_submission_stores_atomic_private_historical_snapshot(self):
        v = self.publish()
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse('marketplace:order_create'), self.payload(v.pk),
        )
        self.assertEqual(response.status_code, 302)
        order = Order.objects.get(client=self.owner)
        self.assertEqual(OrderQuestionnaireAnswer.objects.count(), 1)
        snapshot = order.questionnaire_answer
        self.assertEqual(snapshot.version_id, v.pk)
        self.assertEqual(snapshot.answers, {
            'issue': 'pipe',
            'urgent': True,
            'access': 'Synthetic safe details',
        })
        self.assertEqual(snapshot.schema_snapshot, v.schema)
        self.assertContains(
            self.client.get(reverse('marketplace:order_detail', args=[order.pk])),
            'Где протечка?',
        )
        self.assertContains(
            self.client.get(reverse('marketplace:order_detail', args=[order.pk])),
            'Труба',
        )
        self.client.force_login(self.stranger)
        public = self.client.get(reverse('marketplace:order_detail', args=[order.pk]))
        self.assertEqual(public.status_code, 200)
        self.assertNotContains(public, 'Где протечка?')
        self.assertNotContains(public, 'Synthetic safe details')
        self.assertNotContains(public, 'Sensitive synthetic address')

    def test_conditional_required_and_hidden_tampered_values_ignored(self):
        version = self.publish()
        base = self.payload(version.pk, q_urgent='false', q_access='SHOULD_NOT_SAVE')
        form = OrderCreateForm(base)
        self.assertTrue(form.is_valid(), form.errors.as_json())
        self.assertEqual(
            form.questionnaire_answers, {'issue': 'pipe', 'urgent': False},
        )
        missing = self.payload(version.pk, q_issue='', q_urgent='')
        invalid = OrderCreateForm(missing)
        self.assertFalse(invalid.is_valid())
        self.assertIn('q_issue', invalid.errors)
        self.assertIn('q_urgent', invalid.errors)
        wrong = OrderCreateForm(self.payload(version.pk, q_issue='not_an_option'))
        self.assertFalse(wrong.is_valid())
        self.assertIn('q_issue', wrong.errors)

    def test_stale_or_forged_version_cannot_create_order(self):
        old = self.publish()
        self.client.force_login(self.owner)
        edited = deepcopy(self.draft.draft_schema)
        edited[0]['labels']['ru'] = 'Новая редакция'
        self.draft.draft_schema = edited
        self.draft.save(update_fields=['draft_schema'])
        new, inserted = publish_questionnaire(self.draft.pk)
        self.assertTrue(inserted)
        self.assertNotEqual(old.pk, new.pk)
        invalid = self.client.post(
            reverse('marketplace:order_create'), self.payload(old.pk),
        )
        self.assertEqual(invalid.status_code, 200)
        self.assertContains(invalid, 'Анкета изменилась.')
        self.assertFalse(Order.objects.exists())
        forged = self.client.post(
            reverse('marketplace:order_create'), self.payload('99999999'),
        )
        self.assertEqual(forged.status_code, 200)
        self.assertFalse(Order.objects.exists())

    def test_snapshot_stays_old_after_admin_republishes(self):
        version = self.publish()
        self.client.force_login(self.owner)
        self.client.post(reverse('marketplace:order_create'), self.payload(version.pk))
        order = Order.objects.get(client=self.owner)
        previous = deepcopy(order.questionnaire_answer.schema_snapshot)
        edited = deepcopy(self.draft.draft_schema)
        edited[0]['labels']['ru'] = 'Новая редакция анкеты'
        self.draft.draft_schema = edited
        self.draft.save(update_fields=['draft_schema'])
        publish_questionnaire(self.draft.pk)
        order.questionnaire_answer.refresh_from_db()
        self.assertEqual(order.questionnaire_answer.schema_snapshot, previous)
        with override('en'):
            rows = present_order_answers(order.questionnaire_answer)
            self.assertEqual(rows[0]['label'], 'Where is the leak?')
            self.assertEqual(rows[0]['value'], 'Pipe')
        with self.assertRaises(ValidationError):
            order.questionnaire_answer.save()

    def test_category_mismatch_and_inactive_service_rejected(self):
        v = self.publish()
        another = Category.objects.create(
            slug='qa025-other', name_ru='Другие услуги',
        )
        form = OrderCreateForm(self.payload(v.pk, category=str(another.pk)))
        self.assertFalse(form.is_valid())
        self.service.is_active = False
        self.service.save(update_fields=['is_active'])
        self.client.force_login(self.owner)
        response = self.client.post(
            reverse('marketplace:order_create'), self.payload(v.pk),
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Order.objects.exists())

    def test_legacy_order_without_subcategory_remains_unchanged(self):
        self.publish()
        self.client.force_login(self.owner)
        data = self.payload()
        data.pop('subcategory')
        data.pop('questionnaire_version')
        for key in ('q_issue', 'q_urgent', 'q_access'):
            data.pop(key)
        result = self.client.post(reverse('marketplace:order_create'), data)
        self.assertEqual(result.status_code, 302)
        order = Order.objects.get(client=self.owner)
        self.assertFalse(OrderQuestionnaireAnswer.objects.filter(order=order).exists())

    def test_custom_answer_is_limited_and_no_arbitrary_question_is_saved(self):
        v = self.publish()
        form = OrderCreateForm(self.payload(
            v.pk, q_access='x' * 501, q_fake='private-forged-payload',
        ))
        self.assertFalse(form.is_valid())
        self.assertIn('q_access', form.errors)
        valid = OrderCreateForm(self.payload(
            v.pk, q_fake='private-forged-payload',
        ))
        self.assertTrue(valid.is_valid(), valid.errors.as_json())
        self.assertNotIn('fake', valid.questionnaire_answers)


class QuestionnaireDemoSeedTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        for category_slug, service_slug, _ in DEMO_QUESTIONNAIRES:
            category = Category.objects.create(
                slug=category_slug, name_ru=category_slug,
            )
            Subcategory.objects.create(
                category=category, slug=service_slug, name_ru=service_slug,
            )

    def run_demo(self, *args):
        stream = StringIO()
        call_command('seed_demo_questionnaires', *args, stdout=stream)
        return stream.getvalue()

    def test_plan_no_db_and_publish_twice_is_idempotent(self):
        self.assertIn('PLAN: 4', self.run_demo('--plan'))
        self.assertFalse(ServiceQuestionnaire.objects.exists())
        self.run_demo('--publish')
        self.assertEqual(ServiceQuestionnaire.objects.count(), 4)
        self.assertEqual(QuestionnaireVersion.objects.count(), 4)
        self.run_demo('--check')
        again = self.run_demo('--publish')
        self.assertIn('new versions 0', again)
        self.assertEqual(QuestionnaireVersion.objects.count(), 4)

    def test_admin_edit_kept_by_idempotent_seed(self):
        self.run_demo('--publish')
        obj = ServiceQuestionnaire.objects.first()
        old_pk = obj.pk
        schema = deepcopy(obj.draft_schema)
        schema[0]['labels']['ru'] = 'Правка администратора'
        obj.draft_schema = schema
        obj.save(update_fields=['draft_schema'])
        self.run_demo()
        obj.refresh_from_db()
        self.assertEqual(obj.pk, old_pk)
        self.assertEqual(obj.draft_schema[0]['labels']['ru'], 'Правка администратора')
