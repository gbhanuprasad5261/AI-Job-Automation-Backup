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


class CandidateDisposition(str, Enum):
    QUALIFYING = "QUALIFYING"
    FILTERED = "FILTERED"
    UNPROCESSED = "UNPROCESSED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class SearchScope:
    """One explicitly requested keyword/location scope."""

    keyword: str
    location: str


@dataclass(frozen=True)
class CandidateEvidence:
    """A candidate identifier and its explicitly recorded disposition."""

    candidate_id: str
    disposition: CandidateDisposition | None


@dataclass(frozen=True)
class ScopeEvidence:
    """Evidence recorded for one requested search scope."""

    scope: SearchScope
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
    )


def _known_scope_incomplete(evidence):
    """Return whether valid evidence positively records unfinished work."""
    if not isinstance(evidence, ScopeEvidence):
        return False
    if evidence.fatal_failure is True:
        return False
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
    if not isinstance(evidence.fatal_failure, bool):
        return CollectionStatus.UNKNOWN

    if _known_scope_incomplete(evidence):
        return CollectionStatus.INCOMPLETE

    if not _valid_scope(evidence.scope):
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

    candidate_ids = []
    qualifying_dispositions = 0
    for candidate in evidence.candidates:
        if not isinstance(candidate.candidate_id, str) or not candidate.candidate_id.strip():
            return CollectionStatus.UNKNOWN
        if candidate.candidate_id in candidate_ids:
            return CollectionStatus.UNKNOWN
        candidate_ids.append(candidate.candidate_id)
        if candidate.disposition is CandidateDisposition.UNPROCESSED:
            return CollectionStatus.INCOMPLETE
        if candidate.disposition is CandidateDisposition.UNKNOWN or candidate.disposition is None:
            return CollectionStatus.UNKNOWN
        if not isinstance(candidate.disposition, CandidateDisposition) or candidate.disposition not in {
            CandidateDisposition.QUALIFYING,
            CandidateDisposition.FILTERED,
        }:
            return CollectionStatus.UNKNOWN
        if candidate.disposition is CandidateDisposition.QUALIFYING:
            qualifying_dispositions += 1

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
        isinstance(scope, ScopeEvidence) and scope.fatal_failure is True
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
        if len(set(requested)) != len(requested):
            request_shape_valid = False
    if not request_shape_valid:
        return CollectionStatus.INCOMPLETE if known_incomplete else CollectionStatus.UNKNOWN

    # A requested scope with no corresponding record is known unprocessed work,
    # even if other evidence is malformed or names an unexpected scope.
    if isinstance(evidence.scopes, tuple):
        valid_observed_scopes = {
            scope.scope
            for scope in evidence.scopes
            if isinstance(scope, ScopeEvidence) and _valid_scope(scope.scope)
        }
        if set(evidence.requested_scopes) - valid_observed_scopes:
            return CollectionStatus.INCOMPLETE

    if not _nonnegative_integer(evidence.unresolved_error_count):
        return CollectionStatus.INCOMPLETE if known_incomplete else CollectionStatus.UNKNOWN
    if not isinstance(evidence.scopes, tuple) or any(
        not isinstance(scope, ScopeEvidence) for scope in evidence.scopes
    ):
        return CollectionStatus.INCOMPLETE if known_incomplete else CollectionStatus.UNKNOWN

    observed_scopes = [scope.scope for scope in evidence.scopes if _valid_scope(scope.scope)]
    if len(observed_scopes) != len(set(observed_scopes)):
        return CollectionStatus.INCOMPLETE if known_incomplete else CollectionStatus.UNKNOWN
    if any(scope not in requested for scope in observed_scopes):
        return CollectionStatus.INCOMPLETE if known_incomplete else CollectionStatus.UNKNOWN

    missing_scopes = set(requested) - set(observed_scopes)
    if missing_scopes:
        return CollectionStatus.INCOMPLETE
    if evidence.unresolved_error_count > 0:
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
