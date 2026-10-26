"""Pure helpers for validating declared CSV header contracts."""

from __future__ import annotations

from collections.abc import Collection, Sequence
import re
from urllib.parse import urlsplit


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


def validate_link_value(value: object) -> tuple[bool, str | None]:
    """Validate one Link cell without I/O or configuration access.

    Returns ``(True, None)`` for an absolute HTTP(S) URL with a hostname and
    valid optional port. Invalid inputs return ``(False, reason_code)``.
    This checks syntax only: it does not resolve hosts, fetch URLs, normalize
    accepted values, or impose a hostname allowlist.
    """
    if value is None:
        return False, "LINK_MISSING"
    if not isinstance(value, str):
        return False, "LINK_TYPE_INVALID"
    if not value.strip():
        return False, "LINK_MISSING"
    if "\\" in value or any(
        char.isspace() or ord(char) < 32 or 0x7F <= ord(char) <= 0x9F
        for char in value
    ):
        return False, "LINK_INVALID"
    if re.search(r"%(?![0-9A-Fa-f]{2})", value):
        return False, "LINK_INVALID"

    try:
        parsed = urlsplit(value)
    except ValueError:
        return False, "LINK_INVALID"

    if parsed.scheme.lower() not in {"http", "https"}:
        if parsed.scheme:
            return False, "LINK_UNSUPPORTED_SCHEME"
        return False, "LINK_INVALID"
    if not parsed.netloc:
        return False, "LINK_INVALID"
    if parsed.username is not None or parsed.password is not None or "@" in parsed.netloc:
        return False, "LINK_INVALID"

    # urlsplit accepts an explicitly empty port (for example, example.com:).
    # Reject it alongside nonnumeric and out-of-range ports.
    if parsed.netloc.endswith(":"):
        return False, "LINK_INVALID"
    if parsed.netloc.startswith("["):
        closing_bracket = parsed.netloc.find("]")
        if closing_bracket >= 0 and parsed.netloc[closing_bracket + 1 :] == ":":
            return False, "LINK_INVALID"

    try:
        hostname = parsed.hostname
        parsed.port
    except ValueError:
        return False, "LINK_INVALID"
    if not hostname:
        return False, "LINK_INVALID"
    return True, None
