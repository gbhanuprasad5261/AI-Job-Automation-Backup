import contextlib
import csv
import io
import tempfile
import unittest
from datetime import datetime
from unittest.mock import Mock, patch

import config
import easy_apply


class DailyApplicationLimitTests(unittest.TestCase):
    @staticmethod
    def _jobs(count):
        return [
            {"Title": f"Backend Engineer {index}", "Match Score": "90%"}
            for index in range(count)
        ]

    def _run_main(self, limit, jobs, outcomes, already_applied=0):
        open_job = Mock(side_effect=outcomes)
        with (
            patch.object(config, "DAILY_APPLICATION_LIMIT", limit),
            patch.object(easy_apply, "get_recommended_jobs", return_value=jobs),
            patch.object(easy_apply, "get_today_applied_count", return_value=already_applied),
            patch.object(easy_apply, "display_jobs"),
            patch.object(easy_apply, "open_easy_apply", open_job),
            contextlib.redirect_stdout(io.StringIO()) as output,
        ):
            easy_apply.main()
        return open_job, output.getvalue()

    def test_default_daily_limit_remains_15(self):
        self.assertEqual(config.DAILY_APPLICATION_LIMIT, 15)

    def test_custom_configured_limit_controls_active_runner(self):
        open_job, output = self._run_main(
            2,
            self._jobs(4),
            [True, True, True, True],
        )

        self.assertEqual(open_job.call_count, 2)
        self.assertIn("2/2", output)

    def test_zero_limit_prevents_application_attempts(self):
        open_job, _ = self._run_main(0, self._jobs(2), [True, True])

        open_job.assert_not_called()

    def test_confirmed_application_consumes_daily_slot(self):
        open_job, output = self._run_main(1, self._jobs(2), [True, True])

        self.assertEqual(open_job.call_count, 1)
        self.assertIn("Confirmed applications today: 1/1", output)

    def test_non_submission_statuses_do_not_consume_daily_slots(self):
        # open_easy_apply returns False for these non-submission outcomes.
        # The final True models the next confirmed application.
        non_submission_statuses = (
            "READY_FOR_REVIEW",
            "FORM_NOT_FOUND",
            "FAILED",
            "CLOSED",
            "INELIGIBLE",
        )
        with self.subTest(statuses=non_submission_statuses):
            open_job, output = self._run_main(
                1,
                self._jobs(len(non_submission_statuses) + 1),
                [False] * len(non_submission_statuses) + [True],
            )

        self.assertEqual(open_job.call_count, len(non_submission_statuses) + 1)
        self.assertIn("Confirmed applications today: 1/1", output)

    def test_duplicate_does_not_consume_daily_slot(self):
        # The already-applied check returns False; a subsequent distinct job
        # can still consume the one allowed slot.
        open_job, output = self._run_main(1, self._jobs(2), [False, True])

        self.assertEqual(open_job.call_count, 2)
        self.assertIn("Confirmed applications today: 1/1", output)

    def test_only_confirmed_applied_history_counts_toward_daily_limit(self):
        today = datetime.now().strftime("%Y-%m-%d")
        statuses = (
            "APPLIED",
            "SUBMITTED",
            "READY_FOR_REVIEW",
            "FORM_NOT_FOUND",
            "FAILED",
            "CLOSED",
            "INELIGIBLE",
            "LOGIN_REQUIRED",
        )
        with tempfile.TemporaryDirectory() as directory:
            history_path = f"{directory}/history.csv"
            tracker_path = f"{directory}/tracker.csv"
            with open(history_path, "w", newline="", encoding="utf-8") as file:
                writer = csv.DictWriter(
                    file,
                    fieldnames=["Title", "Company", "URL", "Status", "Applied Date"],
                )
                writer.writeheader()
                for index, status in enumerate(statuses):
                    writer.writerow({
                        "Title": f"Role {index}",
                        "Company": "Example",
                        "URL": f"https://www.linkedin.com/jobs/view/{1000 + index}/",
                        "Status": status,
                        "Applied Date": today,
                    })
                writer.writerow({
                    "Title": "Old applied role",
                    "Company": "Example",
                    "URL": "https://www.linkedin.com/jobs/view/9999/",
                    "Status": "APPLIED",
                    "Applied Date": "2000-01-01",
                })
            with open(tracker_path, "w", newline="", encoding="utf-8") as file:
                writer = csv.DictWriter(
                    file,
                    fieldnames=["Title", "Company", "Link", "Status", "Applied Date"],
                )
                writer.writeheader()

            with (
                patch.object(easy_apply, "APPLICATION_HISTORY_FILE", history_path),
                patch.object(easy_apply, "TRACKER_FILE", tracker_path),
            ):
                self.assertEqual(easy_apply.get_today_applied_count(), 1)


if __name__ == "__main__":
    unittest.main()
