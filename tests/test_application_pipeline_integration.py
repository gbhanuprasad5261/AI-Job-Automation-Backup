import csv
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import dashboard
import easy_apply


class TrackerDashboardIntegrationTests(unittest.TestCase):
    FIELDS = [
        "Title",
        "Company",
        "Location",
        "Link",
        "URL",
        "Status",
        "Application Status",
        "Priority",
        "Match Score",
    ]
    JOB = {
        "Title": "Synthetic Engineer",
        "Company": "Synthetic Employer",
        "Location": "Synthetic City",
        "Link": "https://jobs.example.invalid/synthetic-role",
        "URL": "https://jobs.example.invalid/synthetic-role",
        "Status": "NOT APPLIED",
        "Application Status": "NOT APPLIED",
        "Priority": "HIGH",
        "Match Score": "90%",
    }

    def _create_tracker(self, path):
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=self.FIELDS)
            writer.writeheader()
            writer.writerow(self.JOB)

    def test_persisted_status_reaches_dashboard_through_shared_csv(self):
        with tempfile.TemporaryDirectory(prefix="synthetic-tracker-dashboard-") as temp:
            tracker_path = Path(temp) / "application_tracker.csv"
            history_path = Path(temp) / "application_history.csv"
            self._create_tracker(tracker_path)

            with (
                patch.object(easy_apply, "TRACKER_FILE", str(tracker_path)),
                patch.object(easy_apply, "APPLICATION_HISTORY_FILE", str(history_path)),
                patch.object(dashboard, "TRACKER_FILE", str(tracker_path)),
                patch.object(
                    easy_apply.EXECUTION_POLICY,
                    "allows_persistence",
                    return_value=True,
                ),
                redirect_stdout(StringIO()),
            ):
                persisted = easy_apply.record_application_status(
                    self.JOB, "READY_FOR_REVIEW"
                )
                rows = dashboard.load_jobs()

            self.assertTrue(persisted)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["Status"], "READY_FOR_REVIEW")
            self.assertEqual(rows[0]["Application Status"], "READY_FOR_REVIEW")
            self.assertFalse(history_path.exists())

    def test_tracker_write_failure_returns_false_and_dashboard_keeps_prior_status(self):
        with tempfile.TemporaryDirectory(prefix="synthetic-tracker-failure-") as temp:
            tracker_path = Path(temp) / "application_tracker.csv"
            history_path = Path(temp) / "application_history.csv"
            self._create_tracker(tracker_path)
            original_bytes = tracker_path.read_bytes()

            with (
                patch.object(easy_apply, "TRACKER_FILE", str(tracker_path)),
                patch.object(easy_apply, "APPLICATION_HISTORY_FILE", str(history_path)),
                patch.object(dashboard, "TRACKER_FILE", str(tracker_path)),
                patch.object(
                    easy_apply.EXECUTION_POLICY,
                    "allows_persistence",
                    return_value=True,
                ),
                patch.object(
                    easy_apply,
                    "_atomic_write_csv",
                    side_effect=OSError("synthetic tracker write failure"),
                ),
                redirect_stdout(StringIO()),
            ):
                persisted = easy_apply.record_application_status(
                    self.JOB, "READY_FOR_REVIEW"
                )
                rows = dashboard.load_jobs()

            self.assertFalse(persisted)
            self.assertEqual(tracker_path.read_bytes(), original_bytes)
            self.assertEqual(rows[0]["Status"], "NOT APPLIED")
            self.assertEqual(rows[0]["Application Status"], "NOT APPLIED")
            self.assertFalse(history_path.exists())


if __name__ == "__main__":
    unittest.main()
