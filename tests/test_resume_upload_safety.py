import unittest
from contextlib import ExitStack
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import MagicMock, patch

import application_form
import config
import external_app


class FakeFileInput:
    def __init__(self, *, file_count=0, filename="resume.pdf"):
        self.file_count = file_count
        self.filename = filename
        self.set_input_files = MagicMock()

    def is_visible(self):
        return True

    def get_attribute(self, name):
        return {"type": "file", "required": "", "aria-label": "Resume"}.get(name)

    def evaluate(self, script):
        if "tagName" in script:
            return "INPUT"
        if "files.length" in script and "name" in script:
            return self.filename if self.file_count or self.set_input_files.called else ""
        if "files.length" in script and "size" in script:
            return 123 if self.file_count or self.set_input_files.called else 0
        if "files ?" in script:
            return self.file_count
        if "validity.valid" in script:
            return False
        return ""

    def input_value(self):
        return ""

    def inner_text(self):
        return "Resume"


class FakeLocator:
    def __init__(self, items):
        self.items = items

    def count(self):
        return len(self.items)

    def nth(self, index):
        return self.items[index]


class FakeContainer:
    def __init__(self, file_input):
        self.file_input = file_input
        self.locator = MagicMock(return_value=FakeLocator([file_input]))


class FakeFrame:
    def __init__(self, file_input):
        self.file_input = file_input

    def locator(self, selector):
        if selector == "input[type='file']":
            return FakeLocator([self.file_input])
        return FakeLocator([])


class FakeUploadPage:
    url = "https://careers.example.test/application"

    def __init__(self, file_input):
        self.frames = [FakeFrame(file_input)]

    def locator(self, selector):
        return FakeLocator([self.frames[0].file_input])


class UnexpectedPageAccess:
    @property
    def frames(self):
        raise AssertionError("Disabled upload must not inspect page frames")

    def locator(self, selector):
        raise AssertionError("Disabled upload must not inspect page controls")

    def expect_file_chooser(self, **kwargs):
        raise AssertionError("Disabled upload must not open a file chooser")


class ResumeUploadSafetyTests(unittest.TestCase):
    def test_linkedin_upload_is_skipped_when_auto_submit_is_false(self):
        container = FakeContainer(FakeFileInput())

        with patch.object(config, "AUTO_SUBMIT", False):
            uploaded = application_form.upload_resume(container)

        self.assertFalse(uploaded)
        container.locator.assert_not_called()

    def test_linkedin_upload_remains_available_when_auto_submit_is_true(self):
        file_input = FakeFileInput()
        container = FakeContainer(file_input)

        with (
            patch.object(config, "AUTO_SUBMIT", True),
            patch.object(application_form.os.path, "exists", return_value=True),
        ):
            uploaded = application_form.upload_resume(container)

        self.assertTrue(uploaded)
        file_input.set_input_files.assert_called_once_with(application_form.RESUME_PATH)

    def test_google_forms_upload_is_skipped_without_page_or_chooser_access(self):
        with patch.object(config, "AUTO_SUBMIT", False):
            uploaded = external_app._upload_google_forms_resume(
                UnexpectedPageAccess(), "resume.pdf"
            )

        self.assertFalse(uploaded)

    def test_google_forms_enabled_upload_keeps_direct_file_input_path(self):
        file_input = FakeFileInput()
        page = FakeUploadPage(file_input)

        with (
            patch.object(config, "AUTO_SUBMIT", True),
            patch.object(external_app, "_resolve_resume_path", return_value="/fake/resume.pdf"),
        ):
            uploaded = external_app._upload_google_forms_resume(page, "resume.pdf")

        self.assertTrue(uploaded)
        file_input.set_input_files.assert_called_once_with("/fake/resume.pdf")

    def test_generic_ats_upload_is_skipped_without_page_or_chooser_access(self):
        with patch.object(config, "AUTO_SUBMIT", False):
            uploaded = external_app._upload_resume(
                UnexpectedPageAccess(), "resume.pdf"
            )

        self.assertFalse(uploaded)

    def test_generic_ats_enabled_upload_keeps_direct_file_input_path(self):
        file_input = FakeFileInput()
        page = FakeUploadPage(file_input)

        with (
            patch.object(config, "AUTO_SUBMIT", True),
            patch.object(external_app, "_resolve_resume_path", return_value="/fake/resume.pdf"),
        ):
            uploaded = external_app._upload_resume(page, "resume.pdf")

        self.assertTrue(uploaded)
        file_input.set_input_files.assert_called_once_with("/fake/resume.pdf")

    def test_missing_required_resume_is_still_reported(self):
        file_input = FakeFileInput(file_count=0)
        container = FakeContainer(file_input)
        page = FakeUploadPage(file_input)

        linkedin_missing = application_form.inspect_required_fields(container)
        missing = external_app._required_empty_count(page)

        self.assertEqual(linkedin_missing, 1)
        self.assertEqual(missing, 1)

    def test_workflow_callers_skip_upload_helpers_when_auto_submit_is_false(self):
        container = FakeContainer(FakeFileInput())
        linkedin_page = type("LinkedInPage", (), {"url": "https://www.linkedin.com/jobs/view/123"})()

        with ExitStack() as stack:
            stack.enter_context(patch.object(config, "AUTO_SUBMIT", False))
            stack.enter_context(patch.object(application_form, "get_application_container", return_value=container))
            stack.enter_context(patch.object(application_form, "print_application_status"))
            stack.enter_context(patch.object(application_form, "fill_education_editor"))
            stack.enter_context(patch.object(application_form, "fill_name"))
            stack.enter_context(patch.object(application_form, "fill_email"))
            stack.enter_context(patch.object(application_form, "fill_phone"))
            linkedin_upload = stack.enter_context(patch.object(application_form, "upload_resume"))
            stack.enter_context(patch.object(application_form, "fill_common_text_fields"))
            stack.enter_context(patch.object(application_form, "inspect_radio_buttons", return_value=0))
            stack.enter_context(patch.object(application_form, "inspect_checkboxes"))
            stack.enter_context(patch.object(application_form, "inspect_selects"))
            stack.enter_context(patch.object(application_form, "inspect_required_fields", return_value=0))
            stack.enter_context(patch.object(application_form, "_unanswered_unknown_text_questions", return_value=([], [])))

            self.assertEqual(application_form.prepare_current_page(linkedin_page), 0)

        linkedin_upload.assert_not_called()

        google_page = MagicMock()
        google_output = StringIO()
        google_fields = MagicMock()
        google_radios = MagicMock()
        with (
            redirect_stdout(google_output),
            patch.object(config, "AUTO_SUBMIT", False),
            patch.object(external_app, "_fill_google_forms_known_fields", google_fields),
            patch.object(external_app, "_google_forms_confirmed_radio_answers", google_radios),
            patch.object(external_app, "_upload_google_forms_resume") as google_upload,
            patch.object(external_app, "_google_forms_required_empty_count", return_value=1),
            patch.object(external_app, "_auto_submit_google_form", return_value="READY_FOR_REVIEW"),
        ):
            self.assertEqual(
                external_app._prepare_google_form(
                    google_page, "Name", "email@example.test", "123", "City", "Company", "resume.pdf"
                ),
                "READY_FOR_REVIEW",
            )

        google_upload.assert_not_called()
        google_fields.assert_not_called()
        google_radios.assert_not_called()
        self.assertIn("manual review required", google_output.getvalue())

        ats_page = MagicMock()
        ats_page.url = "https://careers.example.test/application"
        ats_output = StringIO()
        ats_application_fields = MagicMock(return_value=0)
        ats_fields = MagicMock(return_value=0)
        ats_profile_links = MagicMock(return_value=0)
        ats_dropdowns = MagicMock(return_value=0)
        with (
            redirect_stdout(ats_output),
            patch.object(config, "AUTO_SUBMIT", False),
            patch.object(external_app, "detect_ats", return_value="UNKNOWN"),
            patch.object(external_app, "_text", return_value="Application form"),
            patch.object(external_app, "_external_page_has_error", return_value=False),
            patch.object(external_app, "_wait_for_manual_consent", return_value=True),
            patch.object(external_app, "_click_external_application_start", return_value=ats_page),
            patch.object(external_app, "_looks_like_application_form", return_value=True),
            patch.object(external_app, "_fill_known_application_fields", ats_application_fields),
            patch.object(external_app, "_fill_known_fields", ats_fields),
            patch.object(external_app, "_upload_resume") as ats_upload,
            patch.object(external_app, "_fill_known_profile_links", ats_profile_links),
            patch.object(external_app, "_select_known_dropdowns", ats_dropdowns),
            patch.object(external_app, "_check_known_terms_consent", return_value=0),
            patch.object(external_app, "_required_empty_count", return_value=1),
        ):
            self.assertEqual(
                external_app.prepare_external_application_page(ats_page),
                "READY_FOR_REVIEW",
            )

        ats_upload.assert_not_called()
        ats_application_fields.assert_not_called()
        ats_fields.assert_not_called()
        ats_profile_links.assert_not_called()
        ats_dropdowns.assert_not_called()
        self.assertIn("fields were not modified", ats_output.getvalue())

    def test_auto_submit_false_preserves_final_submit_safety_gates(self):
        with (
            patch.object(config, "AUTO_SUBMIT", False),
            patch.object(application_form, "verify_final_review_page", return_value=True),
            patch.object(application_form, "find_submit_button") as linkedin_submit,
        ):
            linkedin_result = application_form.handle_final_submission(object())

        self.assertEqual(linkedin_result, "READY_FOR_REVIEW")
        linkedin_submit.assert_not_called()

        with (
            patch.object(config, "AUTO_SUBMIT", False),
            patch.object(external_app, "_google_forms_required_empty_count") as google_required,
        ):
            google_result = external_app._auto_submit_google_form(object())

        self.assertEqual(google_result, "READY_FOR_REVIEW")
        google_required.assert_not_called()

        with (
            patch.object(config, "AUTO_SUBMIT", False),
            patch.object(external_app, "_required_empty_count") as ats_required,
            patch.object(external_app, "_find_final_submit_control") as ats_submit,
        ):
            ats_result = external_app._auto_submit_external_application(object())

        self.assertEqual(ats_result, "READY_FOR_REVIEW")
        ats_required.assert_not_called()
        ats_submit.assert_not_called()


if __name__ == "__main__":
    unittest.main()
