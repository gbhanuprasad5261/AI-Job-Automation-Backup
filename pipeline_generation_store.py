"""Standalone validation primitives for isolated pipeline generations.

This module is deliberately not wired into production pipeline code. Its path
handling is for application-level generation consistency only; it does not
establish trusted-root containment or defend against hostile reparse points,
path replacement, or concurrent writers.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime
from pathlib import Path, PurePosixPath


MANIFEST_SCHEMA_VERSION = 1
POINTER_SCHEMA_VERSION = 1
STAGES = frozenset({"job_details", "job_analyzer"})
STATUSES = frozenset({"IN_PROGRESS", "COMPLETE", "EMPTY", "PARTIAL", "FAILED"})
SELECTION_MODES = frozenset({"NONE", "CURRENT", "EMPTY", "EXPLICIT_ROLLBACK"})

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_RUN_ID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
_FAILURE_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

_MANIFEST_KEYS = {
    "schema_version",
    "run_id",
    "stage",
    "status",
    "started_at",
    "completed_at",
    "source",
    "input_generation",
    "accounting",
    "outputs",
    "failure",
}
_POINTER_KEYS = {
    "schema_version",
    "stage",
    "latest_attempt",
    "selected_generation_id",
    "previous_complete_generation_id",
    "selection_mode",
    "recovery_event",
}
_ACCOUNTING_KEYS = {
    "source_records",
    "processed_records",
    "intentionally_skipped_records",
    "failed_records",
}
_EXPECTED_OUTPUTS = {
    "job_details": frozenset({"details_csv", "diagnostics_json"}),
    "job_analyzer": frozenset({"analysis_csv"}),
}
_EXPECTED_OUTPUT_PATHS = {
    "details_csv": "job_details.csv",
    "diagnostics_json": "job_details_diagnostics.json",
    "analysis_csv": "job_analysis.csv",
}


class GenerationValidationError(ValueError):
    """Raised when a generation manifest, pointer, or artifact is invalid."""


def _require_exact_keys(value, expected, label):
    if not isinstance(value, dict):
        raise GenerationValidationError(f"{label} must be an object")
    actual = set(value)
    missing = expected - actual
    extra = actual - expected
    if missing or extra:
        raise GenerationValidationError(
            f"{label} keys mismatch (missing={sorted(missing)}, extra={sorted(extra)})"
        )


def _require_text(value, label):
    if not isinstance(value, str) or not value.strip():
        raise GenerationValidationError(f"{label} must be non-empty text")


def _require_nonnegative_int(value, label):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise GenerationValidationError(f"{label} must be a non-negative integer")


def _validate_timestamp(value, label):
    if not isinstance(value, str):
        raise GenerationValidationError(f"{label} must be a UTC timestamp")
    try:
        parsed = datetime.strptime(value, _TIMESTAMP_FORMAT)
    except ValueError as exc:
        raise GenerationValidationError(
            f"{label} must use YYYY-MM-DDTHH:MM:SSZ"
        ) from exc
    if parsed.strftime(_TIMESTAMP_FORMAT) != value:
        raise GenerationValidationError(f"{label} is not canonical")
    return parsed


def validate_run_id(run_id):
    """Validate and return a canonical lowercase UUIDv4 string."""
    if not isinstance(run_id, str) or not _RUN_ID_RE.fullmatch(run_id):
        raise GenerationValidationError("run_id must be a canonical lowercase UUIDv4")
    try:
        parsed = uuid.UUID(run_id)
    except (ValueError, AttributeError) as exc:
        raise GenerationValidationError("run_id is not a valid UUID") from exc
    if parsed.version != 4 or str(parsed) != run_id:
        raise GenerationValidationError("run_id must be a canonical lowercase UUIDv4")
    return run_id


def new_run_id():
    """Return a canonical UUIDv4 generation identifier."""
    return str(uuid.uuid4())


def create_generation(root, stage, run_id=None):
    """Create a unique generation directory below an existing caller root.

    The root must be explicitly supplied and already exist. This is a simple
    storage primitive, not a trusted-root or race-safe containment boundary.
    """
    if root is None:
        raise GenerationValidationError("an explicit generation root is required")
    if not isinstance(stage, str) or stage not in STAGES:
        raise GenerationValidationError("unsupported stage")
    run_id = new_run_id() if run_id is None else validate_run_id(run_id)
    root_path = Path(root)
    if not root_path.is_dir():
        raise GenerationValidationError("generation root must already be a directory")
    stage_path = root_path / stage
    stage_path.mkdir(exist_ok=True)
    generation_path = stage_path / run_id
    # exist_ok=False ensures a collision never reuses or overwrites a generation.
    generation_path.mkdir(exist_ok=False)
    return generation_path


def fingerprint_bytes(data):
    """Fingerprint the exact supplied bytes; callers should parse these bytes."""
    if not isinstance(data, bytes):
        raise TypeError("data must be bytes")
    return {"sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data)}


def _validate_digest(value, label):
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise GenerationValidationError(f"{label} must be lowercase SHA-256 hex")


def _validate_fingerprint(value, label, *, include_record_count=False):
    expected = {"sha256", "size_bytes"}
    if include_record_count:
        expected.add("record_count")
    _require_exact_keys(value, expected, label)
    _validate_digest(value["sha256"], f"{label}.sha256")
    _require_nonnegative_int(value["size_bytes"], f"{label}.size_bytes")
    if include_record_count:
        _require_nonnegative_int(value["record_count"], f"{label}.record_count")


def _validate_relative_artifact_path(value):
    _require_text(value, "artifact relative_path")
    if "\\" in value or ":" in value or "\x00" in value:
        raise GenerationValidationError("artifact path must use safe relative POSIX syntax")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise GenerationValidationError("artifact path contains an unsafe component")
    path = PurePosixPath(value)
    if path.is_absolute() or path.as_posix() != value:
        raise GenerationValidationError("artifact path must be normalized and relative")
    return parts


def _validate_input_generation(value, *, required=False):
    if value is None:
        if required:
            raise GenerationValidationError("input_generation is required for this state")
        return
    expected = {
        "stage",
        "run_id",
        "status",
        "manifest_sha256",
        "artifact_role",
        "artifact_sha256",
        "artifact_size_bytes",
    }
    _require_exact_keys(value, expected, "input_generation")
    if value["stage"] != "job_details":
        raise GenerationValidationError("input_generation.stage must be job_details")
    validate_run_id(value["run_id"])
    if not isinstance(value["status"], str) or value["status"] not in {"COMPLETE", "EMPTY"}:
        raise GenerationValidationError("analyzer input generation must be COMPLETE or EMPTY")
    _validate_digest(value["manifest_sha256"], "input_generation.manifest_sha256")
    if value["status"] == "COMPLETE":
        if value["artifact_role"] != "details_csv":
            raise GenerationValidationError("COMPLETE details input requires details_csv")
        _validate_digest(value["artifact_sha256"], "input_generation.artifact_sha256")
        _require_nonnegative_int(value["artifact_size_bytes"], "input_generation.artifact_size_bytes")
    elif value["artifact_role"] is not None or value["artifact_sha256"] is not None:
        raise GenerationValidationError("EMPTY details input cannot reference a data artifact")
    elif value.get("artifact_size_bytes") is not None:
        raise GenerationValidationError("EMPTY details input cannot reference an artifact size")


def validate_manifest(manifest, *, generation_dir=None, read_artifacts=False):
    """Validate a manifest and optionally verify every listed artifact.

    When ``read_artifacts`` is true, bytes are read once and checked against the
    manifest. This does not protect against symlink/reparse traversal or prove
    trusted-root containment. Use the returned byte map as the parser input.
    """
    _require_exact_keys(manifest, _MANIFEST_KEYS, "manifest")
    if type(manifest["schema_version"]) is not int or manifest["schema_version"] != MANIFEST_SCHEMA_VERSION:
        raise GenerationValidationError("unknown manifest schema version")
    validate_run_id(manifest["run_id"])
    stage = manifest["stage"]
    status = manifest["status"]
    if not isinstance(stage, str) or stage not in STAGES:
        raise GenerationValidationError("unsupported manifest stage")
    if not isinstance(status, str) or status not in STATUSES:
        raise GenerationValidationError("unsupported manifest status")

    started = _validate_timestamp(manifest["started_at"], "started_at")
    completed_value = manifest["completed_at"]
    if status == "IN_PROGRESS":
        if completed_value is not None:
            raise GenerationValidationError("IN_PROGRESS requires completed_at=null")
        if manifest["source"] is not None or manifest["accounting"] is not None:
            raise GenerationValidationError("IN_PROGRESS source/accounting must be null")
        if manifest["outputs"] != {} or manifest["failure"] is not None:
            raise GenerationValidationError("IN_PROGRESS cannot publish outputs or failure")
        if stage == "job_details" and manifest["input_generation"] is not None:
            raise GenerationValidationError("job_details cannot have input_generation")
        if stage == "job_analyzer":
            _validate_input_generation(manifest["input_generation"])
        return {}

    completed = _validate_timestamp(completed_value, "completed_at")
    if completed < started:
        raise GenerationValidationError("completed_at precedes started_at")
    if manifest["failure"] is not None:
        if status != "FAILED":
            raise GenerationValidationError("failure details are only valid for FAILED")
    elif status == "FAILED":
        raise GenerationValidationError("FAILED requires a failure code")

    failure = manifest["failure"]
    if status == "FAILED":
        _require_exact_keys(failure, {"code"}, "failure")
        if not isinstance(failure["code"], str) or not _FAILURE_CODE_RE.fullmatch(failure["code"]):
            raise GenerationValidationError("failure.code must be a stable uppercase code")
        if manifest["outputs"] != {}:
            raise GenerationValidationError("FAILED outputs must be empty and unselectable")
        if manifest["accounting"] is not None:
            self_accounting = manifest["accounting"]
            _validate_accounting(self_accounting)
        if manifest["source"] is not None:
            _validate_source(manifest["source"], stage=stage)
        if manifest["source"] is not None and manifest["accounting"] is not None:
            if manifest["source"]["record_count"] != self_accounting["source_records"]:
                raise GenerationValidationError("failed source and accounting record counts disagree")
        if stage == "job_details" and manifest["input_generation"] is not None:
            raise GenerationValidationError("job_details cannot have input_generation")
        if stage == "job_analyzer":
            _validate_input_generation(manifest["input_generation"])
        return {}

    if manifest["failure"] is not None:
        raise GenerationValidationError("non-failed status cannot contain failure details")
    _validate_source(manifest["source"], stage=stage)
    accounting = _validate_accounting(manifest["accounting"])
    if accounting["source_records"] != manifest["source"]["record_count"]:
        raise GenerationValidationError("source and accounting record counts disagree")
    if stage == "job_details":
        if manifest["input_generation"] is not None:
            raise GenerationValidationError("job_details cannot have input_generation")
    else:
        _validate_input_generation(manifest["input_generation"], required=True)
        input_generation = manifest["input_generation"]
        if input_generation["status"] == "COMPLETE":
            if (
                manifest["source"]["sha256"] != input_generation["artifact_sha256"]
                or manifest["source"]["size_bytes"] != input_generation["artifact_size_bytes"]
            ):
                raise GenerationValidationError("analyzer source does not match its input-generation artifact")

    outputs = manifest["outputs"]
    if not isinstance(outputs, dict):
        raise GenerationValidationError("outputs must be an object")
    if status == "EMPTY":
        if manifest["source"]["record_count"] != 0 or any(accounting.values()):
            raise GenerationValidationError("EMPTY requires zero source and accounting records")
        if outputs:
            raise GenerationValidationError("EMPTY cannot select data outputs")
        if stage == "job_analyzer" and manifest["input_generation"]["status"] != "EMPTY":
            raise GenerationValidationError("analyzer EMPTY requires an EMPTY details generation")
        return {}

    if status == "COMPLETE":
        if manifest["source"]["record_count"] == 0 or accounting["failed_records"] != 0:
            raise GenerationValidationError("COMPLETE requires nonempty input and zero failed records")
        if stage == "job_analyzer" and manifest["input_generation"]["status"] != "COMPLETE":
            raise GenerationValidationError("analyzer COMPLETE requires a COMPLETE details generation")
    elif status == "PARTIAL":
        if (
            manifest["source"]["record_count"] == 0
            or accounting["failed_records"] == 0
            or accounting["processed_records"] == 0
        ):
            raise GenerationValidationError("PARTIAL requires failures and useful processed records")
        if stage == "job_analyzer" and manifest["input_generation"]["status"] != "COMPLETE":
            raise GenerationValidationError("analyzer PARTIAL requires a COMPLETE details generation")

    _validate_outputs(outputs, stage)
    if read_artifacts:
        if generation_dir is None:
            raise GenerationValidationError("generation_dir is required to read artifacts")
        return read_verified_artifacts(manifest, generation_dir)
    return {}


def validate_analyzer_input_binding(
    analyzer_manifest,
    details_manifest,
    *,
    details_manifest_bytes,
    details_artifact_bytes=None,
):
    """Verify an analyzer reference against the exact details bytes supplied.

    Callers must obtain both byte strings through their approved storage
    boundary. This function checks schema and content identity only; it does
    not safely open paths or establish filesystem containment.
    """
    validate_manifest(analyzer_manifest)
    validate_manifest(details_manifest)
    if analyzer_manifest["stage"] != "job_analyzer":
        raise GenerationValidationError("analyzer manifest has the wrong stage")
    if details_manifest["stage"] != "job_details":
        raise GenerationValidationError("input manifest has the wrong stage")
    reference = analyzer_manifest["input_generation"]
    if reference is None:
        raise GenerationValidationError("analyzer manifest has no input-generation reference")
    if details_manifest["status"] not in {"COMPLETE", "EMPTY"}:
        raise GenerationValidationError("details input generation is not selectable")
    if reference["run_id"] != details_manifest["run_id"] or reference["status"] != details_manifest["status"]:
        raise GenerationValidationError("analyzer references a different details generation")
    if not isinstance(details_manifest_bytes, bytes):
        raise TypeError("details_manifest_bytes must be bytes")
    parsed_details = parse_manifest(details_manifest_bytes)
    if parsed_details != details_manifest:
        raise GenerationValidationError("details manifest bytes do not match the supplied manifest")
    if fingerprint_bytes(details_manifest_bytes)["sha256"] != reference["manifest_sha256"]:
        raise GenerationValidationError("details manifest hash does not match analyzer reference")

    if details_manifest["status"] == "COMPLETE":
        artifact = details_manifest["outputs"]["details_csv"]
        if (
            reference["artifact_role"] != "details_csv"
            or reference["artifact_sha256"] != artifact["sha256"]
            or reference["artifact_size_bytes"] != artifact["size_bytes"]
        ):
            raise GenerationValidationError("analyzer artifact reference disagrees with details manifest")
        if not isinstance(details_artifact_bytes, bytes):
            raise GenerationValidationError("complete details generation requires its exact artifact bytes")
        actual = fingerprint_bytes(details_artifact_bytes)
        if actual["sha256"] != artifact["sha256"] or actual["size_bytes"] != artifact["size_bytes"]:
            raise GenerationValidationError("details artifact bytes do not match details manifest")
    elif details_artifact_bytes is not None:
        raise GenerationValidationError("empty details generation cannot supply a details artifact")
    return True


def _validate_source(source, *, stage):
    _require_exact_keys(
        source,
        {"role", "sha256", "size_bytes", "record_count"},
        "source",
    )
    _require_text(source["role"], "source.role")
    expected_role = "jobs.csv" if stage == "job_details" else "details_csv"
    if source["role"] != expected_role:
        raise GenerationValidationError(f"{stage} source.role must be {expected_role}")
    _validate_digest(source["sha256"], "source.sha256")
    _require_nonnegative_int(source["size_bytes"], "source.size_bytes")
    _require_nonnegative_int(source["record_count"], "source.record_count")


def _validate_accounting(accounting):
    _require_exact_keys(accounting, _ACCOUNTING_KEYS, "accounting")
    for key, value in accounting.items():
        _require_nonnegative_int(value, f"accounting.{key}")
    if accounting["source_records"] != (
        accounting["processed_records"]
        + accounting["intentionally_skipped_records"]
        + accounting["failed_records"]
    ):
        raise GenerationValidationError("accounting counts do not reconcile")
    return accounting


def _validate_outputs(outputs, stage):
    if not isinstance(outputs, dict):
        raise GenerationValidationError("outputs must be an object")
    if set(outputs) != _EXPECTED_OUTPUTS[stage]:
        raise GenerationValidationError("outputs do not match the required stage artifact set")
    seen_paths = set()
    for role, artifact in outputs.items():
        _require_exact_keys(artifact, {"relative_path", "sha256", "size_bytes"}, f"outputs.{role}")
        parts = _validate_relative_artifact_path(artifact["relative_path"])
        path_key = tuple(parts)
        if path_key in seen_paths:
            raise GenerationValidationError("multiple outputs reference the same path")
        seen_paths.add(path_key)
        if artifact["relative_path"] != _EXPECTED_OUTPUT_PATHS[role]:
            raise GenerationValidationError(f"outputs.{role} has an unexpected artifact path")
        _validate_digest(artifact["sha256"], f"outputs.{role}.sha256")
        _require_nonnegative_int(artifact["size_bytes"], f"outputs.{role}.size_bytes")


def read_verified_artifacts(manifest, generation_dir):
    """Read and fingerprint the exact bytes consumers should parse."""
    validate_manifest(manifest)
    stage = manifest.get("stage")
    if manifest.get("status") not in {"COMPLETE", "PARTIAL"}:
        raise GenerationValidationError("this generation status has no readable outputs")
    _validate_outputs(manifest.get("outputs"), stage)
    root = Path(generation_dir)
    if root.name != manifest["run_id"] or root.parent.name != stage:
        raise GenerationValidationError("generation directory path does not match manifest stage and run_id")
    verified = {}
    for role, artifact in manifest["outputs"].items():
        parts = _validate_relative_artifact_path(artifact["relative_path"])
        data = (root.joinpath(*parts)).read_bytes()
        actual = fingerprint_bytes(data)
        if actual["size_bytes"] != artifact["size_bytes"]:
            raise GenerationValidationError(f"artifact size mismatch: {role}")
        if actual["sha256"] != artifact["sha256"]:
            raise GenerationValidationError(f"artifact hash mismatch: {role}")
        verified[role] = data
    return verified


def serialize_manifest(manifest):
    """Validate and serialize a manifest as deterministic UTF-8 JSON bytes."""
    validate_manifest(manifest)
    try:
        text = json.dumps(
            manifest,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise GenerationValidationError("manifest cannot be serialized as strict JSON") from exc
    return text.encode("utf-8")


def _reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise GenerationValidationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def parse_manifest(data, *, generation_dir=None, read_artifacts=False):
    """Parse strict UTF-8 JSON and validate it; duplicate keys are rejected."""
    if not isinstance(data, bytes):
        raise TypeError("manifest data must be bytes")
    try:
        manifest = json.loads(data.decode("utf-8", errors="strict"), object_pairs_hook=_reject_duplicate_keys)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise GenerationValidationError("manifest is not valid UTF-8 JSON") from exc
    validate_manifest(manifest, generation_dir=generation_dir, read_artifacts=read_artifacts)
    return manifest


def validate_pointer(
    pointer,
    *,
    manifest=None,
    latest_attempt_manifest=None,
    current_source_sha256=None,
):
    """Validate pointer shape and, when supplied, its referenced manifest.

    For normal selection, ``manifest`` is the latest-attempt manifest. For
    explicit rollback, ``manifest`` is the selected prior COMPLETE manifest
    and ``latest_attempt_manifest`` is the failed/partial attempt manifest.
    This validates data consistency only. It does not publish pointers or
    establish filesystem atomicity, trusted-root containment, or durability.
    """
    _require_exact_keys(pointer, _POINTER_KEYS, "pointer")
    if type(pointer["schema_version"]) is not int or pointer["schema_version"] != POINTER_SCHEMA_VERSION:
        raise GenerationValidationError("unknown pointer schema version")
    stage = pointer["stage"]
    if not isinstance(stage, str) or stage not in STAGES:
        raise GenerationValidationError("unsupported pointer stage")
    latest = pointer["latest_attempt"]
    _require_exact_keys(latest, {"run_id", "status"}, "latest_attempt")
    validate_run_id(latest["run_id"])
    if not isinstance(latest["status"], str) or latest["status"] not in STATUSES:
        raise GenerationValidationError("unsupported latest attempt status")

    selected = pointer["selected_generation_id"]
    previous = pointer["previous_complete_generation_id"]
    if selected is not None:
        validate_run_id(selected)
    if previous is not None:
        validate_run_id(previous)
    mode = pointer["selection_mode"]
    if not isinstance(mode, str) or mode not in SELECTION_MODES:
        raise GenerationValidationError("unsupported selection_mode")
    if mode != "EXPLICIT_ROLLBACK" and latest_attempt_manifest is not None:
        raise GenerationValidationError("latest_attempt_manifest is only valid for rollback")
    if previous == latest["run_id"]:
        raise GenerationValidationError("previous complete generation cannot be the latest attempt")

    if mode == "NONE":
        if selected is not None or latest["status"] not in {"IN_PROGRESS", "PARTIAL", "FAILED"}:
            raise GenerationValidationError("NONE selection requires no selected generation and a nonselectable status")
        if pointer["recovery_event"] is not None:
            raise GenerationValidationError("NONE selection cannot contain a recovery event")
    elif mode == "CURRENT":
        if latest["status"] != "COMPLETE" or selected != latest["run_id"]:
            raise GenerationValidationError("CURRENT must select the latest COMPLETE run")
        if pointer["recovery_event"] is not None:
            raise GenerationValidationError("CURRENT selection cannot contain a recovery event")
    elif mode == "EMPTY":
        if latest["status"] != "EMPTY" or selected != latest["run_id"]:
            raise GenerationValidationError("EMPTY must select the latest EMPTY run")
        if pointer["recovery_event"] is not None:
            raise GenerationValidationError("EMPTY selection cannot contain a recovery event")
    else:
        event = pointer["recovery_event"]
        _require_exact_keys(
            event,
            {"authorized_by", "authorization_ref", "at", "reason", "source_sha256"},
            "recovery_event",
        )
        if latest["status"] not in {"PARTIAL", "FAILED"}:
            raise GenerationValidationError("rollback requires a failed or partial latest attempt")
        if selected is None or selected != previous:
            raise GenerationValidationError("rollback must select the recorded previous generation")
        if selected == latest["run_id"]:
            raise GenerationValidationError("rollback cannot select the latest failed or partial attempt")
        for field in ("authorized_by", "authorization_ref", "reason"):
            _require_text(event[field], f"recovery_event.{field}")
        _validate_timestamp(event["at"], "recovery_event.at")
        _validate_digest(event["source_sha256"], "recovery_event.source_sha256")
        _validate_digest(current_source_sha256, "current_source_sha256")
        if current_source_sha256 != event["source_sha256"]:
            raise GenerationValidationError("rollback source fingerprint does not match current source")
        if manifest is None:
            raise GenerationValidationError("rollback requires the selected generation manifest")
        validate_manifest(manifest)
        if (
            manifest["stage"] != stage
            or manifest["status"] != "COMPLETE"
            or manifest["run_id"] != selected
            or manifest["source"]["sha256"] != current_source_sha256
        ):
            raise GenerationValidationError("rollback generation is not a matching COMPLETE generation")
        if latest_attempt_manifest is None:
            raise GenerationValidationError("rollback requires the latest-attempt manifest")
        validate_manifest(latest_attempt_manifest)
        if (
            latest_attempt_manifest["stage"] != stage
            or latest_attempt_manifest["run_id"] != latest["run_id"]
            or latest_attempt_manifest["status"] != latest["status"]
        ):
            raise GenerationValidationError("pointer and latest-attempt manifest disagree")

    if manifest is not None and mode != "EXPLICIT_ROLLBACK":
        validate_manifest(manifest)
        if manifest["stage"] != stage or manifest["run_id"] != latest["run_id"] or manifest["status"] != latest["status"]:
            raise GenerationValidationError("pointer and latest manifest disagree")
        if mode in {"CURRENT", "EMPTY"} and selected != manifest["run_id"]:
            raise GenerationValidationError("selected generation and manifest disagree")
    return pointer
