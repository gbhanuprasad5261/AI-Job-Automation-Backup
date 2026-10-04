import csv
import hashlib
import tempfile
import unittest
from pathlib import Path
from contextlib import nullcontext
from unittest.mock import MagicMock, patch

import application_form
import config
import easy_apply
import external_app
import external_apply


class FakeElement:
    def is_visible(self):
        return True

    def inner_text(self):
        return "Application details"

    def get_attribute(self, name):
        return "jobs-easy-apply-modal" if name == "class" else None


class FakeLocator:
    def count(self):
        return 1

    def nth(self, index):
        return FakeElement()

    def inner_text(self):
        return "Backend Developer job application"


class FakePage:
    url = "https://www.linkedin.com/jobs/view/1234567890/"

    def locator(self, selector):
        return FakeLocator()

    def title(self):
        return "Backend Developer | Example Co | LinkedIn"

    def wait_for_timeout(self, milliseconds):
        return None


class FakeApplyButton:
    def scroll_into_view_if_needed(self):
        return None

    def click(self, **kwargs):
        return None


class SubmitGuardTests(unittest.TestCase):
    def test_linkedin_submit_guard_uses_canonical_false_config(self):
        with (
            patch.object(config, "AUTO_SUBMIT", False),
            patch.object(application_form, "AUTO_SUBMIT", True),
            patch.object(application_form, "verify_final_review_page", return_value=True),
            patch.object(application_form, "find_submit_button") as find_submit,
        ):
            result = application_form.handle_final_submission(object())

        self.assertEqual(result, "READY_FOR_REVIEW")
        find_submit.assert_not_called()

    def test_external_google_forms_submit_guard_uses_canonical_false_config(self):
        with (
            patch.object(config, "AUTO_SUBMIT", False),
            patch.object(external_app, "AUTO_SUBMIT", True),
            patch.object(external_app, "_google_forms_required_empty_count") as required,
        ):
            result = external_app._auto_submit_google_form(object())

        self.assertEqual(result, "READY_FOR_REVIEW")
        required.assert_not_called()

    def test_external_ats_submit_guard_uses_canonical_false_config(self):
        with (
            patch.object(config, "AUTO_SUBMIT", False),
            patch.object(external_app, "AUTO_SUBMIT", True),
            patch.object(external_app, "_required_empty_count") as required,
            patch.object(external_app, "_find_final_submit_control") as find_submit,
        ):
            result = external_app._auto_submit_external_application(object())

        self.assertEqual(result, "READY_FOR_REVIEW")
        required.assert_not_called()
        find_submit.assert_not_called()

    def test_review_policy_blocks_both_external_submit_routines(self):
        for module in (external_app, external_apply):
            with self.subTest(module=module.__name__):
                with (
                    patch.object(config, "AUTO_SUBMIT", False),
                    patch.object(module, "UNKNOWN_QUESTIONS_POLICY", "REVIEW"),
                    patch.object(module, "_required_empty_count") as ats_required,
                    patch.object(module, "_google_forms_required_empty_count") as forms_required,
                    patch.object(module, "_find_final_submit_control") as find_submit,
                ):
                    ats_result = module._auto_submit_external_application(object())
                    forms_result = module._auto_submit_google_form(object())

                self.assertEqual(ats_result, "READY_FOR_REVIEW")
                self.assertEqual(forms_result, "READY_FOR_REVIEW")
                ats_required.assert_not_called()
                forms_required.assert_not_called()
                find_submit.assert_not_called()

    def test_compatibility_external_module_submit_guard_uses_canonical_config(self):
        with (
            patch.object(config, "AUTO_SUBMIT", False),
            patch.object(external_apply, "AUTO_SUBMIT", True),
            patch.object(external_apply, "_required_empty_count") as required,
            patch.object(external_apply, "_find_final_submit_control") as find_submit,
        ):
            result = external_apply._auto_submit_external_application(object())

        self.assertEqual(result, "READY_FOR_REVIEW")
        required.assert_not_called()
        find_submit.assert_not_called()


class ApplicationRecordSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        root = Path(self.temp_dir.name)
        self.tracker_path = root / "application_tracker.csv"
        self.history_path = root / "application_history.csv"
        self.tracker_path.write_text(
            "Title,Company,Location,Match Score,Priority,Easy Apply,"
            "Application Status,Applied Date,Link,Status\n"
            "Sample Role,Example Co,Chennai,90%,HIGH,No,NOT APPLIED,,"
            "https://www.linkedin.com/jobs/view/1234567890/,NOT APPLIED\n",
            encoding="utf-8",
        )
        self.history_path.write_text(
            "Title,Company,Location,URL,Status,Applied Date\n",
            encoding="utf-8",
        )
        self.job = {
            "Title": "Sample Role",
            "Company": "Example Co",
            "Location": "Chennai",
            "Link": "https://www.linkedin.com/jobs/view/1234567890/",
        }
        self.tracker_patch = patch.object(
            easy_apply, "TRACKER_FILE", str(self.tracker_path)
        )
        self.history_patch = patch.object(
            easy_apply, "APPLICATION_HISTORY_FILE", str(self.history_path)
        )
        self.tracker_patch.start()
        self.history_patch.start()
        self.addCleanup(self.tracker_patch.stop)
        self.addCleanup(self.history_patch.stop)

    @staticmethod
    def _sha256(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def test_unconfirmed_applied_or_submitted_status_does_not_write(self):
        tracker_before = self._sha256(self.tracker_path)
        history_before = self._sha256(self.history_path)

        for status in ("APPLIED", "SUBMITTED"):
            with self.subTest(status=status):
                self.assertFalse(
                    easy_apply.record_application_status(self.job, status)
                )
                self.assertEqual(self._sha256(self.tracker_path), tracker_before)
                self.assertEqual(self._sha256(self.history_path), history_before)

    def test_pre_submit_ready_for_review_updates_no_history(self):
        history_before = self._sha256(self.history_path)

        self.assertTrue(
            easy_apply.record_application_status(self.job, "READY_FOR_REVIEW")
        )

        with self.tracker_path.open(encoding="utf-8", newline="") as f:
            tracker_row = next(csv.DictReader(f))
        self.assertEqual(tracker_row["Status"], "READY_FOR_REVIEW")
        self.assertEqual(tracker_row["Application Status"], "READY_FOR_REVIEW")
        self.assertEqual(self._sha256(self.history_path), history_before)

    def test_only_confirmed_submission_writes_applied_tracker_and_history(self):
        self.assertTrue(
            easy_apply.record_application_status(
                self.job,
                "SUBMITTED",
                submission_confirmed=True,
            )
        )

        with self.tracker_path.open(encoding="utf-8", newline="") as f:
            tracker_row = next(csv.DictReader(f))
        with self.history_path.open(encoding="utf-8", newline="") as f:
            history_row = next(csv.DictReader(f))

        self.assertEqual(tracker_row["Status"], "APPLIED")
        self.assertEqual(tracker_row["Application Status"], "APPLIED")
        self.assertEqual(history_row["Status"], "APPLIED")

    def test_history_writer_rejects_unconfirmed_applied_status(self):
        history_before = self._sha256(self.history_path)

        self.assertFalse(easy_apply._record_application_history(self.job, "APPLIED"))

        self.assertEqual(self._sha256(self.history_path), history_before)


class OpenFormPersistenceTests(unittest.TestCase):
    def _run_open_form(
        self,
        application_result,
        detection_result=None,
        record_status_result=True,
        record_status_override=None,
    ):
        page = FakePage()
        context = MagicMock()
        context.pages = [page]
        browser = MagicMock()
        browser.contexts = [context]
        playwright = MagicMock()
        playwright.chromium.connect_over_cdp.return_value = browser
        manager = MagicMock()
        manager.__enter__.return_value = playwright
        manager.__exit__.return_value = False
        record_status = record_status_override or MagicMock(
            return_value=record_status_result
        )
        prepare_form = MagicMock(return_value=application_result)
        diagnostic_writer = MagicMock()
        detector_patch = (
            patch.object(
                easy_apply,
                "_detect_easy_apply_container",
                return_value=detection_result,
            )
            if detection_result is not None
            else nullcontext()
        )
        job = {
            "Title": "Backend Developer",
            "Company": "Example Co",
            "Location": "Chennai",
            "Match Score": "90%",
            "Link": page.url,
        }

        with (
            patch.object(easy_apply, "sync_playwright", return_value=manager),
            patch.object(easy_apply, "get_application_status", return_value="NOT APPLIED"),
            patch.object(easy_apply, "convert_to_job_url", side_effect=lambda url: url),
            patch.object(easy_apply, "navigate_page", return_value=True),
            patch.object(easy_apply, "is_job_closed", return_value=False),
            patch.object(easy_apply, "is_current_job_already_applied", return_value=False),
            patch.object(easy_apply, "check_external_eligibility", return_value="UNKNOWN"),
            patch.object(easy_apply, "find_easy_apply_button", return_value=FakeApplyButton()),
            detector_patch,
            patch.object(easy_apply, "inspect_and_prepare_form", prepare_form),
            patch.object(easy_apply, "record_application_status", record_status),
            patch.object(easy_apply, "save_diagnostic_screenshot"),
            patch.object(easy_apply, "write_diagnostic", diagnostic_writer),
        ):
            result = easy_apply.open_easy_apply(job)

        return result, record_status, job, prepare_form, diagnostic_writer

    def test_open_or_blocked_form_does_not_record_applied(self):
        for application_result in ("READY_FOR_REVIEW", "FAILED"):
            with self.subTest(application_result=application_result):
                _, record_status, job, _, _ = self._run_open_form(application_result)
                calls = record_status.call_args_list
                self.assertFalse(
                    any(call.args[1] in {"APPLIED", "SUBMITTED"} for call in calls)
                )
                if application_result == "READY_FOR_REVIEW":
                    record_status.assert_called_once_with(job, "READY_FOR_REVIEW")
                else:
                    record_status.assert_not_called()

    def test_visible_sdui_detection_reaches_existing_form_inspection(self):
        sdui_diagnostics = {
            "selector": easy_apply.EASY_APPLY_SDUI_SELECTOR,
            "match_count": 1,
            "visible_match_count": 1,
            "candidates": [{"class": "auygt0 auymt3", "text_preview": "Contact info"}],
        }
        detection_result = {
            "detected": True,
            "source": "sdui",
            "sdui_diagnostics": sdui_diagnostics,
        }

        _, _, _, prepare_form, diagnostic_writer = self._run_open_form(
            "FAILED",
            detection_result=detection_result,
        )

        prepare_form.assert_called_once()
        sdui_event = next(
            call.args[0]
            for call in diagnostic_writer.call_args_list
            if call.args[0].get("event") == "easy_apply_sdui_container_detected"
        )
        self.assertEqual(sdui_event["selector"], sdui_diagnostics["selector"])
        self.assertEqual(sdui_event["match_count"], 1)
        self.assertEqual(sdui_event["visible_match_count"], 1)
        self.assertEqual(sdui_event["candidates"][0]["class"], "auygt0 auymt3")

    def test_confirmed_submitted_result_is_the_applied_recording_path(self):
        result, record_status, job, _, _ = self._run_open_form("SUBMITTED")

        self.assertTrue(result)
        record_status.assert_called_once_with(
            job,
            "APPLIED",
            submission_confirmed=True,
        )

    def test_confirmed_linkedin_submission_counts_when_tracking_fails(self):
        result, record_status, job, _, _ = self._run_open_form(
            "SUBMITTED",
            record_status_result=False,
        )

        self.assertTrue(result)
        record_status.assert_called_once_with(
            job,
            "APPLIED",
            submission_confirmed=True,
        )

    def test_confirmed_submission_remains_countable_when_both_sinks_fail(self):
        record_status = MagicMock(side_effect=easy_apply.record_application_status)
        with (
            patch.object(
                easy_apply,
                "_write_tracker_application_status",
                side_effect=OSError("tracker write failed"),
            ),
            patch.object(easy_apply, "_record_application_history", return_value=False),
        ):
            result, _, job, _, _ = self._run_open_form(
                "SUBMITTED",
                record_status_override=record_status,
            )

        self.assertTrue(result)
        record_status.assert_called_once_with(
            job,
            "APPLIED",
            submission_confirmed=True,
        )

    def test_confirmed_external_submission_counts_when_tracking_fails(self):
        page = FakePage()
        context = MagicMock()
        context.pages = [page]
        browser = MagicMock()
        browser.contexts = [context]
        playwright = MagicMock()
        playwright.chromium.connect_over_cdp.return_value = browser
        manager = MagicMock()
        manager.__enter__.return_value = playwright
        manager.__exit__.return_value = False
        job = {
            "Title": "Backend Developer",
            "Company": "Example Co",
            "Location": "Chennai",
            "Match Score": "90%",
            "Link": page.url,
        }

        with (
            patch.object(easy_apply, "sync_playwright", return_value=manager),
            patch.object(easy_apply, "get_application_status", return_value="NOT APPLIED"),
            patch.object(easy_apply, "convert_to_job_url", side_effect=lambda url: url),
            patch.object(easy_apply, "navigate_page", return_value=True),
            patch.object(easy_apply, "is_job_closed", return_value=False),
            patch.object(easy_apply, "is_current_job_already_applied", return_value=False),
            patch.object(easy_apply, "check_external_eligibility", return_value="UNKNOWN"),
            patch.object(easy_apply, "find_easy_apply_button", return_value=None),
            patch.object(easy_apply, "find_external_apply_link", return_value="https://careers.example.test/apply"),
            patch.object(easy_apply, "prepare_external_application_page", return_value="SUBMITTED"),
            patch.object(easy_apply, "record_application_status", return_value=False) as record_status,
        ):
            result = easy_apply.open_easy_apply(job)

        self.assertTrue(result)
        record_status.assert_called_once_with(
            job,
            "APPLIED",
            submission_confirmed=True,
        )


if __name__ == "__main__":
    unittest.main()
