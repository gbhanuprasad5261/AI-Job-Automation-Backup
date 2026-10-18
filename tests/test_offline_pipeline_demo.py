"""Repeatable offline demonstration of the safe analysis stages."""

import csv
from contextlib import redirect_stdout
from io import StringIO
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import application_tracker
import config
import easy_apply
import job_analyzer
import skill_matcher
from execution_policy import DRY_RUN_SKIPPED_BROWSER, EXECUTION_POLICY


class OfflinePipelineDemoTests(unittest.TestCase):
    def test_normalized_fixture_flows_through_analysis_selection_dry_run_and_isolated_tracker(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            jobs_path = root / "jobs.csv"
            details_path = root / "job_details.csv"
            analysis_path = root / "job_analysis.csv"
            tracker_path = root / "application_tracker.csv"
            history_path = root / "application_history.csv"
            job = {
                "Title": "Java Backend Engineer",
                "Company": "Example Corp",
                "Location": "Bengaluru",
                "Easy Apply": "Yes",
                "Link": "https://www.linkedin.com/jobs/view/9876543210/",
                "Description": (
                    "Java Spring Boot SQL REST API microservices experience. "
                    "Build reliable backend services, design maintainable APIs, "
                    "work with relational data, review code, write automated tests, "
                    "support production systems, collaborate with product teams, "
                    "and document technical decisions. "
                ) * 3,
            }
            base_fields = ["Title", "Company", "Location", "Easy Apply", "Link"]
            details_fields = base_fields + ["Experience", "Skills", "Description"]

            with jobs_path.open("w", encoding="utf-8", newline="") as file:
                writer = csv.DictWriter(file, fieldnames=base_fields)
                writer.writeheader()
                writer.writerow({key: job[key] for key in base_fields})
            with details_path.open("w", encoding="utf-8", newline="") as file:
                writer = csv.DictWriter(file, fieldnames=details_fields)
                writer.writeheader()
                writer.writerow({key: job.get(key, "") for key in details_fields})

            # Isolate job_analyzer's relative data-directory setup as well as
            # every file it reads or writes to this test's temporary folder.
            previous_cwd = Path.cwd()
            try:
                import os
                os.chdir(root)
                with (
                    patch.object(job_analyzer, "INPUT_FILE", str(details_path)),
                    patch.object(job_analyzer, "OUTPUT_FILE", str(analysis_path)),
                    patch.object(easy_apply, "JOBS_FILE", str(jobs_path)),
                    patch.object(easy_apply, "DETAILS_FILE", str(details_path)),
                    patch.object(easy_apply, "ANALYSIS_FILE", str(analysis_path)),
                    patch.object(easy_apply, "TRACKER_FILE", str(tracker_path)),
                    patch.object(easy_apply, "APPLICATION_HISTORY_FILE", str(history_path)),
                    patch.object(application_tracker, "OUTPUT_FILE", str(tracker_path)),
                    patch.object(skill_matcher, "canonical_resume_skills", {
                        "java", "spring", "spring boot", "sql", "rest api", "microservices",
                    }),
                    patch.object(config, "MIN_MATCH_SCORE", 70),
                    redirect_stdout(StringIO()),
                ):
                    job_analyzer.analyze_jobs()
                    candidates = easy_apply.get_recommended_jobs()
                    self.assertEqual(len(candidates), 1)

                    with patch.object(config, "DRY_RUN", True):
                        decision = EXECUTION_POLICY.dry_run_result(candidates[0])
                        self.assertEqual(decision["status"], DRY_RUN_SKIPPED_BROWSER)
                        self.assertFalse(EXECUTION_POLICY.allows_browser_actions())
                        self.assertFalse(EXECUTION_POLICY.allows_persistence())
                        self.assertFalse(decision["live_route_confirmed"])

                    # Exercise tracker serialization only against a separate
                    # temporary CSV; no application workflow is invoked.
                    application_tracker.save_tracker([{
                        "Title": decision["job_title"],
                        "Company": decision["company"],
                        "Location": candidates[0]["Location"],
                        "Match Score": candidates[0]["Match Score"],
                        "Priority": candidates[0]["Priority"],
                        "Easy Apply": candidates[0]["Easy Apply"],
                        "Link": decision["job_url"],
                        "Status": "NOT APPLIED",
                    }])
            finally:
                os.chdir(previous_cwd)

            with tracker_path.open(encoding="utf-8", newline="") as file:
                tracker_rows = list(csv.DictReader(file))
            self.assertEqual(len(tracker_rows), 1)
            self.assertEqual(tracker_rows[0]["Status"], "NOT APPLIED")
            self.assertTrue(analysis_path.exists())


if __name__ == "__main__":
    unittest.main()
