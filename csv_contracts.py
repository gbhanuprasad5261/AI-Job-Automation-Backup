"""Pure helpers for validating declared CSV header contracts."""

from __future__ import annotations

from collections.abc import Collection, Sequence


def missing_required_columns(
    headers: Sequence[str] | None,
    required: Collection[str],
) -> tuple[str, ...]:
    """Return absent required header names in deterministic sorted order.

    Header comparison is exact and case-sensitive. Extra columns are accepted.
    This helper does not parse CSV data, validate duplicate headers, or access
    files, configuration, or workflow modules.
    """
    present = set(headers or ())
    return tuple(sorted(set(required) - present))
