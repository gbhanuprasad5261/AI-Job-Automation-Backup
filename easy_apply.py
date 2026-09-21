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
MAX_APPLICATIONS_PER_RUN = 1
MAX_CANDIDATE_JOBS_PER_RUN = 10

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

def _wait_for_cookie_consent(page, timeout_ms=8000):
    """Automatically accept clearly identified cookie/privacy banners."""
    import re
    import time

    phrases = (
        "we use cookies",
        "cookie preferences",
        "cookie consent",
        "cookie policy",
        "cookies necessary",
        "use cookies",
        "privacy preferences",
        "privacy notice",
        "data privacy",
    )
    reject_words = (
        "reject", "decline", "deny", "do not accept",
        "necessary only", "only necessary",
    )

    def visible(el):
        try:
            return el.is_visible()
        except Exception:
            return False

    def label(el):
        try:
            values = [
                el.inner_text() or "",
                el.get_attribute("aria-label") or "",
                el.get_attribute("title") or "",
                el.get_attribute("value") or "",
            ]
            return re.sub(r"\s+", " ", " ".join(values).lower()).strip()
        except Exception:
            return ""

    def accept_label(value):
        if not value or any(x in value for x in reject_words):
            return False
        return bool(re.search(
            r"\b(?:accept(?:\s+all)?(?:\s+(?:cookies?|tracking|optional))?"
            r"|allow(?:\s+all)?(?:\s+(?:cookies?|tracking|optional))?"
            r"|agree|i\s+agree|consent)\b",
            value,
            re.I,
        ))

    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        try:
            body = page.locator("body").inner_text() or ""
            if any(p in body.lower() for p in phrases):
                controls = page.locator(
                    "button, [role='button'], input[type='button'], "
                    "input[type='submit'], a"
                )
                candidates = []
                for i in range(controls.count()):
                    el = controls.nth(i)
                    if not visible(el):
                        continue
                    text = label(el)
                    if accept_label(text):
                        candidates.append((el, text))

                # Cookie-labelled accept controls first.
                for el, text in candidates:
                    if "cookie" in text or "cookies" in text:
                        el.click(timeout=5000)
                        page.wait_for_timeout(800)
                        return True

                # Prefer Accept All/Allow All.
                for el, text in candidates:
                    if "accept all" in text or "allow all" in text:
                        el.click(timeout=5000)
                        page.wait_for_timeout(800)
                        return True

                # A single unambiguous consent button is safe.
                if len(candidates) == 1:
                    candidates[0][0].click(timeout=5000)
                    page.wait_for_timeout(800)
                    return True
        except Exception:
            pass

        try:
            page.wait_for_timeout(300)
        except Exception:
            time.sleep(0.3)

    return False


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
    candidates = {(row.get("Application Status") or "").strip().upper(), (row.get("Status") or "").strip().upper()}
    if "APPLIED" in candidates: return "APPLIED"
    if "READY_FOR_REVIEW" in candidates: return "READY_FOR_REVIEW"
    if "INELIGIBLE" in candidates: return "INELIGIBLE"
    if "LOGIN_REQUIRED" in candidates: return "LOGIN_REQUIRED"
    if "CLOSED" in candidates: return "CLOSED"
    return next((x for x in candidates if x), "NOT APPLIED")

def _normalize_url(value):
    return (value or "").strip().lower().split("?", 1)[0].rstrip("/")

def _normalize_text(value):
    return " ".join((value or "").strip().lower().split())

def get_application_statuses():
    tracker = load_csv(TRACKER_FILE); statuses = {}
    priority = {"NOT APPLIED":0,"CLOSED":1,"LOGIN_REQUIRED":2,"INELIGIBLE":3,"READY_FOR_REVIEW":4,"APPLIED":5}
    for row in tracker:
        title=(row.get("Title") or "").strip()
        if not title: continue
        status=_effective_tracker_status(row); old=statuses.get(title)
        if old is None or priority.get(status,0)>priority.get(old,0): statuses[title]=status
    return statuses

def get_application_status(job):
    if _history_status_for_job(job) == "APPLIED":
        return "APPLIED"

    tracker = load_csv(TRACKER_FILE)
    job_url = _normalize_url(convert_to_job_url(job.get("Link", "")))
    title = _normalize_text(job.get("Title", "")); company = _normalize_text(job.get("Company", ""))
    priority = {"NOT APPLIED":0,"CLOSED":1,"LOGIN_REQUIRED":2,"INELIGIBLE":3,"READY_FOR_REVIEW":4,"APPLIED":5}
    best="NOT APPLIED"
    if job_url:
        for row in tracker:
            row_url=_normalize_url(row.get("URL") or row.get("Link") or "")
            if row_url==job_url:
                s=_effective_tracker_status(row)
                if priority.get(s,0)>priority.get(best,0): best=s
        if best!="NOT APPLIED": return best
    for row in tracker:
        if title and company and _normalize_text(row.get("Title"))==title and _normalize_text(row.get("Company"))==company:
            s=_effective_tracker_status(row)
            if priority.get(s,0)>priority.get(best,0): best=s
    return best


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

    # Keep the application limit at 1, but retain several eligible candidates
    # so closed/unavailable jobs can be skipped without ending the run.
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
    """Find the Easy Apply control for the CURRENT LinkedIn job only."""

    def visible(element):
        try:
            return element.is_visible()
        except Exception:
            return False

    def describe(element):
        attrs = {}
        for name in ("aria-label", "title", "href", "class"):
            try:
                attrs[name] = element.get_attribute(name) or ""
            except Exception:
                attrs[name] = ""
        try:
            attrs["text"] = (element.inner_text() or "").strip()
        except Exception:
            attrs["text"] = ""
        return attrs

    def visible_candidates(selector):
        try:
            locator = page.locator(selector)
            return [
                locator.nth(i)
                for i in range(locator.count())
                if visible(locator.nth(i))
            ]
        except Exception:
            return []

    # LinkedIn can render Easy Apply buttons on recommended-job cards.
    # Therefore never scan every page-wide button for the words Easy Apply.
    current_job_selectors = (
        # New LinkedIn UI: this exact accessible name explicitly refers to
        # the current job, so it is safe to prefer over page-wide matches.
        ".jobs-details__main-content [aria-label='Easy Apply to this job']",
        "main [aria-label='Easy Apply to this job']",
        "[aria-label='Easy Apply to this job']",
        ".jobs-details__main-content button.jobs-apply-button",
        ".jobs-details__main-content [aria-label^='LinkedIn Apply to']",
        ".jobs-details__main-content button[aria-label*='Easy Apply']",
        ".jobs-details__main-content [role='button'][aria-label*='Easy Apply']",
        "main button.jobs-apply-button",
        "main [aria-label^='LinkedIn Apply to']",
        "main [role='button'][aria-label*='Easy Apply']",
    )

    for selector in current_job_selectors:
        for element in visible_candidates(selector):
            data = describe(element)
            combined = f"{data['text']} {data['aria-label']} {data['title']}".lower()
            if (
                "easy apply" in combined
                or "linkedin apply to" in combined
                or "openSDUIApplyFlow=true" in data["href"]
                or "jobs-apply-button" in data["class"]
            ):
                print("Current-job Easy Apply control found.")
                return element

    # New LinkedIn UI can expose the apply flow through a stable aria label.
    candidates = visible_candidates("[aria-label^='LinkedIn Apply to']")
    if len(candidates) == 1:
        print("Unique LinkedIn Apply control found.")
        return candidates[0]

    # Only accept a page-wide jobs-apply-button when it is unique.
    candidates = visible_candidates("button.jobs-apply-button")
    if len(candidates) == 1:
        data = describe(candidates[0])
        combined = f"{data['text']} {data['aria-label']} {data['title']}".lower()
        if "easy apply" in combined or "linkedin apply to" in combined or "openSDUIApplyFlow=true" in data["href"]:
            print("Unique LinkedIn Easy Apply control found.")
            return candidates[0]

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

                    if result == "READY_FOR_REVIEW":
                        print()
                        print("=" * 70)
                        print("EXTERNAL APPLICATION NOT SUBMITTED")
                        print("=" * 70)
                        print(
                            "Automation could not safely verify a completed submission."
                        )
                        print(
                            "Tracker remains NOT APPLIED. Continuing automatically..."
                        )
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

        def has_application_ui(candidate_page):
            """
            Detect LinkedIn Easy Apply using BOTH DOM and URL evidence.

            LinkedIn can launch Easy Apply as an internal route such as:
              ?companyName=...&applicantTrackingSystemName=LinkedIn

            In that state, the classic .jobs-easy-apply-modal selector may
            not be exposed even though the Easy Apply flow is active.
            """
            try:
                url = (candidate_page.url or "").lower()
            except Exception:
                url = ""

            # Strong LinkedIn Easy Apply route signal.
            linkedin_apply_route = (
                "applicanttrackingsystemname=linkedin" in url
                and "companyname=" in url
            )

            selectors = (
                ".jobs-easy-apply-modal",
                ".jobs-easy-apply-content",
                "[class*='jobs-easy-apply']",
                ".artdeco-modal[role='dialog']",
                "[aria-modal='true']",
                "[role='dialog']",
                "section[aria-label*='application' i]",
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

                        classes = (
                            el.get_attribute("class") or ""
                        ).lower()

                        if (
                            "jobs-easy-apply" in classes
                            or any(token in text for token in (
                                "application",
                                "resume",
                                "contact info",
                                "work experience",
                                "education",
                                "submit application",
                                "review application",
                                "continue to next step",
                            ))
                        ):
                            return True
                except Exception:
                    continue

            # URL itself is strong evidence that the Easy Apply route opened.
            # We deliberately require the LinkedIn-specific query parameters,
            # so a normal LinkedIn job URL is not treated as an application.
            if linkedin_apply_route:
                return True

            return False

        # LinkedIn may need several seconds to mount its application UI.
        # Poll instead of taking one screenshot after a fixed 3-second wait.
        application_page_found = False

        for _ in range(24):
            if has_application_ui(original_page):
                page = original_page
                application_page_found = True
                print("LinkedIn Easy Apply flow detected on the original job page.")
                break

            # Check only additional LinkedIn pages. Never switch to an
            # arbitrary tab such as a company or unrelated LinkedIn page.
            for candidate_page in list(context.pages):
                if candidate_page is original_page:
                    continue

                try:
                    candidate_url = (candidate_page.url or "").lower()
                    if "linkedin.com" not in candidate_url:
                        continue

                    if has_application_ui(candidate_page):
                        page = candidate_page
                        application_page_found = True
                        print(
                            "LinkedIn Easy Apply flow detected on an additional page."
                        )
                        break
                except Exception:
                    continue

            if application_page_found:
                break

            try:
                page.wait_for_timeout(500)
            except Exception:
                pass

        if not application_page_found:
            print()
            print("EASY APPLY FLOW NOT DETECTED")
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
                record_application_status(
                    job,
                    "APPLIED"
                )
                print(
                    "\nConfirmed submission: tracker marked APPLIED."
                )

            elif application_result == "READY_FOR_REVIEW":
                print(
                    "\nApplication reached a review/unknown-field state."
                )
                print(
                    "Automation could not safely verify submission."
                )
                print(
                    "Tracker remains NOT APPLIED. Continuing automatically..."
                )

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

        return True


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

    print()
    print(
        f"Eligible jobs: {len(jobs)}"
    )

    display_jobs(jobs)

    if not jobs:
        return

    print()

    # ---------------------------------------
    # Select starting job
    # ---------------------------------------

    try:

        choice = int(
            input(
                f"Select starting job "
                f"(1-{len(jobs)}): "
            )
        )

    except ValueError:

        print(
            "Invalid selection."
        )

        return

    if choice < 1 or choice > len(jobs):

        print(
            "Invalid job number."
        )

        return

    # ---------------------------------------
    # Try selected and following jobs
    # ---------------------------------------

    for index in range(
        choice - 1,
        len(jobs)
    ):

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

        # ---------------------------------------
        # Active Easy Apply found
        # ---------------------------------------

        if success:

            print()
            print("=" * 70)

            print(
                "READY FOR APPLICATION AUTOMATION"
            )

            print("=" * 70)

            return

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