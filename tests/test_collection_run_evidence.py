"""Synthetic offline tests for multi-scope collection evidence policy."""

import ast
from dataclasses import replace
from pathlib import Path
import unittest

from collection_run_evidence import (
    CandidateDisposition,
    CandidateEvidence,
    CandidateProcessingStatus,
    CandidateReason,
    CollectionRunEvidence,
    CollectionStatus,
    PageEvidenceState,
    PaginationBatchEvidence,
    PaginationBatchStatus,
    PaginationEvidence,
    PaginationState,
    ScopeEvidence,
    SearchScope,
    classify_collection_run,
    classify_pagination_evidence,
    classify_scope_evidence,
)


def complete_scope(keyword="engineer", location="remote", candidates=None):
    candidates = candidates if candidates is not None else (
        CandidateEvidence("job-1", CandidateDisposition.QUALIFYING),
    )
    scope = SearchScope(keyword, location, f"scope:{keyword.strip().casefold()}:{location.strip().casefold()}")
    normalized_candidates = []
    prior_ids = {}
    for sequence, candidate in enumerate(candidates, start=1):
        status = candidate.processing_status
        if status is None and isinstance(candidate.disposition, CandidateDisposition):
            status = {
                CandidateDisposition.QUALIFYING: CandidateProcessingStatus.PROCESSED,
                CandidateDisposition.FILTERED: CandidateProcessingStatus.PROCESSED,
                CandidateDisposition.UNPROCESSED: CandidateProcessingStatus.PENDING,
                CandidateDisposition.FAILED_PROCESSING: CandidateProcessingStatus.FAILED,
                CandidateDisposition.DUPLICATE: CandidateProcessingStatus.DUPLICATE,
                CandidateDisposition.UNKNOWN: CandidateProcessingStatus.UNKNOWN,
            }.get(candidate.disposition)
        duplicate_of = candidate.duplicate_of_sequence
        reason = candidate.reason
        if candidate.disposition is CandidateDisposition.DUPLICATE:
            duplicate_of = duplicate_of or prior_ids.get(candidate.candidate_id)
            reason = reason or CandidateReason.DUPLICATE_WITHIN_SCOPE
        normalized = replace(
            candidate,
            source_scope_id=candidate.source_scope_id or scope.scope_id,
            discovery_sequence=candidate.discovery_sequence or sequence,
            processing_status=status,
            duplicate_of_sequence=duplicate_of,
            reason=reason,
        )
        normalized_candidates.append(normalized)
        prior_ids.setdefault(candidate.candidate_id, sequence)
    candidates = tuple(normalized_candidates)
    qualifying_count = sum(
        candidate.disposition is CandidateDisposition.QUALIFYING
        for candidate in candidates
    )
    return ScopeEvidence(
        scope=scope,
        observed_scope=scope,
        identity_evidence_refs=("identity",),
        identity_basis="direct_observation",
        page_state=(
            PageEvidenceState.LEGITIMATE_EMPTY
            if not candidates
            else PageEvidenceState.POPULATED_RESULTS_SETTLED
        ),
        page_state_evidence_refs=("page-state",),
        page_state_basis="direct_observation",
        pagination=PaginationEvidence(
            batches=(
                PaginationBatchEvidence(
                    1,
                    PaginationBatchStatus.OBSERVED,
                    False,
                    ("batch-1",),
                    ("terminal-1",),
                ),
            ),
            cap_reached=False,
            cap_prevented_exhaustion=False,
        ),
        identity_verified=True,
        results_settled=True,
        exhaustion_verified=True,
        filters_applied=True,
        cap_reached=False,
        cap_stopped_before_exhaustion=False,
        discovered_candidate_count=len(candidates),
        qualifying_candidate_count=qualifying_count,
        candidates=candidates,
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


class PaginationEvidenceTests(unittest.TestCase):
    def batch(self, sequence, more, *, terminal=(), status=PaginationBatchStatus.OBSERVED):
        return PaginationBatchEvidence(
            sequence=sequence,
            status=status,
            more_indicated=more,
            evidence_refs=(f"batch-{sequence}",),
            terminal_evidence_refs=tuple(terminal),
        )

    def test_contiguous_batches_and_explicit_terminal_are_verified(self):
        evidence = PaginationEvidence(
            (self.batch(1, True), self.batch(2, False, terminal=("terminal",))),
            cap_reached=False,
            cap_prevented_exhaustion=False,
        )
        self.assertEqual(
            classify_pagination_evidence(evidence),
            PaginationState.TERMINAL_VERIFIED,
        )

    def test_more_batch_indication_is_incomplete(self):
        evidence = PaginationEvidence(
            (self.batch(1, True),), False, False
        )
        self.assertEqual(classify_pagination_evidence(evidence), PaginationState.INCOMPLETE)

    def test_missing_sequence_is_incomplete(self):
        evidence = PaginationEvidence(
            (self.batch(1, True), self.batch(3, False, terminal=("terminal",))),
            False,
            False,
        )
        self.assertEqual(classify_pagination_evidence(evidence), PaginationState.INCOMPLETE)

    def test_duplicate_sequence_is_unknown(self):
        evidence = PaginationEvidence(
            (self.batch(1, True), self.batch(1, False, terminal=("terminal",))),
            False,
            False,
        )
        self.assertEqual(classify_pagination_evidence(evidence), PaginationState.UNKNOWN)

    def test_missing_terminal_reference_is_unknown(self):
        evidence = PaginationEvidence((self.batch(1, False),), False, False)
        self.assertEqual(classify_pagination_evidence(evidence), PaginationState.UNKNOWN)

    def test_cap_that_prevents_exhaustion_is_incomplete(self):
        evidence = PaginationEvidence(
            (self.batch(1, False, terminal=("terminal",)),), True, True
        )
        self.assertEqual(classify_pagination_evidence(evidence), PaginationState.INCOMPLETE)

    def test_unknown_cap_effect_is_unknown(self):
        evidence = PaginationEvidence(
            (self.batch(1, False, terminal=("terminal",)),), True, None
        )
        self.assertEqual(classify_pagination_evidence(evidence), PaginationState.UNKNOWN)

    def test_failed_batch_is_incomplete(self):
        evidence = PaginationEvidence(
            (self.batch(1, None, status=PaginationBatchStatus.FAILED),), False, False
        )
        self.assertEqual(classify_pagination_evidence(evidence), PaginationState.INCOMPLETE)

    def test_malformed_sequence_or_contradictory_transition_is_unknown(self):
        malformed = PaginationEvidence((self.batch(True, False, terminal=("terminal",)),), False, False)
        self.assertEqual(classify_pagination_evidence(malformed), PaginationState.UNKNOWN)
        conflict = PaginationEvidence(
            (self.batch(1, False, terminal=("terminal",)), self.batch(2, False, terminal=("terminal-2",))),
            False,
            False,
        )
        self.assertEqual(classify_pagination_evidence(conflict), PaginationState.UNKNOWN)

    def test_nonterminal_batch_cannot_include_terminal_evidence(self):
        evidence = PaginationEvidence(
            (
                self.batch(1, True, terminal=("contradictory-terminal",)),
                self.batch(2, False, terminal=("terminal",)),
            ),
            cap_reached=False,
            cap_prevented_exhaustion=False,
        )

        self.assertEqual(classify_pagination_evidence(evidence), PaginationState.UNKNOWN)
        self.assertEqual(
            classify_scope_evidence(replace(complete_scope(), pagination=evidence)),
            CollectionStatus.UNKNOWN,
        )


class ScopeClassificationTests(unittest.TestCase):
    def test_complete_populated_and_complete_empty(self):
        populated = complete_scope()
        empty = complete_scope(
            keyword="none",
            candidates=(
                CandidateEvidence(
                    "filtered-job",
                    CandidateDisposition.FILTERED,
                    CandidateReason.OUTSIDE_TARGET_LOCATION,
                ),
            ),
        )
        self.assertEqual(classify_scope_evidence(populated), CollectionStatus.COMPLETE)
        self.assertEqual(classify_scope_evidence(empty), CollectionStatus.COMPLETE_EMPTY)

    def test_zero_candidates_require_verified_legitimate_empty_state(self):
        legitimate_empty = complete_scope("none", "remote", candidates=())
        exhaustion_only = replace(
            legitimate_empty,
            page_state=PageEvidenceState.EXHAUSTION_REVIEW_RECORDED,
        )

        self.assertEqual(
            classify_scope_evidence(exhaustion_only),
            CollectionStatus.UNKNOWN,
        )
        self.assertEqual(
            classify_collection_run(complete_run(exhaustion_only)),
            CollectionStatus.UNKNOWN,
        )
        self.assertEqual(
            classify_scope_evidence(legitimate_empty),
            CollectionStatus.COMPLETE_EMPTY,
        )

    def test_fatal_failure_precedes_errors_and_missing_evidence(self):
        evidence = ScopeEvidence(
            scope=SearchScope("engineer", "remote"),
            fatal_failure=True,
            unresolved_error_count=2,
            exhaustion_verified=None,
        )
        self.assertEqual(classify_scope_evidence(evidence), CollectionStatus.FAILED)

    def test_malformed_fatal_flag_is_unknown_without_known_incompleteness(self):
        for fatal_failure in (1, "true", None):
            with self.subTest(fatal_failure=fatal_failure):
                evidence = ScopeEvidence(
                    **{**complete_scope().__dict__, "fatal_failure": fatal_failure}
                )
                self.assertEqual(classify_scope_evidence(evidence), CollectionStatus.UNKNOWN)

    def test_malformed_fatal_flag_preserves_known_incomplete_precedence(self):
        for fatal_failure in (1, "true", None):
            for known_incomplete in (
                {"unresolved_error_count": 1},
                {"exhaustion_verified": False},
            ):
                with self.subTest(
                    fatal_failure=fatal_failure,
                    known_incomplete=known_incomplete,
                ):
                    evidence = ScopeEvidence(
                        **{
                            **complete_scope().__dict__,
                            "fatal_failure": fatal_failure,
                            **known_incomplete,
                        }
                    )
                    self.assertEqual(
                        classify_scope_evidence(evidence),
                        CollectionStatus.INCOMPLETE,
                    )

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
                CandidateEvidence(
                    "same",
                    CandidateDisposition.FILTERED,
                    CandidateReason.OUTSIDE_TARGET_LOCATION,
                ),
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

    def test_within_scope_duplicate_is_explicit_and_not_marked_processed(self):
        evidence = complete_scope(
            candidates=(
                CandidateEvidence("same", CandidateDisposition.QUALIFYING),
                CandidateEvidence("same", CandidateDisposition.DUPLICATE),
            )
        )
        duplicate = evidence.candidates[1]

        self.assertEqual(duplicate.processing_status, CandidateProcessingStatus.DUPLICATE)
        self.assertEqual(duplicate.reason, CandidateReason.DUPLICATE_WITHIN_SCOPE)
        self.assertNotEqual(duplicate.processing_status, CandidateProcessingStatus.PROCESSED)
        self.assertEqual(classify_scope_evidence(evidence), CollectionStatus.COMPLETE)

    def test_unaccounted_discovered_candidates_are_incomplete(self):
        evidence = ScopeEvidence(
            **{**complete_scope().__dict__, "discovered_candidate_count": 2}
        )
        self.assertEqual(classify_scope_evidence(evidence), CollectionStatus.INCOMPLETE)

    def test_filters_must_be_accounted_for_and_filtered_candidates_are_not_qualifying(self):
        unfiltered = ScopeEvidence(**{**complete_scope().__dict__, "filters_applied": False})
        filtered_empty = complete_scope(
            candidates=(
                CandidateEvidence(
                    "job-1",
                    CandidateDisposition.FILTERED,
                    CandidateReason.OUTSIDE_TARGET_LOCATION,
                ),
            )
        )
        self.assertEqual(classify_scope_evidence(unfiltered), CollectionStatus.INCOMPLETE)
        self.assertEqual(classify_scope_evidence(filtered_empty), CollectionStatus.COMPLETE_EMPTY)

    def test_filtered_candidates_require_a_valid_reason_code(self):
        missing_reason = complete_scope(
            candidates=(CandidateEvidence("job-1", CandidateDisposition.FILTERED),)
        )
        unsupported_reason = complete_scope(
            candidates=(
                CandidateEvidence(
                    "job-1", CandidateDisposition.FILTERED, CandidateReason.PROCESSING_ERROR
                ),
            )
        )
        qualifying_with_reason = complete_scope(
            candidates=(
                CandidateEvidence(
                    "job-1", CandidateDisposition.QUALIFYING, CandidateReason.CLOSED_JOB
                ),
            )
        )
        for evidence in (missing_reason, unsupported_reason, qualifying_with_reason):
            with self.subTest(evidence=evidence):
                self.assertEqual(classify_scope_evidence(evidence), CollectionStatus.UNKNOWN)

    def test_missing_or_malformed_filter_assertion_is_unknown(self):
        for filter_evidence in (None, 1, "true"):
            with self.subTest(filter_evidence=filter_evidence):
                evidence = ScopeEvidence(
                    **{**complete_scope().__dict__, "filters_applied": filter_evidence}
                )
                self.assertEqual(classify_scope_evidence(evidence), CollectionStatus.UNKNOWN)

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
            CandidateEvidence(
                "job-2",
                CandidateDisposition.FILTERED,
                CandidateReason.OUTSIDE_TARGET_LOCATION,
            ),
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

    def test_same_candidate_id_is_accounted_per_scope_without_global_deduplication(self):
        first = complete_scope("engineer", "remote", candidates=(
            CandidateEvidence("shared-job", CandidateDisposition.QUALIFYING),
        ))
        second = complete_scope("developer", "Bengaluru", candidates=(
            CandidateEvidence("shared-job", CandidateDisposition.QUALIFYING),
        ))

        self.assertEqual(classify_scope_evidence(first), CollectionStatus.COMPLETE)
        self.assertEqual(classify_scope_evidence(second), CollectionStatus.COMPLETE)
        self.assertEqual(first.discovered_candidate_count, 1)
        self.assertEqual(second.discovered_candidate_count, 1)
        self.assertEqual(
            classify_collection_run(complete_run(first, second)),
            CollectionStatus.COMPLETE,
        )

    def test_cross_scope_duplicate_remains_an_occurrence_and_is_incomplete(self):
        first = complete_scope(
            "engineer", "remote",
            candidates=(CandidateEvidence("shared", CandidateDisposition.QUALIFYING),),
        )
        second = complete_scope(
            "developer", "Bengaluru",
            candidates=(CandidateEvidence(
                "shared",
                CandidateDisposition.UNPROCESSED,
                CandidateReason.DUPLICATE_ACROSS_SCOPES,
                output_deduplicated=True,
                output_duplicate_of_scope_id=first.scope.scope_id,
                output_duplicate_of_sequence=1,
                processing_status=CandidateProcessingStatus.PENDING,
            ),),
        )

        self.assertEqual(len(first.candidates), 1)
        self.assertEqual(len(second.candidates), 1)
        self.assertEqual(second.candidates[0].source_scope_id, second.scope.scope_id)
        self.assertEqual(classify_scope_evidence(second), CollectionStatus.INCOMPLETE)
        self.assertEqual(classify_collection_run(complete_run(first, second)), CollectionStatus.INCOMPLETE)

    def test_cross_scope_duplicate_with_wrong_target_remains_incomplete(self):
        first = complete_scope(
            "engineer", "remote",
            candidates=(CandidateEvidence("shared", CandidateDisposition.QUALIFYING),),
        )
        base = complete_scope(
            "developer", "Bengaluru",
            candidates=(CandidateEvidence(
                "shared",
                CandidateDisposition.UNPROCESSED,
                CandidateReason.DUPLICATE_ACROSS_SCOPES,
                output_deduplicated=True,
                output_duplicate_of_scope_id=first.scope.scope_id,
                output_duplicate_of_sequence=1,
                processing_status=CandidateProcessingStatus.PENDING,
            ),),
        )
        wrong_target = replace(
            base,
            candidates=(replace(base.candidates[0], output_duplicate_of_sequence=2),),
        )
        self.assertEqual(
            classify_collection_run(complete_run(first, wrong_target)),
            CollectionStatus.INCOMPLETE,
        )

    def test_candidate_identity_ledger_must_match_occurrence_ids_and_count(self):
        base = complete_scope(
            candidates=(
                CandidateEvidence("job-1", CandidateDisposition.QUALIFYING),
                CandidateEvidence("job-1", CandidateDisposition.DUPLICATE),
            )
        )
        valid = replace(
            base,
            candidate_identity_ids=("job-1",),
            reported_candidate_identity_count=1,
        )
        wrong_ids = replace(valid, candidate_identity_ids=("job-2",))
        wrong_count = replace(valid, reported_candidate_identity_count=2)

        self.assertEqual(classify_scope_evidence(valid), CollectionStatus.COMPLETE)
        self.assertEqual(classify_scope_evidence(wrong_ids), CollectionStatus.UNKNOWN)
        self.assertEqual(classify_scope_evidence(wrong_count), CollectionStatus.UNKNOWN)

    def test_scope_not_attempted_is_incomplete(self):
        evidence = replace(complete_scope(), scope_attempted=False)
        self.assertEqual(classify_scope_evidence(evidence), CollectionStatus.INCOMPLETE)

    def test_reported_scope_sequence_must_match_requested_order(self):
        scope = replace(complete_scope(), scope_sequence=2)
        self.assertEqual(classify_collection_run(complete_run(scope)), CollectionStatus.UNKNOWN)

    def test_missing_requested_scope_is_incomplete(self):
        present = complete_scope()
        missing = SearchScope("developer", "Bengaluru", "scope:developer:bengaluru")
        run = complete_run(present, requested_scopes=(present.scope, missing))
        self.assertEqual(classify_collection_run(run), CollectionStatus.INCOMPLETE)

    def test_missing_scope_precedes_unrelated_malformed_scope_evidence(self):
        present = complete_scope()
        missing = SearchScope("developer", "Bengaluru", "scope:developer:bengaluru")
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

    def test_malformed_scope_records_are_unknown_without_raising(self):
        present = complete_scope()
        for malformed_scope in (None, object(), SearchScope("", "", "")):
            with self.subTest(malformed_scope=type(malformed_scope).__name__):
                malformed = ScopeEvidence(scope=malformed_scope)
                run = complete_run(
                    present,
                    malformed,
                    requested_scopes=(present.scope,),
                )
                self.assertEqual(classify_collection_run(run), CollectionStatus.UNKNOWN)

    def test_unexpected_scope_is_unknown(self):
        requested = SearchScope("engineer", "remote", "scope:engineer:remote")
        requested_evidence = complete_scope("engineer", "remote")
        unexpected = complete_scope("developer", "Bengaluru")
        run = complete_run(
            requested_evidence,
            unexpected,
            requested_scopes=(requested,),
        )
        self.assertEqual(classify_collection_run(run), CollectionStatus.UNKNOWN)

    def test_observed_keyword_and_location_must_match_requested_scope(self):
        requested = SearchScope("engineer", "remote", "scope:shared")
        evidence = complete_scope("developer", "Bengaluru")
        substituted_scope = replace(evidence.scope, scope_id=requested.scope_id)
        candidates = tuple(
            replace(candidate, source_scope_id=requested.scope_id)
            for candidate in evidence.candidates
        )
        evidence = replace(
            evidence,
            scope=substituted_scope,
            observed_scope=substituted_scope,
            candidates=candidates,
        )

        run = complete_run(evidence, requested_scopes=(requested,))
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
        fatal = ScopeEvidence(
            scope=SearchScope("developer", "Bengaluru", "scope:developer:bengaluru"),
            fatal_failure=True,
        )
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

    def test_navigation_failure_precedes_missing_requested_scope(self):
        failed_scope = SearchScope("engineer", "remote", "scope:engineer:remote")
        missing_scope = SearchScope("developer", "Bengaluru", "scope:developer:bengaluru")
        navigation_failure = ScopeEvidence(
            scope=failed_scope,
            page_state=PageEvidenceState.NAVIGATION_ERROR,
        )
        run = CollectionRunEvidence(
            requested_scopes=(failed_scope, missing_scope),
            scopes=(navigation_failure,),
            fatal_failure=False,
            unresolved_error_count=0,
        )

        self.assertEqual(classify_scope_evidence(navigation_failure), CollectionStatus.FAILED)
        self.assertEqual(classify_collection_run(run), CollectionStatus.FAILED)

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
        unknown = ScopeEvidence(
            scope=SearchScope("developer", "Bengaluru", "scope:developer:bengaluru")
        )
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
