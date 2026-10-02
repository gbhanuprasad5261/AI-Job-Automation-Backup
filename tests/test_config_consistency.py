import csv
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import config
import easy_apply
import job_analyzer


class MatchThresholdConfigurationTests(unittest.TestCase):
    def _analyze_eligibility(self, score, threshold):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "job_details.csv"
            output_path = Path(temp_dir) / "job_analysis.csv"
            with input_path.open("w", encoding="utf-8", newline="") as file:
                writer = csv.DictWriter(
                    file,
                    fieldnames=[
                        "Title", "Company", "Location", "Easy Apply", "Link",
                        "Description",
                    ],
                )
                writer.writeheader()
                writer.writerow({
                    "Title": "Backend Engineer",
                    "Company": "Example Corp",
                    "Location": "Bengaluru",
                    "Easy Apply": "Yes",
                    "Link": "https://www.linkedin.com/jobs/view/1234567890/",
                    "Description": "Java backend engineer role",
                })

            with (
                patch.object(config, "MIN_MATCH_SCORE", threshold),
                patch.object(job_analyzer, "INPUT_FILE", str(input_path)),
                patch.object(job_analyzer, "OUTPUT_FILE", str(output_path)),
                patch.object(job_analyzer, "match_resume", return_value=(score, set(), set())),
                patch.object(job_analyzer, "extract_experience_years", return_value=0),
                patch.object(job_analyzer, "get_experience_label", return_value="Not specified"),
                redirect_stdout(StringIO()),
            ):
                job_analyzer.analyze_jobs()

            with output_path.open(encoding="utf-8", newline="") as file:
                return next(csv.DictReader(file))["Application Eligible"]

    @staticmethod
    def _selection_job(score):
        return {
            "Title": "Backend Engineer",
            "Company": "Example Corp",
            "Location": "Bengaluru",
            "Match Score": f"{score}%",
            "Application Eligible": "Yes",
            "Experience Skip": "No",
            "Data Status": "OK",
            "Link": "https://www.linkedin.com/jobs/view/1234567890/",
        }

    @staticmethod
    def _select(job):
        def load_csv(path):
            return [job] if path == easy_apply.ANALYSIS_FILE else []

        with (
            patch.object(easy_apply, "load_csv", side_effect=load_csv),
            patch.object(easy_apply, "_analysis_matches_details", return_value=True),
            patch.object(easy_apply, "_load_application_history", return_value=[]),
        ):
            return easy_apply.get_recommended_jobs()

    def test_runtime_default_threshold_is_70(self):
        self.assertEqual(config.MIN_MATCH_SCORE, 70)

    def test_analyzer_default_threshold_includes_70_and_rejects_below(self):
        self.assertEqual(self._analyze_eligibility(70, 70), "Yes")
        self.assertEqual(self._analyze_eligibility(69, 70), "No")

    def test_analyzer_uses_non_default_threshold(self):
        self.assertEqual(self._analyze_eligibility(79, 80), "No")
        self.assertEqual(self._analyze_eligibility(80, 80), "Yes")

    def test_selector_default_threshold_includes_70_and_rejects_below(self):
        with patch.object(config, "MIN_MATCH_SCORE", 70):
            self.assertEqual(self._select(self._selection_job(70)), [self._selection_job(70)])
            self.assertEqual(self._select(self._selection_job(69)), [])

    def test_selector_uses_non_default_threshold(self):
        with patch.object(config, "MIN_MATCH_SCORE", 80):
            self.assertEqual(self._select(self._selection_job(75)), [])
            self.assertEqual(self._select(self._selection_job(80)), [self._selection_job(80)])

    def test_analyzer_and_selector_use_the_same_configured_threshold(self):
        with patch.object(config, "MIN_MATCH_SCORE", 80):
            self.assertEqual(self._analyze_eligibility(79, 80), "No")
            self.assertEqual(self._select(self._selection_job(79)), [])
            self.assertEqual(self._analyze_eligibility(80, 80), "Yes")
            self.assertEqual(self._select(self._selection_job(80)), [self._selection_job(80)])


class CdpConfigurationTests(unittest.TestCase):
    def test_easy_apply_uses_configured_cdp_url(self):
        browser = MagicMock()
        browser.contexts = []
        playwright = MagicMock()
        playwright.chromium.connect_over_cdp.return_value = browser
        manager = MagicMock()
        manager.__enter__.return_value = playwright
        manager.__exit__.return_value = False
        job = {
            "Title": "Backend Engineer",
            "Company": "Example Corp",
            "Location": "Bengaluru",
            "Link": "https://www.linkedin.com/jobs/view/1234567890/",
        }
        test_url = "http://127.0.0.1:9333"

        with (
            patch.object(config, "CHROME_CDP_URL", test_url),
            patch.object(easy_apply, "sync_playwright", return_value=manager),
            redirect_stdout(StringIO()),
        ):
            self.assertFalse(easy_apply.open_easy_apply(job))

        playwright.chromium.connect_over_cdp.assert_called_once_with(test_url)


if __name__ == "__main__":
    unittest.main()
