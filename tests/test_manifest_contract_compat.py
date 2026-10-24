"""Synthetic conformance tests for the explicit no-conversion contract fence."""
from __future__ import annotations

import copy
import hashlib
import json
import unittest
from unittest.mock import patch

from tools import manifest_contract_compat as compat
from tools import offline_provenance_verifier as verifier
from tools import provenance_manifest_schema as schema
import pipeline_generation_store as store


RUN = "7c9d5c21-66eb-4ee7-84b8-2523d3bbf1d2"
STARTED = "2026-10-18T12:00:00Z"
COMPLETED = "2026-10-18T12:01:00Z"
SOURCE_DATA = b"Title,Company,Location,Easy Apply,Actively Reviewing,Link\n"


def _fp(data: bytes) -> dict:
    return {"sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data)}


def _encode(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _v2_source(status="EMPTY") -> dict:
    data = SOURCE_DATA
    fp = _fp(data)
    path, fmt = schema.ROLE_PATH_FORMAT["jobs_csv"]
    return {
        "schema_version": 2,
        "run_id": RUN,
        "stage": "source",
        "status": status,
        "producer": {"id": "synthetic", "version": "1"},
        "started_at": STARTED,
        "completed_at": COMPLETED,
        "source": {"role": "jobs_csv", **fp, "record_count": 0, "encoding": "utf-8", "format": fmt},
        "input_generation": None,
        "accounting": None,
        "occurrences": None,
        "outputs": {"jobs_csv": {"relative_path": path, **fp, "record_count": 0, "format": fmt}},
        "diagnostics": [],
        "failure": None,
        "previous_generation": None,
        "policy_dependencies": [],
        "extensions": {},
    }


def _verifier_v1_empty_source() -> tuple[bytes, dict[str, bytes]]:
    manifest = {
        "schema_version": 1, "run_id": RUN, "stage": "source", "status": "EMPTY",
        "producer": {"id": "synthetic", "version": "1"}, "started_at": STARTED,
        "completed_at": COMPLETED,
        "source": {"role": "jobs_csv", **_fp(SOURCE_DATA), "record_count": 0, "encoding": "utf-8", "format": "csv/jobs-v1"},
        "input_generation": None, "accounting": None, "occurrences": None,
        "outputs": {"jobs_csv": {"relative_path": "jobs.csv", **_fp(SOURCE_DATA), "record_count": 0, "format": "csv/jobs-v1"}},
        "failure": None,
    }
    return _encode(manifest), {"jobs_csv": SOURCE_DATA}


def _store_v1_details() -> dict:
    details = b"synthetic details bytes"
    diagnostics = b"[]"
    return {
        "schema_version": 1,
        "run_id": "2eb56da5-e63b-4e6b-9d3c-b5abff7aa63b",
        "stage": "job_details",
        "status": "COMPLETE",
        "started_at": STARTED,
        "completed_at": COMPLETED,
        "source": {"role": "jobs.csv", **_fp(SOURCE_DATA), "record_count": 1},
        "input_generation": None,
        "accounting": {"source_records": 1, "processed_records": 1, "intentionally_skipped_records": 0, "failed_records": 0},
        "outputs": {
            "details_csv": {"relative_path": "job_details.csv", **_fp(details)},
            "diagnostics_json": {"relative_path": "job_details_diagnostics.json", **_fp(diagnostics)},
        },
        "failure": None,
    }


class ManifestContractCompatibilityTests(unittest.TestCase):
    def test_valid_schema_v2_input_remains_non_authorizing(self):
        result = compat.validate_for_component(_v2_source(), target="schema_v2", source_schema_version=2)
        self.assertEqual(result["outcome"], "VALID")
        self.assertTrue(result["accepted"])
        self.assertEqual(result["authorization"], "NOT_AUTHORIZED")
        self.assertEqual(result["findings"]["unresolved_decisions"], [f"D{i}" for i in range(1, 14)])
        self.assertFalse(result["findings"]["external_lineage_verified"])

    def test_valid_native_inputs_for_both_existing_v1_validators(self):
        verifier_bytes, artifacts = _verifier_v1_empty_source()
        verifier_result = compat.validate_for_component(
            target="offline_verifier_v1", source_schema_version=1, manifest_bytes=verifier_bytes,
            artifacts_by_role=artifacts, expected_stage="source",
        )
        self.assertEqual(verifier_result["outcome"], "EMPTY_DATA_ONLY")
        self.assertTrue(verifier_result["accepted"])
        self.assertFalse(verifier_result["eligible"])
        self.assertEqual(verifier_result["authorization"], "NOT_AUTHORIZED")

        store_result = compat.validate_for_component(
            _store_v1_details(), target="generation_store_v1", source_schema_version=1,
        )
        self.assertEqual(store_result["outcome"], "VALID")
        self.assertTrue(store_result["accepted"])
        self.assertEqual(store_result["authorization"], "NOT_AUTHORIZED")

    def test_cross_version_conversion_is_explicitly_rejected_in_both_directions(self):
        canonical = _v2_source()
        verifier_result = compat.validate_for_component(
            canonical, target="offline_verifier_v1", source_schema_version=2,
            manifest_bytes=_encode(canonical), artifacts_by_role={"jobs_csv": SOURCE_DATA},
        )
        store_result = compat.validate_for_component(
            canonical, target="generation_store_v1", source_schema_version=2,
        )
        reverse_result = compat.validate_for_component(
            _store_v1_details(), target="schema_v2", source_schema_version=1,
        )
        for result in (verifier_result, store_result, reverse_result):
            self.assertEqual(result["failure_code"], "SCHEMA_VERSION_MISMATCH")
            self.assertFalse(result["accepted"])
            self.assertEqual(result["authorization"], "NOT_AUTHORIZED")

    def test_declared_version_must_match_actual_version(self):
        result = compat.validate_for_component(_v2_source(), target="schema_v2", source_schema_version=1)
        self.assertEqual(result["failure_code"], "DECLARED_VERSION_MISMATCH")

    def test_unknown_and_missing_fields_are_rejected_by_native_schema(self):
        unknown = _v2_source()
        unknown["unreviewed"] = True
        result = compat.validate_for_component(unknown, target="schema_v2", source_schema_version=2)
        self.assertEqual(result["failure_code"], "FIELD_SET_INVALID")
        missing = _v2_source()
        del missing["producer"]
        result = compat.validate_for_component(missing, target="schema_v2", source_schema_version=2)
        self.assertEqual(result["failure_code"], "FIELD_SET_INVALID")

    def test_unsupported_status_is_rejected_before_component_dispatch(self):
        manifest = _v2_source()
        manifest["status"] = "UNKNOWN"
        result = compat.validate_for_component(manifest, target="schema_v2", source_schema_version=2)
        self.assertEqual(result["failure_code"], "STATUS_UNSUPPORTED")

    def test_missing_artifact_metadata_is_not_filled_or_inferred(self):
        manifest = _v2_source()
        del manifest["outputs"]["jobs_csv"]["sha256"]
        result = compat.validate_for_component(manifest, target="schema_v2", source_schema_version=2)
        self.assertEqual(result["failure_code"], "FIELD_SET_INVALID")

    def test_verifier_native_in_progress_remains_incomplete(self):
        raw, _ = _verifier_v1_empty_source()
        manifest = json.loads(raw)
        manifest.update(status="IN_PROGRESS", completed_at=None, source=None, outputs={}, accounting=None, occurrences=None)
        in_progress = _encode(manifest)
        result = compat.validate_for_component(
            target="offline_verifier_v1", source_schema_version=1, manifest_bytes=in_progress,
            artifacts_by_role={}, expected_stage="source",
        )
        self.assertEqual(result["outcome"], "INCOMPLETE")
        self.assertFalse(result["accepted"])

    def test_failed_canonical_manifest_stays_schema_valid_but_non_authorizing(self):
        # The lifecycle's FAILED fixture is the existing canonical v2 native shape.
        from tools import offline_generation_lifecycle as lifecycle
        failed = lifecycle.run_offline_lifecycle(
            ['"Synthetic 1",Example,Offline,No,No,https://example.test/1\n'],
            status="FAILED", dispositions=["FAILED"],
        )
        self.assertEqual(failed["stages"]["manifest_schema_v2"]["outcome"], "VALID")
        self.assertEqual(failed["stages"]["manifest_schema_v2"]["authorization"], "NOT_AUTHORIZED")

    def test_rollback_metadata_does_not_authorize_rollback(self):
        event = {"authorized_by": "synthetic", "authorization_ref": "synthetic-ref", "at": COMPLETED,
                 "reason": "synthetic-only", "source_sha256": "a" * 64}
        result = verifier.verify_rollback_request(event)
        self.assertEqual(result.failure_code, "ROLLBACK_AUTHORITY_UNVERIFIABLE")
        self.assertFalse(result.accepted)
        self.assertFalse(result.eligible)

    def test_unexpected_validation_exception_is_explicit_and_not_accepted(self):
        with patch("tools.manifest_contract_compat.schema.validate_manifest", side_effect=RuntimeError("synthetic fault")):
            result = compat.validate_for_component(_v2_source(), target="schema_v2", source_schema_version=2)
        self.assertEqual(result["failure_code"], "UNEXPECTED_VALIDATION_EXCEPTION")
        self.assertFalse(result["accepted"])

    def test_results_are_deterministic(self):
        manifest = _v2_source()
        first = compat.validate_for_component(manifest, target="schema_v2", source_schema_version=2)
        second = compat.validate_for_component(copy.deepcopy(manifest), target="schema_v2", source_schema_version=2)
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
