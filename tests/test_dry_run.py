import os
import tempfile
import unittest
from unittest.mock import Mock, patch

import application_form
import config
import easy_apply
import external_app
import runtime_diagnostics
from execution_policy import DRY_RUN_SKIPPED_BROWSER


JOB = {
    "Title": "Backend Engineer",
    "Company": "Example Co",
    "Link": "https://www.linkedin.com/jobs/view/123456/",
    "Match Score": 88,
    "Application Eligible": "Yes",
    "Experience Skip": "No",
    "Easy Apply": "Yes",
}


class DryRunExecutionPolicyTests(unittest.TestCase):
    def test_main_selects_from_saved_data_and_never_starts_browser_workflow(self):
        with patch.object(config, "DRY_RUN", True), patch.object(
            easy_apply, "get_recommended_jobs", return_value=[JOB]
        ), patch.object(easy_apply, "open_easy_apply") as open_job, patch.object(
            easy_apply, "sync_playwright"
        ) as playwright, patch.object(
            easy_apply, "inspect_and_prepare_form"
        ) as linkedin_prepare, patch.object(
            easy_apply, "prepare_external_application_page"
        ) as external_prepare:
            results = easy_apply.main()

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status"], DRY_RUN_SKIPPED_BROWSER)
        self.assertEqual(results[0]["route_hint"], "LinkedIn Easy Apply")
        self.assertFalse(results[0]["live_route_confirmed"])
        open_job.assert_not_called()
        playwright.assert_not_called()
        linkedin_prepare.assert_not_called()
        external_prepare.assert_not_called()

    def test_open_easy_apply_returns_candidate_report_before_cdp(self):
        with patch.object(config, "DRY_RUN", True), patch.object(
            easy_apply, "sync_playwright"
        ) as playwright:
            result = easy_apply.open_easy_apply(JOB)

        self.assertEqual(result["status"], DRY_RUN_SKIPPED_BROWSER)
        self.assertEqual(result["job_url"], JOB["Link"])
        playwright.assert_not_called()

    def test_linkedin_navigation_and_preparation_boundaries_are_blocked(self):
        page = Mock()
        with patch.object(config, "DRY_RUN", True), patch.object(
            application_form, "get_application_container"
        ) as get_container, patch.object(
            application_form, "job_is_closed"
        ) as job_closed:
            self.assertFalse(easy_apply.navigate_page(page, "https://example.test"))
            self.assertEqual(
                application_form.prepare_current_page(page), DRY_RUN_SKIPPED_BROWSER
            )
            self.assertEqual(
                application_form.inspect_and_prepare_form(page), DRY_RUN_SKIPPED_BROWSER
            )
            self.assertFalse(application_form.move_to_next_page(page))

        page.goto.assert_not_called()
        page.wait_for_load_state.assert_not_called()
        get_container.assert_not_called()
        job_closed.assert_not_called()

    def test_linkedin_final_submission_and_upload_are_blocked_even_if_auto_submit_true(self):
        with patch.object(config, "DRY_RUN", True), patch.object(
            config, "AUTO_SUBMIT", True
        ), patch.object(application_form, "verify_final_review_page") as verifier:
            self.assertEqual(
                application_form.handle_final_submission(Mock()), DRY_RUN_SKIPPED_BROWSER
            )
            self.assertFalse(application_form.upload_resume(Mock()))

        verifier.assert_not_called()

    def test_external_entry_points_stop_before_page_queries_or_controls(self):
        page = Mock()
        with patch.object(config, "DRY_RUN", True), patch.object(
            config, "AUTO_SUBMIT", True
        ), patch.object(external_app, "_text") as page_text, patch.object(
            external_app, "_looks_like_application_form"
        ) as detector, patch.object(
            external_app, "_wait_for_manual_consent"
        ) as consent, patch.object(
            external_app, "_fill_known_application_fields"
        ) as fill_fields, patch.object(
            external_app, "_fill_known_fields"
        ) as fill_known, patch.object(
            external_app, "_fill_known_profile_links"
        ) as fill_links, patch.object(
            external_app, "_select_known_dropdowns"
        ) as dropdowns, patch.object(
            external_app, "_fill_google_forms_known_fields"
        ) as google_fields, patch.object(
            external_app, "_google_forms_confirmed_radio_answers"
        ) as google_radios:
            result = external_app.prepare_external_application_page(page)
            self.assertIs(external_app._click_external_application_start(page), page)
            sf_result = external_app._prepare_successfactors_account(page)
            google_result = external_app._prepare_google_form(
                page, "name", "email", "phone", "location", "company"
            )
            submit_result = external_app._auto_submit_external_application(page)

        self.assertEqual(result, DRY_RUN_SKIPPED_BROWSER)
        self.assertEqual(sf_result, DRY_RUN_SKIPPED_BROWSER)
        self.assertEqual(google_result, DRY_RUN_SKIPPED_BROWSER)
        self.assertEqual(submit_result, DRY_RUN_SKIPPED_BROWSER)
        page_text.assert_not_called()
        detector.assert_not_called()
        consent.assert_not_called()
        fill_fields.assert_not_called()
        fill_known.assert_not_called()
        fill_links.assert_not_called()
        dropdowns.assert_not_called()
        google_fields.assert_not_called()
        google_radios.assert_not_called()
        page.locator.assert_not_called()
        page.goto.assert_not_called()

    def test_google_forms_submission_and_upload_are_blocked(self):
        page = Mock()
        with patch.object(config, "DRY_RUN", True), patch.object(
            config, "AUTO_SUBMIT", True
        ), patch.object(external_app, "_fill_google_forms_known_fields") as fill, patch.object(
            external_app, "_google_forms_confirmed_radio_answers"
        ) as radios:
            result = external_app._auto_submit_google_form(page)
            upload = external_app._upload_google_forms_resume(page, "resume.pdf")

        self.assertEqual(result, DRY_RUN_SKIPPED_BROWSER)
        self.assertFalse(upload)
        fill.assert_not_called()
        radios.assert_not_called()
        page.locator.assert_not_called()

    def test_external_resume_upload_is_blocked(self):
        page = Mock()
        with patch.object(config, "DRY_RUN", True), patch.object(
            config, "AUTO_SUBMIT", True
        ):
            self.assertFalse(external_app._upload_resume(page, "resume.pdf"))
        page.locator.assert_not_called()

    def test_tracker_and_history_writes_are_suppressed(self):
        job = dict(JOB)
        with tempfile.TemporaryDirectory() as directory, patch.object(
            config, "DRY_RUN", True
        ), patch.object(easy_apply, "TRACKER_FILE", os.path.join(directory, "tracker.csv")), patch.object(
            easy_apply,
            "APPLICATION_HISTORY_FILE",
            os.path.join(directory, "history.csv"),
        ):
            self.assertFalse(
                easy_apply.record_application_status(
                    job, "APPLIED", submission_confirmed=True
                )
            )
            self.assertFalse(
                easy_apply._record_application_history(
                    job, "APPLIED", submission_confirmed=True
                )
            )
            self.assertFalse(easy_apply._write_application_history([], ["Status"]))
            self.assertEqual(os.listdir(directory), [])

    def test_all_application_statuses_are_non_persistent_in_dry_run(self):
        with patch.object(config, "DRY_RUN", True), patch.object(
            easy_apply, "open"
        ) as open_file:
            for status in (
                "READY_FOR_REVIEW",
                "FAILED",
                "CLOSED",
                "FORM_NOT_FOUND",
                "INELIGIBLE",
                "APPLIED",
                "SUBMITTED",
            ):
                self.assertFalse(easy_apply.record_application_status(JOB, status))
        open_file.assert_not_called()

    def test_diagnostic_jsonl_and_screenshot_artifacts_are_suppressed(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(
            config, "DRY_RUN", True
        ):
            target = os.path.join(directory, "nested", "diagnostic.jsonl")
            self.assertFalse(runtime_diagnostics.write_diagnostic({"event": "test"}, target))
            page = Mock()
            self.assertFalse(easy_apply.save_diagnostic_screenshot(page))
            self.assertEqual(os.listdir(directory), [])
            page.screenshot.assert_not_called()

    def test_dry_run_false_preserves_existing_review_mode_policy(self):
        page = Mock()
        with patch.object(config, "DRY_RUN", False), patch.object(
            config, "AUTO_SUBMIT", False
        ), patch.object(external_app, "_text", return_value="form"), patch.object(
            external_app, "detect_ats", return_value="GOOGLE_FORMS"
        ), patch.object(external_app, "_wait_for_manual_consent", return_value=True), patch.object(
            external_app, "_external_page_has_error", return_value=False
        ), patch.object(
            external_app, "_prepare_google_form", return_value="READY_FOR_REVIEW"
        ) as prepare_google:
            result = external_app.prepare_external_application_page(page)

        self.assertEqual(result, "READY_FOR_REVIEW")
        prepare_google.assert_called_once()

    def test_dry_run_false_auto_submit_true_preserves_google_answer_preparation(self):
        page = Mock()
        with patch.object(config, "DRY_RUN", False), patch.object(
            config, "AUTO_SUBMIT", True
        ), patch.object(
            external_app, "_fill_google_forms_known_fields", return_value=3
        ) as fill_fields, patch.object(
            external_app, "_google_forms_confirmed_radio_answers", return_value=2
        ) as radio_answers, patch.object(
            external_app, "_upload_google_forms_resume", return_value=False
        ), patch.object(
            external_app, "_google_forms_required_empty_count", return_value=0
        ), patch.object(
            external_app, "_auto_submit_google_form", return_value="READY_FOR_REVIEW"
        ) as submit:
            result = external_app._prepare_google_form(
                page, "name", "email", "phone", "location", "company"
            )

        self.assertEqual(result, "READY_FOR_REVIEW")
        fill_fields.assert_called_once()
        radio_answers.assert_called_once_with(page)
        submit.assert_called_once_with(page)


if __name__ == "__main__":
    unittest.main()
