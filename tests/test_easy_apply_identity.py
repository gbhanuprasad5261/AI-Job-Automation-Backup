import unittest
from unittest.mock import patch

import easy_apply


class ApplicationIdentityTests(unittest.TestCase):
    def setUp(self):
        self.history_patch = patch(
            "easy_apply._load_application_history",
            return_value=[],
        )
        self.history_patch.start()
        self.addCleanup(self.history_patch.stop)

    def test_unique_title_company_fallback_matches(self):
        job = {"Title": "Backend Engineer", "Company": "Example Corp"}
        tracker = [{
            "Title": "Backend Engineer",
            "Company": "Example Corp",
            "Status": "APPLIED",
            "Application Status": "APPLIED",
            "Link": "",
        }]

        with patch("easy_apply.load_csv", return_value=tracker):
            self.assertEqual(easy_apply.get_application_status(job), "APPLIED")

    def test_duplicate_title_company_candidates_do_not_match_arbitrarily(self):
        job = {"Title": "Backend Engineer", "Company": "Example Corp"}
        tracker = [
            {
                "Title": "Backend Engineer",
                "Company": "Example Corp",
                "Status": "APPLIED",
                "Application Status": "APPLIED",
                "Link": "",
            },
            {
                "Title": " backend   engineer ",
                "Company": "EXAMPLE CORP",
                "Status": "READY_FOR_REVIEW",
                "Application Status": "READY_FOR_REVIEW",
                "Link": "",
            },
        ]

        with patch("easy_apply.load_csv", return_value=tracker):
            self.assertEqual(easy_apply.get_application_status(job), "NOT APPLIED")

    def test_exact_job_url_matches_even_with_duplicate_title_company(self):
        job = {
            "Title": "Backend Engineer",
            "Company": "Example Corp",
            "Link": "https://www.linkedin.com/jobs/view/1234567890/",
        }
        tracker = [
            {
                "Title": "Backend Engineer",
                "Company": "Example Corp",
                "Status": "APPLIED",
                "Application Status": "APPLIED",
                "Link": "https://www.linkedin.com/jobs/view/1234567890/",
            },
            {
                "Title": "Backend Engineer",
                "Company": "Example Corp",
                "Status": "READY_FOR_REVIEW",
                "Application Status": "READY_FOR_REVIEW",
                "Link": "https://www.linkedin.com/jobs/view/9876543210/",
            },
        ]

        with patch("easy_apply.load_csv", return_value=tracker):
            self.assertEqual(easy_apply.get_application_status(job), "APPLIED")

    def _select_jobs(self, job, tracker=None, history=None):
        tracker = tracker or []

        def fake_load_csv(path):
            if path == easy_apply.ANALYSIS_FILE:
                return [job]
            if path == easy_apply.TRACKER_FILE:
                return tracker
            return []

        with patch("easy_apply.load_csv", side_effect=fake_load_csv):
            with patch(
                "easy_apply._load_application_history",
                return_value=history or [],
            ):
                with patch("easy_apply._analysis_matches_details", return_value=True):
                    return easy_apply.get_recommended_jobs()

    def _eligible_job(self, **overrides):
        job = {
            "Title": "Backend Engineer",
            "Company": "Example Corp",
            "Location": "Bengaluru",
            "Match Score": "70%",
            "Application Eligible": "Yes",
            "Experience Skip": "No",
            "Data Status": "OK",
            "Link": "https://www.linkedin.com/jobs/view/1234567890/",
        }
        job.update(overrides)
        return job

    def test_eligible_job_at_score_threshold_is_selected(self):
        job = self._eligible_job()

        self.assertEqual(self._select_jobs(job), [job])

    def test_application_eligible_no_is_excluded(self):
        job = self._eligible_job(**{"Application Eligible": "No"})

        self.assertEqual(self._select_jobs(job), [])

    def test_experience_skip_yes_is_excluded(self):
        job = self._eligible_job(**{"Experience Skip": "Yes"})

        self.assertEqual(self._select_jobs(job), [])

    def test_non_ok_data_status_is_excluded(self):
        job = self._eligible_job(**{"Data Status": "MISSING"})

        self.assertEqual(self._select_jobs(job), [])

    def test_missing_data_status_remains_compatible(self):
        job = self._eligible_job()
        del job["Data Status"]

        self.assertEqual(self._select_jobs(job), [job])

    def test_tracker_applied_status_still_excludes_job(self):
        job = self._eligible_job()
        tracker = [{
            "Title": job["Title"],
            "Company": job["Company"],
            "Status": "APPLIED",
            "Application Status": "APPLIED",
            "Link": job["Link"],
        }]

        self.assertEqual(self._select_jobs(job, tracker=tracker), [])

    def test_history_applied_status_still_excludes_job(self):
        job = self._eligible_job()
        history = [{
            "Title": job["Title"],
            "Company": job["Company"],
            "Status": "APPLIED",
            "URL": job["Link"],
        }]

        self.assertEqual(self._select_jobs(job, history=history), [])

    def test_ambiguous_title_company_fallback_remains_unresolved(self):
        job = self._eligible_job()
        tracker = [
            {
                "Title": "Backend Engineer",
                "Company": "Example Corp",
                "Status": "APPLIED",
                "Application Status": "APPLIED",
                "Link": "",
            },
            {
                "Title": " backend   engineer ",
                "Company": "EXAMPLE CORP",
                "Status": "READY_FOR_REVIEW",
                "Application Status": "READY_FOR_REVIEW",
                "Link": "",
            },
        ]

        self.assertEqual(self._select_jobs(job, tracker=tracker), [job])


if __name__ == "__main__":
    unittest.main()
