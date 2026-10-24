"""Isolated synthetic lifecycle probe across separate manifest contracts.

Fixtures for each native contract are authored independently. Cross-version
submissions pass through the compatibility fence and are rejected; no field
translation or filesystem access occurs. Component results remain separate.
"""
from __future__ import annotations

import copy
import hashlib
import json
from typing import Any, Mapping, Sequence

from tools import provenance_manifest_schema as schema
from tools import manifest_contract_compat as compat
import pipeline_generation_store as generation_store


RUN_SOURCE = "7c9d5c21-66eb-4ee7-84b8-2523d3bbf1d2"
RUN_DETAILS = "2eb56da5-e63b-4e6b-9d3c-b5abff7aa63b"
RUN_ANALYSIS = "8b0f41c4-32e7-4c26-80ae-2e995ef5a189"
STARTED = "2026-10-18T12:00:00Z"
COMPLETED = "2026-10-18T12:01:00Z"
JOB_HEADER = "Title,Company,Location,Easy Apply,Actively Reviewing,Link\n"
DETAILS_HEADER = "Title,Company,Location,Experience,Easy Apply,Skills,Link,Description\n"


def _fingerprint(data: bytes) -> dict[str, Any]:
    return {"sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data)}


def _encode_unchecked(manifest: Any) -> bytes:
    """Serialize a test subject without running schema validation a second time."""
    return json.dumps(manifest, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _output(role: str, data: bytes, rows: int) -> dict[str, Any]:
    path, fmt = schema.ROLE_PATH_FORMAT[role]
    return {"relative_path": path, **_fingerprint(data), "record_count": rows, "format": fmt}


def _base(run_id: str, stage: str, status: str) -> dict[str, Any]:
    return {
        "schema_version": schema.SCHEMA_VERSION,
        "run_id": run_id,
        "stage": stage,
        "status": status,
        "producer": {"id": "synthetic-offline-lifecycle", "version": "1"},
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
        "policy_dependencies": ["D1", "D2", "D13"],
        "extensions": {},
    }


def _source_manifest(source_bytes: bytes, record_count: int, status: str) -> dict[str, Any]:
    manifest = _base(RUN_SOURCE, "source", status)
    manifest["source"] = {
        "role": "jobs_csv", **_fingerprint(source_bytes), "record_count": record_count,
        "encoding": "utf-8", "format": "csv/jobs-v1",
    }
    manifest["outputs"] = {"jobs_csv": _output("jobs_csv", source_bytes, record_count)}
    return manifest


def _details_manifest(
    source_manifest: dict[str, Any],
    source_bytes: bytes,
    status: str,
    dispositions: Sequence[str],
    *,
    overrides: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, bytes]]:
    source_count = len(dispositions)
    source_fp = _fingerprint(source_bytes)
    source_status = source_manifest["status"]
    source_output = source_manifest["outputs"]["jobs_csv"]
    source = {
        "role": "jobs_csv", **source_fp, "record_count": source_count,
        "encoding": "utf-8", "format": "csv/jobs-v1",
    }
    source_manifest_bytes = _encode_unchecked(source_manifest)
    reference = {
        "stage": "source", "run_id": source_manifest["run_id"], "status": source_status,
        "manifest_sha256": hashlib.sha256(source_manifest_bytes).hexdigest(),
        "artifact_role": "jobs_csv", "artifact_sha256": source_output["sha256"],
        "size_bytes": source_output["size_bytes"], "record_count": source_output["record_count"],
        "format": source_output["format"],
    }
    processed = sum(item == "PROCESSED" for item in dispositions)
    skipped = sum(item == "INTENTIONAL_SKIP" for item in dispositions)
    failed = sum(item == "FAILED" for item in dispositions)
    details_lines = []
    for index, disposition in enumerate(dispositions, 1):
        if disposition == "PROCESSED":
            details_lines.append(f'"Synthetic {index}","Example Co","Offline","", "No","Python","https://example.test/{index}","Synthetic description"\n')
    details_bytes = (DETAILS_HEADER + "".join(details_lines)).encode("utf-8")
    diagnostics_bytes = b"[]"
    outputs = {}
    artifacts: dict[str, bytes] = {}
    if status in {"COMPLETE", "PARTIAL"}:
        outputs = {
            "details_csv": _output("details_csv", details_bytes, processed),
            "diagnostics_json": _output("diagnostics_json", diagnostics_bytes, 0),
        }
        artifacts = {"details_csv": details_bytes, "diagnostics_json": diagnostics_bytes}

    manifest = _base(RUN_DETAILS, "job_details", status)
    manifest["source"] = source
    manifest["input_generation"] = reference
    manifest["outputs"] = outputs
    if status != "IN_PROGRESS":
        manifest["accounting"] = {
            "source_occurrences": source_count,
            "processed_occurrences": processed,
            "intentional_skip_occurrences": skipped,
            "failed_occurrences": failed,
            "output_rows": processed,
        }
        manifest["occurrences"] = []
        for ordinal, disposition in enumerate(dispositions, 1):
            manifest["occurrences"].append({
                "ordinal": ordinal,
                "occurrence_key": f"{source_fp['sha256']}:{ordinal}",
                "disposition": disposition,
                "logical_identity": f"synthetic-{ordinal}",
                "reason_code": "SYNTHETIC_SKIP" if disposition == "INTENTIONAL_SKIP" else None,
                "policy_rule_id": "synthetic-rule" if disposition == "INTENTIONAL_SKIP" else None,
                "retained_occurrence_key": None,
                "error_code": "SYNTHETIC_FAILURE" if disposition == "FAILED" else None,
                "quality_code": None,
                "output_row": (sum(x == "PROCESSED" for x in dispositions[:ordinal]) if disposition == "PROCESSED" else None),
            })
    if status == "FAILED":
        manifest["failure"] = {"code": "SYNTHETIC_STAGE_FAILURE"}
        manifest["outputs"] = {}
        artifacts = {}
    if status == "EMPTY":
        manifest["outputs"] = {}
        artifacts = {}
    if status == "IN_PROGRESS":
        manifest.update(source=None, input_generation=None, accounting=None, occurrences=None, outputs={}, diagnostics=[], policy_dependencies=[], previous_generation=None)
    if overrides:
        for key, value in overrides.items():
            manifest[key] = copy.deepcopy(value)
    return manifest, artifacts


def _capture_schema(manifest: Any) -> dict[str, Any]:
    try:
        result = schema.validate_manifest(manifest)
        return {
            "outcome": "VALID" if result.schema_valid else "INVALID",
            "schema_valid": result.schema_valid,
            "authorization": result.authorization,
            "policy_resolved": result.policy_resolved,
            "unresolved_decisions": list(result.unresolved_decisions),
            "findings": list(result.unresolved_findings),
            "raw_result": {
                "schema_valid": result.schema_valid,
                "policy_resolved": result.policy_resolved,
                "authorization": result.authorization,
                "unresolved_decisions": list(result.unresolved_decisions),
                "policy_dependencies": list(result.policy_dependencies),
                "unresolved_findings": list(result.unresolved_findings),
            },
            "failure_code": None,
        }
    except schema.SchemaValidationError as exc:
        return {"outcome": "INVALID", "schema_valid": False, "authorization": "NOT_AUTHORIZED", "failure_code": exc.code, "message": str(exc)}
    except Exception as exc:  # keep unexpected validation failures observable and bounded
        return {"outcome": "ERROR", "schema_valid": False, "authorization": "NOT_AUTHORIZED", "failure_code": "UNEXPECTED_VALIDATION_EXCEPTION", "exception_type": type(exc).__name__, "message": str(exc)}


def _capture_compat(target: str, **kwargs: Any) -> dict[str, Any]:
    """Keep orchestration-boundary failures structured even if dispatch raises."""
    try:
        return compat.validate_for_component(target=target, **kwargs)
    except Exception as exc:
        return {
            "target": target,
            "source_schema_version": kwargs.get("source_schema_version"),
            "outcome": "ERROR",
            "accepted": False,
            "eligible": False,
            "authorization": "NOT_AUTHORIZED",
            "failure_code": "UNEXPECTED_VALIDATION_EXCEPTION",
            "message": f"{type(exc).__name__}: {exc}",
            "exception_type": type(exc).__name__,
            "findings": {},
        }


def _source_binding_diagnostics(manifest: Mapping[str, Any], source_manifest: Mapping[str, Any]) -> dict[str, Any]:
    reference = manifest.get("input_generation")
    status = manifest.get("status")
    if reference is None:
        outcome = "CONSISTENT" if status in {"IN_PROGRESS", "FAILED"} else "MISSING_SOURCE_GENERATION_BINDING"
        return {"outcome": outcome, "source_run_id": source_manifest["run_id"], "declared_run_id": None, "mismatched_fields": []}
    if not isinstance(reference, Mapping):
        return {"outcome": "MALFORMED_SOURCE_GENERATION_BINDING", "source_run_id": source_manifest["run_id"],
                "declared_run_id": None, "mismatched_fields": ["input_generation"]}
    source_output = source_manifest["outputs"]["jobs_csv"]
    source_bytes = _encode_unchecked(source_manifest)
    expected = {
        "stage": "source", "run_id": source_manifest["run_id"], "status": source_manifest["status"],
        "manifest_sha256": hashlib.sha256(source_bytes).hexdigest(), "artifact_role": "jobs_csv",
        "artifact_sha256": source_output["sha256"], "size_bytes": source_output["size_bytes"],
        "record_count": source_output["record_count"], "format": source_output["format"],
    }
    mismatched = sorted(key for key in set(reference) | set(expected) if reference.get(key) != expected.get(key))
    if reference.get("run_id") != source_manifest["run_id"]:
        outcome = "CONTRADICTORY_SOURCE_GENERATION_ID"
    elif mismatched:
        outcome = "CONTRADICTORY_SOURCE_GENERATION_METADATA"
    else:
        outcome = "CONSISTENT"
    return {"outcome": outcome, "source_run_id": source_manifest["run_id"],
            "declared_run_id": reference.get("run_id"), "mismatched_fields": mismatched}


def _aggregate_lifecycle(status: str, schema_result: Mapping[str, Any], schema_compat: Mapping[str, Any],
                         verifier_native: Mapping[str, Any], store_native: Mapping[str, Any],
                         analyzer_binding: Mapping[str, Any]) -> tuple[str, list[str]]:
    """Aggregate required native stages fail-closed while preserving expected status outcomes."""
    stages = {
        "manifest_schema_v2": schema_result,
        "schema_v2_compatibility": schema_compat,
        "offline_provenance_verifier": verifier_native,
        "generation_store": store_native,
    }
    errors = [name for name, result in stages.items() if result.get("outcome") == "ERROR"]
    if analyzer_binding.get("outcome") == "ERROR":
        errors.append("generation_store_analyzer_input_binding")
    if errors:
        return "ERROR", errors

    rejected = []
    if schema_result.get("outcome") != "VALID":
        rejected.append("manifest_schema_v2")
    if schema_compat.get("outcome") != "VALID" or not schema_compat.get("accepted"):
        rejected.append("schema_v2_compatibility")
    if store_native.get("outcome") != "VALID" or not store_native.get("accepted"):
        rejected.append("generation_store")

    expected_verifier_outcomes = {
        "COMPLETE": "VERIFIED_DATA_ONLY", "EMPTY": "EMPTY_DATA_ONLY",
        "PARTIAL": "UNSUPPORTED_POLICY", "FAILED": "FAILED", "IN_PROGRESS": "INCOMPLETE",
    }
    if verifier_native.get("outcome") != expected_verifier_outcomes[status]:
        rejected.append("offline_provenance_verifier")
    if status in {"COMPLETE", "EMPTY"}:
        if analyzer_binding.get("outcome") != "MATCHED" or not analyzer_binding.get("accepted"):
            rejected.append("generation_store_analyzer_input_binding")
    elif analyzer_binding.get("outcome") != "NOT_APPLICABLE":
        rejected.append("generation_store_analyzer_input_binding")
    if rejected:
        return "REJECTED", rejected
    if status == "IN_PROGRESS":
        return "INCOMPLETE", []
    if status == "PARTIAL":
        return "PARTIAL_POLICY_UNRESOLVED", []
    if status == "FAILED":
        return "FAILED_NOT_AUTHORIZED", []
    return "NATIVE_CONTRACTS_VALIDATED_CROSS_VERSION_INCOMPATIBLE", []


def _native_contract_fixtures(source_records: Sequence[str], status: str) -> tuple[dict[str, Any], bytes, dict[str, bytes], dict[str, Any], bytes]:
    """Build independent v1 fixtures from the synthetic request, never from v2 fields."""
    native_records = () if status == "EMPTY" else source_records
    source_data = (JOB_HEADER + "".join(native_records)).encode("utf-8")
    source_fp = _fingerprint(source_data)
    count = len(native_records)
    processed_rows = max(1, count - 1) if status == "PARTIAL" and count > 1 else count
    details_data = (DETAILS_HEADER + "".join(
        f'"Synthetic {index}","Example Co","Offline","","No","Python","https://example.test/{index}","Synthetic description"\n'
        for index in range(1, processed_rows + 1)
    )).encode("utf-8")
    diagnostics = b"[]"
    details_fp = _fingerprint(details_data)
    diagnostics_fp = _fingerprint(diagnostics)

    def verifier_artifact(path: str, digest: dict[str, Any], rows: int, fmt: str) -> dict[str, Any]:
        return {"relative_path": path, **digest, "record_count": rows, "format": fmt}

    # Verifier-v1 source and details manifests are authored using that contract's own keys.
    verifier_source = {
        "schema_version": 1, "run_id": RUN_SOURCE, "stage": "source", "status": "EMPTY" if count == 0 else "COMPLETE",
        "producer": {"id": "synthetic-offline-lifecycle", "version": "1"}, "started_at": STARTED, "completed_at": COMPLETED,
        "source": {"role": "jobs_csv", **source_fp, "record_count": count, "encoding": "utf-8", "format": "csv/jobs-v1"},
        "input_generation": None, "accounting": None, "occurrences": None,
        "outputs": {"jobs_csv": verifier_artifact("jobs.csv", source_fp, count, "csv/jobs-v1")}, "failure": None,
    }
    verifier_source_bytes = _encode_unchecked(verifier_source)
    verifier_status = status
    v_outputs: dict[str, Any] = {}
    v_artifacts: dict[str, bytes] = {}
    v_source: Any = None
    v_ref: Any = None
    v_accounting: Any = None
    v_occurrences: Any = None
    v_failure: Any = None
    if status in {"COMPLETE", "EMPTY", "PARTIAL"}:
        v_source = {"role": "jobs_csv", **source_fp, "record_count": count, "encoding": "utf-8", "format": "csv/jobs-v1"}
        source_desc = verifier_source["outputs"]["jobs_csv"]
        v_ref = {"stage": "source", "run_id": RUN_SOURCE, "status": verifier_source["status"],
                 "manifest_sha256": hashlib.sha256(verifier_source_bytes).hexdigest(), "artifact_role": "jobs_csv",
                 "artifact_sha256": source_fp["sha256"], "artifact_size_bytes": source_fp["size_bytes"], "record_count": count}
        if status == "EMPTY":
            v_accounting = {"source_occurrences": 0, "processed_occurrences": 0, "intentional_skip_occurrences": 0, "failed_occurrences": 0, "output_rows": 0}
            v_occurrences = []
        else:
            proc = processed_rows
            fail = max(1, count - proc) if status == "PARTIAL" else 0
            v_accounting = {"source_occurrences": count, "processed_occurrences": proc, "intentional_skip_occurrences": 0, "failed_occurrences": fail, "output_rows": proc}
            v_occurrences = []
            for ordinal in range(1, count + 1):
                processed = ordinal <= proc
                v_occurrences.append({"ordinal": ordinal, "occurrence_key": f"{source_fp['sha256']}:{ordinal}",
                    "logical_identity": f"synthetic-{ordinal}", "disposition": "PROCESSED" if processed else "FAILED",
                    "reason_code": None, "policy_rule_id": None, "retained_occurrence_key": None,
                    "error_code": None if processed else "SYNTHETIC_FAILURE", "quality_code": None,
                    "output_row": ordinal if processed else None})
        if status in {"COMPLETE", "PARTIAL"}:
            v_outputs = {"details_csv": verifier_artifact("job_details.csv", details_fp, v_accounting["output_rows"], "csv/details-v1"),
                         "diagnostics_json": verifier_artifact("job_details_diagnostics.json", diagnostics_fp, 0, "json/diagnostics-v1")}
            v_artifacts = {"details_csv": details_data, "diagnostics_json": diagnostics}
    elif status == "FAILED":
        v_failure = {"code": "SYNTHETIC_STAGE_FAILURE"}
    verifier_manifest = {"schema_version": 1, "run_id": RUN_DETAILS, "stage": "job_details", "status": verifier_status,
        "producer": {"id": "synthetic-offline-lifecycle", "version": "1"}, "started_at": STARTED,
        "completed_at": None if status == "IN_PROGRESS" else COMPLETED, "source": v_source, "input_generation": v_ref,
        "accounting": v_accounting, "occurrences": v_occurrences, "outputs": v_outputs, "failure": v_failure}
    if status == "IN_PROGRESS":
        verifier_manifest.update(source=None, input_generation=None, accounting=None, occurrences=None, outputs={}, failure=None)
    verifier_bytes = _encode_unchecked(verifier_manifest)

    # Store-v1 uses an independent aggregate-only manifest, with no source-stage reference.
    store_status = status
    store_source = None
    store_accounting = None
    store_outputs: dict[str, Any] = {}
    store_failure = {"code": "SYNTHETIC_STAGE_FAILURE"} if status == "FAILED" else None
    if status != "IN_PROGRESS" and status != "FAILED":
        row_count = 0 if status == "EMPTY" else count
        store_source = {"role": "jobs.csv", "sha256": source_fp["sha256"], "size_bytes": source_fp["size_bytes"], "record_count": row_count}
        store_processed = processed_rows if status == "PARTIAL" else row_count
        store_failed = row_count - store_processed if status == "PARTIAL" else 0
        store_accounting = {"source_records": row_count, "processed_records": store_processed, "intentionally_skipped_records": 0, "failed_records": store_failed}
        if status in {"COMPLETE", "PARTIAL"}:
            store_outputs = {"details_csv": {"relative_path": "job_details.csv", **details_fp}, "diagnostics_json": {"relative_path": "job_details_diagnostics.json", **diagnostics_fp}}
    if status == "FAILED":
        store_accounting = {"source_records": count, "processed_records": 0, "intentionally_skipped_records": 0, "failed_records": count}
        store_source = {"role": "jobs.csv", "sha256": source_fp["sha256"], "size_bytes": source_fp["size_bytes"], "record_count": count}
    store_manifest = {"schema_version": 1, "run_id": RUN_DETAILS, "stage": "job_details", "status": store_status,
        "started_at": STARTED, "completed_at": None if status == "IN_PROGRESS" else COMPLETED,
        "source": store_source, "input_generation": None, "accounting": store_accounting, "outputs": store_outputs, "failure": store_failure}
    return verifier_manifest, verifier_bytes, v_artifacts, store_manifest, details_data


def run_offline_lifecycle(
    source_records: Sequence[str],
    *,
    status: str = "COMPLETE",
    dispositions: Sequence[str] | None = None,
    manifest_overrides: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Run separate native contracts and explicit cross-version fences on synthetic data."""
    if status not in schema.STATUSES:
        raise ValueError(f"unsupported lifecycle status: {status}")
    if any(not isinstance(record, str) for record in source_records):
        raise TypeError("source_records must contain synthetic CSV row strings")
    source_bytes = (JOB_HEADER + "".join(source_records)).encode("utf-8")
    source_count = len(source_records)
    source_status = "EMPTY" if source_count == 0 else "COMPLETE"
    source_manifest = _source_manifest(source_bytes, source_count, source_status)
    if dispositions is None:
        if status == "COMPLETE":
            dispositions = ["PROCESSED"] * source_count
        elif status == "EMPTY":
            dispositions = []
        elif status == "PARTIAL":
            dispositions = ["PROCESSED"] + (["FAILED"] if source_count > 1 else [])
        elif status == "FAILED":
            dispositions = ["FAILED"] * source_count
        else:
            dispositions = []
    manifest, artifacts = _details_manifest(source_manifest, source_bytes, status, dispositions, overrides=manifest_overrides)
    schema_result = _capture_schema(manifest)
    v1_manifest, v1_bytes, v1_artifacts, store_manifest, native_details_bytes = _native_contract_fixtures(source_records, status)
    v1_records = () if status == "EMPTY" else source_records
    v1_source_bytes_data = (JOB_HEADER + "".join(v1_records)).encode("utf-8")
    v1_source_count = len(v1_records)
    v1_source = {
        "schema_version": 1, "run_id": RUN_SOURCE, "stage": "source",
        "status": "EMPTY" if v1_source_count == 0 else "COMPLETE", "producer": {"id": "synthetic-offline-lifecycle", "version": "1"},
        "started_at": STARTED, "completed_at": COMPLETED,
        "source": {"role": "jobs_csv", **_fingerprint(v1_source_bytes_data), "record_count": v1_source_count, "encoding": "utf-8", "format": "csv/jobs-v1"},
        "input_generation": None, "accounting": None, "occurrences": None,
        "outputs": {"jobs_csv": {"relative_path": "jobs.csv", **_fingerprint(v1_source_bytes_data), "record_count": v1_source_count, "format": "csv/jobs-v1"}}, "failure": None,
    }
    v1_source_bytes = _encode_unchecked(v1_source)
    verifier_native = _capture_compat(
        "offline_verifier_v1", source_schema_version=1, manifest=v1_manifest,
        manifest_bytes=v1_bytes, artifacts_by_role=v1_artifacts, expected_stage="job_details",
        upstream_manifest_bytes=v1_source_bytes, upstream_artifacts_by_role={"jobs_csv": v1_source_bytes_data},
    )
    store_native = _capture_compat("generation_store_v1", source_schema_version=1, manifest=store_manifest)
    analyzer_binding: dict[str, Any]
    if status in {"COMPLETE", "EMPTY"} and store_native["accepted"]:
        try:
            details_manifest_bytes = generation_store.serialize_manifest(store_manifest)
            details_digest = _fingerprint(details_manifest_bytes)["sha256"]
            details_fp = _fingerprint(native_details_bytes)
            row_count = 0 if status == "EMPTY" else source_count
            analysis_bytes = ("Title,Company,Score\n" + "".join(f'"Synthetic {i}","Example Co",0\n' for i in range(1, row_count + 1))).encode("utf-8")
            analyzer = {
                "schema_version": 1, "run_id": RUN_ANALYSIS, "stage": "job_analyzer", "status": status,
                "started_at": STARTED, "completed_at": COMPLETED,
                "source": {"role": "details_csv", "sha256": details_fp["sha256"], "size_bytes": details_fp["size_bytes"], "record_count": row_count},
                "input_generation": {"stage": "job_details", "run_id": RUN_DETAILS, "status": status,
                    "manifest_sha256": details_digest,
                    "artifact_role": "details_csv" if status == "COMPLETE" else None,
                    "artifact_sha256": details_fp["sha256"] if status == "COMPLETE" else None,
                    "artifact_size_bytes": details_fp["size_bytes"] if status == "COMPLETE" else None},
                "accounting": {"source_records": row_count, "processed_records": row_count, "intentionally_skipped_records": 0, "failed_records": 0},
                "outputs": ({"analysis_csv": {"relative_path": "job_analysis.csv", **_fingerprint(analysis_bytes)}} if status == "COMPLETE" else {}),
                "failure": None,
            }
            analyzer_result = _capture_compat("generation_store_v1", source_schema_version=1, manifest=analyzer)
            if analyzer_result["outcome"] == "ERROR":
                analyzer_binding = {"outcome": "ERROR", "accepted": False, "raw_result": analyzer_result}
            elif not analyzer_result["accepted"]:
                analyzer_binding = {"outcome": "REJECTED", "accepted": False, "raw_result": analyzer_result}
            else:
                generation_store.validate_analyzer_input_binding(
                    analyzer, store_manifest, details_manifest_bytes=details_manifest_bytes,
                    details_artifact_bytes=native_details_bytes if status == "COMPLETE" else None,
                )
                analyzer_binding = {"outcome": "MATCHED", "accepted": True, "raw_result": analyzer_result,
                    "binding_result": "EXACT_SYNTHETIC_MANIFEST_AND_ARTIFACT_BYTES"}
        except generation_store.GenerationValidationError as exc:
            analyzer_binding = {"outcome": "REJECTED", "accepted": False,
                "failure_code": "GENERATION_VALIDATION_REJECTED", "exception_type": type(exc).__name__, "message": str(exc)}
        except Exception as exc:
            analyzer_binding = {"outcome": "ERROR", "accepted": False, "exception_type": type(exc).__name__, "message": str(exc)}
    else:
        analyzer_binding = {"outcome": "NOT_APPLICABLE", "accepted": False, "reason": "details generation is not selectable in the store contract"}
    schema_compat = _capture_compat("schema_v2", source_schema_version=2, manifest=manifest)
    verifier_cross = _capture_compat("offline_verifier_v1", source_schema_version=2, manifest=manifest, manifest_bytes=_encode_unchecked(manifest), artifacts_by_role=artifacts)
    store_cross = _capture_compat("generation_store_v1", source_schema_version=2, manifest=manifest)
    binding_diagnostics = _source_binding_diagnostics(manifest, source_manifest)
    aggregate_outcome, aggregate_failures = _aggregate_lifecycle(status, schema_result, schema_compat, verifier_native, store_native, analyzer_binding)

    incompatibilities = [
        "verifier expects schema_version=1 and a 13-key manifest; canonical schema v2 emits schema_version=2 and 17 keys (including diagnostics, previous_generation, policy_dependencies, extensions)",
        "generation store expects schema_version=1 and an 11-key downstream manifest; canonical schema v2 emits schema_version=2 and 17 keys",
        "canonical schema input_generation uses size_bytes; verifier expects artifact_size_bytes; generation store expects artifact_size_bytes and has no source-stage manifest support",
        "generation store accounting uses source_records/processed_records/intentionally_skipped_records/failed_records; canonical schema uses occurrence-suffixed keys plus output_rows",
    ]
    return {
        "lifecycle_version": 1,
        "status": status,
        "run_id": RUN_DETAILS,
        "synthetic_only": True,
        "source_record_count": source_count,
        "declared_accounting": copy.deepcopy(manifest.get("accounting")),
        "stages": {
            "manifest_schema_v2": schema_result,
            "source_generation_binding": binding_diagnostics,
        "offline_provenance_verifier": {"outcome": verifier_native["outcome"], "accepted": verifier_native["accepted"], "eligible": False,
            "failure_code": verifier_native["failure_code"], "raw_result": verifier_native},
            "generation_store": {"outcome": store_native["outcome"], "accepted": store_native["accepted"],
                "failure_code": store_native["failure_code"], "raw_result": store_native},
            "generation_store_analyzer_input_binding": analyzer_binding,
            "schema_v2_compatibility": schema_compat,
            "synthetic_manifest_state": {"status": manifest.get("status"),
                "previous_generation": copy.deepcopy(manifest.get("previous_generation")),
                "declared_output_roles": sorted(manifest.get("outputs", {}).keys()) if isinstance(manifest.get("outputs"), dict) else None},
            "native_contract_fixtures": {"offline_verifier_v1": {"schema_version": v1_manifest["schema_version"], "key_count": len(v1_manifest), "status": v1_manifest["status"]},
                "generation_store_v1": {"schema_version": store_manifest["schema_version"], "key_count": len(store_manifest), "status": store_manifest["status"]}},
        },
        "component_contract_compatibility": {"outcome": "CROSS_VERSION_REJECTED", "mismatches": incompatibilities,
            "schema_v2_native": schema_compat, "v2_to_verifier_v1": verifier_cross, "v2_to_generation_store_v1": store_cross},
        "aggregate_outcome": aggregate_outcome,
        "aggregate_failures": aggregate_failures,
        "production_selection_authorized": False,
        "publication_authorized": False,
    }


__all__ = ["run_offline_lifecycle"]
