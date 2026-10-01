import json
import os
import tempfile
import unittest
from unittest.mock import patch

import external_app
from runtime_diagnostics import (
    element_diagnostic,
    overlay_diagnostics,
    selector_diagnostics,
    write_diagnostic,
)


class FakeElement:
    def __init__(self, tag="div", attributes=None, text="", visible=True, click_error=None):
        self.tag = tag
        self.attributes = attributes or {}
        self.text = text
        self.visible = visible
        self.click_error = click_error

    def evaluate(self, _script):
        return self.tag

    def get_attribute(self, name):
        return self.attributes.get(name)

    def inner_text(self):
        return self.text

    def is_visible(self):
        return self.visible

    def scroll_into_view_if_needed(self):
        return None

    def click(self, timeout=None):
        if self.click_error:
            raise self.click_error


class FakeLocator:
    def __init__(self, elements=()):
        self.elements = list(elements)

    def count(self):
        return len(self.elements)

    def nth(self, index):
        return self.elements[index]


class FakeContext:
    def __init__(self):
        self.pages = []


class FakePage:
    def __init__(self, selector_map=None):
        self.url = "https://careers.example.test/application"
        self.context = FakeContext()
        self.context.pages.append(self)
        self.selector_map = selector_map or {}

    def title(self):
        return "Example Application"

    def is_closed(self):
        return False

    def locator(self, selector):
        return FakeLocator(self.selector_map.get(selector, ()))

    def wait_for_load_state(self, *args, **kwargs):
        return None

    def wait_for_timeout(self, *_args, **_kwargs):
        return None


class RuntimeDiagnosticTests(unittest.TestCase):
    def test_mocked_control_metadata_can_be_written_as_jsonl(self):
        control = FakeElement(
            tag="a",
            attributes={"href": "https://example.test/apply", "class": "apply"},
            text="Apply now",
        )
        record = {"event": "control", "control": element_diagnostic(control)}

        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "diagnostics.jsonl")
            self.assertTrue(write_diagnostic(record, path=path))
            with open(path, encoding="utf-8") as source:
                saved = json.loads(source.readline())

        self.assertEqual(saved["control"]["tag"], "a")
        self.assertEqual(saved["control"]["text_preview"], "Apply now")

    def test_missing_optional_control_attributes_do_not_crash(self):
        control = FakeElement(tag="button", text="Apply")
        info = element_diagnostic(control)

        self.assertEqual(info["tag"], "button")
        self.assertEqual(info["href"], "")
        self.assertEqual(info["aria_label"], "")
        self.assertEqual(info["title"], "")
        self.assertEqual(info["class"], "")

    def test_modal_selector_match_and_visible_counts_are_recorded(self):
        page = FakePage({
            ".jobs-easy-apply-modal": [
                FakeElement("div", {"class": "jobs-easy-apply-modal"}, "Contact info"),
                FakeElement("div", {"class": "jobs-easy-apply-modal"}, visible=False),
            ],
            "[role='dialog']": [
                FakeElement("div", {"role": "dialog", "aria-modal": "true"}, "Resume")
            ],
        })

        results = selector_diagnostics(
            page,
            (".jobs-easy-apply-modal", "[role='dialog']"),
        )

        self.assertEqual(results[0]["match_count"], 2)
        self.assertEqual(results[0]["visible_match_count"], 1)
        self.assertEqual(results[0]["candidates"][0]["class"], "jobs-easy-apply-modal")
        self.assertEqual(results[1]["candidates"][0]["aria_modal"], "true")

    def test_visible_overlay_information_is_recordable(self):
        alert = FakeElement(
            "div",
            {"id": "notice", "class": "system-alert", "role": "alert"},
            "Please review this notice",
        )
        page = FakePage({'[role="alert"]': [alert]})
        overlay_info = overlay_diagnostics(page)

        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "diagnostics.jsonl")
            self.assertTrue(write_diagnostic({"visible_overlays": overlay_info}, path=path))
            with open(path, encoding="utf-8") as source:
                saved = json.loads(source.readline())

        candidates = saved["visible_overlays"]["visible_candidates"]
        self.assertTrue(any(candidate["role"] == "alert" for candidate in candidates))
        self.assertTrue(any("review this notice" in candidate["text_preview"] for candidate in candidates))

    def test_click_exception_is_logged_without_changing_application_status(self):
        control = FakeElement(
            "button",
            {"aria-label": "Apply now", "id": "apply-control"},
            "Apply now",
            click_error=TimeoutError("control blocked"),
        )
        overlay = FakeElement(
            "div",
            {"id": "system-alert", "class": "alert", "role": "alert"},
            "Action could not be completed",
        )
        page = FakePage({
            "button, [role='button'], a, [role='link'], input[type='submit'], input[type='button']": [control],
            '[role="alert"]': [overlay],
        })
        diagnostics = []

        with (
            patch.object(external_app, "write_diagnostic", side_effect=diagnostics.append),
            patch.object(external_app, "_looks_like_application_form", return_value=False),
            patch.object(external_app, "_text", return_value="Company careers"),
            patch.object(external_app, "detect_ats", return_value="UNKNOWN"),
            patch.object(external_app, "_external_page_has_error", return_value=False),
            patch.object(external_app, "_wait_for_manual_consent", return_value=True),
            patch.object(external_app, "_wait_for_external_application", return_value=page),
        ):
            result = external_app.prepare_external_application_page(page)

        self.assertEqual(result, "FORM_NOT_FOUND")
        failed_click = next(
            event for event in diagnostics
            if event.get("event") == "external_application_control_click"
        )
        self.assertEqual(failed_click["click_result"], "exception")
        self.assertEqual(failed_click["exception_type"], "TimeoutError")
        self.assertEqual(failed_click["candidate"]["id"], "apply-control")
        self.assertTrue(failed_click["visible_overlays"]["visible_candidates"])


if __name__ == "__main__":
    unittest.main()
