import csv
import os
import re
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import easy_apply
import job_analyzer


class AnalysisRecommendationHandoffTests(unittest.TestCase):
    DETAILS_FIELDS = [
        "Title", "Company", "Location", "Easy Apply", "Link", "Description",
    ]
    ANALYSIS_FIELDS = [
        "Title", "Company", "Location", "Easy Apply", "Match Score",
        "Priority", "Matched Skills", "Missing Skills", "Experience Required",
        "Experience Years", "Experience Skip", "Data Status",
        "Application Eligible", "Link",
    ]
    DESCRIPTION = (
        "Synthetic software engineering role with backend development, APIs, "
        "databases, testing, collaboration, documentation, reliability, "
        "distributed services, code reviews, deployment, monitoring, and "
        "cross-functional communication responsibilities for an entry level "
        "developer position."
    )

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="synthetic-analysis-handoff-")
        self.addCleanup(self.temp.cleanup)
        self.previous_cwd = Path.cwd()
        os.chdir(self.temp.name)
        self.addCleanup(os.chdir, self.previous_cwd)

        self.jobs_file = Path("jobs.csv")
        self.details_file = Path("data/job_details.csv")
        self.analysis_file = Path("data/job_analysis.csv")
        self.tracker_file = Path("data/application_tracker.csv")
        self.details_file.parent.mkdir(parents=True, exist_ok=True)
        self._write_csv(self.tracker_file, ["Title", "Company", "Link", "Status"], [])

    @staticmethod
    def _write_csv(path, fieldnames, rows):
        with Path(path).open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(
                stream,
                fieldnames=fieldnames,
                extrasaction="ignore",
            )
            writer.writeheader()
            writer.writerows(rows)

    def _row(self, *, title="Synthetic Engineer", company="Synthetic Employer", link=None,
             location="Synthetic Region", score=90, description=None):
        return {
            "Title": title,
            "Company": company,
            "Location": location,
            "Easy Apply": "Yes",
            "Link": link or f"https://www.linkedin.com/jobs/view/{1000 + score}/",
            "Description": description if description is not None else f"{self.DESCRIPTION} SyntheticScore{score}.",
        }

    def _write_stages(self, rows, *, source_fields=None, detail_fields=None):
        source_fields = source_fields or ["Title", "Company", "Link"]
        detail_fields = detail_fields or self.DETAILS_FIELDS
        self._write_csv(
            self.jobs_file,
            source_fields,
            [{key: row.get(key, "") for key in source_fields} for row in rows],
        )
        self._write_csv(self.details_file, detail_fields, rows)

    def _run_analyzer_and_recommend(self, rows, *, source_fields=None, detail_fields=None):
        self._write_stages(rows, source_fields=source_fields, detail_fields=detail_fields)

        def synthetic_match(description):
            match = re.search(r"SyntheticScore(-?\d+(?:\.\d+)?)", description)
            score = float(match.group(1)) if match else 90.0
            return score, {"Synthetic Skill"}, {"Unmatched Skill"}

        with ExitStack() as stack:
            stack.enter_context(patch.object(job_analyzer, "INPUT_FILE", str(self.details_file)))
            stack.enter_context(patch.object(job_analyzer, "OUTPUT_FILE", str(self.analysis_file)))
            stack.enter_context(patch.object(easy_apply, "JOBS_FILE", str(self.jobs_file)))
            stack.enter_context(patch.object(easy_apply, "DETAILS_FILE", str(self.details_file)))
            stack.enter_context(patch.object(easy_apply, "ANALYSIS_FILE", str(self.analysis_file)))
            stack.enter_context(patch.object(easy_apply, "TRACKER_FILE", str(self.tracker_file)))
            stack.enter_context(patch.object(easy_apply, "get_application_status", return_value="NOT APPLIED"))
            stack.enter_context(patch.object(easy_apply, "is_allowed_location", return_value=True))
            stack.enter_context(patch.object(job_analyzer, "location_matches", return_value=True))
            stack.enter_context(patch.object(job_analyzer, "match_resume", side_effect=synthetic_match))
            stack.enter_context(patch.object(job_analyzer, "extract_experience_years", return_value=0))
            stack.enter_context(patch.object(job_analyzer, "get_experience_label", return_value="Synthetic entry level"))
            stack.enter_context(patch.object(job_analyzer.config, "MIN_MATCH_SCORE", 70))
            stack.enter_context(patch.object(easy_apply.config, "MIN_MATCH_SCORE", 70))
            stack.enter_context(patch.object(job_analyzer, "CANDIDATE_EXPERIENCE_YEARS", 10))
            job_analyzer.analyze_jobs()
            analyzed = easy_apply.load_csv(str(self.analysis_file))
            recommendations = easy_apply.get_recommended_jobs()
        return analyzed, recommendations

    def _write_analysis_stages(self, rows, fields=None):
        self._write_stages(rows)
        self._write_csv(self.analysis_file, fields or self.ANALYSIS_FIELDS, rows)

    def _read_recommendations(self, *, min_score=70):
        with (
            patch.object(easy_apply, "JOBS_FILE", str(self.jobs_file)),
            patch.object(easy_apply, "DETAILS_FILE", str(self.details_file)),
            patch.object(easy_apply, "ANALYSIS_FILE", str(self.analysis_file)),
            patch.object(easy_apply, "TRACKER_FILE", str(self.tracker_file)),
            patch.object(easy_apply, "get_application_status", return_value="NOT APPLIED"),
            patch.object(easy_apply, "is_allowed_location", return_value=True),
            patch.object(easy_apply.config, "MIN_MATCH_SCORE", min_score),
        ):
            return easy_apply.get_recommended_jobs()

    def test_actual_analyzer_output_handoff_filters_score_and_description_and_preserves_unicode(self):
        rows = [
            self._row(title="Backend Ω Engineer", company="Café Synthetic", score=92),
            self._row(title="Platform Engineer", company="Synthetic Labs", score=81),
            self._row(title="Below Threshold", company="Synthetic Labs", score=69),
            self._row(title="Missing Description", company="Synthetic Labs", score=99, description=""),
        ]

        analyzed, recommendations = self._run_analyzer_and_recommend(
            rows,
            detail_fields=["Description", "Link", "Company", "Title", "Easy Apply", "Location"],
        )

        self.assertEqual(len(analyzed), 4)
        self.assertEqual(
            [row["Title"] for row in recommendations],
            ["Backend Ω Engineer", "Platform Engineer"],
        )
        self.assertEqual(recommendations[0]["Company"], "Café Synthetic")
        self.assertEqual(recommendations[0]["Application Eligible"], "Yes")
        self.assertEqual(analyzed[2]["Application Eligible"], "No")
        self.assertEqual(analyzed[3]["Data Status"], "INSUFFICIENT_DATA")

    def test_missing_title_or_company_is_not_promoted(self):
        for missing in ("title", "company"):
            with self.subTest(missing=missing):
                row = self._row(
                    title="" if missing == "title" else "Synthetic Engineer",
                    company="" if missing == "company" else "Synthetic Employer",
                    link="https://www.linkedin.com/jobs/view/2001/",
                    score=95,
                )
                analyzed, recommendations = self._run_analyzer_and_recommend([row])
                self.assertEqual(analyzed[0]["Application Eligible"], "No")
                self.assertEqual(recommendations, [])

    def test_duplicate_urls_produce_at_most_one_recommendation(self):
        duplicate_url = "https://www.linkedin.com/jobs/view/3001/"
        rows = [
            self._row(title="Duplicate Listing", link=duplicate_url, score=90),
            self._row(title="Duplicate Listing", link=duplicate_url, score=85),
        ]

        analyzed, recommendations = self._run_analyzer_and_recommend(rows)

        self.assertEqual(len(analyzed), 2)
        self.assertEqual(len(recommendations), 1)
        self.assertEqual(recommendations[0]["Match Score"], "90.0%")

    def test_duplicate_url_with_conflicting_metadata_is_not_promoted(self):
        duplicate_url = "https://www.linkedin.com/jobs/view/3002/"
        rows = [
            self._row(title="Listing A", company="Synthetic One", link=duplicate_url, score=92),
            self._row(title="Listing B", company="Synthetic Two", link=duplicate_url, score=98),
        ]

        _, recommendations = self._run_analyzer_and_recommend(rows)

        self.assertEqual(recommendations, [])

    def test_distinct_linkedin_search_urls_for_same_job_id_deduplicate(self):
        rows = [
            self._row(
                title="Canonical Engineer",
                link="https://www.linkedin.com/jobs/search/?currentJobId=3101",
                score=91,
            ),
            self._row(
                title="Canonical Engineer",
                link="https://www.linkedin.com/jobs/search/?currentJobId=3101&tracking=synthetic",
                score=84,
            ),
        ]

        _, recommendations = self._run_analyzer_and_recommend(rows)

        self.assertEqual(len(recommendations), 1)
        self.assertEqual(recommendations[0]["Title"], "Canonical Engineer")

    def test_malformed_scores_never_promote_even_when_threshold_is_zero(self):
        row = self._row(link="https://www.linkedin.com/jobs/view/4001/", score=90)
        malformed = []
        for score in ("not-a-score", "NaN", "Infinity", "", "90%%"):
            candidate = dict(row)
            candidate["Match Score"] = score
            malformed.append(candidate)
        self._write_analysis_stages(malformed)

        recommendations = self._read_recommendations(min_score=0)

        self.assertEqual(recommendations, [])

    def test_missing_optional_analysis_columns_remain_compatible(self):
        row = {
            "Title": "Synthetic Engineer",
            "Company": "Synthetic Employer",
            "Location": "Synthetic Region",
            "Match Score": "90%",
            "Application Eligible": "Yes",
            "Link": "https://www.linkedin.com/jobs/view/5001/",
        }
        self._write_analysis_stages([row], list(row))

        recommendations = self._read_recommendations()

        self.assertEqual([job["Title"] for job in recommendations], ["Synthetic Engineer"])

    def test_analysis_without_required_identity_or_eligibility_column_fails_closed(self):
        row = {
            "Title": "Synthetic Engineer",
            "Company": "Synthetic Employer",
            "Location": "Synthetic Region",
            "Match Score": "90%",
            "Application Eligible": "Yes",
            "Link": "https://www.linkedin.com/jobs/view/6001/",
        }
        self._write_analysis_stages([row], ["Title", "Company", "Location", "Match Score", "Application Eligible"])
        self.assertEqual(self._read_recommendations(), [])

        self._write_analysis_stages([row], ["Title", "Company", "Location", "Match Score", "Link"])
        self.assertEqual(self._read_recommendations(), [])

    def test_missing_required_details_header_and_malformed_row_are_rejected(self):
        valid = self._row(link="https://www.linkedin.com/jobs/view/7001/")
        missing_header = [field for field in self.DETAILS_FIELDS if field != "Description"]
        self._write_stages([valid], detail_fields=missing_header)
        with (
            patch.object(job_analyzer, "INPUT_FILE", str(self.details_file)),
            patch.object(job_analyzer, "OUTPUT_FILE", str(self.analysis_file)),
            self.assertRaises(ValueError),
        ):
            job_analyzer.analyze_jobs()

        self._write_stages([valid])
        with self.details_file.open("a", encoding="utf-8", newline="") as stream:
            stream.write('"too","few"\n')
        with (
            patch.object(job_analyzer, "INPUT_FILE", str(self.details_file)),
            patch.object(job_analyzer, "OUTPUT_FILE", str(self.analysis_file)),
            self.assertRaises(ValueError),
        ):
            job_analyzer.analyze_jobs()

    def test_empty_analysis_stage_fails_closed(self):
        self._write_stages([])
        self._write_csv(self.analysis_file, self.ANALYSIS_FIELDS, [])
        self.assertEqual(self._read_recommendations(), [])


if __name__ == "__main__":
    unittest.main()
