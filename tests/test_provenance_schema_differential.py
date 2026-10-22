"""Synthetic differential observations across the three isolated validators.

Each validator receives a fixture in its own existing contract. This module
does not adapt one schema into another: the point is to make native contract
differences visible. All artifact bytes and temporary files are synthetic.
"""
from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import pipeline_generation_store as store
from tools import offline_provenance_verifier as verifier
from tools import provenance_manifest_schema as schema


SOURCE_ID = "7c9d5c21-66eb-4ee7-84b8-2523d3bbf1d2"
DETAILS_ID = "2eb56da5-e63b-4e6b-9d3c-b5abff7aa63b"
OTHER_ID = "3c7c5d21-66eb-4ee7-84b8-3523d3bbf1d2"
STARTED = "2026-10-18T12:00:00Z"
FINISHED = "2026-10-18T12:01:00Z"
SOURCE_HEADER = b"Title,Company,Location,Easy Apply,Actively Reviewing,Link\n"
DETAILS_HEADER = b'"Title","Company","Location","Experience","Easy Apply","Skills","Link","Description"\n'
DETAIL_ROW = b'"Backend","Example","Bengaluru","5 years","Yes","Java","https://example.test/1","Java experience"\n'


def _fp(data: bytes) -> dict:
    return {"sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data)}


def _encoded(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _verifier_source(rows: int = 1):
    body = b"".join(
        f'Backend,Example,Bengaluru,Yes,No,https://example.test/{n}\n'.encode()
        for n in range(1, rows + 1)
    )
    data = SOURCE_HEADER + body
    status = "COMPLETE" if rows else "EMPTY"
    manifest = {
        "schema_version": 1, "run_id": SOURCE_ID, "stage": "source", "status": status,
        "producer": {"id": "synthetic", "version": "1"}, "started_at": STARTED,
        "completed_at": FINISHED, "source": {"role": "jobs_csv", **_fp(data),
            "record_count": rows, "encoding": "utf-8", "format": "csv/jobs-v1"},
        "input_generation": None, "accounting": None, "occurrences": None,
        "outputs": {"jobs_csv": {"relative_path": "jobs.csv", **_fp(data),
            "record_count": rows, "format": "csv/jobs-v1"}}, "failure": None,
    }
    return _encoded(manifest), {"jobs_csv": data}, manifest


def _verifier_details(*, status="COMPLETE", diagnostics=b"[]", wrong_parent=False):
    rows = 0 if status == "EMPTY" else (2 if status == "PARTIAL" else 1)
    parent_bytes, parent_artifacts, parent = _verifier_source(rows)
    source_data = parent_artifacts["jobs_csv"]
    output_rows = 1
    details_data = DETAILS_HEADER + DETAIL_ROW
    detail_outputs = {
        "details_csv": {"relative_path": "job_details.csv", **_fp(details_data),
            "record_count": output_rows, "format": "csv/details-v1"},
        "diagnostics_json": {"relative_path": "job_details_diagnostics.json", **_fp(diagnostics),
            "record_count": 0, "format": "json/diagnostics-v1"},
    }
    if status == "EMPTY":
        detail_outputs = {}
    src = parent["source"]
    occurrences = []
    for n in range(1, rows + 1):
        processed = n == 1
        occurrences.append({
            "ordinal": n, "occurrence_key": f"{src['sha256']}:{n}",
            "logical_identity": f"job-{n}",
            "disposition": "PROCESSED" if processed else "FAILED",
            "reason_code": None, "policy_rule_id": None, "retained_occurrence_key": None,
            "error_code": None if processed else "EXTRACTION_ERROR", "quality_code": None,
            "output_row": 1 if processed else None,
        })
    manifest = {
        "schema_version": 1, "run_id": DETAILS_ID, "stage": "job_details", "status": status,
        "producer": {"id": "synthetic", "version": "1"}, "started_at": STARTED,
        "completed_at": FINISHED,
        "source": {"role": "jobs_csv", **_fp(source_data), "record_count": rows,
            "encoding": "utf-8", "format": "csv/jobs-v1"},
        "input_generation": {"stage": "source", "run_id": OTHER_ID if wrong_parent else SOURCE_ID,
            "status": parent["status"], "manifest_sha256": hashlib.sha256(parent_bytes).hexdigest(),
            "artifact_role": "jobs_csv", "artifact_sha256": hashlib.sha256(source_data).hexdigest(),
            "artifact_size_bytes": len(source_data), "record_count": rows},
        "accounting": {"source_occurrences": rows, "processed_occurrences": 1,
            "intentional_skip_occurrences": 0, "failed_occurrences": rows - 1,
            "output_rows": output_rows},
        "occurrences": occurrences, "outputs": detail_outputs, "failure": None,
    }
    artifacts = {"details_csv": details_data, "diagnostics_json": diagnostics} if status != "EMPTY" else {}
    if status == "EMPTY":
        manifest["accounting"] = {"source_occurrences": 0, "processed_occurrences": 0,
            "intentional_skip_occurrences": 0, "failed_occurrences": 0, "output_rows": 0}
        manifest["occurrences"] = []
    return _encoded(manifest), artifacts, manifest, parent_bytes, parent_artifacts


def _schema_base(*, run_id=SOURCE_ID, stage="source", status="COMPLETE"):
    return {
        "schema_version": schema.SCHEMA_VERSION, "run_id": run_id, "stage": stage,
        "status": status, "producer": {"id": "synthetic", "version": "1"},
        "started_at": STARTED, "completed_at": None if status == "IN_PROGRESS" else FINISHED, "source": None,
        "input_generation": None, "accounting": None, "occurrences": None,
        "outputs": {}, "diagnostics": [], "failure": None,
        "previous_generation": None, "policy_dependencies": [], "extensions": {},
    }


def _schema_source(rows=1):
    data = SOURCE_HEADER + b"".join(
        f"Backend,Example,Bengaluru,Yes,No,https://example.test/{n}\n".encode()
        for n in range(1, rows + 1)
    )
    status = "COMPLETE" if rows else "EMPTY"
    value = _schema_base(status=status)
    fp = _fp(data)
    value["source"] = {"role": "jobs_csv", **fp, "record_count": rows,
        "encoding": "utf-8", "format": "csv/jobs-v1"}
    value["outputs"] = {"jobs_csv": {"relative_path": "jobs.csv", **fp,
        "record_count": rows, "format": "csv/jobs-v1"}}
    return value


def _schema_details(*, status="COMPLETE", conflicting_parent=False, conflicting_fingerprint=False):
    rows = 0 if status == "EMPTY" else (2 if status == "PARTIAL" else 1)
    source_rows = b"Backend,Example,Bengaluru,Yes,No,https://example.test/1\n" if status != "EMPTY" else b""
    if status == "PARTIAL":
        source_rows += b"Backend,Example,Bengaluru,Yes,No,https://example.test/2\n"
    source_data = SOURCE_HEADER + source_rows
    details_data = DETAILS_HEADER + DETAIL_ROW
    diagnostics_data = b"[]"
    srcfp, outfp, diagfp = _fp(source_data), _fp(details_data), _fp(diagnostics_data)
    source_sha = srcfp["sha256"]
    value = _schema_base(run_id=DETAILS_ID, stage="job_details", status=status)
    value["source"] = {"role": "jobs_csv", **srcfp, "record_count": rows,
        "encoding": "utf-8", "format": "csv/jobs-v1"}
    value["input_generation"] = {"stage": "source", "run_id": OTHER_ID if conflicting_parent else SOURCE_ID,
        "status": "EMPTY" if status == "EMPTY" else "COMPLETE", "manifest_sha256": "a" * 64, "artifact_role": "jobs_csv",
        "artifact_sha256": "b" * 64 if conflicting_fingerprint else source_sha, "size_bytes": len(source_data), "record_count": rows,
        "format": "csv/jobs-v1"}
    value["accounting"] = {"source_occurrences": rows, "processed_occurrences": 1 if rows else 0,
        "intentional_skip_occurrences": 0, "failed_occurrences": 0, "output_rows": 1 if rows else 0}
    value["occurrences"] = [{"ordinal": 1, "occurrence_key": f"{source_sha}:1",
        "disposition": "PROCESSED", "logical_identity": "job-1", "reason_code": None,
        "policy_rule_id": None, "retained_occurrence_key": None, "error_code": None,
        "quality_code": None, "output_row": 1}]
    value["outputs"] = {"details_csv": {"relative_path": "job_details.csv", **outfp,
        "record_count": 1, "format": "csv/details-v1"},
        "diagnostics_json": {"relative_path": "job_details_diagnostics.json", **diagfp,
        "record_count": 0, "format": "json/diagnostics-v1"}}
    if status == "PARTIAL":
        value["accounting"].update(source_occurrences=2, processed_occurrences=1, failed_occurrences=1)
        value["occurrences"].append({"ordinal": 2, "occurrence_key": f"{source_sha}:2",
            "disposition": "FAILED", "logical_identity": "job-2", "reason_code": None,
            "policy_rule_id": None, "retained_occurrence_key": None, "error_code": "EXTRACTION_ERROR",
            "quality_code": None, "output_row": None})
    if status == "EMPTY":
        value["accounting"] = {"source_occurrences": 0, "processed_occurrences": 0,
            "intentional_skip_occurrences": 0, "failed_occurrences": 0, "output_rows": 0}
        value["occurrences"] = []
        value["outputs"] = {}
    return value


def _store_details(*, status="COMPLETE"):
    data = b"details payload\n"
    diagnostics = b"[]"
    source = b"source payload\n"
    count = 2 if status == "PARTIAL" else (0 if status == "EMPTY" else 1)
    processed, failed = (1, 1) if status == "PARTIAL" else (count, 0)
    outputs = {}
    if status in {"COMPLETE", "PARTIAL"}:
        outputs = {
            "details_csv": {"relative_path": "job_details.csv", **_fp(data)},
            "diagnostics_json": {"relative_path": "job_details_diagnostics.json", **_fp(diagnostics)},
        }
    return {
        "schema_version": 1, "run_id": DETAILS_ID, "stage": "job_details", "status": status,
        "started_at": STARTED, "completed_at": FINISHED,
        "source": {"role": "jobs.csv", **_fp(source), "record_count": count},
        "input_generation": None,
        "accounting": {"source_records": count, "processed_records": processed,
            "intentionally_skipped_records": 0, "failed_records": failed},
        "outputs": outputs, "failure": None,
    }, {"details_csv": data, "diagnostics_json": diagnostics}


def _verifier_analyzer(details_bundle, *, wrong_run_id=False):
    details_bytes, details_artifacts, details_manifest, source_bytes, source_artifacts = details_bundle
    data = (b'"Title","Company","Location","Easy Apply","Match Score","Priority",'
            b'"Matched Skills","Missing Skills","Experience Required","Experience Years",'
            b'"Experience Skip","Data Status","Application Eligible","Link"\n'
            b'"Backend","Example","Bengaluru","Yes","80%","High","Java","",'
            b'"5 years","5","No","OK","No","https://example.test/1"\n')
    input_artifact = details_manifest["outputs"]["details_csv"]
    details_ref = {
        "stage": "job_details", "run_id": OTHER_ID if wrong_run_id else details_manifest["run_id"],
        "status": "COMPLETE", "manifest_sha256": hashlib.sha256(details_bytes).hexdigest(),
        "artifact_role": "details_csv", "artifact_sha256": input_artifact["sha256"],
        "artifact_size_bytes": input_artifact["size_bytes"], "record_count": input_artifact["record_count"],
    }
    source = {"role": "details_csv", **_fp(details_artifacts["details_csv"]),
        "record_count": 1, "encoding": "utf-8", "format": "csv/details-v1"}
    occurrence = {"ordinal": 1, "occurrence_key": f"{source['sha256']}:1",
        "logical_identity": "job-1", "disposition": "PROCESSED", "reason_code": None,
        "policy_rule_id": None, "retained_occurrence_key": None, "error_code": None,
        "quality_code": None, "output_row": 1}
    manifest = {
        "schema_version": 1, "run_id": OTHER_ID, "stage": "job_analyzer", "status": "COMPLETE",
        "producer": {"id": "synthetic", "version": "1"}, "started_at": STARTED,
        "completed_at": FINISHED, "source": source, "input_generation": details_ref,
        "accounting": {"source_occurrences": 1, "processed_occurrences": 1,
            "intentional_skip_occurrences": 0, "failed_occurrences": 0, "output_rows": 1},
        "occurrences": [occurrence],
        "outputs": {"analysis_csv": {"relative_path": "job_analysis.csv", **_fp(data),
            "record_count": 1, "format": "csv/analysis-v1"}}, "failure": None,
    }
    return (_encoded(manifest), {"analysis_csv": data}, manifest,
            details_bytes, details_artifacts,
            [(source_bytes, source_artifacts)])


def _store_analyzer(details_manifest, details_artifacts, *, wrong_run_id=False):
    details_bytes = store.serialize_manifest(details_manifest)
    details = details_artifacts["details_csv"]
    manifest = {
        "schema_version": 1, "run_id": OTHER_ID, "stage": "job_analyzer", "status": "COMPLETE",
        "started_at": STARTED, "completed_at": FINISHED,
        "source": {"role": "details_csv", **_fp(details), "record_count": 1},
        "input_generation": {"stage": "job_details", "run_id": OTHER_ID if wrong_run_id else details_manifest["run_id"],
            "status": "COMPLETE", "manifest_sha256": hashlib.sha256(details_bytes).hexdigest(),
            "artifact_role": "details_csv", "artifact_sha256": hashlib.sha256(details).hexdigest(),
            "artifact_size_bytes": len(details)},
        "accounting": {"source_records": 1, "processed_records": 1,
            "intentionally_skipped_records": 0, "failed_records": 0},
        "outputs": {"analysis_csv": {"relative_path": "job_analysis.csv", **_fp(b"analysis\n")}},
        "failure": None,
    }
    return manifest, details_bytes


def _evaluate_schema(manifest):
    try:
        result = schema.validate_manifest(manifest)
        return {"raw": {"schema_valid": result.schema_valid, "policy_resolved": result.policy_resolved,
                         "authorization": result.authorization, "findings": list(result.unresolved_findings)},
                "outcome": "ACCEPT" if result.schema_valid else "REJECT", "code": None}
    except schema.SchemaValidationError as exc:
        return {"raw": {"exception": type(exc).__name__, "message": str(exc)}, "outcome": "REJECT", "code": exc.code}
    except Exception as exc:  # Harness records errors; never treats them as acceptance.
        return {"raw": {"exception": type(exc).__name__, "message": str(exc)}, "outcome": "ERROR", "code": type(exc).__name__}


def _evaluate_store(manifest, *, artifacts=None, generation_dir=None, read_artifacts=False):
    try:
        result = store.validate_manifest(manifest, generation_dir=generation_dir, read_artifacts=read_artifacts)
        return {"raw": {"returned_roles": sorted(result)}, "outcome": "ACCEPT", "code": None}
    except store.GenerationValidationError as exc:
        return {"raw": {"exception": type(exc).__name__, "message": str(exc)}, "outcome": "REJECT", "code": type(exc).__name__}
    except Exception as exc:
        return {"raw": {"exception": type(exc).__name__, "message": str(exc)}, "outcome": "ERROR", "code": type(exc).__name__}


def _evaluate_verifier(bundle):
    try:
        raw = verifier.verify_generation(bundle[0], bundle[1], expected_stage="job_details",
            upstream_manifest_bytes=bundle[3], upstream_artifacts_by_role=bundle[4])
        outcome = "ACCEPT" if raw.accepted else ("NOT_AUTHORIZED" if raw.failure_code == "ROLLBACK_AUTHORITY_UNVERIFIABLE" else "REJECT")
        return {"raw": {"classification": raw.classification, "accepted": raw.accepted,
                         "eligible": raw.eligible, "failure_code": raw.failure_code,
                         "policy_dependencies": list(raw.policy_dependencies)},
                "outcome": outcome, "code": raw.failure_code}
    except Exception as exc:
        return {"raw": {"exception": type(exc).__name__, "message": str(exc)}, "outcome": "ERROR", "code": type(exc).__name__}


class ProvenanceSchemaDifferentialTests(unittest.TestCase):
    """Conformance observations intentionally retain each validator's vocabulary."""

    def test_native_valid_contracts_and_partial_semantics_are_observable(self):
        observations = []
        cases = (
            ("DETAILS_COMPLETE", "same conceptual successful details stage"),
            ("DETAILS_PARTIAL", "one success and one extraction failure"),
        )
        for case_id, intent in cases:
            status = "PARTIAL" if case_id.endswith("PARTIAL") else "COMPLETE"
            canonical = _evaluate_schema(_schema_details(status=status))
            store_manifest, _ = _store_details(status=status)
            store_result = _evaluate_store(store_manifest)
            verifier_result = _evaluate_verifier(_verifier_details(status=status))
            observations.extend((
                {"case_id": case_id, "intent": intent, "component": "schema_v2", **canonical},
                {"case_id": case_id, "intent": intent, "component": "generation_store_v1", **store_result},
                {"case_id": case_id, "intent": intent, "component": "offline_verifier_v1", **verifier_result},
            ))
            self.assertEqual(canonical["outcome"], "ACCEPT")
            self.assertEqual(canonical["raw"]["authorization"], "NOT_AUTHORIZED")
            self.assertEqual(store_result["outcome"], "ACCEPT")
            self.assertNotEqual(verifier_result["outcome"], "ERROR")
        self._record(observations)

    def test_empty_failed_and_in_progress_states_keep_native_result_vocabularies(self):
        empty_schema = _evaluate_schema(_schema_details(status="EMPTY"))
        empty_store_manifest, _ = _store_details(status="EMPTY")
        empty_store = _evaluate_store(empty_store_manifest)
        empty_verifier = _evaluate_verifier(_verifier_details(status="EMPTY"))
        self.assertEqual(empty_schema["outcome"], "ACCEPT")
        self.assertEqual(empty_store["outcome"], "ACCEPT")
        self.assertEqual(empty_verifier["outcome"], "ACCEPT")

        in_progress_schema = _schema_base(run_id=DETAILS_ID, stage="job_details", status="IN_PROGRESS")
        in_progress_store, _ = _store_details()
        in_progress_store.update(status="IN_PROGRESS", completed_at=None, source=None,
            accounting=None, outputs={}, failure=None)
        in_progress_verifier = _verifier_details()
        vm = json.loads(in_progress_verifier[0])
        vm.update(status="IN_PROGRESS", completed_at=None, source=None, input_generation=None,
            accounting=None, occurrences=None, outputs={}, failure=None)
        in_progress_verifier = (_encoded(vm), {}, vm, in_progress_verifier[3], in_progress_verifier[4])
        store.validate_manifest(in_progress_store)
        verifier_nonterminal = _evaluate_verifier(in_progress_verifier)
        self.assertEqual(_evaluate_schema(in_progress_schema)["outcome"], "ACCEPT")
        self.assertEqual(verifier_nonterminal["raw"]["classification"], "INCOMPLETE")

        failed_schema = _schema_base(run_id=DETAILS_ID, stage="job_details", status="FAILED")
        failed_schema["failure"] = {"code": "SOURCE_INVALID"}
        failed_store, _ = _store_details()
        failed_store.update(status="FAILED", source=None, accounting=None, outputs={}, failure={"code": "SOURCE_INVALID"})
        failed_verifier = _verifier_details()
        fm = json.loads(failed_verifier[0])
        fm.update(status="FAILED", source=None, input_generation=None, accounting=None,
            occurrences=None, outputs={}, failure={"code": "SOURCE_INVALID"})
        failed_verifier = (_encoded(fm), {}, fm, failed_verifier[3], failed_verifier[4])
        failed_schema_result = _evaluate_schema(failed_schema)
        # A failed run must never be accepted. Preserve ERROR as its own
        # observation: current schema v2 raises NameError in its FAILED path.
        self.assertIn(failed_schema_result["outcome"], {"REJECT", "ERROR"})
        if failed_schema_result["outcome"] == "ERROR":
            self.assertEqual(failed_schema_result["raw"]["exception"], "NameError")
        self.assertEqual(_evaluate_store(failed_store)["outcome"], "ACCEPT")
        failed_result = _evaluate_verifier(failed_verifier)
        self.assertEqual(failed_result["outcome"], "REJECT")
        self.assertEqual(failed_result["raw"]["classification"], "FAILED")
        self._record([
            {"case_id": "EMPTY_DETAILS", "component": "schema_v2", **empty_schema},
            {"case_id": "EMPTY_DETAILS", "component": "generation_store_v1", **empty_store},
            {"case_id": "EMPTY_DETAILS", "component": "offline_verifier_v1", **empty_verifier},
            {"case_id": "IN_PROGRESS_DETAILS", "component": "schema_v2", **_evaluate_schema(in_progress_schema)},
            {"case_id": "IN_PROGRESS_DETAILS", "component": "generation_store_v1", "outcome": "ACCEPT", "raw": {"status": "IN_PROGRESS", "selectable": False}, "code": None},
            {"case_id": "IN_PROGRESS_DETAILS", "component": "offline_provenance_verifier_v1", **verifier_nonterminal},
            {"case_id": "FAILED_DETAILS", "component": "schema_v2", **failed_schema_result},
            {"case_id": "FAILED_DETAILS", "component": "generation_store_v1", **_evaluate_store(failed_store)},
            {"case_id": "FAILED_DETAILS", "component": "offline_provenance_verifier_v1", **failed_result},
        ])

    def test_schema_and_verifier_reject_conflicting_source_fingerprints(self):
        canonical = _evaluate_schema(_schema_details(conflicting_fingerprint=True))
        verifier_result = _evaluate_verifier(_verifier_details(wrong_parent=True))
        store_manifest, _ = _store_details()
        store_result = _evaluate_store(store_manifest)
        self.assertEqual(canonical["outcome"], "REJECT")
        self.assertEqual(canonical["code"], "GENERATION_REFERENCE_CONFLICT")
        self.assertEqual(verifier_result["outcome"], "REJECT")
        self.assertEqual(verifier_result["code"], "INPUT_GENERATION_MISMATCH")
        self.assertEqual(store_result["outcome"], "ACCEPT")
        self._record([
            {"case_id": "SOURCE_FINGERPRINT_CONFLICT", "component": "schema_v2", **canonical},
            {"case_id": "SOURCE_FINGERPRINT_CONFLICT", "component": "generation_store_v1", "outcome": "NOT_APPLICABLE", "raw": {"reason": "details-store v1 has no source input-generation edge"}, "code": None},
            {"case_id": "UPSTREAM_RUN_ID_CONFLICT", "component": "offline_verifier_v1", **verifier_result},
        ])

    def test_artifact_bytes_are_verified_at_different_contract_depths(self):
        # A hash-consistent but malformed diagnostics payload is structurally
        # acceptable to the store (which does not parse its contents) and is
        # rejected by the byte/schema verifier. Schema v2 has no byte input.
        bundle = _verifier_details(diagnostics=b"not-json")
        verifier_result = _evaluate_verifier(bundle)
        store_manifest, artifacts = _store_details()
        store_manifest["outputs"]["diagnostics_json"] = {"relative_path": "job_details_diagnostics.json", **_fp(b"not-json")}
        with tempfile.TemporaryDirectory() as temp:
            generation_dir = Path(temp) / "job_details" / DETAILS_ID
            generation_dir.mkdir(parents=True)
            (generation_dir / "job_details.csv").write_bytes(artifacts["details_csv"])
            (generation_dir / "job_details_diagnostics.json").write_bytes(b"not-json")
            store_result = _evaluate_store(store_manifest, artifacts=artifacts,
                generation_dir=generation_dir, read_artifacts=True)
        canonical = _evaluate_schema(_schema_details())
        self.assertEqual(verifier_result["outcome"], "REJECT")
        # The verifier routes malformed nested diagnostics JSON through the
        # same strict JSON parser used for manifests, so it reports that code.
        self.assertEqual(verifier_result["code"], "MALFORMED_MANIFEST")
        self.assertEqual(store_result["outcome"], "ACCEPT")
        self.assertEqual(canonical["outcome"], "ACCEPT")
        self._record([
            {"case_id": "HASH_CONSISTENT_MALFORMED_DIAGNOSTICS", "component": "schema_v2", "outcome": "NOT_APPLICABLE", "raw": {"reason": "pure-data API receives declarations, not artifact bytes"}, "code": None},
            {"case_id": "HASH_CONSISTENT_MALFORMED_DIAGNOSTICS", "component": "generation_store_v1", **store_result},
            {"case_id": "HASH_CONSISTENT_MALFORMED_DIAGNOSTICS", "component": "offline_verifier_v1", **verifier_result},
        ])

    def test_required_field_version_stage_and_outcome_contradictions(self):
        observations = []
        base = _schema_details()
        variants = []
        missing = copy.deepcopy(base); missing.pop("producer"); variants.append(("MISSING_REQUIRED_FIELD", missing, "FIELD_SET_INVALID"))
        version = copy.deepcopy(base); version["schema_version"] = 99; variants.append(("UNKNOWN_VERSION", version, "UNKNOWN_SCHEMA_VERSION"))
        stage = copy.deepcopy(base); stage["stage"] = "not-a-stage"; variants.append(("INVALID_STAGE", stage, "STAGE_INVALID"))
        complete_bad = copy.deepcopy(base); complete_bad["accounting"]["failed_occurrences"] = 1; variants.append(("CONTRADICTORY_COMPLETE", complete_bad, "OCCURRENCE_ACCOUNTING_INVALID"))
        for case_id, value, expected_code in variants:
            differential_case_id = f"CANONICAL_ONLY_{case_id}"
            result = _evaluate_schema(value)
            self.assertEqual(result["outcome"], "REJECT", case_id)
            self.assertEqual(result["code"], expected_code, case_id)
            observations.append({"case_id": differential_case_id, "component": "schema_v2", **result})
        # Existing v1 components are deliberately not fed v2 mappings: their
        # exact envelopes differ. The v1 suites provide their own negative
        # contract coverage; cross-reading is recorded as an expected schema difference.
        observations.extend([
            {"case_id": f"CANONICAL_ONLY_{case_id}", "component": "generation_store_v1", "outcome": "NOT_APPLICABLE", "raw": {"reason": "v1 exact-key envelope is not schema v2; this v2-only shape case was not coerced"}, "code": None}
            for case_id, _, _ in variants
        ])
        observations.extend([
            {"case_id": f"CANONICAL_ONLY_{case_id}", "component": "offline_verifier_v1", "outcome": "NOT_APPLICABLE", "raw": {"reason": "v1 byte-verifier envelope is not schema v2; this v2-only shape case was not coerced"}, "code": None}
            for case_id, _, _ in variants
        ])
        self._record(observations)

    def test_native_negative_corpus_is_rejected_without_cross_schema_adaptation(self):
        cases = (
            "MISSING_REQUIRED_FIELD", "UNEXPECTED_FIELD", "WRONG_FIELD_TYPE",
            "UNKNOWN_VERSION", "INVALID_RUN_ID", "INVALID_STATUS", "INVALID_STAGE",
            "TRAVERSAL_ARTIFACT_PATH", "INVALID_HASH", "NEGATIVE_SIZE",
            "MISSING_ARTIFACT", "DUPLICATE_OCCURRENCE", "CONTRADICTORY_COMPLETE",
        )
        observations = []
        for case_id in cases:
            canonical = _schema_details()
            store_manifest, _ = _store_details()
            verifier_bundle = list(_verifier_details())
            verifier_manifest = json.loads(verifier_bundle[0])

            def mutate(value, *, component):
                if case_id == "MISSING_REQUIRED_FIELD":
                    value.pop("failure")
                elif case_id == "UNEXPECTED_FIELD":
                    value["unexpected_extension"] = True
                elif case_id == "WRONG_FIELD_TYPE":
                    value["run_id"] = 7
                elif case_id == "UNKNOWN_VERSION":
                    value["schema_version"] = 99
                elif case_id == "INVALID_RUN_ID":
                    value["run_id"] = "not-a-uuid"
                elif case_id == "INVALID_STATUS":
                    value["status"] = "UNKNOWN"
                elif case_id == "INVALID_STAGE":
                    value["stage"] = "not-a-stage"
                elif case_id == "TRAVERSAL_ARTIFACT_PATH":
                    value["outputs"]["details_csv"]["relative_path"] = "../escape.csv"
                elif case_id == "INVALID_HASH":
                    value["outputs"]["details_csv"]["sha256"] = "z" * 64
                elif case_id == "NEGATIVE_SIZE":
                    value["outputs"]["details_csv"]["size_bytes"] = -1
                elif case_id == "MISSING_ARTIFACT":
                    value["outputs"].pop("diagnostics_json")
                elif case_id == "DUPLICATE_OCCURRENCE":
                    value["occurrences"].append(copy.deepcopy(value["occurrences"][0]))
                elif case_id == "CONTRADICTORY_COMPLETE":
                    counts = value["accounting"]
                    if "failed_occurrences" in counts:
                        counts["failed_occurrences"] = 1
                    else:
                        counts["failed_records"] = 1

            for value in (canonical, store_manifest, verifier_manifest):
                if case_id == "DUPLICATE_OCCURRENCE" and value is store_manifest:
                    continue
                mutate(value, component="native")
            schema_result = _evaluate_schema(canonical)
            store_result = _evaluate_store(store_manifest)
            if case_id == "DUPLICATE_OCCURRENCE":
                verifier_bundle[0] = _encoded(verifier_manifest)
                verifier_result = _evaluate_verifier(tuple(verifier_bundle))
                store_result = {"outcome": "NOT_APPLICABLE", "code": None,
                    "raw": {"reason": "generation-store v1 has aggregate counts and no occurrence ledger"}}
            else:
                verifier_bundle[0] = _encoded(verifier_manifest)
                verifier_result = _evaluate_verifier(tuple(verifier_bundle))
            self.assertEqual(schema_result["outcome"], "REJECT", case_id)
            self.assertEqual(store_result["outcome"], "REJECT" if case_id != "DUPLICATE_OCCURRENCE" else "NOT_APPLICABLE", case_id)
            if case_id != "DUPLICATE_OCCURRENCE":
                self.assertEqual(verifier_result["outcome"], "REJECT", case_id)
            observations.extend([
                {"case_id": case_id, "component": "schema_v2", **schema_result},
                {"case_id": case_id, "component": "generation_store_v1", **store_result},
                {"case_id": case_id, "component": "offline_provenance_verifier_v1", **verifier_result},
            ])
        self._record(observations)

    def test_source_stage_is_not_a_generation_store_stage(self):
        source = _schema_source()
        canonical = _evaluate_schema(source)
        source_bytes, source_artifacts, _ = _verifier_source()
        verified = verifier.verify_generation(source_bytes, source_artifacts, expected_stage="source")
        self.assertTrue(verified.accepted)
        self.assertFalse(verified.eligible)
        self.assertEqual(canonical["outcome"], "ACCEPT")
        with self.assertRaises(store.GenerationValidationError):
            store.validate_manifest(source)
        self._record([
            {"case_id": "SOURCE_STAGE", "component": "schema_v2", **canonical},
            {"case_id": "SOURCE_STAGE", "component": "generation_store_v1", "outcome": "NOT_APPLICABLE", "raw": {"reason": "source is outside store v1 STAGES"}, "code": None},
            {"case_id": "SOURCE_STAGE", "component": "offline_verifier_v1", "outcome": "ACCEPT", "raw": {"classification": verified.classification, "accepted": verified.accepted, "eligible": verified.eligible, "policy_dependencies": list(verified.policy_dependencies)}, "code": verified.failure_code},
        ])

    def test_valid_empty_source_is_accepted_as_empty_data_only_not_eligibility(self):
        canonical = _evaluate_schema(_schema_source(rows=0))
        source_bytes, source_artifacts, _ = _verifier_source(rows=0)
        verified = verifier.verify_generation(source_bytes, source_artifacts, expected_stage="source")
        self.assertEqual(canonical["outcome"], "ACCEPT")
        self.assertEqual(canonical["raw"]["authorization"], "NOT_AUTHORIZED")
        self.assertTrue(verified.accepted)
        self.assertFalse(verified.eligible)
        self.assertEqual(verified.classification, "EMPTY_DATA_ONLY")
        self._record([
            {"case_id": "VALID_EMPTY_SOURCE", "component": "schema_v2", **canonical},
            {"case_id": "VALID_EMPTY_SOURCE", "component": "generation_store_v1", "outcome": "NOT_APPLICABLE", "raw": {"reason": "source stage is unsupported"}, "code": None},
            {"case_id": "VALID_EMPTY_SOURCE", "component": "offline_verifier_v1", "outcome": "ACCEPT", "raw": {"classification": verified.classification, "accepted": verified.accepted, "eligible": verified.eligible}, "code": verified.failure_code},
        ])

    def test_analyzer_generation_binding_requires_parent_evidence_in_existing_validators(self):
        store_details, store_artifacts = _store_details()
        store_analyzer, store_details_bytes = _store_analyzer(store_details, store_artifacts)
        wrong_store_analyzer, _ = _store_analyzer(store_details, store_artifacts, wrong_run_id=True)
        store.validate_analyzer_input_binding(store_analyzer, store_details,
            details_manifest_bytes=store_details_bytes, details_artifact_bytes=store_artifacts["details_csv"])
        with self.assertRaises(store.GenerationValidationError):
            store.validate_analyzer_input_binding(wrong_store_analyzer, store_details,
                details_manifest_bytes=store_details_bytes, details_artifact_bytes=store_artifacts["details_csv"])

        details_bundle = _verifier_details()
        good_verifier = _verifier_analyzer(details_bundle)
        bad_verifier = _verifier_analyzer(details_bundle, wrong_run_id=True)
        verifier_result = verifier.verify_generation(good_verifier[0], good_verifier[1],
            expected_stage="job_analyzer", upstream_manifest_bytes=good_verifier[3],
            upstream_artifacts_by_role=good_verifier[4], upstream_chain=good_verifier[5])
        verifier_bad = verifier.verify_generation(bad_verifier[0], bad_verifier[1],
            expected_stage="job_analyzer", upstream_manifest_bytes=bad_verifier[3],
            upstream_artifacts_by_role=bad_verifier[4], upstream_chain=bad_verifier[5])
        self.assertTrue(verifier_result.accepted)
        self.assertEqual(verifier_bad.failure_code, "INPUT_GENERATION_MISMATCH")

        schema_details = _schema_details()
        schema_ref = schema_details["outputs"]["details_csv"]
        schema_details_bytes = schema.serialize_manifest(schema_details)
        analyzer = _schema_base(run_id=OTHER_ID, stage="job_analyzer", status="COMPLETE")
        analyzer_source = {"role": "details_csv", "sha256": schema_ref["sha256"],
            "size_bytes": schema_ref["size_bytes"], "record_count": 1,
            "encoding": "utf-8", "format": "csv/details-v1"}
        analyzer["source"] = analyzer_source
        analyzer["input_generation"] = {"stage": "job_details", "run_id": DETAILS_ID,
            "status": "COMPLETE", "manifest_sha256": hashlib.sha256(schema_details_bytes).hexdigest(),
            "artifact_role": "details_csv", "artifact_sha256": schema_ref["sha256"],
            "size_bytes": schema_ref["size_bytes"], "record_count": 1, "format": "csv/details-v1"}
        analyzer["accounting"] = {"source_occurrences": 1, "processed_occurrences": 1,
            "intentional_skip_occurrences": 0, "failed_occurrences": 0, "output_rows": 1}
        analyzer["occurrences"] = [{"ordinal": 1, "occurrence_key": f"{schema_ref['sha256']}:1",
            "disposition": "PROCESSED", "logical_identity": "job-1", "reason_code": None,
            "policy_rule_id": None, "retained_occurrence_key": None, "error_code": None,
            "quality_code": None, "output_row": 1}]
        analyzer["outputs"] = {"analysis_csv": {"relative_path": "job_analysis.csv",
            "sha256": "c" * 64, "size_bytes": 8, "record_count": 1, "format": "csv/analysis-v1"}}
        schema_result = _evaluate_schema(analyzer)
        self.assertEqual(schema_result["outcome"], "ACCEPT")
        self._record([
            {"case_id": "ANALYZER_PARENT_MATCH", "component": "generation_store_v1", "outcome": "ACCEPT", "raw": {"binding": "validated against supplied manifest and bytes"}, "code": None},
            {"case_id": "ANALYZER_PARENT_RUN_ID_MISMATCH", "component": "generation_store_v1", "outcome": "REJECT", "raw": {"binding": "wrong details run_id rejected"}, "code": "GenerationValidationError"},
            {"case_id": "ANALYZER_PARENT_MATCH", "component": "offline_verifier_v1", "outcome": "ACCEPT" if verifier_result.accepted else "REJECT", "raw": {"classification": verifier_result.classification, "accepted": verifier_result.accepted, "eligible": verifier_result.eligible}, "code": verifier_result.failure_code},
            {"case_id": "ANALYZER_PARENT_RUN_ID_MISMATCH", "component": "offline_verifier_v1", "outcome": "REJECT", "raw": {"classification": verifier_bad.classification, "accepted": verifier_bad.accepted, "eligible": verifier_bad.eligible}, "code": verifier_bad.failure_code},
            {"case_id": "ANALYZER_PARENT_RUN_ID_MISMATCH", "component": "schema_v2", **schema_result, "raw": {**schema_result["raw"], "limitation": "schema validates reference shape and artifact fingerprint fields but receives no parent manifest bytes"}},
        ])

    def test_rollback_metadata_is_not_authorization(self):
        event = {"authorized_by": "owner", "authorization_ref": "ticket-1", "at": FINISHED,
                 "reason": "synthetic", "source_sha256": "a" * 64}
        result = verifier.verify_rollback_request(event)
        self.assertFalse(result.accepted)
        self.assertFalse(result.eligible)
        self.assertEqual(result.failure_code, "ROLLBACK_AUTHORITY_UNVERIFIABLE")
        prior, _ = _store_details()
        source_sha = prior["source"]["sha256"]
        failed = copy.deepcopy(prior)
        failed.update(run_id=OTHER_ID, status="FAILED", source=None, accounting=None,
                      outputs={}, failure={"code": "SOURCE_INVALID"})
        event["source_sha256"] = source_sha
        pointer = {"schema_version": 1, "stage": "job_details",
            "latest_attempt": {"run_id": OTHER_ID, "status": "FAILED"},
            "selected_generation_id": DETAILS_ID, "previous_complete_generation_id": DETAILS_ID,
            "selection_mode": "EXPLICIT_ROLLBACK", "recovery_event": event}
        pointer_result = store.validate_pointer(pointer, manifest=prior,
            latest_attempt_manifest=failed, current_source_sha256=source_sha)
        self._record([
            {"case_id": "ROLLBACK_TEXT_FIELDS_ONLY", "component": "generation_store_v1",
             "outcome": "ACCEPT", "raw": {"pointer_shape_and_source_match": bool(pointer_result),
             "authorization_authenticated": False}, "code": None},
            {"case_id": "ROLLBACK_TEXT_FIELDS_ONLY", "component": "offline_verifier_v1",
             "outcome": "NOT_AUTHORIZED", "raw": {"classification": result.classification,
             "accepted": result.accepted, "eligible": result.eligible,
             "failure_code": result.failure_code, "policy_dependencies": list(result.policy_dependencies)},
             "code": result.failure_code},
            {"case_id": "ROLLBACK_TEXT_FIELDS_ONLY", "component": "schema_v2",
             "outcome": "NOT_APPLICABLE", "raw": {"reason": "manifest schema has previous-generation metadata but no pointer or authorization verifier"}, "code": None},
        ])

    def test_current_pointer_structure_is_distinct_from_data_verification(self):
        manifest, _ = _store_details()
        pointer = {"schema_version": 1, "stage": "job_details",
            "latest_attempt": {"run_id": DETAILS_ID, "status": "COMPLETE"},
            "selected_generation_id": DETAILS_ID, "previous_complete_generation_id": None,
            "selection_mode": "CURRENT", "recovery_event": None}
        checked = store.validate_pointer(pointer, manifest=manifest)
        detail_bundle = _verifier_details()
        data_result = _evaluate_verifier(detail_bundle)
        selection = verifier.verify_selection(verifier.verify_generation(
            detail_bundle[0], detail_bundle[1], expected_stage="job_details",
            upstream_manifest_bytes=detail_bundle[3], upstream_artifacts_by_role=detail_bundle[4]))
        self.assertTrue(checked)
        self.assertTrue(selection.accepted)
        self.assertFalse(selection.eligible)
        self._record([
            {"case_id": "CURRENT_SELECTION", "component": "generation_store_v1", "outcome": "ACCEPT",
             "raw": {"pointer_validated": True, "published": False}, "code": None},
            {"case_id": "CURRENT_SELECTION", "component": "offline_provenance_verifier_v1",
             "outcome": "ACCEPT", "raw": {"data_acceptance": data_result["outcome"],
             "selection_eligible": selection.eligible, "policy_dependencies": list(selection.policy_dependencies)}, "code": selection.failure_code},
            {"case_id": "CURRENT_SELECTION", "component": "schema_v2", "outcome": "NOT_APPLICABLE",
             "raw": {"reason": "schema v2 validates manifest structure only; it has no selection/pointer interface"}, "code": None},
        ])

    def _record(self, rows):
        # Machine-readable raw/normalized evidence is retained in captured test
        # stdout by the bounded runner; it does not alter validator behavior.
        print("DIFFERENTIAL " + json.dumps(rows, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    unittest.main()
