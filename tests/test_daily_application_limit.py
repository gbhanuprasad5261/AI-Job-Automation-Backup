import contextlib
import io
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
        rows = [
            {"Status": "APPLIED", "Applied Date": today},
            {"Status": "SUBMITTED", "Applied Date": today},
            {"Status": "READY_FOR_REVIEW", "Applied Date": today},
            {"Status": "FORM_NOT_FOUND", "Applied Date": today},
            {"Status": "FAILED", "Applied Date": today},
            {"Status": "CLOSED", "Applied Date": today},
            {"Status": "INELIGIBLE", "Applied Date": today},
            {"Status": "APPLIED", "Applied Date": "2000-01-01"},
        ]

        with patch.object(easy_apply, "_load_application_history", return_value=rows):
            self.assertEqual(easy_apply.get_today_applied_count(), 1)


if __name__ == "__main__":
    unittest.main()
