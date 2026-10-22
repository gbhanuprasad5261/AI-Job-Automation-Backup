"""Experimental, pure-data provenance verifier.

This module validates explicitly supplied synthetic manifest/artifact bytes.
It performs no filesystem access, publication, network, browser, collection, or
application actions. A successful result means only that bytes are internally
consistent under this prototype contract. It never means production-selectable
or trusted. Windows filesystem security and source authenticity remain
unresolved and are outside this module.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import uuid
from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping, Optional


SCHEMA_VERSION = 1
STAGES = frozenset({"source", "job_details", "job_analyzer"})
STATUSES = frozenset({"IN_PROGRESS", "COMPLETE", "EMPTY", "PARTIAL", "FAILED"})
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
UUID4_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
FAILURE_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")

TOP_KEYS = {
    "schema_version", "run_id", "stage", "status", "producer",
    "started_at", "completed_at", "source", "input_generation",
    "accounting", "occurrences", "outputs", "failure",
}
SOURCE_KEYS = {"role", "sha256", "size_bytes", "record_count", "encoding", "format"}
INPUT_KEYS = {
    "stage", "run_id", "status", "manifest_sha256", "artifact_role",
    "artifact_sha256", "artifact_size_bytes", "record_count",
}
ACCOUNTING_KEYS = {
    "source_occurrences", "processed_occurrences",
    "intentional_skip_occurrences", "failed_occurrences", "output_rows",
}
OCCURRENCE_KEYS = {
    "ordinal", "occurrence_key", "disposition", "logical_identity",
    "reason_code", "policy_rule_id", "retained_occurrence_key",
    "error_code", "quality_code", "output_row",
}
ARTIFACT_KEYS = {"relative_path", "sha256", "size_bytes", "record_count", "format"}
EXPECTED_SOURCE = ("jobs_csv", "jobs.csv", "csv/jobs-v1", (
    "Title", "Company", "Location", "Easy Apply", "Actively Reviewing", "Link",
))
EXPECTED_DETAILS = ("details_csv", "job_details.csv", "csv/details-v1", (
    "Title", "Company", "Location", "Experience", "Easy Apply", "Skills", "Link", "Description",
))
EXPECTED_ANALYSIS = ("analysis_csv", "job_analysis.csv", "csv/analysis-v1", (
    "Title", "Company", "Location", "Easy Apply", "Match Score", "Priority",
    "Matched Skills", "Missing Skills", "Experience Required", "Experience Years",
    "Experience Skip", "Data Status", "Application Eligible", "Link",
))
EXPECTED_ARTIFACTS = {
    "source": {"jobs_csv": EXPECTED_SOURCE},
    "job_details": {
        "details_csv": EXPECTED_DETAILS,
        "diagnostics_json": ("diagnostics_json", "job_details_diagnostics.json", "json/diagnostics-v1", None),
    },
    "job_analyzer": {
        "analysis_csv": EXPECTED_ANALYSIS,
    },
}
DISPOSITIONS = {"PROCESSED", "INTENTIONAL_SKIP", "FAILED"}


@dataclass(frozen=True)
class VerificationResult:
    """Structured data-only result; eligible is always false in this prototype."""

    classification: str
    accepted: bool
    eligible: bool
    failure_code: Optional[str] = None
    run_id: Optional[str] = None
    stage: Optional[str] = None
    status: Optional[str] = None
    policy_dependencies: tuple[str, ...] = ()
    artifact_bytes: Mapping[str, bytes] = MappingProxyType({})


class _Invalid(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def fingerprint(data: bytes) -> dict:
    if not isinstance(data, bytes):
        raise TypeError("fingerprint input must be bytes")
    return {"sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data)}


def _reject(code: str, classification: str = "INVALID") -> VerificationResult:
    return VerificationResult(classification, False, False, failure_code=code)


def _fail(code: str) -> None:
    raise _Invalid(code)


def _exact_keys(value, keys, code="MALFORMED_MANIFEST") -> None:
    if not isinstance(value, dict) or set(value) != set(keys):
        _fail(code)


def _text(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _nonnegative(value) -> bool:
    return type(value) is int and value >= 0


def _digest(value) -> bool:
    return isinstance(value, str) and SHA256_RE.fullmatch(value) is not None


def _parse_constant(_value):
    _fail("MALFORMED_MANIFEST")


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _fail("DUPLICATE_JSON_KEY")
        result[key] = value
    return result


def _parse_json(data: bytes):
    if not isinstance(data, bytes):
        _fail("MALFORMED_MANIFEST")
    try:
        return json.loads(
            data.decode("utf-8", errors="strict"),
            object_pairs_hook=_unique_pairs,
            parse_constant=_parse_constant,
        )
    except _Invalid:
        raise
    except (UnicodeError, json.JSONDecodeError, TypeError, ValueError):
        _fail("MALFORMED_MANIFEST")


def _valid_run_id(value) -> bool:
    if not isinstance(value, str) or UUID4_RE.fullmatch(value) is None:
        return False
    try:
        return uuid.UUID(value).version == 4 and str(uuid.UUID(value)) == value
    except (ValueError, AttributeError):
        return False


def _valid_time(value) -> bool:
    if not isinstance(value, str) or TIMESTAMP_RE.fullmatch(value) is None:
        return False
    try:
        from datetime import datetime
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ) == value
    except ValueError:
        return False


def _validate_source(value, expected_role: str) -> None:
    _exact_keys(value, SOURCE_KEYS)
    if value["role"] != expected_role:
        _fail("SOURCE_ROLE_MISMATCH")
    if not _digest(value["sha256"]) or not _nonnegative(value["size_bytes"]):
        _fail("SOURCE_FINGERPRINT_INVALID")
    if not _nonnegative(value["record_count"]):
        _fail("SOURCE_RECORD_COUNT_INVALID")
    if value["encoding"] != "utf-8" or value["format"] != ("csv/jobs-v1" if expected_role == "jobs_csv" else "csv/details-v1"):
        _fail("SOURCE_FORMAT_INVALID")


def _expected_input_stage(stage: str) -> str:
    return "source" if stage == "job_details" else "job_details"


def _verify_input_binding(manifest: dict, upstream_manifest_bytes, upstream_artifacts,
                          upstream_chain=()):
    stage = manifest["stage"]
    if stage == "source":
        if manifest["input_generation"] is not None:
            _fail("UNEXPECTED_INPUT_GENERATION")
        return (), None

    ref = manifest["input_generation"]
    _exact_keys(ref, INPUT_KEYS, "INPUT_GENERATION_INVALID")
    expected_stage = _expected_input_stage(stage)
    if ref["stage"] != expected_stage or not _valid_run_id(ref["run_id"]):
        _fail("INPUT_GENERATION_MISMATCH")
    if not isinstance(ref["status"], str) or ref["status"] not in {"COMPLETE", "EMPTY"}:
        _fail("INPUT_GENERATION_NOT_SELECTABLE")
    if not _digest(ref["manifest_sha256"]) or not _nonnegative(ref["record_count"]):
        _fail("INPUT_GENERATION_INVALID")
    if not isinstance(upstream_manifest_bytes, bytes):
        _fail("MISSING_UPSTREAM_GENERATION")
    if not isinstance(upstream_artifacts, Mapping):
        _fail("MISSING_UPSTREAM_GENERATION")
    upstream = _parse_json(upstream_manifest_bytes)
    if not isinstance(upstream, dict):
        _fail("UPSTREAM_MANIFEST_INVALID")
    actual_manifest_hash = hashlib.sha256(upstream_manifest_bytes).hexdigest()
    if actual_manifest_hash != ref["manifest_sha256"]:
        _fail("INPUT_GENERATION_MISMATCH")
    if (
        upstream.get("run_id") != ref["run_id"]
        or upstream.get("stage") != ref["stage"]
        or upstream.get("status") != ref["status"]
    ):
        _fail("INPUT_GENERATION_MISMATCH")

    if stage == "job_details":
        parent_result = _manifest_result(
            upstream_manifest_bytes, upstream_artifacts, "source", None, None
        )
    else:
        if not isinstance(upstream_chain, (list, tuple)) or len(upstream_chain) != 1:
            _fail("MISSING_UPSTREAM_GENERATION")
        ancestor = upstream_chain[0]
        if not isinstance(ancestor, (list, tuple)) or len(ancestor) != 2:
            _fail("MISSING_UPSTREAM_GENERATION")
        parent_result = _manifest_result(
            upstream_manifest_bytes, upstream_artifacts, "job_details",
            ancestor[0], ancestor[1]
        )
    if not parent_result.accepted:
        _fail(parent_result.failure_code or "UPSTREAM_POLICY_UNRESOLVED")

    expected_role = "jobs_csv" if stage == "job_details" else "details_csv"
    upstream_outputs = upstream.get("outputs")
    if not isinstance(upstream_outputs, dict):
        _fail("UPSTREAM_MANIFEST_INVALID")
    if ref["status"] == "EMPTY" and stage == "job_analyzer":
        # An EMPTY details generation intentionally has no data artifact.
        if ref["artifact_role"] is not None or ref["artifact_sha256"] is not None:
            _fail("INPUT_GENERATION_MISMATCH")
        if ref["artifact_size_bytes"] is not None or ref["record_count"] != 0:
            _fail("INPUT_GENERATION_MISMATCH")
        if upstream_outputs:
            _fail("UPSTREAM_MANIFEST_INVALID")
        return ("D6", "D7"), None

    if ref["artifact_role"] != expected_role:
        _fail("INPUT_GENERATION_MISMATCH")

    descriptor = upstream_outputs.get(expected_role)
    if not isinstance(descriptor, dict):
        _fail("MISSING_UPSTREAM_ARTIFACT")
    if (
        descriptor.get("sha256") != ref["artifact_sha256"]
        or descriptor.get("size_bytes") != ref["artifact_size_bytes"]
        or descriptor.get("record_count") != ref["record_count"]
    ):
        _fail("INPUT_GENERATION_MISMATCH")
    data = upstream_artifacts.get(expected_role)
    if not isinstance(data, bytes):
        _fail("MISSING_UPSTREAM_ARTIFACT")
    actual = fingerprint(data)
    if actual["sha256"] != descriptor["sha256"] or actual["size_bytes"] != descriptor["size_bytes"]:
        _fail("UPSTREAM_ARTIFACT_MISMATCH")
    return (), data


def _parse_csv(data: bytes, encoding: str, expected_header, expected_format: str):
    if not isinstance(data, bytes):
        _fail("MALFORMED_ARTIFACT")
    if expected_header is None:
        parsed = _parse_json(data)
        if not isinstance(parsed, list):
            _fail("ARTIFACT_SCHEMA_INVALID")
        return parsed
    try:
        text = data.decode(encoding, errors="strict")
        reader = csv.reader(io.StringIO(text, newline=""), strict=True)
        rows = list(reader)
    except (UnicodeError, csv.Error, LookupError):
        _fail("ARTIFACT_SCHEMA_INVALID")
    if not rows or tuple(rows[0]) != tuple(expected_header):
        _fail("ARTIFACT_SCHEMA_INVALID")
    if any(len(row) != len(expected_header) for row in rows[1:]):
        _fail("ARTIFACT_SCHEMA_INVALID")
    return rows[1:]


def _validate_occurrences(manifest, source_sha: str, source_count: int, output_count: int):
    accounting = manifest["accounting"]
    _exact_keys(accounting, ACCOUNTING_KEYS, "ACCOUNTING_INVALID")
    if any(not _nonnegative(v) for v in accounting.values()):
        _fail("ACCOUNTING_INVALID")
    if accounting["source_occurrences"] != source_count:
        _fail("COUNT_MISMATCH")
    if source_count != (
        accounting["processed_occurrences"]
        + accounting["intentional_skip_occurrences"]
        + accounting["failed_occurrences"]
    ):
        _fail("COUNT_MISMATCH")
    if accounting["output_rows"] != output_count:
        _fail("OUTPUT_ROW_COUNT_MISMATCH")
    occurrences = manifest["occurrences"]
    if not isinstance(occurrences, list) or len(occurrences) != source_count:
        _fail("UNACCOUNTED_OCCURRENCE")
    seen_keys = set()
    seen_output_rows = set()
    dispositions = {key: 0 for key in DISPOSITIONS}
    dependencies = set()
    for expected_ordinal, item in enumerate(occurrences, 1):
        _exact_keys(item, OCCURRENCE_KEYS, "OCCURRENCE_INVALID")
        for field in (
            "occurrence_key", "disposition", "reason_code", "policy_rule_id",
            "retained_occurrence_key", "error_code", "quality_code",
        ):
            value = item[field]
            if value is not None and not isinstance(value, str):
                _fail("OCCURRENCE_INVALID")
        ordinal = item["ordinal"]
        if type(ordinal) is not int or ordinal != expected_ordinal:
            _fail("UNACCOUNTED_OCCURRENCE")
        key = f"{source_sha}:{ordinal}"
        if item["occurrence_key"] != key or key in seen_keys:
            _fail("UNACCOUNTED_OCCURRENCE")
        seen_keys.add(key)
        disposition = item["disposition"]
        if disposition not in DISPOSITIONS:
            _fail("OCCURRENCE_INVALID")
        dispositions[disposition] += 1
        if item["logical_identity"] is not None and not _text(item["logical_identity"]):
            _fail("OCCURRENCE_INVALID")
        if disposition == "PROCESSED":
            if item["reason_code"] is not None or item["policy_rule_id"] is not None or item["error_code"] is not None:
                _fail("OCCURRENCE_INVALID")
            if type(item["output_row"]) is not int or item["output_row"] < 1 or item["output_row"] > output_count:
                _fail("OCCURRENCE_OUTPUT_MISMATCH")
            if item["output_row"] in seen_output_rows:
                _fail("OCCURRENCE_OUTPUT_MISMATCH")
            seen_output_rows.add(item["output_row"])
            if item["quality_code"] == "DESCRIPTION_MISSING":
                dependencies.add("D5")
        elif disposition == "INTENTIONAL_SKIP":
            if not _text(item["reason_code"]) or not _text(item["policy_rule_id"]):
                _fail("UNAPPROVED_SKIP_RULE")
            if item["error_code"] is not None or item["output_row"] is not None:
                _fail("OCCURRENCE_INVALID")
            if item["retained_occurrence_key"] is not None and item["retained_occurrence_key"] not in seen_keys:
                _fail("DUPLICATE_OCCURRENCE_UNACCOUNTED")
            dependencies.update(("D3", "D4"))
        else:
            if (
                not isinstance(item["error_code"], str)
                or FAILURE_RE.fullmatch(item["error_code"]) is None
                or item["output_row"] is not None
            ):
                _fail("OCCURRENCE_INVALID")
    if seen_output_rows != set(range(1, output_count + 1)):
        _fail("OCCURRENCE_OUTPUT_MISMATCH")
    if dispositions["PROCESSED"] != accounting["processed_occurrences"]:
        _fail("COUNT_MISMATCH")
    if dispositions["INTENTIONAL_SKIP"] != accounting["intentional_skip_occurrences"]:
        _fail("COUNT_MISMATCH")
    if dispositions["FAILED"] != accounting["failed_occurrences"]:
        _fail("COUNT_MISMATCH")
    return dispositions, tuple(sorted(dependencies))


def _manifest_result(manifest_bytes, artifacts_by_role, expected_stage,
                     upstream_manifest_bytes, upstream_artifacts_by_role,
                     upstream_chain=()):
    manifest = _parse_json(manifest_bytes)
    _exact_keys(manifest, TOP_KEYS)
    if type(manifest["schema_version"]) is not int or manifest["schema_version"] != SCHEMA_VERSION:
        _fail("UNKNOWN_SCHEMA_VERSION")
    run_id, stage, status = manifest["run_id"], manifest["stage"], manifest["status"]
    if not _valid_run_id(run_id):
        _fail("INVALID_RUN_ID")
    if not isinstance(stage, str) or stage not in STAGES or (expected_stage is not None and stage != expected_stage):
        _fail("UNSUPPORTED_STAGE")
    if not isinstance(status, str) or status not in STATUSES:
        _fail("UNSUPPORTED_STATUS")
    if not isinstance(manifest["producer"], dict):
        _fail("MALFORMED_MANIFEST")
    _exact_keys(manifest["producer"], {"id", "version"})
    if not _text(manifest["producer"]["id"]) or not _text(manifest["producer"]["version"]):
        _fail("MALFORMED_MANIFEST")
    if not _valid_time(manifest["started_at"]):
        _fail("INVALID_TIMESTAMP")
    if not isinstance(artifacts_by_role, Mapping) or any(
        not isinstance(k, str) or not isinstance(v, bytes)
        for k, v in artifacts_by_role.items()
    ):
        _fail("MALFORMED_ARTIFACT_INPUT")
    if status == "IN_PROGRESS":
        if manifest["completed_at"] is not None:
            _fail("STATUS_CONTRADICTION")
        if (
            manifest["source"] is not None
            or manifest["accounting"] is not None
            or manifest["occurrences"] is not None
            or manifest["outputs"] != {}
            or manifest["failure"] is not None
        ):
            _fail("STATUS_CONTRADICTION")
        return VerificationResult(
            "INCOMPLETE", False, False, "IN_PROGRESS", run_id, stage, status,
            ("D6", "D7"), MappingProxyType({})
        )
    if not _valid_time(manifest["completed_at"]) or manifest["completed_at"] < manifest["started_at"]:
        _fail("INVALID_TIMESTAMP")
    if manifest["failure"] is not None:
        _exact_keys(manifest["failure"], {"code"}, "FAILURE_INVALID")
        if not isinstance(manifest["failure"]["code"], str) or FAILURE_RE.fullmatch(manifest["failure"]["code"]) is None:
            _fail("FAILURE_INVALID")
    if stage == "source":
        expected_source_role = "jobs_csv"
    elif stage == "job_details":
        expected_source_role = "jobs_csv"
    else:
        expected_source_role = "details_csv"

    if status == "FAILED":
        if manifest["failure"] is None or manifest["outputs"] != {}:
            _fail("STATUS_CONTRADICTION")
        if set(artifacts_by_role):
            _fail("UNEXPECTED_ARTIFACT_ROLE")
        return VerificationResult("FAILED", False, False, None, run_id, stage, status,
                                  ("D6", "D7"), MappingProxyType({}))
    if manifest["failure"] is not None:
        _fail("STATUS_CONTRADICTION")

    _validate_source(manifest["source"], expected_source_role)
    policy_dependencies, upstream_data = _verify_input_binding(
        manifest, upstream_manifest_bytes, upstream_artifacts_by_role,
        upstream_chain
    )
    source = manifest["source"]
    if stage != "source":
        if not isinstance(upstream_manifest_bytes, bytes):
            _fail("MISSING_UPSTREAM_GENERATION")
        upstream = _parse_json(upstream_manifest_bytes)
        upstream_output_role = "jobs_csv" if stage == "job_details" else "details_csv"
        upstream_desc = upstream.get("outputs", {}).get(upstream_output_role)
        empty_analyzer_input = (
            stage == "job_analyzer"
            and upstream.get("status") == "EMPTY"
            and manifest["status"] == "EMPTY"
        )
        if empty_analyzer_input:
            empty_hash = hashlib.sha256(b"").hexdigest()
            if source["record_count"] != 0 or source["size_bytes"] != 0 or source["sha256"] != empty_hash:
                _fail("SOURCE_FINGERPRINT_MISMATCH")
        else:
            if not isinstance(upstream_desc, dict):
                _fail("MISSING_UPSTREAM_ARTIFACT")
            if (
                source["sha256"] != upstream_desc.get("sha256")
                or source["size_bytes"] != upstream_desc.get("size_bytes")
                or source["record_count"] != upstream_desc.get("record_count")
                or source["format"] != upstream_desc.get("format")
            ):
                _fail("SOURCE_FINGERPRINT_MISMATCH")
            if upstream_data is not None and upstream_data != (upstream_artifacts_by_role or {}).get(upstream_output_role):
                _fail("SOURCE_FINGERPRINT_MISMATCH")

    outputs = manifest["outputs"]
    if not isinstance(outputs, dict):
        _fail("MALFORMED_MANIFEST")
    source_rows = None
    if stage == "source":
        expected_roles = {"jobs_csv"}
    elif status == "EMPTY":
        expected_roles = set()
    elif stage == "job_details":
        expected_roles = {"details_csv", "diagnostics_json"}
    else:
        expected_roles = {"analysis_csv"}
    if set(outputs) != expected_roles or set(artifacts_by_role) != expected_roles:
        _fail("MISSING_ARTIFACT" if expected_roles - set(outputs) or expected_roles - set(artifacts_by_role) else "UNEXPECTED_ARTIFACT_ROLE")

    parsed_outputs = {}
    seen_paths = set()
    for role, descriptor in outputs.items():
        _exact_keys(descriptor, ARTIFACT_KEYS, "ARTIFACT_DESCRIPTOR_INVALID")
        expected = EXPECTED_ARTIFACTS[stage].get(role)
        if expected is None or descriptor["relative_path"] != expected[1] or descriptor["format"] != expected[2]:
            _fail("UNEXPECTED_ARTIFACT_ROLE")
        if descriptor["relative_path"] in seen_paths:
            _fail("DUPLICATE_ARTIFACT")
        seen_paths.add(descriptor["relative_path"])
        if not _digest(descriptor["sha256"]) or not _nonnegative(descriptor["size_bytes"]) or not _nonnegative(descriptor["record_count"]):
            _fail("ARTIFACT_DESCRIPTOR_INVALID")
        data = artifacts_by_role[role]
        actual = fingerprint(data)
        if actual["size_bytes"] != descriptor["size_bytes"]:
            _fail("ARTIFACT_SIZE_MISMATCH")
        if actual["sha256"] != descriptor["sha256"]:
            _fail("ARTIFACT_HASH_MISMATCH")
        expected_header = expected[3]
        parsed = _parse_csv(data, source["encoding"], expected_header, expected[2])
        if expected_header is None and not isinstance(parsed, (list, dict)):
            _fail("ARTIFACT_SCHEMA_INVALID")
        if expected_header is not None and len(parsed) != descriptor["record_count"]:
            _fail("ARTIFACT_ROW_COUNT_MISMATCH")
        if expected_header is None and descriptor["record_count"] != len(parsed):
            _fail("ARTIFACT_ROW_COUNT_MISMATCH")
        parsed_outputs[role] = parsed
    if stage == "source":
        source_rows = parsed_outputs["jobs_csv"]
        if len(source_rows) != source["record_count"]:
            _fail("SOURCE_RECORD_COUNT_MISMATCH")
        if source["sha256"] != outputs["jobs_csv"]["sha256"] or source["size_bytes"] != outputs["jobs_csv"]["size_bytes"]:
            _fail("SOURCE_FINGERPRINT_MISMATCH")
        if status not in {"COMPLETE", "EMPTY"}:
            _fail("STATUS_CONTRADICTION")
        expected_status = "EMPTY" if len(source_rows) == 0 else "COMPLETE"
        if status != expected_status:
            _fail("STATUS_CONTRADICTION")
        if manifest["accounting"] is not None or manifest["occurrences"] is not None:
            _fail("ACCOUNTING_INVALID")
        return VerificationResult(
            "EMPTY_DATA_ONLY" if status == "EMPTY" else "VERIFIED_DATA_ONLY",
            True, False, None, run_id, stage, status,
            ("D1", "D2", "D6", "D7", "D13"), MappingProxyType(dict(artifacts_by_role))
        )

    if status == "EMPTY":
        accounting = manifest["accounting"]
        if not isinstance(accounting, dict):
            _fail("ACCOUNTING_INVALID")
        _exact_keys(accounting, ACCOUNTING_KEYS, "ACCOUNTING_INVALID")
        if any(not _nonnegative(value) for value in accounting.values()):
            _fail("ACCOUNTING_INVALID")
        if source["record_count"] != 0 or any(accounting.values()) or manifest["occurrences"] != []:
            _fail("STATUS_CONTRADICTION")
        if stage == "job_analyzer" and manifest["input_generation"]["status"] != "EMPTY":
            _fail("STATUS_CONTRADICTION")
        return VerificationResult(
            "EMPTY_DATA_ONLY", True, False, None, run_id, stage, status,
            tuple(sorted(set(policy_dependencies) | {"D1", "D2", "D6", "D7", "D13"})),
            MappingProxyType({})
        )

    accounting = manifest["accounting"]
    if not isinstance(accounting, dict):
        _fail("ACCOUNTING_INVALID")
    output_role = "details_csv" if stage == "job_details" else "analysis_csv"
    output_rows = outputs[output_role]["record_count"]
    dispositions, occurrence_dependencies = _validate_occurrences(
        manifest, source["sha256"], source["record_count"], output_rows
    )
    policy_dependencies = tuple(sorted(set(policy_dependencies) | set(occurrence_dependencies)))
    processed = dispositions["PROCESSED"]
    skipped = dispositions["INTENTIONAL_SKIP"]
    failed = dispositions["FAILED"]
    if status == "COMPLETE":
        if source["record_count"] == 0 or failed:
            _fail("STATUS_CONTRADICTION")
        if processed == 0 and skipped:
            policy_dependencies = tuple(sorted(set(policy_dependencies) | {"D6"}))
        if skipped:
            policy_dependencies = tuple(sorted(set(policy_dependencies) | {"D3", "D6"}))
    elif status == "PARTIAL":
        if source["record_count"] == 0 or processed == 0 or failed == 0:
            _fail("STATUS_CONTRADICTION")
        policy_dependencies = tuple(sorted(set(policy_dependencies) | {"D6", "D7"}))
    else:
        _fail("STATUS_CONTRADICTION")

    # A blank extracted description is a quality fact, but its product meaning
    # remains unresolved. Do not convert it to an approved success/failure rule.
    if stage == "job_details":
        rows = parsed_outputs["details_csv"]
        for occurrence in manifest["occurrences"]:
            if occurrence["disposition"] == "PROCESSED":
                row = rows[occurrence["output_row"] - 1]
                if not row[7].strip():
                    if occurrence["quality_code"] != "DESCRIPTION_MISSING":
                        _fail("BLANK_QUALITY_UNCLASSIFIED")
                    policy_dependencies = tuple(sorted(set(policy_dependencies) | {"D5"}))

    if policy_dependencies:
        return VerificationResult(
            "UNSUPPORTED_POLICY", False, False, "POLICY_UNRESOLVED",
            run_id, stage, status, policy_dependencies, MappingProxyType({})
        )
    if status == "PARTIAL":
        return VerificationResult(
            "PARTIAL_DATA_ONLY", True, False, None,
            run_id, stage, status, ("D6", "D7"), MappingProxyType(dict(artifacts_by_role))
        )
    return VerificationResult(
        "VERIFIED_DATA_ONLY", True, False, None,
        run_id, stage, status, ("D1", "D2", "D6", "D7", "D13"),
        MappingProxyType(dict(artifacts_by_role))
    )


def verify_generation(
    manifest_bytes: bytes,
    artifacts_by_role: Mapping[str, bytes],
    *,
    expected_stage: Optional[str] = None,
    upstream_manifest_bytes: Optional[bytes] = None,
    upstream_artifacts_by_role: Optional[Mapping[str, bytes]] = None,
    upstream_chain=(),
) -> VerificationResult:
    """Validate supplied bytes only. No paths are opened and eligible is always false."""
    if manifest_bytes is None:
        return _reject("MISSING_MANIFEST")
    try:
        return _manifest_result(
            manifest_bytes, artifacts_by_role, expected_stage,
            upstream_manifest_bytes, upstream_artifacts_by_role,
            upstream_chain
        )
    except _Invalid as exc:
        classification = "INCOMPLETE" if exc.code in {
            "IN_PROGRESS", "MISSING_UPSTREAM_GENERATION", "MISSING_UPSTREAM_ARTIFACT"
        } else "INVALID"
        return _reject(exc.code, classification)
    except (KeyError, TypeError, AttributeError, IndexError):
        return _reject("MALFORMED_MANIFEST")
    except Exception:
        return _reject("INTERNAL_VALIDATION_ERROR")


def verify_rollback_request(rollback_event: Optional[dict], authorization_verifier=None) -> VerificationResult:
    """Rollback is unsupported until an approved authorization verifier exists."""
    if not isinstance(rollback_event, dict):
        return _reject("ROLLBACK_UNAUTHORIZED")
    required = {"authorized_by", "authorization_ref", "at", "reason", "source_sha256"}
    if set(rollback_event) != required:
        return _reject("ROLLBACK_UNAUTHORIZED")
    if authorization_verifier is None:
        return VerificationResult(
            "UNSUPPORTED_POLICY", False, False, "ROLLBACK_AUTHORITY_UNVERIFIABLE",
            policy_dependencies=("D10", "D13")
        )
    # No caller-supplied callback is trusted in this prototype.
    return VerificationResult(
        "UNSUPPORTED_POLICY", False, False, "ROLLBACK_AUTHORITY_UNVERIFIABLE",
        policy_dependencies=("D10", "D13")
    )


def verify_selection(latest: VerificationResult, previous=None, *, explicit_policy=None) -> VerificationResult:
    """Never implicitly falls back to an older generation."""
    if not isinstance(latest, VerificationResult):
        return _reject("SELECTION_INPUT_INVALID")
    if latest.status in {"FAILED", "IN_PROGRESS", "PARTIAL"}:
        if previous is not None and explicit_policy is None:
            return _reject("IMPLICIT_OLD_GENERATION_FALLBACK")
        return VerificationResult(
            "UNSUPPORTED_POLICY", False, False, "SELECTION_POLICY_UNRESOLVED",
            latest.run_id, latest.stage, latest.status, ("D8",)
        )
    if not latest.accepted or latest.status == "EMPTY":
        return VerificationResult(
            "EMPTY_DATA_ONLY" if latest.status == "EMPTY" else "INVALID",
            latest.accepted, False, latest.failure_code, latest.run_id,
            latest.stage, latest.status, latest.policy_dependencies
        )
    return VerificationResult(
        latest.classification, latest.accepted, False, latest.failure_code,
        latest.run_id, latest.stage, latest.status,
        tuple(sorted(set(latest.policy_dependencies) | {"D8", "D13"})),
        latest.artifact_bytes
    )


