"""Synthetic-only integration probes; no filesystem or production workflow use."""
from __future__ import annotations

import copy
import hashlib
import json
import unittest
from unittest.mock import patch

from tools import offline_generation_lifecycle as lifecycle
from tools import offline_provenance_verifier as verifier
from tools import manifest_contract_compat as compat
import pipeline_generation_store as generation_store


RECORDS = [
    '"Synthetic 1",Example Co,Offline,No,No,https://example.test/1\n',
    '"Synthetic 2",Example Co,Offline,No,No,https://example.test/2\n',
]


def _verifier_native_partial() -> tuple[bytes, dict[str, bytes], bytes, dict[str, bytes]]:
    """A verifier-v1 native fixture for probing its existing PARTIAL policy."""
    source_data = (
        "Title,Company,Location,Easy Apply,Actively Reviewing,Link\n"
        "Backend,Example,Offline,No,No,https://example.test/1\n"
        "Backend,Example,Offline,No,No,https://example.test/2\n"
    ).encode()
    fp = lambda data: {"sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data)}
    def artifact(path, fmt, data, count):
        return {"relative_path": path, **fp(data), "record_count": count, "format": fmt}
    source_manifest = {
        "schema_version": 1, "run_id": lifecycle.RUN_SOURCE, "stage": "source", "status": "COMPLETE",
        "producer": {"id": "synthetic", "version": "1"}, "started_at": lifecycle.STARTED,
        "completed_at": lifecycle.COMPLETED,
        "source": {"role": "jobs_csv", **fp(source_data), "record_count": 2, "encoding": "utf-8", "format": "csv/jobs-v1"},
        "input_generation": None, "accounting": None, "occurrences": None,
        "outputs": {"jobs_csv": artifact("jobs.csv", "csv/jobs-v1", source_data, 2)}, "failure": None,
    }
    source_bytes = json.dumps(source_manifest, sort_keys=True, separators=(",", ":")).encode()
    details_data = (
        '"Title","Company","Location","Experience","Easy Apply","Skills","Link","Description"\n'
        '"Backend","Example","Offline","","No","Python","https://example.test/1","Synthetic description"\n'
    ).encode()
    diagnostics = b"[]"
    source_hash = fp(source_data)["sha256"]
    occurrences = [
        {"ordinal": 1, "occurrence_key": f"{source_hash}:1", "logical_identity": "synthetic-1", "disposition": "PROCESSED", "reason_code": None, "policy_rule_id": None, "retained_occurrence_key": None, "error_code": None, "quality_code": None, "output_row": 1},
        {"ordinal": 2, "occurrence_key": f"{source_hash}:2", "logical_identity": "synthetic-2", "disposition": "FAILED", "reason_code": None, "policy_rule_id": None, "retained_occurrence_key": None, "error_code": "EXTRACTION_ERROR", "quality_code": None, "output_row": None},
    ]
    details_manifest = {
        "schema_version": 1, "run_id": lifecycle.RUN_DETAILS, "stage": "job_details", "status": "PARTIAL",
        "producer": {"id": "synthetic", "version": "1"}, "started_at": lifecycle.STARTED,
        "completed_at": lifecycle.COMPLETED,
        "source": {"role": "jobs_csv", **fp(source_data), "record_count": 2, "encoding": "utf-8", "format": "csv/jobs-v1"},
        "input_generation": {
            "stage": "source", "run_id": lifecycle.RUN_SOURCE, "status": "COMPLETE",
            "manifest_sha256": hashlib.sha256(source_bytes).hexdigest(), "artifact_role": "jobs_csv",
            "artifact_sha256": fp(source_data)["sha256"], "artifact_size_bytes": fp(source_data)["size_bytes"], "record_count": 2,
        },
        "accounting": {"source_occurrences": 2, "processed_occurrences": 1, "intentional_skip_occurrences": 0, "failed_occurrences": 1, "output_rows": 1},
        "occurrences": occurrences,
        "outputs": {"details_csv": artifact("job_details.csv", "csv/details-v1", details_data, 1), "diagnostics_json": artifact("job_details_diagnostics.json", "json/diagnostics-v1", diagnostics, 0)},
        "failure": None,
    }
    details_bytes = json.dumps(details_manifest, sort_keys=True, separators=(",", ":")).encode()
    result = verifier.verify_generation(
        details_bytes, {"details_csv": details_data, "diagnostics_json": diagnostics}, expected_stage="job_details",
        upstream_manifest_bytes=source_bytes, upstream_artifacts_by_role={"jobs_csv": source_data},
    )
    return details_bytes, {"details_csv": details_data, "diagnostics_json": diagnostics}, source_bytes, {"jobs_csv": source_data}


class OfflineGenerationLifecycleTests(unittest.TestCase):
    def test_complete_synthetic_run_preserves_each_component_outcome(self):
        result = lifecycle.run_offline_lifecycle(RECORDS, status="COMPLETE")
        self.assertEqual(result["stages"]["manifest_schema_v2"]["outcome"], "VALID")
        self.assertEqual(result["stages"]["source_generation_binding"]["outcome"], "CONSISTENT")
        self.assertEqual(result["stages"]["offline_provenance_verifier"]["raw_result"]["target_schema_version"], 1)
        self.assertTrue(result["stages"]["offline_provenance_verifier"]["accepted"])
        self.assertEqual(result["stages"]["generation_store"]["outcome"], "VALID")
        self.assertEqual(result["stages"]["generation_store_analyzer_input_binding"]["outcome"], "MATCHED")
        self.assertEqual(result["aggregate_outcome"], "NATIVE_CONTRACTS_VALIDATED_CROSS_VERSION_INCOMPATIBLE")
        self.assertEqual(result["component_contract_compatibility"]["outcome"], "CROSS_VERSION_REJECTED")
        self.assertEqual(result["component_contract_compatibility"]["v2_to_verifier_v1"]["failure_code"], "SCHEMA_VERSION_MISMATCH")
        self.assertEqual(result["component_contract_compatibility"]["v2_to_generation_store_v1"]["failure_code"], "SCHEMA_VERSION_MISMATCH")
        self.assertFalse(result["production_selection_authorized"])

    def test_all_lifecycle_statuses_keep_native_component_results_separate(self):
        expected = {
            "COMPLETE": ("VERIFIED_DATA_ONLY", "VALID"),
            "EMPTY": ("EMPTY_DATA_ONLY", "VALID"),
            "PARTIAL": ("UNSUPPORTED_POLICY", "VALID"),
            "FAILED": ("FAILED", "VALID"),
            "IN_PROGRESS": ("INCOMPLETE", "VALID"),
        }
        for status, (verifier_outcome, store_outcome) in expected.items():
            with self.subTest(status=status):
                result = lifecycle.run_offline_lifecycle(RECORDS, status=status)
                self.assertEqual(result["stages"]["offline_provenance_verifier"]["outcome"], verifier_outcome)
                self.assertEqual(result["stages"]["generation_store"]["outcome"], store_outcome)
                self.assertFalse(result["stages"]["offline_provenance_verifier"]["raw_result"]["eligible"])
                self.assertFalse(result["publication_authorized"])
                binding = result["stages"]["generation_store_analyzer_input_binding"]
                self.assertEqual(binding["outcome"], "MATCHED" if status in {"COMPLETE", "EMPTY"} else "NOT_APPLICABLE")
                self.assertIs(binding["accepted"], status in {"COMPLETE", "EMPTY"})
        partial = lifecycle.run_offline_lifecycle(RECORDS, status="PARTIAL")
        self.assertEqual(set(partial["stages"]["offline_provenance_verifier"]["raw_result"]["findings"]["policy_dependencies"]) & {"D6", "D7"}, {"D6", "D7"})
        self.assertEqual(lifecycle.run_offline_lifecycle(RECORDS, status="PARTIAL")["aggregate_outcome"], "PARTIAL_POLICY_UNRESOLVED")
        self.assertEqual(partial["declared_accounting"]["processed_occurrences"], 1)
        self.assertEqual(partial["declared_accounting"]["failed_occurrences"], 1)

    def test_empty_run_accounting_is_consistent(self):
        result = lifecycle.run_offline_lifecycle([], status="EMPTY")
        self.assertEqual(result["stages"]["manifest_schema_v2"]["outcome"], "VALID")
        self.assertEqual(result["declared_accounting"]["source_occurrences"], 0)
        self.assertEqual(result["declared_accounting"]["output_rows"], 0)

    def test_partial_omission_is_explicit_and_verifier_keeps_d6_d7_rejection(self):
        result = lifecycle.run_offline_lifecycle(RECORDS, status="PARTIAL", dispositions=["PROCESSED", "FAILED"])
        self.assertEqual(result["stages"]["manifest_schema_v2"]["outcome"], "VALID")
        native_bytes, artifacts, upstream_bytes, upstream_artifacts = _verifier_native_partial()
        native_result = verifier.verify_generation(
            native_bytes, artifacts, expected_stage="job_details",
            upstream_manifest_bytes=upstream_bytes, upstream_artifacts_by_role=upstream_artifacts,
        )
        self.assertFalse(native_result.accepted)
        self.assertEqual(native_result.classification, "UNSUPPORTED_POLICY")
        self.assertEqual(set(native_result.policy_dependencies) & {"D6", "D7"}, {"D6", "D7"})

    def test_failed_manifest_is_valid_but_not_authorized(self):
        result = lifecycle.run_offline_lifecycle(RECORDS, status="FAILED", dispositions=["FAILED", "FAILED"])
        schema_result = result["stages"]["manifest_schema_v2"]
        self.assertEqual(schema_result["outcome"], "VALID")
        self.assertEqual(schema_result["authorization"], "NOT_AUTHORIZED")
        self.assertEqual(result["aggregate_outcome"], "FAILED_NOT_AUTHORIZED")
        self.assertIs(result["production_selection_authorized"], False)
        self.assertIs(result["publication_authorized"], False)

    def test_interrupted_manifest_is_nonterminal_and_non_authorizing(self):
        result = lifecycle.run_offline_lifecycle(RECORDS, status="IN_PROGRESS")
        self.assertEqual(result["stages"]["manifest_schema_v2"]["outcome"], "VALID")
        self.assertEqual(result["stages"]["manifest_schema_v2"]["authorization"], "NOT_AUTHORIZED")
        self.assertEqual(result["stages"]["offline_provenance_verifier"]["outcome"], "INCOMPLETE")

    def test_invalid_manifest_rejection_for_malformed_and_contradictory_fields(self):
        for overrides, code in (
            ({"schema_version": 99}, "UNKNOWN_SCHEMA_VERSION"),
            ({"status": "COMPLETE", "accounting": {"source_occurrences": 8}}, "FIELD_SET_INVALID"),
            ({"outputs": {}}, "REQUIRED_ARTIFACT_MISSING"),
        ):
            with self.subTest(code=code):
                result = lifecycle.run_offline_lifecycle(RECORDS, status="COMPLETE", manifest_overrides=overrides)
                self.assertEqual(result["stages"]["manifest_schema_v2"]["failure_code"], code)

    def test_missing_source_generation_binding_is_rejected(self):
        result = lifecycle.run_offline_lifecycle(RECORDS, status="COMPLETE", manifest_overrides={"input_generation": None})
        self.assertEqual(result["stages"]["source_generation_binding"]["outcome"], "MISSING_SOURCE_GENERATION_BINDING")
        self.assertEqual(result["stages"]["manifest_schema_v2"]["failure_code"], "GENERATION_REFERENCE_MISSING")

    def test_contradictory_source_generation_identifier_is_reported(self):
        # UUIDv4 is structurally valid; the lifecycle's explicit upstream comparison catches its contradiction.
        result = lifecycle.run_offline_lifecycle(RECORDS, manifest_overrides={
            "input_generation": {"stage": "source", "run_id": "4c7c5d21-66eb-4e6b-9d3c-b5abff7aa63b", "status": "COMPLETE",
                "manifest_sha256": "0" * 64, "artifact_role": "jobs_csv", "artifact_sha256": "0" * 64,
                "size_bytes": 1, "record_count": 2, "format": "csv/jobs-v1"}
        })
        self.assertEqual(result["stages"]["source_generation_binding"]["outcome"], "CONTRADICTORY_SOURCE_GENERATION_ID")

    def test_source_binding_checks_digest_size_role_and_manifest_identity(self):
        source_bytes = (lifecycle.JOB_HEADER + "".join(RECORDS)).encode()
        source = lifecycle._source_manifest(source_bytes, len(RECORDS), "COMPLETE")
        base, _ = lifecycle._details_manifest(source, source_bytes, "COMPLETE", ["PROCESSED", "PROCESSED"])
        changes = {
            "artifact_sha256": "0" * 64,
            "size_bytes": base["input_generation"]["size_bytes"] + 1,
            "artifact_role": "details_csv",
            "manifest_sha256": "f" * 64,
        }
        for field, value in changes.items():
            with self.subTest(field=field):
                reference = copy.deepcopy(base["input_generation"])
                reference[field] = value
                result = lifecycle.run_offline_lifecycle(RECORDS, manifest_overrides={"input_generation": reference})
                binding = result["stages"]["source_generation_binding"]
                self.assertEqual(binding["outcome"], "CONTRADICTORY_SOURCE_GENERATION_METADATA")
                self.assertIn(field, binding["mismatched_fields"])

    def test_non_object_input_reference_fails_closed_without_crashing(self):
        result = lifecycle.run_offline_lifecycle(RECORDS, manifest_overrides={"input_generation": "malformed"})
        self.assertEqual(result["stages"]["manifest_schema_v2"]["outcome"], "INVALID")
        self.assertEqual(result["stages"]["source_generation_binding"]["outcome"], "MALFORMED_SOURCE_GENERATION_BINDING")
        self.assertEqual(result["aggregate_outcome"], "REJECTED")

    def test_in_progress_rejects_even_partially_declared_artifacts(self):
        partial = {"details_csv": {"relative_path": "job_details.csv", "sha256": "a" * 64,
            "size_bytes": 12, "record_count": 1, "format": "csv/details-v1"}}
        result = lifecycle.run_offline_lifecycle(RECORDS, status="IN_PROGRESS", manifest_overrides={"outputs": partial})
        self.assertEqual(result["stages"]["manifest_schema_v2"]["outcome"], "INVALID")
        self.assertEqual(result["stages"]["manifest_schema_v2"]["failure_code"], "OUTCOME_CONTRADICTION")
        self.assertEqual(result["aggregate_outcome"], "REJECTED")

    def test_native_verifier_faults_remain_visible_and_reject_complete_aggregate(self):
        original = compat.validate_for_component
        faults = {
            "conflicting_role": lambda manifest, evidence: manifest["outputs"].update(
                {"analysis_csv": manifest["outputs"].pop("details_csv")}),
            "wrong_size": lambda manifest, evidence: manifest["outputs"]["details_csv"].update(size_bytes=999),
            "malformed_digest": lambda manifest, evidence: manifest["outputs"]["details_csv"].update(sha256="z" * 64),
            "missing_evidence": lambda manifest, evidence: evidence.pop("details_csv"),
        }
        for label, mutate in faults.items():
            def injected(target, **kwargs):
                if target == "offline_verifier_v1" and kwargs.get("source_schema_version") == 1:
                    native = copy.deepcopy(kwargs["manifest"])
                    evidence = dict(kwargs["artifacts_by_role"])
                    mutate(native, evidence)
                    kwargs["manifest"] = native
                    kwargs["manifest_bytes"] = lifecycle._encode_unchecked(native)
                    kwargs["artifacts_by_role"] = evidence
                return original(target=target, **kwargs)
            with self.subTest(fault=label), patch("tools.offline_generation_lifecycle.compat.validate_for_component", side_effect=injected):
                result = lifecycle.run_offline_lifecycle(RECORDS, status="COMPLETE")
                verifier_stage = result["stages"]["offline_provenance_verifier"]
                self.assertNotEqual(verifier_stage["outcome"], "VERIFIED_DATA_ONLY")
                self.assertFalse(verifier_stage["accepted"])
                self.assertEqual(result["aggregate_outcome"], "REJECTED")
                self.assertFalse(result["production_selection_authorized"])

    def test_rejected_stage_cannot_be_overwritten_by_later_validators(self):
        original = compat.validate_for_component
        calls = []
        def reject_store_details(target, **kwargs):
            result = original(target=target, **kwargs)
            if target == "generation_store_v1" and kwargs.get("source_schema_version") == 1 and kwargs.get("manifest", {}).get("stage") == "job_details":
                calls.append("rejected_store_details")
                return {**result, "outcome": "REJECTED", "accepted": False, "failure_code": "INJECTED_STORE_REJECTION"}
            calls.append(f"{target}:{result['outcome']}")
            return result
        with patch("tools.offline_generation_lifecycle.compat.validate_for_component", side_effect=reject_store_details):
            result = lifecycle.run_offline_lifecycle(RECORDS, status="COMPLETE")
        self.assertIn("rejected_store_details", calls)
        self.assertEqual(calls.count("rejected_store_details"), 1, "rejected store validation is not retried through a fallback path")
        self.assertEqual(result["stages"]["generation_store"]["failure_code"], "INJECTED_STORE_REJECTION")
        self.assertEqual(result["stages"]["schema_v2_compatibility"]["outcome"], "VALID")
        self.assertEqual(result["aggregate_outcome"], "REJECTED")
        self.assertIn("generation_store", result["aggregate_failures"])

    def test_unexpected_compatibility_exception_is_preserved_as_error(self):
        original = compat.validate_for_component
        def explode_schema(target, **kwargs):
            if target == "schema_v2":
                raise RuntimeError("synthetic schema-fence fault")
            return original(target=target, **kwargs)
        with patch("tools.offline_generation_lifecycle.compat.validate_for_component", side_effect=explode_schema):
            result = lifecycle.run_offline_lifecycle(RECORDS, status="IN_PROGRESS")
        stage = result["stages"]["schema_v2_compatibility"]
        self.assertEqual(stage["outcome"], "ERROR")
        self.assertEqual(stage["exception_type"], "RuntimeError")
        self.assertEqual(result["aggregate_outcome"], "ERROR")

    def test_unexpected_dispatch_exception_at_each_validator_stage_fails_closed(self):
        original = compat.validate_for_component
        for target in ("schema_v2", "offline_verifier_v1", "generation_store_v1"):
            def fail_selected(actual_target, **kwargs):
                if actual_target == target:
                    raise RuntimeError(f"synthetic {target} dispatch fault")
                return original(target=actual_target, **kwargs)
            with self.subTest(target=target), patch("tools.offline_generation_lifecycle.compat.validate_for_component", side_effect=fail_selected):
                result = lifecycle.run_offline_lifecycle(RECORDS, status="COMPLETE")
                stage = {"schema_v2": "schema_v2_compatibility", "offline_verifier_v1": "offline_provenance_verifier", "generation_store_v1": "generation_store"}[target]
                self.assertEqual(result["stages"][stage]["outcome"], "ERROR")
                self.assertEqual(result["aggregate_outcome"], "ERROR")
                self.assertIs(result["production_selection_authorized"], False)
                self.assertIs(result["publication_authorized"], False)

    def test_unknown_lifecycle_status_raises_without_dispatch_or_success(self):
        with patch("tools.offline_generation_lifecycle.compat.validate_for_component") as dispatch:
            with self.assertRaisesRegex(ValueError, "unsupported lifecycle status"):
                lifecycle.run_offline_lifecycle(RECORDS, status="UNKNOWN")
        dispatch.assert_not_called()

    def test_analyzer_binding_byte_and_identifier_faults_remain_rejected(self):
        original = generation_store.validate_analyzer_input_binding
        def changed_bytes(analyzer, details, **kwargs):
            changed = bytearray(kwargs["details_artifact_bytes"])
            changed[-1] ^= 1
            kwargs["details_artifact_bytes"] = bytes(changed)
            return original(analyzer, details, **kwargs)
        def wrong_identifier(analyzer, details, **kwargs):
            analyzer = copy.deepcopy(analyzer)
            analyzer["input_generation"]["run_id"] = lifecycle.RUN_SOURCE
            return original(analyzer, details, **kwargs)
        def missing_reference(analyzer, details, **kwargs):
            analyzer = copy.deepcopy(analyzer)
            analyzer["input_generation"] = None
            return original(analyzer, details, **kwargs)
        for label, fault in (("changed_bytes", changed_bytes), ("wrong_identifier", wrong_identifier), ("missing_reference", missing_reference)):
            with self.subTest(fault=label), patch("tools.offline_generation_lifecycle.generation_store.validate_analyzer_input_binding", side_effect=fault):
                result = lifecycle.run_offline_lifecycle(RECORDS, status="COMPLETE")
                binding = result["stages"]["generation_store_analyzer_input_binding"]
                self.assertEqual(binding["outcome"], "REJECTED")
                self.assertFalse(binding["accepted"])
                self.assertEqual(binding["failure_code"], "GENERATION_VALIDATION_REJECTED")
                self.assertEqual(result["aggregate_outcome"], "REJECTED")

    def test_analyzer_binding_unexpected_exception_is_not_success(self):
        with patch("tools.offline_generation_lifecycle.generation_store.validate_analyzer_input_binding", side_effect=RuntimeError("synthetic binding fault")):
            result = lifecycle.run_offline_lifecycle(RECORDS, status="COMPLETE")
        self.assertEqual(result["stages"]["generation_store_analyzer_input_binding"]["outcome"], "ERROR")
        self.assertEqual(result["aggregate_outcome"], "ERROR")

    def test_consecutive_empty_and_failed_runs_do_not_inherit_previous_success(self):
        complete = lifecycle.run_offline_lifecycle(RECORDS, status="COMPLETE")
        empty = lifecycle.run_offline_lifecycle([], status="EMPTY")
        failed = lifecycle.run_offline_lifecycle(RECORDS, status="FAILED", dispositions=["FAILED", "FAILED"])
        repeated = lifecycle.run_offline_lifecycle(RECORDS, status="COMPLETE")
        self.assertEqual(complete, repeated)
        self.assertIsNone(empty["stages"]["synthetic_manifest_state"]["previous_generation"])
        self.assertEqual(empty["stages"]["synthetic_manifest_state"]["declared_output_roles"], [])
        self.assertEqual(empty["aggregate_outcome"], "NATIVE_CONTRACTS_VALIDATED_CROSS_VERSION_INCOMPATIBLE")
        self.assertIsNone(failed["stages"]["synthetic_manifest_state"]["previous_generation"])
        self.assertEqual(failed["aggregate_outcome"], "FAILED_NOT_AUTHORIZED")

    def test_missing_or_inconsistent_artifact_declarations_reject(self):
        result = lifecycle.run_offline_lifecycle(RECORDS, manifest_overrides={"outputs": {"details_csv": {}}})
        self.assertEqual(result["stages"]["manifest_schema_v2"]["outcome"], "INVALID")
        result = lifecycle.run_offline_lifecycle(RECORDS, manifest_overrides={"outputs": {"details_csv": {"relative_path": "job_details.csv", "sha256": "0" * 64, "size_bytes": 1, "record_count": 2, "format": "csv/details-v1"}, "diagnostics_json": {"relative_path": "job_details_diagnostics.json", "sha256": "0" * 64, "size_bytes": 2, "record_count": 0, "format": "json/diagnostics-v1"}}})
        self.assertEqual(result["stages"]["manifest_schema_v2"]["outcome"], "VALID")
        self.assertEqual(result["component_contract_compatibility"]["v2_to_verifier_v1"]["failure_code"], "SCHEMA_VERSION_MISMATCH")

    def test_inconsistent_occurrence_accounting_rejects(self):
        result = lifecycle.run_offline_lifecycle(RECORDS, manifest_overrides={
            "accounting": {"source_occurrences": 3, "processed_occurrences": 2, "intentional_skip_occurrences": 0, "failed_occurrences": 0, "output_rows": 2}
        })
        self.assertEqual(result["stages"]["manifest_schema_v2"]["failure_code"], "OCCURRENCE_ACCOUNTING_INVALID")

    def test_unexpected_validation_exception_is_structured(self):
        with patch("tools.offline_generation_lifecycle.schema.validate_manifest", side_effect=RuntimeError("synthetic validator fault")):
            result = lifecycle.run_offline_lifecycle(RECORDS)
        self.assertEqual(result["stages"]["manifest_schema_v2"]["failure_code"], "UNEXPECTED_VALIDATION_EXCEPTION")
        self.assertEqual(result["stages"]["manifest_schema_v2"]["exception_type"], "RuntimeError")
        self.assertEqual(result["aggregate_outcome"], "ERROR")

    def test_repeated_execution_is_deterministic(self):
        first = lifecycle.run_offline_lifecycle(RECORDS, status="PARTIAL", dispositions=["PROCESSED", "FAILED"])
        second = lifecycle.run_offline_lifecycle(RECORDS, status="PARTIAL", dispositions=["PROCESSED", "FAILED"])
        self.assertEqual(first, second)

    def test_production_selection_and_publication_are_explicitly_refused(self):
        result = lifecycle.run_offline_lifecycle(RECORDS)
        self.assertIs(result["production_selection_authorized"], False)
        self.assertIs(result["publication_authorized"], False)


if __name__ == "__main__":
    unittest.main()
