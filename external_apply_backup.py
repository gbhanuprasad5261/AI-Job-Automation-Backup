import re

"""
External ATS discovery and safe form preparation.

This module handles company-career-page applications opened from LinkedIn.
It may prepare a form for manual review, but it never submits an external
application automatically.
"""

from pathlib import Path
from urllib.parse import urlparse


ATS_DOMAINS = {
    "greenhouse.io": "GREENHOUSE",
    "boards.greenhouse.io": "GREENHOUSE",
    "lever.co": "LEVER",
    "jobs.lever.co": "LEVER",
    "myworkdayjobs.com": "WORKDAY",
    "workday.com": "WORKDAY",
    "ashbyhq.com": "ASHBY",
    "smartrecruiters.com": "SMARTRECRUITERS",
}

def is_external_login_required(page):
    """
    Detect external ATS pages that require user authentication.

    This does NOT attempt to log in automatically.
    """
    try:
        url = (page.url or "").lower()

        if "/login" in url or "signin" in url or "sign-in" in url:
            return True

        body = (page.locator("body").inner_text() or "").lower()

        login_signals = [
            "sign in to continue",
            "continue with google",
            "sign in with google",
            "log in to continue",
            "login to continue",
        ]

        return any(signal in body for signal in login_signals)

    except Exception:
        return False
    
def detect_ats(url):
    host = urlparse(url).netloc.lower()
    for domain, name in ATS_DOMAINS.items():
        if host == domain or host.endswith("." + domain):
            return name
    return "UNKNOWN"

# ============================================================
# External Eligibility
# ============================================================

CANDIDATE_EXPERIENCE_YEARS = 0


def extract_external_experience_requirement(text):
    """
    Extract an explicit minimum professional-experience requirement.

    Returns:
        required_years: minimum clearly stated years
        label: human-readable requirement
        skip: True when candidate experience is insufficient
    """

    text = " ".join(
        str(text or "").lower().split()
    )

    # Normalize common Unicode dash characters so experience ranges
    # such as "1–3 years" and "1—3 years" are detected consistently.
    text = (
        text
        .replace("–", "-")
        .replace("—", "-")
    )

    if not text:
        return 0, "Not specified", False

    # Explicit fresher/entry-level wording.
    fresher_terms = (
        "fresher",
        "freshers",
        "fresh graduate",
        "recent graduate",
        "entry level",
        "entry-level",
        "0 years experience",
        "0-1 years",
        "0 - 1 years",
    )

    # Check explicit experience requirements first.
    patterns = [
        # Range:
        # 1-3 years of professional software engineering experience
        # 1–3 years professional experience
        r"(\d+)\s*-\s*(\d+)\s+years?\b.*?\bexperience",

        # Minimum:
        # minimum 2 years of experience
        # minimum 2 years professional experience
        r"minimum\s+(\d+)\s+years?\b.*?\bexperience",

        # At least:
        # at least 1 year of professional experience
        # at least 1 year software engineering experience
        r"at\s+least\s+(\d+)\s+years?\b.*?\bexperience",

        # Plus:
        # 2+ years of experience
        # 2+ years professional software engineering experience
        r"(\d+)\s*\+\s*years?\b.*?\bexperience",

        # Simple:
        # 2 years of experience
        # 2 years professional software engineering experience
        r"(\d+)\s+years?\b.*?\bexperience",
    ]
    requirements = []

    for pattern in patterns:
        for match in re.finditer(pattern, text):
            try:
                minimum = int(match.group(1))
                requirements.append(minimum)
            except (ValueError, TypeError):
                continue

    if requirements:
        # For a range such as 1-3 years, group(1) is the
        # minimum requirement (1), not the maximum (3).
        required_years = min(requirements)

        return (
            required_years,
            f"{required_years}+ years",
            required_years > CANDIDATE_EXPERIENCE_YEARS,
        )

    if any(term in text for term in fresher_terms):
        return 0, "Fresher / Entry Level", False

    return 0, "Not specified", False


def check_external_eligibility(page):
    """
    Perform a conservative eligibility check using the visible external
    application page.

    Returns:
        ELIGIBLE
        INELIGIBLE
        UNKNOWN
    """

    try:
        body_text = page.locator("body").inner_text(
            timeout=10000
        )
    except Exception as e:
        print(
            f"Could not read external application page: {e}"
        )
        return "UNKNOWN"

    required_years, label, should_skip = (
        extract_external_experience_requirement(
            body_text
        )
    )

    print()
    print("=" * 70)
    print("EXTERNAL ELIGIBILITY CHECK")
    print("=" * 70)

    print(
        f"Candidate experience : "
        f"{CANDIDATE_EXPERIENCE_YEARS} years"
    )

    print(
        f"External requirement  : "
        f"{label}"
    )

    if should_skip:
        print()
        print(
            "INELIGIBLE: external page explicitly requires "
            "more professional experience."
        )
        return "INELIGIBLE"

    if required_years == 0:
        print(
            "No explicit minimum experience requirement detected."
        )
        return "UNKNOWN"

    print(
        "External experience requirement is compatible."
    )

    return "ELIGIBLE"


def find_external_apply_link(page):
    """Return the strongest visible external application link on a LinkedIn page."""
    selectors = [
        'a[href*="greenhouse"]',
        'a[href*="lever.co"]',
        'a[href*="myworkdayjobs"]',
        'a[href*="ashbyhq"]',
        'a[href*="smartrecruiters"]',
    ]

    for selector in selectors:
        links = page.locator(selector)
        for i in range(links.count()):
            link = links.nth(i)
            try:
                if not link.is_visible():
                    continue
                href = link.get_attribute("href") or ""
                if href.startswith("http"):
                    return href
            except Exception:
                continue

    links = page.locator("a[href]")
    for i in range(links.count()):
        link = links.nth(i)
        try:
            if not link.is_visible():
                continue
            text = (link.inner_text() or "").strip().lower()
            href = link.get_attribute("href") or ""
            if "apply" in text and "linkedin.com" not in href.lower():
                return href
        except Exception:
            continue

    return ""


def _fill_first(page, selectors, value):
    if not value:
        return False

    for selector in selectors:
        fields = page.locator(selector)
        for i in range(fields.count()):
            field = fields.nth(i)
            try:
                if not field.is_visible():
                    continue
                current = field.input_value()
                if not (current or "").strip():
                    field.fill(value)
                    return True
            except Exception:
                continue
    return False


def _upload_resume(page, resume_path):
    if not resume_path:
        return False

    path = Path(resume_path)
    if not path.exists():
        return False

    inputs = page.locator('input[type="file"]')
    for i in range(inputs.count()):
        try:
            inputs.nth(i).set_input_files(str(path))
            return True
        except Exception:
            continue
    return False


def _click_application_continue(page):
    """
    Click only an obvious non-final continuation control such as Apply Now.

    This function deliberately does NOT click Submit/Send/Apply-to-submit
    controls. The goal is to expose the actual application form safely.
    """
    patterns = [
        r"^apply now$",
        r"^continue$",
        r"^next$",
        r"^start application$",
    ]

    for pattern in patterns:
        try:
            button = page.get_by_role("button", name=__import__("re").compile(pattern, __import__("re").IGNORECASE)).first
            if button.count() > 0 and button.is_visible():
                button.click(timeout=10000)
                return True
        except Exception:
            pass

        try:
            link = page.get_by_role("link", name=__import__("re").compile(pattern, __import__("re").IGNORECASE)).first
            if link.count() > 0 and link.is_visible():
                link.click(timeout=10000)
                return True
        except Exception:
            pass

    # Text fallback for sites that expose Apply Now as a div/span control.
    controls = page.locator('[role="button"], button, a')
    for i in range(controls.count()):
        try:
            control = controls.nth(i)
            if not control.is_visible():
                continue
            text = (control.inner_text() or "").strip().lower()
            if text in {"apply now", "continue", "next", "start application"}:
                control.click(timeout=10000)
                return True
        except Exception:
            continue

    return False


def _required_fields_empty(page):
    required = page.locator(
        'input[required], textarea[required], select[required], '
        '[aria-required="true"]'
    )

    empty = 0
    visible_required = 0

    for i in range(required.count()):
        field = required.nth(i)
        try:
            if not field.is_visible():
                continue

            visible_required += 1
            tag = field.evaluate("e => e.tagName")

            if tag in {"INPUT", "TEXTAREA", "SELECT"}:
                value = field.input_value()
            else:
                value = field.inner_text()

            if not str(value or "").strip():
                empty += 1
        except Exception:
            continue

    return visible_required, empty


def prepare_external_application_page(page, resume_path, name, email, phone):
    """
    Prepare an already-open external application page.

    Returns:
        INELIGIBLE
        READY_FOR_REVIEW

    The function never submits an external application.
    """

    ats = detect_ats(page.url)

    print(f"External ATS detected: {ats}")
    print(f"External page: {page.url}")

    try:
        page.bring_to_front()
    except Exception:
        pass

    try:
        page.wait_for_load_state(
            "domcontentloaded",
            timeout=15000
        )
    except Exception:
        pass

    page.wait_for_timeout(1500)

    print("Preparing external application page...")

    # --------------------------------------------------
    # External eligibility gate
    # --------------------------------------------------

    eligibility = check_external_eligibility(page)

    if eligibility == "INELIGIBLE":
        print()
        print("=" * 70)
        print("EXTERNAL APPLICATION SKIPPED")
        print("=" * 70)

        print(
            "Candidate does not meet the explicit "
            "experience requirement."
        )

        print(
            "No resume upload or application preparation "
            "was performed."
        )

        return "INELIGIBLE"

    # --------------------------------------------------
    # Continue only when eligibility is not INELIGIBLE
    # --------------------------------------------------

    clicked = _click_application_continue(page)

    if clicked:
        print(
            "External application continuation control clicked."
        )

        page.wait_for_timeout(1500)

    # --------------------------------------------------
    # Fill known contact fields
    # --------------------------------------------------

    filled = 0

    if _fill_first(
        page,
        [
            'input[name*="name" i]',
            'input[id*="name" i]',
            'input[placeholder*="name" i]'
        ],
        name
    ):
        filled += 1

    if _fill_first(
        page,
        [
            'input[type="email"]',
            'input[name*="email" i]',
            'input[id*="email" i]'
        ],
        email
    ):
        filled += 1

    if _fill_first(
        page,
        [
            'input[type="tel"]',
            'input[name*="phone" i]',
            'input[name*="mobile" i]',
            'input[id*="phone" i]'
        ],
        phone
    ):
        filled += 1

    # --------------------------------------------------
    # Resume upload
    # --------------------------------------------------

    uploaded = _upload_resume(
        page,
        resume_path
    )

    print(
        f"Known contact fields filled: {filled}"
    )

    print(
        "Resume uploaded: "
        f"{'Yes' if uploaded else 'No / not required yet'}"
    )

    # --------------------------------------------------
    # Required fields check
    # --------------------------------------------------

    visible_required, empty_required = (
        _required_fields_empty(page)
    )

    print(
        f"Visible required fields: "
        f"{visible_required}"
    )

    print(
        f"Required fields still empty: "
        f"{empty_required}"
    )

    if empty_required:
        print(
            "External application needs "
            "manual completion/review."
        )
    else:
        print(
            "No visible required fields remain empty."
        )

    # --------------------------------------------------
    # Never submit externally
    # --------------------------------------------------

    print(
        "External application prepared "
        "for manual review."
    )

    print(
        "No external submission was performed."
    )

    return "READY_FOR_REVIEW"


def prepare_external_form(page, resume_path, name, email, phone):
    """Backward-compatible alias for the older helper name."""
    return prepare_external_application_page(page, resume_path, name, email, phone)


def external_apply(url, resume_path, name, email, phone):
    """
    Open an external URL in a standalone browser and prepare it for review.

    This legacy entry point is retained for compatibility. It never submits.
    """
    from playwright.sync_api import sync_playwright

    print(f"External ATS detected: {detect_ats(url)}")
    print(f"Opening: {url}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2500)
            return prepare_external_application_page(
                page, resume_path, name, email, phone
            )
        finally:
            # Leave the visible browser usable for manual review until the
            # automation finishes. The caller owns the final review/closure.
            pass


if __name__ == "__main__":
    print("external_apply.py loaded successfully.")
    print("This module does not submit external applications automatically.")
