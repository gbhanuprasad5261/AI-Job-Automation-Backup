"""Prepare offline search-page evidence candidates from explicit local files.

This module has no browser, network, subprocess, production workflow, or output
file integration. Provenance and observed states remain caller assertions, and
completion status is always UNKNOWN.
"""

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import stat

from search_page_evidence import (
    EvidenceCompletionStatus,
    EvidenceState,
    EvidenceValidation,
    _contains_unsafe_free_text,
    validate_evidence_fixture,
)


MAX_METADATA_BYTES = 256 * 1024
MAX_PNG_BYTES = 10 * 1024 * 1024
_READ_CHUNK_BYTES = 64 * 1024
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$", re.I)


@dataclass(frozen=True)
class CandidatePreparation:
    """In-memory candidate and validation result; no output is persisted."""

    candidate_fixture: dict | None
    validation: EvidenceValidation


def _failure(message):
    return CandidatePreparation(
        candidate_fixture=None,
        validation=EvidenceValidation(
            valid=False,
            observed_state=EvidenceState.UNKNOWN,
            issues=(message,),
            completion_status=EvidenceCompletionStatus.UNKNOWN,
        ),
    )


def _resolve_under_root(root, supplied_path, field_name):
    try:
        raw_path = Path(supplied_path)
        candidate = raw_path if raw_path.is_absolute() else root / raw_path
        resolved = candidate.resolve(strict=True)
        if not resolved.is_relative_to(root):
            raise ValueError
        if not resolved.is_file():
            raise ValueError
        return resolved
    except (OSError, RuntimeError, TypeError, ValueError):
        raise ValueError(f"{field_name} must be an existing file inside artifact_root.") from None


def _read_metadata(path):
    try:
        size = path.stat().st_size
        if not stat.S_ISREG(path.stat().st_mode) or size > MAX_METADATA_BYTES:
            raise ValueError
        # Bound the read even if the file grows after stat().
        with path.open("rb") as source:
            raw = source.read(MAX_METADATA_BYTES + 1)
        if len(raw) > MAX_METADATA_BYTES:
            raise ValueError
        decoded = raw.decode("utf-8", errors="strict")
        value = json.loads(decoded)
        if not isinstance(value, dict):
            raise ValueError
        return value
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
        raise ValueError(
            "metadata must be a readable UTF-8 JSON object within the size limit."
        ) from None


def _relative_reference(root, reference):
    if not isinstance(reference, str) or not reference.strip():
        raise ValueError("screenshot reference must be a non-empty relative path.")
    if _contains_unsafe_free_text(reference):
        raise ValueError("screenshot reference contains a URL or unsafe text.")
    relative = Path(reference)
    if relative.is_absolute() or ".." in relative.parts or ":" in reference:
        raise ValueError("screenshot reference must remain inside artifact_root.")
    try:
        resolved = (root / relative).resolve(strict=True)
    except (OSError, RuntimeError, TypeError, ValueError):
        raise ValueError("screenshot reference must identify an existing local file.") from None
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise ValueError("screenshot reference must remain inside artifact_root.")
    return resolved


def _hash_png(path):
    """Verify a bounded PNG input and return its SHA-256 digest."""
    try:
        info = path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_PNG_BYTES:
            raise ValueError
        digest = hashlib.sha256()
        total = 0
        with path.open("rb") as source:
            signature = source.read(len(_PNG_SIGNATURE))
            total += len(signature)
            if signature != _PNG_SIGNATURE:
                raise ValueError
            digest.update(signature)
            while True:
                chunk = source.read(min(_READ_CHUNK_BYTES, MAX_PNG_BYTES + 1 - total))
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_PNG_BYTES:
                    raise ValueError
                digest.update(chunk)
        if total != info.st_size:
            # Reject a file that changed size while it was being inspected.
            raise ValueError
        return digest.hexdigest()
    except (OSError, RuntimeError, TypeError, ValueError):
        raise ValueError(
            "screenshot must be a stable, readable PNG within the size limit."
        ) from None


def _validation_with_screenshot(base_validation, screenshot_issue=None):
    issues = base_validation.issues
    if screenshot_issue:
        issues += (screenshot_issue,)
    valid = base_validation.valid and screenshot_issue is None
    return EvidenceValidation(
        valid=valid,
        observed_state=(
            base_validation.observed_state if valid else EvidenceState.UNKNOWN
        ),
        issues=issues,
        completion_status=EvidenceCompletionStatus.UNKNOWN,
    )


def prepare_evidence_candidate(
    metadata_path,
    *,
    artifact_root,
    screenshot_path=None,
):
    """Read explicit local inputs and return a validated candidate in memory.

    Relative input paths are resolved under ``artifact_root``. No directories
    are scanned and no files are created or modified.
    """
    try:
        root = Path(artifact_root).resolve(strict=True)
        if not root.is_dir():
            raise ValueError
        metadata_file = _resolve_under_root(root, metadata_path, "metadata_path")
        if metadata_file.suffix.casefold() != ".json":
            raise ValueError("metadata_path must have a .json extension.")
        metadata = _read_metadata(metadata_file)
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        return _failure("artifact_root or metadata_path is invalid.")

    declared_screenshot = metadata.get("screenshot")
    if screenshot_path is None and declared_screenshot is not None:
        return _failure(
            "metadata screenshot references require an explicit screenshot_path."
        )

    candidate = dict(metadata)
    candidate.pop("screenshot", None)
    base_validation = validate_evidence_fixture(candidate, artifact_root=None)
    if not base_validation.valid:
        return CandidatePreparation(None, _validation_with_screenshot(base_validation))

    if screenshot_path is None:
        return CandidatePreparation(
            candidate_fixture=candidate,
            validation=_validation_with_screenshot(base_validation),
        )

    try:
        screenshot_file = _resolve_under_root(root, screenshot_path, "screenshot_path")
        if screenshot_file.suffix.casefold() != ".png":
            raise ValueError("screenshot_path must have a .png extension.")
        if declared_screenshot is not None:
            if (
                not isinstance(declared_screenshot, dict)
                or set(declared_screenshot) != {"reference", "sha256"}
            ):
                raise ValueError("metadata screenshot entry must be an object.")
            declared_reference = declared_screenshot.get("reference")
            declared_digest = declared_screenshot.get("sha256")
            if _relative_reference(root, declared_reference) != screenshot_file:
                raise ValueError(
                    "metadata screenshot reference must match the explicit screenshot_path."
                )
            if not isinstance(declared_digest, str) or not _SHA256_PATTERN.fullmatch(
                declared_digest
            ):
                raise ValueError("metadata screenshot hash must be a SHA-256 digest.")
        else:
            declared_digest = None

        actual_digest = _hash_png(screenshot_file)
        if declared_digest is not None and actual_digest.casefold() != declared_digest.casefold():
            raise ValueError("screenshot hash does not match the explicit PNG file.")

        reference = screenshot_file.relative_to(root).as_posix()
        _relative_reference(root, reference)
        candidate["screenshot"] = {
            "reference": reference,
            "sha256": actual_digest,
        }
        validation = _validation_with_screenshot(base_validation)
        return CandidatePreparation(candidate, validation)
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        return _failure("screenshot input failed offline validation.")
