import unittest
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

import config
import external_app


class FakeControl:
    def __init__(self, label):
        self.label = label
        self.click = MagicMock()

    def is_visible(self):
        return True

    def get_attribute(self, name):
        return None

    def inner_text(self):
        return self.label

    def scroll_into_view_if_needed(self):
        return None

    def is_disabled(self):
        return False


class FakeLocator:
    def __init__(self, controls):
        self.controls = controls

    def count(self):
        return len(self.controls)

    def nth(self, index):
        return self.controls[index]


class FakePage:
    url = "https://careers.example.test/start"

    def __init__(self, controls):
        self.controls = controls

    def locator(self, selector):
        return FakeLocator(self.controls)

    def wait_for_timeout(self, milliseconds):
        return None

    def wait_for_load_state(self, *args, **kwargs):
        return None


class ExternalStartControlSafetyTests(unittest.TestCase):
    def _start_patches(self, page):
        return (
            patch.object(external_app, "_looks_like_application_form", return_value=False),
            patch.object(external_app, "_all_application_pages", return_value=[page]),
            patch.object(external_app, "_wait_for_external_application", return_value=page),
            patch.object(external_app, "element_diagnostic", return_value={}),
            patch.object(external_app, "write_diagnostic"),
        )

    def test_submit_application_is_not_an_external_start_control(self):
        submit = FakeControl("Submit application")
        page = FakePage([submit])

        with (
            patch.object(external_app, "_looks_like_application_form", return_value=False),
            patch.object(external_app, "_all_application_pages", return_value=[page]),
        ):
            result = external_app._click_external_application_start(page)

        self.assertIs(result, page)
        submit.click.assert_not_called()

    def test_detector_miss_cannot_route_submit_application_through_start_path(self):
        submit = FakeControl("Submit application")
        page = FakePage([submit])

        with (
            patch.object(external_app, "detect_ats", return_value="UNKNOWN"),
            patch.object(external_app, "_text", return_value="Company careers"),
            patch.object(external_app, "_external_page_has_error", return_value=False),
            patch.object(external_app, "_wait_for_manual_consent", return_value=True),
            patch.object(external_app, "_looks_like_application_form", return_value=False),
            patch.object(external_app, "_all_application_pages", return_value=[page]),
        ):
            result = external_app.prepare_external_application_page(page)

        self.assertEqual(result, "FORM_NOT_FOUND")
        submit.click.assert_not_called()

    def test_legitimate_apply_now_start_control_still_clicks(self):
        apply = FakeControl("Apply now")
        page = FakePage([apply])

        with ExitStack() as stack:
            for patcher in self._start_patches(page):
                stack.enter_context(patcher)
            result = external_app._click_external_application_start(page)

        self.assertIs(result, page)
        apply.click.assert_called_once_with(timeout=5000)

    def test_final_submit_routine_can_click_submit_when_enabled(self):
        submit = FakeControl("Submit application")
        page = FakePage([submit])

        with (
            patch.object(config, "AUTO_SUBMIT", True),
            patch.object(external_app, "UNKNOWN_QUESTIONS_POLICY", "SKIP"),
            patch.object(external_app, "_required_empty_count", return_value=0),
            patch.object(external_app, "_external_submission_verified", return_value=True),
        ):
            result = external_app._auto_submit_external_application(page)

        self.assertEqual(result, "SUBMITTED")
        submit.click.assert_called_once_with()

    def test_auto_submit_false_returns_ready_without_clicking_final_submit(self):
        submit = FakeControl("Submit application")
        page = FakePage([submit])

        with (
            patch.object(config, "AUTO_SUBMIT", False),
            patch.object(external_app, "UNKNOWN_QUESTIONS_POLICY", "SKIP"),
            patch.object(external_app, "_find_final_submit_control") as find_submit,
        ):
            result = external_app._auto_submit_external_application(page)

        self.assertEqual(result, "READY_FOR_REVIEW")
        find_submit.assert_not_called()
        submit.click.assert_not_called()


if __name__ == "__main__":
    unittest.main()
