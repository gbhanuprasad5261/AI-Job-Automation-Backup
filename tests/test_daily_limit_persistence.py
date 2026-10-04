import csv
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import config
import easy_apply


class FixedDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 10, 4)


class DailyLimitPersistenceTests(unittest.TestCase):
    TODAY = "2026-10-04"
    JOB = {
        "Title": "Test Engineer",
        "Company": "Example Corp",
        "Location": "Bengaluru",
        "Link": "https://www.linkedin.com/jobs/view/1234567890/",
    }
    HISTORY_FIELDS = ["Title", "Company", "Location", "URL", "Status", "Applied Date"]
    TRACKER_FIELDS = [
        "Title", "Company", "Location", "Application Status", "Applied Date", "Link", "Status"
    ]

    def setUp(self):
        datetime_patch = patch.object(easy_apply, "datetime", FixedDateTime)
        datetime_patch.start()
        self.addCleanup(datetime_patch.stop)
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        root = Path(self.temp_dir.name)
        self.history_path = root / "history.csv"
        self.tracker_path = root / "tracker.csv"
        self._write(self.history_path, self.HISTORY_FIELDS, [])
        self._write(self.tracker_path, self.TRACKER_FIELDS, [])

    @staticmethod
    def _write(path, fields, rows):
        with open(path, "w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

    def _history_row(self, job, status="APPLIED", applied_date=None):
        return {
            "Title": job["Title"],
            "Company": job["Company"],
            "Location": job["Location"],
            "URL": job["Link"],
            "Status": status,
            "Applied Date": applied_date or self.TODAY,
        }

    def _tracker_row(self, job, status="APPLIED", applied_date=None):
        return {
            "Title": job["Title"],
            "Company": job["Company"],
            "Location": job["Location"],
            "Application Status": status,
            "Status": status,
            "Applied Date": applied_date or self.TODAY,
            "Link": job["Link"],
        }

    def _with_store_paths(self):
        return (
            patch.object(easy_apply, "APPLICATION_HISTORY_FILE", str(self.history_path)),
            patch.object(easy_apply, "TRACKER_FILE", str(self.tracker_path)),
        )

    def _count(self):
        history_patch, tracker_patch = self._with_store_paths()
        with history_patch, tracker_patch:
            return easy_apply.get_today_applied_count()

    def test_history_only_confirmed_application_counts(self):
        self._write(self.history_path, self.HISTORY_FIELDS, [self._history_row(self.JOB)])
        self.assertEqual(self._count(), 1)

    def test_tracker_only_confirmed_application_counts(self):
        self._write(self.tracker_path, self.TRACKER_FIELDS, [self._tracker_row(self.JOB)])
        self.assertEqual(self._count(), 1)

    def test_same_application_in_both_sources_counts_once(self):
        history_job = dict(self.JOB, Link=self.JOB["Link"] + "?tracking=1")
        self._write(self.history_path, self.HISTORY_FIELDS, [self._history_row(history_job)])
        self._write(self.tracker_path, self.TRACKER_FIELDS, [self._tracker_row(self.JOB)])
        self.assertEqual(self._count(), 1)

    def test_two_different_confirmed_applications_count_twice(self):
        other = dict(self.JOB, Title="Platform Engineer", Link="https://www.linkedin.com/jobs/view/9876543210/")
        self._write(self.history_path, self.HISTORY_FIELDS, [self._history_row(self.JOB)])
        self._write(self.tracker_path, self.TRACKER_FIELDS, [self._tracker_row(other)])
        self.assertEqual(self._count(), 2)

    def test_duplicate_rows_with_same_identity_count_once(self):
        self._write(
            self.history_path,
            self.HISTORY_FIELDS,
            [self._history_row(self.JOB), self._history_row(self.JOB)],
        )
        self.assertEqual(self._count(), 1)

    def test_nonconfirmed_statuses_do_not_count(self):
        statuses = (
            "READY_FOR_REVIEW",
            "FAILED",
            "FORM_NOT_FOUND",
            "INELIGIBLE",
            "CLOSED",
            "LOGIN_REQUIRED",
        )
        history_rows = []
        tracker_rows = []
        for index, status in enumerate(statuses):
            job = dict(
                self.JOB,
                Title=f"Role {index}",
                Link=f"https://www.linkedin.com/jobs/view/{2000 + index}/",
            )
            history_rows.append(self._history_row(job, status=status))
            tracker_rows.append(self._tracker_row(job, status=status))
        self._write(self.history_path, self.HISTORY_FIELDS, history_rows)
        self._write(self.tracker_path, self.TRACKER_FIELDS, tracker_rows)
        self.assertEqual(self._count(), 0)

    def test_unconfirmed_submitted_is_rejected_and_confirmed_submitted_normalizes(self):
        tracker_row = self._tracker_row(self.JOB, status="NOT APPLIED", applied_date="")
        self._write(self.tracker_path, self.TRACKER_FIELDS, [tracker_row])
        self._write(
            self.history_path,
            self.HISTORY_FIELDS,
            [self._history_row(self.JOB, status="SUBMITTED")],
        )
        history_patch, tracker_patch = self._with_store_paths()
        with history_patch, tracker_patch:
            self.assertFalse(easy_apply.record_application_status(self.JOB, "SUBMITTED"))
            self.assertEqual(easy_apply.get_today_applied_count(), 0)
            self.assertTrue(
                easy_apply.record_application_status(
                    self.JOB,
                    "SUBMITTED",
                    submission_confirmed=True,
                )
            )
            self.assertEqual(easy_apply.get_today_applied_count(), 1)

    def test_tracker_write_failure_does_not_prevent_history_write(self):
        with (
            self._with_store_paths()[0],
            self._with_store_paths()[1],
            patch.object(easy_apply, "_write_tracker_application_status", side_effect=OSError("tracker denied")),
        ):
            self.assertTrue(
                easy_apply.record_application_status(
                    self.JOB,
                    "APPLIED",
                    submission_confirmed=True,
                )
            )
            self.assertEqual(easy_apply.get_today_applied_count(), 1)

    def test_history_write_failure_does_not_prevent_tracker_write(self):
        with (
            self._with_store_paths()[0],
            self._with_store_paths()[1],
            patch.object(easy_apply, "_record_application_history", return_value=False),
        ):
            self.assertTrue(
                easy_apply.record_application_status(
                    self.JOB,
                    "APPLIED",
                    submission_confirmed=True,
                )
            )
            self.assertEqual(self._count(), 1)

    def test_read_failure_in_either_source_fails_closed(self):
        original_open = open
        history_patch, tracker_patch = self._with_store_paths()
        with history_patch, tracker_patch:
            for unreadable_path in (self.history_path, self.tracker_path):
                def read_with_one_denied(path, *args, **kwargs):
                    if Path(path) == unreadable_path:
                        raise PermissionError("read denied")
                    return original_open(path, *args, **kwargs)

                with self.subTest(path=unreadable_path):
                    with patch("builtins.open", side_effect=read_with_one_denied):
                        with self.assertRaises(easy_apply.DailyApplicationCountUnavailable):
                            easy_apply.get_today_applied_count()

    def test_malformed_tracker_source_fails_closed(self):
        self._write(self.tracker_path, ["Title", "Status"], [])
        with self._with_store_paths()[0], self._with_store_paths()[1]:
            with self.assertRaises(easy_apply.DailyApplicationCountUnavailable):
                easy_apply.get_today_applied_count()

    def test_malformed_history_source_fails_closed(self):
        self._write(self.history_path, ["Title", "Status"], [])
        with self._with_store_paths()[0], self._with_store_paths()[1]:
            with self.assertRaises(easy_apply.DailyApplicationCountUnavailable):
                easy_apply.get_today_applied_count()

    def test_confirmed_today_record_without_identity_fails_closed(self):
        row = self._history_row(self.JOB)
        row["URL"] = ""
        self._write(self.history_path, self.HISTORY_FIELDS, [row])
        with self.assertRaises(easy_apply.DailyApplicationCountUnavailable):
            self._count()

    def test_main_stops_before_application_if_count_is_unavailable(self):
        with (
            patch.object(easy_apply, "get_recommended_jobs", return_value=[self.JOB]),
            patch.object(
                easy_apply,
                "get_today_applied_count",
                side_effect=easy_apply.DailyApplicationCountUnavailable("bad CSV"),
            ),
            patch.object(easy_apply, "open_easy_apply") as open_job,
            redirect_stdout(io.StringIO()),
        ):
            easy_apply.main()
        open_job.assert_not_called()

    def test_daily_limit_uses_combined_persisted_count(self):
        self._write(self.tracker_path, self.TRACKER_FIELDS, [self._tracker_row(self.JOB)])
        with (
            self._with_store_paths()[0],
            self._with_store_paths()[1],
            patch.object(config, "DAILY_APPLICATION_LIMIT", 1),
            patch.object(easy_apply, "get_recommended_jobs", return_value=[self.JOB]),
            patch.object(easy_apply, "display_jobs"),
            patch.object(easy_apply, "open_easy_apply") as open_job,
            redirect_stdout(io.StringIO()),
        ):
            easy_apply.main()
        open_job.assert_not_called()

    def test_already_applied_live_detection_consumes_current_run_slot(self):
        class FakeLocator:
            def inner_text(self, **kwargs):
                return "Backend Developer job page"

        class FakePage:
            url = "https://www.linkedin.com/jobs/view/1234567890/"

            def title(self):
                return "Test Engineer | Example Corp | LinkedIn"

            def locator(self, selector):
                return FakeLocator()

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
        record = Mock(return_value=False)
        real_open_easy_apply = easy_apply.open_easy_apply
        open_spy = Mock(side_effect=lambda job: real_open_easy_apply(job))
        output = io.StringIO()

        with (
            patch.object(easy_apply, "sync_playwright", return_value=manager),
            patch.object(easy_apply, "get_application_status", return_value="NOT APPLIED"),
            patch.object(easy_apply, "navigate_page", return_value=True),
            patch.object(easy_apply, "is_job_closed", return_value=False),
            patch.object(easy_apply, "is_current_job_already_applied", return_value=True),
            patch.object(easy_apply, "record_application_status", record),
            patch.object(easy_apply, "get_recommended_jobs", return_value=[self.JOB]),
            patch.object(easy_apply, "get_today_applied_count", return_value=0),
            patch.object(config, "DAILY_APPLICATION_LIMIT", 1),
            patch.object(easy_apply, "display_jobs"),
            patch.object(easy_apply, "open_easy_apply", open_spy),
            redirect_stdout(output),
        ):
            easy_apply.main()

        open_spy.assert_called_once_with(self.JOB)
        record.assert_called_once_with(
            self.JOB,
            "APPLIED",
            submission_confirmed=True,
        )
        self.assertIn("Confirmed applications today: 1/1", output.getvalue())


if __name__ == "__main__":
    unittest.main()
