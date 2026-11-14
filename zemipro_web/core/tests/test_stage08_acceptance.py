"""Stage 08.7 acceptance: RTL visual contract and safe isolated UI E2E."""
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils.translation import override

from apps.marketplace.wizard_services import _budget_label

from apps.locations.models import City
from apps.marketplace.models import Category, Subcategory
from apps.marketplace.tests.factories import make_user


class VisualContractSourceTests(SimpleTestCase):
    def test_browser_runner_cannot_use_production_or_disable_django_async_guard(self):
        text = (
            Path(settings.BASE_DIR) / "scripts/stage08_ux_e2e.py"
        ).read_text(encoding="utf-8")
        self.assertIn('settings.ENVIRONMENT != "test"', text)
        self.assertIn('ZEMIPRO_TEST_ASHDOD_ONLY', text)
        self.assertIn("ThreadPoolExecutor", text)
        self.assertIn("db_call(", text)
        self.assertNotIn("DJANGO_ALLOW_ASYNC_UNSAFE", text)
        self.assertNotIn("https://", text)
        for visible in (
            "create_published_request", "submit_worker_offer",
            "owner_accept_and_chat", "report_message", "RatingReply",
        ):
            self.assertIn(visible, text)

    def test_negotiable_budget_preview_is_localized_without_price_mutation(self):
        for language, expected in (
            ("ru", "Договорная"),
            ("en", "Negotiable"),
            ("he", "לפי סיכום"),
        ):
            with self.subTest(language=language), override(language):
                self.assertEqual(
                    _budget_label({"price_type": "negotiable"}), expected
                )
        offer_form = (
            Path(settings.BASE_DIR) / "templates/pages/offer_form.html"
        ).read_text(encoding="utf-8")
        self.assertIn('{% trans order.price %}', offer_form)

    def test_wizard_step_numbers_are_ltr_isolated_without_changing_rtl_document(self):
        text = (
            Path(settings.BASE_DIR) / "templates/pages/order_wizard.html"
        ).read_text(encoding="utf-8")
        self.assertIn('<bdi dir="ltr">{{ item.number }} / 8</bdi>', text)
        self.assertNotIn('<span class="zw-step-number">{{ item.number }} / 8</span>', text)


@override_settings(ZEMIPRO_PILOT_CITY_SLUG="ashdod")
class VisualContractPagesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.city = City.objects.create(
            slug="ashdod", name_ru="Ашдод",
            name_en="Ashdod", name_he="אשדוד",
        )
        cls.cat = Category.objects.create(
            slug="stage08-7-rtl-category", name_ru="Услуги",
            name_en="Services", name_he="שירותים",
        )
        cls.service = Subcategory.objects.create(
            category=cls.cat, slug="stage08-7-rtl-service",
            name_ru="Услуга", name_en="Service", name_he="שירות",
        )
        cls.owner = make_user("stage08-7-rtl-owner")

    def test_harmonized_wizard_step_number_order_in_all_three_languages(self):
        self.client.force_login(self.owner)
        for lang, expected_dir in (("ru", "ltr"), ("en", "ltr"), ("he", "rtl")):
            with self.subTest(language=lang):
                res = self.client.get(
                    reverse("marketplace:order_wizard_start"),
                    HTTP_ACCEPT_LANGUAGE=lang,
                )
                self.assertEqual(res.status_code, 200)
                self.assertContains(
                    res, f'<html lang="{lang}" dir="{expected_dir}">'
                )
                for step in range(1, 9):
                    self.assertContains(
                        res, f'<bdi dir="ltr">{step} / 8</bdi>'
                    )
                self.assertContains(res, 'role="note"')
                self.assertContains(res, '<progress')
