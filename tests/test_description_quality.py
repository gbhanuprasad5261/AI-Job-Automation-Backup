import csv
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import config
import job_analyzer


class DescriptionQualityTests(unittest.TestCase):
    @staticmethod
    def _exact_boundary_description(token_count=30):
        if token_count == 30:
            # 81 + 7 + (28 * 4) = 200 non-whitespace characters and 30 tokens.
            return "x" * 81 + " wording " + " ".join(["word"] * 28)
        return "x" * 200 + " " + " ".join(["word"] * 28)

    def _analyze(self, description, *, experience_years=0, job_overrides=None):
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / "job_details.csv"
            output_path = Path(temp_dir) / "job_analysis.csv"
            job = {
                "Title": "Backend Engineer",
                "Company": "Example Corp",
                "Location": "Bengaluru",
                "Easy Apply": "Yes",
                "Link": "https://www.linkedin.com/jobs/view/1234567890/",
                "Description": description,
                **(job_overrides or {}),
            }
            with input_path.open("w", encoding="utf-8", newline="") as file:
                writer = csv.DictWriter(file, fieldnames=list(job))
                writer.writeheader()
                writer.writerow(job)

            with (
                patch.object(job_analyzer, "INPUT_FILE", str(input_path)),
                patch.object(job_analyzer, "OUTPUT_FILE", str(output_path)),
                patch.object(config, "MIN_MATCH_SCORE", 70),
                patch.object(job_analyzer, "CANDIDATE_EXPERIENCE_YEARS", 2),
                patch.object(job_analyzer, "match_resume", return_value=(85, {"java"}, set())) as matcher,
                patch.object(job_analyzer, "extract_experience_years", return_value=experience_years),
                patch.object(job_analyzer, "get_experience_label", return_value=f"{experience_years}+ years"),
                redirect_stdout(StringIO()),
            ):
                job_analyzer.analyze_jobs()

            with output_path.open(encoding="utf-8", newline="") as file:
                result = next(csv.DictReader(file))
            return result, matcher

    def test_empty_description_is_insufficient_and_ineligible(self):
        result, matcher = self._analyze("")
        self.assertEqual(result["Data Status"], "INSUFFICIENT_DATA")
        self.assertEqual(result["Application Eligible"], "No")
        self.assertEqual(result["Experience Skip"], "No")
        matcher.assert_not_called()

    def test_whitespace_only_description_is_insufficient(self):
        result, matcher = self._analyze(" \t\r\n ")
        self.assertEqual(result["Data Status"], "INSUFFICIENT_DATA")
        self.assertEqual(result["Application Eligible"], "No")
        matcher.assert_not_called()

    def test_short_description_below_threshold_is_insufficient(self):
        result, matcher = self._analyze("Java backend engineer role")
        self.assertEqual(result["Data Status"], "INSUFFICIENT_DATA")
        self.assertEqual(result["Application Eligible"], "No")
        matcher.assert_not_called()

    def test_placeholder_only_description_is_rejected_even_when_long(self):
        result, matcher = self._analyze("lorem ipsum " * 40)
        self.assertEqual(result["Data Status"], "INSUFFICIENT_DATA")
        self.assertEqual(result["Application Eligible"], "No")
        self.assertEqual(result["Experience Skip"], "No")
        matcher.assert_not_called()

    def test_single_known_placeholder_is_insufficient(self):
        result, matcher = self._analyze("no description available")
        self.assertEqual(result["Data Status"], "INSUFFICIENT_DATA")
        self.assertEqual(result["Application Eligible"], "No")
        self.assertEqual(result["Experience Skip"], "No")
        matcher.assert_not_called()

    def test_repeated_known_placeholder_is_insufficient_above_both_thresholds(self):
        description = "no description available " * 20
        self.assertGreaterEqual(sum(not char.isspace() for char in description), 200)
        self.assertGreaterEqual(len(job_analyzer.re.findall(r"\b\w+\b", description)), 30)
        result, matcher = self._analyze(description)
        self.assertEqual(result["Data Status"], "INSUFFICIENT_DATA")
        self.assertEqual(result["Application Eligible"], "No")
        self.assertEqual(result["Experience Skip"], "No")
        matcher.assert_not_called()

    def test_placeholder_phrase_inside_valid_description_remains_accepted(self):
        description = (
            "This role is fully described with real responsibilities, required skills, "
            "team collaboration, software delivery, testing, and support. The phrase "
            "no description available is not a substitute for these details. "
        ).strip()
        description = description + " " + description
        result, matcher = self._analyze(description)
        self.assertEqual(result["Data Status"], "OK")
        matcher.assert_called_once_with(description)

    def test_199_nonwhitespace_characters_is_below_boundary(self):
        description = self._exact_boundary_description().replace("x" * 81, "x" * 80, 1)
        self.assertEqual(sum(not char.isspace() for char in description), 199)
        self.assertEqual(len(job_analyzer.re.findall(r"\b\w+\b", description)), 30)
        result, matcher = self._analyze(description)
        self.assertEqual(result["Data Status"], "INSUFFICIENT_DATA")
        self.assertEqual(result["Application Eligible"], "No")
        matcher.assert_not_called()

    def test_29_tokens_is_below_boundary_even_with_enough_characters(self):
        description = self._exact_boundary_description(token_count=29)
        self.assertGreaterEqual(sum(not char.isspace() for char in description), 200)
        self.assertEqual(len(job_analyzer.re.findall(r"\b\w+\b", description)), 29)
        result, matcher = self._analyze(description)
        self.assertEqual(result["Data Status"], "INSUFFICIENT_DATA")
        self.assertEqual(result["Application Eligible"], "No")
        matcher.assert_not_called()

    def test_exact_character_and_token_thresholds_are_accepted(self):
        description = self._exact_boundary_description()
        self.assertEqual(sum(not char.isspace() for char in description), 200)
        self.assertEqual(len(job_analyzer.re.findall(r"\b\w+\b", description)), 30)
        result, matcher = self._analyze(description)
        self.assertEqual(result["Data Status"], "OK")
        matcher.assert_called_once_with(description)

    def test_tcs_description_fixture_remains_accepted(self):
        description = (
            "Hi Greetings From TCS!!! We have exciting opportunities with TCS for Java FSD "
            "Professionals. If you have relevant experience in Java technologies and are "
            "looking for a career move, please share your updated resume. Job Details "
            "Virtual- Interview Location: Chennai/Bengaluru/Hyderabad/Mumbai/Indore/"
            "Ahmedabad Experience Range: 5 - 10 Yrs MUST SKILLS: Java FSD Job Description "
            "Required Technical Skill Set Java FSD with Angular. NOTE: Please only apply "
            "if you are currently working and having 90 days of Notice period."
        )

        result, matcher = self._analyze(description)
        self.assertEqual(result["Data Status"], "OK")
        matcher.assert_called_once_with(description)

    def test_valid_long_description_preserves_match_and_experience_rules(self):
        description = ("Java backend engineer with Spring experience. " * 12) + "3 years of experience."
        result, matcher = self._analyze(description, experience_years=3)
        self.assertEqual(result["Data Status"], "OK")
        self.assertEqual(result["Match Score"], "85%")
        self.assertEqual(result["Experience Years"], "3")
        self.assertEqual(result["Experience Skip"], "Yes")
        self.assertEqual(result["Application Eligible"], "No")
        matcher.assert_called_once_with(description)


if __name__ == "__main__":
    unittest.main()
