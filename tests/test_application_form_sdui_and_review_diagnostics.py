import contextlib
import io
import json
import re
import unittest
from unittest.mock import patch

import application_form
import config


SDUI_SELECTOR = (
    'div[data-sdui-screen="'
    'com.linkedin.sdui.flagshipnav.jobs.easyapply.EasyApply"]'
)


class FakeLocator:
    def __init__(self, items=()):
        self.items = list(items)

    def count(self):
        return len(self.items)

    def nth(self, index):
        return self.items[index]


class FakeContainer:
    def __init__(self, *, visible=True, text="Contact info Resume", class_name=""):
        self.visible = visible
        self.text = text
        self.class_name = class_name

    def is_visible(self):
        return self.visible

    def get_attribute(self, name):
        return {"class": self.class_name}.get(name)

    def inner_text(self, *args, **kwargs):
        return self.text

    def locator(self, selector):
        if selector.startswith("button,") or selector.startswith("input:not"):
            return FakeLocator([object()])
        return FakeLocator()


class FakeApplicationPage:
    # This reproduces the TCS URL where the LinkedIn ATS query parameter is absent.
    url = "https://www.linkedin.com/jobs/view/4472304771/?companyName=TCS"

    def __init__(self, *, sdui=None, legacy=None):
        self.sdui = sdui
        self.legacy = legacy

    def locator(self, selector):
        if selector == SDUI_SELECTOR:
            return FakeLocator([self.sdui] if self.sdui is not None else [])
        if selector == ".jobs-easy-apply-modal":
            return FakeLocator([self.legacy] if self.legacy is not None else [])
        return FakeLocator()


class FakeReviewButton:
    def __init__(self, text, visible=True, enabled=True):
        self.text = text
        self.visible = visible
        self.enabled = enabled

    def is_visible(self):
        return self.visible

    def is_enabled(self):
        return self.enabled

    def inner_text(self):
        return self.text

    def get_attribute(self, name):
        return None


class FakeReviewBody:
    def __init__(self, text):
        self.text = text

    def inner_text(self, **kwargs):
        return self.text


class FakeReviewPage:
    def __init__(self, text, buttons):
        self.body = FakeReviewBody(text)
        self.buttons = buttons

    def locator(self, selector):
        if selector == "body":
            return self.body
        if selector == "button":
            return FakeLocator(self.buttons)
        return FakeLocator()


class EasyApplyContainerTests(unittest.TestCase):
    def test_visible_sdui_root_is_accepted(self):
        screen = FakeContainer(visible=True)
        page = FakeApplicationPage(sdui=screen)

        self.assertIn(SDUI_SELECTOR, application_form._candidate_application_selectors())
        self.assertIs(application_form.get_application_container(page, wait_seconds=0), screen)

    def test_hidden_sdui_root_is_not_accepted(self):
        screen = FakeContainer(visible=False)
        page = FakeApplicationPage(sdui=screen)

        self.assertIsNone(application_form.get_application_container(page, wait_seconds=0))

    def test_legacy_selector_remains_supported(self):
        legacy = FakeContainer(
            visible=True,
            text="Easy Apply application",
            class_name="jobs-easy-apply-modal",
        )
        page = FakeApplicationPage(legacy=legacy)

        self.assertIn(".jobs-easy-apply-modal", application_form._candidate_application_selectors())
        self.assertIs(application_form.get_application_container(page, wait_seconds=0), legacy)

    def test_auto_submit_false_still_stops_before_submit_lookup(self):
        with (
            patch.object(config, "AUTO_SUBMIT", False),
            patch.object(application_form, "verify_final_review_page", return_value=True),
            patch.object(application_form, "find_submit_button") as find_submit,
        ):
            result = application_form.handle_final_submission(object())

        self.assertEqual(result, "READY_FOR_REVIEW")
        find_submit.assert_not_called()


class FinalReviewDiagnosticTests(unittest.TestCase):
    def test_engineering_square_review_evidence_is_exposed_without_changing_verifier(self):
        # Concise text evidence captured from the Phase 7N live Review page.
        review_text = (
            "4/4 pages Review your application. Contact info. Resume. "
            "Work authorization. We must fill this position urgently. "
            "Can you start immediately? Yes. Submit application."
        )
        page = FakeReviewPage(
            review_text,
            [
                FakeReviewButton("Submit application", visible=True, enabled=True),
                FakeReviewButton("Submit", visible=False, enabled=False),
            ],
        )
        blocking_phrases = (
            "this field is required",
            "please fill out this field",
            "required field",
            "required information is missing",
            "please correct the errors",
            "error occurred",
        )
        review_signals = (
            "review your application",
            "additional questions",
            "resume",
            "application",
        )
        normalized = re.sub(r"\s+", " ", review_text).strip().lower()

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            verifier_result = application_form.verify_final_review_page(page)

        verifier_output = output.getvalue()
        visible_enabled_submit_count = sum(
            1
            for button in page.locator("button").items
            if button.is_visible()
            and button.is_enabled()
            and re.search(r"\bsubmit application\b", button.inner_text(), re.I)
        )
        diagnostics = {
            "blocking_phrases": [p for p in blocking_phrases if p in normalized],
            "review_signal_count": sum(signal in normalized for signal in review_signals),
            "answer_pair_matches": verifier_output.count("✓ "),
            "answer_pair_total": verifier_output.count("Could not text-verify:"),
            "visible_enabled_submit_application_buttons": visible_enabled_submit_count,
            "verifier_result": verifier_result,
        }

        self.assertEqual(
            diagnostics,
            {
                "blocking_phrases": [],
                "review_signal_count": 3,
                "answer_pair_matches": 0,
                "answer_pair_total": 7,
                "visible_enabled_submit_application_buttons": 1,
                "verifier_result": False,
            },
            msg=json.dumps(diagnostics, sort_keys=True),
        )
        self.assertIn("No configured answer could be verified", verifier_output)


if __name__ == "__main__":
    unittest.main()
