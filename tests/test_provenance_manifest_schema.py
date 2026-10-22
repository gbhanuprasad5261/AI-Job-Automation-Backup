"""Pure synthetic tests for the proposed canonical schema v2.

No production modules, project data, paths, or workflows are used.
"""
from __future__ import annotations

import copy
import hashlib
import unittest

from tools import provenance_manifest_schema as schema


RUN_SOURCE = "7c9d5c21-66eb-4ee7-84b8-2523d3bbf1d2"
RUN_DETAILS = "2eb56da5-e63b-4e6b-9d3c-b5abff7aa63b"
RUN_ANALYSIS = "3c7c5d21-66eb-4ee7-84b8-3523d3bbf1d2"
RUN_PRIOR = "4c7c5d21-66eb-4e6b-9d3c-b5abff7aa63b"
STARTED = "2026-10-18T12:00:00Z"
COMPLETED = "2026-10-18T12:01:00Z"


def _fp(data: bytes) -> dict:
    return {"sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data)}


def _output(role: str, data: bytes, rows: int) -> dict:
    path, fmt = schema.ROLE_PATH_FORMAT[role]
    return {
        "relative_path": path,
        "sha256": hashlib.sha256(data).hexdigest(),
        "size_bytes": len(data),
        "record_count": rows,
        "format": fmt,
    }


def _source(data: bytes, role="jobs_csv", rows=1) -> dict:
    return {
        "role": role,
        "sha256": hashlib.sha256(data).hexdigest(),
        "size_bytes": len(data),
        "record_count": rows,
        "encoding": "utf-8",
        "format": schema.ROLE_PATH_FORMAT[role][1],
    }


def _base(*, run_id=RUN_SOURCE, stage="source", status="COMPLETE") -> dict:
    return {
        "schema_version": schema.SCHEMA_VERSION,
        "run_id": run_id,
        "stage": stage,
        "status": status,
        "producer": {"id": "synthetic-fixture", "version": "test-v1"},
        "started_at": STARTED,
        "completed_at": None if status == "IN_PROGRESS" else COMPLETED,
        "source": None,
        "input_generation": None,
        "accounting": None,
        "occurrences": None,
        "outputs": {},
        "diagnostics": [],
        "failure": None,
        "previous_generation": None,
        "policy_dependencies": [],
        "extensions": {},
    }


def _source_manifest(*, status="COMPLETE", data=b"source row\\n", rows=1) -> dict:
    value = _base(status=status)
    value["source"] = _source(data, rows=rows)
    value["outputs"] = {"jobs_csv": _output("jobs_csv", data, rows)}
    if status == "EMPTY":
        value["source"] = _source(data, rows=0)
        value["outputs"] = {"jobs_csv": _output("jobs_csv", data, 0)}
    value["policy_dependencies"] = ["D1", "D2", "D13"]
    return value


def _reference(stage: str, run_id: str, status: str, role: str, data: bytes, rows: int, manifest_data=b"parent manifest") -> dict:
    return {
        "stage": stage,
        "run_id": run_id,
        "status": status,
        "manifest_sha256": hashlib.sha256(manifest_data).hexdigest(),
        "artifact_role": role,
        "artifact_sha256": hashlib.sha256(data).hexdigest(),
        "size_bytes": len(data),
        "record_count": rows,
        "format": schema.ROLE_PATH_FORMAT[role][1],
    }


def _details_manifest(*, status="COMPLETE", source_data=b"source row\\n", source_rows=1,
                      input_status="COMPLETE", processed=1, skipped=0, failed=0,
                      details_data=b"details row\\n", diagnostics_data=b"[]"):
    value = _base(run_id=RUN_DETAILS, stage="job_details", status=status)
    value["source"] = _source(source_data, rows=source_rows)
    value["input_generation"] = _reference(
        "source", RUN_SOURCE, input_status, "jobs_csv", source_data, source_rows
    )
    if status in {"COMPLETE", "PARTIAL"}:
        value["outputs"] = {
            "details_csv": _output("details_csv", details_data, processed),
            "diagnostics_json": _output("diagnostics_json", diagnostics_data, 0),
        }
    source_sha = value["source"]["sha256"]
    rows = []
    for ordinal in range(1, source_rows + 1):
        disposition = "PROCESSED" if ordinal <= processed else ("INTENTIONAL_SKIP" if ordinal <= processed + skipped else "FAILED")
        rows.append({
            "ordinal": ordinal,
            "occurrence_key": f"{source_sha}:{ordinal}",
            "disposition": disposition,
            "logical_identity": f"job-{ordinal}",
            "reason_code": "POLICY_FILTER" if disposition == "INTENTIONAL_SKIP" else None,
            "policy_rule_id": "rule-v1" if disposition == "INTENTIONAL_SKIP" else None,
            "retained_occurrence_key": None,
            "error_code": "EXTRACTION_ERROR" if disposition == "FAILED" else None,
            "quality_code": None,
            "output_row": ordinal if disposition == "PROCESSED" else None,
        })
    value["accounting"] = {
        "source_occurrences": source_rows,
        "processed_occurrences": processed,
        "intentional_skip_occurrences": skipped,
        "failed_occurrences": failed,
        "output_rows": processed,
    }
    value["occurrences"] = rows
    if status == "EMPTY":
        value["outputs"] = {}
        value["accounting"] = {
            "source_occurrences": source_rows,
            "processed_occurrences": processed,
            "intentional_skip_occurrences": skipped,
            "failed_occurrences": failed,
            "output_rows": 0,
        }
    return value


def _analysis_manifest(*, details_data=b"details row\\n", details_rows=1,
                       source_data=b"details row\\n", status="COMPLETE",
                       analysis_data=b"analysis row\\n"):
    value = _base(run_id=RUN_ANALYSIS, stage="job_analyzer", status=status)
    value["source"] = _source(source_data, role="details_csv", rows=details_rows)
    value["input_generation"] = _reference(
        "job_details", RUN_DETAILS, "COMPLETE", "details_csv", details_data, details_rows
    )
    if status == "COMPLETE":
        value["outputs"] = {"analysis_csv": _output("analysis_csv", analysis_data, details_rows)}
    value["accounting"] = {
        "source_occurrences": details_rows,
        "processed_occurrences": details_rows,
        "intentional_skip_occurrences": 0,
        "failed_occurrences": 0,
        "output_rows": details_rows,
    }
    sha = value["source"]["sha256"]
    value["occurrences"] = [{
        "ordinal": 1,
        "occurrence_key": f"{sha}:1",
        "disposition": "PROCESSED",
        "logical_identity": "job-1",
        "reason_code": None,
        "policy_rule_id": None,
        "retained_occurrence_key": None,
        "error_code": None,
        "quality_code": None,
        "output_row": 1,
    }] if details_rows else []
    return value


class CanonicalManifestSchemaTests(unittest.TestCase):
    def test_valid_synthetic_source_is_schema_valid_but_never_authorized(self):
        result = schema.validate_manifest(_source_manifest())
        self.assertTrue(result.schema_valid)
        self.assertFalse(result.policy_resolved)
        self.assertEqual(result.authorization, "NOT_AUTHORIZED")
        self.assertEqual(result.unresolved_decisions, tuple(f"D{i}" for i in range(1, 14)))

    def test_valid_details_and_analysis_lineage_shapes(self):
        details = _details_manifest()
        analysis = _analysis_manifest()
        self.assertTrue(schema.validate_manifest(details).schema_valid)
        self.assertTrue(schema.validate_manifest(analysis).schema_valid)

    def test_missing_top_level_field_rejects(self):
        value = _source_manifest()
        del value["producer"]
        with self.assertRaises(schema.SchemaValidationError) as caught:
            schema.validate_manifest(value)
        self.assertEqual(caught.exception.code, "FIELD_SET_INVALID")

    def test_unknown_schema_version_rejects(self):
        value = _source_manifest()
        value["schema_version"] = 99
        self._assert_code(value, "UNKNOWN_SCHEMA_VERSION")

    def test_invalid_identifier_rejects(self):
        value = _source_manifest()
        value["run_id"] = RUN_SOURCE.upper()
        self._assert_code(value, "IDENTIFIER_INVALID")

    def test_wrong_types_and_negative_sizes_or_counts_reject(self):
        for mutate, code in (
            (lambda m: m.update(schema_version=True), "UNKNOWN_SCHEMA_VERSION"),
            (lambda m: m["source"].update(size_bytes=-1), "COUNT_INVALID"),
            (lambda m: m["source"].update(record_count=True), "COUNT_INVALID"),
            (lambda m: m["producer"].update(id=17), "FIELD_TYPE_INVALID"),
        ):
            value = _source_manifest()
            mutate(value)
            self._assert_code(value, code)

    def test_invalid_timestamp_and_order_reject(self):
        value = _source_manifest()
        value["started_at"] = "2026-02-30T12:00:00Z"
        self._assert_code(value, "TIMESTAMP_INVALID")
        value = _source_manifest()
        value["completed_at"] = "2026-10-18T11:59:59Z"
        self._assert_code(value, "TIMESTAMP_ORDER_INVALID")

    def test_unknown_stage_or_status_reject(self):
        value = _source_manifest()
        value["stage"] = "unknown"
        self._assert_code(value, "STAGE_INVALID")
        value = _source_manifest()
        value["status"] = "UNKNOWN"
        self._assert_code(value, "STATUS_INVALID")

    def test_missing_required_artifact_role_rejects(self):
        value = _source_manifest()
        value["outputs"] = {}
        self._assert_code(value, "REQUIRED_ARTIFACT_MISSING")

    def test_duplicate_role_path_or_noncanonical_artifact_path_rejects(self):
        value = _details_manifest()
        value["outputs"]["details_csv"]["relative_path"] = "../job_details.csv"
        self._assert_code(value, "ARTIFACT_PATH_INVALID")
        value = _details_manifest()
        value["outputs"]["diagnostics_json"]["relative_path"] = "job_details.csv"
        self._assert_code(value, "ARTIFACT_PATH_INVALID")

    def test_duplicate_artifact_role_key_in_json_rejects(self):
        raw = b'{"schema_version":2,"outputs":{"jobs_csv":{},"jobs_csv":{}}}'
        with self.assertRaises(schema.SchemaValidationError) as caught:
            schema.parse_manifest(raw)
        self.assertEqual(caught.exception.code, "DUPLICATE_JSON_KEY")

    def test_invalid_artifact_hash_format_and_negative_size_reject(self):
        value = _source_manifest()
        value["outputs"]["jobs_csv"]["sha256"] = "x" * 64
        self._assert_code(value, "FINGERPRINT_INVALID")
        value = _source_manifest()
        value["outputs"]["jobs_csv"]["size_bytes"] = -1
        self._assert_code(value, "COUNT_INVALID")

    def test_details_source_to_source_generation_mismatch_rejects(self):
        value = _details_manifest()
        value["input_generation"]["artifact_sha256"] = "0" * 64
        self._assert_code(value, "GENERATION_REFERENCE_CONFLICT")

    def test_details_to_analysis_lineage_mismatch_rejects(self):
        value = _analysis_manifest(source_data=b"different bytes\\n")
        self._assert_code(value, "GENERATION_REFERENCE_CONFLICT")

    def test_wrong_upstream_stage_and_status_reject(self):
        value = _details_manifest()
        value["input_generation"]["stage"] = "job_analyzer"
        self._assert_code(value, "GENERATION_REFERENCE_CONFLICT")
        value = _details_manifest()
        value["input_generation"]["status"] = "PARTIAL"
        self._assert_code(value, "GENERATION_REFERENCE_CONFLICT")

    def test_malformed_or_inconsistent_accounting_rejects(self):
        value = _details_manifest()
        value["accounting"]["processed_occurrences"] = 2
        self._assert_code(value, "OCCURRENCE_ACCOUNTING_INVALID")
        value = _details_manifest()
        del value["accounting"]["output_rows"]
        self._assert_code(value, "FIELD_SET_INVALID")

    def test_occurrence_ledger_must_cover_each_source_row_and_output_row(self):
        value = _details_manifest()
        value["occurrences"] = []
        self._assert_code(value, "OCCURRENCE_ACCOUNTING_INVALID")
        value = _details_manifest()
        value["occurrences"][0]["output_row"] = 2
        self._assert_code(value, "OCCURRENCE_OUTPUT_MISMATCH")

    def test_contradictory_complete_status_rejects(self):
        value = _details_manifest(status="COMPLETE", source_rows=1, processed=0, skipped=0, failed=1)
        self._assert_code(value, "OUTCOME_CONTRADICTION")

    def test_empty_source_has_snapshot_but_no_candidate_rows(self):
        value = _source_manifest(status="EMPTY", data=b"header\\n", rows=0)
        result = schema.validate_manifest(value)
        self.assertTrue(result.schema_valid)
        empty_details = _details_manifest(status="EMPTY", source_data=b"header\\n", source_rows=0,
                                          input_status="EMPTY", processed=0, skipped=0, failed=0)
        self.assertTrue(schema.validate_manifest(empty_details).schema_valid)

    def test_in_progress_is_nonterminal_and_non_authorizing(self):
        value = _base(status="IN_PROGRESS")
        result = schema.validate_manifest(value)
        self.assertEqual(result.authorization, "NOT_AUTHORIZED")
        value["outputs"] = {"jobs_csv": {}}
        self._assert_code(value, "OUTCOME_CONTRADICTION")

    def test_partial_and_all_skipped_remain_explicitly_policy_unresolved(self):
        partial = _details_manifest(status="PARTIAL", source_rows=2, processed=1, skipped=0, failed=1)
        result = schema.validate_manifest(partial)
        self.assertFalse(result.policy_resolved)
        all_skipped = _details_manifest(source_rows=1, processed=0, skipped=1, failed=0)
        result = schema.validate_manifest(all_skipped)
        self.assertIn("D6_ALL_SKIPPED_COMPLETE_POLICY_OPEN", result.unresolved_findings)

    def test_diagnostics_must_reference_declared_roles_and_occurrences(self):
        value = _details_manifest()
        value["diagnostics"] = [{"code": "WARN", "occurrence_key": "missing", "artifact_role": "diagnostics_json"}]
        self._assert_code(value, "DIAGNOSTICS_REFERENCE_INVALID")
        value = _details_manifest()
        value["diagnostics"] = [{"code": "WARN", "occurrence_key": None, "artifact_role": "not_a_role"}]
        self._assert_code(value, "DIAGNOSTICS_REFERENCE_INVALID")

    def test_previous_generation_self_reference_rejects_and_source_mismatch_stays_open(self):
        value = _source_manifest()
        value["previous_generation"] = {
            "stage": "source",
            "run_id": RUN_SOURCE,
            "status": "COMPLETE",
            "manifest_sha256": "a" * 64,
            "source_sha256": value["source"]["sha256"],
        }
        self._assert_code(value, "GENERATION_REFERENCE_CONFLICT")
        value = _source_manifest()
        value["previous_generation"] = {
            "stage": "source",
            "run_id": RUN_PRIOR,
            "status": "COMPLETE",
            "manifest_sha256": "a" * 64,
            "source_sha256": "b" * 64,
        }
        result = schema.validate_manifest(value)
        self.assertIn("D10_SOURCE_MATCH_POLICY_OPEN", result.unresolved_findings)
        self.assertEqual(result.authorization, "NOT_AUTHORIZED")

    def test_unsupported_policy_dependencies_and_extensions_reject(self):
        value = _source_manifest()
        value["policy_dependencies"] = ["D99"]
        self._assert_code(value, "UNSUPPORTED_POLICY_EXTENSION")
        value = _source_manifest()
        value["extensions"] = {"unapproved": {"value": 1}}
        self._assert_code(value, "UNSUPPORTED_POLICY_EXTENSION")

    def test_unknown_duplicate_and_malformed_json_reject(self):
        raw = schema.serialize_manifest(_source_manifest())
        parsed, result = schema.parse_manifest(raw)
        self.assertEqual(parsed, _source_manifest())
        self.assertFalse(result.policy_resolved)
        duplicate = b'{"schema_version":2,"schema_version":2}'
        with self.assertRaises(schema.SchemaValidationError) as caught:
            schema.parse_manifest(duplicate)
        self.assertEqual(caught.exception.code, "DUPLICATE_JSON_KEY")
        with self.assertRaises(schema.SchemaValidationError):
            schema.parse_manifest(b"\xff")

    def test_deterministic_serialization_and_exact_supplied_byte_fingerprint(self):
        value = _source_manifest()
        one = schema.serialize_manifest(value)
        two = schema.serialize_manifest(copy.deepcopy(value))
        self.assertEqual(one, two)
        self.assertEqual(schema.fingerprint_supplied_bytes(b"abc"), _fp(b"abc"))
        self.assertNotEqual(schema.fingerprint_supplied_bytes(b"abc"), schema.fingerprint_supplied_bytes(b"abd"))

    def test_schema_acceptance_does_not_verify_artifact_bytes_or_source_authenticity(self):
        value = _source_manifest()
        value["source"]["sha256"] = "a" * 64
        value["outputs"]["jobs_csv"]["sha256"] = "a" * 64
        result = schema.validate_manifest(value)
        self.assertTrue(result.schema_valid)
        self.assertFalse(result.policy_resolved)
        self.assertEqual(result.authorization, "NOT_AUTHORIZED")

    def _assert_code(self, value, expected):
        with self.assertRaises(schema.SchemaValidationError) as caught:
            schema.validate_manifest(value)
        self.assertEqual(caught.exception.code, expected)


if __name__ == "__main__":
    unittest.main()

