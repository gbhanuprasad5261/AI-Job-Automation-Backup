"""Offline tests for the conservative collection-evidence policy boundary."""

from dataclasses import fields
import tempfile
import unittest
from pathlib import Path

import job_search
from search_page_evidence import EvidenceCompletionStatus


def complete_single_scope_evidence(**overrides):
    values = {
        "fatal_failure": False,
        "unresolved_error_count": 0,
        "requested_scope_verified": True,
        "expected_search_state_verified": True,
        "results_settled": True,
        "exhaustion_verified": True,
        "required_processing_succeeded": True,
        "filters_applied": True,
        "cap_reached": False,
        "cap_stopped_before_exhaustion": False,
        "candidate_count": 2,
        "processed_candidate_count": 2,
        "qualifying_job_count": 1,
    }
    values.update(overrides)
    return job_search.CollectionEvidence(**values)


class CollectionEvidencePolicySpecificationTests(unittest.TestCase):
    def test_fatal_failure_precedes_unresolved_and_missing_evidence(self):
        evidence = complete_single_scope_evidence(
            fatal_failure=True,
            unresolved_error_count=5,
            requested_scope_verified=None,
        )
        self.assertEqual(
            job_search.classify_collection_evidence(evidence),
            job_search.CollectionStatus.FAILED,
        )

    def test_known_unfinished_work_precedes_missing_evidence(self):
        evidence = complete_single_scope_evidence(
            unresolved_error_count=1,
            exhaustion_verified=None,
        )
        self.assertEqual(
            job_search.classify_collection_evidence(evidence),
            job_search.CollectionStatus.INCOMPLETE,
        )

    def test_missing_or_contradictory_evidence_is_unknown(self):
        missing = complete_single_scope_evidence(exhaustion_verified=None)
        contradictory = complete_single_scope_evidence(
            candidate_count=1,
            processed_candidate_count=2,
        )
        for evidence in (missing, contradictory):
            with self.subTest(evidence=evidence):
                self.assertEqual(
                    job_search.classify_collection_evidence(evidence),
                    job_search.CollectionStatus.UNKNOWN,
                )

    def test_known_unsettled_or_unexhausted_scope_is_incomplete(self):
        for override in (
            {"results_settled": False},
            {"exhaustion_verified": False},
            {"required_processing_succeeded": False},
            {"filters_applied": False},
        ):
            with self.subTest(override=override):
                self.assertEqual(
                    job_search.classify_collection_evidence(
                        complete_single_scope_evidence(**override)
                    ),
                    job_search.CollectionStatus.INCOMPLETE,
                )

    def test_unknown_scope_evidence_remains_unknown(self):
        for override in (
            {"requested_scope_verified": None},
            {"expected_search_state_verified": None},
            {"results_settled": None},
            {"exhaustion_verified": None},
            {"required_processing_succeeded": None},
            {"filters_applied": None},
            {"candidate_count": None},
            {"processed_candidate_count": None},
            {"qualifying_job_count": None},
        ):
            with self.subTest(override=override):
                self.assertEqual(
                    job_search.classify_collection_evidence(
                        complete_single_scope_evidence(**override)
                    ),
                    job_search.CollectionStatus.UNKNOWN,
                )

    def test_cap_before_verified_exhaustion_is_incomplete(self):
        evidence = complete_single_scope_evidence(
            cap_reached=True,
            cap_stopped_before_exhaustion=True,
            exhaustion_verified=False,
        )
        self.assertEqual(
            job_search.classify_collection_evidence(evidence),
            job_search.CollectionStatus.INCOMPLETE,
        )

    def test_cap_after_independently_verified_exhaustion_can_be_complete(self):
        evidence = complete_single_scope_evidence(
            cap_reached=True,
            cap_stopped_before_exhaustion=False,
            exhaustion_verified=True,
        )
        self.assertEqual(
            job_search.classify_collection_evidence(evidence),
            job_search.CollectionStatus.COMPLETE,
        )

    def test_only_all_processed_qualifying_count_controls_empty_classification(self):
        empty = complete_single_scope_evidence(
            candidate_count=0,
            processed_candidate_count=0,
            qualifying_job_count=0,
        )
        filtered_empty = complete_single_scope_evidence(
            qualifying_job_count=0,
            filters_applied=True,
        )
        self.assertEqual(
            job_search.classify_collection_evidence(empty),
            job_search.CollectionStatus.COMPLETE_EMPTY,
        )
        self.assertEqual(
            job_search.classify_collection_evidence(filtered_empty),
            job_search.CollectionStatus.COMPLETE_EMPTY,
        )

    def test_current_model_cannot_classify_multiple_scopes_or_dispositions(self):
        evidence_fields = {item.name for item in fields(job_search.CollectionEvidence)}
        self.assertNotIn("scopes", evidence_fields)
        self.assertNotIn("candidate_dispositions", evidence_fields)
        self.assertNotIn("filter_dispositions", evidence_fields)

        complete = complete_single_scope_evidence()
        incomplete = complete_single_scope_evidence(exhaustion_verified=False)
        unknown = complete_single_scope_evidence(exhaustion_verified=None)
        scope_cases = {
            "all complete": (complete, complete),
            "all complete empty": (
                complete_single_scope_evidence(
                    candidate_count=0,
                    processed_candidate_count=0,
                    qualifying_job_count=0,
                ),
            ),
            "one incomplete": (complete, incomplete),
            "one unknown": (complete, unknown),
            "mixed incomplete and unknown": (incomplete, unknown),
        }
        for label, scopes in scope_cases.items():
            with self.subTest(scope_case=label):
                self.assertEqual(
                    job_search.classify_collection_evidence(scopes),
                    job_search.CollectionStatus.UNKNOWN,
                )

    def test_fixture_completion_status_is_always_unknown(self):
        self.assertEqual(
            tuple(EvidenceCompletionStatus),
            (EvidenceCompletionStatus.UNKNOWN,),
        )

    def test_policy_verified_statuses_use_existing_temp_csv_gate(self):
        row = {
            "Title": "Synthetic role",
            "Company": "Synthetic company",
            "Location": "Synthetic location",
            "Easy Apply": "No",
            "Actively Reviewing": "No",
            "Link": "https://example.invalid/job/1",
        }
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "jobs.csv"
            original = b"original bytes\r\n"
            output.write_bytes(original)

            complete_status = job_search.classify_collection_evidence(
                complete_single_scope_evidence()
            )
            complete_outcome = job_search.CollectionOutcome(complete_status, (row,))
            self.assertTrue(job_search.publish_collection(complete_outcome, output))
            self.assertNotEqual(output.read_bytes(), original)

            output.write_bytes(original)
            unknown_status = job_search.classify_collection_evidence(
                complete_single_scope_evidence(exhaustion_verified=None)
            )
            unknown_outcome = job_search.CollectionOutcome(unknown_status, (row,))
            self.assertFalse(job_search.publish_collection(unknown_outcome, output))
            self.assertEqual(output.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
