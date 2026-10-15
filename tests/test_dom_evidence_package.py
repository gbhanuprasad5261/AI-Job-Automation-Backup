"""Synthetic, in-memory contract tests; these are not live-page evidence."""

import ast
from copy import deepcopy
from pathlib import Path
import unittest

import dom_evidence_package as package_validator
from dom_evidence_package import (
    CompletionStatus,
    PackageValidation,
    PageEvidenceState,
    validate_dom_evidence_package,
)


def synthetic_package(state="POPULATED_RESULTS_SETTLED"):
    """Build synthetic claims only; no files or real observations are used."""
    package = {
        "schema_version": "1.2",
        "package_identity": {
            "capture_id": None,
            "production_run_id": None,
            "production_run_association": "not_established",
        },
        "provenance": {
            "source_type": "synthetic_fixture",
            "source_reference": "synthetic/package.json",
            "provider_assertions": ["Synthetic test data only."],
            "independent_verification": {
                "status": "unverified",
                "method": None,
                "evidence_refs": [],
                "reviewed_claims": [],
            },
        },
        "capture_time": {
            "timestamp_utc": None,
            "time_basis": "unknown",
            "method": None,
        },
        "code_revision": {"value": None, "basis": "unknown"},
        "requested_scope": {
            "query": "backend engineer",
            "location": "Bengaluru",
            "basis": "provider_assertion",
        },
        "observed_search_identity": {
            "query": {
                "value": "backend engineer",
                "basis": "direct_observation",
                "evidence_refs": ["dom_snapshot"],
            },
            "location": {
                "value": "Bengaluru",
                "basis": "direct_observation",
                "evidence_refs": ["dom_snapshot"],
            },
            "match_assessment": {"value": "matched", "basis": "provider_assertion"},
        },
        "artifacts": {
            "dom_snapshot": {
                "reference": "synthetic/dom.txt",
                "sha256": "a" * 64,
                "redaction_review": "reviewed",
            },
            "screenshot": None,
            "source_run_ledger": None,
        },
        "observations": {
            "sanitized_origin": None,
            "dom": {
                "excerpt": "Synthetic DOM excerpt; no page was visited.",
                "sanitized": True,
                "basis": "direct_observation",
                "evidence_refs": ["dom_snapshot"],
            },
            "loading": {
                "state": "settled",
                "basis": "direct_observation",
                "evidence_refs": ["dom_snapshot"],
                "history": [
                    {"sequence": 1, "state": "settled", "evidence_refs": ["dom_snapshot"]}
                ],
            },
            "results": {
                "visible_card_count": 3,
                "displayed_total_text": "3 results",
                "empty_state": {
                    "observed": False,
                    "basis": "direct_observation",
                    "evidence_refs": [],
                },
            },
            "pagination": {
                "state": "not_observed",
                "batches": [],
                "exhaustion_review": {
                    "status": "not_reviewed",
                    "method": None,
                    "evidence_refs": [],
                },
                "cap": {"reached": False, "prevented_exhaustion": False},
            },
            "page_error": None,
            "interstitial": {
                "observed": False,
                "kind": None,
                "basis": "unknown",
                "evidence_refs": [],
            },
        },
        "candidate_processing": None,
        "interpretations": {"observed_state": state, "claims": []},
        "privacy_review": {
            "status": "reviewed",
            "redactions_made": ["Synthetic data contains no personal content."],
            "heuristic_scan": "no_matches_found",
            "notes": [],
        },
        "limitations": ["Synthetic fixture structure does not establish real page behavior."],
        "completion_status": "UNKNOWN",
    }
    if state == "LEGITIMATE_EMPTY":
        package["observations"]["results"]["visible_card_count"] = 0
        package["observations"]["results"]["displayed_total_text"] = None
        package["observations"]["results"]["empty_state"] = {
            "observed": True,
            "basis": "direct_observation",
            "evidence_refs": ["dom_snapshot"],
        }
    elif state == "LOADING_OR_UNSETTLED":
        package["observations"]["loading"]["state"] = "loading"
        package["observations"]["loading"]["evidence_refs"] = ["dom_snapshot"]
        package["observations"]["loading"]["history"] = [
            {"sequence": 1, "state": "loading", "evidence_refs": ["dom_snapshot"]}
        ]
        package["observed_search_identity"]["match_assessment"] = {
            "value": "unverified", "basis": "unknown"
        }
    elif state in {"AUTHENTICATION_REQUIRED", "CHALLENGE_OR_INTERSTITIAL"}:
        package["observations"]["results"]["visible_card_count"] = None
        package["observations"]["results"]["displayed_total_text"] = None
        package["observations"]["loading"]["state"] = "unknown"
        package["observations"]["loading"]["history"] = []
        package["observations"]["interstitial"] = {
            "observed": True,
            "kind": "authentication_required" if state == "AUTHENTICATION_REQUIRED" else "challenge",
            "basis": "direct_observation",
            "evidence_refs": ["dom_snapshot"],
        }
        package["observed_search_identity"]["match_assessment"] = {
            "value": "unverified", "basis": "unknown"
        }
    elif state in {"POPULATED_MORE_PAGINATION", "EXHAUSTION_REVIEW_RECORDED"}:
        terminal = state == "EXHAUSTION_REVIEW_RECORDED"
        package["observations"]["pagination"] = {
            "state": "terminal_condition_observed" if terminal else "more_batches_observed",
            "batches": [
                {
                    "sequence": 1,
                    "status": "OBSERVED",
                    "observation": "Synthetic additional batch indication.",
                    "more_indicated": not terminal,
                    "basis": "direct_observation",
                    "evidence_refs": ["dom_snapshot"],
                    "terminal_evidence_refs": ["dom_snapshot"] if terminal else [],
                },
            ],
            "exhaustion_review": {
                "status": "not_reviewed", "method": None, "evidence_refs": []
            },
            "cap": {"reached": False, "prevented_exhaustion": False},
        }
        if terminal:
            package["provenance"]["independent_verification"] = {
                "status": "review_recorded",
                "method": "Synthetic test review record.",
                "evidence_refs": ["dom_snapshot"],
                "reviewed_claims": ["pagination_exhaustion"],
            }
            package["observations"]["pagination"]["exhaustion_review"] = {
                "status": "review_recorded",
                "method": "Synthetic test review record.",
                "evidence_refs": ["dom_snapshot"],
            }
    elif state in {"NAVIGATION_ERROR", "PARSING_ERROR"}:
        package["observations"]["loading"]["state"] = "unknown"
        package["observations"]["loading"]["history"] = []
        package["observations"]["page_error"] = {
            "kind": "navigation" if state == "NAVIGATION_ERROR" else "parsing",
            "description": "Synthetic offline error observation.",
            "basis": "direct_observation",
            "evidence_refs": ["dom_snapshot"],
        }
        package["observed_search_identity"]["match_assessment"] = {
            "value": "unverified", "basis": "unknown"
        }
    elif state == "PAGINATION_BATCH_FAILED":
        package["observations"]["pagination"] = {
            "state": "failed_batch",
            "batches": [{
                "sequence": 1,
                "status": "FAILED",
                "observation": "Synthetic batch failure.",
                "more_indicated": None,
                "basis": "direct_observation",
                "evidence_refs": ["dom_snapshot"],
                "terminal_evidence_refs": [],
            }],
            "exhaustion_review": {"status": "not_reviewed", "method": None, "evidence_refs": []},
            "cap": {"reached": False, "prevented_exhaustion": False},
        }
    return package


class DomEvidencePackageTests(unittest.TestCase):
    def validate(self, fixture):
        result = validate_dom_evidence_package(fixture)
        self.assertEqual(result.completion_status, CompletionStatus.UNKNOWN)
        return result

    def test_synthetic_state_shapes_are_valid_but_never_completion(self):
        states = {
            "POPULATED_RESULTS_SETTLED": PageEvidenceState.POPULATED_RESULTS_SETTLED,
            "LEGITIMATE_EMPTY": PageEvidenceState.LEGITIMATE_EMPTY,
            "LOADING_OR_UNSETTLED": PageEvidenceState.LOADING_OR_UNSETTLED,
            "AUTHENTICATION_REQUIRED": PageEvidenceState.AUTHENTICATION_REQUIRED,
            "CHALLENGE_OR_INTERSTITIAL": PageEvidenceState.CHALLENGE_OR_INTERSTITIAL,
            "NAVIGATION_ERROR": PageEvidenceState.NAVIGATION_ERROR,
            "PARSING_ERROR": PageEvidenceState.PARSING_ERROR,
            "PAGINATION_BATCH_FAILED": PageEvidenceState.PAGINATION_BATCH_FAILED,
            "POPULATED_MORE_PAGINATION": PageEvidenceState.POPULATED_MORE_PAGINATION,
            "EXHAUSTION_REVIEW_RECORDED": PageEvidenceState.EXHAUSTION_REVIEW_RECORDED,
        }
        for label, expected in states.items():
            with self.subTest(label=label):
                result = self.validate(synthetic_package(label))
                self.assertTrue(result.valid, result.issues)
                self.assertEqual(result.observed_state, expected)

    def test_unverified_provenance_is_explicit_and_accepted_as_unverified(self):
        fixture = synthetic_package()
        result = self.validate(fixture)
        self.assertTrue(result.valid, result.issues)
        self.assertEqual(fixture["provenance"]["independent_verification"]["status"], "unverified")
        self.assertIsNone(fixture["package_identity"]["production_run_id"])

    def test_missing_fields_and_wrong_schema_are_rejected(self):
        fixture = synthetic_package()
        del fixture["observations"]["loading"]
        result = self.validate(fixture)
        self.assertFalse(result.valid)
        self.assertEqual(result.observed_state, PageEvidenceState.UNKNOWN)

        fixture = synthetic_package()
        fixture["schema_version"] = "2.0"
        self.assertFalse(self.validate(fixture).valid)

    def test_malformed_nested_types_fail_as_validation_not_exceptions(self):
        for mutate in (
            lambda f: f.update({"observations": []}),
            lambda f: f["observations"].update({"loading": {"state": [], "basis": {}, "evidence_refs": []}}),
            lambda f: f["interpretations"].update({"observed_state": []}),
            lambda f: f["artifacts"].update({"screenshot": {"reference": [], "sha256": {}, "redaction_review": []}}),
            lambda f: f["provenance"]["independent_verification"].update({"reviewed_claims": None}),
        ):
            fixture = synthetic_package()
            mutate(fixture)
            result = self.validate(fixture)
            self.assertFalse(result.valid)
            self.assertEqual(result.observed_state, PageEvidenceState.UNKNOWN)

    def test_observation_basis_types_are_validated_without_type_errors(self):
        for bad_basis in ([], {}, None):
            fixture = synthetic_package()
            fixture["observed_search_identity"]["query"]["basis"] = bad_basis
            result = self.validate(fixture)
            self.assertFalse(result.valid)
            self.assertEqual(result.observed_state, PageEvidenceState.UNKNOWN)
            self.assertIn(
                "observed_search_identity.query.basis is unsupported.",
                result.issues,
            )

        fixture = synthetic_package()
        del fixture["observed_search_identity"]["query"]["basis"]
        result = self.validate(fixture)
        self.assertFalse(result.valid)
        self.assertTrue(any(
            "observed_search_identity.query is missing fields" in issue
            for issue in result.issues
        ))

        self.assertTrue(self.validate(synthetic_package()).valid)

    def test_malformed_review_claims_do_not_raise_in_exhaustion_case(self):
        fixture = synthetic_package("EXHAUSTION_REVIEW_RECORDED")
        fixture["provenance"]["independent_verification"]["reviewed_claims"] = None
        result = self.validate(fixture)
        self.assertFalse(result.valid)
        self.assertEqual(result.observed_state, PageEvidenceState.UNKNOWN)

    def test_query_location_mismatch_cannot_be_asserted_as_matched(self):
        fixture = synthetic_package()
        fixture["observed_search_identity"]["query"]["value"] = "different role"
        result = self.validate(fixture)
        self.assertFalse(result.valid)
        self.assertTrue(any("differs" in issue for issue in result.issues))

    def test_loading_and_settled_label_conflict_is_rejected(self):
        fixture = synthetic_package("POPULATED_RESULTS_SETTLED")
        fixture["observations"]["loading"]["state"] = "unsettled"
        result = self.validate(fixture)
        self.assertFalse(result.valid)

    def test_loading_transition_history_is_ordered_and_matches_final_state(self):
        fixture = synthetic_package()
        fixture["observations"]["loading"]["history"] = [
            {"sequence": 1, "state": "loading", "evidence_refs": ["dom_snapshot"]},
            {"sequence": 2, "state": "settled", "evidence_refs": ["dom_snapshot"]},
        ]
        self.assertTrue(self.validate(fixture).valid)
        fixture["observations"]["loading"]["history"][1]["state"] = "unsettled"
        self.assertFalse(self.validate(fixture).valid)

    def test_matched_identity_requires_directly_referenced_query_and_location(self):
        fixture = synthetic_package()
        fixture["observed_search_identity"]["query"]["evidence_refs"] = []
        result = self.validate(fixture)
        self.assertFalse(result.valid)
        fixture = synthetic_package()
        fixture["observed_search_identity"]["location"]["basis"] = "provider_assertion"
        self.assertFalse(self.validate(fixture).valid)

    def test_populated_results_conflict_with_an_observed_empty_state(self):
        fixture = synthetic_package()
        fixture["observations"]["results"]["empty_state"]["observed"] = True
        self.assertFalse(self.validate(fixture).valid)

    def test_legitimate_empty_requires_zero_cards_empty_observation_and_identity(self):
        fixture = synthetic_package("LEGITIMATE_EMPTY")
        fixture["observations"]["results"]["empty_state"]["evidence_refs"] = []
        result = self.validate(fixture)
        self.assertFalse(result.valid)
        fixture = synthetic_package("LEGITIMATE_EMPTY")
        fixture["observations"]["pagination"]["state"] = "more_batches_observed"
        fixture["observations"]["pagination"]["batches"] = [
            {"sequence": 1, "observation": "More batches", "basis": "direct_observation", "evidence_refs": ["dom_snapshot"]}
        ]
        self.assertFalse(self.validate(fixture).valid)

    def test_authentication_and_challenge_states_are_distinct_and_referenced(self):
        for label in ("AUTHENTICATION_REQUIRED", "CHALLENGE_OR_INTERSTITIAL"):
            with self.subTest(label=label):
                self.assertTrue(self.validate(synthetic_package(label)).valid)
        fixture = synthetic_package("AUTHENTICATION_REQUIRED")
        fixture["observations"]["interstitial"]["kind"] = None
        self.assertFalse(self.validate(fixture).valid)

    def test_pagination_batches_require_contiguous_unique_sequence(self):
        fixture = synthetic_package("POPULATED_MORE_PAGINATION")
        fixture["observations"]["pagination"]["batches"].append({
            "sequence": 2,
            "status": "OBSERVED",
            "observation": "Synthetic next batch was observed.",
            "more_indicated": True,
            "basis": "direct_observation",
            "evidence_refs": ["dom_snapshot"],
            "terminal_evidence_refs": [],
        })
        result = self.validate(fixture)
        self.assertTrue(result.valid, result.issues)
        fixture["observations"]["pagination"]["batches"][1]["sequence"] = 1
        self.assertFalse(self.validate(fixture).valid)

    def test_pagination_requires_each_prior_batch_to_indicate_more(self):
        fixture = synthetic_package("POPULATED_MORE_PAGINATION")
        fixture["observations"]["pagination"]["batches"].append({
            "sequence": 2,
            "status": "OBSERVED",
            "observation": "Synthetic next batch was observed.",
            "more_indicated": False,
            "basis": "direct_observation",
            "evidence_refs": ["dom_snapshot"],
            "terminal_evidence_refs": ["dom_snapshot"],
        })
        self.assertFalse(self.validate(fixture).valid)

    def test_failed_pagination_batch_is_distinct_from_terminal_state(self):
        fixture = synthetic_package("PAGINATION_BATCH_FAILED")
        self.assertTrue(self.validate(fixture).valid)
        fixture["observations"]["pagination"]["state"] = "terminal_condition_observed"
        self.assertFalse(self.validate(fixture).valid)

    def test_terminal_state_conflicts_with_more_batches(self):
        fixture = synthetic_package("EXHAUSTION_REVIEW_RECORDED")
        fixture["observations"]["pagination"]["state"] = "more_batches_observed"
        self.assertFalse(self.validate(fixture).valid)

    def test_terminal_evidence_requires_a_final_batch_not_an_empty_list(self):
        fixture = synthetic_package("EXHAUSTION_REVIEW_RECORDED")
        fixture["observations"]["pagination"]["batches"] = []
        self.assertFalse(self.validate(fixture).valid)

    def test_navigation_and_parsing_errors_require_matching_direct_evidence(self):
        for label in ("NAVIGATION_ERROR", "PARSING_ERROR"):
            with self.subTest(label=label):
                fixture = synthetic_package(label)
                self.assertTrue(self.validate(fixture).valid)
                fixture["observations"]["page_error"]["kind"] = "parsing" if label == "NAVIGATION_ERROR" else "navigation"
                self.assertFalse(self.validate(fixture).valid)

    def test_premature_cap_and_unknown_cap_block_exhaustion_claim(self):
        for cap in (
            {"reached": True, "prevented_exhaustion": True},
            {"reached": True, "prevented_exhaustion": None},
            {"reached": None, "prevented_exhaustion": None},
        ):
            fixture = synthetic_package("EXHAUSTION_REVIEW_RECORDED")
            fixture["observations"]["pagination"]["cap"] = cap
            self.assertFalse(self.validate(fixture).valid)

    def test_cap_after_independently_reviewed_exhaustion_is_representable(self):
        fixture = synthetic_package("EXHAUSTION_REVIEW_RECORDED")
        fixture["observations"]["pagination"]["cap"] = {
            "reached": True, "prevented_exhaustion": False
        }
        self.assertTrue(self.validate(fixture).valid)

    def test_exhaustion_requires_recorded_review_and_never_means_collection_complete(self):
        fixture = synthetic_package("EXHAUSTION_REVIEW_RECORDED")
        fixture["provenance"]["independent_verification"]["status"] = "unverified"
        result = self.validate(fixture)
        self.assertFalse(result.valid)
        self.assertEqual(result.completion_status, CompletionStatus.UNKNOWN)

    def test_candidate_dispositions_require_an_explicit_matching_ledger(self):
        fixture = synthetic_package()
        fixture["artifacts"]["source_run_ledger"] = {
            "reference": "synthetic/run-ledger.json",
            "sha256": "b" * 64,
            "redaction_review": "reviewed",
        }
        fixture["candidate_processing"] = {
            "source_run_ledger": {
                "run_id": "synthetic-run-1",
                "scope_id": "scope-1",
                "reference": "synthetic/run-ledger.json",
                "scope_query": "backend engineer",
                "scope_location": "Bengaluru",
                "basis": "provider_assertion",
            },
            "discovered_count": 2,
            "dispositions": [
                {
                    "candidate_id": "job-1", "source_scope_id": "scope-1",
                    "discovery_sequence": 1, "processing_status": "PROCESSED",
                    "disposition": "QUALIFYING",
                },
                {
                    "candidate_id": "job-2", "source_scope_id": "scope-1",
                    "discovery_sequence": 2, "processing_status": "PROCESSED",
                    "disposition": "FILTERED",
                    "reason_code": "OUTSIDE_TARGET_LOCATION",
                },
            ],
        }
        self.assertTrue(self.validate(fixture).valid)
        fixture["candidate_processing"]["dispositions"].pop()
        self.assertFalse(self.validate(fixture).valid)

    def test_duplicate_ids_missing_ledger_and_scope_mismatch_are_rejected(self):
        fixture = synthetic_package()
        fixture["candidate_processing"] = {
            "source_run_ledger": {
                "run_id": "run-1",
                "scope_id": "scope-1",
                "reference": "synthetic/run-ledger.json",
                "scope_query": "backend engineer",
                "scope_location": "Bengaluru",
                "basis": "provider_assertion",
            },
            "discovered_count": 2,
            "dispositions": [
                {
                    "candidate_id": "job-1", "source_scope_id": "scope-1",
                    "discovery_sequence": 1, "processing_status": "PROCESSED",
                    "disposition": "QUALIFYING",
                },
                {
                    "candidate_id": "job-1", "source_scope_id": "scope-1",
                    "discovery_sequence": 2, "processing_status": "PROCESSED",
                    "disposition": "UNKNOWN",
                },
            ],
        }
        self.assertFalse(self.validate(fixture).valid)
        fixture["artifacts"]["source_run_ledger"] = {
            "reference": "synthetic/other.json", "sha256": "b" * 64,
            "redaction_review": "reviewed",
        }
        self.assertFalse(self.validate(fixture).valid)

    def test_candidate_dispositions_require_consistent_reason_codes(self):
        fixture = synthetic_package()
        fixture["artifacts"]["source_run_ledger"] = {
            "reference": "synthetic/run-ledger.json",
            "sha256": "b" * 64,
            "redaction_review": "reviewed",
        }
        fixture["candidate_processing"] = {
            "source_run_ledger": {
                "run_id": "synthetic-run-1",
                "scope_id": "scope-1",
                "reference": "synthetic/run-ledger.json",
                "scope_query": "backend engineer",
                "scope_location": "Bengaluru",
                "basis": "provider_assertion",
            },
            "discovered_count": 1,
            "dispositions": [
                {
                    "candidate_id": "job-1", "source_scope_id": "scope-1",
                    "discovery_sequence": 1, "processing_status": "PROCESSED",
                    "disposition": "FILTERED",
                },
            ],
        }
        result = self.validate(fixture)
        self.assertFalse(result.valid)
        self.assertTrue(any("reason_code" in issue for issue in result.issues))

        fixture["candidate_processing"]["dispositions"][0]["reason_code"] = "OUTSIDE_TARGET_LOCATION"
        self.assertTrue(self.validate(fixture).valid)

        fixture["candidate_processing"]["dispositions"][0]["reason_code"] = "PROCESSING_ERROR"
        result = self.validate(fixture)
        self.assertFalse(result.valid)
        self.assertTrue(any("reason_code" in issue for issue in result.issues))

    def test_unsafe_references_urls_and_sensitive_text_are_rejected(self):
        changes = (
            lambda f: f["artifacts"]["dom_snapshot"].update({"reference": "../outside.html"}),
            lambda f: f["artifacts"]["dom_snapshot"].update({"reference": "https://example.invalid/dom"}),
            lambda f: f["artifacts"]["dom_snapshot"].update({"reference": "%2e%2e/outside.html"}),
            lambda f: f["observations"]["dom"].update({"excerpt": "contact person@example.invalid"}),
            lambda f: f["observations"]["dom"].update({"excerpt": "Details at example.invalid"}),
            lambda f: f["requested_scope"].update({"query": "token=secret"}),
        )
        for mutate in changes:
            fixture = synthetic_package()
            mutate(fixture)
            result = self.validate(fixture)
            self.assertFalse(result.valid)
            self.assertTrue(any(
                "must be a safe relative reference" in issue
                or "heuristic privacy screening" in issue
                for issue in result.issues
            ), result.issues)

    def test_artifact_references_reject_control_characters_and_allow_relative_paths(self):
        for reference in (
            "synthetic/dom\x00.txt",
            "synthetic/dom\n.txt",
            "synthetic/dom\t.txt",
            "synthetic/dom\x01.txt",
            "synthetic/dom\x7f.txt",
        ):
            with self.subTest(reference=repr(reference)):
                fixture = synthetic_package()
                fixture["artifacts"]["dom_snapshot"]["reference"] = reference
                result = self.validate(fixture)
                self.assertFalse(result.valid)
                self.assertIn(
                    "artifacts.dom_snapshot.reference must be a safe relative reference.",
                    result.issues,
                )

        fixture = synthetic_package()
        fixture["artifacts"]["dom_snapshot"]["reference"] = "synthetic/evidence/dom.txt"
        self.assertTrue(self.validate(fixture).valid)

    def test_sanitized_origin_accepts_supported_origins_and_rejects_malformed_values(self):
        for origin in (
            "https://example.com",
            "http://localhost:8080",
            "https://127.0.0.1",
            "https://[::1]",
        ):
            with self.subTest(origin=origin):
                fixture = synthetic_package()
                fixture["observations"]["sanitized_origin"] = origin
                self.assertTrue(self.validate(fixture).valid)

        for origin in (
            "https://a..b",
            "https://example.com:99999",
            "https://example.com:" + ("9" * 5000),
            "https://",
            "https://example..com",
            "https://example.com:",
            "https://user@example.com",
            "https://[::::]",
            "https://example.com/path",
            "https://example.com?query=1",
            "https://example.com#fragment",
        ):
            with self.subTest(origin=origin):
                fixture = synthetic_package()
                fixture["observations"]["sanitized_origin"] = origin
                result = self.validate(fixture)
                self.assertFalse(result.valid)
                self.assertIn(
                    "observations.sanitized_origin must be a sanitized origin or null.",
                    result.issues,
                )

    def test_artifact_digest_shape_is_checked_but_bytes_are_not_read(self):
        fixture = synthetic_package()
        fixture["artifacts"]["dom_snapshot"]["sha256"] = "not-a-digest"
        self.assertFalse(self.validate(fixture).valid)
        fixture = synthetic_package()
        self.assertTrue(self.validate(fixture).valid)

    def test_privacy_review_and_redaction_flags_are_not_sanitizers(self):
        fixture = synthetic_package()
        fixture["privacy_review"]["heuristic_scan"] = "matches_flagged"
        self.assertFalse(self.validate(fixture).valid)
        fixture = synthetic_package()
        fixture["artifacts"]["dom_snapshot"]["redaction_review"] = "not_reviewed"
        self.assertFalse(self.validate(fixture).valid)

    def test_completion_status_is_fixed_unknown_for_valid_and_invalid_inputs(self):
        valid = self.validate(synthetic_package())
        invalid_fixture = synthetic_package()
        invalid_fixture["completion_status"] = "COMPLETE"
        invalid = self.validate(invalid_fixture)
        malformed = self.validate(None)
        for result in (valid, invalid, malformed):
            self.assertEqual(result.completion_status, CompletionStatus.UNKNOWN)

    def test_package_validation_cannot_be_constructed_with_other_completion_status(self):
        result = PackageValidation(True, PageEvidenceState.UNKNOWN)
        self.assertEqual(result.completion_status, CompletionStatus.UNKNOWN)
        with self.assertRaises(TypeError):
            PackageValidation(
                True,
                PageEvidenceState.UNKNOWN,
                completion_status="COMPLETE",
            )

    def test_module_is_in_memory_only_and_isolated(self):
        source = Path(package_validator.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        forbidden = {
            "job_search", "offline_search_evidence",
            "route_audit", "easy_apply", "external_app", "playwright",
            "requests", "httpx", "urllib", "socket", "subprocess", "pathlib",
        }
        self.assertTrue(forbidden.isdisjoint(imported), imported & forbidden)
        self.assertIn("datetime", imported)
        self.assertIn("collection_run_evidence", imported)
        forbidden_classifier_calls = {"classify_collection_run", "classify_scope_evidence"}
        invoked_names = {
            node.func.id for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        self.assertTrue(forbidden_classifier_calls.isdisjoint(invoked_names))
        forbidden_calls = {"open", "read_text", "read_bytes", "write_text", "write_bytes", "urlopen", "Popen"}
        calls = {
            node.func.id for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        self.assertTrue(forbidden_calls.isdisjoint(calls), calls & forbidden_calls)


if __name__ == "__main__":
    unittest.main()
