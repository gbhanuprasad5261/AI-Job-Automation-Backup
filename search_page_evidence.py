"""Offline-only validation for sanitized search-page evidence fixtures.

This module has no browser, network, collector, publication, or application
workflow integration. A valid fixture label is an observation annotation only;
the production completion status always remains UNKNOWN. Provenance labels and
observations are fixture assertions, not independently verified facts. Text
screening is heuristic and cannot identify every secret or personal detail.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
from pathlib import Path
import re
import stat
from urllib.parse import urlsplit


class EvidenceState(str, Enum):
    POPULATED_RESULTS = "POPULATED_RESULTS"
    LEGITIMATE_EMPTY = "LEGITIMATE_EMPTY"
    LOADING_OR_INCOMPLETE = "LOADING_OR_INCOMPLETE"
    AUTHENTICATION_OR_INTERSTITIAL = "AUTHENTICATION_OR_INTERSTITIAL"
    UNKNOWN = "UNKNOWN"


class EvidenceCompletionStatus(str, Enum):
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class EvidenceValidation:
    valid: bool
    observed_state: EvidenceState
    issues: tuple = ()
    completion_status: EvidenceCompletionStatus = EvidenceCompletionStatus.UNKNOWN


_ALLOWED_SOURCES = {
    "synthetic_fixture",
    "user_provided_reference",
    "approved_live_capture",
}
_ALLOWED_LOADING_STATES = {
    "loading_observed",
    "settled_observed",
    "not_observed",
    "conflicting",
    "unknown",
}
_ALLOWED_IDENTITY_STATES = {"matched", "mismatched", "unverified"}
_ALLOWED_EXHAUSTION_OBSERVATIONS = {
    "more_batches_observed",
    "terminal_condition_observed",
    "not_observed",
    "unknown",
}
_ALLOWED_CAP_OBSERVATIONS = {"reached", "not_reached", "unknown"}
_EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
_PHONE_PATTERN = re.compile(r"(?<!\w)\+?(?:\d[\s().-]*){10,}(?!\w)")
_SECRET_PATTERN = re.compile(
    r"\b(?:password|cookie|set-cookie|authorization|csrf|session|token)\b\s*[:=]",
    re.I,
)
_IDENTIFIER_PATTERN = re.compile(
    r"\b(?:account|member|profile|user)\s*(?:id|identifier)\b\s*[:=]", re.I
)
_URL_PATTERN = re.compile(
    r"(?:\b[a-z][a-z0-9+.-]*://[^\s<>\"']+|(?<!\w)//[^\s<>\"']+|"
    r"\bwww\.[^\s<>\"']+|"
    r"\b[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.[a-z]{2,}"
    r"(?::\d+)?[/?#][^\s<>\"']*)",
    re.I,
)
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$", re.I)
MAX_SCREENSHOT_BYTES = 10 * 1024 * 1024
_SCREENSHOT_READ_CHUNK_BYTES = 64 * 1024


def sanitize_url(url):
    """Return only a canonical HTTP(S) origin, dropping path and URL secrets."""
    try:
        parsed = urlsplit(str(url or ""))
        scheme = parsed.scheme.casefold()
        if scheme not in {"http", "https"} or not parsed.hostname:
            return None
        hostname = parsed.hostname.casefold()
        if ":" in hostname and not hostname.startswith("["):
            hostname = f"[{hostname}]"
        netloc = hostname
        if parsed.port is not None:
            netloc = f"{netloc}:{parsed.port}"
        return f"{scheme}://{netloc}"
    except (TypeError, ValueError):
        return None


def _contains_sensitive_text(value):
    return bool(
        _EMAIL_PATTERN.search(value)
        or _PHONE_PATTERN.search(value)
        or _SECRET_PATTERN.search(value)
        or _IDENTIFIER_PATTERN.search(value)
    )


def _contains_unsafe_free_text(value):
    """Flag common URL forms and the existing heuristic sensitive-text patterns."""
    return _contains_sensitive_text(value) or bool(_URL_PATTERN.search(value))


def _check_text(value, field_name, issues, *, required=False):
    if not isinstance(value, str) or (required and not value.strip()):
        issues.append(f"{field_name} must be a non-empty string.")
        return False
    if _contains_unsafe_free_text(value):
        issues.append(
            f"{field_name} appears to contain a URL, sensitive, or contact data."
        )
        return False
    return True


def _check_state_evidence(value, field_name, issues):
    """Require an evidence value, rejecting only obvious non-observation labels.

    Relevance beyond these placeholders remains a reviewer judgment; this
    offline validator does not interpret DOM semantics or establish truth.
    """
    if not _check_text(value, field_name, issues, required=True):
        return False
    if value.strip().casefold() in {
        "none",
        "unknown",
        "n/a",
        "not observed",
        "no observation",
        "no evidence",
        "placeholder",
    }:
        issues.append(f"{field_name} must describe an observation, not a placeholder.")
        return False
    return True


def _check_object(value, field_name, required_keys, optional_keys, issues):
    if not isinstance(value, dict):
        issues.append(f"{field_name} must be an object.")
        return False
    missing = set(required_keys) - set(value)
    extra = set(value) - set(required_keys) - set(optional_keys)
    if missing:
        issues.append(f"{field_name} is missing required fields: {sorted(missing)}.")
    if extra:
        issues.append(f"{field_name} has unsupported fields: {sorted(extra)}.")
    return not missing and not extra


def _check_timestamp(value, issues):
    if value is None:
        return
    if not isinstance(value, str):
        issues.append("provenance.captured_at_utc must be an ISO-8601 UTC string or null.")
        return
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        issues.append("provenance.captured_at_utc must be a valid ISO-8601 UTC timestamp.")
        return
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        issues.append("provenance.captured_at_utc must include a UTC offset.")


def _check_screenshot(value, artifact_root, issues):
    """Check containment and byte consistency, not image authenticity/origin."""
    if value is None:
        return
    if not _check_object(
        value,
        "screenshot",
        required_keys=("reference", "sha256"),
        optional_keys=(),
        issues=issues,
    ):
        return

    reference = value["reference"]
    digest = value["sha256"]
    if not isinstance(reference, str) or not reference.strip():
        issues.append("screenshot.reference must be a non-empty relative path.")
        return
    if not _SHA256_PATTERN.fullmatch(str(digest or "")):
        issues.append("screenshot.sha256 must be a 64-character hexadecimal digest.")
        return
    if _contains_unsafe_free_text(reference):
        issues.append("screenshot.reference appears to contain a URL or sensitive data.")
        return

    relative_path = Path(reference)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        issues.append("screenshot.reference must stay inside the supplied artifact root.")
        return
    if artifact_root is None:
        issues.append("screenshot hash cannot be verified without an artifact root.")
        return

    try:
        root = Path(artifact_root).resolve()
        target = (root / relative_path).resolve()
        if not target.is_relative_to(root):
            issues.append("screenshot.reference resolves outside the artifact root.")
            return
        info = target.stat()
        if not stat.S_ISREG(info.st_mode):
            issues.append("screenshot reference must identify a regular file.")
            return
        if info.st_size > MAX_SCREENSHOT_BYTES:
            issues.append("screenshot exceeds the maximum permitted size.")
            return

        hasher = hashlib.sha256()
        total = 0
        with target.open("rb") as source:
            while True:
                chunk = source.read(
                    min(
                        _SCREENSHOT_READ_CHUNK_BYTES,
                        MAX_SCREENSHOT_BYTES + 1 - total,
                    )
                )
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_SCREENSHOT_BYTES:
                    issues.append("screenshot exceeds the maximum permitted size.")
                    return
                hasher.update(chunk)
        if total != info.st_size:
            issues.append("screenshot changed while its hash was being verified.")
            return
        actual_digest = hasher.hexdigest()
    except (OSError, RuntimeError, TypeError, ValueError):
        issues.append("screenshot reference could not be read for hash verification.")
        return
    if actual_digest.casefold() != digest.casefold():
        issues.append("screenshot hash does not match the referenced file.")


def validate_evidence_fixture(fixture, *, artifact_root=None):
    """Validate a local fixture without treating it as collection completion."""
    issues = []
    if not _check_object(
        fixture,
        "fixture",
        required_keys=(
            "schema_version",
            "provenance",
            "requested_scope",
            "observations",
            "interpretation",
            "limitations",
        ),
        optional_keys=("screenshot",),
        issues=issues,
    ):
        return EvidenceValidation(False, EvidenceState.UNKNOWN, tuple(issues))

    version = fixture["schema_version"]
    if not isinstance(version, int) or isinstance(version, bool) or version != 1:
        issues.append("schema_version must be integer 1.")

    provenance = fixture["provenance"]
    if _check_object(
        provenance,
        "provenance",
        required_keys=("source",),
        optional_keys=("source_reference", "captured_at_utc", "code_revision"),
        issues=issues,
    ):
        if (
            not isinstance(provenance["source"], str)
            or provenance["source"] not in _ALLOWED_SOURCES
        ):
            issues.append("provenance.source is not a supported source label.")
        if "source_reference" in provenance:
            source_reference = provenance["source_reference"]
            if _check_text(source_reference, "provenance.source_reference", issues):
                source_path = Path(source_reference)
                if (
                    source_path.is_absolute()
                    or ".." in source_path.parts
                    or ":" in source_reference
                ):
                    issues.append("provenance.source_reference must be a safe relative reference.")
        _check_timestamp(provenance.get("captured_at_utc"), issues)
        if "code_revision" in provenance:
            revision = provenance["code_revision"]
            if not isinstance(revision, str) or not revision.strip() or any(
                c.isspace() for c in revision
            ):
                issues.append("provenance.code_revision must be a non-empty revision string.")
            else:
                _check_text(
                    revision,
                    "provenance.code_revision",
                    issues,
                    required=True,
                )

    requested_scope = fixture["requested_scope"]
    if _check_object(
        requested_scope,
        "requested_scope",
        required_keys=("query", "location"),
        optional_keys=(),
        issues=issues,
    ):
        _check_text(requested_scope["query"], "requested_scope.query", issues, required=True)
        _check_text(requested_scope["location"], "requested_scope.location", issues, required=True)

    observations = fixture["observations"]
    if not _check_object(
        observations,
        "observations",
        required_keys=(
            "sanitized_url",
            "observed_state",
            "page_identity",
            "dom_evidence",
            "loading",
            "visible_results",
            "pagination",
            "interstitial",
            "errors_observed",
        ),
        optional_keys=(),
        issues=issues,
    ):
        state = EvidenceState.UNKNOWN
    else:
        try:
            state = EvidenceState(observations["observed_state"])
        except (TypeError, ValueError):
            state = EvidenceState.UNKNOWN
            issues.append("observations.observed_state is not a supported evidence label.")

        sanitized_url = observations["sanitized_url"]
        if (
            not isinstance(sanitized_url, str)
            or sanitize_url(sanitized_url) != sanitized_url
        ):
            issues.append("observations.sanitized_url must contain only a sanitized HTTP(S) origin.")

        identity = observations["page_identity"]
        if _check_object(
            identity,
            "observations.page_identity",
            required_keys=("state", "evidence"),
            optional_keys=(),
            issues=issues,
        ):
            if (
                not isinstance(identity["state"], str)
                or identity["state"] not in _ALLOWED_IDENTITY_STATES
            ):
                issues.append("observations.page_identity.state is not supported.")
            _check_text(identity["evidence"], "observations.page_identity.evidence", issues)

        dom = observations["dom_evidence"]
        if _check_object(
            dom,
            "observations.dom_evidence",
            required_keys=("excerpt", "sanitized"),
            optional_keys=(),
            issues=issues,
        ):
            _check_text(dom["excerpt"], "observations.dom_evidence.excerpt", issues, required=True)
            # This flag records an assertion by the fixture author; it does not
            # sanitize the excerpt or independently verify its contents.
            if dom["sanitized"] is not True:
                issues.append("observations.dom_evidence.sanitized must be true.")

        loading = observations["loading"]
        if _check_object(
            loading,
            "observations.loading",
            required_keys=("state", "evidence"),
            optional_keys=(),
            issues=issues,
        ):
            if (
                not isinstance(loading["state"], str)
                or loading["state"] not in _ALLOWED_LOADING_STATES
            ):
                issues.append("observations.loading.state is not supported.")
            _check_text(loading["evidence"], "observations.loading.evidence", issues)

        visible = observations["visible_results"]
        if _check_object(
            visible,
            "observations.visible_results",
            required_keys=("card_count", "displayed_count_text", "empty_state_observed"),
            optional_keys=(),
            issues=issues,
        ):
            card_count = visible["card_count"]
            if card_count is not None and (
                not isinstance(card_count, int)
                or isinstance(card_count, bool)
                or card_count < 0
            ):
                issues.append("observations.visible_results.card_count must be a non-negative integer or null.")
            count_text = visible["displayed_count_text"]
            if count_text is not None:
                _check_text(count_text, "observations.visible_results.displayed_count_text", issues)
            if not isinstance(visible["empty_state_observed"], bool):
                issues.append("observations.visible_results.empty_state_observed must be boolean.")

        pagination = observations["pagination"]
        if _check_object(
            pagination,
            "observations.pagination",
            required_keys=(
                "batch_observations",
                "exhaustion_observation",
                "cap_observation",
            ),
            optional_keys=(),
            issues=issues,
        ):
            batches = pagination["batch_observations"]
            if not isinstance(batches, list):
                issues.append("observations.pagination.batch_observations must be a list.")
            else:
                for index, item in enumerate(batches):
                    _check_text(item, f"observations.pagination.batch_observations[{index}]", issues)
            if (
                not isinstance(pagination["exhaustion_observation"], str)
                or pagination["exhaustion_observation"]
                not in _ALLOWED_EXHAUSTION_OBSERVATIONS
            ):
                issues.append("observations.pagination.exhaustion_observation is not supported.")
            if (
                not isinstance(pagination["cap_observation"], str)
                or pagination["cap_observation"] not in _ALLOWED_CAP_OBSERVATIONS
            ):
                issues.append("observations.pagination.cap_observation is not supported.")

        interstitial = observations["interstitial"]
        if _check_object(
            interstitial,
            "observations.interstitial",
            required_keys=("observed", "kind", "evidence"),
            optional_keys=(),
            issues=issues,
        ):
            if not isinstance(interstitial["observed"], bool):
                issues.append("observations.interstitial.observed must be boolean.")
            _check_text(interstitial["kind"], "observations.interstitial.kind", issues)
            _check_text(interstitial["evidence"], "observations.interstitial.evidence", issues)

        observed_errors = observations["errors_observed"]
        if not isinstance(observed_errors, list):
            issues.append("observations.errors_observed must be a list.")
        else:
            for index, item in enumerate(observed_errors):
                _check_text(item, f"observations.errors_observed[{index}]", issues)

        identity = identity if isinstance(identity, dict) else {}
        loading = loading if isinstance(loading, dict) else {}
        visible = visible if isinstance(visible, dict) else {}
        pagination = pagination if isinstance(pagination, dict) else {}
        interstitial = interstitial if isinstance(interstitial, dict) else {}

        if state == EvidenceState.POPULATED_RESULTS:
            card_count = visible.get("card_count")
            if (
                not isinstance(card_count, int)
                or isinstance(card_count, bool)
                or card_count <= 0
            ):
                issues.append(
                    "POPULATED_RESULTS requires a positive observed visible-card count; "
                    "a displayed total is insufficient."
                )
            if isinstance(loading.get("state"), str) and loading.get("state") in {
                "loading_observed",
                "conflicting",
            }:
                issues.append("POPULATED_RESULTS conflicts with observed loading or conflicting state.")
        elif state == EvidenceState.LEGITIMATE_EMPTY:
            if visible.get("card_count") != 0 or visible.get("empty_state_observed") is not True:
                issues.append("LEGITIMATE_EMPTY requires zero visible cards and an explicit observed empty state.")
            if loading.get("state") != "settled_observed":
                issues.append("LEGITIMATE_EMPTY requires a directly observed settled state.")
            if identity.get("state") != "matched":
                issues.append("LEGITIMATE_EMPTY requires the requested search identity to be matched.")
            _check_state_evidence(
                identity.get("evidence"),
                "LEGITIMATE_EMPTY page-identity evidence",
                issues,
            )
            _check_state_evidence(
                loading.get("evidence"),
                "LEGITIMATE_EMPTY settled-state evidence",
                issues,
            )
            _check_state_evidence(
                dom.get("excerpt"),
                "LEGITIMATE_EMPTY DOM evidence",
                issues,
            )
            if pagination.get("exhaustion_observation") == "more_batches_observed":
                issues.append("LEGITIMATE_EMPTY conflicts with observed additional result batches.")
        elif state == EvidenceState.LOADING_OR_INCOMPLETE:
            has_loading_evidence = loading.get("state") in {"loading_observed", "conflicting"}
            has_more_batches = pagination.get("exhaustion_observation") == "more_batches_observed"
            if not (has_loading_evidence or has_more_batches):
                issues.append("LOADING_OR_INCOMPLETE requires an explicit loading or additional-batch observation.")
            if has_loading_evidence:
                _check_state_evidence(
                    loading.get("evidence"),
                    "LOADING_OR_INCOMPLETE loading evidence",
                    issues,
                )
            if has_more_batches:
                batches = pagination.get("batch_observations")
                if not isinstance(batches, list) or not any(
                    isinstance(item, str) and item.strip() for item in batches
                ):
                    issues.append(
                        "LOADING_OR_INCOMPLETE requires non-empty additional-batch evidence."
                    )
        elif state == EvidenceState.AUTHENTICATION_OR_INTERSTITIAL:
            if interstitial.get("observed") is not True:
                issues.append("AUTHENTICATION_OR_INTERSTITIAL requires an observed interstitial.")
            kind = interstitial.get("kind")
            if not _check_state_evidence(
                kind,
                "AUTHENTICATION_OR_INTERSTITIAL kind",
                issues,
            ) or kind.strip().casefold() in {"none", "unknown", "not observed", "not applicable"}:
                issues.append(
                    "AUTHENTICATION_OR_INTERSTITIAL requires a specific observed kind."
                )
            _check_state_evidence(
                interstitial.get("evidence"),
                "AUTHENTICATION_OR_INTERSTITIAL evidence",
                issues,
            )

    interpretation = fixture["interpretation"]
    if _check_object(
        interpretation,
        "interpretation",
        required_keys=("notes", "search_completion_claim"),
        optional_keys=(),
        issues=issues,
    ):
        _check_text(interpretation["notes"], "interpretation.notes", issues)
        if interpretation["search_completion_claim"] is not False:
            issues.append("interpretation.search_completion_claim must be false.")

    limitations = fixture["limitations"]
    if not isinstance(limitations, list) or not limitations:
        issues.append("limitations must be a non-empty list.")
    else:
        for index, item in enumerate(limitations):
            _check_text(item, f"limitations[{index}]", issues, required=True)

    _check_screenshot(fixture.get("screenshot"), artifact_root, issues)

    valid = not issues
    return EvidenceValidation(
        valid=valid,
        observed_state=state if valid else EvidenceState.UNKNOWN,
        issues=tuple(issues),
        completion_status=EvidenceCompletionStatus.UNKNOWN,
    )
