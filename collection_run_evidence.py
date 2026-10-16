"""Pure offline policy model for multi-scope collection evidence.

This module models explicit evidence only. It does not inspect pages, run a
collector, or publish data, and it is intentionally independent of production
collection and application modules.
"""

from dataclasses import dataclass
from enum import Enum


class CollectionStatus(str, Enum):
    COMPLETE = "COMPLETE"
    COMPLETE_EMPTY = "COMPLETE_EMPTY"
    INCOMPLETE = "INCOMPLETE"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


class PageEvidenceState(str, Enum):
    POPULATED_RESULTS_SETTLED = "POPULATED_RESULTS_SETTLED"
    LEGITIMATE_EMPTY = "LEGITIMATE_EMPTY"
    LOADING_OR_UNSETTLED = "LOADING_OR_UNSETTLED"
    AUTHENTICATION_REQUIRED = "AUTHENTICATION_REQUIRED"
    CHALLENGE_OR_INTERSTITIAL = "CHALLENGE_OR_INTERSTITIAL"
    NAVIGATION_ERROR = "NAVIGATION_ERROR"
    PARSING_ERROR = "PARSING_ERROR"
    PAGINATION_BATCH_FAILED = "PAGINATION_BATCH_FAILED"
    POPULATED_MORE_PAGINATION = "POPULATED_MORE_PAGINATION"
    EXHAUSTION_REVIEW_RECORDED = "EXHAUSTION_REVIEW_RECORDED"
    UNKNOWN = "UNKNOWN"


class CandidateDisposition(str, Enum):
    QUALIFYING = "QUALIFYING"
    FILTERED = "FILTERED"
    UNPROCESSED = "UNPROCESSED"
    FAILED_PROCESSING = "FAILED_PROCESSING"
    DUPLICATE = "DUPLICATE"
    UNKNOWN = "UNKNOWN"


class CandidateProcessingStatus(str, Enum):
    DISCOVERED = "DISCOVERED"
    PENDING = "PENDING"
    PROCESSED = "PROCESSED"
    FAILED = "FAILED"
    DUPLICATE = "DUPLICATE"
    UNKNOWN = "UNKNOWN"


class CandidateReason(str, Enum):
    """Non-sensitive reason codes for candidate accounting."""

    CLOSED_JOB = "CLOSED_JOB"
    OUTSIDE_TARGET_LOCATION = "OUTSIDE_TARGET_LOCATION"
    NOT_EASY_APPLY = "NOT_EASY_APPLY"
    OTHER_FILTER = "OTHER_FILTER"
    PROCESSING_ERROR = "PROCESSING_ERROR"
    DUPLICATE_WITHIN_SCOPE = "DUPLICATE_WITHIN_SCOPE"
    DUPLICATE_ACROSS_SCOPES = "DUPLICATE_ACROSS_SCOPES"


class PaginationBatchStatus(str, Enum):
    OBSERVED = "OBSERVED"
    FAILED = "FAILED"


class PaginationObservationState(str, Enum):
    MORE_BATCHES_OBSERVED = "more_batches_observed"
    TERMINAL_CONDITION_OBSERVED = "terminal_condition_observed"
    FAILED_BATCH = "failed_batch"
    NOT_OBSERVED = "not_observed"
    UNKNOWN = "unknown"


class PaginationState(str, Enum):
    TERMINAL_VERIFIED = "TERMINAL_VERIFIED"
    MORE_AVAILABLE = "MORE_AVAILABLE"
    INCOMPLETE = "INCOMPLETE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class SearchScope:
    """One explicitly requested keyword/location scope."""

    keyword: str
    location: str
    scope_id: str | None = None


@dataclass(frozen=True)
class CandidateEvidence:
    """One ordered candidate occurrence within its explicitly named scope."""

    candidate_id: str
    disposition: CandidateDisposition | None
    reason: CandidateReason | None = None
    source_scope_id: str | None = None
    discovery_sequence: int | None = None
    processing_status: CandidateProcessingStatus | None = None
    duplicate_of_sequence: int | None = None
    output_deduplicated: bool | None = None
    output_duplicate_of_scope_id: str | None = None
    output_duplicate_of_sequence: int | None = None


@dataclass(frozen=True)
class PaginationBatchEvidence:
    """A batch observation; references are supplied assertions, not verified files."""

    sequence: int
    status: PaginationBatchStatus
    more_indicated: bool | None
    evidence_refs: tuple = ()
    terminal_evidence_refs: tuple = ()


@dataclass(frozen=True)
class PaginationEvidence:
    """Ordered batch evidence and explicit cap impact for one search scope."""

    batches: tuple
    cap_reached: bool | None
    cap_prevented_exhaustion: bool | None


@dataclass(frozen=True)
class ScopeEvidence:
    """Evidence recorded for one requested search scope."""

    scope: SearchScope
    observed_scope: SearchScope | None = None
    identity_evidence_refs: tuple = ()
    identity_basis: str | None = None
    page_state: PageEvidenceState | None = None
    page_state_evidence_refs: tuple = ()
    page_state_basis: str | None = None
    pagination: PaginationEvidence | None = None
    fatal_failure: bool = False
    unresolved_error_count: int = 0
    identity_verified: bool | None = None
    results_settled: bool | None = None
    exhaustion_verified: bool | None = None
    filters_applied: bool | None = None
    cap_reached: bool | None = None
    cap_stopped_before_exhaustion: bool | None = None
    discovered_candidate_count: int | None = None
    qualifying_candidate_count: int | None = None
    candidates: tuple = ()
    scope_attempted: bool | None = None
    candidate_identity_ids: tuple | None = None
    reported_candidate_identity_count: int | None = None
    scope_sequence: int | None = None


@dataclass(frozen=True)
class CollectionRunEvidence:
    """The requested scope set and its explicit per-scope evidence."""

    requested_scopes: tuple
    scopes: tuple
    fatal_failure: bool = False
    unresolved_error_count: int = 0


def _nonnegative_integer(value):
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _valid_scope(scope):
    return (
        isinstance(scope, SearchScope)
        and isinstance(scope.keyword, str)
        and bool(scope.keyword.strip())
        and isinstance(scope.location, str)
        and bool(scope.location.strip())
        and isinstance(scope.scope_id, str)
        and bool(scope.scope_id.strip())
    )


def _scope_identity(scope):
    return scope.keyword.strip().casefold(), scope.location.strip().casefold()


def classify_pagination_evidence(evidence):
    """Classify an ordered batch ledger without treating an absent control as terminal."""
    if not isinstance(evidence, PaginationEvidence) or not isinstance(evidence.batches, tuple):
        return PaginationState.UNKNOWN
    if (
        evidence.cap_reached is not None
        and not isinstance(evidence.cap_reached, bool)
    ) or (
        evidence.cap_prevented_exhaustion is not None
        and not isinstance(evidence.cap_prevented_exhaustion, bool)
    ):
        return PaginationState.UNKNOWN
    if not evidence.batches:
        return PaginationState.UNKNOWN

    sequences = []
    for batch in evidence.batches:
        if not isinstance(batch, PaginationBatchEvidence):
            return PaginationState.UNKNOWN
        if not _positive_integer(batch.sequence):
            return PaginationState.UNKNOWN
        sequences.append(batch.sequence)
        if not isinstance(batch.status, PaginationBatchStatus):
            return PaginationState.UNKNOWN
        if batch.status is PaginationBatchStatus.FAILED:
            return PaginationState.INCOMPLETE
        if batch.status is not PaginationBatchStatus.OBSERVED:
            return PaginationState.UNKNOWN
        if not isinstance(batch.more_indicated, bool):
            return PaginationState.UNKNOWN
        if not _nonempty_reference_tuple(batch.evidence_refs):
            return PaginationState.UNKNOWN
        if not isinstance(batch.terminal_evidence_refs, tuple) or any(
            not isinstance(ref, str) or not ref.strip()
            for ref in batch.terminal_evidence_refs
        ):
            return PaginationState.UNKNOWN

    if len(sequences) != len(set(sequences)):
        return PaginationState.UNKNOWN
    if sorted(sequences) != list(range(1, len(sequences) + 1)):
        return PaginationState.INCOMPLETE
    if sequences != list(range(1, len(sequences) + 1)):
        return PaginationState.UNKNOWN

    for previous, following in zip(evidence.batches, evidence.batches[1:]):
        if previous.more_indicated is not True:
            return PaginationState.UNKNOWN
        if following.sequence != previous.sequence + 1:
            return PaginationState.INCOMPLETE

    last = evidence.batches[-1]
    if last.more_indicated is True:
        return PaginationState.INCOMPLETE
    if not last.terminal_evidence_refs:
        return PaginationState.UNKNOWN
    if evidence.cap_reached is None or evidence.cap_prevented_exhaustion is None:
        return PaginationState.UNKNOWN
    if evidence.cap_reached is True and evidence.cap_prevented_exhaustion is not False:
        return PaginationState.INCOMPLETE
    if evidence.cap_prevented_exhaustion is True:
        return PaginationState.INCOMPLETE
    return PaginationState.TERMINAL_VERIFIED


def _positive_integer(value):
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _nonempty_reference_tuple(value):
    return (
        isinstance(value, tuple)
        and bool(value)
        and all(isinstance(ref, str) and ref.strip() for ref in value)
    )


def _known_scope_incomplete(evidence):
    """Return whether valid evidence positively records unfinished work."""
    if not isinstance(evidence, ScopeEvidence):
        return False
    if evidence.fatal_failure is True:
        return False
    if evidence.scope_attempted is False:
        return True
    if isinstance(evidence.page_state, PageEvidenceState) and evidence.page_state in {
        PageEvidenceState.LOADING_OR_UNSETTLED,
        PageEvidenceState.AUTHENTICATION_REQUIRED,
        PageEvidenceState.CHALLENGE_OR_INTERSTITIAL,
        PageEvidenceState.PARSING_ERROR,
        PageEvidenceState.PAGINATION_BATCH_FAILED,
        PageEvidenceState.POPULATED_MORE_PAGINATION,
    }:
        return True
    if classify_pagination_evidence(evidence.pagination) is PaginationState.INCOMPLETE:
        return True
    if (
        _nonnegative_integer(evidence.unresolved_error_count)
        and evidence.unresolved_error_count > 0
    ):
        return True
    if any(
        value is False
        for value in (
            evidence.identity_verified,
            evidence.results_settled,
            evidence.exhaustion_verified,
            evidence.filters_applied,
        )
    ):
        return True
    if isinstance(evidence.candidates, tuple) and any(
        isinstance(candidate, CandidateEvidence)
        and candidate.disposition is CandidateDisposition.UNPROCESSED
        for candidate in evidence.candidates
    ):
        return True
    if (
        _nonnegative_integer(evidence.discovered_candidate_count)
        and isinstance(evidence.candidates, tuple)
        and evidence.discovered_candidate_count > len(evidence.candidates)
    ):
        return True
    if (
        evidence.cap_reached is True
        and evidence.cap_stopped_before_exhaustion is True
        and evidence.exhaustion_verified is not True
    ):
        return True
    return False


def classify_scope_evidence(evidence):
    """Classify one scope conservatively without manufacturing evidence."""
    if not isinstance(evidence, ScopeEvidence):
        return CollectionStatus.UNKNOWN

    if evidence.fatal_failure is True:
        return CollectionStatus.FAILED
    if evidence.scope_attempted is False:
        return CollectionStatus.INCOMPLETE
    if evidence.page_state is PageEvidenceState.NAVIGATION_ERROR:
        return CollectionStatus.FAILED
    if _known_scope_incomplete(evidence):
        return CollectionStatus.INCOMPLETE
    if not isinstance(evidence.fatal_failure, bool):
        return CollectionStatus.UNKNOWN
    if evidence.scope_attempted is not None and not isinstance(evidence.scope_attempted, bool):
        return CollectionStatus.UNKNOWN

    if not _valid_scope(evidence.scope):
        return CollectionStatus.UNKNOWN
    if not _valid_scope(evidence.observed_scope):
        return CollectionStatus.UNKNOWN
    if (
        evidence.scope.scope_id != evidence.observed_scope.scope_id
        or _scope_identity(evidence.scope) != _scope_identity(evidence.observed_scope)
        or evidence.identity_verified is not True
        or evidence.identity_basis != "direct_observation"
        or not _nonempty_reference_tuple(evidence.identity_evidence_refs)
    ):
        return CollectionStatus.UNKNOWN
    if not isinstance(evidence.page_state, PageEvidenceState):
        return CollectionStatus.UNKNOWN
    if evidence.page_state_basis != "direct_observation" or not _nonempty_reference_tuple(
        evidence.page_state_evidence_refs
    ):
        return CollectionStatus.UNKNOWN
    if evidence.page_state not in {
        PageEvidenceState.POPULATED_RESULTS_SETTLED,
        PageEvidenceState.LEGITIMATE_EMPTY,
        PageEvidenceState.EXHAUSTION_REVIEW_RECORDED,
    }:
        return CollectionStatus.UNKNOWN
    if not _nonnegative_integer(evidence.unresolved_error_count):
        return CollectionStatus.UNKNOWN

    required_flags = (
        evidence.identity_verified,
        evidence.results_settled,
        evidence.exhaustion_verified,
        evidence.filters_applied,
        evidence.cap_reached,
        evidence.cap_stopped_before_exhaustion,
    )
    if any(value is not None and not isinstance(value, bool) for value in required_flags):
        return CollectionStatus.UNKNOWN

    if (
        evidence.cap_stopped_before_exhaustion is True
        and (
            evidence.cap_reached is not True
            or evidence.exhaustion_verified is True
        )
    ):
        return CollectionStatus.UNKNOWN
    if evidence.cap_reached is True and evidence.cap_stopped_before_exhaustion is None:
        return CollectionStatus.UNKNOWN

    if not isinstance(evidence.candidates, tuple):
        return CollectionStatus.UNKNOWN
    if any(not isinstance(item, CandidateEvidence) for item in evidence.candidates):
        return CollectionStatus.UNKNOWN

    sequence_values = []
    candidate_occurrences = {}
    qualifying_dispositions = 0
    for index, candidate in enumerate(evidence.candidates, start=1):
        if not isinstance(candidate.candidate_id, str) or not candidate.candidate_id.strip():
            return CollectionStatus.UNKNOWN
        if candidate.source_scope_id != evidence.scope.scope_id:
            return CollectionStatus.UNKNOWN
        if not _positive_integer(candidate.discovery_sequence):
            return CollectionStatus.UNKNOWN
        if (
            candidate.disposition is not None
            and not isinstance(candidate.disposition, CandidateDisposition)
        ) or (
            candidate.processing_status is not None
            and not isinstance(candidate.processing_status, CandidateProcessingStatus)
        ) or (
            candidate.reason is not None
            and not isinstance(candidate.reason, CandidateReason)
        ):
            return CollectionStatus.UNKNOWN
        sequence_values.append(candidate.discovery_sequence)
        previous_sequence = candidate_occurrences.get(candidate.candidate_id)
        if (
            candidate.processing_status is CandidateProcessingStatus.DISCOVERED
            or candidate.processing_status is CandidateProcessingStatus.PENDING
            or candidate.disposition is CandidateDisposition.UNPROCESSED
        ):
            return CollectionStatus.INCOMPLETE
        if candidate.processing_status is CandidateProcessingStatus.FAILED or candidate.disposition is CandidateDisposition.FAILED_PROCESSING:
            if (
                candidate.processing_status is CandidateProcessingStatus.FAILED
                and candidate.disposition is CandidateDisposition.FAILED_PROCESSING
                and candidate.reason is CandidateReason.PROCESSING_ERROR
            ):
                return CollectionStatus.INCOMPLETE
            return CollectionStatus.UNKNOWN
        if not isinstance(candidate.processing_status, CandidateProcessingStatus):
            return CollectionStatus.UNKNOWN
        if candidate.disposition is CandidateDisposition.DUPLICATE:
            if candidate.reason is CandidateReason.DUPLICATE_ACROSS_SCOPES:
                # A scope-level classifier cannot validate a cross-scope target.
                # The run classifier validates the reference and preserves the
                # occurrence as known unprocessed work.
                return CollectionStatus.UNKNOWN
            if (
                candidate.processing_status is not CandidateProcessingStatus.DUPLICATE
                or previous_sequence is None
                or candidate.duplicate_of_sequence != previous_sequence
                or candidate.reason is not CandidateReason.DUPLICATE_WITHIN_SCOPE
                or any(
                    value is not None
                    for value in (
                        candidate.output_deduplicated,
                        candidate.output_duplicate_of_scope_id,
                        candidate.output_duplicate_of_sequence,
                    )
                )
            ):
                return CollectionStatus.UNKNOWN
            continue
        if previous_sequence is not None:
            return CollectionStatus.UNKNOWN
        if candidate.duplicate_of_sequence is not None or any(
            value is not None
            for value in (
                candidate.output_deduplicated,
                candidate.output_duplicate_of_scope_id,
                candidate.output_duplicate_of_sequence,
            )
        ):
            return CollectionStatus.UNKNOWN
        if candidate.processing_status is not CandidateProcessingStatus.PROCESSED:
            return CollectionStatus.UNKNOWN
        if candidate.disposition not in (
            CandidateDisposition.QUALIFYING,
            CandidateDisposition.FILTERED,
        ):
            return CollectionStatus.UNKNOWN
        if candidate.disposition is CandidateDisposition.FILTERED:
            if not isinstance(candidate.reason, CandidateReason) or candidate.reason not in {
                CandidateReason.CLOSED_JOB,
                CandidateReason.OUTSIDE_TARGET_LOCATION,
                CandidateReason.NOT_EASY_APPLY,
                CandidateReason.OTHER_FILTER,
            }:
                return CollectionStatus.UNKNOWN
        elif candidate.reason is not None:
            return CollectionStatus.UNKNOWN
        if candidate.disposition is CandidateDisposition.QUALIFYING:
            qualifying_dispositions += 1
        candidate_occurrences[candidate.candidate_id] = candidate.discovery_sequence

    if len(sequence_values) != len(set(sequence_values)):
        return CollectionStatus.UNKNOWN
    if sorted(sequence_values) != list(range(1, len(sequence_values) + 1)):
        if sequence_values and max(sequence_values) > len(sequence_values):
            return CollectionStatus.INCOMPLETE
        return CollectionStatus.UNKNOWN
    if sequence_values != list(range(1, len(sequence_values) + 1)):
        return CollectionStatus.UNKNOWN

    discovered_count = evidence.discovered_candidate_count
    qualifying_count = evidence.qualifying_candidate_count
    if discovered_count is not None and not _nonnegative_integer(discovered_count):
        return CollectionStatus.UNKNOWN
    if qualifying_count is not None and not _nonnegative_integer(qualifying_count):
        return CollectionStatus.UNKNOWN
    if discovered_count is None or qualifying_count is None:
        return CollectionStatus.UNKNOWN
    if discovered_count > len(evidence.candidates):
        return CollectionStatus.INCOMPLETE
    if discovered_count != len(evidence.candidates):
        return CollectionStatus.UNKNOWN
    if qualifying_count != qualifying_dispositions:
        return CollectionStatus.UNKNOWN

    if evidence.candidate_identity_ids is not None:
        if (
            not isinstance(evidence.candidate_identity_ids, tuple)
            or any(not isinstance(item, str) or not item.strip() for item in evidence.candidate_identity_ids)
            or len(evidence.candidate_identity_ids) != len(set(evidence.candidate_identity_ids))
            or evidence.candidate_identity_ids
            != tuple(dict.fromkeys(candidate.candidate_id for candidate in evidence.candidates))
        ):
            return CollectionStatus.UNKNOWN
        if (
            not _nonnegative_integer(evidence.reported_candidate_identity_count)
            or evidence.reported_candidate_identity_count != len(evidence.candidate_identity_ids)
        ):
            return CollectionStatus.UNKNOWN
    elif evidence.reported_candidate_identity_count is not None:
        return CollectionStatus.UNKNOWN

    pagination_state = classify_pagination_evidence(evidence.pagination)
    if pagination_state is PaginationState.INCOMPLETE:
        return CollectionStatus.INCOMPLETE
    if pagination_state is not PaginationState.TERMINAL_VERIFIED:
        return CollectionStatus.UNKNOWN
    if evidence.exhaustion_verified is not True:
        return CollectionStatus.UNKNOWN
    pagination = evidence.pagination
    if (
        evidence.cap_reached != pagination.cap_reached
        or evidence.cap_stopped_before_exhaustion != pagination.cap_prevented_exhaustion
    ):
        return CollectionStatus.UNKNOWN

    if evidence.results_settled is not True:
        return CollectionStatus.UNKNOWN
    if discovered_count == 0 and evidence.page_state is not PageEvidenceState.LEGITIMATE_EMPTY:
        return CollectionStatus.UNKNOWN
    if evidence.page_state is PageEvidenceState.LEGITIMATE_EMPTY and discovered_count != 0:
        return CollectionStatus.UNKNOWN

    if any(value is None for value in required_flags):
        return CollectionStatus.UNKNOWN
    if evidence.cap_stopped_before_exhaustion is True:
        return CollectionStatus.INCOMPLETE

    if qualifying_count == 0:
        return CollectionStatus.COMPLETE_EMPTY
    return CollectionStatus.COMPLETE


def classify_collection_run(evidence):
    """Aggregate a multi-scope run using FAILED > INCOMPLETE > UNKNOWN."""
    if not isinstance(evidence, CollectionRunEvidence):
        return CollectionStatus.UNKNOWN

    if evidence.fatal_failure is True:
        return CollectionStatus.FAILED

    scope_records = evidence.scopes if isinstance(evidence.scopes, tuple) else ()
    if any(
        isinstance(scope, ScopeEvidence)
        and (
            scope.fatal_failure is True
            or scope.page_state is PageEvidenceState.NAVIGATION_ERROR
        )
        for scope in scope_records
    ):
        return CollectionStatus.FAILED

    known_incomplete = (
        _nonnegative_integer(evidence.unresolved_error_count)
        and evidence.unresolved_error_count > 0
    )
    if isinstance(evidence.scopes, tuple):
        known_incomplete = known_incomplete or any(
            _known_scope_incomplete(scope) for scope in evidence.scopes
        )

    request_shape_valid = (
        isinstance(evidence.requested_scopes, tuple)
        and bool(evidence.requested_scopes)
        and all(_valid_scope(scope) for scope in evidence.requested_scopes)
    )
    if request_shape_valid:
        requested = evidence.requested_scopes
        if (
            len({scope.scope_id for scope in requested}) != len(requested)
            or len({_scope_identity(scope) for scope in requested}) != len(requested)
        ):
            request_shape_valid = False
    if not request_shape_valid:
        return CollectionStatus.INCOMPLETE if known_incomplete else CollectionStatus.UNKNOWN

    # A requested scope with no corresponding record is known unprocessed work,
    # even if other evidence is malformed or names an unexpected scope.
    if isinstance(evidence.scopes, tuple):
        valid_observed_scopes = {
            scope.scope.scope_id
            for scope in evidence.scopes
            if isinstance(scope, ScopeEvidence) and _valid_scope(scope.scope)
        }
        if {scope.scope_id for scope in evidence.requested_scopes} - valid_observed_scopes:
            return CollectionStatus.INCOMPLETE

    if not isinstance(evidence.fatal_failure, bool):
        return CollectionStatus.INCOMPLETE if known_incomplete else CollectionStatus.UNKNOWN

    if not _nonnegative_integer(evidence.unresolved_error_count):
        return CollectionStatus.INCOMPLETE if known_incomplete else CollectionStatus.UNKNOWN
    if not isinstance(evidence.scopes, tuple) or any(
        not isinstance(scope, ScopeEvidence) for scope in evidence.scopes
    ):
        return CollectionStatus.INCOMPLETE if known_incomplete else CollectionStatus.UNKNOWN
    if any(not _valid_scope(scope.scope) for scope in evidence.scopes):
        return CollectionStatus.INCOMPLETE if known_incomplete else CollectionStatus.UNKNOWN

    observed_scopes = [scope.scope for scope in evidence.scopes if _valid_scope(scope.scope)]
    observed_ids = [scope.scope_id for scope in observed_scopes]
    if len(observed_ids) != len(set(observed_ids)):
        return CollectionStatus.INCOMPLETE if known_incomplete else CollectionStatus.UNKNOWN
    if any(scope_id not in {item.scope_id for item in requested} for scope_id in observed_ids):
        return CollectionStatus.INCOMPLETE if known_incomplete else CollectionStatus.UNKNOWN

    requested_by_id = {scope.scope_id: scope for scope in requested}
    if any(
        _scope_identity(scope)
        != _scope_identity(requested_by_id[scope.scope_id])
        for scope in observed_scopes
    ):
        return CollectionStatus.INCOMPLETE if known_incomplete else CollectionStatus.UNKNOWN

    requested_positions = {
        scope.scope_id: index
        for index, scope in enumerate(requested, start=1)
    }
    if any(
        scope.scope_sequence is not None
        and (
            not _positive_integer(scope.scope_sequence)
            or not _valid_scope(scope.scope)
            or scope.scope.scope_id not in requested_positions
            or scope.scope_sequence != requested_positions.get(scope.scope.scope_id)
        )
        for scope in evidence.scopes
    ):
        return CollectionStatus.INCOMPLETE if known_incomplete else CollectionStatus.UNKNOWN

    missing_scopes = {scope.scope_id for scope in requested} - set(observed_ids)
    if missing_scopes:
        return CollectionStatus.INCOMPLETE
    if evidence.unresolved_error_count > 0:
        return CollectionStatus.INCOMPLETE

    cross_scope_duplicate_state = _cross_scope_duplicate_state(evidence)
    if cross_scope_duplicate_state is None:
        return CollectionStatus.INCOMPLETE if known_incomplete else CollectionStatus.UNKNOWN
    if cross_scope_duplicate_state:
        # The production collector records and skips these occurrences. Its
        # diagnostic is not a per-scope filtering/qualification disposition.
        return CollectionStatus.INCOMPLETE

    statuses = [classify_scope_evidence(scope) for scope in evidence.scopes]
    if any(status is CollectionStatus.FAILED for status in statuses):
        return CollectionStatus.FAILED
    if any(status is CollectionStatus.INCOMPLETE for status in statuses):
        return CollectionStatus.INCOMPLETE
    if any(status not in {CollectionStatus.COMPLETE, CollectionStatus.COMPLETE_EMPTY} for status in statuses):
        return CollectionStatus.UNKNOWN

    if any(scope.qualifying_candidate_count > 0 for scope in evidence.scopes):
        return CollectionStatus.COMPLETE
    return CollectionStatus.COMPLETE_EMPTY


def _cross_scope_duplicate_state(evidence):
    """Return True for valid skipped cross-scope duplicates, None if malformed."""
    requested_order = {
        scope.scope_id: index
        for index, scope in enumerate(evidence.requested_scopes)
    }
    scopes_by_id = {scope.scope.scope_id: scope for scope in evidence.scopes}
    found_valid = False
    found_malformed = False

    for current_scope in evidence.scopes:
        current_scope_id = current_scope.scope.scope_id
        if not isinstance(current_scope.candidates, tuple):
            continue
        prior_ids = set()
        for candidate in current_scope.candidates:
            if not isinstance(candidate, CandidateEvidence):
                continue
            is_cross_scope = (
                candidate.reason is CandidateReason.DUPLICATE_ACROSS_SCOPES
                or candidate.output_deduplicated is not None
                or candidate.output_duplicate_of_scope_id is not None
                or candidate.output_duplicate_of_sequence is not None
            )
            if not is_cross_scope:
                if not isinstance(candidate.candidate_id, str):
                    continue
                prior_ids.add(candidate.candidate_id)
                continue

            found_malformed = True
            target_scope_id = candidate.output_duplicate_of_scope_id
            if (
                candidate.disposition is not CandidateDisposition.UNPROCESSED
                or candidate.processing_status is not CandidateProcessingStatus.PENDING
                or candidate.reason is not CandidateReason.DUPLICATE_ACROSS_SCOPES
                or candidate.output_deduplicated is not True
                or candidate.duplicate_of_sequence is not None
                or not isinstance(candidate.candidate_id, str)
                or not candidate.candidate_id.strip()
                or candidate.candidate_id in prior_ids
                or candidate.source_scope_id != current_scope_id
                or not isinstance(current_scope_id, str)
                or not isinstance(target_scope_id, str)
                or not target_scope_id.strip()
                or target_scope_id == current_scope_id
                or not _positive_integer(candidate.discovery_sequence)
                or not _positive_integer(candidate.output_duplicate_of_sequence)
                or target_scope_id not in scopes_by_id
                or target_scope_id not in requested_order
                or current_scope_id not in requested_order
                or requested_order[target_scope_id] >= requested_order[current_scope_id]
            ):
                continue

            target_scope = scopes_by_id[target_scope_id]
            target = next(
                (
                    item
                    for item in target_scope.candidates
                    if isinstance(item, CandidateEvidence)
                    and item.candidate_id == candidate.candidate_id
                    and item.discovery_sequence == candidate.output_duplicate_of_sequence
                ),
                None,
            ) if isinstance(target_scope.candidates, tuple) else None
            if target is None or target.source_scope_id != target_scope_id:
                continue
            prior_ids.add(candidate.candidate_id)
            found_valid = True

    if found_valid:
        return True
    return None if found_malformed else False
