import csv
import os
import re
from datetime import datetime

from application_form import inspect_and_prepare_form
from external_app import (
    find_external_apply_link,
    check_external_eligibility,
    prepare_external_application_page,
)
from playwright.sync_api import sync_playwright


# ---------------------------------------
# Configuration
# ---------------------------------------

ANALYSIS_FILE = "data/job_analysis.csv"
TRACKER_FILE = "data/application_tracker.csv"
APPLICATION_HISTORY_FILE = "data/application_history.csv"

MIN_MATCH_SCORE = 70
MAX_APPLICATIONS_PER_RUN = 15
MAX_CANDIDATE_JOBS_PER_RUN = 30

ALLOWED_LOCATION_KEYWORDS = (
    "bengaluru",
    "bangalore",
    "hyderabad",
    "chennai",
    "remote",
)

ALLOW_EXTERNAL_APPLICATIONS = True

CHROME_CDP_URL = "http://127.0.0.1:9222"


# ---------------------------------------
# Navigation helper
# ---------------------------------------

def navigate_page(page, url, timeout=30000, settle_ms=5000, required_url_fragment=None):
    """Navigate while tolerating slow post-navigation page loading."""
    last_error = None

    for attempt in range(2):
        try:
            page.goto(
                url,
                wait_until="commit",
                timeout=timeout,
            )
            page.wait_for_timeout(settle_ms)

            if required_url_fragment:
                current_url = (page.url or "").lower()
                if required_url_fragment.lower() not in current_url:
                    raise RuntimeError(
                        f"Unexpected navigation URL: {page.url}"
                    )

            return True

        except Exception as e:
            last_error = e

            try:
                current_url = page.url or ""
            except Exception:
                current_url = ""

            # A navigation timeout can occur after the requested page has
            # already committed. If the expected URL is active, continue.
            if required_url_fragment and required_url_fragment.lower() in current_url.lower():
                try:
                    page.wait_for_timeout(settle_ms)
                except Exception:
                    pass
                print(
                    "Navigation reported a timeout, but the expected page URL is already active. Continuing."
                )
                return True

            if attempt == 0:
                print("Navigation did not complete normally; retrying once...")
                try:
                    page.wait_for_timeout(2000)
                except Exception:
                    pass

    print(f"Navigation failed: {last_error}")
    return False


# ---------------------------------------
# Load CSV
# ---------------------------------------

def load_csv(file_path):

    if not os.path.exists(file_path):

        print(f"File not found: {file_path}")

        return []

    with open(
        file_path,
        "r",
        encoding="utf-8"
    ) as f:

        return list(csv.DictReader(f))


# ---------------------------------------
# General Application History
# ---------------------------------------

def _load_application_history():
    """Load one persistent history of confirmed submitted applications."""
    if not os.path.exists(APPLICATION_HISTORY_FILE):
        return []

    try:
        with open(
            APPLICATION_HISTORY_FILE,
            "r",
            encoding="utf-8",
            newline="",
        ) as f:
            return list(csv.DictReader(f))
    except Exception:
        return []


def get_today_applied_count():
    """Return the number of confirmed applications submitted today."""
    today = datetime.now().strftime("%Y-%m-%d")
    count = 0

    for row in _load_application_history():
        status = (row.get("Status") or "").strip().upper()
        applied_date = (row.get("Applied Date") or "").strip()

        if status == "APPLIED" and applied_date == today:
            count += 1

    return count


def _history_status_for_job(job):
    """Return APPLIED when this exact job is already in submission history."""
    job_url = _normalize_url(
        convert_to_job_url(job.get("Link", "") or job.get("URL", ""))
    )
    title = _normalize_text(job.get("Title", ""))
    company = _normalize_text(job.get("Company", ""))

    for row in _load_application_history():
        status = (row.get("Status") or "").strip().upper()
        if status != "APPLIED":
            continue

        row_url = _normalize_url(
            convert_to_job_url(row.get("URL") or row.get("Link") or "")
        )

        if job_url and row_url and job_url == row_url:
            return "APPLIED"

        row_title = _normalize_text(row.get("Title", ""))
        row_company = _normalize_text(row.get("Company", ""))

        if title and company and row_title == title and row_company == company:
            return "APPLIED"

    return "NOT APPLIED"


def _record_application_history(job, status):
    """Persist confirmed application status in one shared history CSV."""
    if status != "APPLIED":
        return True

    os.makedirs(
        os.path.dirname(APPLICATION_HISTORY_FILE) or ".",
        exist_ok=True,
    )

    fields = [
        "Title",
        "Company",
        "Location",
        "URL",
        "Status",
        "Applied Date",
    ]

    rows = _load_application_history()

    job_url = _normalize_url(
        convert_to_job_url(job.get("Link", "") or job.get("URL", ""))
    )
    title = _normalize_text(job.get("Title", ""))
    company = _normalize_text(job.get("Company", ""))

    # Never create duplicate history records.
    for row in rows:
        row_url = _normalize_url(
            convert_to_job_url(row.get("URL") or row.get("Link") or "")
        )
        row_title = _normalize_text(row.get("Title", ""))
        row_company = _normalize_text(row.get("Company", ""))

        if (
            (job_url and row_url and job_url == row_url)
            or (title and company and row_title == title and row_company == company)
        ):
            row["Status"] = "APPLIED"
            row["Applied Date"] = row.get("Applied Date") or datetime.now().strftime("%Y-%m-%d")
            return _write_application_history(rows, fields)

    rows.append({
        "Title": job.get("Title", ""),
        "Company": job.get("Company", ""),
        "Location": job.get("Location", ""),
        "URL": job.get("URL", "") or job.get("Link", ""),
        "Status": "APPLIED",
        "Applied Date": datetime.now().strftime("%Y-%m-%d"),
    })

    return _write_application_history(rows, fields)


def _write_application_history(rows, fields):
    try:
        with open(
            APPLICATION_HISTORY_FILE,
            "w",
            encoding="utf-8",
            newline="",
        ) as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        return True
    except Exception as exc:
        print(f"Could not update application history: {exc}")
        return False


# ---------------------------------------
# Get Application Status
# ---------------------------------------

def _effective_tracker_status(row):
    """Return the status that should affect future job selection.

    Only a confirmed APPLIED result is permanent. Other statuses are
    informational and must not permanently block a fresh job-analysis row.
    """
    candidates = {
        (row.get("Application Status") or "").strip().upper(),
        (row.get("Status") or "").strip().upper(),
    }
    if "APPLIED" in candidates:
        return "APPLIED"
    return "NOT APPLIED"

def _normalize_url(value):
    return (value or "").strip().lower().split("?", 1)[0].rstrip("/")

def _normalize_text(value):
    return " ".join((value or "").strip().lower().split())

def get_application_statuses():
    tracker = load_csv(TRACKER_FILE)
    statuses = {}
    for row in tracker:
        title = (row.get("Title") or "").strip()
        if not title:
            continue
        status = _effective_tracker_status(row)
        # APPLIED is the only persistent status used to exclude jobs.
        if status == "APPLIED":
            statuses[title] = "APPLIED"
    return statuses

def get_application_status(job):
    if _history_status_for_job(job) == "APPLIED":
        return "APPLIED"

    tracker = load_csv(TRACKER_FILE)
    job_url = _normalize_url(convert_to_job_url(job.get("Link", "")))
    title = _normalize_text(job.get("Title", ""))
    company = _normalize_text(job.get("Company", ""))

    # A confirmed APPLIED record is the only tracker status that permanently
    # excludes a job. CLOSED/LOGIN_REQUIRED/INELIGIBLE/READY_FOR_REVIEW are
    # retryable outcomes and must not block a fresh job-analysis row.
    if job_url:
        for row in tracker:
            row_url = _normalize_url(row.get("URL") or row.get("Link") or "")
            if row_url == job_url and _effective_tracker_status(row) == "APPLIED":
                return "APPLIED"

    for row in tracker:
        if (
            title
            and company
            and _normalize_text(row.get("Title")) == title
            and _normalize_text(row.get("Company")) == company
            and _effective_tracker_status(row) == "APPLIED"
        ):
            return "APPLIED"

    return "NOT APPLIED"


def parse_match_score(value):
    try:
        return float(
            str(value or "0").replace("%", "").strip()
        )
    except (ValueError, TypeError):
        return 0.0


def is_allowed_location(location):
    text = (location or "").strip().lower()

    if not text:
        return False

    return any(
        keyword in text
        for keyword in ALLOWED_LOCATION_KEYWORDS
    )




# ---------------------------------------
# Select Recommended Jobs
# ---------------------------------------

def get_recommended_jobs():
    jobs = load_csv(ANALYSIS_FILE)

    if not jobs:
        return []

    recommended = []

    for job in jobs:
        score = parse_match_score(
            job.get("Match Score", "0")
        )

        location = (
            job.get("Location") or ""
        ).strip()

        title = (
            job.get("Title") or ""
        ).strip()

        status = get_application_status(job)

        if score < MIN_MATCH_SCORE:
            continue

        if not is_allowed_location(location):
            continue

        if status != "NOT APPLIED":
            continue

        recommended.append(job)

    recommended.sort(
        key=lambda x: parse_match_score(
            x.get("Match Score", "0")
        ),
        reverse=True
    )

    # Retain enough eligible candidates so closed/unavailable/unsupported jobs
    # can be skipped while the daily confirmed-application limit is enforced.
    return recommended[:MAX_CANDIDATE_JOBS_PER_RUN]




# ---------------------------------------
# Display Jobs
# ---------------------------------------

def display_jobs(jobs):

    print()
    print("=" * 70)
    print("RECOMMENDED JOBS")
    print("=" * 70)

    if not jobs:

        print()
        print(
            "No jobs currently meet the requirements."
        )

        print()

        print(
            f"Minimum Match Score : "
            f"{MIN_MATCH_SCORE}%"
        )

        print(
            "Live Easy Apply     : Verified when job opens"
        )

        print(
            "Application Status  : NOT APPLIED"
        )

        return

    for index, job in enumerate(
        jobs,
        start=1
    ):

        print()

        print(
            f"{index}. "
            f"{job.get('Title', '')}"
        )

        print(
            f"   Company : "
            f"{job.get('Company') or 'Not available'}"
        )

        print(
            f"   Location: "
            f"{job.get('Location') or 'Not available'}"
        )

        print(
            f"   Score   : "
            f"{job.get('Match Score', '0%')}"
        )

        print(
            f"   Priority: "
            f"{job.get('Priority', '')}"
        )

        print(
            f"   CSV Easy Apply: "
            f"{job.get('Easy Apply', '')}"
        )

        print(
            "   Status  : NOT APPLIED"
        )


# ---------------------------------------
# Convert LinkedIn Search URL
# ---------------------------------------

def convert_to_job_url(link):

    if not link:

        return ""

    if "currentJobId=" in link:

        match = re.search(
            r"currentJobId=(\d+)",
            link
        )

        if match:

            job_id = match.group(1)

            return (
                "https://www.linkedin.com/jobs/view/"
                f"{job_id}/"
            )

    return link


# ---------------------------------------
# Job closed detection
# ---------------------------------------

def is_job_closed(body_text):

    closed_messages = [

        "No longer accepting applications",

        "This job is no longer accepting applications",

        "Job is no longer accepting applications",

        "Not currently accepting applications",

        "This job is not currently accepting applications",

        "No longer accepting applications for this job",

        "applications are no longer being accepted",

        "applications are currently closed",

        "job applications are closed"
    ]

    text = body_text.lower()

    for message in closed_messages:

        if message.lower() in text:

            return True

    return False


# ---------------------------------------
# Find Easy Apply Button
# ---------------------------------------

def is_current_job_already_applied(page):
    """Detect a confirmed LinkedIn Applied state for the current job only."""
    selectors = (
        ".jobs-details__main-content button",
        ".jobs-details__main-content [role='button']",
        ".jobs-details__main-content a",
        "main button",
    )

    for selector in selectors:
        try:
            locator = page.locator(selector)
            count = locator.count()
        except Exception:
            continue

        for i in range(count):
            try:
                element = locator.nth(i)
                if not element.is_visible():
                    continue
                text = (element.inner_text() or "").strip().lower()
                aria = (element.get_attribute("aria-label") or "").strip().lower()
                title = (element.get_attribute("title") or "").strip().lower()
                combined = " ".join((text, aria, title)).strip()
                if combined in {"applied", "application submitted", "application already submitted"}:
                    return True
                if "applied" in combined and "easy apply" not in combined and "apply" not in combined:
                    return True
            except Exception:
                continue

    return False


def find_easy_apply_button(page):
    """Find the Easy Apply control belonging to the CURRENT LinkedIn job."""

    def visible(element):
        try:
            return element.is_visible()
        except Exception:
            return False

    def get_text(element):
        try:
            return (element.inner_text() or "").strip()
        except Exception:
            return ""

    def get_attr(element, name):
        try:
            return element.get_attribute(name) or ""
        except Exception:
            return ""

    def is_easy_apply(element):
        text = get_text(element).lower()
        aria = get_attr(element, "aria-label").lower()
        title = get_attr(element, "title").lower()
        href = get_attr(element, "href").lower()
        classes = get_attr(element, "class").lower()

        combined = f"{text} {aria} {title}"

        return (
            "easy apply" in combined
            or "linkedin apply to" in combined
            or "opensduiapplyflow=true" in href
            or "jobs-apply-button" in classes
        )

    def visible_candidates(selector):
        try:
            locator = page.locator(selector)
            result = []

            for i in range(locator.count()):
                element = locator.nth(i)
                if visible(element):
                    result.append(element)

            return result
        except Exception:
            return []

    # ---------------------------------------------------------
    # 1. Strong current-job selectors
    # ---------------------------------------------------------
    selectors = (
        ".jobs-details__main-content [aria-label='Easy Apply to this job']",
        ".jobs-details__main-content [aria-label^='LinkedIn Apply to']",
        ".jobs-details__main-content button.jobs-apply-button",
        ".jobs-details__main-content button[aria-label*='Easy Apply']",
        ".jobs-details__main-content [role='button'][aria-label*='Easy Apply']",

        "main [aria-label='Easy Apply to this job']",
        "main [aria-label^='LinkedIn Apply to']",
        "main button.jobs-apply-button",
    )

    for selector in selectors:
        for element in visible_candidates(selector):
            if is_easy_apply(element):
                print("Current-job Easy Apply control found.")
                return element

    # ---------------------------------------------------------
    # 2. Find the current job title and walk UP its DOM tree.
    #
    # This is important because LinkedIn may show Easy Apply
    # buttons for recommended/sidebar jobs elsewhere on the page.
    # ---------------------------------------------------------
    title_candidates = []

    for selector in (
        ".jobs-details__main-content h1",
        ".jobs-details__main-content .job-details-jobs-unified-top-card__job-title",
        "main h1",
    ):
        try:
            locator = page.locator(selector)

            for i in range(locator.count()):
                element = locator.nth(i)

                if visible(element) and get_text(element):
                    title_candidates.append(element)

        except Exception:
            pass

    # Use the first visible current-job title.
    for title_element in title_candidates[:3]:
        try:
            # Start from the title and progressively move upward.
            container = title_element

            for level in range(8):
                if not container:
                    break

                try:
                    candidates = container.locator(
                        "button, a, [role='button']"
                    )

                    matching = []

                    for i in range(candidates.count()):
                        candidate = candidates.nth(i)

                        if visible(candidate) and is_easy_apply(candidate):
                            matching.append(candidate)

                    if len(matching) == 1:
                        print(
                            "Current-job Easy Apply control found "
                            "using job-title container."
                        )
                        return matching[0]

                except Exception:
                    pass

                try:
                    container = container.locator("..")
                except Exception:
                    break

        except Exception:
            pass

    # ---------------------------------------------------------
    # 3. Last safe fallback:
    # accept a page-wide control ONLY when it is unique.
    # ---------------------------------------------------------
    candidates = visible_candidates(
        "[aria-label^='LinkedIn Apply to']"
    )

    matching = [element for element in candidates if is_easy_apply(element)]

    if len(matching) == 1:
        print("Unique LinkedIn Apply control found.")
        return matching[0]

    candidates = visible_candidates(
        "button.jobs-apply-button"
    )

    matching = [element for element in candidates if is_easy_apply(element)]

    if len(matching) == 1:
        print("Unique LinkedIn Easy Apply control found.")
        return matching[0]

    # ---------------------------------------------------------
    # 4. External application detection.
    # ---------------------------------------------------------
    try:
        body = page.locator("body").inner_text().lower()
    except Exception:
        body = ""

    external_signals = (
        "apply on company website",
        "apply on the company website",
        "apply externally",
        "application on company website",
        "apply via company website",
    )

    if any(signal in body for signal in external_signals):
        print("External application detected.")
        return None

    print("No verified current-job Easy Apply control found.")
    return None


def print_application_controls(page):

    print()
    print(
        "Visible application-related elements:"
    )

    try:

        candidates = page.locator(
            "button, a, [role='button']"
        )

        count = candidates.count()

        shown = 0

        for i in range(count):

            if shown >= 30:

                break

            element = candidates.nth(i)

            try:

                if not element.is_visible():

                    continue

                text = (
                    element.inner_text()
                    .strip()
                )

                aria = (
                    element.get_attribute(
                        "aria-label"
                    )
                    or ""
                )

                combined = (
                    text + " " + aria
                ).lower()

                if any(
                    keyword in combined
                    for keyword in [
                        "apply",
                        "easy",
                        "application"
                    ]
                ):

                    print(
                        f"  [{i}] "
                        f"Text: {text[:150]}"
                    )

                    if aria:

                        print(
                            f"       "
                            f"Aria: {aria[:150]}"
                        )

                    shown += 1

            except Exception:

                continue

    except Exception as e:

        print(
            "Could not inspect "
            f"application controls: {e}"
        )


# ---------------------------------------
# Save Diagnostic Screenshot
# ---------------------------------------

def save_diagnostic_screenshot(page):

    try:

        os.makedirs(
            "screenshots",
            exist_ok=True
        )

        path = (
            "screenshots/"
            "easy_apply_not_found.png"
        )

        page.screenshot(
            path=path,
            full_page=True
        )

        print()
        print(
            f"Diagnostic screenshot saved: {path}"
        )

    except Exception as e:

        print(
            f"Screenshot failed: {e}"
        )



# ---------------------------------------
# Detect confirmed LinkedIn submission
# ---------------------------------------

def detect_linkedin_submission_confirmation(page):
    """Return True only for strong, visible LinkedIn submission-confirmation text."""
    strong_signals = (
        "your application was sent to",
        "application was sent to",
        "your application has been submitted",
        "application has been submitted",
        "application submitted successfully",
        "application submitted",
    )

    try:
        body_text = (page.locator("body").inner_text(timeout=5000) or "").lower()
    except Exception:
        return False

    return any(signal in body_text for signal in strong_signals)


# ---------------------------------------
# Record Application Status
# ---------------------------------------

def record_application_status(job, status):
    """
    Update the tracker for the job after a confirmed application result.

    Matching order:
      1. Exact LinkedIn job URL
      2. Exact Title + Company

    A confirmed APPLIED result is also written to the general application
    history so future runs skip the job even if tracker rows are regenerated.
    """
    try:
        if not os.path.exists(TRACKER_FILE):
            print(f"Tracker file not found: {TRACKER_FILE}")
            tracker_updated = False
        else:
            with open(
                TRACKER_FILE,
                "r",
                encoding="utf-8",
                newline=""
            ) as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames or []
                rows = list(reader)

            if "Status" not in fieldnames:
                fieldnames.append("Status")

            title = _normalize_text(job.get("Title", ""))
            company = _normalize_text(job.get("Company", ""))
            job_url = _normalize_url(
                convert_to_job_url(job.get("Link", "") or job.get("URL", ""))
            )

            updated = False

            # Exact URL first.
            if job_url:
                for row in rows:
                    row_url = _normalize_url(
                        row.get("URL") or row.get("Link") or ""
                    )
                    if row_url == job_url:
                        row["Status"] = status
                        if "Application Status" in fieldnames:
                            row["Application Status"] = status
                        if status == "APPLIED" and "Applied Date" in fieldnames:
                            row["Applied Date"] = datetime.now().strftime("%Y-%m-%d")
                        updated = True
                        break

            # Exact Title + Company fallback.
            if not updated and title and company:
                for row in rows:
                    if (
                        _normalize_text(row.get("Title", "")) == title
                        and _normalize_text(row.get("Company", "")) == company
                    ):
                        row["Status"] = status
                        if "Application Status" in fieldnames:
                            row["Application Status"] = status
                        if status == "APPLIED" and "Applied Date" in fieldnames:
                            row["Applied Date"] = datetime.now().strftime("%Y-%m-%d")
                        updated = True
                        break

            if not updated:
                new_row = {field: "" for field in fieldnames}
                new_row["Title"] = job.get("Title", "")
                new_row["Company"] = job.get("Company", "")
                new_row["Location"] = job.get("Location", "")
                new_row["Status"] = status

                if "Application Status" in fieldnames:
                    new_row["Application Status"] = status

                if "URL" in fieldnames:
                    new_row["URL"] = job.get("URL", "") or job.get("Link", "")

                if status == "APPLIED" and "Applied Date" in fieldnames:
                    new_row["Applied Date"] = datetime.now().strftime("%Y-%m-%d")

                rows.append(new_row)

            with open(
                TRACKER_FILE,
                "w",
                encoding="utf-8",
                newline=""
            ) as f:
                writer = csv.DictWriter(
                    f,
                    fieldnames=fieldnames
                )
                writer.writeheader()
                writer.writerows(rows)

            tracker_updated = True
            print(f"Application tracker updated: {status}")

        if status == "APPLIED":
            history_updated = _record_application_history(job, "APPLIED")
            if not history_updated:
                print("Warning: tracker updated but application history update failed.")
                return False

        return tracker_updated if status != "APPLIED" else (tracker_updated or history_updated)

    except Exception as e:
        print(f"Could not update application tracker: {e}")
        return False


# ---------------------------------------
# Open Easy Apply
# ---------------------------------------

def open_easy_apply(job):

    link = job.get(
        "Link",
        ""
    )

    link = convert_to_job_url(link)

    if not link:

        print(
            "Job URL not found."
        )

        return False

    print()
    print("=" * 70)
    print("OPENING JOB")
    print("=" * 70)

    print(
        f"Title   : "
        f"{job.get('Title', '')}"
    )

    print(
        f"Company : "
        f"{job.get('Company') or 'Not available'}"
    )

    print(
        f"Location: "
        f"{job.get('Location') or 'Not available'}"
    )

    print(
        f"Score   : "
        f"{job.get('Match Score', '')}"
    )

    print(
        f"URL     : {link}"
    )

    # ---------------------------------------
    # Connect to existing Chrome
    # ---------------------------------------

    with sync_playwright() as p:

        try:

            browser = (
                p.chromium.connect_over_cdp(
                    CHROME_CDP_URL
                )
            )

        except Exception as e:

            print()
            print(
                "Could not connect to Chrome."
            )

            print(
                "Start Chrome using:"
            )

            print(
                ".\\start_chrome.bat"
            )

            print()
            print(
                f"Error: {e}"
            )

            return False

        if not browser.contexts:

            print(
                "No browser context found."
            )

            return False

        context = browser.contexts[0]

        # ---------------------------------------
        # Find LinkedIn page
        # ---------------------------------------

        page = None

        for existing_page in context.pages:

            try:

                if (
                    "linkedin.com"
                    in existing_page.url
                ):

                    page = existing_page

                    break

            except Exception:

                continue

        if page is None:

            if context.pages:

                page = context.pages[0]

            else:

                page = context.new_page()

        # ---------------------------------------
        # Open job
        # ---------------------------------------

        if not navigate_page(
            page,
            link,
            timeout=30000,
            settle_ms=5000,
            required_url_fragment="/jobs/view/",
        ):
            print()
            print("Could not open the LinkedIn job page.")
            return False

        print()
        print(
            f"Page title: {page.title()}"
        )

        print(
            f"Current URL: {page.url}"
        )

        # ---------------------------------------
        # Read page
        # ---------------------------------------

        try:

            body_text = (
                page.locator(
                    "body"
                ).inner_text()
            )

        except Exception:

            body_text = ""

        # ---------------------------------------
        # Check closed job
        # ---------------------------------------

        if is_job_closed(body_text):

            print()
            print("=" * 70)
            print("JOB CLOSED")
            print("=" * 70)

            print(
                "This job is no longer "
                "accepting applications."
            )

            print(
                "Skipping this job..."
            )

            # Persist the live closed state so this job is not reopened on
            # future runs.
            record_application_status(job, "CLOSED")
            return False

        # ---------------------------------------
        # Live LinkedIn applied-state check
        # ---------------------------------------
        # A job may have been applied to manually before it entered the
        # tracker. Never reopen or prepare such an application.
        if is_current_job_already_applied(page):
            print()
            print("=" * 70)
            print("JOB ALREADY APPLIED")
            print("=" * 70)
            print("LinkedIn shows that this application was already submitted.")
            print("No Easy Apply click, external application, or resume upload was performed.")
            record_application_status(job, "APPLIED")
            return False

        # ---------------------------------------
        # Fresher eligibility gate
        # ---------------------------------------
        # Check the CURRENT LinkedIn job page before clicking Easy Apply.
        # This prevents opening an application for a role whose visible
        # description explicitly requires more than 0 years of experience.
        try:
            eligibility = check_external_eligibility(page)
        except Exception as e:
            print()
            print(
                f"Could not perform pre-application eligibility check: {e}"
            )
            eligibility = "UNKNOWN"

        if eligibility == "INELIGIBLE":
            print()
            print("=" * 70)
            print("APPLICATION SKIPPED - INELIGIBLE")
            print("=" * 70)
            print(
                "The current job explicitly requires more professional "
                "experience than the candidate has."
            )
            print("No Easy Apply click or resume upload was performed.")
            record_application_status(job, "INELIGIBLE")
            return False

        # ---------------------------------------
        # Find Easy Apply
        # ---------------------------------------

        print()
        print(
            "Searching for Easy Apply button..."
        )

        easy_apply = (
            find_easy_apply_button(page)
        )

        # ---------------------------------------
        # Easy Apply not found
        # ---------------------------------------

        if easy_apply is None:

            # -------------------------------------------------------
            # External ATS fallback
            # -------------------------------------------------------
            # The CSV Easy Apply value is not trusted as proof of the
            # current application route. We inspect the live LinkedIn
            # page for a real external application destination.
            if ALLOW_EXTERNAL_APPLICATIONS:
                print()
                print("Searching for external application link...")

                external_link = find_external_apply_link(page)

                if external_link:
                    print()
                    print("=" * 70)
                    print("EXTERNAL APPLICATION FOUND")
                    print("=" * 70)
                    print(f"External URL: {external_link}")

                    eligibility = check_external_eligibility(page)

                    if eligibility == "INELIGIBLE":
                        print()
                        print("Skipping external application: candidate is ineligible.")
                        # Persist the eligibility decision so the same job is
                        # not reopened on future runs.
                        record_application_status(job, "INELIGIBLE")
                        return False

                    if not navigate_page(
                        page,
                        external_link,
                        timeout=30000,
                        settle_ms=3000,
                    ):
                        print()
                        print("Could not open the external application page.")
                        return False

                    print()
                    print(f"External page title: {page.title()}")
                    print(f"External current URL: {page.url}")

                    result = prepare_external_application_page(
                        page=page,
                        resume_path="resume/resume.pdf",
                        name="G Bhanu Prasad",
                        email="gbhanuprasad1236@gmail.com",
                        phone="9392801041",
                        current_location="Bengaluru",
                        current_company="N/A",
                    )

                    if result == "LOGIN_REQUIRED":
                        print()
                        print("=" * 70)
                        print("EXTERNAL APPLICATION REQUIRES LOGIN/ACCOUNT SETUP")
                        print("=" * 70)
                        print("No external submission was performed.")
                        print("This job will be skipped without asking for manual submission confirmation.")
                        record_application_status(job, "LOGIN_REQUIRED")
                        return False

                    if result == "READY_FOR_REVIEW":
                        print()
                        print("=" * 70)
                        print("EXTERNAL APPLICATION READY FOR REVIEW")
                        print("=" * 70)
                        print("No external submission was performed.")
                        print("Unattended mode: skipping this application.")
                        print("The automation will continue to the next eligible job.")

                        record_application_status(job, "READY_FOR_REVIEW")
                        return False

                    print()
                    print(f"External application stopped with status: {result}")
                    return False

            print()
            print("=" * 70)
            print("EASY APPLY NOT FOUND")
            print("=" * 70)

            print()
            print(
                "LinkedIn did not expose an "
                "Easy Apply control or a usable external application link."
            )

            print_application_controls(
                page
            )

            save_diagnostic_screenshot(
                page
            )

            return False

        # ---------------------------------------
        # Easy Apply found
        # ---------------------------------------

        print()
        print("=" * 70)
        print("EASY APPLY BUTTON FOUND")
        print("=" * 70)

        try:

            easy_apply.scroll_into_view_if_needed()

            page.wait_for_timeout(
                500
            )

            easy_apply.click(
                timeout=10000
            )

        except Exception as e:

            print()
            print(
                f"Normal click failed: {e}"
            )

            print(
                "Trying JavaScript click..."
            )

            try:

                easy_apply.evaluate(
                    "(element) => element.click()"
                )

            except Exception as js_error:

                print(
                    "JavaScript click failed:"
                )

                print(
                    js_error
                )

                return False

        # ---------------------------------------
        # Resolve the actual Easy Apply UI
        # ---------------------------------------
        original_page = page
        page.wait_for_timeout(3000)

        def has_application_ui(candidate_page):
            selectors = (
                ".jobs-easy-apply-modal",
                ".jobs-easy-apply-content",
                "[class*='jobs-easy-apply']",
                ".artdeco-modal[role='dialog']",
                "[aria-modal='true']",
                "[role='dialog']",
            )
            for selector in selectors:
                try:
                    locator = candidate_page.locator(selector)
                    for i in range(locator.count()):
                        el = locator.nth(i)
                        if not el.is_visible():
                            continue
                        try:
                            text = (el.inner_text() or "").lower()
                        except Exception:
                            text = ""
                        if any(token in text for token in (
                            "application", "resume", "contact info",
                            "work experience", "education", "submit application",
                            "review application", "continue to next step",
                        )) or "jobs-easy-apply" in (el.get_attribute("class") or ""):
                            return True
                except Exception:
                    continue
            return False

        if has_application_ui(original_page):
            page = original_page
            print("Easy Apply modal detected on the original LinkedIn job page.")
        else:
            # Check actual popups/new tabs only. Never switch to an arbitrary
            # LinkedIn page such as a company-home tab.
            for candidate_page in context.pages:
                if candidate_page is original_page:
                    continue
                try:
                    if "linkedin.com" not in (candidate_page.url or "").lower():
                        continue
                    if has_application_ui(candidate_page):
                        page = candidate_page
                        print("Easy Apply modal detected on an additional LinkedIn page.")
                        break
                except Exception:
                    continue

        if not has_application_ui(page):
            print()
            print("EASY APPLY MODAL NOT DETECTED")
            print(f"Current page URL after click: {page.url}")
            print("The automation will NOT process this page.")
            print("No form navigation or submission will be performed.")
            save_diagnostic_screenshot(original_page)
            return False

        print()
        print("=" * 70)
        print("EASY APPLY FORM OPENED")
        print("=" * 70)
        print(f"Application page URL: {page.url}")

        # ---------------------------------------
        # Run application form automation
        # ---------------------------------------

        try:

            application_result = inspect_and_prepare_form(
                page
            )

            if application_result == "SUBMITTED":
                tracker_success = record_application_status(
                    job,
                    "APPLIED"
                )

                if tracker_success:
                    print(
                        "\nConfirmed submission: tracker marked APPLIED."
                    )
                    return True

                print(
                    "\nSubmission was reported, but application tracking failed."
                )
                return False

            elif application_result == "READY_FOR_REVIEW":
                print()
                print("Form reached final review.")
                print("Unattended mode: submission was not confirmed.")
                print("Skipping this application and continuing.")

                record_application_status(job, "READY_FOR_REVIEW")
                return False

            else:
                print(
                    f"\nApplication automation stopped with status: "
                    f"{application_result}"
                )

        except Exception as e:

            print()
            print(
                "Application form automation "
                "failed:"
            )

            print(e)

            return False

        return False


# ---------------------------------------
# Main
# ---------------------------------------

def main():

    print()
    print("=" * 70)
    print("AI JOB AUTOMATION - JOB APPLICATION")
    print("=" * 70)

    # ---------------------------------------
    # Load eligible jobs
    # ---------------------------------------

    jobs = get_recommended_jobs()

    today_applied = get_today_applied_count()
    daily_remaining = MAX_APPLICATIONS_PER_RUN - today_applied

    print()
    print(
        f"Eligible jobs: {len(jobs)}"
    )
    print(
        f"Applications already submitted today: "
        f"{today_applied}/{MAX_APPLICATIONS_PER_RUN}"
    )

    if daily_remaining <= 0:
        print()
        print("=" * 70)
        print("DAILY APPLICATION LIMIT REACHED")
        print("=" * 70)
        print(
            f"Confirmed applications today: "
            f"{today_applied}/{MAX_APPLICATIONS_PER_RUN}"
        )
        return

    display_jobs(jobs)

    if not jobs:
        return

    print()

    # ---------------------------------------
    # Try eligible jobs until today's confirmed
    # application limit has been reached.
    # ---------------------------------------

    applications_this_run = 0

    for index in range(len(jobs)):

        if applications_this_run >= daily_remaining:
            print()
            print("=" * 70)
            print("APPLICATION LIMIT REACHED")
            print("=" * 70)
            print(
                f"Confirmed applications this run: "
                f"{applications_this_run}/{daily_remaining}"
            )
            break

        job = jobs[index]

        print()
        print("=" * 70)

        print(
            f"TRYING JOB "
            f"{index + 1}/{len(jobs)}"
        )

        print("=" * 70)

        print(
            f"Title : "
            f"{job.get('Title', '')}"
        )

        print(
            f"Score : "
            f"{job.get('Match Score', '')}"
        )

        # ---------------------------------------
        # Try job
        # ---------------------------------------
        # Easy Apply is verified LIVE inside
        # open_easy_apply(). The CSV value is only
        # a candidate hint because LinkedIn status
        # can change after the CSV is generated.

        success = open_easy_apply(job)

        if success:
            applications_this_run += 1

            print()
            print("=" * 70)
            print("APPLICATION CONFIRMED")
            print("=" * 70)
            print(
                f"Confirmed applications today: "
                f"{today_applied + applications_this_run}/{MAX_APPLICATIONS_PER_RUN}"
            )

            if applications_this_run >= daily_remaining:
                print()
                print("Daily confirmed-application limit reached.")
                break

        # ---------------------------------------
        # Try next job
        # ---------------------------------------

        if index + 1 < len(jobs):

            print()
            print(
                "Trying next eligible job..."
            )

    # ---------------------------------------
    # No active job found
    # ---------------------------------------

    print()
    print("=" * 70)

    print(
        "NO ACTIVE EASY APPLY JOB FOUND"
    )

    print("=" * 70)

    print(
        "All selected/remaining jobs "
        "were closed or unavailable."
    )


# ---------------------------------------
# Entry Point
# ---------------------------------------

if __name__ == "__main__":
    main()