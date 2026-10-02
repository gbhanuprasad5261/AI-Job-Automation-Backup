import csv
import hashlib
import tempfile
import unittest
from contextlib import ExitStack, redirect_stdout
from datetime import datetime
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import application_tracker
import config
import dashboard
import easy_apply
import external_app


JOB = {
    "Title": "Backend Engineer",
    "Company": "Example Corp",
    "Location": "Bengaluru",
    "Match Score": "90%",
    "Priority": "HIGH",
    "Easy Apply": "No",
    "Application Eligible": "Yes",
    "Experience Skip": "No",
    "Data Status": "OK",
    "Link": "https://www.linkedin.com/jobs/view/1234567890/",
}


class FakePage:
    def __init__(self, url="https://careers.example.test/application"):
        self.url = url

    def title(self):
        return "Example application page"

    def locator(self, selector):
        return FakeLocator()

    def wait_for_load_state(self, *args, **kwargs):
        return None

    def wait_for_timeout(self, *args, **kwargs):
        return None


class FakeLocator:
    def inner_text(self, *args, **kwargs):
        return ""


class ExternalFormStatusTests(unittest.TestCase):
    def _prepare(self, *, recognized, required=0, ats="UNKNOWN", account_result=None):
        page = FakePage()
        patches = [
            patch.object(external_app, "detect_ats", return_value=ats),
            patch.object(external_app, "_text", return_value="Example careers page"),
            patch.object(external_app, "_external_page_has_error", return_value=False),
            patch.object(external_app, "_wait_for_manual_consent", return_value=True),
            patch.object(external_app, "_click_external_application_start", return_value=page),
            patch.object(external_app, "_looks_like_application_form", return_value=recognized),
            patch.object(external_app, "_fill_known_application_fields", return_value=0),
            patch.object(external_app, "_fill_known_fields", return_value=0),
            patch.object(external_app, "_upload_resume", return_value=False),
            patch.object(external_app, "_fill_known_profile_links", return_value=0),
            patch.object(external_app, "_select_known_dropdowns", return_value=0),
            patch.object(external_app, "_check_known_terms_consent", return_value=0),
            patch.object(external_app, "_required_empty_count", return_value=required),
            patch.object(external_app, "_prepare_successfactors_account", return_value=account_result),
            patch.object(external_app, "UNKNOWN_QUESTIONS_POLICY", "SKIP"),
            patch.object(config, "AUTO_SUBMIT", False),
        ]
        with ExitStack() as stack, redirect_stdout(StringIO()):
            for mocked in patches:
                stack.enter_context(mocked)
            return external_app.prepare_external_application_page(page)

    def test_unrecognized_external_page_returns_form_not_found(self):
        self.assertEqual(self._prepare(recognized=False), "FORM_NOT_FOUND")

    def test_recognized_form_with_required_fields_returns_ready_for_review(self):
        self.assertEqual(self._prepare(recognized=True, required=1), "READY_FOR_REVIEW")

    def test_recognized_form_with_auto_submit_disabled_returns_ready_for_review(self):
        self.assertEqual(self._prepare(recognized=True), "READY_FOR_REVIEW")

    def test_successfactors_login_required_is_preserved(self):
        self.assertEqual(
            self._prepare(
                recognized=False,
                ats="SUCCESSFACTORS",
                account_result="LOGIN_REQUIRED",
            ),
            "LOGIN_REQUIRED",
        )


class FormNotFoundPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        root = Path(self.temp_dir.name)
        self.tracker_path = root / "application_tracker.csv"
        self.history_path = root / "application_history.csv"
        self.tracker_path.write_text(
            "Title,Company,Location,Match Score,Priority,Easy Apply,"
            "Application Status,Applied Date,Link,Status\n"
            "Backend Engineer,Example Corp,Bengaluru,90%,HIGH,No,"
            "NOT APPLIED,,https://www.linkedin.com/jobs/view/1234567890/,NOT APPLIED\n",
            encoding="utf-8",
        )
        self.history_path.write_text(
            "Title,Company,Location,URL,Status,Applied Date\n",
            encoding="utf-8",
        )

    @staticmethod
    def _hash(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def test_easy_apply_records_form_not_found_without_history_write(self):
        page = FakePage(JOB["Link"])
        context = MagicMock()
        context.pages = [page]
        browser = MagicMock()
        browser.contexts = [context]
        playwright = MagicMock()
        playwright.chromium.connect_over_cdp.return_value = browser
        manager = MagicMock()
        manager.__enter__.return_value = playwright
        manager.__exit__.return_value = False
        history_before = self._hash(self.history_path)

        with (
            patch.object(easy_apply, "TRACKER_FILE", str(self.tracker_path)),
            patch.object(easy_apply, "APPLICATION_HISTORY_FILE", str(self.history_path)),
            patch.object(easy_apply, "sync_playwright", return_value=manager),
            patch.object(easy_apply, "get_application_status", return_value="NOT APPLIED"),
            patch.object(easy_apply, "navigate_page", return_value=True),
            patch.object(easy_apply, "is_job_closed", return_value=False),
            patch.object(easy_apply, "is_current_job_already_applied", return_value=False),
            patch.object(easy_apply, "check_external_eligibility", return_value="UNKNOWN"),
            patch.object(easy_apply, "find_easy_apply_button", return_value=None),
            patch.object(easy_apply, "find_external_apply_link", return_value="https://careers.example.test/apply"),
            patch.object(easy_apply, "prepare_external_application_page", return_value="FORM_NOT_FOUND"),
            redirect_stdout(StringIO()),
        ):
            self.assertFalse(easy_apply.open_easy_apply(JOB))

        with self.tracker_path.open(encoding="utf-8", newline="") as file:
            row = next(csv.DictReader(file))
        self.assertEqual(row["Status"], "FORM_NOT_FOUND")
        self.assertEqual(row["Application Status"], "FORM_NOT_FOUND")
        self.assertEqual(self._hash(self.history_path), history_before)

    def test_form_not_found_is_not_counted_as_an_application(self):
        today = datetime.now().strftime("%Y-%m-%d")
        with patch.object(
            easy_apply,
            "_load_application_history",
            return_value=[{"Status": "FORM_NOT_FOUND", "Applied Date": today}],
        ):
            self.assertEqual(easy_apply.get_today_applied_count(), 0)

        tracker_path = self.tracker_path
        contents = tracker_path.read_text(encoding="utf-8").replace(
            "NOT APPLIED,,https://",
            f"FORM_NOT_FOUND,{today},https://",
        ).replace(
            "/,NOT APPLIED\n",
            "/,FORM_NOT_FOUND\n",
        )
        tracker_path.write_text(contents, encoding="utf-8")
        with patch.object(application_tracker, "OUTPUT_FILE", str(tracker_path)):
            self.assertEqual(application_tracker.count_confirmed_today(), 0)

    def test_form_not_found_is_retryable_and_not_applied(self):
        tracker_row = {
            **JOB,
            "Status": "FORM_NOT_FOUND",
            "Application Status": "FORM_NOT_FOUND",
        }

        def fake_load_csv(path):
            if path == easy_apply.ANALYSIS_FILE:
                return [JOB.copy()]
            if path == easy_apply.TRACKER_FILE:
                return [tracker_row]
            return []

        with (
            patch.object(easy_apply, "load_csv", side_effect=fake_load_csv),
            patch.object(easy_apply, "_analysis_matches_details", return_value=True),
            patch.object(easy_apply, "_load_application_history", return_value=[]),
        ):
            self.assertEqual(easy_apply.get_application_status(JOB), "NOT APPLIED")
            self.assertEqual(easy_apply.get_recommended_jobs(), [JOB])


class FormNotFoundReportingTests(unittest.TestCase):
    def test_tracker_technical_status_summary_includes_form_not_found(self):
        self.assertIn("FORM_NOT_FOUND", application_tracker.TECHNICAL_STATUSES)
        output = StringIO()
        with redirect_stdout(output):
            application_tracker.show_summary([{"Status": "FORM_NOT_FOUND"}])
        self.assertIn("Form_Not_Found", output.getvalue())
        self.assertIn(": 1", output.getvalue())

    def test_dashboard_reports_form_not_found_without_counting_application(self):
        output = StringIO()
        with redirect_stdout(output):
            dashboard.show_dashboard([{"Application Status": "FORM_NOT_FOUND"}])
        report = output.getvalue()
        self.assertIn("Form Not Found", report)
        self.assertIn("Form Not Found      : 1", report)
        self.assertIn("Jobs with application activity : 0/1", report)
        self.assertIn("Application Rate                : 0%", report)


if __name__ == "__main__":
    unittest.main()
