"""Offline tests for the production-diagnostic to canonical-evidence adapter."""

import ast
from pathlib import Path
import unittest
from unittest import mock

import job_search
from collection_diagnostics_adapter import adapt_collection_outcome
from collection_run_evidence import (
    CandidateDisposition,
    CandidateProcessingStatus,
    CandidateReason,
    CollectionStatus,
    SearchScope,
    classify_collection_run,
)


def diagnostic(
    keyword,
    scope_id,
    occurrences=(),
    *,
    location="Bengaluru",
    candidate_ids=None,
    attempted=True,
    **overrides,
):
    candidate_ids = (
        tuple(dict.fromkeys(item.candidate_id for item in occurrences))
        if candidate_ids is None
        else candidate_ids
    )
    fields = {
        "keyword": keyword,
        "location": location,
        "scope_id": scope_id,
        "scope_sequence": int(scope_id.rsplit("-", 1)[-1]),
        "search_attempted": attempted,
        "candidate_ids": candidate_ids,
        "candidate_occurrences": tuple(occurrences),
        "extracted_link_count": len(candidate_ids),
        "per_search_cap_reached": False,
        "global_cap_reached": False,
    }
    fields.update(overrides)
    return job_search.SearchDiagnostic(**fields)


def occurrence(candidate_id, sequence, *, status="PROCESSED", disposition="QUALIFYING", reason=None, **overrides):
    fields = {
        "candidate_id": candidate_id,
        "discovery_sequence": sequence,
        "selector": "fixture-selector",
        "processing_status": status,
        "disposition": disposition,
        "reason_code": reason,
    }
    fields.update(overrides)
    return job_search.CandidateOccurrenceDiagnostic(**fields)


def outcome(*diagnostics, status=job_search.CollectionStatus.UNKNOWN, issues=()):
    return job_search.CollectionOutcome(
        status=status,
        jobs=(),
        issues=issues,
        search_diagnostics=tuple(diagnostics),
    )


class CollectionDiagnosticsAdapterTests(unittest.TestCase):
    def adapt(self, result, scopes):
        return adapt_collection_outcome(result, tuple(scopes))

    def test_one_candidate_preserves_scope_and_order_but_remains_unknown(self):
        scope = SearchScope("backend", "Bengaluru", "scope-0001")
        source = diagnostic(
            "backend",
            "scope-0001",
            (occurrence("job-1", 1),),
        )
        evidence = self.adapt(outcome(source), (scope,))

        self.assertEqual(classify_collection_run(evidence), CollectionStatus.UNKNOWN)
        mapped = evidence.scopes[0].candidates[0]
        self.assertEqual(mapped.source_scope_id, scope.scope_id)
        self.assertEqual(mapped.discovery_sequence, 1)
        self.assertEqual(mapped.disposition, CandidateDisposition.QUALIFYING)
        self.assertIsNone(evidence.scopes[0].observed_scope)
        self.assertIsNone(evidence.scopes[0].results_settled)
        self.assertIsNone(evidence.scopes[0].pagination)

    def test_same_candidate_across_scopes_is_retained_and_not_inherited(self):
        first_scope = SearchScope("backend", "Bengaluru", "scope-0001")
        second_scope = SearchScope("platform", "Bengaluru", "scope-0002")
        first = diagnostic("backend", "scope-0001", (occurrence("job-1", 1),))
        second = diagnostic(
            "platform",
            "scope-0002",
            (occurrence(
                "job-1",
                1,
                status="DUPLICATE",
                disposition="DUPLICATE",
                reason="DUPLICATE_ACROSS_SCOPES",
                duplicate_of_scope_id="scope-0001",
                duplicate_of_sequence=1,
            ),),
        )
        evidence = self.adapt(outcome(first, second), (first_scope, second_scope))

        self.assertEqual(len(evidence.scopes[0].candidates), 1)
        self.assertEqual(len(evidence.scopes[1].candidates), 1)
        duplicate = evidence.scopes[1].candidates[0]
        self.assertEqual(duplicate.disposition, CandidateDisposition.UNPROCESSED)
        self.assertEqual(duplicate.processing_status, CandidateProcessingStatus.PENDING)
        self.assertEqual(duplicate.reason, CandidateReason.DUPLICATE_ACROSS_SCOPES)
        self.assertTrue(duplicate.output_deduplicated)
        self.assertEqual(duplicate.output_duplicate_of_scope_id, first_scope.scope_id)
        self.assertEqual(duplicate.output_duplicate_of_sequence, 1)
        self.assertEqual(classify_collection_run(evidence), CollectionStatus.INCOMPLETE)

    def test_contradictory_cross_scope_duplicate_status_is_unknown(self):
        scopes = (
            SearchScope("backend", "Bengaluru", "scope-0001"),
            SearchScope("platform", "Bengaluru", "scope-0002"),
        )
        first = diagnostic("backend", "scope-0001", (occurrence("job-1", 1),))
        contradictory = diagnostic(
            "platform", "scope-0002",
            (occurrence("job-1", 1, status="PROCESSED", disposition="DUPLICATE",
                        reason="DUPLICATE_ACROSS_SCOPES", duplicate_of_scope_id="scope-0001",
                        duplicate_of_sequence=1),),
        )
        evidence = self.adapt(outcome(first, contradictory), scopes)
        self.assertEqual(classify_collection_run(evidence), CollectionStatus.UNKNOWN)

    def test_multiple_overlapping_candidates_keep_each_scope_occurrence(self):
        scopes = (
            SearchScope("backend", "Bengaluru", "scope-0001"),
            SearchScope("platform", "Bengaluru", "scope-0002"),
        )
        first = diagnostic(
            "backend", "scope-0001",
            (occurrence("job-a", 1), occurrence("job-b", 2)),
        )
        second = diagnostic(
            "platform", "scope-0002",
            (
                occurrence("job-a", 1, status="DUPLICATE", disposition="DUPLICATE",
                           reason="DUPLICATE_ACROSS_SCOPES", duplicate_of_scope_id="scope-0001",
                           duplicate_of_sequence=1),
                occurrence("job-b", 2, status="DUPLICATE", disposition="DUPLICATE",
                           reason="DUPLICATE_ACROSS_SCOPES", duplicate_of_scope_id="scope-0001",
                           duplicate_of_sequence=2),
            ),
        )
        evidence = self.adapt(outcome(first, second), scopes)

        self.assertEqual(tuple(len(scope.candidates) for scope in evidence.scopes), (2, 2))
        self.assertEqual(
            tuple(item.candidate_id for item in evidence.scopes[1].candidates),
            ("job-a", "job-b"),
        )
        self.assertEqual(classify_collection_run(evidence), CollectionStatus.INCOMPLETE)

    def test_within_scope_duplicate_remains_explicit_and_not_processed(self):
        scope = SearchScope("backend", "Bengaluru", "scope-0001")
        source = diagnostic(
            "backend",
            "scope-0001",
            (
                occurrence("job-1", 1),
                occurrence("job-1", 2, status="DUPLICATE", disposition="DUPLICATE",
                           reason="DUPLICATE_WITHIN_SCOPE", duplicate_of_sequence=1),
            ),
        )
        evidence = self.adapt(outcome(source), (scope,))
        duplicate = evidence.scopes[0].candidates[1]

        self.assertEqual(duplicate.processing_status, CandidateProcessingStatus.DUPLICATE)
        self.assertNotEqual(duplicate.processing_status, CandidateProcessingStatus.PROCESSED)
        self.assertEqual(duplicate.reason, CandidateReason.DUPLICATE_WITHIN_SCOPE)
        self.assertEqual(evidence.scopes[0].candidate_identity_ids, ("job-1",))
        self.assertEqual(evidence.scopes[0].reported_candidate_identity_count, 1)

    def test_filtered_reason_and_missing_filter_evidence_are_preserved(self):
        scope = SearchScope("backend", "Bengaluru", "scope-0001")
        filtered = diagnostic(
            "backend", "scope-0001",
            (occurrence("job-1", 1, disposition="FILTERED", reason="NOT_EASY_APPLY"),),
        )
        evidence = self.adapt(outcome(filtered), (scope,))

        self.assertEqual(evidence.scopes[0].candidates[0].reason, CandidateReason.NOT_EASY_APPLY)
        self.assertIsNone(evidence.scopes[0].filters_applied)
        self.assertEqual(classify_collection_run(evidence), CollectionStatus.UNKNOWN)

    def test_filter_without_a_supported_reason_is_unknown(self):
        scope = SearchScope("backend", "Bengaluru", "scope-0001")
        source = diagnostic(
            "backend", "scope-0001",
            (occurrence("job-1", 1, disposition="FILTERED", reason=None),),
        )
        evidence = self.adapt(outcome(source), (scope,))
        self.assertEqual(classify_collection_run(evidence), CollectionStatus.UNKNOWN)

    def test_missing_disposition_or_malformed_candidate_data_is_unknown(self):
        scope = SearchScope("backend", "Bengaluru", "scope-0001")
        missing_disposition = diagnostic(
            "backend", "scope-0001",
            (occurrence("job-1", 1, status="UNKNOWN", disposition=None),),
        )
        malformed_id = diagnostic(
            "backend", "scope-0001",
            (occurrence(["not", "an", "id"], 1),),
            candidate_ids=("job-1",),
        )
        malformed_reason = diagnostic(
            "backend", "scope-0001",
            (occurrence("job-1", 1, disposition="FILTERED", reason="UNSUPPORTED"),),
        )
        unhashable_reason = diagnostic(
            "backend", "scope-0001",
            (occurrence("job-1", 1, disposition="FILTERED", reason=["invalid"]),),
        )

        for source in (missing_disposition, malformed_id, malformed_reason, unhashable_reason):
            with self.subTest(source=source):
                self.assertEqual(
                    classify_collection_run(self.adapt(outcome(source), (scope,))),
                    CollectionStatus.UNKNOWN,
                )

    def test_processing_failure_and_recorded_errors_are_incomplete(self):
        scope = SearchScope("backend", "Bengaluru", "scope-0001")
        failed = diagnostic(
            "backend", "scope-0001",
            (occurrence("job-1", 1, status="FAILED", disposition="FAILED_PROCESSING",
                        reason="PROCESSING_ERROR"),),
            candidate_page_failure_count=1,
        )
        evidence = self.adapt(outcome(failed, issues=("candidate processing failed",)), (scope,))
        self.assertEqual(classify_collection_run(evidence), CollectionStatus.INCOMPLETE)

    def test_unattempted_scope_and_missing_requested_scope_are_incomplete(self):
        first_scope = SearchScope("backend", "Bengaluru", "scope-0001")
        second_scope = SearchScope("platform", "Bengaluru", "scope-0002")
        first = diagnostic("backend", "scope-0001", (), attempted=True)
        skipped = diagnostic(
            "platform", "scope-0002", (), attempted=False,
            skip_reason="GLOBAL_RESULT_CAP_REACHED", global_cap_reached=True,
        )
        evidence = self.adapt(outcome(first, skipped), (first_scope, second_scope))
        missing = self.adapt(outcome(first), (first_scope, second_scope))

        self.assertEqual(classify_collection_run(evidence), CollectionStatus.INCOMPLETE)
        self.assertEqual(classify_collection_run(missing), CollectionStatus.INCOMPLETE)

    def test_duplicate_or_unexpected_scope_records_do_not_complete(self):
        requested = SearchScope("backend", "Bengaluru", "scope-0001")
        first = diagnostic("backend", "scope-0001", ())
        duplicate = diagnostic("backend", "scope-0001", ())
        unexpected = diagnostic("platform", "scope-0002", ())

        self.assertEqual(
            classify_collection_run(self.adapt(outcome(first, duplicate), (requested,))),
            CollectionStatus.UNKNOWN,
        )
        self.assertEqual(
            classify_collection_run(self.adapt(outcome(first, unexpected), (requested,))),
            CollectionStatus.UNKNOWN,
        )

    def test_candidate_identity_count_or_id_mismatch_is_unknown(self):
        scope = SearchScope("backend", "Bengaluru", "scope-0001")
        candidate = occurrence("job-1", 1)
        mismatch = diagnostic(
            "backend", "scope-0001", (candidate,), candidate_ids=("job-other",),
        )
        count_mismatch = diagnostic(
            "backend", "scope-0001", (candidate,), extracted_link_count=2,
        )
        for source in (mismatch, count_mismatch):
            with self.subTest(source=source):
                evidence = self.adapt(outcome(source), (scope,))
                self.assertEqual(classify_collection_run(evidence), CollectionStatus.UNKNOWN)

    def test_caps_are_observed_without_establishing_exhaustion(self):
        scope = SearchScope("backend", "Bengaluru", "scope-0001")
        source = diagnostic(
            "backend", "scope-0001", (occurrence("job-1", 1),),
            per_search_cap_reached=True,
        )
        evidence = self.adapt(outcome(source), (scope,))
        self.assertTrue(evidence.scopes[0].cap_reached)
        self.assertIsNone(evidence.scopes[0].cap_stopped_before_exhaustion)
        self.assertEqual(classify_collection_run(evidence), CollectionStatus.UNKNOWN)

    def test_empty_links_do_not_create_legitimate_empty_evidence(self):
        scope = SearchScope("backend", "Bengaluru", "scope-0001")
        source = diagnostic("backend", "scope-0001", ())
        evidence = self.adapt(outcome(source), (scope,))
        self.assertIsNone(evidence.scopes[0].page_state)
        self.assertEqual(classify_collection_run(evidence), CollectionStatus.UNKNOWN)

    def test_fatal_outcome_maps_to_failed_and_malformed_inputs_fail_closed(self):
        scope = SearchScope("backend", "Bengaluru", "scope-0001")
        source = diagnostic("backend", "scope-0001", ())
        self.assertEqual(
            classify_collection_run(
                self.adapt(outcome(source, status=job_search.CollectionStatus.FAILED), (scope,))
            ),
            CollectionStatus.FAILED,
        )
        malformed = adapt_collection_outcome(object(), (scope,))
        self.assertEqual(classify_collection_run(malformed), CollectionStatus.UNKNOWN)

        claimed_complete = outcome(source, status=job_search.CollectionStatus.COMPLETE)
        self.assertEqual(
            classify_collection_run(self.adapt(claimed_complete, (scope,))),
            CollectionStatus.UNKNOWN,
        )

    def test_adapter_evidence_cannot_authorize_production_publication(self):
        scope = SearchScope("backend", "Bengaluru", "scope-0001")
        source = diagnostic("backend", "scope-0001", ())
        evidence = self.adapt(outcome(source), (scope,))
        with mock.patch.object(job_search, "_write_jobs_csv_atomically") as writer:
            self.assertFalse(job_search.publish_collection(evidence, "unused.csv"))
        writer.assert_not_called()

    def test_adapter_source_has_no_production_browser_or_network_imports(self):
        source_path = Path(__file__).resolve().parents[1] / "collection_diagnostics_adapter.py"
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        self.assertEqual(imported, {"collection_run_evidence"})


if __name__ == "__main__":
    unittest.main()
