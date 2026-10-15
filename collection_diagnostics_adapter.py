"""One-way mapping of sanitized collector diagnostics to the canonical model.

The production collector may use this adapter for in-memory diagnostic
classification. It copies recorded values only; it does not inspect a page,
read an artifact, infer a search state, authorize publication, or create
completion evidence that the collector did not record.
"""

from collection_run_evidence import (
    CandidateDisposition,
    CandidateEvidence,
    CandidateProcessingStatus,
    CandidateReason,
    CollectionRunEvidence,
    ScopeEvidence,
    SearchScope,
)


_MISSING = object()

_REASONS = {
    "CLOSED_JOB": CandidateReason.CLOSED_JOB,
    "OUTSIDE_TARGET_LOCATION": CandidateReason.OUTSIDE_TARGET_LOCATION,
    "NOT_EASY_APPLY": CandidateReason.NOT_EASY_APPLY,
    "PROCESSING_ERROR": CandidateReason.PROCESSING_ERROR,
    "OTHER_FILTER": CandidateReason.OTHER_FILTER,
    "DUPLICATE_WITHIN_SCOPE": CandidateReason.DUPLICATE_WITHIN_SCOPE,
    "DUPLICATE_ACROSS_SCOPES": CandidateReason.DUPLICATE_ACROSS_SCOPES,
}


def _read(value, name, default=_MISSING):
    try:
        return getattr(value, name)
    except Exception:
        return default


def _status_value(value):
    if isinstance(value, str):
        return value
    return _read(value, "value", None)


def _map_candidate(source, scope_id):
    candidate_id = _read(source, "candidate_id")
    sequence = _read(source, "discovery_sequence")
    status_value = _read(source, "processing_status")
    disposition_value = _read(source, "disposition")
    reason_value = _read(source, "reason_code")
    duplicate_scope = _read(source, "duplicate_of_scope_id")
    duplicate_sequence = _read(source, "duplicate_of_sequence")

    try:
        status = CandidateProcessingStatus(status_value)
    except (TypeError, ValueError):
        status = CandidateProcessingStatus.UNKNOWN

    reason = _REASONS.get(reason_value) if isinstance(reason_value, str) else None
    output_duplicate = (
        disposition_value == "DUPLICATE"
        and reason is CandidateReason.DUPLICATE_ACROSS_SCOPES
        and status is CandidateProcessingStatus.DUPLICATE
    )
    if output_duplicate:
        # The collector's global dedup branch skips detail-page processing for
        # this scope. Keep that scope disposition explicitly unprocessed while
        # storing the output-level dedup link in separate fields.
        status = CandidateProcessingStatus.PENDING
        disposition = CandidateDisposition.UNPROCESSED
    elif disposition_value == "DUPLICATE":
        disposition = CandidateDisposition.DUPLICATE
    elif disposition_value == "QUALIFYING" and status is CandidateProcessingStatus.PROCESSED:
        disposition = CandidateDisposition.QUALIFYING
    elif disposition_value == "FILTERED" and status is CandidateProcessingStatus.PROCESSED:
        disposition = CandidateDisposition.FILTERED
    elif disposition_value == "FAILED_PROCESSING" and status is CandidateProcessingStatus.FAILED:
        disposition = CandidateDisposition.FAILED_PROCESSING
    elif disposition_value is None and status in {
        CandidateProcessingStatus.DISCOVERED,
        CandidateProcessingStatus.PENDING,
    }:
        disposition = CandidateDisposition.UNPROCESSED
    else:
        disposition = CandidateDisposition.UNKNOWN

    return CandidateEvidence(
        candidate_id=candidate_id,
        disposition=disposition,
        reason=reason,
        source_scope_id=scope_id,
        discovery_sequence=sequence,
        processing_status=status,
        duplicate_of_sequence=None if output_duplicate else duplicate_sequence,
        output_deduplicated=True if output_duplicate else None,
        output_duplicate_of_scope_id=duplicate_scope if output_duplicate else None,
        output_duplicate_of_sequence=duplicate_sequence if output_duplicate else None,
    )


def _map_scope(diagnostic):
    keyword = _read(diagnostic, "keyword")
    location = _read(diagnostic, "location")
    scope_id = _read(diagnostic, "scope_id")
    scope = SearchScope(keyword, location, scope_id)

    raw_candidates = _read(diagnostic, "candidate_occurrences")
    if isinstance(raw_candidates, tuple):
        candidates = tuple(_map_candidate(item, scope_id) for item in raw_candidates)
        occurrence_count = len(candidates)
    else:
        candidates = ()
        occurrence_count = None

    candidate_ids = _read(diagnostic, "candidate_ids")
    reported_count = _read(diagnostic, "extracted_link_count")

    error_names = (
        "selector_error_count",
        "parser_error_count",
        "navigation_failure_count",
        "scroll_failures",
        "candidate_page_failure_count",
    )
    error_values = tuple(_read(diagnostic, name) for name in error_names)
    if all(
        isinstance(value, int) and not isinstance(value, bool) and value >= 0
        for value in error_values
    ):
        unresolved_errors = sum(error_values)
    else:
        unresolved_errors = -1

    cap_values = (
        _read(diagnostic, "per_search_cap_reached"),
        _read(diagnostic, "global_cap_reached"),
    )
    caps_valid = all(isinstance(value, bool) for value in cap_values)
    cap_reached = any(cap_values) if caps_valid else None
    cap_stopped = False if caps_valid and not cap_reached else None

    qualifying_count = sum(
        candidate.disposition is CandidateDisposition.QUALIFYING
        for candidate in candidates
    )

    return ScopeEvidence(
        scope=scope,
        # Current collector diagnostics contain only a sanitized origin, not
        # independently observed keyword/location values from the result page.
        observed_scope=None,
        page_state=None,
        pagination=None,
        unresolved_error_count=unresolved_errors,
        identity_verified=None,
        results_settled=None,
        exhaustion_verified=None,
        filters_applied=None,
        cap_reached=cap_reached,
        cap_stopped_before_exhaustion=cap_stopped,
        discovered_candidate_count=occurrence_count,
        qualifying_candidate_count=qualifying_count if occurrence_count is not None else None,
        candidates=candidates,
        scope_attempted=_read(diagnostic, "search_attempted"),
        candidate_identity_ids=candidate_ids,
        reported_candidate_identity_count=reported_count,
        scope_sequence=_read(diagnostic, "scope_sequence"),
    )


def adapt_collection_outcome(outcome, requested_scopes):
    """Translate an outcome into canonical evidence without upgrading its status.

    ``requested_scopes`` must be supplied by the caller. The adapter never
    reconstructs the required scope set from observed diagnostics, since doing
    so would hide omitted scopes.
    """
    raw_diagnostics = _read(outcome, "search_diagnostics")
    if isinstance(raw_diagnostics, tuple):
        scopes = tuple(_map_scope(item) for item in raw_diagnostics)
    else:
        scopes = raw_diagnostics

    raw_issues = _read(outcome, "issues")
    if isinstance(raw_issues, (tuple, list)):
        run_errors = len(raw_issues)
    else:
        run_errors = -1

    return CollectionRunEvidence(
        requested_scopes=requested_scopes,
        scopes=scopes,
        fatal_failure=_status_value(_read(outcome, "status")) == "FAILED",
        unresolved_error_count=run_errors,
    )

