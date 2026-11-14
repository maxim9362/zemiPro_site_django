"""Recipient-language and privacy checks for existing Stage 06 notices."""

from types import SimpleNamespace
from django.test import SimpleTestCase
from django.utils.translation import override
from apps.marketplace.offer_ui import stage06_notice


class Stage06NoticeLanguages(SimpleTestCase):
    def test_recipient_language_overrides_request_language(self):
        for kind in (
            "new_response",
            "response_accepted",
            "response_rejected",
            "order_updated",
            "order_completed",
            "review_created",
        ):
            notices = []
            with override("ru"):
                for lang in ("ru", "en", "he"):
                    recipient = SimpleNamespace(preferred_language=lang)
                    notice = stage06_notice(recipient, kind, 12345)
                    self.assertIn("12345", notice["message"])
                    notices.append(notice["title"])
            self.assertEqual(len(set(notices)), 3)

    def test_unknown_language_has_safe_fallback(self):
        self.assertEqual(
            stage06_notice(SimpleNamespace(preferred_language="unknown"), "new_response", 1),
            stage06_notice(SimpleNamespace(preferred_language="ru"), "new_response", 1),
        )
