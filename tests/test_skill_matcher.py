import unittest
from unittest.mock import patch

import skill_matcher


class SkillMatcherTests(unittest.TestCase):
    def test_exact_known_skills_are_matched_with_full_score(self):
        with patch.object(
            skill_matcher,
            "canonical_resume_skills",
            {"java", "spring", "spring boot"},
        ):
            score, matched, missing = skill_matcher.match_resume(
                "Java and Spring Boot experience required."
            )

        self.assertEqual(score, 100)
        self.assertEqual(matched, {"java", "spring", "spring boot"})
        self.assertEqual(missing, set())

    def test_case_and_whitespace_are_normalized(self):
        with patch.object(skill_matcher, "canonical_resume_skills", {"java"}):
            score, matched, missing = skill_matcher.match_resume("  JAVA\n java  ")

        self.assertEqual(score, 100)
        self.assertEqual(matched, {"java"})
        self.assertEqual(missing, set())

    def test_unmatched_skills_are_reported_as_missing(self):
        with patch.object(skill_matcher, "canonical_resume_skills", {"java"}):
            score, matched, missing = skill_matcher.match_resume(
                "Java and Kubernetes are required."
            )

        self.assertEqual(matched, {"java"})
        self.assertEqual(missing, {"kubernetes"})
        self.assertGreater(score, 0)
        self.assertLess(score, 100)

    def test_category_weighting_is_used_for_core_supporting_and_optional_skills(self):
        with patch.object(
            skill_matcher,
            "canonical_resume_skills",
            {"java", "docker", "python"},
        ):
            score, matched, missing = skill_matcher.match_resume(
                "Java, Docker, and Python required."
            )

        self.assertEqual(score, 100)
        self.assertEqual(matched, {"java", "docker", "python"})
        self.assertEqual(missing, set())
        self.assertEqual(skill_matcher.skill_category("java"), "core")
        self.assertEqual(skill_matcher.skill_category("docker"), "supporting")
        self.assertEqual(skill_matcher.skill_category("python"), "optional")

    def test_core_supporting_and_optional_categories_have_distinct_score_influence(self):
        with patch.object(skill_matcher, "canonical_resume_skills", {"java"}):
            core_match_score, _, _ = skill_matcher.match_resume("Java and Docker required.")
        with patch.object(skill_matcher, "canonical_resume_skills", {"docker"}):
            supporting_match_score, _, _ = skill_matcher.match_resume("Java and Docker required.")
        with patch.object(skill_matcher, "canonical_resume_skills", {"docker"}):
            supporting_only_score, _, _ = skill_matcher.match_resume("Docker and Python required.")
        with patch.object(skill_matcher, "canonical_resume_skills", {"python"}):
            optional_only_score, _, _ = skill_matcher.match_resume("Docker and Python required.")

        self.assertGreater(core_match_score, supporting_match_score)
        self.assertGreater(supporting_only_score, optional_only_score)
        self.assertEqual((core_match_score, supporting_match_score), (90, 21))
        self.assertEqual((supporting_only_score, optional_only_score), (79, 21))

    def test_empty_or_sparse_text_returns_zero_and_empty_sets(self):
        for text in ("", "   \n", "No matching technical terms here."):
            with self.subTest(text=text):
                self.assertEqual(skill_matcher.match_resume(text), (0, set(), set()))

    def test_duplicate_mentions_count_once(self):
        with patch.object(skill_matcher, "canonical_resume_skills", {"java"}):
            result = skill_matcher.match_resume("Java, JAVA, Java")

        self.assertEqual(result, (100, {"java"}, set()))

    def test_unrecognized_malformed_values_fail_to_empty_match(self):
        for value in (None, 123, object()):
            with self.subTest(value_type=type(value).__name__):
                self.assertEqual(skill_matcher.match_resume(value), (0, set(), set()))

    def test_reported_sets_are_disjoint_and_account_for_extracted_skills(self):
        with patch.object(skill_matcher, "canonical_resume_skills", {"java", "sql"}):
            score, matched, missing = skill_matcher.match_resume(
                "Java, SQL, and Kubernetes are used."
            )

        extracted = skill_matcher.extract_job_skills(
            "Java, SQL, and Kubernetes are used."
        )
        self.assertTrue(0 <= score <= 100)
        self.assertIsInstance(score, int)
        self.assertTrue(matched.isdisjoint(missing))
        self.assertEqual(matched | missing, extracted)


if __name__ == "__main__":
    unittest.main()
