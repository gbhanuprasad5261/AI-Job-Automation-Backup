"""Best-effort redaction for explicitly labelled diagnostic credentials.

This standalone helper is not wired into the protected offline runner. It is not
an exhaustive secret scanner and must not be treated as a security boundary.
"""
from __future__ import annotations

import re

_REDACTED = "[REDACTED]"
_FAILURE = "<diagnostic omitted: redaction failed>"
_SECRET_KEY = (
    r"password|passwd|pwd|api[-_]?key|access[-_]?token|refresh[-_]?token|"
    r"id[-_]?token|auth[-_]?token|session(?:[-_]?id)?|csrf[-_]?token|"
    r"client[-_]?secret|session[-_]?token|secret|token|credential|authorization|"
    r"proxy[-_]?authorization|cookie|set-cookie|x-api-key"
)
_ASSIGNMENT_PREFIX = (
    r"(?<![A-Za-z0-9_-])\"?(?:" + _SECRET_KEY + r")\"?[ \t]*[:=][ \t]*"
)
_HEADER = re.compile(
    r"(?im)^(?P<prefix>[ \t]*(?:authorization|proxy-authorization|cookie|set-cookie|x-api-key)"
    r"[ \t]*:[ \t]*)(?P<value>[^\r\n]*(?:\r?\n[ \t]+[^\r\n]*)*)"
)
_BEARER = re.compile(r"(?i)\bBearer[ \t]+(?:\"[^\"\r\n]*\"|'[^'\r\n]*'|[A-Za-z0-9._~+/=-]+)")
_MALFORMED_BEARER = re.compile(
    r"(?im)(?P<prefix>\bBearer[ \t]+)(?P<quote>[\"'])(?P<value>(?:\\.|(?!(?P=quote))[^\r\n])*)$"
)
_MALFORMED_QUOTED_ASSIGNMENT = re.compile(
    r"(?im)(?P<prefix>" + _ASSIGNMENT_PREFIX + r")(?P<quote>[\"'])(?P<value>(?:\\.|(?!(?P=quote))[^\r\n])*)$"
)
_ASSIGNMENT = re.compile(
    r"(?i)(?P<prefix>" + _ASSIGNMENT_PREFIX + r")"
    r"(?P<value>\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|[^\s,;}&\]#\r\n]+)"
)
_QUERY_SECRET = re.compile(
    r"(?i)(?P<prefix>[?&](?:\"?(?:" + _SECRET_KEY + r")\"?)[ \t]*=[ \t]*)"
    r"(?P<value>[^&#\s]+)"
)
_MULTILINE_ASSIGNMENT = re.compile(
    r"(?im)(?P<prefix>" + _ASSIGNMENT_PREFIX + r")"
    r"(?P<first>[^\s,;}&\]#\r\n]+)"
    r"(?P<wrapped>(?:\r?\n[ \t]+[A-Za-z0-9._~+/=-]+)+)"
)
_MULTILINE_BEARER = re.compile(
    r"(?im)(?P<prefix>\bBearer[ \t]+)(?P<first>[A-Za-z0-9._~+/=-]+)"
    r"(?P<wrapped>(?:\r?\n[ \t]+[A-Za-z0-9._~+/=-]+)+)"
)


def _wrapped_replacement(match: re.Match[str]) -> str:
    continuation = re.sub(r"(?<=\n)[ \t]*[^\r\n]+", _REDACTED, match.group("wrapped"))
    return match.group("prefix") + _REDACTED + continuation


def redact_diagnostic_text(value: str | bytes) -> str:
    """Redact common bearer, header, and labelled key/value credentials.

    Bytes are decoded as UTF-8 with replacement. Non-text values are rejected
    without calling ``repr`` so arbitrary object representations are not copied
    into diagnostics. If redaction itself fails, the diagnostic is omitted.
    This deliberately does not claim complete secret detection.
    """
    if type(value) is bytes:
        text = value.decode("utf-8", errors="replace")
    elif type(value) is str:
        text = value
    else:
        return "<non-text diagnostic>"

    try:
        text = _HEADER.sub(lambda match: match.group("prefix") + _REDACTED, text)
        text = _MULTILINE_BEARER.sub(_wrapped_replacement, text)
        text = _MALFORMED_BEARER.sub(lambda match: match.group("prefix") + match.group("quote") + _REDACTED, text)
        text = _BEARER.sub("Bearer " + _REDACTED, text)
        text = _MULTILINE_ASSIGNMENT.sub(_wrapped_replacement, text)
        text = _MALFORMED_QUOTED_ASSIGNMENT.sub(
            lambda match: match.group("prefix") + match.group("quote") + _REDACTED,
            text,
        )
        text = _QUERY_SECRET.sub(lambda match: match.group("prefix") + _REDACTED, text)

        def replace_assignment(match: re.Match[str]) -> str:
            value_text = match.group("value")
            quote = value_text[0] if value_text.startswith(("\"", "'")) else ""
            return match.group("prefix") + quote + _REDACTED + quote

        return _ASSIGNMENT.sub(replace_assignment, text)
    except Exception:
        # Never return the original text or exception detail on a redaction failure.
        return _FAILURE