"""Proposed, isolated canonical generation-manifest schema v2.

This module performs pure in-memory schema and cross-field validation only.
It does not verify artifact bytes, source authenticity, filesystem containment,
safe file opening, publication, selection, rollback authority, or durability.
Every successful result remains policy-unapproved and non-authorizing.
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePosixPath
from typing import Any, Mapping


SCHEMA_VERSION = 2
STAGES = frozenset({"source", "job_details", "job_analyzer"})
STATUSES = frozenset({"IN_PROGRESS", "COMPLETE", "EMPTY", "PARTIAL", "FAILED"})
OPEN_DECISIONS = tuple(f"D{i}" for i in range(1, 14))

TOP_LEVEL_KEYS = frozenset({
    "schema_version", "run_id", "stage", "status", "producer",
    "started_at", "completed_at", "source", "input_generation",
    "accounting", "occurrences", "outputs", "diagnostics", "failure",
    "previous_generation", "policy_dependencies", "extensions",
})
SOURCE_KEYS = frozenset({
    "role", "sha256", "size_bytes", "record_count", "encoding", "format",
})
INPUT_KEYS = frozenset({
    "stage", "run_id", "status", "manifest_sha256", "artifact_role",
    "artifact_sha256", "size_bytes", "record_count", "format",
})
ACCOUNTING_KEYS = frozenset({
    "source_occurrences", "processed_occurrences",
    "intentional_skip_occurrences", "failed_occurrences", "output_rows",
})
OCCURRENCE_KEYS = frozenset({
    "ordinal", "occurrence_key", "disposition", "logical_identity",
    "reason_code", "policy_rule_id", "retained_occurrence_key",
    "error_code", "quality_code", "output_row",
})
OUTPUT_KEYS = frozenset({
    "relative_path", "sha256", "size_bytes", "record_count", "format",
})
DIAGNOSTIC_KEYS = frozenset({"code", "occurrence_key", "artifact_role"})
PREVIOUS_KEYS = frozenset({
    "stage", "run_id", "status", "manifest_sha256", "source_sha256",
})

ROLE_PATH_FORMAT = {
    "jobs_csv": ("jobs.csv", "csv/jobs-v1"),
    "details_csv": ("job_details.csv", "csv/details-v1"),
    "diagnostics_json": ("job_details_diagnostics.json", "json/diagnostics-v1"),
    "analysis_csv": ("job_analysis.csv", "csv/analysis-v1"),
}
STAGE_ROLES = {
    "source": frozenset({"jobs_csv"}),
    "job_details": frozenset({"details_csv", "diagnostics_json"}),
    "job_analyzer": frozenset({"analysis_csv"}),
}
EXPECTED_INPUT_STAGE = {"job_details": "source", "job_analyzer": "job_details"}
EXPECTED_SOURCE_ROLE = {"source": "jobs_csv", "job_details": "jobs_csv", "job_analyzer": "details_csv"}

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_UUID4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
_TIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
_DISPOSITIONS = frozenset({"PROCESSED", "INTENTIONAL_SKIP", "FAILED"})


class SchemaValidationError(ValueError):
    """Invalid or contradictory canonical-schema input."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class SchemaValidationResult:
    """Schema result, deliberately separate from policy approval/eligibility."""

    schema_valid: bool
    policy_resolved: bool
    authorization: str
    unresolved_decisions: tuple[str, ...]
    policy_dependencies: tuple[str, ...]
    unresolved_findings: tuple[str, ...]


def _fail(code: str, message: str) -> None:
    raise SchemaValidationError(code, message)


def _exact_keys(value: Any, expected: frozenset[str], label: str) -> None:
    if not isinstance(value, dict) or set(value) != set(expected):
        _fail("FIELD_SET_INVALID", f"{label} must contain exactly {sorted(expected)}")


def _text(value: Any, label: str, *, nonempty: bool = True) -> None:
    if not isinstance(value, str) or (nonempty and not value.strip()):
        _fail("FIELD_TYPE_INVALID", f"{label} must be {'nonempty ' if nonempty else ''}text")


def _count(value: Any, label: str) -> None:
    if type(value) is not int or value < 0:
        _fail("COUNT_INVALID", f"{label} must be a nonnegative integer")


def _digest(value: Any, label: str) -> None:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        _fail("FINGERPRINT_INVALID", f"{label} must be lowercase SHA-256 hex")


def _run_id(value: Any, label: str = "run_id") -> None:
    if not isinstance(value, str) or _UUID4_RE.fullmatch(value) is None:
        _fail("IDENTIFIER_INVALID", f"{label} must be canonical lowercase UUIDv4")
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError) as exc:
        raise SchemaValidationError("IDENTIFIER_INVALID", f"{label} is not a UUID") from exc
    if parsed.version != 4 or str(parsed) != value:
        _fail("IDENTIFIER_INVALID", f"{label} must be canonical lowercase UUIDv4")


def _timestamp(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or _TIME_RE.fullmatch(value) is None:
        _fail("TIMESTAMP_INVALID", f"{label} must use UTC YYYY-MM-DDTHH:MM:SSZ")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise SchemaValidationError("TIMESTAMP_INVALID", f"{label} is not a calendar timestamp") from exc
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        _fail("TIMESTAMP_INVALID", f"{label} is not canonical")
    return parsed


def _relative_path(value: Any, role: str) -> None:
    _text(value, f"outputs.{role}.relative_path")
    if "\\" in value or ":" in value or "\x00" in value:
        _fail("ARTIFACT_PATH_INVALID", f"outputs.{role}.relative_path is not portable relative syntax")
    parts = value.split("/")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or path.as_posix() != value
        or any(part in {"", ".", ".."} for part in parts)
        or value != ROLE_PATH_FORMAT[role][0]
    ):
        _fail("ARTIFACT_PATH_INVALID", f"outputs.{role}.relative_path is not the role's canonical logical path")


def _validate_source(value: Any, stage: str) -> None:
    _exact_keys(value, SOURCE_KEYS, "source")
    role = EXPECTED_SOURCE_ROLE[stage]
    if value["role"] != role:
        _fail("SOURCE_ROLE_MISMATCH", f"{stage} source role must be {role}")
    _digest(value["sha256"], "source.sha256")
    _count(value["size_bytes"], "source.size_bytes")
    _count(value["record_count"], "source.record_count")
    if value["encoding"] != "utf-8":
        _fail("SOURCE_FORMAT_INVALID", "source.encoding must be utf-8 in this proposal")
    expected_format = ROLE_PATH_FORMAT[role][1]
    if value["format"] != expected_format:
        _fail("SOURCE_FORMAT_INVALID", f"source.format must be {expected_format}")


def _validate_reference(value: Any, expected_stage: str, label: str) -> None:
    _exact_keys(value, INPUT_KEYS, label)
    if not isinstance(value["stage"], str) or value["stage"] != expected_stage:
        _fail("GENERATION_REFERENCE_CONFLICT", f"{label}.stage must be {expected_stage}")
    _run_id(value["run_id"], f"{label}.run_id")
    if not isinstance(value["status"], str) or value["status"] not in {"COMPLETE", "EMPTY"}:
        _fail("GENERATION_REFERENCE_CONFLICT", f"{label}.status must reference COMPLETE or EMPTY")
    _digest(value["manifest_sha256"], f"{label}.manifest_sha256")
    expected_role = "jobs_csv" if expected_stage == "source" else "details_csv"
    if value["artifact_role"] != expected_role:
        _fail("GENERATION_REFERENCE_CONFLICT", f"{label}.artifact_role must be {expected_role}")
    _digest(value["artifact_sha256"], f"{label}.artifact_sha256")
    _count(value["size_bytes"], f"{label}.size_bytes")
    _count(value["record_count"], f"{label}.record_count")
    expected_format = ROLE_PATH_FORMAT[expected_role][1]
    if value["format"] != expected_format:
        _fail("GENERATION_REFERENCE_CONFLICT", f"{label}.format must be {expected_format}")


def _validate_outputs(value: Any, stage: str, status: str) -> None:
    if not isinstance(value, dict):
        _fail("OUTPUT_SET_INVALID", "outputs must be an object keyed by unique artifact role")
    roles = set(value)
    if any(not isinstance(role, str) or role not in STAGE_ROLES[stage] for role in roles):
        _fail("OUTPUT_ROLE_INVALID", f"outputs contains a role unsupported by {stage}")
    if status in {"IN_PROGRESS", "FAILED"} or (status == "EMPTY" and stage != "source"):
        if roles:
            _fail("OUTCOME_CONTRADICTION", f"{status} {stage} cannot declare data outputs in this proposal")
        return
    expected = set(STAGE_ROLES[stage])
    if roles != expected:
        _fail("REQUIRED_ARTIFACT_MISSING", f"{stage} {status} requires roles {sorted(expected)}")
    paths = set()
    for role, descriptor in value.items():
        _exact_keys(descriptor, OUTPUT_KEYS, f"outputs.{role}")
        _relative_path(descriptor["relative_path"], role)
        if descriptor["relative_path"] in paths:
            _fail("DUPLICATE_ARTIFACT_PATH", "output roles cannot share a logical path")
        paths.add(descriptor["relative_path"])
        _digest(descriptor["sha256"], f"outputs.{role}.sha256")
        _count(descriptor["size_bytes"], f"outputs.{role}.size_bytes")
        _count(descriptor["record_count"], f"outputs.{role}.record_count")
        expected_format = ROLE_PATH_FORMAT[role][1]
        if descriptor["format"] != expected_format:
            _fail("OUTPUT_FORMAT_INVALID", f"outputs.{role}.format must be {expected_format}")


def _validate_occurrences(value: Any, accounting: dict, source_sha256: str) -> None:
    if not isinstance(value, list) or len(value) != accounting["source_occurrences"]:
        _fail("OCCURRENCE_ACCOUNTING_INVALID", "occurrences length must equal source_occurrences")
    counts = {name: 0 for name in _DISPOSITIONS}
    seen = set()
    output_rows = set()
    for ordinal, item in enumerate(value, 1):
        _exact_keys(item, OCCURRENCE_KEYS, f"occurrences[{ordinal - 1}]")
        if type(item["ordinal"]) is not int or item["ordinal"] != ordinal:
            _fail("OCCURRENCE_ACCOUNTING_INVALID", "occurrence ordinals must be consecutive and 1-based")
        expected_key = f"{source_sha256}:{ordinal}"
        if item["occurrence_key"] != expected_key or expected_key in seen:
            _fail("OCCURRENCE_ACCOUNTING_INVALID", "occurrence key must bind source digest and ordinal")
        seen.add(expected_key)
        if not isinstance(item["disposition"], str) or item["disposition"] not in _DISPOSITIONS:
            _fail("OCCURRENCE_DISPOSITION_INVALID", "unknown occurrence disposition")
        for key in (
            "logical_identity", "reason_code", "policy_rule_id",
            "retained_occurrence_key", "error_code", "quality_code",
        ):
            if item[key] is not None and (not isinstance(item[key], str) or not item[key].strip()):
                _fail("OCCURRENCE_FIELD_INVALID", f"{key} must be null or nonempty text")
        disposition = item["disposition"]
        counts[disposition] += 1
        if disposition == "PROCESSED":
            if item["reason_code"] is not None or item["policy_rule_id"] is not None or item["error_code"] is not None:
                _fail("OCCURRENCE_FIELD_INVALID", "PROCESSED cannot carry skip or failure fields")
            row = item["output_row"]
            if type(row) is not int or row < 1 or row > accounting["output_rows"] or row in output_rows:
                _fail("OCCURRENCE_OUTPUT_MISMATCH", "processed occurrence output_row must be unique and in range")
            output_rows.add(row)
        elif disposition == "INTENTIONAL_SKIP":
            if not item["reason_code"] or not item["policy_rule_id"] or item["error_code"] is not None or item["output_row"] is not None:
                _fail("OCCURRENCE_FIELD_INVALID", "INTENTIONAL_SKIP requires reason/rule and no output/error")
            retained = item["retained_occurrence_key"]
            if retained is not None and retained not in seen - {expected_key}:
                _fail("OCCURRENCE_REFERENCE_INVALID", "retained occurrence must refer to an earlier occurrence")
        else:
            if not item["error_code"] or item["output_row"] is not None:
                _fail("OCCURRENCE_FIELD_INVALID", "FAILED occurrence requires error_code and no output row")
    if (
        counts["PROCESSED"] != accounting["processed_occurrences"]
        or counts["INTENTIONAL_SKIP"] != accounting["intentional_skip_occurrences"]
        or counts["FAILED"] != accounting["failed_occurrences"]
    ):
        _fail("OCCURRENCE_ACCOUNTING_INVALID", "occurrence dispositions disagree with aggregate counts")
    if output_rows != set(range(1, accounting["output_rows"] + 1)):
        _fail("OCCURRENCE_OUTPUT_MISMATCH", "processed occurrences must account for each output row exactly once")


def _validate_accounting(value: Any, source_count: int, outputs: dict, stage: str) -> None:
    _exact_keys(value, ACCOUNTING_KEYS, "accounting")
    for key, count in value.items():
        _count(count, f"accounting.{key}")
    if value["source_occurrences"] != source_count:
        _fail("OCCURRENCE_ACCOUNTING_INVALID", "accounting source count disagrees with source descriptor")
    if value["source_occurrences"] != (
        value["processed_occurrences"] + value["intentional_skip_occurrences"] + value["failed_occurrences"]
    ):
        _fail("OCCURRENCE_ACCOUNTING_INVALID", "source occurrences do not reconcile to dispositions")
    primary_role = "details_csv" if stage == "job_details" else "analysis_csv"
    expected_rows = outputs.get(primary_role, {}).get("record_count", 0)
    if value["output_rows"] != expected_rows:
        _fail("OCCURRENCE_ACCOUNTING_INVALID", "output_rows disagrees with primary output descriptor")


def _validate_diagnostics(value: Any, outputs: dict, occurrence_keys: set[str]) -> None:
    if not isinstance(value, list):
        _fail("DIAGNOSTICS_INVALID", "diagnostics must be a list")
    for index, item in enumerate(value):
        _exact_keys(item, DIAGNOSTIC_KEYS, f"diagnostics[{index}]")
        if not isinstance(item["code"], str) or _CODE_RE.fullmatch(item["code"]) is None:
            _fail("DIAGNOSTICS_INVALID", "diagnostic code must be stable uppercase text")
        occurrence_key = item["occurrence_key"]
        if occurrence_key is not None:
            if not isinstance(occurrence_key, str) or occurrence_key not in occurrence_keys:
                _fail("DIAGNOSTICS_REFERENCE_INVALID", "diagnostic occurrence_key is not in the manifest ledger")
        role = item["artifact_role"]
        if role is not None:
            if not isinstance(role, str) or role not in outputs:
                _fail("DIAGNOSTICS_REFERENCE_INVALID", "diagnostic artifact_role is not declared in outputs")


def _validate_previous(value: Any, stage: str, run_id: str, source_sha256: str, findings: list[str]) -> None:
    if value is None:
        return
    _exact_keys(value, PREVIOUS_KEYS, "previous_generation")
    if not isinstance(value["stage"], str) or value["stage"] != stage or value["status"] != "COMPLETE":
        _fail("PREVIOUS_GENERATION_INVALID", "previous_generation must be a COMPLETE generation of the same stage")
    _run_id(value["run_id"], "previous_generation.run_id")
    if value["run_id"] == run_id:
        _fail("GENERATION_REFERENCE_CONFLICT", "previous_generation cannot refer to the current run")
    _digest(value["manifest_sha256"], "previous_generation.manifest_sha256")
    _digest(value["source_sha256"], "previous_generation.source_sha256")
    if source_sha256 is not None and value["source_sha256"] != source_sha256:
        findings.append("D10_SOURCE_MATCH_POLICY_OPEN")


def validate_manifest(manifest: Any) -> SchemaValidationResult:
    """Validate canonical-proposal v2 structure and internal consistency.

    No artifact bytes are opened or verified. All D1-D13 decisions remain
    unresolved; this result cannot authorize a policy, read, selection, or write.
    """
    _exact_keys(manifest, TOP_LEVEL_KEYS, "manifest")
    if type(manifest["schema_version"]) is not int or manifest["schema_version"] != SCHEMA_VERSION:
        _fail("UNKNOWN_SCHEMA_VERSION", f"schema_version must be {SCHEMA_VERSION}")
    _run_id(manifest["run_id"])
    stage, status = manifest["stage"], manifest["status"]
    if not isinstance(stage, str) or stage not in STAGES:
        _fail("STAGE_INVALID", "unsupported stage")
    if not isinstance(status, str) or status not in STATUSES:
        _fail("STATUS_INVALID", "unsupported status")

    producer = manifest["producer"]
    _exact_keys(producer, frozenset({"id", "version"}), "producer")
    _text(producer["id"], "producer.id")
    _text(producer["version"], "producer.version")

    started = _timestamp(manifest["started_at"], "started_at")
    completed_value = manifest["completed_at"]
    if status == "IN_PROGRESS":
        if completed_value is not None:
            _fail("OUTCOME_CONTRADICTION", "IN_PROGRESS requires completed_at=null")
    else:
        completed = _timestamp(completed_value, "completed_at")
        if completed < started:
            _fail("TIMESTAMP_ORDER_INVALID", "completed_at precedes started_at")

    if not isinstance(manifest["policy_dependencies"], list):
        _fail("POLICY_DEPENDENCIES_INVALID", "policy_dependencies must be a list")
    dependencies = manifest["policy_dependencies"]
    if any(not isinstance(item, str) or item not in OPEN_DECISIONS for item in dependencies):
        _fail("UNSUPPORTED_POLICY_EXTENSION", "policy_dependencies may contain only D1-D13")
    if len(set(dependencies)) != len(dependencies):
        _fail("POLICY_DEPENDENCIES_INVALID", "policy_dependencies must be unique")
    extensions = manifest["extensions"]
    if not isinstance(extensions, dict):
        _fail("EXTENSIONS_INVALID", "extensions must be an object")
    if extensions:
        _fail("UNSUPPORTED_POLICY_EXTENSION", "schema v2 prototype supports no extensions")

    source = manifest["source"]
    input_generation = manifest["input_generation"]
    accounting = manifest["accounting"]
    occurrences = manifest["occurrences"]
    outputs = manifest["outputs"]
    failure = manifest["failure"]
    findings: list[str] = []

    if stage == "source":
        if input_generation is not None:
            _fail("GENERATION_REFERENCE_CONFLICT", "source stage cannot reference an upstream generation")
    elif input_generation is not None:
        _validate_reference(input_generation, EXPECTED_INPUT_STAGE[stage], "input_generation")
    elif status not in {"IN_PROGRESS", "FAILED"}:
        _fail("GENERATION_REFERENCE_MISSING", f"{stage} terminal result requires input_generation")

    if status == "IN_PROGRESS":
        if source is not None or accounting is not None or occurrences is not None or outputs != {} or failure is not None:
            _fail("OUTCOME_CONTRADICTION", "IN_PROGRESS cannot claim source/accounting/outputs/failure")
        if manifest["diagnostics"] != [] or manifest["previous_generation"] is not None:
            _fail("OUTCOME_CONTRADICTION", "IN_PROGRESS cannot publish diagnostics or previous-generation metadata")
        if dependencies:
            findings.append("POLICY_DEPENDENCIES_UNRESOLVED")
        return SchemaValidationResult(True, False, "NOT_AUTHORIZED", OPEN_DECISIONS, tuple(sorted(dependencies)), tuple(findings))

    if failure is not None:
        _exact_keys(failure, frozenset({"code"}), "failure")
        if not isinstance(failure["code"], str) or _CODE_RE.fullmatch(failure["code"]) is None:
            _fail("FAILURE_INVALID", "failure.code must be stable uppercase text")
        if status != "FAILED":
            _fail("OUTCOME_CONTRADICTION", "failure metadata is only valid for FAILED")
    elif status == "FAILED":
        _fail("OUTCOME_CONTRADICTION", "FAILED requires failure metadata")
    if status == "FAILED":
        if outputs != {}:
            _fail("OUTCOME_CONTRADICTION", "FAILED cannot declare selectable outputs")
        if source is not None:
            _validate_source(source, stage)
        if (accounting is None) != (occurrences is None):
            _fail("OCCURRENCE_ACCOUNTING_INVALID", "failed-attempt accounting and ledger must be both present or both absent")
        if accounting is not None:
            if source is None:
                _fail("OCCURRENCE_ACCOUNTING_INVALID", "accounting requires a known source descriptor")
            if stage == "source":
                _fail("OCCURRENCE_ACCOUNTING_INVALID", "source-stage accounting is not defined in this proposal")
            _validate_accounting(accounting, source["record_count"], outputs, stage)
            _validate_occurrences(occurrences, accounting, source["sha256"])
        failed_occurrence_keys = {
            item["occurrence_key"] for item in (occurrences or [])
            if isinstance(item, dict) and isinstance(item.get("occurrence_key"), str)
        }
        _validate_diagnostics(manifest["diagnostics"], outputs, failed_occurrence_keys)
        if input_generation is not None and source is not None:
            _check_source_reference(source, input_generation)
        _validate_previous(manifest["previous_generation"], stage, manifest["run_id"], source["sha256"] if source else None, findings)
        if dependencies:
            findings.append("POLICY_DEPENDENCIES_UNRESOLVED")
        findings.append("D6_D7_FAILED_DIAGNOSTIC_POLICY_OPEN")
        return SchemaValidationResult(True, False, "NOT_AUTHORIZED", OPEN_DECISIONS, tuple(sorted(dependencies)), tuple(sorted(set(findings))))

    if source is None:
        _fail("SOURCE_MISSING", "terminal non-failed manifest requires source")
    _validate_source(source, stage)
    if stage != "source":
        _check_source_reference(source, input_generation)

    _validate_outputs(outputs, stage, status)
    if stage == "source":
        if accounting is not None or occurrences is not None:
            _fail("OCCURRENCE_ACCOUNTING_INVALID", "source-stage accounting is not defined in this proposal")
    else:
        _validate_accounting(accounting, source["record_count"], outputs, stage)
        _validate_occurrences(occurrences, accounting, source["sha256"])
    occurrence_keys = {item["occurrence_key"] for item in occurrences} if occurrences is not None else set()
    _validate_diagnostics(manifest["diagnostics"], outputs, occurrence_keys)

    if stage == "source":
        output = outputs["jobs_csv"]
        if (
            output["sha256"] != source["sha256"]
            or output["size_bytes"] != source["size_bytes"]
            or output["record_count"] != source["record_count"]
        ):
            _fail("SOURCE_OUTPUT_MISMATCH", "source descriptor must match the source snapshot output")
        if status == "COMPLETE" and source["record_count"] == 0:
            _fail("OUTCOME_CONTRADICTION", "source COMPLETE requires at least one record")
        if status == "EMPTY" and source["record_count"] != 0:
            _fail("OUTCOME_CONTRADICTION", "source EMPTY requires zero records")
        if status not in {"COMPLETE", "EMPTY"}:
            _fail("OUTCOME_CONTRADICTION", "source stage supports COMPLETE or EMPTY terminal states")
    else:
        _validate_non_source_outcome(manifest, findings)

    _validate_previous(
        manifest["previous_generation"], stage, manifest["run_id"], source["sha256"], findings
    )
    if manifest["previous_generation"] is not None:
        findings.append("D8_D10_D11_PREVIOUS_GENERATION_POLICY_OPEN")
    if dependencies:
        findings.append("POLICY_DEPENDENCIES_UNRESOLVED")
    return SchemaValidationResult(True, False, "NOT_AUTHORIZED", OPEN_DECISIONS, tuple(sorted(dependencies)), tuple(sorted(set(findings))))


def _check_source_reference(source: dict, reference: dict) -> None:
    if reference is None:
        _fail("GENERATION_REFERENCE_MISSING", "source-bearing downstream result requires its input reference")
    if (
        source["role"] != reference["artifact_role"]
        or source["sha256"] != reference["artifact_sha256"]
        or source["size_bytes"] != reference["size_bytes"]
        or source["record_count"] != reference["record_count"]
        or source["format"] != reference["format"]
    ):
        _fail("GENERATION_REFERENCE_CONFLICT", "source descriptor disagrees with input-generation artifact reference")


def _validate_non_source_outcome(manifest: dict, findings: list[str]) -> None:
    stage, status = manifest["stage"], manifest["status"]
    source = manifest["source"]
    accounting = manifest["accounting"]
    reference = manifest["input_generation"]

    if status == "EMPTY":
        if accounting["output_rows"] != 0 or accounting["processed_occurrences"] != 0 or accounting["failed_occurrences"] != 0:
            _fail("OUTCOME_CONTRADICTION", "EMPTY requires zero outputs, processed, and failed occurrences")
        if source["record_count"] == 0 and accounting["intentional_skip_occurrences"] != 0:
            _fail("OUTCOME_CONTRADICTION", "zero-record EMPTY cannot contain skips")
        if source["record_count"] > 0:
            if accounting["intentional_skip_occurrences"] != source["record_count"]:
                _fail("OUTCOME_CONTRADICTION", "nonempty EMPTY input must account for every source row as a skip")
            findings.append("D6_ALL_SKIPPED_EMPTY_POLICY_OPEN")
        if stage == "job_analyzer" and reference["status"] == "COMPLETE":
            findings.append("D6_EMPTY_ANALYSIS_POLICY_OPEN")
        if reference["status"] == "EMPTY" and source["record_count"] != 0:
            _fail("GENERATION_REFERENCE_CONFLICT", "EMPTY upstream generation must have zero source records")
        return

    if status == "COMPLETE":
        if source["record_count"] == 0 or accounting["failed_occurrences"] != 0:
            _fail("OUTCOME_CONTRADICTION", "COMPLETE requires nonempty source and no failed occurrences")
        if accounting["processed_occurrences"] == 0 and accounting["intentional_skip_occurrences"] > 0:
            findings.append("D6_ALL_SKIPPED_COMPLETE_POLICY_OPEN")
        if reference["status"] == "EMPTY":
            _fail("GENERATION_REFERENCE_CONFLICT", "COMPLETE cannot consume an EMPTY input generation")
        return

    if status == "PARTIAL":
        if source["record_count"] == 0 or accounting["failed_occurrences"] == 0:
            _fail("OUTCOME_CONTRADICTION", "PARTIAL requires nonempty source and at least one failed occurrence")
        if accounting["processed_occurrences"] == 0:
            findings.append("D6_ALL_FAILED_PARTIAL_POLICY_OPEN")
        if reference["status"] == "EMPTY":
            _fail("GENERATION_REFERENCE_CONFLICT", "PARTIAL cannot consume an EMPTY input generation")
        return

    _fail("OUTCOME_CONTRADICTION", f"{status} is not valid for {stage}")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            _fail("DUPLICATE_JSON_KEY", f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    _fail("JSON_CONSTANT_INVALID", f"non-finite JSON constant is not allowed: {value}")


def serialize_manifest(manifest: Any) -> bytes:
    """Serialize deterministically after proposed-schema validation."""
    validate_manifest(manifest)
    try:
        text = json.dumps(manifest, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise SchemaValidationError("SERIALIZATION_INVALID", "manifest is not strict JSON data") from exc
    return text.encode("utf-8")


def parse_manifest(data: bytes) -> tuple[dict, SchemaValidationResult]:
    """Parse strict UTF-8 JSON, reject duplicate keys, then validate structure."""
    if not isinstance(data, bytes):
        raise TypeError("manifest data must be bytes")
    try:
        manifest = json.loads(
            data.decode("utf-8", errors="strict"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except SchemaValidationError:
        raise
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise SchemaValidationError("MANIFEST_JSON_INVALID", "manifest is not strict UTF-8 JSON") from exc
    result = validate_manifest(manifest)
    return manifest, result


def fingerprint_supplied_bytes(data: bytes) -> dict[str, Any]:
    """Return a hash/size for bytes already supplied by the caller; perform no I/O."""
    if not isinstance(data, bytes):
        raise TypeError("data must be bytes")
    return {"sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data)}


__all__ = [
    "SCHEMA_VERSION", "STAGES", "STATUSES", "OPEN_DECISIONS",
    "SchemaValidationError", "SchemaValidationResult",
    "validate_manifest", "serialize_manifest", "parse_manifest",
    "fingerprint_supplied_bytes",
]

