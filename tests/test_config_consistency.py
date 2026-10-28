import csv
import json
import os
import subprocess
import sys
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
                    "Description": "Java backend engineer role. " * 12,
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


class ConfigEnvironmentParsingTests(unittest.TestCase):
    CONFIG_KEYS = (
        "LINKEDIN_EMAIL",
        "LINKEDIN_PASSWORD",
        "MIN_MATCH_SCORE",
        "DAILY_APPLICATION_LIMIT",
        "MAX_JOBS",
        "AUTO_SUBMIT",
        "DRY_RUN",
        "UNKNOWN_QUESTIONS_POLICY",
        "CHROME_CDP_URL",
    )

    @classmethod
    def _import_config(cls, overrides=None, dotenv_contents=None):
        project_root = Path(__file__).resolve().parents[1]
        env = os.environ.copy()
        for name in cls.CONFIG_KEYS:
            env.pop(name, None)
        if dotenv_contents is None:
            env["PYTHON_DOTENV_DISABLED"] = "1"
        else:
            env.pop("PYTHON_DOTENV_DISABLED", None)
        env.pop("PYTHONHOME", None)
        env.pop("PYTHONUSERBASE", None)
        env["PYTHONPATH"] = str(project_root)
        env.update(overrides or {})
        output = (
            "import json, config; "
            "print(json.dumps({"
            "'email_missing': config.LINKEDIN_EMAIL is None,"
            "'password_missing': config.LINKEDIN_PASSWORD is None,"
            "'min_match_score': config.MIN_MATCH_SCORE,"
            "'daily_application_limit': config.DAILY_APPLICATION_LIMIT,"
            "'max_jobs': config.MAX_JOBS,"
            "'auto_submit': config.AUTO_SUBMIT,"
            "'dry_run': config.DRY_RUN,"
            "'unknown_questions_policy': config.UNKNOWN_QUESTIONS_POLICY,"
            "'cdp_url': config.CHROME_CDP_URL"
            "}))"
        )
        with tempfile.TemporaryDirectory() as working_dir:
            if dotenv_contents is not None:
                (Path(working_dir) / ".env").write_text(dotenv_contents, encoding="utf-8")
            return subprocess.run(
                [sys.executable, "-c", output],
                cwd=working_dir,
                env=env,
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )

    def test_missing_optional_credentials_and_settings_use_documented_defaults(self):
        result = self._import_config()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(
            json.loads(result.stdout),
            {
                "email_missing": True,
                "password_missing": True,
                "min_match_score": 70,
                "daily_application_limit": 15,
                "max_jobs": 30,
                "auto_submit": False,
                "dry_run": False,
                "unknown_questions_policy": "SKIP",
                "cdp_url": "http://127.0.0.1:9222",
            },
        )

    def test_environment_values_override_dotenv_and_dotenv_fills_missing_values(self):
        result = self._import_config(
            {"MIN_MATCH_SCORE": "88"},
            dotenv_contents="MIN_MATCH_SCORE=62\nMAX_JOBS=23\n",
        )
        self.assertEqual(result.returncode, 0)
        values = json.loads(result.stdout)
        self.assertEqual(values["min_match_score"], 88)
        self.assertEqual(values["max_jobs"], 23)

    def test_empty_optional_credentials_remain_distinct_from_missing(self):
        result = self._import_config({"LINKEDIN_EMAIL": "", "LINKEDIN_PASSWORD": "   "})
        self.assertEqual(result.returncode, 0)
        values = json.loads(result.stdout)
        self.assertFalse(values["email_missing"])
        self.assertFalse(values["password_missing"])

    def test_auto_submit_boolean_spellings_and_empty_values(self):
        for value in ("1", "true", "YES", " On "):
            with self.subTest(value=value):
                result = self._import_config({"AUTO_SUBMIT": value})
                self.assertEqual(result.returncode, 0)
                self.assertTrue(json.loads(result.stdout)["auto_submit"])

        for value in ("", "   ", "false", "NO", "0", "off"):
            with self.subTest(value=value):
                result = self._import_config({"AUTO_SUBMIT": value})
                self.assertEqual(result.returncode, 0)
                self.assertFalse(json.loads(result.stdout)["auto_submit"])

    def test_environment_numeric_and_policy_overrides_are_parsed(self):
        result = self._import_config(
            {
                "MIN_MATCH_SCORE": "81",
                "DAILY_APPLICATION_LIMIT": "4",
                "MAX_JOBS": "12",
                "CHROME_CDP_URL": "http://127.0.0.1:9333",
                "DRY_RUN": "on",
                "UNKNOWN_QUESTIONS_POLICY": "review",
            }
        )
        self.assertEqual(result.returncode, 0)
        values = json.loads(result.stdout)
        self.assertEqual(values["min_match_score"], 81)
        self.assertEqual(values["daily_application_limit"], 4)
        self.assertEqual(values["max_jobs"], 12)
        self.assertTrue(values["dry_run"])
        self.assertEqual(values["unknown_questions_policy"], "REVIEW")
        self.assertEqual(values["cdp_url"], "http://127.0.0.1:9333")

    def test_malformed_integer_settings_fail_during_import(self):
        for name in ("MIN_MATCH_SCORE", "DAILY_APPLICATION_LIMIT", "MAX_JOBS"):
            for value in ("not-an-integer", "", "   "):
                with self.subTest(setting=name, value=value):
                    result = self._import_config({name: value})
                    self.assertNotEqual(result.returncode, 0)
                    self.assertTrue(
                        any(line.startswith("ValueError:") for line in result.stderr.splitlines())
                    )

    def test_negative_daily_application_limit_is_rejected(self):
        result = self._import_config({"DAILY_APPLICATION_LIMIT": "-1"})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "DAILY_APPLICATION_LIMIT must be zero or greater",
            result.stderr,
        )

    def test_unsupported_unknown_question_policy_is_rejected(self):
        for value in ("UNSAFE", "", "   "):
            with self.subTest(value=value):
                result = self._import_config({"UNKNOWN_QUESTIONS_POLICY": value})
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("UNKNOWN_QUESTIONS_POLICY must be SKIP or REVIEW", result.stderr)

if __name__ == "__main__":
    unittest.main()
