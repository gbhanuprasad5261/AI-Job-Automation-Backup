import unittest
from unittest.mock import patch

import config
import external_app


class FakeLocator:
    def __init__(self, elements=()):
        self.elements = list(elements)

    def count(self):
        return len(self.elements)

    def nth(self, index):
        return self.elements[index]


class FakeControl:
    def __init__(self, label="", page=None):
        self.label = label
        self.page = page
        self.checked = False
        self.click_count = 0
        self.check_count = 0

    def is_visible(self):
        return True

    def is_checked(self):
        return self.checked

    def inner_text(self):
        return self.label

    def get_attribute(self, name):
        return None

    def evaluate(self, _script):
        return ""

    def locator(self, _selector):
        return FakeLocator()

    def click(self, *args, **kwargs):
        self.click_count += 1
        if self.page is not None:
            self.page.dialog_visible = False

    def check(self):
        self.check_count += 1
        self.checked = True

    def scroll_into_view_if_needed(self):
        return None


class FakePage:
    def __init__(self, banner_label="Accept", checkbox=None):
        self.url = "https://careers.example.test/application"
        self.dialog_visible = True
        self.banner = FakeControl(
            banner_label,
            page=self,
        )
        self.checkbox = checkbox
        self.wait_for_timeout_calls = []

    def locator(self, selector):
        if selector == "dialog, [role='dialog'], [aria-modal='true']":
            return FakeLocator([self] if self.dialog_visible else [])
        if selector == "input[type='checkbox']":
            return FakeLocator([self.checkbox] if self.checkbox is not None else [])
        if selector.startswith("button,"):
            return FakeLocator([self.banner] if self.dialog_visible else [])
        if selector == "body":
            return FakeBody(self)
        return FakeLocator()

    def inner_text(self):
        if self.dialog_visible:
            return "Privacy policy and cookie consent"
        return ""

    def is_visible(self):
        return self.dialog_visible

    def wait_for_timeout(self, milliseconds):
        self.wait_for_timeout_calls.append(milliseconds)

    def wait_for_load_state(self, *args, **kwargs):
        return None


class FakeBody:
    def __init__(self, page):
        self.page = page

    def inner_text(self):
        return self.page.inner_text()


class ConsentSafetyTests(unittest.TestCase):
    def test_auto_submit_false_banner_returns_ready_without_accepting(self):
        page = FakePage("Accept All")

        with (
            patch.object(config, "AUTO_SUBMIT", False),
            patch.object(external_app, "_text", return_value="Company careers"),
            patch.object(external_app, "detect_ats", return_value="UNKNOWN"),
            patch.object(external_app, "_external_page_has_error", return_value=False),
            patch.object(external_app, "_click_external_application_start") as click_start,
        ):
            result = external_app.prepare_external_application_page(page)

        self.assertEqual(result, "READY_FOR_REVIEW")
        self.assertEqual(page.banner.click_count, 0)
        click_start.assert_not_called()

    def test_auto_submit_false_terms_consent_returns_ready_without_checking(self):
        checkbox = FakeControl()
        page = FakePage(checkbox=checkbox)

        with (
            patch.object(config, "AUTO_SUBMIT", False),
            patch.object(external_app, "detect_ats", return_value="UNKNOWN"),
            patch.object(external_app, "_text", return_value="Company application form"),
            patch.object(external_app, "_external_page_has_error", return_value=False),
            patch.object(external_app, "_wait_for_manual_consent", return_value=True),
            patch.object(external_app, "_click_external_application_start", return_value=page),
            patch.object(external_app, "_looks_like_application_form", return_value=True),
            patch.object(external_app, "_fill_known_application_fields", return_value=0),
            patch.object(external_app, "_fill_known_fields", return_value=0),
            patch.object(external_app, "_fill_known_profile_links", return_value=0),
            patch.object(external_app, "_select_known_dropdowns", return_value=0),
            patch.object(external_app, "_field_text", return_value="I agree to data privacy terms"),
            patch.object(external_app, "_required_empty_count") as required_count,
        ):
            result = external_app.prepare_external_application_page(page)

        self.assertEqual(result, "READY_FOR_REVIEW")
        self.assertFalse(checkbox.checked)
        self.assertEqual(checkbox.check_count, 0)
        self.assertEqual(checkbox.click_count, 0)
        required_count.assert_not_called()

    def test_auto_submit_true_keeps_cookie_consent_acceptance(self):
        page = FakePage("Agree")

        with patch.object(config, "AUTO_SUBMIT", True):
            result = external_app._wait_for_manual_consent(
                page,
                detection_timeout_ms=1,
                wait_timeout_ms=1,
            )

        self.assertTrue(result)
        self.assertEqual(page.banner.click_count, 1)

    def test_auto_submit_true_keeps_terms_privacy_checkbox_behavior(self):
        checkbox = FakeControl()
        page = FakePage(checkbox=checkbox)

        with (
            patch.object(config, "AUTO_SUBMIT", True),
            patch.object(external_app, "_field_text", return_value="I agree to data privacy terms"),
        ):
            checked = external_app._check_known_terms_consent(page)

        self.assertEqual(checked, 1)
        self.assertTrue(checkbox.checked)
        self.assertEqual(checkbox.check_count, 1)


if __name__ == "__main__":
    unittest.main()
