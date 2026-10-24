"""Fail-closed boundary between distinct manifest validator contracts.

The current schema-v2 proposal and the two v1 validators are not converted
into one another. This module checks an explicitly named input version, rejects
cross-version submissions, and dispatches only native-contract inputs to the
existing public validators. A successful validation is never authorization.
"""
from __future__ import annotations

import json
from typing import Any, Mapping

from tools import offline_provenance_verifier as verifier
from tools import provenance_manifest_schema as schema
import pipeline_generation_store as generation_store


TARGETS = frozenset({"schema_v2", "offline_verifier_v1", "generation_store_v1"})
TARGET_VERSIONS = {"schema_v2": 2, "offline_verifier_v1": 1, "generation_store_v1": 1}
SUPPORTED_STATUSES = frozenset({"COMPLETE", "EMPTY", "PARTIAL", "FAILED", "IN_PROGRESS"})


class _EnvelopeError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _duplicate_reject(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise _EnvelopeError("DUPLICATE_JSON_KEY", f"duplicate manifest key: {key}")
        result[key] = value
    return result


def _parse_envelope(manifest: Any, manifest_bytes: bytes | None) -> tuple[dict, bytes | None]:
    if manifest_bytes is not None:
        if not isinstance(manifest_bytes, bytes):
            raise _EnvelopeError("MANIFEST_BYTES_INVALID", "manifest_bytes must be bytes")
        try:
            parsed = json.loads(
                manifest_bytes.decode("utf-8", errors="strict"),
                object_pairs_hook=_duplicate_reject,
                parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f"invalid JSON constant: {value}")),
            )
        except _EnvelopeError:
            raise
        except (UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise _EnvelopeError("MANIFEST_JSON_INVALID", "manifest bytes are not strict UTF-8 JSON") from exc
        if not isinstance(parsed, dict):
            raise _EnvelopeError("MANIFEST_ENVELOPE_INVALID", "manifest must be a JSON object")
        if manifest is not None and manifest != parsed:
            raise _EnvelopeError("MANIFEST_BYTES_DISAGREE", "manifest object does not match supplied bytes")
        return parsed, manifest_bytes
    if not isinstance(manifest, dict):
        raise _EnvelopeError("MANIFEST_ENVELOPE_INVALID", "manifest must be an object")
    return manifest, None


def _result(
    *, target: str, target_version: int, source_version: int | None,
    outcome: str, accepted: bool, failure_code: str | None = None,
    findings: Mapping[str, Any] | None = None, message: str | None = None,
) -> dict[str, Any]:
    return {
        "target": target,
        "source_schema_version": source_version,
        "target_schema_version": target_version,
        "outcome": outcome,
        "accepted": accepted,
        "eligible": False,
        "authorization": "NOT_AUTHORIZED",
        "failure_code": failure_code,
        "message": message,
        "findings": dict(findings or {}),
    }


def validate_for_component(
    manifest: Any = None,
    *,
    target: str,
    source_schema_version: int,
    manifest_bytes: bytes | None = None,
    artifacts_by_role: Mapping[str, bytes] | None = None,
    expected_stage: str | None = None,
    upstream_manifest_bytes: bytes | None = None,
    upstream_artifacts_by_role: Mapping[str, bytes] | None = None,
    upstream_chain=(),
) -> dict[str, Any]:
    """Validate only when the explicitly declared and actual versions match.

    This is a compatibility *fence*, not a v2↔v1 adapter. Verifier calls must
    supply the exact native manifest bytes and artifact evidence expected by
    ``verify_generation``. Store and schema calls use native manifest objects.
    """
    if not isinstance(target, str) or target not in TARGETS:
        return _result(target=str(target), target_version=-1, source_version=None, outcome="REJECTED", accepted=False, failure_code="UNKNOWN_TARGET")
    target_version = TARGET_VERSIONS[target]
    try:
        parsed, supplied_bytes = _parse_envelope(manifest, manifest_bytes)
    except _EnvelopeError as exc:
        return _result(target=target, target_version=target_version, source_version=None, outcome="REJECTED", accepted=False, failure_code=exc.code, message=str(exc))
    actual_version = parsed.get("schema_version")
    if type(source_schema_version) is not int or source_schema_version != actual_version:
        return _result(target=target, target_version=target_version, source_version=actual_version if type(actual_version) is int else None, outcome="REJECTED", accepted=False, failure_code="DECLARED_VERSION_MISMATCH", message="declared source version does not match the manifest")
    if type(actual_version) is not int or actual_version != target_version:
        return _result(target=target, target_version=target_version, source_version=actual_version if type(actual_version) is int else None, outcome="INCOMPATIBLE", accepted=False, failure_code="SCHEMA_VERSION_MISMATCH", message="no conversion is defined between these manifest contracts")
    status = parsed.get("status")
    if not isinstance(status, str) or status not in SUPPORTED_STATUSES:
        return _result(target=target, target_version=target_version, source_version=actual_version, outcome="REJECTED", accepted=False, failure_code="STATUS_UNSUPPORTED", message="status is outside the explicitly supported lifecycle vocabulary")

    try:
        if target == "schema_v2":
            result = schema.validate_manifest(parsed)
            return _result(
                target=target, target_version=target_version, source_version=actual_version,
                outcome="VALID" if result.schema_valid else "REJECTED", accepted=result.schema_valid,
                failure_code=None if result.schema_valid else "SCHEMA_REJECTED",
                findings={
                    "policy_resolved": result.policy_resolved,
                    "unresolved_decisions": list(result.unresolved_decisions),
                    "policy_dependencies": list(result.policy_dependencies),
                    "unresolved_findings": list(result.unresolved_findings),
                    "external_lineage_verified": False,
                },
            )
        if target == "offline_verifier_v1":
            if supplied_bytes is None:
                raise _EnvelopeError("MANIFEST_BYTES_REQUIRED", "offline verifier requires the exact native manifest bytes")
            result = verifier.verify_generation(
                supplied_bytes,
                artifacts_by_role if artifacts_by_role is not None else {},
                expected_stage=expected_stage,
                upstream_manifest_bytes=upstream_manifest_bytes,
                upstream_artifacts_by_role=upstream_artifacts_by_role,
                upstream_chain=upstream_chain,
            )
            return _result(
                target=target, target_version=target_version, source_version=actual_version,
                outcome=result.classification, accepted=result.accepted, failure_code=result.failure_code,
                findings={"status": result.status, "stage": result.stage, "eligible": result.eligible, "policy_dependencies": list(result.policy_dependencies)},
            )
        generation_store.validate_manifest(parsed)
        return _result(
            target=target, target_version=target_version, source_version=actual_version,
            outcome="VALID", accepted=True,
            findings={"status": parsed.get("status"), "stage": parsed.get("stage"), "selection_authorized": False},
        )
    except _EnvelopeError as exc:
        return _result(target=target, target_version=target_version, source_version=actual_version, outcome="REJECTED", accepted=False, failure_code=exc.code, message=str(exc))
    except schema.SchemaValidationError as exc:
        return _result(target=target, target_version=target_version, source_version=actual_version, outcome="REJECTED", accepted=False, failure_code=exc.code, message=str(exc))
    except generation_store.GenerationValidationError as exc:
        return _result(target=target, target_version=target_version, source_version=actual_version, outcome="REJECTED", accepted=False, failure_code="GENERATION_VALIDATION_REJECTED", message=str(exc))
    except Exception as exc:
        return _result(target=target, target_version=target_version, source_version=actual_version, outcome="ERROR", accepted=False, failure_code="UNEXPECTED_VALIDATION_EXCEPTION", message=f"{type(exc).__name__}: {exc}")


__all__ = ["TARGETS", "TARGET_VERSIONS", "validate_for_component"]
