import unittest
from contextlib import ExitStack, redirect_stdout
from io import StringIO
from unittest.mock import MagicMock, patch

import config
import external_app


class FakeLocator:
    def __init__(self, text=""):
        self.text = text

    def inner_text(self, *args, **kwargs):
        return self.text

    def count(self):
        return 0


class FakeFordApplicationPage:
    url = "https://apply.ford.com/en/sites/CX_1/job/71089/apply/email"

    def __init__(self):
        self.main_frame = object()
        self.frames = [self.main_frame]

    def locator(self, selector):
        if selector == "body":
            return FakeLocator(
                "Job application form. Authentication screen. "
                "Get started by using your email or phone number. "
                "Your profile will be created and kept up to date as you "
                "enter details for each of your job applications."
            )
        return FakeLocator()

    def wait_for_load_state(self, *args, **kwargs):
        return None

    def wait_for_timeout(self, *args, **kwargs):
        return None


class ExternalReviewModeMutationTests(unittest.TestCase):
    def _patch_mutation_helpers(self):
        return (
            patch.object(external_app, "_fill_known_application_fields"),
            patch.object(external_app, "_fill_known_fields"),
            patch.object(external_app, "_fill_known_profile_links"),
            patch.object(external_app, "_select_known_dropdowns"),
            patch.object(external_app, "_upload_resume"),
            patch.object(external_app, "_check_known_terms_consent"),
            patch.object(external_app, "_required_empty_count"),
            patch.object(external_app, "_auto_submit_external_application"),
        )

    def test_ford_authentication_form_review_mode_exits_before_any_field_mutation(self):
        page = FakeFordApplicationPage()
        self.assertTrue(external_app._looks_like_application_form(page))
        helpers = self._patch_mutation_helpers()

        with ExitStack() as stack, redirect_stdout(StringIO()):
            stack.enter_context(patch.object(config, "AUTO_SUBMIT", False))
            stack.enter_context(patch.object(external_app, "_external_page_has_error", return_value=False))
            stack.enter_context(patch.object(external_app, "_wait_for_manual_consent", return_value=True))
            stack.enter_context(patch.object(external_app, "_click_external_application_start", return_value=page))
            contexts = [stack.enter_context(helper) for helper in helpers]
            result = external_app.prepare_external_application_page(
                page,
                name="Candidate Name",
                email="candidate@example.test",
                phone="1234567890",
            )

        self.assertEqual(result, "READY_FOR_REVIEW")
        for helper in contexts:
            helper.assert_not_called()

    def test_generic_form_review_mode_skips_all_candidate_data_writers(self):
        page = FakeFordApplicationPage()
        helpers = self._patch_mutation_helpers()

        with ExitStack() as stack, redirect_stdout(StringIO()):
            stack.enter_context(patch.object(config, "AUTO_SUBMIT", False))
            stack.enter_context(patch.object(external_app, "detect_ats", return_value="UNKNOWN"))
            stack.enter_context(patch.object(external_app, "_text", return_value="Application form"))
            stack.enter_context(patch.object(external_app, "_external_page_has_error", return_value=False))
            stack.enter_context(patch.object(external_app, "_wait_for_manual_consent", return_value=True))
            stack.enter_context(patch.object(external_app, "_click_external_application_start", return_value=page))
            stack.enter_context(patch.object(external_app, "_looks_like_application_form", return_value=True))
            contexts = [stack.enter_context(helper) for helper in helpers]
            result = external_app.prepare_external_application_page(page)

        self.assertEqual(result, "READY_FOR_REVIEW")
        for helper in contexts:
            helper.assert_not_called()

    def test_google_forms_review_mode_skips_text_and_radio_answer_mutations(self):
        page = MagicMock()
        page.url = "https://docs.google.com/forms/d/example/viewform"

        with (
            patch.object(config, "AUTO_SUBMIT", False),
            patch.object(external_app, "_text", return_value="Google Form"),
            patch.object(external_app, "_external_page_has_error", return_value=False),
            patch.object(external_app, "_wait_for_manual_consent", return_value=True),
            patch.object(external_app, "_fill_google_forms_known_fields") as fields,
            patch.object(external_app, "_google_forms_confirmed_radio_answers") as radios,
            patch.object(external_app, "_upload_google_forms_resume") as upload,
            patch.object(external_app, "_google_forms_required_empty_count") as required,
            patch.object(external_app, "_auto_submit_google_form") as submit,
            redirect_stdout(StringIO()),
        ):
            result = external_app.prepare_external_application_page(page)

        self.assertEqual(result, "READY_FOR_REVIEW")
        fields.assert_not_called()
        radios.assert_not_called()
        upload.assert_not_called()
        required.assert_not_called()
        submit.assert_not_called()

    def test_auto_submit_true_generic_field_preparation_remains_available(self):
        page = FakeFordApplicationPage()
        special_fields = MagicMock(return_value=1)
        known_fields = MagicMock(return_value=1)
        profile_links = MagicMock(return_value=1)
        dropdowns = MagicMock(return_value=1)

        with (
            patch.object(config, "AUTO_SUBMIT", True),
            patch.object(external_app, "UNKNOWN_QUESTIONS_POLICY", "SKIP"),
            patch.object(external_app, "detect_ats", return_value="UNKNOWN"),
            patch.object(external_app, "_text", return_value="Application form"),
            patch.object(external_app, "_external_page_has_error", return_value=False),
            patch.object(external_app, "_wait_for_manual_consent", return_value=True),
            patch.object(external_app, "_click_external_application_start", return_value=page),
            patch.object(external_app, "_looks_like_application_form", return_value=True),
            patch.object(external_app, "_fill_known_application_fields", special_fields),
            patch.object(external_app, "_fill_known_fields", known_fields),
            patch.object(external_app, "_upload_resume", return_value=False),
            patch.object(external_app, "_fill_known_profile_links", profile_links),
            patch.object(external_app, "_select_known_dropdowns", dropdowns),
            patch.object(external_app, "_check_known_terms_consent", return_value=0),
            patch.object(external_app, "_required_empty_count", return_value=1),
            redirect_stdout(StringIO()),
        ):
            result = external_app.prepare_external_application_page(page)

        self.assertEqual(result, "READY_FOR_REVIEW")
        special_fields.assert_called_once()
        known_fields.assert_called_once()
        profile_links.assert_called_once()
        dropdowns.assert_called_once()

    def test_auto_submit_true_google_form_answer_preparation_remains_available(self):
        page = MagicMock()
        fields = MagicMock(return_value=2)
        radios = MagicMock(return_value=1)

        with (
            patch.object(config, "AUTO_SUBMIT", True),
            patch.object(external_app, "_fill_google_forms_known_fields", fields),
            patch.object(external_app, "_google_forms_confirmed_radio_answers", radios),
            patch.object(external_app, "_upload_google_forms_resume", return_value=False),
            patch.object(external_app, "_google_forms_required_empty_count", return_value=1),
            patch.object(external_app, "_auto_submit_google_form", return_value="READY_FOR_REVIEW"),
            redirect_stdout(StringIO()),
        ):
            result = external_app._prepare_google_form(
                page,
                "Candidate Name",
                "candidate@example.test",
                "1234567890",
                "Bengaluru",
                "Example Company",
            )

        self.assertEqual(result, "READY_FOR_REVIEW")
        fields.assert_called_once()
        radios.assert_called_once()


if __name__ == "__main__":
    unittest.main()
