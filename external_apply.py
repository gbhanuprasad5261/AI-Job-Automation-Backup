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

    Returns READY_FOR_REVIEW after filling obvious fields and navigating through
    a non-final Apply Now/Continue/Next step. It never submits the application.
    """
    ats = detect_ats(page.url)
    print(f"External ATS detected: {ats}")
    print(f"External page: {page.url}")

    try:
        page.bring_to_front()
    except Exception:
        pass

    try:
        page.wait_for_load_state("domcontentloaded", timeout=15000)
    except Exception:
        pass
    page.wait_for_timeout(1500)

    print("Preparing external application page...")

    # Some company pages show a job-detail page first. Apply Now is a safe
    # continuation control; it is not treated as final submission.
    clicked = _click_application_continue(page)
    if clicked:
        print("External application continuation control clicked.")
        page.wait_for_timeout(1500)

    filled = 0
    if _fill_first(page, ['input[name*="name" i]', 'input[id*="name" i]', 'input[placeholder*="name" i]'], name):
        filled += 1
    if _fill_first(page, ['input[type="email"]', 'input[name*="email" i]', 'input[id*="email" i]'], email):
        filled += 1
    if _fill_first(page, ['input[type="tel"]', 'input[name*="phone" i]', 'input[name*="mobile" i]', 'input[id*="phone" i]'], phone):
        filled += 1

    uploaded = _upload_resume(page, resume_path)

    print(f"Known contact fields filled: {filled}")
    print(f"Resume uploaded: {'Yes' if uploaded else 'No / not required yet'}")

    visible_required, empty_required = _required_fields_empty(page)
    print(f"Visible required fields: {visible_required}")
    print(f"Required fields still empty: {empty_required}")

    if empty_required:
        print("External application needs manual completion/review.")
    else:
        print("No visible required fields remain empty.")

    print("External application prepared for manual review.")
    print("No external submission was performed.")
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
