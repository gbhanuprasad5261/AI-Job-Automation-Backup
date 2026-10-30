"""Synchronous, one-time human confirmation for an individual application.

This module deliberately keeps no approval state. A fresh challenge is issued
at the final-submit boundary and must be entered exactly before that one
application can proceed.
"""

import hmac
import secrets
import time


APPROVAL_CHALLENGE_TTL_SECONDS = 120


def confirm_application_submission(application_identity, title="", company=""):
    """Return true only after an exact, fresh console confirmation.

    Missing or malformed identity, unavailable input, interruption, and every
    response other than the current challenge fail closed. Approval is not
    cached and cannot be reused for another application or later attempt.
    """
    if not isinstance(application_identity, str):
        print("Submission blocked: application identity is missing or invalid.")
        return False

    identity = application_identity.strip()
    if not identity or any(ord(char) < 32 or ord(char) == 127 for char in identity):
        print("Submission blocked: application identity is missing or invalid.")
        return False

    safe_title = " ".join(str(title or "").split())
    safe_company = " ".join(str(company or "").split())
    nonce = secrets.token_urlsafe(12)
    expected = f"APPROVE {identity} {nonce}"
    issued_at = time.monotonic()

    print("Human approval is required for this application.")
    print(f"Application: {safe_title or '(title unavailable)'} at {safe_company or '(company unavailable)'}")
    print(f"Application identity: {identity}")
    print(
        f"This one-time challenge expires in {APPROVAL_CHALLENGE_TTL_SECONDS} seconds."
    )
    print(f"To approve this submission once, type exactly: {expected}")
    try:
        response = input("Approval: ")
    except KeyboardInterrupt:
        print("Submission blocked: approval input was interrupted.")
        return False
    except Exception:
        print("Submission blocked: approval input was unavailable or interrupted.")
        return False

    if time.monotonic() - issued_at > APPROVAL_CHALLENGE_TTL_SECONDS:
        print("Submission blocked: the application approval challenge expired.")
        return False

    if not isinstance(response, str) or not hmac.compare_digest(response, expected):
        print("Submission blocked: explicit application approval was not confirmed.")
        return False
    return True
