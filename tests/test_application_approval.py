import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import MagicMock, patch

import application_approval
import application_form
import config
import external_app
import external_apply


class ApprovalChallengeTests(unittest.TestCase):
    def _confirm_with(self, identity, response, nonce="fresh-nonce"):
        output = StringIO()
        with (
            patch.object(application_approval.secrets, "token_urlsafe", return_value=nonce),
            patch("builtins.input", return_value=response) as read_input,
            redirect_stdout(output),
        ):
            result = application_approval.confirm_application_submission(
                identity, "Synthetic role", "Example employer"
            )
        return result, output.getvalue(), read_input

    def test_exact_fresh_application_challenge_is_accepted_once(self):
        with patch.object(
            application_approval.secrets,
            "token_urlsafe",
            side_effect=("nonce-one", "nonce-two"),
        ), patch("builtins.input", side_effect=(
            "APPROVE job:alpha nonce-one",
            "APPROVE job:alpha nonce-one",
        )), redirect_stdout(StringIO()):
            first = application_approval.confirm_application_submission(
                "job:alpha", "Synthetic role", "Example employer"
            )
            replay = application_approval.confirm_application_submission(
                "job:alpha", "Synthetic role", "Example employer"
            )

        self.assertTrue(first)
        self.assertFalse(replay)

    def test_missing_rejected_and_malformed_approvals_fail_closed(self):
        for identity, response in (
            (None, "APPROVE job:alpha fresh-nonce"),
            ("   ", "APPROVE job:alpha fresh-nonce"),
            ("job:alpha", "no"),
            ("job:alpha", None),
        ):
            with self.subTest(identity=identity, response=response):
                result, _, read_input = self._confirm_with(identity, response)
                self.assertFalse(result)
                if not identity or not str(identity).strip():
                    read_input.assert_not_called()

    def test_approval_for_another_application_is_rejected(self):
        result, _, _ = self._confirm_with(
            "job:target", "APPROVE job:other fresh-nonce"
        )
        self.assertFalse(result)

    def test_expired_or_replayed_nonce_is_rejected(self):
        result, _, _ = self._confirm_with(
            "job:target", "APPROVE job:target expired-nonce", nonce="current-nonce"
        )
        self.assertFalse(result)

        with (
            patch.object(application_approval.secrets, "token_urlsafe", return_value="fresh-nonce"),
            patch.object(application_approval.time, "monotonic", side_effect=(10.0, 131.0)),
            patch("builtins.input", return_value="APPROVE job:target fresh-nonce"),
            redirect_stdout(StringIO()),
        ):
            expired = application_approval.confirm_application_submission("job:target")
        self.assertFalse(expired)

    def test_unavailable_or_interrupted_console_input_fails_closed(self):
        for error in (EOFError(), KeyboardInterrupt()):
            with self.subTest(error=type(error).__name__), patch.object(
                application_approval.secrets, "token_urlsafe", return_value="fresh-nonce"
            ), patch("builtins.input", side_effect=error), redirect_stdout(StringIO()):
                self.assertFalse(
                    application_approval.confirm_application_submission("job:target")
                )

    def test_prompt_preserves_useful_single_line_application_context(self):
        result, output, _ = self._confirm_with(
            "job:alpha", "APPROVE job:alpha fresh-nonce"
        )
        self.assertTrue(result)
        self.assertIn("Synthetic role at Example employer", output)
        self.assertIn("Application identity: job:alpha", output)
        self.assertIn(
            f"expires in {application_approval.APPROVAL_CHALLENGE_TTL_SECONDS} seconds",
            output,
        )


class FinalSubmitBoundaryTests(unittest.TestCase):
    IDENTITY = "linkedin-job:synthetic-123"

    def _linkedin(self, approved, auto_submit=True, unanswered=0, unknown=(0, 0)):
        submit = MagicMock()
        submit.is_visible.return_value = True
        submit.is_enabled.return_value = True
        page = MagicMock()
        container = object()
        with (
            patch.object(config, "DRY_RUN", False),
            patch.object(config, "AUTO_SUBMIT", auto_submit),
            patch.object(application_form, "verify_final_review_page", return_value=True),
            patch.object(application_form, "get_application_container", return_value=container),
            patch.object(application_form, "inspect_required_fields", return_value=unanswered),
            patch.object(application_form, "_unanswered_unknown_text_questions", return_value=unknown),
            patch.object(application_form, "find_submit_button", return_value=submit) as find_submit,
            patch.object(application_form, "_control_text", return_value="Submit application"),
            patch.object(application_form, "confirm_application_submission", return_value=approved) as approval,
            patch.object(application_form, "_final_submission_confirmed", return_value=True),
            redirect_stdout(StringIO()),
        ):
            result = application_form.handle_final_submission(
                page, self.IDENTITY, "Synthetic role", "Example employer"
            )
        return result, submit, approval, find_submit

    def _external_page(self):
        control = MagicMock()
        control.is_visible.return_value = True
        control.is_disabled.return_value = False
        page = MagicMock()
        page.url = "https://forms.example.test/synthetic"
        page.locator.return_value.count.return_value = 1
        page.locator.return_value.nth.return_value = control
        return page, control

    def test_linkedin_gate_blocks_without_approval_and_rechecks_required_questions(self):
        result, submit, approval, _ = self._linkedin(False)
        self.assertEqual(result, "READY_FOR_REVIEW")
        approval.assert_called_once_with(self.IDENTITY, "Synthetic role", "Example employer")
        submit.click.assert_not_called()

        result, submit, approval, find_submit = self._linkedin(
            True, unanswered=1, unknown=(0, 1)
        )
        self.assertEqual(result, "READY_FOR_REVIEW")
        approval.assert_not_called()
        find_submit.assert_not_called()
        submit.click.assert_not_called()

    def test_linkedin_approval_only_allows_exact_application_boundary(self):
        result, submit, approval, _ = self._linkedin(True)
        self.assertEqual(result, "SUBMITTED")
        approval.assert_called_once_with(self.IDENTITY, "Synthetic role", "Example employer")
        submit.click.assert_called_once_with(timeout=10000)

    def test_google_form_submit_boundary_requires_identity_and_approval(self):
        page, submit = self._external_page()
        with (
            patch.object(config, "DRY_RUN", False),
            patch.object(config, "AUTO_SUBMIT", True),
            patch.object(external_app, "UNKNOWN_QUESTIONS_POLICY", "SKIP"),
            patch.object(external_app, "_google_forms_required_empty_count", return_value=0),
            patch.object(external_app, "_normalized_control_label", return_value="submit"),
            patch.object(external_app, "confirm_application_submission", return_value=False) as approval,
            redirect_stdout(StringIO()),
        ):
            result = external_app._auto_submit_google_form(
                page, self.IDENTITY, "Synthetic role", "Example employer"
            )
        self.assertEqual(result, "READY_FOR_REVIEW")
        approval.assert_called_once_with(self.IDENTITY, "Synthetic role", "Example employer")
        submit.click.assert_not_called()

        with (
            patch.object(config, "AUTO_SUBMIT", True),
            patch.object(external_app, "UNKNOWN_QUESTIONS_POLICY", "SKIP"),
            patch.object(external_app, "_google_forms_required_empty_count", return_value=0),
            patch.object(external_app, "_normalized_control_label", return_value="submit"),
            patch.object(external_app, "confirm_application_submission", return_value=True),
            patch.object(external_app, "_text", return_value="Your response has been recorded"),
            redirect_stdout(StringIO()),
        ):
            result = external_app._auto_submit_google_form(
                page, self.IDENTITY, "Synthetic role", "Example employer"
            )
        self.assertEqual(result, "SUBMITTED")
        submit.click.assert_called_once_with()

    def test_external_ats_submit_boundary_requires_per_application_approval(self):
        page, submit = self._external_page()
        with (
            patch.object(config, "DRY_RUN", False),
            patch.object(config, "AUTO_SUBMIT", True),
            patch.object(external_app, "UNKNOWN_QUESTIONS_POLICY", "SKIP"),
            patch.object(external_app, "_required_empty_count", return_value=0),
            patch.object(external_app, "_find_final_submit_control", return_value=submit),
            patch.object(external_app, "confirm_application_submission", return_value=False) as approval,
            redirect_stdout(StringIO()),
        ):
            result = external_app._auto_submit_external_application(
                page, self.IDENTITY, "Synthetic role", "Example employer"
            )
        self.assertEqual(result, "READY_FOR_REVIEW")
        approval.assert_called_once_with(self.IDENTITY, "Synthetic role", "Example employer")
        submit.click.assert_not_called()

        with (
            patch.object(config, "AUTO_SUBMIT", True),
            patch.object(external_app, "UNKNOWN_QUESTIONS_POLICY", "SKIP"),
            patch.object(external_app, "_required_empty_count", return_value=0),
            patch.object(external_app, "_find_final_submit_control", return_value=submit),
            patch.object(external_app, "confirm_application_submission", return_value=True),
            patch.object(external_app, "_external_submission_verified", return_value=True),
            redirect_stdout(StringIO()),
        ):
            result = external_app._auto_submit_external_application(
                page, self.IDENTITY, "Synthetic role", "Example employer"
            )
        self.assertEqual(result, "SUBMITTED")
        submit.click.assert_called_once_with()

    def test_real_fresh_approval_is_consumed_at_the_final_submit_boundary(self):
        page, submit = self._external_page()
        with (
            patch.object(config, "DRY_RUN", False),
            patch.object(config, "AUTO_SUBMIT", True),
            patch.object(external_app, "UNKNOWN_QUESTIONS_POLICY", "SKIP"),
            patch.object(external_app, "_required_empty_count", return_value=0),
            patch.object(external_app, "_find_final_submit_control", return_value=submit),
            patch.object(external_app, "_external_submission_verified", return_value=True),
            patch.object(application_approval.secrets, "token_urlsafe", return_value="fresh-nonce"),
            patch("builtins.input", return_value=f"APPROVE {self.IDENTITY} fresh-nonce"),
            redirect_stdout(StringIO()),
        ):
            result = external_app._auto_submit_external_application(
                page, self.IDENTITY, "Synthetic role", "Example employer"
            )

        self.assertEqual(result, "SUBMITTED")
        submit.click.assert_called_once_with()

    def test_missing_identity_blocks_direct_final_submit_call(self):
        page, submit = self._external_page()
        with (
            patch.object(config, "DRY_RUN", False),
            patch.object(config, "AUTO_SUBMIT", True),
            patch.object(external_app, "UNKNOWN_QUESTIONS_POLICY", "SKIP"),
            patch.object(external_app, "_required_empty_count", return_value=0),
            patch.object(external_app, "_find_final_submit_control", return_value=submit),
            patch("builtins.input") as read_input,
            redirect_stdout(StringIO()),
        ):
            result = external_app._auto_submit_external_application(page)

        self.assertEqual(result, "READY_FOR_REVIEW")
        read_input.assert_not_called()
        submit.click.assert_not_called()

    def test_legacy_external_module_cannot_bypass_approval(self):
        page, submit = self._external_page()
        with (
            patch.object(config, "AUTO_SUBMIT", True),
            patch.object(external_apply, "UNKNOWN_QUESTIONS_POLICY", "SKIP"),
            patch.object(external_apply, "_required_empty_count", return_value=0),
            patch.object(external_apply, "_find_final_submit_control", return_value=submit),
            patch.object(external_apply, "confirm_application_submission", return_value=False) as approval,
            redirect_stdout(StringIO()),
        ):
            result = external_apply._auto_submit_external_application(
                page, self.IDENTITY, "Synthetic role", "Example employer"
            )
        self.assertEqual(result, "READY_FOR_REVIEW")
        approval.assert_called_once_with(self.IDENTITY, "Synthetic role", "Example employer")
        submit.click.assert_not_called()

        with (
            patch.object(config, "AUTO_SUBMIT", True),
            patch.object(external_apply, "UNKNOWN_QUESTIONS_POLICY", "SKIP"),
            patch.object(external_apply, "_required_empty_count", return_value=0),
            patch.object(external_apply, "_find_final_submit_control", return_value=submit),
            patch.object(external_apply, "confirm_application_submission", return_value=True),
            patch.object(external_apply, "_external_submission_verified", return_value=True),
            redirect_stdout(StringIO()),
        ):
            result = external_apply._auto_submit_external_application(
                page, self.IDENTITY, "Synthetic role", "Example employer"
            )
        self.assertEqual(result, "SUBMITTED")
        submit.click.assert_called_once_with()

        google_page, google_submit = self._external_page()
        with (
            patch.object(config, "AUTO_SUBMIT", True),
            patch.object(external_apply, "UNKNOWN_QUESTIONS_POLICY", "SKIP"),
            patch.object(external_apply, "_google_forms_required_empty_count", return_value=0),
            patch.object(external_apply, "_normalized_control_label", return_value="submit"),
            patch.object(external_apply, "confirm_application_submission", return_value=False),
            redirect_stdout(StringIO()),
        ):
            google_result = external_apply._auto_submit_google_form(
                google_page, self.IDENTITY, "Synthetic role", "Example employer"
            )
        self.assertEqual(google_result, "READY_FOR_REVIEW")
        google_submit.click.assert_not_called()

    def test_external_compatibility_wrappers_forward_application_identity(self):
        page = MagicMock()
        for module in (external_app, external_apply):
            with self.subTest(module=module.__name__), patch.object(
                module, "prepare_external_application_page", return_value="READY_FOR_REVIEW"
            ) as prepare:
                result = module.external_apply(
                    page=page,
                    application_identity=self.IDENTITY,
                    title="Synthetic role",
                    company="Example employer",
                )
            self.assertEqual(result, "READY_FOR_REVIEW")
            prepare.assert_called_once_with(
                page,
                "",
                "",
                "",
                "",
                application_identity=self.IDENTITY,
                title="Synthetic role",
                company="Example employer",
            )

    def test_legacy_external_module_obeys_dry_run_even_if_auto_submit_is_true(self):
        page = MagicMock()
        with (
            patch.object(config, "DRY_RUN", True),
            patch.object(config, "AUTO_SUBMIT", True),
            patch.object(external_apply, "confirm_application_submission") as approval,
            patch.object(external_apply, "_required_empty_count") as ats_required,
            patch.object(external_apply, "_google_forms_required_empty_count") as forms_required,
            patch.object(external_apply, "_text") as page_text,
            redirect_stdout(StringIO()),
        ):
            ats = external_apply._auto_submit_external_application(
                page, self.IDENTITY, "Synthetic role", "Example employer"
            )
            google = external_apply._auto_submit_google_form(
                page, self.IDENTITY, "Synthetic role", "Example employer"
            )
            prepared = external_apply.prepare_external_application_page(page)

        self.assertEqual(ats, "DRY_RUN_SKIPPED_BROWSER")
        self.assertEqual(google, "DRY_RUN_SKIPPED_BROWSER")
        self.assertEqual(prepared, "DRY_RUN_SKIPPED_BROWSER")
        approval.assert_not_called()
        ats_required.assert_not_called()
        forms_required.assert_not_called()
        page_text.assert_not_called()

    def test_auto_submit_false_skips_approval_prompt_on_all_final_paths(self):
        with (
            patch.object(config, "AUTO_SUBMIT", False),
            patch.object(application_form, "verify_final_review_page", return_value=True),
            patch.object(application_form, "confirm_application_submission") as linkedin_approval,
            patch.object(external_app, "confirm_application_submission") as external_approval,
            redirect_stdout(StringIO()),
        ):
            linkedin = application_form.handle_final_submission(MagicMock(), self.IDENTITY)
            google = external_app._auto_submit_google_form(MagicMock(), self.IDENTITY)
            ats = external_app._auto_submit_external_application(MagicMock(), self.IDENTITY)
        self.assertEqual(linkedin, "READY_FOR_REVIEW")
        self.assertEqual(google, "READY_FOR_REVIEW")
        self.assertEqual(ats, "READY_FOR_REVIEW")
        linkedin_approval.assert_not_called()
        external_approval.assert_not_called()


if __name__ == "__main__":
    unittest.main()
