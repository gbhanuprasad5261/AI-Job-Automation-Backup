import csv
import os
import tempfile
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
    JOBS_ROWS = [
        {"Title": "Backend Engineer", "Link": JOB["Link"]},
        {"Title": "Platform Engineer", "Link": "https://www.linkedin.com/jobs/view/9876543210/"},
    ]

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.paths = {
            "jobs": os.path.join(self.temp_dir.name, "jobs.csv"),
            "details": os.path.join(self.temp_dir.name, "job_details.csv"),
            "analysis": os.path.join(self.temp_dir.name, "job_analysis.csv"),
        }
        self.rows = {
            "jobs": list(self.JOBS_ROWS),
            "details": list(reversed(self.JOBS_ROWS)),
            "analysis": [
                {"Title": row["Title"], "Link": row["Link"]}
                for row in self.JOBS_ROWS
            ],
        }
        self._write_all()

    def _write_csv(self, path, rows, fieldnames=None):
        if fieldnames is None:
            fieldnames = list(rows[0]) if rows else ["Link"]
        with open(path, "w", newline="", encoding="utf-8") as file_obj:
            writer = csv.DictWriter(
                file_obj,
                fieldnames=fieldnames,
                extrasaction="ignore",
            )
            writer.writeheader()
            writer.writerows(rows)

    def _write_all(self):
        for stage, path in self.paths.items():
            self._write_csv(path, self.rows[stage])

    def _select(
        self,
        *,
        mtimes=None,
        missing=(),
        analysis_jobs=None,
        rows=None,
        headers=None,
        getmtime_side_effect=None,
    ):
        if rows:
            self.rows.update(rows)
        self._write_all()
        if headers:
            for stage, fieldnames in headers.items():
                self._write_csv(self.paths[stage], self.rows[stage], fieldnames)

        mtimes = mtimes or {"jobs": 100, "details": 100, "analysis": 100}
        path_by_stage = self.paths
        mtime_by_path = {path_by_stage[stage]: value for stage, value in mtimes.items()}
        missing_paths = {path_by_stage[stage] for stage in missing}

        def load_csv(path):
            if path == path_by_stage["analysis"]:
                return [self.JOB] if analysis_jobs is None else list(analysis_jobs)
            return []

        def fake_getmtime(path):
            if getmtime_side_effect is not None:
                return getmtime_side_effect(path)
            return mtime_by_path[path]

        with (
            patch.object(easy_apply, "JOBS_FILE", path_by_stage["jobs"]),
            patch.object(easy_apply, "DETAILS_FILE", path_by_stage["details"]),
            patch.object(easy_apply, "ANALYSIS_FILE", path_by_stage["analysis"]),
            patch.object(
                easy_apply.os.path,
                "exists",
                side_effect=lambda path: path not in missing_paths and os.path.isfile(path),
            ),
            patch.object(easy_apply.os.path, "getmtime", side_effect=fake_getmtime),
            patch.object(easy_apply, "load_csv", side_effect=load_csv),
            patch.object(easy_apply, "get_application_status", return_value="NOT APPLIED"),
        ):
            return easy_apply.get_recommended_jobs()

    def test_jobs_newer_than_details_blocks_selection(self):
        output = StringIO()
        with redirect_stdout(output):
            result = self._select(mtimes={"jobs": 101, "details": 100, "analysis": 100})
        self.assertEqual(result, [])
        self.assertIn("rerun job_details.py", output.getvalue())

    def test_jobs_and_details_equal_timestamp_allows_boundary(self):
        self.assertEqual(
            self._select(mtimes={"jobs": 100, "details": 100, "analysis": 100}),
            [self.JOB],
        )

    def test_jobs_older_than_details_allows_consistent_selection(self):
        self.assertEqual(
            self._select(mtimes={"jobs": 99, "details": 100, "analysis": 101}),
            [self.JOB],
        )

    def test_analysis_same_age_or_newer_preserves_selection(self):
        self.assertEqual(
            self._select(mtimes={"jobs": 100, "details": 100, "analysis": 100}),
            [self.JOB],
        )
        self.assertEqual(
            self._select(mtimes={"jobs": 100, "details": 101, "analysis": 102}),
            [self.JOB],
        )

    def test_details_newer_than_analysis_still_blocks_selection(self):
        output = StringIO()
        with redirect_stdout(output):
            result = self._select(mtimes={"jobs": 100, "details": 101, "analysis": 100})
        self.assertEqual(result, [])
        self.assertIn("rerun job_analyzer.py", output.getvalue())

    def test_missing_jobs_file_fails_closed_explicitly(self):
        output = StringIO()
        with redirect_stdout(output):
            result = self._select(missing=("jobs",))
        self.assertEqual(result, [])
        self.assertIn("Source jobs file not found", output.getvalue())

    def test_missing_details_file_fails_closed_explicitly(self):
        output = StringIO()
        with redirect_stdout(output):
            result = self._select(missing=("details",))
        self.assertEqual(result, [])
        self.assertIn("Details file not found", output.getvalue())

    def test_missing_analysis_file_fails_closed_explicitly(self):
        output = StringIO()
        with redirect_stdout(output):
            result = self._select(missing=("analysis",))
        self.assertEqual(result, [])
        self.assertIn("Analysis file not found", output.getvalue())

    def test_timestamp_read_failure_fails_closed(self):
        output = StringIO()

        def fail_for_details(path):
            if path == self.paths["details"]:
                raise OSError("stat denied")
            return 100

        with redirect_stdout(output):
            result = self._select(getmtime_side_effect=fail_for_details)
        self.assertEqual(result, [])
        self.assertIn("Could not verify source-stage timestamps", output.getvalue())

    def test_missing_identity_column_fails_closed(self):
        output = StringIO()
        with redirect_stdout(output):
            result = self._select(headers={"details": ["Title", "Company"]})
        self.assertEqual(result, [])
        self.assertIn("missing Link/URL column", output.getvalue())

    def test_identity_mismatch_fails_closed_even_at_equal_timestamps(self):
        changed_details = [
            {"Title": "Backend Engineer", "Link": "https://www.linkedin.com/jobs/view/2222222222/"},
            self.JOBS_ROWS[1],
        ]
        output = StringIO()
        with redirect_stdout(output):
            result = self._select(
                mtimes={"jobs": 100, "details": 100, "analysis": 100},
                rows={"details": changed_details},
            )
        self.assertEqual(result, [])
        self.assertIn("Job identities in", output.getvalue())

    def test_details_analysis_identity_mismatch_fails_closed(self):
        changed_analysis = [
            {"Title": "Backend Engineer", "Link": "https://www.linkedin.com/jobs/view/2222222222/"},
            self.JOBS_ROWS[1],
        ]
        output = StringIO()
        with redirect_stdout(output):
            result = self._select(
                rows={"analysis": changed_analysis},
                mtimes={"jobs": 100, "details": 100, "analysis": 100},
            )
        self.assertEqual(result, [])
        self.assertIn("Job identities in", output.getvalue())

    def test_available_job_id_must_agree_with_url_identity(self):
        rows = {
            "jobs": [
                {"Title": "Backend Engineer", "Link": self.JOB["Link"], "Job ID": "1111111111"},
                {"Title": "Platform Engineer", "Link": self.JOBS_ROWS[1]["Link"], "Job ID": "9876543210"},
            ],
        }
        output = StringIO()
        with redirect_stdout(output):
            result = self._select(
                rows=rows,
                headers={"jobs": ["Title", "Link", "Job ID"]},
            )
        self.assertEqual(result, [])
        self.assertIn("does not match its URL", output.getvalue())

    def test_identity_comparison_is_independent_of_row_order(self):
        self.assertEqual(self._select(), [self.JOB])

    def test_existing_eligibility_filters_remain_unchanged(self):
        rejected_jobs = [
            {**self.JOB, "Match Score": "69%"},
            {**self.JOB, "Location": "Toronto"},
            {**self.JOB, "Application Eligible": "No"},
            {**self.JOB, "Experience Skip": "Yes"},
            {**self.JOB, "Data Status": "MISSING"},
        ]
        self.assertEqual(self._select(analysis_jobs=rejected_jobs), [])
        self.assertEqual(self._select(), [self.JOB])

if __name__ == "__main__":
    unittest.main()
