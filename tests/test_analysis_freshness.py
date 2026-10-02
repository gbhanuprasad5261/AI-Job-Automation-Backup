import unittest
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

import easy_apply


class AnalysisFreshnessTests(unittest.TestCase):
    JOB = {
        "Title": "Backend Engineer",
        "Company": "Example Corp",
        "Location": "Bengaluru",
        "Match Score": "80%",
        "Application Eligible": "Yes",
        "Experience Skip": "No",
        "Data Status": "OK",
        "Link": "https://www.linkedin.com/jobs/view/1234567890/",
    }

    def _select(self, *, exists=None, mtimes=None, jobs=None):
        exists = exists or {
            easy_apply.ANALYSIS_FILE: True,
            easy_apply.DETAILS_FILE: True,
        }
        mtimes = mtimes or {
            easy_apply.DETAILS_FILE: 100,
            easy_apply.ANALYSIS_FILE: 100,
        }

        def fake_load_csv(path):
            if path == easy_apply.ANALYSIS_FILE:
                return [self.JOB] if jobs is None else list(jobs)
            return []

        with (
            patch.object(easy_apply.os.path, "exists", side_effect=lambda p: exists.get(p, False)),
            patch.object(easy_apply.os.path, "getmtime", side_effect=lambda p: mtimes[p]),
            patch.object(easy_apply, "load_csv", side_effect=fake_load_csv),
            patch.object(easy_apply, "_load_application_history", return_value=[]),
        ):
            return easy_apply.get_recommended_jobs()

    def test_details_newer_than_analysis_blocks_selection(self):
        output = StringIO()
        with redirect_stdout(output):
            result = self._select(mtimes={easy_apply.DETAILS_FILE: 101, easy_apply.ANALYSIS_FILE: 100})
        self.assertEqual(result, [])
        self.assertIn("rerun job_analyzer.py", output.getvalue())

    def test_same_age_allows_normal_selection_at_comparison_boundary(self):
        self.assertEqual(
            self._select(mtimes={easy_apply.DETAILS_FILE: 100, easy_apply.ANALYSIS_FILE: 100}),
            [self.JOB],
        )

    def test_newer_analysis_allows_normal_selection(self):
        self.assertEqual(
            self._select(mtimes={easy_apply.DETAILS_FILE: 100, easy_apply.ANALYSIS_FILE: 101}),
            [self.JOB],
        )

    def test_missing_analysis_file_fails_closed_explicitly(self):
        output = StringIO()
        with redirect_stdout(output):
            result = self._select(exists={easy_apply.ANALYSIS_FILE: False, easy_apply.DETAILS_FILE: True})
        self.assertEqual(result, [])
        self.assertIn("Analysis file not found", output.getvalue())

    def test_missing_details_file_fails_closed_explicitly(self):
        output = StringIO()
        with redirect_stdout(output):
            result = self._select(exists={easy_apply.ANALYSIS_FILE: True, easy_apply.DETAILS_FILE: False})
        self.assertEqual(result, [])
        self.assertIn("cannot verify analysis freshness", output.getvalue())

    def test_existing_eligibility_filters_remain_unchanged(self):
        rejected_jobs = [
            {**self.JOB, "Match Score": "69%"},
            {**self.JOB, "Location": "Toronto"},
            {**self.JOB, "Application Eligible": "No"},
            {**self.JOB, "Experience Skip": "Yes"},
            {**self.JOB, "Data Status": "MISSING"},
        ]
        self.assertEqual(self._select(jobs=rejected_jobs), [])
        self.assertEqual(self._select(), [self.JOB])


if __name__ == "__main__":
    unittest.main()
