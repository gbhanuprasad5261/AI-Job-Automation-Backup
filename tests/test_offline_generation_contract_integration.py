"""Synthetic compatibility tests for the isolated provenance components.

These tests use temporary files and caller-supplied bytes only. They do not
import production pipeline modules, publish pointers, or establish filesystem
security or production authorization.
"""
from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pipeline_generation_store as store
from tools import offline_provenance_verifier as verifier


SOURCE_HEADER = "Title,Company,Location,Easy Apply,Actively Reviewing,Link\n"
DETAILS_HEADER = '"Title","Company","Location","Experience","Easy Apply","Skills","Link","Description"\n'
ANALYSIS_HEADER = '"Title","Company","Location","Easy Apply","Match Score","Priority","Matched Skills","Missing Skills","Experience Required","Experience Years","Experience Skip","Data Status","Application Eligible","Link"\n'
RUN_SOURCE = "7c9d5c21-66eb-4ee7-84b8-2523d3bbf1d2"
RUN_DETAILS = "2eb56da5-e63b-4e6b-9d3c-b5abff7aa63b"
RUN_ANALYSIS = "3c7c5d21-66eb-4ee7-84b8-3523d3bbf1d2"
RUN_PRIOR = "4c7c5d21-66eb-4ee6-9d3c-b5abff7aa63b"
STARTED = "2026-10-18T12:00:00Z"
COMPLETED = "2026-10-18T12:01:00Z"


def _hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _fp(data: bytes) -> dict:
    return {"sha256": _hash(data), "size_bytes": len(data)}


def _encode(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _v_artifact(path: str, fmt: str, data: bytes, count: int) -> dict:
    return {"relative_path": path, **_fp(data), "record_count": count, "format": fmt}


def _v_source(*, rows=None, run_id=RUN_SOURCE, status=None):
    rows = rows if rows is not None else ["Backend,Example,Bengaluru,Yes,No,https://example.test/1\n"]
    data = (SOURCE_HEADER + "".join(rows)).encode("utf-8")
    count = len(rows)
    status = status or ("EMPTY" if count == 0 else "COMPLETE")
    manifest = {
        "schema_version": 1,
        "run_id": run_id,
        "stage": "source",
        "status": status,
        "producer": {"id": "synthetic-source", "version": "test-1"},
        "started_at": STARTED,
        "completed_at": COMPLETED,
        "source": {"role": "jobs_csv", **_fp(data), "record_count": count,
                   "encoding": "utf-8", "format": "csv/jobs-v1"},
        "input_generation": None,
        "accounting": None,
        "occurrences": None,
        "outputs": {"jobs_csv": _v_artifact("jobs.csv", "csv/jobs-v1", data, count)},
        "failure": None,
    }
    return _encode(manifest), {"jobs_csv": data}, manifest


def _v_details(source=None, *, status="COMPLETE", run_id=RUN_DETAILS, data=None,
               diagnostics=b"[]", dispositions=None):
    source = source or _v_source()
    source_bytes, source_artifacts, source_manifest = source
    source_data = source_artifacts["jobs_csv"]
    source_count = source_manifest["source"]["record_count"]
    if data is None:
        if status == "EMPTY":
            data = b""
            processed = failed = 0
            dispositions = []
        else:
            data = (DETAILS_HEADER + '"Backend","Example","Bengaluru","5 years","Yes","Java","https://example.test/1","Java experience"\n').encode()
            dispositions = dispositions or ["PROCESSED"]
            processed = sum(d == "PROCESSED" for d in dispositions)
            failed = sum(d == "FAILED" for d in dispositions)
    else:
        processed = sum(d == "PROCESSED" for d in (dispositions or []))
        failed = sum(d == "FAILED" for d in (dispositions or []))
    outputs = {}
    artifacts = {}
    if status in {"COMPLETE", "PARTIAL"}:
        outputs = {
            "details_csv": _v_artifact("job_details.csv", "csv/details-v1", data, processed),
            "diagnostics_json": _v_artifact("job_details_diagnostics.json", "json/diagnostics-v1", diagnostics, len(json.loads(diagnostics))),
        }
        artifacts = {"details_csv": data, "diagnostics_json": diagnostics}
    occurrences = []
    for ordinal in range(1, source_count + 1):
        disposition = (dispositions or ["PROCESSED"] * source_count)[ordinal - 1]
        occurrences.append({
            "ordinal": ordinal,
            "occurrence_key": f"{source_manifest['source']['sha256']}:{ordinal}",
            "disposition": disposition,
            "logical_identity": f"job-{ordinal}",
            "reason_code": None,
            "policy_rule_id": None,
            "retained_occurrence_key": None,
            "error_code": "EXTRACTION_ERROR" if disposition == "FAILED" else None,
            "quality_code": None,
            "output_row": ordinal if disposition == "PROCESSED" else None,
        })
    input_ref = {
        "stage": "source", "run_id": source_manifest["run_id"], "status": source_manifest["status"],
        "manifest_sha256": _hash(source_bytes), "artifact_role": "jobs_csv",
        "artifact_sha256": _hash(source_data), "artifact_size_bytes": len(source_data),
        "record_count": source_count,
    }
    manifest = {
        "schema_version": 1, "run_id": run_id, "stage": "job_details", "status": status,
        "producer": {"id": "synthetic-details", "version": "test-1"},
        "started_at": STARTED, "completed_at": COMPLETED,
        "source": {"role": "jobs_csv", **_fp(source_data), "record_count": source_count,
                   "encoding": "utf-8", "format": "csv/jobs-v1"},
        "input_generation": input_ref,
        "accounting": {"source_occurrences": source_count, "processed_occurrences": processed,
                       "intentional_skip_occurrences": 0, "failed_occurrences": failed,
                       "output_rows": processed},
        "occurrences": occurrences, "outputs": outputs, "failure": None,
    }
    if status == "EMPTY":
        manifest["accounting"] = {"source_occurrences": 0, "processed_occurrences": 0,
                                  "intentional_skip_occurrences": 0, "failed_occurrences": 0,
                                  "output_rows": 0}
    return _encode(manifest), artifacts, manifest, source


def _v_analysis(details, *, run_id=RUN_ANALYSIS):
    details_bytes, details_artifacts, details_manifest, source = details
    details_status = details_manifest["status"]
    empty = details_status == "EMPTY"
    data = (ANALYSIS_HEADER + '"Backend","Example","Bengaluru","Yes","80%","High","Java","","5 years","5","No","OK","No","https://example.test/1"\n').encode()
    outputs = {} if empty else {"analysis_csv": _v_artifact("job_analysis.csv", "csv/analysis-v1", data, 1)}
    artifacts = {} if empty else {"analysis_csv": data}
    source_data = details_artifacts.get("details_csv", b"")
    input_ref = {
        "stage": "job_details", "run_id": details_manifest["run_id"], "status": details_status,
        "manifest_sha256": _hash(details_bytes),
        "artifact_role": None if empty else "details_csv",
        "artifact_sha256": None if empty else _hash(source_data),
        "artifact_size_bytes": None if empty else len(source_data),
        "record_count": 0 if empty else details_manifest["accounting"]["output_rows"],
    }
    manifest = {
        "schema_version": 1, "run_id": run_id, "stage": "job_analyzer",
        "status": "EMPTY" if empty else "COMPLETE",
        "producer": {"id": "synthetic-analyzer", "version": "test-1"},
        "started_at": STARTED, "completed_at": COMPLETED,
        "source": {"role": "details_csv", **_fp(source_data), "record_count": 0 if empty else 1,
                   "encoding": "utf-8", "format": "csv/details-v1"},
        "input_generation": input_ref,
        "accounting": {"source_occurrences": 0 if empty else 1,
                       "processed_occurrences": 0 if empty else 1,
                       "intentional_skip_occurrences": 0, "failed_occurrences": 0,
                       "output_rows": 0 if empty else 1},
        "occurrences": [] if empty else [{
            "ordinal": 1, "occurrence_key": f"{_hash(source_data)}:1", "disposition": "PROCESSED",
            "logical_identity": "job-1", "reason_code": None, "policy_rule_id": None,
            "retained_occurrence_key": None, "error_code": None, "quality_code": None,
            "output_row": 1,
        }],
        "outputs": outputs, "failure": None,
    }
    return _encode(manifest), artifacts, manifest, details


def _s_artifact(path, data):
    return {"relative_path": path, **_fp(data)}


def _s_details(*, status="COMPLETE", run_id=RUN_DETAILS, source_data=b"input bytes",
               source_count=1, details_data=None, diagnostics=b"[]", failed=0):
    if status == "EMPTY":
        source_data, source_count, failed = SOURCE_HEADER.encode("utf-8"), 0, 0
    if details_data is None:
        details_data = b'Title,Link,Description\nBackend,https://example.test/1,Java\n'
    outputs = {}
    if status in {"COMPLETE", "PARTIAL"}:
        outputs = {
            "details_csv": _s_artifact("job_details.csv", details_data),
            "diagnostics_json": _s_artifact("job_details_diagnostics.json", diagnostics),
        }
    manifest = {
        "schema_version": 1, "run_id": run_id, "stage": "job_details", "status": status,
        "started_at": STARTED, "completed_at": None if status == "IN_PROGRESS" else COMPLETED,
        "source": None if status == "IN_PROGRESS" else {
            "role": "jobs.csv", **_fp(source_data), "record_count": source_count,
        },
        "input_generation": None,
        "accounting": None if status == "IN_PROGRESS" else {
            "source_records": source_count, "processed_records": source_count - failed,
            "intentionally_skipped_records": 0, "failed_records": failed,
        },
        "outputs": {} if status in {"IN_PROGRESS", "EMPTY", "FAILED"} else outputs,
        "failure": {"code": "EXTRACTION_FAILED"} if status == "FAILED" else None,
    }
    if status == "FAILED":
        manifest["source"] = None
        manifest["accounting"] = None
    return manifest, {"details_csv": details_data, "diagnostics_json": diagnostics}


def _write_store_artifacts(generation_dir, artifacts):
    for role, data in artifacts.items():
        name = {"details_csv": "job_details.csv", "diagnostics_json": "job_details_diagnostics.json"}[role]
        (generation_dir / name).write_bytes(data)


def _s_analyzer(*, run_id=RUN_ANALYSIS, input_run_id=RUN_DETAILS,
                details_manifest_bytes=None, details_artifact=None, empty=False):
    details_manifest_bytes = details_manifest_bytes or b"synthetic details manifest"
    details_artifact = details_artifact if details_artifact is not None else b"details bytes"
    analysis_data = b"Title,Link,Match Score\nBackend,https://example.test/1,80%\n"
    source_data = b"" if empty else details_artifact
    status = "EMPTY" if empty else "COMPLETE"
    return {
        "schema_version": 1, "run_id": run_id, "stage": "job_analyzer", "status": status,
        "started_at": STARTED, "completed_at": COMPLETED,
        "source": {"role": "details_csv", **_fp(source_data), "record_count": 0 if empty else 1},
        "input_generation": {
            "stage": "job_details", "run_id": input_run_id,
            "status": "EMPTY" if empty else "COMPLETE",
            "manifest_sha256": _hash(details_manifest_bytes),
            "artifact_role": None if empty else "details_csv",
            "artifact_sha256": None if empty else _hash(details_artifact),
            "artifact_size_bytes": None if empty else len(details_artifact),
        },
        "accounting": {"source_records": 0 if empty else 1,
                       "processed_records": 0 if empty else 1,
                       "intentionally_skipped_records": 0, "failed_records": 0},
        "outputs": {} if empty else {"analysis_csv": _s_artifact("job_analysis.csv", analysis_data)},
        "failure": None,
    }


class OfflineGenerationContractIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def _store_generation(self, manifest, artifacts):
        generation = self.root / manifest["stage"] / manifest["run_id"]
        generation.mkdir(parents=True)
        _write_store_artifacts(generation, artifacts)
        return generation

    def _verify_details(self, bundle):
        return verifier.verify_generation(
            bundle[0], bundle[1], expected_stage="job_details",
            upstream_manifest_bytes=bundle[3][0], upstream_artifacts_by_role=bundle[3][1],
        )

    def test_a_valid_details_generation_is_accepted_under_both_distinct_schemas(self):
        source = _v_source()
        vdetails = _v_details(source)
        vresult = self._verify_details(vdetails)
        smanifest, s_artifacts = _s_details(
            source_data=source[1]["jobs_csv"],
            details_data=vdetails[1]["details_csv"],
            diagnostics=vdetails[1]["diagnostics_json"],
        )
        generation = self._store_generation(smanifest, s_artifacts)
        sresult = store.validate_manifest(smanifest, generation_dir=generation, read_artifacts=True)
        self.assertTrue(vresult.accepted)
        self.assertFalse(vresult.eligible)
        self.assertEqual(sresult, s_artifacts)
        vmanifest = json.loads(vdetails[0])
        for role in ("details_csv", "diagnostics_json"):
            self.assertEqual(_fp(vresult.artifact_bytes[role]), {
                "sha256": vmanifest["outputs"][role]["sha256"],
                "size_bytes": vmanifest["outputs"][role]["size_bytes"],
            })
            self.assertEqual(_fp(sresult[role]), {
                "sha256": smanifest["outputs"][role]["sha256"],
                "size_bytes": smanifest["outputs"][role]["size_bytes"],
            })
        self.assertEqual(vresult.artifact_bytes, sresult)

    def test_a2_valid_analyzer_binding_is_accepted_by_both_without_eligibility(self):
        source = _v_source()
        vdetails = _v_details(source)
        vanalysis = _v_analysis(vdetails)
        vresult = verifier.verify_generation(
            vanalysis[0], vanalysis[1], expected_stage="job_analyzer",
            upstream_manifest_bytes=vdetails[0], upstream_artifacts_by_role=vdetails[1],
            upstream_chain=((source[0], source[1]),),
        )

        sdetails, s_artifacts = _s_details()
        sdetails_bytes = store.serialize_manifest(sdetails)
        sanalysis = _s_analyzer(
            details_manifest_bytes=sdetails_bytes,
            details_artifact=s_artifacts["details_csv"],
        )
        self.assertEqual(store.validate_manifest(sanalysis), {})
        self.assertTrue(store.validate_analyzer_input_binding(
            sanalysis, sdetails, details_manifest_bytes=sdetails_bytes,
            details_artifact_bytes=s_artifacts["details_csv"],
        ))
        self.assertTrue(vresult.accepted)
        self.assertFalse(vresult.eligible)

    def test_b_missing_required_run_id_is_rejected_by_both(self):
        vmanifest = json.loads(_v_details()[0])
        del vmanifest["run_id"]
        vresult = verifier.verify_generation(_encode(vmanifest), {})
        smanifest, _ = _s_details()
        del smanifest["run_id"]
        self.assertEqual(vresult.failure_code, "MALFORMED_MANIFEST")
        with self.assertRaises(store.GenerationValidationError):
            store.validate_manifest(smanifest)

    def test_c_unknown_schema_version_is_rejected_by_both(self):
        vmanifest = json.loads(_v_details()[0])
        vmanifest["schema_version"] = 99
        smanifest, _ = _s_details()
        smanifest["schema_version"] = 99
        self.assertEqual(verifier.verify_generation(_encode(vmanifest), {}).failure_code,
                         "UNKNOWN_SCHEMA_VERSION")
        with self.assertRaisesRegex(store.GenerationValidationError, "unknown manifest schema"):
            store.validate_manifest(smanifest)

    def test_d_artifact_fingerprint_mismatch_rejected_by_both(self):
        vdetails = _v_details()
        mutated_v = dict(vdetails[1])
        original = mutated_v["details_csv"]
        mutated_v["details_csv"] = original.replace(b"Java experience", b"Rust experience")
        vresult = self._verify_details((vdetails[0], mutated_v, *vdetails[2:]))
        smanifest, s_artifacts = _s_details()
        generation = self._store_generation(smanifest, s_artifacts)
        (generation / "job_details.csv").write_bytes(s_artifacts["details_csv"].replace(b"Java", b"Rust"))
        self.assertEqual(vresult.failure_code, "ARTIFACT_HASH_MISMATCH")
        with self.assertRaisesRegex(store.GenerationValidationError, "artifact hash mismatch"):
            store.validate_manifest(smanifest, generation_dir=generation, read_artifacts=True)

    def test_e_artifact_size_mismatch_rejected_by_both(self):
        vdetails = _v_details()
        manifest = json.loads(vdetails[0])
        manifest["outputs"]["details_csv"]["size_bytes"] += 1
        vresult = self._verify_details((_encode(manifest), vdetails[1], *vdetails[2:]))
        smanifest, s_artifacts = _s_details()
        smanifest["outputs"]["details_csv"]["size_bytes"] += 1
        generation = self._store_generation(smanifest, s_artifacts)
        self.assertEqual(vresult.failure_code, "ARTIFACT_SIZE_MISMATCH")
        with self.assertRaisesRegex(store.GenerationValidationError, "artifact size mismatch"):
            store.validate_manifest(smanifest, generation_dir=generation, read_artifacts=True)

    def test_f_unexpected_roles_reject_under_each_component_contract(self):
        vdetails = _v_details()
        vmanifest = json.loads(vdetails[0])
        vmanifest["outputs"]["unexpected"] = copy.deepcopy(vmanifest["outputs"]["details_csv"])
        v_artifacts = {**vdetails[1], "unexpected": vdetails[1]["details_csv"]}
        vresult = self._verify_details((_encode(vmanifest), v_artifacts, *vdetails[2:]))
        smanifest, _ = _s_details()
        smanifest["outputs"]["unexpected"] = smanifest["outputs"]["details_csv"]
        self.assertEqual(vresult.failure_code, "UNEXPECTED_ARTIFACT_ROLE")
        with self.assertRaisesRegex(store.GenerationValidationError, "required stage artifact set"):
            store.validate_manifest(smanifest)

    def test_f_duplicate_json_manifest_keys_have_component_specific_errors(self):
        duplicate_top_level = b'{"schema_version":1,"schema_version":1}'
        duplicate_role = (
            b'{"schema_version":1,"run_id":"' + RUN_DETAILS.encode() +
            b'","stage":"job_details","status":"COMPLETE","producer":{"id":"x","version":"1"},'
            b'"started_at":"2026-10-18T12:00:00Z","completed_at":"2026-10-18T12:01:00Z",'
            b'"source":{"role":"jobs_csv","sha256":"' + b"0" * 64 +
            b'","size_bytes":0,"record_count":0,"encoding":"utf-8","format":"csv/jobs-v1"},'
            b'"input_generation":{"stage":"source","run_id":"' + RUN_SOURCE.encode() +
            b'","status":"EMPTY","manifest_sha256":"' + b"0" * 64 +
            b'","artifact_role":"jobs_csv","artifact_sha256":"' + b"0" * 64 +
            b'","artifact_size_bytes":0,"record_count":0},"accounting":{"source_occurrences":0,'
            b'"processed_occurrences":0,"intentional_skip_occurrences":0,"failed_occurrences":0,"output_rows":0},'
            b'"occurrences":[],"outputs":{"details_csv":{},"details_csv":{}},"failure":null}'
        )
        for duplicate in (duplicate_top_level, duplicate_role):
            vresult = verifier.verify_generation(duplicate, {})
            with self.assertRaisesRegex(store.GenerationValidationError, "duplicate JSON key"):
                store.parse_manifest(duplicate)
            self.assertEqual(vresult.failure_code, "DUPLICATE_JSON_KEY")

    def test_g_verifier_binds_details_to_exact_source_generation_store_does_not_model_that_edge(self):
        source_a = _v_source()
        source_b = _v_source(run_id=RUN_PRIOR)
        details = _v_details(source_a)
        vresult = verifier.verify_generation(
            details[0], details[1], expected_stage="job_details",
            upstream_manifest_bytes=source_b[0], upstream_artifacts_by_role=source_b[1],
        )
        smanifest, _ = _s_details(source_data=source_a[1]["jobs_csv"])
        # The store schema has only a source fingerprint/count, not a source
        # generation ID or source-manifest digest, so it cannot express this edge.
        self.assertEqual(vresult.failure_code, "INPUT_GENERATION_MISMATCH")
        self.assertEqual(store.validate_manifest(smanifest), {})

    def test_h_both_components_reject_wrong_analyzer_details_generation(self):
        source = _v_source()
        details = _v_details(source)
        analyzer = _v_analysis(details)
        analyzer_manifest = json.loads(analyzer[0])
        analyzer_manifest["input_generation"]["run_id"] = RUN_PRIOR
        vresult = verifier.verify_generation(
            _encode(analyzer_manifest), analyzer[1], expected_stage="job_analyzer",
            upstream_manifest_bytes=details[0], upstream_artifacts_by_role=details[1],
            upstream_chain=((source[0], source[1]),),
        )

        sm_details, sm_artifacts = _s_details()
        sm_details_bytes = store.serialize_manifest(sm_details)
        sm_analysis = _s_analyzer(
            input_run_id=RUN_PRIOR, details_manifest_bytes=sm_details_bytes,
            details_artifact=sm_artifacts["details_csv"],
        )
        self.assertEqual(vresult.failure_code, "INPUT_GENERATION_MISMATCH")
        with self.assertRaisesRegex(store.GenerationValidationError, "different details generation"):
            store.validate_analyzer_input_binding(
                sm_analysis, sm_details, details_manifest_bytes=sm_details_bytes,
                details_artifact_bytes=sm_artifacts["details_csv"],
            )

    def test_i_contradictory_aggregate_counts_reject_under_both_contracts(self):
        vdetails = _v_details()
        manifest = json.loads(vdetails[0])
        manifest["accounting"]["processed_occurrences"] = 2
        vresult = self._verify_details((_encode(manifest), vdetails[1], *vdetails[2:]))
        smanifest, _ = _s_details()
        smanifest["accounting"]["processed_records"] = 2
        self.assertEqual(vresult.failure_code, "COUNT_MISMATCH")
        with self.assertRaisesRegex(store.GenerationValidationError, "accounting counts do not reconcile"):
            store.validate_manifest(smanifest)

    def test_j_unaccounted_occurrence_is_verifier_only_and_store_accepts_aggregate_contract(self):
        vdetails = _v_details()
        manifest = json.loads(vdetails[0])
        manifest["occurrences"] = []
        vresult = self._verify_details((_encode(manifest), vdetails[1], *vdetails[2:]))
        smanifest, _ = _s_details()
        self.assertEqual(vresult.failure_code, "UNACCOUNTED_OCCURRENCE")
        self.assertEqual(store.validate_manifest(smanifest), {})

    def test_k_empty_generation_is_accepted_as_empty_data_only_by_both(self):
        source = _v_source(rows=[])
        details = _v_details(source, status="EMPTY")
        vresult = self._verify_details(details)
        smanifest, _ = _s_details(status="EMPTY", source_data=source[1]["jobs_csv"])
        self.assertTrue(vresult.accepted)
        self.assertEqual(vresult.classification, "EMPTY_DATA_ONLY")
        self.assertFalse(vresult.eligible)
        self.assertEqual(store.validate_manifest(smanifest), {})

    def test_k2_in_progress_is_nonterminal_under_both_contracts(self):
        vdetails = _v_details()
        vmanifest = json.loads(vdetails[0])
        vmanifest.update({"status": "IN_PROGRESS", "completed_at": None, "source": None,
                          "accounting": None, "occurrences": None, "outputs": {}, "failure": None})
        vresult = verifier.verify_generation(_encode(vmanifest), {})
        smanifest, _ = _s_details(status="IN_PROGRESS")
        self.assertEqual(vresult.classification, "INCOMPLETE")
        self.assertFalse(vresult.accepted)
        self.assertEqual(store.validate_manifest(smanifest), {})

    def test_k3_partial_state_is_not_interchangeable_between_contracts(self):
        source = _v_source(rows=[
            "Backend,Example,Bengaluru,Yes,No,https://example.test/1\n",
            "Backend,Example,Bengaluru,Yes,No,https://example.test/2\n",
        ])
        vdetails = _v_details(source, status="PARTIAL", dispositions=["PROCESSED", "FAILED"])
        vresult = self._verify_details(vdetails)
        smanifest, _ = _s_details(status="PARTIAL", source_count=2, failed=1)
        self.assertEqual(vresult.classification, "UNSUPPORTED_POLICY")
        self.assertIn("D6", vresult.policy_dependencies)
        self.assertFalse(vresult.eligible)
        self.assertEqual(store.validate_manifest(smanifest), {})

    def test_l_failed_occurrence_cannot_be_claimed_complete(self):
        source = _v_source(rows=[
            "Backend,Example,Bengaluru,Yes,No,https://example.test/1\n",
            "Backend,Example,Bengaluru,Yes,No,https://example.test/2\n",
        ])
        vdetails = _v_details(source, dispositions=["PROCESSED", "FAILED"])
        vm = json.loads(vdetails[0])
        vm["status"] = "COMPLETE"
        vresult = self._verify_details((_encode(vm), vdetails[1], *vdetails[2:]))
        smanifest, _ = _s_details(status="COMPLETE", source_count=2, failed=1)
        self.assertEqual(vresult.failure_code, "STATUS_CONTRADICTION")
        with self.assertRaisesRegex(store.GenerationValidationError, "COMPLETE requires"):
            store.validate_manifest(smanifest)

    def test_m_failed_latest_never_causes_implicit_old_generation_fallback(self):
        failed = {
            "schema_version": 1, "run_id": RUN_ANALYSIS, "stage": "source", "status": "FAILED",
            "producer": {"id": "synthetic-source", "version": "test-1"},
            "started_at": STARTED, "completed_at": COMPLETED, "source": None,
            "input_generation": None, "accounting": None, "occurrences": None,
            "outputs": {}, "failure": {"code": "SOURCE_INVALID"},
        }
        latest = verifier.verify_generation(_encode(failed), {})
        previous_source = _v_source()
        previous = verifier.verify_generation(previous_source[0], previous_source[1])
        selected = verifier.verify_selection(latest, previous=previous)

        latest_store, _ = _s_details(status="FAILED", run_id=RUN_ANALYSIS)
        pointer = {
            "schema_version": 1, "stage": "job_details",
            "latest_attempt": {"run_id": RUN_ANALYSIS, "status": "FAILED"},
            "selected_generation_id": None, "previous_complete_generation_id": RUN_PRIOR,
            "selection_mode": "NONE", "recovery_event": None,
        }
        self.assertEqual(selected.failure_code, "IMPLICIT_OLD_GENERATION_FALLBACK")
        self.assertFalse(selected.eligible)
        self.assertEqual(store.validate_pointer(pointer, manifest=latest_store), pointer)

    def test_n_store_rollback_shape_is_not_verifiable_authorization(self):
        prior, _ = _s_details(run_id=RUN_PRIOR)
        latest, _ = _s_details(status="FAILED", run_id=RUN_ANALYSIS)
        source_sha = prior["source"]["sha256"]
        pointer = {
            "schema_version": 1, "stage": "job_details",
            "latest_attempt": {"run_id": RUN_ANALYSIS, "status": "FAILED"},
            "selected_generation_id": RUN_PRIOR, "previous_complete_generation_id": RUN_PRIOR,
            "selection_mode": "EXPLICIT_ROLLBACK",
            "recovery_event": {"authorized_by": "synthetic", "authorization_ref": "test-ref",
                               "at": COMPLETED, "reason": "test only", "source_sha256": source_sha},
        }
        accepted_shape = store.validate_pointer(
            pointer, manifest=prior, latest_attempt_manifest=latest,
            current_source_sha256=source_sha,
        )
        rejected = verifier.verify_rollback_request(pointer["recovery_event"])
        self.assertEqual(accepted_shape, pointer)
        self.assertEqual(rejected.failure_code, "ROLLBACK_AUTHORITY_UNVERIFIABLE")
        self.assertFalse(rejected.eligible)

    def test_o_malformed_diagnostics_are_interpreted_differently(self):
        bad_diagnostics = b"{}"
        vdetails = _v_details(diagnostics=bad_diagnostics)
        vm = json.loads(vdetails[0])
        vm["outputs"]["diagnostics_json"]["record_count"] = 0
        vresult = self._verify_details((_encode(vm), vdetails[1], *vdetails[2:]))
        smanifest, s_artifacts = _s_details(diagnostics=bad_diagnostics)
        generation = self._store_generation(smanifest, s_artifacts)
        sresult = store.validate_manifest(smanifest, generation_dir=generation, read_artifacts=True)
        self.assertEqual(vresult.failure_code, "ARTIFACT_SCHEMA_INVALID")
        self.assertEqual(sresult["diagnostics_json"], bad_diagnostics)

    def test_o_verifier_rejects_unaccounted_occurrence_payload(self):
        vdetails = _v_details()
        manifest = json.loads(vdetails[0])
        manifest["occurrences"][0]["quality_code"] = {"malformed": True}
        result = self._verify_details((_encode(manifest), vdetails[1], *vdetails[2:]))
        self.assertEqual(result.failure_code, "OCCURRENCE_INVALID")
        self.assertFalse(result.eligible)

    def test_p_unexpected_verifier_exception_is_structured(self):
        with patch.object(verifier, "_manifest_result", side_effect=RuntimeError("synthetic")):
            result = verifier.verify_generation(b"{}", {})
        self.assertEqual(result.failure_code, "INTERNAL_VALIDATION_ERROR")
        self.assertFalse(result.accepted)
        self.assertFalse(result.eligible)

    def test_q_component_acceptance_never_means_production_authorization(self):
        vresult = self._verify_details(_v_details())
        smanifest, _ = _s_details()
        sresult = store.validate_manifest(smanifest)
        self.assertTrue(vresult.accepted)
        self.assertFalse(vresult.eligible)
        self.assertEqual(sresult, {})
        self.assertFalse(hasattr(sresult, "eligible"))

    def test_repeated_mutations_have_deterministic_structured_outcomes(self):
        base = _v_details()
        observed = []
        for _ in range(3):
            manifest = json.loads(base[0])
            manifest["outputs"]["details_csv"]["sha256"] = "0" * 64
            result = self._verify_details((_encode(manifest), base[1], *base[2:]))
            observed.append((result.classification, result.failure_code, result.accepted, result.eligible))
        self.assertEqual(observed, [("INVALID", "ARTIFACT_HASH_MISMATCH", False, False)] * 3)


if __name__ == "__main__":
    unittest.main()
