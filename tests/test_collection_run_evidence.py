"""Synthetic offline tests for multi-scope collection evidence policy."""

import ast
from pathlib import Path
import unittest

from collection_run_evidence import (
    CandidateDisposition,
    CandidateEvidence,
    CollectionRunEvidence,
    CollectionStatus,
    ScopeEvidence,
    SearchScope,
    classify_collection_run,
    classify_scope_evidence,
)


def complete_scope(keyword="engineer", location="remote", candidates=None):
    candidates = candidates if candidates is not None else (
        CandidateEvidence("job-1", CandidateDisposition.QUALIFYING),
    )
    qualifying_count = sum(
        candidate.disposition is CandidateDisposition.QUALIFYING
        for candidate in candidates
    )
    return ScopeEvidence(
        scope=SearchScope(keyword, location),
        identity_verified=True,
        results_settled=True,
        exhaustion_verified=True,
        filters_applied=True,
        cap_reached=False,
        cap_stopped_before_exhaustion=False,
        discovered_candidate_count=len(candidates),
        qualifying_candidate_count=qualifying_count,
        candidates=tuple(candidates),
    )


def complete_run(*scopes, requested_scopes=None, **overrides):
    if requested_scopes is None:
        requested_scopes = tuple(scope.scope for scope in scopes)
    values = {
        "requested_scopes": tuple(requested_scopes),
        "scopes": tuple(scopes),
        "fatal_failure": False,
        "unresolved_error_count": 0,
    }
    values.update(overrides)
    return CollectionRunEvidence(**values)


class ScopeClassificationTests(unittest.TestCase):
    def test_complete_populated_and_complete_empty(self):
        populated = complete_scope()
        empty = complete_scope(
            keyword="none",
            candidates=(),
        )
        self.assertEqual(classify_scope_evidence(populated), CollectionStatus.COMPLETE)
        self.assertEqual(classify_scope_evidence(empty), CollectionStatus.COMPLETE_EMPTY)

    def test_fatal_failure_precedes_errors_and_missing_evidence(self):
        evidence = ScopeEvidence(
            scope=SearchScope("engineer", "remote"),
            fatal_failure=True,
            unresolved_error_count=2,
            exhaustion_verified=None,
        )
        self.assertEqual(classify_scope_evidence(evidence), CollectionStatus.FAILED)

    def test_known_errors_and_unprocessed_candidates_are_incomplete(self):
        with_error = complete_scope()
        with_error = ScopeEvidence(**{**with_error.__dict__, "unresolved_error_count": 1})
        unprocessed = complete_scope(
            candidates=(CandidateEvidence("job-1", CandidateDisposition.UNPROCESSED),)
        )
        self.assertEqual(classify_scope_evidence(with_error), CollectionStatus.INCOMPLETE)
        self.assertEqual(classify_scope_evidence(unprocessed), CollectionStatus.INCOMPLETE)

    def test_false_required_evidence_and_known_premature_cap_are_incomplete(self):
        unsettled = ScopeEvidence(**{**complete_scope().__dict__, "results_settled": False})
        capped = ScopeEvidence(
            **{
                **complete_scope().__dict__,
                "cap_reached": True,
                "cap_stopped_before_exhaustion": True,
                "exhaustion_verified": False,
            }
        )
        self.assertEqual(classify_scope_evidence(unsettled), CollectionStatus.INCOMPLETE)
        self.assertEqual(classify_scope_evidence(capped), CollectionStatus.INCOMPLETE)

    def test_missing_or_unverified_evidence_is_unknown(self):
        missing_disposition = complete_scope(
            candidates=(CandidateEvidence("job-1", None),)
        )
        missing_cap_timing = ScopeEvidence(
            **{**complete_scope().__dict__, "cap_reached": True, "cap_stopped_before_exhaustion": None}
        )
        missing_count = ScopeEvidence(
            **{**complete_scope().__dict__, "discovered_candidate_count": None}
        )
        for evidence in (missing_disposition, missing_cap_timing, missing_count):
            with self.subTest(evidence=evidence):
                self.assertEqual(classify_scope_evidence(evidence), CollectionStatus.UNKNOWN)

    def test_malformed_disposition_is_controlled_unknown(self):
        evidence = complete_scope(
            candidates=(CandidateEvidence("job-1", ["invalid"]),)
        )
        self.assertEqual(classify_scope_evidence(evidence), CollectionStatus.UNKNOWN)

    def test_duplicate_candidate_ids_and_contradictory_counts_are_unknown(self):
        duplicate = complete_scope(
            candidates=(
                CandidateEvidence("same", CandidateDisposition.QUALIFYING),
                CandidateEvidence("same", CandidateDisposition.FILTERED),
            )
        )
        count_mismatch = ScopeEvidence(
            **{**complete_scope().__dict__, "qualifying_candidate_count": 0}
        )
        too_many_records = ScopeEvidence(
            **{**complete_scope().__dict__, "discovered_candidate_count": 0}
        )
        for evidence in (duplicate, count_mismatch, too_many_records):
            with self.subTest(evidence=evidence):
                self.assertEqual(classify_scope_evidence(evidence), CollectionStatus.UNKNOWN)

    def test_unaccounted_discovered_candidates_are_incomplete(self):
        evidence = ScopeEvidence(
            **{**complete_scope().__dict__, "discovered_candidate_count": 2}
        )
        self.assertEqual(classify_scope_evidence(evidence), CollectionStatus.INCOMPLETE)

    def test_filters_must_be_accounted_for_and_filtered_candidates_are_not_qualifying(self):
        unfiltered = ScopeEvidence(**{**complete_scope().__dict__, "filters_applied": False})
        filtered_empty = complete_scope(
            candidates=(CandidateEvidence("job-1", CandidateDisposition.FILTERED),)
        )
        self.assertEqual(classify_scope_evidence(unfiltered), CollectionStatus.INCOMPLETE)
        self.assertEqual(classify_scope_evidence(filtered_empty), CollectionStatus.COMPLETE_EMPTY)

    def test_cap_and_exhaustion_contradiction_is_unknown(self):
        evidence = ScopeEvidence(
            **{
                **complete_scope().__dict__,
                "cap_reached": True,
                "cap_stopped_before_exhaustion": True,
                "exhaustion_verified": True,
            }
        )
        self.assertEqual(classify_scope_evidence(evidence), CollectionStatus.UNKNOWN)


class CollectionRunAggregationTests(unittest.TestCase):
    def test_all_complete_scopes_aggregate_populated(self):
        one = complete_scope("engineer", "remote")
        two = complete_scope("developer", "Bengaluru")
        self.assertEqual(classify_collection_run(complete_run(one, two)), CollectionStatus.COMPLETE)

    def test_all_verified_empty_scopes_aggregate_empty(self):
        one = complete_scope("engineer", "remote", candidates=())
        two = complete_scope("developer", "Bengaluru", candidates=(
            CandidateEvidence("job-2", CandidateDisposition.FILTERED),
        ))
        self.assertEqual(
            classify_collection_run(complete_run(one, two)),
            CollectionStatus.COMPLETE_EMPTY,
        )

    def test_one_qualifying_scope_makes_aggregate_populated(self):
        populated = complete_scope("engineer", "remote")
        empty = complete_scope("developer", "Bengaluru", candidates=())
        self.assertEqual(
            classify_collection_run(complete_run(populated, empty)),
            CollectionStatus.COMPLETE,
        )

    def test_missing_requested_scope_is_incomplete(self):
        present = complete_scope()
        missing = SearchScope("developer", "Bengaluru")
        run = complete_run(present, requested_scopes=(present.scope, missing))
        self.assertEqual(classify_collection_run(run), CollectionStatus.INCOMPLETE)

    def test_missing_scope_precedes_unrelated_malformed_scope_evidence(self):
        present = complete_scope()
        missing = SearchScope("developer", "Bengaluru")
        run = CollectionRunEvidence(
            requested_scopes=(present.scope, missing),
            scopes=(present, object()),
            unresolved_error_count="not-counted",
        )
        self.assertEqual(classify_collection_run(run), CollectionStatus.INCOMPLETE)

    def test_duplicate_requested_or_observed_scopes_are_unknown(self):
        scope = complete_scope()
        duplicate_request = complete_run(scope, requested_scopes=(scope.scope, scope.scope))
        duplicate_observation = complete_run(scope, scope)
        self.assertEqual(classify_collection_run(duplicate_request), CollectionStatus.UNKNOWN)
        self.assertEqual(classify_collection_run(duplicate_observation), CollectionStatus.UNKNOWN)

    def test_unexpected_scope_is_unknown(self):
        requested = SearchScope("engineer", "remote")
        requested_evidence = complete_scope("engineer", "remote")
        unexpected = complete_scope("developer", "Bengaluru")
        run = complete_run(
            requested_evidence,
            unexpected,
            requested_scopes=(requested,),
        )
        self.assertEqual(classify_collection_run(run), CollectionStatus.UNKNOWN)

    def test_successful_scope_never_overrides_incomplete_or_unknown_scope(self):
        complete = complete_scope()
        incomplete = ScopeEvidence(
            **{**complete_scope("developer", "Bengaluru").__dict__, "exhaustion_verified": False}
        )
        unknown = ScopeEvidence(
            **{**complete_scope("developer", "Bengaluru").__dict__, "exhaustion_verified": None}
        )
        self.assertEqual(
            classify_collection_run(complete_run(complete, incomplete)),
            CollectionStatus.INCOMPLETE,
        )
        self.assertEqual(
            classify_collection_run(complete_run(complete, unknown)),
            CollectionStatus.UNKNOWN,
        )

    def test_fatal_failure_precedes_known_errors_and_unknown_scopes(self):
        fatal = ScopeEvidence(scope=SearchScope("developer", "Bengaluru"), fatal_failure=True)
        run = complete_run(
            complete_scope(),
            fatal,
            unresolved_error_count=3,
            fatal_failure=False,
        )
        self.assertEqual(classify_collection_run(run), CollectionStatus.FAILED)
        self.assertEqual(
            classify_collection_run(
                CollectionRunEvidence((), (), fatal_failure=True, unresolved_error_count=5)
            ),
            CollectionStatus.FAILED,
        )

    def test_malformed_run_fatal_flag_cannot_produce_complete(self):
        scope = complete_scope()
        malformed = complete_run(scope, fatal_failure=1)
        malformed_with_error = complete_run(
            scope,
            fatal_failure=1,
            unresolved_error_count=1,
        )
        self.assertEqual(classify_collection_run(malformed), CollectionStatus.UNKNOWN)
        self.assertEqual(
            classify_collection_run(malformed_with_error),
            CollectionStatus.INCOMPLETE,
        )

    def test_errors_and_known_incomplete_precede_unknown_evidence(self):
        complete = complete_scope()
        unknown = ScopeEvidence(scope=SearchScope("developer", "Bengaluru"))
        run_error = complete_run(complete, unresolved_error_count=1)
        mixed = complete_run(
            complete,
            unknown,
            requested_scopes=(complete.scope,),
            unresolved_error_count=1,
        )
        self.assertEqual(classify_collection_run(run_error), CollectionStatus.INCOMPLETE)
        self.assertEqual(classify_collection_run(mixed), CollectionStatus.INCOMPLETE)

    def test_empty_or_malformed_run_is_unknown(self):
        self.assertEqual(classify_collection_run(CollectionRunEvidence((), ())), CollectionStatus.UNKNOWN)
        self.assertEqual(classify_collection_run(None), CollectionStatus.UNKNOWN)

    def test_model_has_no_production_workflow_imports(self):
        module_path = Path(__file__).parents[1] / "collection_run_evidence.py"
        tree = ast.parse(module_path.read_text(encoding="utf-8"))
        imported_roots = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_roots.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_roots.add(node.module.split(".")[0])
        forbidden = {
            "job_search", "route_audit", "easy_apply", "external_app",
            "offline_search_evidence", "search_page_evidence", "playwright",
            "requests", "urllib", "subprocess",
        }
        self.assertFalse(imported_roots & forbidden)


if __name__ == "__main__":
    unittest.main()
