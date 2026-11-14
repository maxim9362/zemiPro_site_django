"""Stage08.6 focused accessible forms, contrast, RTL and owner wizard tests."""
from pathlib import Path
import re

from django import forms
from django.conf import settings
from django.test import SimpleTestCase, TestCase, override_settings
from django.template.loader import render_to_string
from django.urls import reverse

from apps.locations.models import City
from apps.marketplace.models import Category, Order, Subcategory
from apps.marketplace.tests.factories import make_user


def _relative_luminance(color):
    channels = [
        int(color[index:index + 2], 16) / 255
        for index in (1, 3, 5)
    ]
    linear = [
        c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
        for c in channels
    ]
    return sum(c * weight for c, weight in
               zip(linear, (0.2126, 0.7152, 0.0722)))


def _contrast(a, b):
    large, small = sorted((_relative_luminance(a),
                           _relative_luminance(b)), reverse=True)
    return (large + 0.05) / (small + 0.05)


class Stage08AccessibilitySources(SimpleTestCase):
    def test_focus_tokens_meet_contrast_on_light_and_dark_surfaces(self):
        css = (Path(settings.BASE_DIR) / "static/css/design-system.css").read_text(
            encoding="utf-8"
        )
        values = dict(re.findall(
            r"(--ui-[a-z-]+):\s*(#[0-9a-fA-F]{6})", css
        ))
        self.assertGreaterEqual(_contrast(values["--ui-focus"], "#ffffff"), 3.0)
        self.assertGreaterEqual(_contrast(values["--ui-focus"], "#f6f9fc"), 3.0)
        self.assertGreaterEqual(
            _contrast(values["--ui-focus-dark"], values["--ui-primary"]), 3.0
        )
        self.assertGreaterEqual(
            _contrast(values["--ui-muted"], "#ffffff"), 4.5
        )
        self.assertIn(".btn--primary:focus-visible", css)
        self.assertIn(".btn--danger:focus-visible", css)
        self.assertIn(":focus-visible", css)
        self.assertIn("prefers-contrast:more", css)

    def test_bound_error_and_help_are_programmatically_associated(self):
        class SampleForm(forms.Form):
            term = forms.CharField(
                label="Service", min_length=4,
                help_text="<img src=x onerror=alert(1)>",
                widget=forms.TextInput(attrs={"aria-describedby": "earlier-help"}),
            )
        form = SampleForm({"term": "x"})
        self.assertFalse(form.is_valid())
        html = render_to_string("components/form_field.html", {
            "field": form["term"],
        })
        for expected in (
            'for="id_term"', 'id="id_term-help"',
            'id="id_term-errors"', 'role="alert"',
            'aria-invalid="true"',
            'aria-describedby="earlier-help id_term-help id_term-errors"',
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, html)
        self.assertIn("&lt;img", html)
        self.assertNotIn("<img", html)

    def test_clean_field_does_not_claim_invalid_state(self):
        class SampleForm(forms.Form):
            value = forms.CharField(required=False, label="Value")
        html = render_to_string("components/form_field.html", {
            "field": SampleForm()["value"],
        })
        self.assertIn('for="id_value"', html)
        self.assertNotIn('aria-invalid="true"', html)
        self.assertNotIn('id="id_value-errors"', html)

    def test_missing_javascript_does_not_hide_menu(self):
        source = (
            Path(settings.BASE_DIR) / "static/css/design-system.css"
        ).read_text(encoding="utf-8")
        js = (
            Path(settings.BASE_DIR) / "static/js/navigation.js"
        ).read_text(encoding="utf-8")
        self.assertIn(".has-nav-js .site-nav.nav:not(.is-open)", source)
        self.assertIn("classList.add('has-nav-js')", js)
        self.assertIn("event.key === 'Escape'", js)
        self.assertIn("trigger.focus()", js)
        self.assertIn("trigger.dataset.closeLabel", js)
        self.assertNotIn("innerHTML", js)

    def test_wizard_field_descriptions_survive_without_scripts(self):
        html = (
            Path(settings.BASE_DIR) / "templates/pages/order_wizard.html"
        ).read_text(encoding="utf-8")
        self.assertIn("{% load i18n static a11y_widgets %}", html)
        self.assertIn("ui_widget item.field help_id errors_id", html)
        self.assertIn("ui_widget field help_id errors_id", html)
        self.assertIn('id="wizard-current-step"', html)
        self.assertIn('id="wizard-errors"', html)
        self.assertIn('<noscript>', html)

    def test_css_responsive_reflow_present_in_all_three_page_styles(self):
        base = Path(settings.BASE_DIR) / "static/css"
        for filename in ("public-pages.css", "app-pages.css", "communication.css"):
            with self.subTest(filename=filename):
                css = (base / filename).read_text(encoding="utf-8")
                self.assertIn("Stage 08.6", css)
                self.assertIn("min-inline-size:0", css)
                self.assertIn("max-inline-size:100%", css)

    def test_smoke_is_ci_only_and_never_touches_production(self):
        src = (
            Path(settings.BASE_DIR) / "scripts/stage08_mobile_a11y_smoke.py"
        ).read_text(encoding="utf-8")
        self.assertIn('settings.ENVIRONMENT != "test"', src)
        self.assertIn('ZEMIPRO_TEST_ASHDOD_ONLY', src)
        self.assertIn('java_script_enabled=False', src)
        self.assertIn('WIDTHS = (320, 390, 768, 1440)', src)
        self.assertIn('"ru", "en", "he"', src)
        self.assertIn("check_control_labels(", src)
        self.assertIn("check_keyboard_disclosure(", src)


@override_settings(ZEMIPRO_PILOT_CITY_SLUG="ashdod")
class Stage08AccessibilityPages(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.city = City.objects.create(
            slug="ashdod", name_ru="Ашдод",
            name_en="Ashdod", name_he="אשדוד",
        )
        cls.category = Category.objects.create(
            slug="ui086-test", name_ru="Сантехника",
            name_en="Plumbing", name_he="אינסטלציה",
            work_mode="onsite",
        )
        cls.service = Subcategory.objects.create(
            category=cls.category, slug="ui086-service",
            name_ru="Замена крана", name_en="Faucet replacement",
            name_he="החלפת ברז", work_mode="onsite",
        )
        cls.user = make_user("ui086-owner")

    def test_menu_labels_and_skip_link_are_localized(self):
        for lang, open_label, close_label, direction in (
            ("ru", "Открыть меню", "Закрыть меню", "ltr"),
            ("en", "Open menu", "Close menu", "ltr"),
            ("he", "פתיחת התפריט", "סגירת התפריט", "rtl"),
        ):
            with self.subTest(language=lang):
                page = self.client.get(
                    reverse("marketplace:home"), HTTP_ACCEPT_LANGUAGE=lang
                )
                self.assertContains(
                    page, f'<html lang="{lang}" dir="{direction}">'
                )
                self.assertContains(page, 'data-open-label="' + open_label + '"')
                self.assertContains(page, 'data-close-label="' + close_label + '"')
                self.assertContains(page, 'aria-controls="site-navigation"')
                self.assertContains(page, 'href="#main-content"')

    def test_search_and_auth_forms_use_accessible_field_partial(self):
        for url in (
            reverse("marketplace:worker_directory"),
            reverse("accounts:login"),
            reverse("accounts:register"),
        ):
            with self.subTest(url=url):
                page = self.client.get(url)
                self.assertEqual(page.status_code, 200)
                self.assertContains(page, 'class="form__label ui-field__label"')

    def test_wizard_invalid_selection_marks_control_and_retains_category(self):
        self.client.force_login(self.user)
        path = reverse("marketplace:order_wizard_start")
        token = self.client.get(path).context["token"]
        response = self.client.post(path, {
            "action": "start", "token": token,
            "category": str(self.category.pk), "subcategory": "",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'aria-invalid="true"')
        self.assertContains(response, 'id="id_subcategory-errors"')
        self.assertContains(response, 'aria-describedby="id_subcategory-errors"')
        self.assertContains(response, 'name="category"')
        self.assertNotContains(response, "PRIVATE_086_UNRELATED")
        self.assertEqual(Order.objects.filter(client=self.user).count(), 0)

    def test_wizard_bound_area_preserves_state_in_hebrew(self):
        self.client.force_login(self.user)
        path = reverse("marketplace:order_wizard_start")
        token = self.client.get(path).context["token"]
        created = self.client.post(path, {
            "action": "start", "token": token,
            "category": str(self.category.pk),
            "subcategory": str(self.service.pk),
        })
        self.assertEqual(created.status_code, 302)
        draft = Order.objects.get(client=self.user)
        edit = reverse("marketplace:order_wizard_edit", args=[draft.pk])
        self.assertEqual(self.client.post(edit + "?step=2", {
            "action": "next", "questionnaire_version": "",
        }).status_code, 302)
        invalid = self.client.post(edit + "?step=3", {
            "action": "next", "city": "99999999",
            "mode": "onsite", "area": "Synthetic central area",
        }, HTTP_ACCEPT_LANGUAGE="he")
        self.assertEqual(invalid.status_code, 200)
        self.assertContains(invalid, 'dir="rtl"')
        self.assertContains(invalid, "Synthetic central area")
        self.assertContains(invalid, 'aria-invalid="true"')
        self.assertContains(invalid, 'id="id_city-errors"')
        draft.refresh_from_db()
        self.assertEqual(draft.status, Order.Status.DRAFT)
        self.assertNotIn("3", draft.wizard_data.get("steps", {}))
