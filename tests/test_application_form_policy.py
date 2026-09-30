import unittest
from unittest.mock import patch

import application_form


class FakeField:
    def __init__(self, attrs=None, value=""):
        self.attrs = attrs or {}
        self.value = value

    def is_visible(self):
        return True

    def get_attribute(self, name):
        return self.attrs.get(name)

    def input_value(self):
        return self.value

    def evaluate(self, script):
        if "tagName" in script:
            return "INPUT"
        if "validity.valid" in script:
            return True
        if "validationMessage" in script:
            return ""
        if "el.required" in script:
            return bool(
                self.attrs.get("required")
                or self.attrs.get("aria-required") == "true"
            )
        return False


class FakeLocator:
    def __init__(self, items):
        self.items = items

    def count(self):
        return len(self.items)

    def nth(self, index):
        return self.items[index]


class FakeContainer:
    def __init__(self, fields):
        self.fields = fields

    def locator(self, selector):
        return FakeLocator(self.fields)


class FakeOption:
    def __init__(self, label, value):
        self.label = label
        self.value = value

    def inner_text(self):
        return self.label

    def get_attribute(self, name):
        return self.value if name == "value" else None


class FakeSelect:
    def __init__(self, options):
        self.options = options
        self.selected = ""
        self.selection_calls = []

    def is_visible(self):
        return True

    def get_attribute(self, name):
        return {"name": "unknown-question", "id": "unknown-question"}.get(name)

    def locator(self, selector):
        return FakeLocator(self.options)

    def input_value(self):
        return self.selected

    def select_option(self, **kwargs):
        self.selection_calls.append(kwargs)
        self.selected = kwargs.get("value") or kwargs.get("label") or ""


class UnknownQuestionPolicyTests(unittest.TestCase):
    def test_skip_leaves_unknown_optional_text_question_unanswered(self):
        field = FakeField({"aria-label": "Preferred office location"})
        container = FakeContainer([field])

        with patch.object(application_form, "UNKNOWN_QUESTIONS_POLICY", "SKIP"):
            optional, required = application_form._unanswered_unknown_text_questions(
                container
            )
            action = application_form._unknown_question_policy_action(False)

        self.assertEqual([question.strip() for question in optional], ["preferred office location"])
        self.assertEqual(required, [])
        self.assertEqual(action, "SKIP")
        self.assertEqual(field.value, "")

    def test_skip_stops_unknown_text_question_marked_required_by_asterisk(self):
        field = FakeField({"aria-label": "MuleSoft experience *"})
        container = FakeContainer([field])
        page = type("Page", (), {"url": "https://www.linkedin.com/jobs/view/123"})()

        with (
            patch.object(application_form, "UNKNOWN_QUESTIONS_POLICY", "SKIP"),
            patch.object(application_form, "get_application_container", return_value=container),
            patch.object(application_form, "print_application_status"),
            patch.object(application_form, "fill_education_editor"),
            patch.object(application_form, "fill_name"),
            patch.object(application_form, "fill_email"),
            patch.object(application_form, "fill_phone"),
            patch.object(application_form, "upload_resume"),
            patch.object(application_form, "fill_common_text_fields"),
            patch.object(application_form, "inspect_radio_buttons", return_value=0),
            patch.object(application_form, "inspect_checkboxes"),
            patch.object(application_form, "inspect_selects"),
            patch.object(application_form, "inspect_required_fields", return_value=0),
        ):
            unresolved = application_form.prepare_current_page(page)

        self.assertGreater(unresolved, 0)
        self.assertEqual(field.value, "")

    def test_skip_does_not_bypass_unknown_required_aria_field(self):
        field = FakeField({
            "aria-label": "MuleSoft experience",
            "aria-required": "true",
        })
        container = FakeContainer([field])

        with patch.object(application_form, "UNKNOWN_QUESTIONS_POLICY", "SKIP"):
            action = application_form._unknown_question_policy_action(True)
            unanswered = application_form.inspect_required_fields(container)

        self.assertEqual(action, "STOP_REQUIRED")
        self.assertEqual(unanswered, 1)

    def test_native_required_field_remains_blocking(self):
        field = FakeField({"aria-label": "Unknown required field", "required": ""})
        unanswered = application_form.inspect_required_fields(FakeContainer([field]))
        self.assertEqual(unanswered, 1)

    def test_review_stops_for_unknown_optional_question(self):
        field = FakeField({"aria-label": "Preferred office location"})
        container = FakeContainer([field])
        page = type("Page", (), {"url": "https://www.linkedin.com/jobs/view/123"})()

        with (
            patch.object(application_form, "UNKNOWN_QUESTIONS_POLICY", "REVIEW"),
            patch.object(application_form, "get_application_container", return_value=container),
            patch.object(application_form, "print_application_status"),
            patch.object(application_form, "fill_education_editor"),
            patch.object(application_form, "fill_name"),
            patch.object(application_form, "fill_email"),
            patch.object(application_form, "fill_phone"),
            patch.object(application_form, "upload_resume"),
            patch.object(application_form, "fill_common_text_fields"),
            patch.object(application_form, "inspect_radio_buttons", return_value=0),
            patch.object(application_form, "inspect_checkboxes"),
            patch.object(application_form, "inspect_selects"),
            patch.object(application_form, "inspect_required_fields", return_value=0),
        ):
            unresolved = application_form.prepare_current_page(page)

        self.assertGreater(unresolved, 0)
        self.assertEqual(field.value, "")

    def test_known_supported_question_keeps_existing_mapping(self):
        self.assertIsNotNone(
            application_form._value_for_text_question(
                "How many years experience with Java?"
            )
        )

    def test_unknown_radio_question_has_no_arbitrary_answer(self):
        answer = application_form._choose_safe_radio_answer(
            "Which cloud platform do you prefer?", ["AWS", "Azure"]
        )
        self.assertIsNone(answer)

    def test_unknown_select_options_are_not_selected_arbitrarily(self):
        select = FakeSelect([
            FakeOption("Choose an option", ""),
            FakeOption("Option A", "a"),
            FakeOption("Option B", "b"),
        ])
        container = type(
            "SelectContainer",
            (),
            {"locator": lambda self, selector: FakeLocator([select])},
        )()

        application_form.inspect_selects(container)

        self.assertEqual(select.selection_calls, [])
        self.assertEqual(select.selected, "")

    def test_required_unknown_stops_before_submit_lookup(self):
        page = object()
        with (
            patch.object(application_form, "job_is_closed", return_value=False),
            patch.object(application_form, "prepare_current_page", return_value=1),
            patch.object(application_form, "find_submit_button") as find_submit,
        ):
            result = application_form.inspect_and_prepare_form(page)

        self.assertFalse(result)
        find_submit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
