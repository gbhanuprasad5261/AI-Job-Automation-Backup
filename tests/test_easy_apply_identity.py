import hashlib
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

    def _select_many_jobs(self, jobs):
        with (
            patch("easy_apply.load_csv", side_effect=lambda path: jobs if path == easy_apply.ANALYSIS_FILE else []),
            patch("easy_apply._analysis_matches_details", return_value=True),
            patch("easy_apply.get_application_status", return_value="NOT APPLIED"),
            patch("easy_apply.is_allowed_location", return_value=True),
        ):
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

    def test_insufficient_data_status_is_excluded(self):
        job = self._eligible_job(**{"Data Status": "INSUFFICIENT_DATA"})

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

    def test_same_normalized_url_with_conflicting_company_is_not_promoted(self):
        url = "https://www.linkedin.com/jobs/view/1234567890/"
        jobs = [
            self._eligible_job(Link=url, **{"Match Score": "90%"}),
            self._eligible_job(Company="Different Synthetic Company", Link=url + "?tracking=two", **{"Match Score": "95%"}),
        ]
        self.assertEqual(self._select_many_jobs(jobs), [])

    def test_distinct_companies_with_similar_titles_and_urls_remain_distinct(self):
        jobs = [
            self._eligible_job(Title="Backend Engineer", Company="Synthetic One", Link="https://www.linkedin.com/jobs/view/1000000001/"),
            self._eligible_job(Title="Backend Engineer II", Company="Synthetic Two", Link="https://www.linkedin.com/jobs/view/1000000002/"),
        ]
        self.assertEqual(len(self._select_many_jobs(jobs)), 2)

    def test_same_normalized_url_with_conflicting_job_ids_is_not_promoted(self):
        url = "https://careers.example.test/job/shared"
        jobs = [
            self._eligible_job(Link=url, **{"Job ID": "synthetic-1"}),
            self._eligible_job(Link=url + "?source=synthetic", **{"Job ID": "synthetic-2"}),
        ]
        self.assertEqual(self._select_many_jobs(jobs), [])

    def test_duplicate_url_tracking_parameters_keep_one_consistent_record(self):
        base = self._eligible_job(Link="https://careers.example.test/job/one")
        tracked = {**base, "Link": base["Link"] + "?campaign=synthetic", "Match Score": "85%"}
        selected = self._select_many_jobs([base, tracked])
        self.assertEqual(selected, [tracked])

    def test_application_identity_preserves_approved_formats_and_rejects_id_url_conflict(self):
        matching = {
            "Job ID": "1234567890",
            "Link": "https://www.linkedin.com/jobs/view/1234567890/?tracking=synthetic",
        }
        self.assertTrue(
            easy_apply._build_application_identity(matching).startswith(
                "linkedin-job:1234567890:url-sha256:"
            )
        )
        self.assertIsNone(easy_apply._build_application_identity({
            "Job ID": "1234567890",
            "Link": "https://www.linkedin.com/jobs/view/9999999999/",
        }))

        url_only = {"Link": "https://www.linkedin.com/jobs/view/1234567890/"}
        expected = "linkedin-link-sha256:" + hashlib.sha256(url_only["Link"].encode("utf-8")).hexdigest()
        self.assertEqual(easy_apply._build_application_identity(url_only), expected)
        self.assertIsNone(easy_apply._build_application_identity({"Job ID": "1234567890", "Link": ""}))

    def test_same_job_id_different_urls_get_distinct_approval_identities(self):
        first = easy_apply._build_application_identity({
            "Job ID": "synthetic-123",
            "Link": "https://careers.example.test/role/first",
        })
        second = easy_apply._build_application_identity({
            "Job ID": "synthetic-123",
            "Link": "https://careers.example.test/role/second",
        })
        tracking_variant = easy_apply._build_application_identity({
            "Job ID": "synthetic-123",
            "Link": "https://careers.example.test/role/first?tracking=synthetic",
        })

        self.assertNotEqual(first, second)
        self.assertEqual(first, tracking_variant)

    def test_direct_open_rejects_explicit_job_id_url_conflict_before_browser(self):
        job = {
            "Title": "Synthetic role",
            "Company": "Synthetic company",
            "Job ID": "1234567890",
            "Link": "https://www.linkedin.com/jobs/view/9999999999/",
        }
        with (
            patch.object(easy_apply.EXECUTION_POLICY, "allows_browser_actions", return_value=True),
            patch.object(easy_apply, "sync_playwright") as browser,
        ):
            self.assertFalse(easy_apply.open_easy_apply(job))
        browser.assert_not_called()


if __name__ == "__main__":
    unittest.main()
