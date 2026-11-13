"""Stage 04.2: eight-step, resumable, multilingual and private order wizard."""
from datetime import timedelta

from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import override

from apps.locations.models import City
from apps.marketplace.models import (
    Category, Order, OrderQuestionnaireAnswer,
    ServiceQuestionnaire, Subcategory,
)
from apps.marketplace.questionnaire_examples import DEMO_QUESTIONNAIRES
from apps.marketplace.questionnaire_services import publish_questionnaire
from apps.marketplace.tests.factories import make_user
from apps.marketplace.wizard_services import publish_order_wizard


@override_settings(ZEMIPRO_PILOT_CITY_SLUG='ashdod')
class OrderWizardFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ashdod = City.objects.create(
            slug='ashdod', name_ru='Ашдод', name_en='Ashdod', name_he='אשדוד',
        )
        cls.haifa = City.objects.create(
            slug='haifa', name_ru='Хайфа', name_en='Haifa', name_he='חיפה',
        )
        cls.owner = make_user('stage04-wizard-owner')
        cls.stranger = make_user('stage04-wizard-stranger')
        cls.categories = []
        cls.services = []
        for index, (ru, en, he, mode) in enumerate((
            ('Ремонт', 'Repairs', 'תיקונים', 'onsite'),
            ('Обучение', 'Tutoring', 'לימוד', 'online'),
            ('Фотография', 'Photography', 'צילום', 'both'),
        )):
            category = Category.objects.create(
                slug=f'04-category-{index}', name_ru=ru, name_en=en,
                name_he=he, work_mode=mode,
            )
            service = Subcategory.objects.create(
                category=category, slug=f'04-service-{index}',
                name_ru=f'{ru} — услуга', name_en=f'{en} service',
                name_he=f'{he} שירות', work_mode=mode,
            )
            cls.categories.append(category)
            cls.services.append(service)
        questionnaire = ServiceQuestionnaire.objects.create(
            service=cls.services[0], draft_schema=DEMO_QUESTIONNAIRES[0][2],
        )
        cls.version, _ = publish_questionnaire(questionnaire.pk)

    def setUp(self):
        self.client.force_login(self.owner)

    def begin(self, index=0):
        url = reverse('marketplace:order_wizard_start')
        page = self.client.get(url)
        self.assertEqual(page.status_code, 200)
        token = page.context['token']
        self.assertTrue(token)
        submitted = self.client.post(url, {
            'action': 'start', 'token': token,
            'category': self.categories[index].pk,
            'subcategory': self.services[index].pk,
        })
        self.assertEqual(submitted.status_code, 302)
        order = Order.objects.get(wizard_token=token)
        self.assertEqual(order.status, Order.Status.DRAFT)
        self.assertEqual(order.client_id, self.owner.pk)
        return order, token

    def post_step(self, order, step, payload):
        url = reverse('marketplace:order_wizard_edit', args=[order.pk])
        return self.client.post(
            f'{url}?step={step}',
            {'action': 'publish' if step == 8 else 'next', **payload},
        )

    def finish_steps(self, order, index=0, *, blank_description=False):
        values = (
            {
                'questionnaire_version': str(self.version.pk),
                'q_issue': 'pipe', 'q_urgent': 'false',
            } if index == 0 else {'questionnaire_version': ''}
        )
        steps = {
            2: values,
            3: {
                'city': self.ashdod.pk,
                'mode': ('onsite', 'online', 'online')[index],
                'area': 'Ashdod, central area',
            },
            4: {
                'preferred_date': (timezone.localdate() + timedelta(days=3)).isoformat(),
                'urgency': 'soon',
            },
            5: {'price_type': 'range', 'amount_min': '200', 'amount_max': '500'},
            6: {
                'description': '' if blank_description else
                'A synthetic service request describing the scope of work.',
            },
            7: {'display_name': 'Test User', 'chat_ack': 'on'},
        }
        for step, payload in steps.items():
            with self.subTest(step=step):
                response = self.post_step(order, step, payload)
                self.assertEqual(response.status_code, 302, response.content[:1000])
        order.refresh_from_db()
        self.assertEqual(set(order.wizard_data['steps']), {
            '1', '2', '3', '4', '5', '6', '7',
        })

    def test_three_services_in_ru_en_he_and_no_contact_leak(self):
        for index in range(3):
            for lang in ('ru', 'en', 'he'):
                with self.subTest(service=index, language=lang), override(lang):
                    self.client.defaults['HTTP_ACCEPT_LANGUAGE'] = lang
                    order, _ = self.begin(index)
                    self.finish_steps(order, index)
                    page = self.client.get(
                        reverse('marketplace:order_wizard_edit', args=[order.pk]) + '?step=8'
                    )
                    self.assertContains(page, order.subcategory.localized_name)
                    self.assertContains(page, 'dir="rtl"' if lang == 'he' else 'dir="ltr"')
                    self.assertContains(page, 'אשדוד' if lang == 'he' else ('Ashdod' if lang == 'en' else 'Ашдод'))
                    result = self.post_step(order, 8, {'confirm': 'on'})
                    self.assertEqual(result.status_code, 302)
                    order.refresh_from_db()
                    self.assertEqual(order.status, Order.Status.PUBLISHED)
                    self.assertEqual(order.city_id, self.ashdod.pk)
                    self.assertEqual(order.price, '200.00–500.00 ₪')
                    self.assertEqual(order.customer_name, 'Test User')
                    self.assertEqual(order.customer_phone, '')
                    self.assertEqual(order.address, '')
                    self.assertEqual(order.status_events.filter(
                        new_status=Order.Status.PUBLISHED,
                    ).count(), 1)
                    if index == 0:
                        self.assertEqual(
                            OrderQuestionnaireAnswer.objects.get(order=order).answers,
                            {'issue': 'pipe', 'urgent': False},
                        )
                    else:
                        self.assertFalse(OrderQuestionnaireAnswer.objects.filter(order=order).exists())
                    self.assertNotContains(
                        self.client.get(reverse('marketplace:order_detail', args=[order.pk])),
                        '0500000000',
                    )

    def test_draft_survives_new_session_and_can_go_back(self):
        order, _ = self.begin()
        response = self.post_step(order, 2, {
            'questionnaire_version': self.version.pk,
            'q_issue': 'pipe', 'q_urgent': 'false',
        })
        self.assertEqual(response.status_code, 302)
        response = self.post_step(order, 3, {
            'city': self.ashdod.pk, 'mode': 'onsite',
            'area': 'synthetic neighbourhood',
        })
        self.assertEqual(response.status_code, 302)
        # A different session for the same account restores from PostgreSQL.
        browser = Client()
        browser.force_login(self.owner)
        url = reverse('marketplace:order_wizard_edit', args=[order.pk])
        restored = browser.get(url + '?step=3')
        self.assertEqual(restored.status_code, 200)
        self.assertEqual(restored.context['form'].initial['area'], 'synthetic neighbourhood')
        previous = browser.get(url + '?step=2')
        self.assertEqual(previous.status_code, 200)
        self.assertContains(previous, 'q_issue')

    def test_replayed_start_and_publish_are_single_order_and_event(self):
        order, token = self.begin()
        self.assertEqual(Order.objects.filter(wizard_token=token).count(), 1)
        # The token was consumed; replay is rejected, not another order.
        failed = self.client.post(reverse('marketplace:order_wizard_start'), {
            'action': 'start', 'token': token,
            'category': self.categories[0].pk, 'subcategory': self.services[0].pk,
        })
        self.assertEqual(failed.status_code, 404)
        self.finish_steps(order)
        published = self.post_step(order, 8, {'confirm': 'on'})
        repeated = self.post_step(order, 8, {'confirm': 'on'})
        self.assertEqual(published.status_code, 302)
        self.assertEqual(repeated.status_code, 302)
        self.assertEqual(Order.objects.filter(wizard_token=token).count(), 1)
        self.assertEqual(order.status_events.filter(
            new_status=Order.Status.PUBLISHED,
        ).count(), 1)

    def test_cannot_skip_questions_or_forge_other_city(self):
        order, _ = self.begin()
        url = reverse('marketplace:order_wizard_edit', args=[order.pk])
        skipped = self.client.get(url + '?step=8')
        self.assertEqual(skipped.status_code, 302)
        forged = self.post_step(order, 3, {
            'city': self.haifa.pk, 'mode': 'onsite', 'area': 'haifa',
        })
        self.assertEqual(forged.status_code, 302)
        self.assertNotIn('3', Order.objects.get(pk=order.pk).wizard_data['steps'])
        self.post_step(order, 2, {
            'questionnaire_version': self.version.pk,
            'q_issue': 'pipe', 'q_urgent': 'false',
        })
        illegal = self.post_step(order, 3, {
            'city': self.haifa.pk, 'mode': 'onsite', 'area': 'haifa',
        })
        self.assertEqual(illegal.status_code, 200)
        self.assertIn('city', illegal.context['form'].errors)
        self.assertEqual(Order.objects.get(pk=order.pk).city_id, self.ashdod.pk)

    def test_foreign_user_cannot_open_or_post_to_draft(self):
        order, _ = self.begin()
        self.client.force_login(self.stranger)
        url = reverse('marketplace:order_wizard_edit', args=[order.pk])
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.post(url + '?step=2', {'action': 'next'}).status_code, 404)
        self.assertEqual(self.client.get(
            reverse('marketplace:order_detail', args=[order.pk])
        ).status_code, 404)
        self.assertFalse(Order.objects.filter(client=self.stranger).exists())

    def test_questions_are_revalidated_before_publish(self):
        order, _ = self.begin()
        self.finish_steps(order)
        questionnaire = ServiceQuestionnaire.objects.get(service=self.services[0])
        schema = [dict(item) for item in questionnaire.draft_schema]
        schema[0] = dict(schema[0])
        schema[0]['labels'] = dict(schema[0]['labels'])
        schema[0]['labels']['ru'] = 'Обновлённый вопрос'
        questionnaire.draft_schema = schema
        questionnaire.save(update_fields=['draft_schema'])
        publish_questionnaire(questionnaire.pk)
        attempt = self.post_step(order, 8, {'confirm': 'on'})
        self.assertEqual(attempt.status_code, 200)
        self.assertEqual(Order.objects.get(pk=order.pk).status, Order.Status.DRAFT)
        self.assertFalse(OrderQuestionnaireAnswer.objects.filter(order=order).exists())

    def test_service_change_invalidates_later_draft_steps(self):
        order, _ = self.begin()
        self.finish_steps(order)
        result = self.post_step(order, 1, {
            'category': self.categories[1].pk, 'subcategory': self.services[1].pk,
        })
        self.assertEqual(result.status_code, 302)
        order.refresh_from_db()
        self.assertEqual(set(order.wizard_data['steps']), {'1'})
        self.assertEqual(order.subcategory_id, self.services[1].pk)

    def test_no_question_and_no_description_cannot_publish(self):
        order, _ = self.begin(1)
        self.finish_steps(order, 1, blank_description=True)
        response = self.post_step(order, 8, {'confirm': 'on'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Order.objects.get(pk=order.pk).status, Order.Status.DRAFT)

    def test_blocked_owner_cannot_publish_using_service(self):
        order, _ = self.begin()
        self.finish_steps(order)
        self.owner.is_blocked = True
        self.owner.save(update_fields=['is_blocked'])
        from django.core.exceptions import PermissionDenied
        with self.assertRaises(PermissionDenied):
            publish_order_wizard(order_id=order.pk, actor=self.owner)
        self.assertEqual(Order.objects.get(pk=order.pk).status, Order.Status.DRAFT)

    def test_missing_csrf_token_rejected_on_start(self):
        browser = Client(enforce_csrf_checks=True)
        browser.force_login(self.owner)
        response = browser.post(reverse('marketplace:order_wizard_start'), {
            'action': 'start',
            'category': self.categories[0].pk,
            'subcategory': self.services[0].pk,
        })
        self.assertEqual(response.status_code, 403)
