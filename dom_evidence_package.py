"""In-memory validation for versioned, sanitized search-page evidence packages.

This module validates structure and consistency only. It does not read artifact
files, inspect a browser, verify provenance, establish that observations are
true, or classify production collection completion. Completion is always
UNKNOWN. Text screening is heuristic and is not a complete privacy control.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from ipaddress import IPv4Address, IPv6Address
import re


class PageEvidenceState(str, Enum):
    POPULATED_RESULTS_SETTLED = "POPULATED_RESULTS_SETTLED"
    LEGITIMATE_EMPTY = "LEGITIMATE_EMPTY"
    LOADING_OR_UNSETTLED = "LOADING_OR_UNSETTLED"
    AUTHENTICATION_OR_INTERSTITIAL = "AUTHENTICATION_OR_INTERSTITIAL"
    POPULATED_MORE_PAGINATION = "POPULATED_MORE_PAGINATION"
    EXHAUSTION_REVIEW_RECORDED = "EXHAUSTION_REVIEW_RECORDED"
    UNKNOWN = "UNKNOWN"


class CompletionStatus(str, Enum):
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class PackageValidation:
    valid: bool
    observed_state: PageEvidenceState
    issues: tuple = ()
    completion_status: CompletionStatus = field(default=CompletionStatus.UNKNOWN, init=False)


_BASIS = {
    "direct_observation",
    "derived",
    "provider_assertion",
    "independent_review_record",
    "unknown",
}
_SOURCES = {
    "synthetic_fixture",
    "user_provided_visual_reference",
    "manual_dom_capture",
    "collector_run_ledger",
}
_STATES = {state.value for state in PageEvidenceState}
_LOADING = {"settled", "loading", "unsettled", "conflicting", "unknown"}
_PAGINATION = {
    "more_batches_observed",
    "terminal_condition_observed",
    "not_observed",
    "unknown",
}
_DISPOSITIONS = {"QUALIFYING", "FILTERED", "UNPROCESSED", "UNKNOWN"}
_FREE_TEXT_PATTERNS = (
    re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I),
    re.compile(r"(?<!\w)\+?(?:\d[\s().-]*){10,}(?!\w)"),
    re.compile(
        r"(?:\b[a-z][a-z0-9+.-]*://\S+|\bwww\.\S+|"
        r"\b[a-z0-9-]+(?:\.[a-z0-9-]+)+(?::\d+)?(?:[/?#]\S*)?)",
        re.I,
    ),
    re.compile(
        r"\b(?:password|cookie|set-cookie|authorization|csrf|session|token|"
        r"access_token|refresh_token|api_key)\s*[:=]",
        re.I,
    ),
    re.compile(r"\bbearer\s+[A-Za-z0-9._~+/-]+=*", re.I),
)
_OPAQUE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$", re.I)
_ENCODED_PATH_ESCAPE = re.compile(r"%(?:2e|2f|5c)", re.I)
_CONTROL_CHARACTER = re.compile(r"[\x00-\x1f\x7f-\x9f]")
_REFERENCE_URL = re.compile(
    r"^(?:[a-z][a-z0-9+.-]*://|www\.)|"
    r"^[a-z0-9-]+(?:\.[a-z0-9-]+)+(?:[/:?#].*)?$",
    re.I,
)
_ORIGIN_AUTHORITY = re.compile(r"^(\[[0-9A-Fa-f:]+\]|[A-Za-z0-9.-]+)(?::([0-9]+))?$")


def _is_mapping(value):
    return isinstance(value, dict)


def _shape(value, name, required, optional, issues):
    if not _is_mapping(value):
        issues.append(f"{name} must be an object.")
        return False
    missing = set(required) - value.keys()
    extra = value.keys() - set(required) - set(optional)
    if missing:
        issues.append(f"{name} is missing fields: {sorted(map(str, missing))}.")
    if extra:
        issues.append(f"{name} has unsupported fields: {sorted(map(str, extra))}.")
    return not missing and not extra


def _safe_text(value, name, issues, *, required=False):
    if not isinstance(value, str) or (required and not value.strip()):
        issues.append(f"{name} must be a non-empty string." if required else f"{name} must be text or null.")
        return False
    if any(pattern.search(value) for pattern in _FREE_TEXT_PATTERNS):
        issues.append(f"{name} contains text flagged by heuristic privacy screening.")
        return False
    return True


def _safe_reference(value, name, issues, *, required=False):
    if value is None and not required:
        return True
    if not isinstance(value, str) or not value.strip():
        issues.append(f"{name} must be a non-empty relative reference or null.")
        return False
    if (
        value.startswith(("/", "\\"))
        or "\\" in value
        or ":" in value
        or "?" in value
        or "#" in value
        or _CONTROL_CHARACTER.search(value)
        or _ENCODED_PATH_ESCAPE.search(value)
        or any(part in {"", ".", ".."} for part in value.split("/"))
        or _REFERENCE_URL.search(value)
        or any(pattern.search(value) for pattern in (
            _FREE_TEXT_PATTERNS[0], _FREE_TEXT_PATTERNS[1],
            _FREE_TEXT_PATTERNS[3], _FREE_TEXT_PATTERNS[4],
        ))
    ):
        issues.append(f"{name} must be a safe relative reference.")
        return False
    return True


def _refs(value, name, artifact_names, issues, *, required=False):
    if not isinstance(value, list) or any(not isinstance(ref, str) for ref in value):
        issues.append(f"{name} must be a list of artifact keys.")
        return False
    if required and not value:
        issues.append(f"{name} must reference direct evidence.")
        return False
    if len(value) != len(set(value)) or any(ref not in artifact_names for ref in value):
        issues.append(f"{name} contains duplicate or unavailable artifact keys.")
        return False
    return True


def _text_observation(value, name, artifacts, issues, *, required=False):
    if not _shape(value, name, ("value", "basis", "evidence_refs"), (), issues):
        return None
    text = value["value"]
    if text is not None:
        _safe_text(text, f"{name}.value", issues, required=required)
    elif required:
        issues.append(f"{name}.value is required for this state.")
    if not isinstance(value["basis"], str) or value["basis"] not in _BASIS:
        issues.append(f"{name}.basis is unsupported.")
    _refs(value["evidence_refs"], f"{name}.evidence_refs", artifacts, issues)
    return text


def _is_sanitized_origin(value):
    """Accept only the module's limited HTTP(S) origin syntax.

    This validates a sanitized origin shape, not every URL standard edge case
    and not the truth or provenance of the supplied origin.
    """
    if not isinstance(value, str) or _CONTROL_CHARACTER.search(value) or any(char.isspace() for char in value):
        return False
    if "?" in value or "#" in value:
        return False
    scheme, separator, authority_value = value.partition("://")
    if not separator or scheme.lower() not in {"http", "https"}:
        return False
    authority = _ORIGIN_AUTHORITY.fullmatch(authority_value)
    if authority is None:
        return False
    host, port_text = authority.groups()
    if port_text is not None:
        if len(port_text) > 5 or int(port_text) > 65535:
            return False
    if host.startswith("["):
        try:
            IPv6Address(host[1:-1])
        except ValueError:
            return False
    elif host.replace(".", "").isdigit():
        try:
            IPv4Address(host)
        except ValueError:
            return False
    else:
        if len(host) > 253:
            return False
        labels = host.split(".")
        if any(
            not label
            or len(label) > 63
            or not label[0].isalnum()
            or not label[-1].isalnum()
            or any(not (char.isascii() and (char.isalnum() or char == "-")) for char in label)
            for label in labels
        ):
            return False
    return True


def _timestamp(value, issues):
    if value is None:
        return
    if not isinstance(value, str):
        issues.append("capture_time.timestamp_utc must be an ISO-8601 string or null.")
        return
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        issues.append("capture_time.timestamp_utc is not valid ISO-8601.")
        return
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        issues.append("capture_time.timestamp_utc must have a UTC offset.")


def _validate_artifacts(artifacts, issues):
    names = {"dom_snapshot", "screenshot", "source_run_ledger"}
    if not _shape(artifacts, "artifacts", names, (), issues):
        return set()
    available = set()
    for name in names:
        item = artifacts[name]
        if item is None:
            continue
        if not _shape(item, f"artifacts.{name}", ("reference", "sha256", "redaction_review"), (), issues):
            continue
        _safe_reference(item["reference"], f"artifacts.{name}.reference", issues, required=True)
        if not isinstance(item["sha256"], str) or not _SHA256.fullmatch(item["sha256"]):
            issues.append(f"artifacts.{name}.sha256 must be a 64-character hexadecimal digest.")
        if not isinstance(item["redaction_review"], str) or item["redaction_review"] not in {"reviewed", "not_reviewed", "unknown"}:
            issues.append(f"artifacts.{name}.redaction_review is unsupported.")
        available.add(name)
    return available


def _validate_candidate_processing(value, requested_scope, artifacts, issues):
    if value is None:
        return
    if not _shape(value, "candidate_processing", ("source_run_ledger", "discovered_count", "dispositions"), (), issues):
        return
    ledger = value["source_run_ledger"]
    if not _shape(
        ledger,
        "candidate_processing.source_run_ledger",
        ("run_id", "reference", "scope_query", "scope_location", "basis"),
        (),
        issues,
    ):
        return
    if not isinstance(ledger["run_id"], str) or not _OPAQUE_ID.fullmatch(ledger["run_id"]):
        issues.append("candidate source ledger run_id must be an opaque identifier.")
    _safe_reference(ledger["reference"], "candidate source ledger reference", issues, required=True)
    _safe_text(ledger["scope_query"], "candidate source ledger scope_query", issues, required=True)
    _safe_text(ledger["scope_location"], "candidate source ledger scope_location", issues, required=True)
    if not isinstance(ledger["basis"], str) or ledger["basis"] not in _BASIS - {"unknown"}:
        issues.append("candidate source ledger basis must state how it was supplied.")
    if (
        isinstance(requested_scope, dict)
        and ledger.get("scope_query") != requested_scope.get("query")
    ) or (
        isinstance(requested_scope, dict)
        and ledger.get("scope_location") != requested_scope.get("location")
    ):
        issues.append("candidate source ledger scope must match the package requested scope.")
    ledger_artifact = artifacts.get("source_run_ledger") if isinstance(artifacts, dict) else None
    if not isinstance(ledger_artifact, dict):
        issues.append("candidate processing requires an explicitly referenced source_run_ledger artifact.")
    elif ledger.get("reference") != ledger_artifact.get("reference"):
        issues.append("candidate source ledger reference must match its declared artifact.")
    count = value["discovered_count"]
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        issues.append("candidate_processing.discovered_count must be a non-negative integer.")
    dispositions = value["dispositions"]
    if not isinstance(dispositions, list):
        issues.append("candidate_processing.dispositions must be a list.")
        return
    ids = []
    for index, item in enumerate(dispositions):
        name = f"candidate_processing.dispositions[{index}]"
        if not _shape(item, name, ("candidate_id", "disposition"), (), issues):
            continue
        candidate_id = item["candidate_id"]
        if not isinstance(candidate_id, str) or not _OPAQUE_ID.fullmatch(candidate_id):
            issues.append(f"{name}.candidate_id must be a non-empty opaque identifier.")
        else:
            ids.append(candidate_id)
        if not isinstance(item["disposition"], str) or item["disposition"] not in _DISPOSITIONS:
            issues.append(f"{name}.disposition is unsupported.")
    if len(ids) != len(set(ids)):
        issues.append("candidate disposition IDs must be unique within the supplied scope ledger.")
    if isinstance(count, int) and not isinstance(count, bool) and count != len(dispositions):
        issues.append("discovered_count must equal the number of explicit candidate dispositions.")


def validate_dom_evidence_package(package):
    """Validate an in-memory package without reading files or verifying claims.

    A valid result means only that the supplied package conforms to this
    structural contract. Provider assertions, hashes, redaction flags, and
    review records are not independently authenticated by this function.
    """
    issues = []
    required = (
        "schema_version", "package_identity", "provenance", "capture_time",
        "code_revision", "requested_scope", "observed_search_identity",
        "artifacts", "observations", "candidate_processing", "interpretations",
        "privacy_review", "limitations", "completion_status",
    )
    if not _shape(package, "package", required, (), issues):
        return PackageValidation(False, PageEvidenceState.UNKNOWN, tuple(issues))
    if package["schema_version"] != "1.0":
        issues.append("schema_version must be '1.0'.")
    if package["completion_status"] != CompletionStatus.UNKNOWN.value:
        issues.append("completion_status must remain UNKNOWN.")
    artifacts = _validate_artifacts(package["artifacts"], issues)

    identity = package["package_identity"]
    if _shape(identity, "package_identity", ("capture_id", "production_run_id", "production_run_association"), (), issues):
        for key in ("capture_id", "production_run_id"):
            item = identity[key]
            if item is not None and (not isinstance(item, str) or not _OPAQUE_ID.fullmatch(item)):
                issues.append(f"package_identity.{key} must be an opaque identifier or null.")
        association = identity["production_run_association"]
        if not isinstance(association, str) or association not in {"not_established", "independent_review_recorded"}:
            issues.append("production_run_association is unsupported.")
        if association == "independent_review_recorded" and identity["production_run_id"] is None:
            issues.append("a recorded production-run association requires a production_run_id.")

    provenance = package["provenance"]
    if _shape(provenance, "provenance", ("source_type", "source_reference", "provider_assertions", "independent_verification"), (), issues):
        if not isinstance(provenance["source_type"], str) or provenance["source_type"] not in _SOURCES:
            issues.append("provenance.source_type is unsupported.")
        _safe_reference(provenance["source_reference"], "provenance.source_reference", issues)
        assertions = provenance["provider_assertions"]
        if not isinstance(assertions, list):
            issues.append("provenance.provider_assertions must be a list.")
        else:
            for index, claim in enumerate(assertions):
                _safe_text(claim, f"provenance.provider_assertions[{index}]", issues, required=True)
        review = provenance["independent_verification"]
        if _shape(review, "provenance.independent_verification", ("status", "method", "evidence_refs", "reviewed_claims"), (), issues):
            if not isinstance(review["status"], str) or review["status"] not in {"unverified", "review_recorded"}:
                issues.append("independent_verification.status is unsupported.")
            if review["method"] is not None:
                _safe_text(review["method"], "independent_verification.method", issues, required=True)
            _refs(review["evidence_refs"], "independent_verification.evidence_refs", artifacts, issues)
            claims = review["reviewed_claims"]
            if not isinstance(claims, list) or any(not isinstance(claim, str) or not claim for claim in claims):
                issues.append("independent_verification.reviewed_claims must be a list of claim names.")
            if review["status"] == "review_recorded" and (not review["method"] or not review["evidence_refs"] or not claims):
                issues.append("review_recorded requires a method, evidence reference, and reviewed claims.")

    capture_time = package["capture_time"]
    if _shape(capture_time, "capture_time", ("timestamp_utc", "time_basis", "method"), (), issues):
        _timestamp(capture_time["timestamp_utc"], issues)
        if not isinstance(capture_time["time_basis"], str) or capture_time["time_basis"] not in {"unknown", "capture_clock_utc", "provider_assertion", "filesystem_metadata"}:
            issues.append("capture_time.time_basis is unsupported.")
        if capture_time["timestamp_utc"] is None and capture_time["time_basis"] != "unknown":
            issues.append("a missing capture timestamp must use time_basis='unknown'.")
        if capture_time["method"] is not None:
            _safe_text(capture_time["method"], "capture_time.method", issues, required=True)

    revision = package["code_revision"]
    if _shape(revision, "code_revision", ("value", "basis"), (), issues):
        if not isinstance(revision["basis"], str) or revision["basis"] not in {"unknown", "provider_assertion", "repository_record"}:
            issues.append("code_revision.basis is unsupported.")
        if revision["value"] is None and revision["basis"] != "unknown":
            issues.append("a missing code revision must use basis='unknown'.")
        if revision["value"] is not None:
            _safe_text(revision["value"], "code_revision.value", issues, required=True)

    scope = package["requested_scope"]
    if _shape(scope, "requested_scope", ("query", "location", "basis"), (), issues):
        for key in ("query", "location"):
            _safe_text(scope[key], f"requested_scope.{key}", issues, required=True)
        if not isinstance(scope["basis"], str) or scope["basis"] not in {"provider_assertion", "unknown"}:
            issues.append("requested_scope.basis is unsupported.")

    observed_identity = package["observed_search_identity"]
    match_status = "unverified"
    if _shape(observed_identity, "observed_search_identity", ("query", "location", "match_assessment"), (), issues):
        observed_query = _text_observation(observed_identity["query"], "observed_search_identity.query", artifacts, issues)
        observed_location = _text_observation(observed_identity["location"], "observed_search_identity.location", artifacts, issues)
        match = observed_identity["match_assessment"]
        if _shape(match, "observed_search_identity.match_assessment", ("value", "basis"), (), issues):
            match_status = match["value"]
            if not isinstance(match_status, str) or match_status not in {"matched", "mismatched", "unverified"}:
                issues.append("identity match_assessment.value is unsupported.")
            if not isinstance(match["basis"], str) or match["basis"] not in _BASIS:
                issues.append("identity match_assessment.basis is unsupported.")
            requested_query = scope.get("query") if isinstance(scope, dict) else None
            requested_location = scope.get("location") if isinstance(scope, dict) else None
            equal = (
                isinstance(requested_query, str) and isinstance(requested_location, str)
                and isinstance(observed_query, str) and isinstance(observed_location, str)
                and requested_query.strip().casefold() == observed_query.strip().casefold()
                and requested_location.strip().casefold() == observed_location.strip().casefold()
            )
            if match_status == "matched" and not equal:
                issues.append("identity is asserted matched but supplied query/location text differs or is missing.")
            if match_status == "mismatched" and equal:
                issues.append("identity is asserted mismatched but supplied query/location text matches.")

    observations = package["observations"]
    state = PageEvidenceState.UNKNOWN
    if _shape(
        observations,
        "observations",
        ("sanitized_origin", "dom", "loading", "results", "pagination", "interstitial"),
        (),
        issues,
    ):
        origin = observations["sanitized_origin"]
        if origin is not None and not _is_sanitized_origin(origin):
            issues.append("observations.sanitized_origin must be a sanitized origin or null.")
        dom = observations["dom"]
        if _shape(dom, "observations.dom", ("excerpt", "sanitized", "basis", "evidence_refs"), (), issues):
            if dom["excerpt"] is not None:
                _safe_text(dom["excerpt"], "observations.dom.excerpt", issues)
            if not isinstance(dom["sanitized"], bool):
                issues.append("observations.dom.sanitized must be boolean.")
            if not isinstance(dom["basis"], str) or dom["basis"] not in _BASIS:
                issues.append("observations.dom.basis is unsupported.")
            _refs(dom["evidence_refs"], "observations.dom.evidence_refs", artifacts, issues)
        loading = observations["loading"]
        if _shape(loading, "observations.loading", ("state", "basis", "evidence_refs", "history"), (), issues):
            if (
                not isinstance(loading["state"], str) or loading["state"] not in _LOADING
                or not isinstance(loading["basis"], str) or loading["basis"] not in _BASIS
            ):
                issues.append("observations.loading state or basis is unsupported.")
            _refs(loading["evidence_refs"], "observations.loading.evidence_refs", artifacts, issues)
            history = loading["history"]
            if not isinstance(history, list):
                issues.append("observations.loading.history must be a list.")
            else:
                sequence_numbers = []
                history_states = []
                for index, observation in enumerate(history):
                    name = f"observations.loading.history[{index}]"
                    if _shape(observation, name, ("sequence", "state", "evidence_refs"), (), issues):
                        sequence = observation["sequence"]
                        if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 1:
                            issues.append(f"{name}.sequence must be a positive integer.")
                        else:
                            sequence_numbers.append(sequence)
                        if not isinstance(observation["state"], str) or observation["state"] not in _LOADING:
                            issues.append(f"{name}.state is unsupported.")
                        else:
                            history_states.append(observation["state"])
                        _refs(observation["evidence_refs"], f"{name}.evidence_refs", artifacts, issues, required=True)
                if sequence_numbers and sorted(sequence_numbers) != list(range(1, len(sequence_numbers) + 1)):
                    issues.append("loading history sequence must be unique and contiguous starting at 1.")
                if history_states and isinstance(loading["state"], str) and history_states[-1] != loading["state"]:
                    issues.append("loading state conflicts with the final loading-history observation.")
        results = observations["results"]
        card_count = None
        empty_observed = None
        if _shape(results, "observations.results", ("visible_card_count", "displayed_total_text", "empty_state"), (), issues):
            card_count = results["visible_card_count"]
            if card_count is not None and (not isinstance(card_count, int) or isinstance(card_count, bool) or card_count < 0):
                issues.append("visible_card_count must be a non-negative integer or null.")
            if results["displayed_total_text"] is not None:
                _safe_text(results["displayed_total_text"], "displayed_total_text", issues)
            empty = results["empty_state"]
            if _shape(empty, "observations.results.empty_state", ("observed", "basis", "evidence_refs"), (), issues):
                empty_observed = empty["observed"]
                if empty_observed is not None and not isinstance(empty_observed, bool):
                    issues.append("empty_state.observed must be boolean or null.")
                if not isinstance(empty["basis"], str) or empty["basis"] not in _BASIS:
                    issues.append("empty_state.basis is unsupported.")
                _refs(empty["evidence_refs"], "empty_state.evidence_refs", artifacts, issues)
        pagination = observations["pagination"]
        pagination_state = "unknown"
        cap = {}
        if _shape(pagination, "observations.pagination", ("state", "batches", "exhaustion_review", "cap"), (), issues):
            pagination_state = pagination["state"]
            if not isinstance(pagination_state, str) or pagination_state not in _PAGINATION:
                issues.append("pagination.state is unsupported.")
            batches = pagination["batches"]
            if not isinstance(batches, list):
                issues.append("pagination.batches must be a list.")
                batches = []
            seen_sequences = []
            for index, batch in enumerate(batches):
                name = f"pagination.batches[{index}]"
                if _shape(batch, name, ("sequence", "observation", "basis", "evidence_refs"), (), issues):
                    sequence = batch["sequence"]
                    if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 1:
                        issues.append(f"{name}.sequence must be a positive integer.")
                    else:
                        seen_sequences.append(sequence)
                    _safe_text(batch["observation"], f"{name}.observation", issues, required=True)
                    if not isinstance(batch["basis"], str) or batch["basis"] not in _BASIS:
                        issues.append(f"{name}.basis is unsupported.")
                    _refs(batch["evidence_refs"], f"{name}.evidence_refs", artifacts, issues, required=True)
            if seen_sequences and sorted(seen_sequences) != list(range(1, len(seen_sequences) + 1)):
                issues.append("pagination batch sequence must be unique and contiguous starting at 1.")
            review = pagination["exhaustion_review"]
            if _shape(review, "pagination.exhaustion_review", ("status", "method", "evidence_refs"), (), issues):
                if not isinstance(review["status"], str) or review["status"] not in {"not_reviewed", "provider_assertion", "review_recorded"}:
                    issues.append("pagination.exhaustion_review.status is unsupported.")
                if review["method"] is not None:
                    _safe_text(review["method"], "exhaustion_review.method", issues, required=True)
                _refs(review["evidence_refs"], "exhaustion_review.evidence_refs", artifacts, issues)
                if review["status"] == "review_recorded" and (not review["method"] or not review["evidence_refs"]):
                    issues.append("recorded exhaustion review requires a method and evidence reference.")
            cap = pagination["cap"]
            if _shape(cap, "pagination.cap", ("reached", "prevented_exhaustion"), (), issues):
                for key in ("reached", "prevented_exhaustion"):
                    if cap[key] is not None and not isinstance(cap[key], bool):
                        issues.append(f"pagination.cap.{key} must be boolean or null.")
            if pagination_state == "more_batches_observed" and not batches:
                issues.append("more_batches_observed requires at least one documented batch observation.")
            if pagination_state == "terminal_condition_observed" and batches:
                issues.append("terminal pagination conflicts with additional batch observations.")
        interstitial = observations["interstitial"]
        interstitial_observed = None
        if _shape(interstitial, "observations.interstitial", ("observed", "kind", "basis", "evidence_refs"), (), issues):
            interstitial_observed = interstitial["observed"]
            if interstitial_observed is not None and not isinstance(interstitial_observed, bool):
                issues.append("interstitial.observed must be boolean or null.")
            if interstitial["kind"] is not None:
                _safe_text(interstitial["kind"], "interstitial.kind", issues)
            if not isinstance(interstitial["basis"], str) or interstitial["basis"] not in _BASIS:
                issues.append("interstitial.basis is unsupported.")
            _refs(interstitial["evidence_refs"], "interstitial.evidence_refs", artifacts, issues)

        interpretation = package["interpretations"]
        if _shape(interpretation, "interpretations", ("observed_state", "claims"), (), issues):
            label = interpretation["observed_state"]
            if not isinstance(label, str) or label not in _STATES:
                issues.append("interpretations.observed_state is unsupported.")
            else:
                state = PageEvidenceState(label)
            claims = interpretation["claims"]
            if not isinstance(claims, list):
                issues.append("interpretations.claims must be a list.")
            else:
                for index, claim in enumerate(claims):
                    name = f"interpretations.claims[{index}]"
                    if _shape(claim, name, ("text", "basis", "evidence_refs"), (), issues):
                        _safe_text(claim["text"], f"{name}.text", issues, required=True)
                        if not isinstance(claim["basis"], str) or claim["basis"] not in {"derived", "provider_assertion", "unknown"}:
                            issues.append(f"{name}.basis must be derived, provider_assertion, or unknown.")
                        _refs(claim["evidence_refs"], f"{name}.evidence_refs", artifacts, issues)

        _validate_candidate_processing(package["candidate_processing"], scope, package["artifacts"], issues)
        _validate_privacy(package["privacy_review"], package["artifacts"], issues)
        _validate_limitations(package["limitations"], issues)
        _validate_state_requirements(
            state, scope, observed_identity, match_status, observations, artifacts,
            provenance, issues,
        )

    valid = not issues
    return PackageValidation(
        valid=valid,
        observed_state=state if valid else PageEvidenceState.UNKNOWN,
        issues=tuple(issues),
    )


def _validate_privacy(value, artifacts, issues):
    if not _shape(value, "privacy_review", ("status", "redactions_made", "heuristic_scan", "notes"), (), issues):
        return
    if not isinstance(value["status"], str) or value["status"] not in {"reviewed", "not_reviewed", "unknown"}:
        issues.append("privacy_review.status is unsupported.")
    elif value["status"] != "reviewed":
        issues.append("privacy_review must record a completed redaction review.")
    if not isinstance(value["heuristic_scan"], str) or value["heuristic_scan"] not in {"not_run", "matches_flagged", "no_matches_found"}:
        issues.append("privacy_review.heuristic_scan is unsupported.")
    for key in ("redactions_made", "notes"):
        items = value[key]
        if not isinstance(items, list):
            issues.append(f"privacy_review.{key} must be a list.")
        else:
            for index, item in enumerate(items):
                _safe_text(item, f"privacy_review.{key}[{index}]", issues, required=True)
    if value["heuristic_scan"] == "matches_flagged":
        issues.append("privacy_review records sensitive-looking content that requires redaction review.")
    if value["heuristic_scan"] == "not_run":
        issues.append("privacy_review must record the heuristic scan outcome.")
    for key in ("dom_snapshot", "screenshot"):
        item = artifacts.get(key) if isinstance(artifacts, dict) else None
        if isinstance(item, dict) and item.get("redaction_review") != "reviewed":
            issues.append(f"artifacts.{key} requires a recorded redaction review.")


def _validate_limitations(value, issues):
    if not isinstance(value, list) or not value:
        issues.append("limitations must be a non-empty list.")
        return
    for index, item in enumerate(value):
        _safe_text(item, f"limitations[{index}]", issues, required=True)


def _validate_state_requirements(state, scope, identity, match_status, observations, artifacts, provenance, issues):
    if not isinstance(observations, dict):
        return
    loading = observations.get("loading") if isinstance(observations.get("loading"), dict) else {}
    results = observations.get("results") if isinstance(observations.get("results"), dict) else {}
    pagination = observations.get("pagination") if isinstance(observations.get("pagination"), dict) else {}
    interstitial = observations.get("interstitial") if isinstance(observations.get("interstitial"), dict) else {}
    card_count = results.get("visible_card_count")
    empty = results.get("empty_state") if isinstance(results.get("empty_state"), dict) else {}
    batches = pagination.get("batches") if isinstance(pagination.get("batches"), list) else []

    def direct_refs(value, field):
        if isinstance(value, dict):
            if value.get("basis") != "direct_observation":
                issues.append(f"{field} must be recorded as a direct observation.")
            _refs(value.get("evidence_refs"), field, artifacts, issues, required=True)

    if state in {
        PageEvidenceState.POPULATED_RESULTS_SETTLED,
        PageEvidenceState.LEGITIMATE_EMPTY,
        PageEvidenceState.POPULATED_MORE_PAGINATION,
        PageEvidenceState.EXHAUSTION_REVIEW_RECORDED,
    }:
        if not isinstance(scope, dict) or not scope.get("query") or not scope.get("location"):
            issues.append("this state requires requested query and location.")
        if match_status != "matched":
            issues.append("this state requires a recorded matched query/location assessment.")
        if not isinstance(identity, dict):
            issues.append("this state requires observed query/location evidence.")
        else:
            for key in ("query", "location"):
                item = identity.get(key)
                if not isinstance(item, dict) or not item.get("value"):
                    issues.append(f"this state requires an observed {key} value.")
                direct_refs(item, f"observed identity {key} evidence")
        if loading.get("state") != "settled":
            issues.append("this state requires a settled loading observation.")
        direct_refs(loading, "loading evidence")
        dom = observations.get("dom") if isinstance(observations.get("dom"), dict) else {}
        if dom.get("sanitized") is not True:
            issues.append("search-state evidence requires a recorded sanitized DOM artifact.")
        direct_refs(dom, "DOM evidence")
        if interstitial.get("observed") is True:
            issues.append("search-results state conflicts with an observed interstitial.")

    if state in {PageEvidenceState.POPULATED_RESULTS_SETTLED, PageEvidenceState.POPULATED_MORE_PAGINATION} and (
        not isinstance(card_count, int) or isinstance(card_count, bool) or card_count <= 0
    ):
        issues.append("populated state requires a positive visible card count.")
    if state == PageEvidenceState.LEGITIMATE_EMPTY:
        if card_count != 0 or empty.get("observed") is not True:
            issues.append("legitimate empty requires zero cards and an observed empty state.")
        direct_refs(empty, "empty-state evidence")
        if pagination.get("state") == "more_batches_observed":
            issues.append("legitimate empty conflicts with observed additional batches.")
    if state == PageEvidenceState.LOADING_OR_UNSETTLED:
        if loading.get("state") not in {"loading", "unsettled", "conflicting"}:
            issues.append("loading state requires loading, unsettled, or conflicting evidence.")
        direct_refs(loading, "loading evidence")
    if state == PageEvidenceState.AUTHENTICATION_OR_INTERSTITIAL:
        if interstitial.get("observed") is not True or not isinstance(interstitial.get("kind"), str) or not interstitial["kind"].strip():
            issues.append("interstitial state requires an observed, specifically described interstitial.")
        direct_refs(interstitial, "interstitial evidence")
    if state == PageEvidenceState.POPULATED_MORE_PAGINATION:
        if pagination.get("state") != "more_batches_observed" or not batches:
            issues.append("additional-pagination state requires observed additional batches.")
    if isinstance(card_count, int) and not isinstance(card_count, bool) and card_count > 0 and empty.get("observed") is True:
        issues.append("positive visible-card evidence conflicts with an observed empty state.")
    if state == PageEvidenceState.EXHAUSTION_REVIEW_RECORDED:
        if not isinstance(card_count, int) or isinstance(card_count, bool) or card_count < 0:
            issues.append("exhaustion state requires a non-negative visible card count.")
        review = pagination.get("exhaustion_review") if isinstance(pagination.get("exhaustion_review"), dict) else {}
        if pagination.get("state") != "terminal_condition_observed" or review.get("status") != "review_recorded":
            issues.append("exhaustion state requires a terminal observation and recorded independent review.")
        verification = provenance.get("independent_verification", {}) if isinstance(provenance, dict) else {}
        if not isinstance(verification, dict) or verification.get("status") != "review_recorded":
            issues.append("exhaustion requires a recorded independent-review assertion.")
        reviewed_claims = verification.get("reviewed_claims") if isinstance(verification, dict) else None
        if not isinstance(reviewed_claims, list) or "pagination_exhaustion" not in reviewed_claims:
            issues.append("independent verification must list pagination_exhaustion as a reviewed claim.")
        if batches:
            issues.append("exhaustion conflicts with observed additional batches.")
        cap = pagination.get("cap") if isinstance(pagination.get("cap"), dict) else {}
        if not isinstance(cap.get("reached"), bool) or not isinstance(cap.get("prevented_exhaustion"), bool):
            issues.append("exhaustion requires explicit cap and cap-impact observations.")
        elif cap["prevented_exhaustion"] is True or (cap["reached"] is True and cap["prevented_exhaustion"] is not False):
            issues.append("a cap that may have prevented exhaustion conflicts with exhaustion.")
