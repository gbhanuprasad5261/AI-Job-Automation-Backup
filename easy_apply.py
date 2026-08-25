import csv
import os
import re

from application_form import inspect_and_prepare_form
from playwright.sync_api import sync_playwright


# ---------------------------------------
# Configuration
# ---------------------------------------

ANALYSIS_FILE = "data/job_analysis.csv"
TRACKER_FILE = "data/application_tracker.csv"

MIN_MATCH_SCORE = 70

CHROME_CDP_URL = "http://127.0.0.1:9222"


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

def _job_key(row):
    """
    Create a stable identifier for a LinkedIn job.

    LinkedIn job ID is preferred because job titles can be duplicated.
    """

    link = (
        row.get("Link")
        or row.get("URL")
        or ""
    ).strip().lower()

    # Prefer LinkedIn job ID
    if link:
        match = re.search(
            r"/jobs/view/(\d+)",
            link
        )

        if match:
            return f"id:{match.group(1)}"

        # Fallback to complete URL
        return f"url:{link.rstrip('/')}"

    # Final fallback when URL is unavailable
    title = (
        row.get("Title")
        or ""
    ).strip().lower()

    company = (
        row.get("Company")
        or ""
    ).strip().lower()

    return f"text:{title}|{company}"


def get_application_statuses():

    tracker = load_csv(TRACKER_FILE)

    statuses = {}

    for row in tracker:

        key = _job_key(row)

        if not key:
            continue

        status = (
            row.get("Status")
            or row.get("Application Status")
            or "NOT APPLIED"
        ).strip().upper()

        # Empty status means NOT APPLIED
        if not status:
            status = "NOT APPLIED"

        statuses[key] = status

    return statuses

# ---------------------------------------
# Select Recommended Jobs
# ---------------------------------------

def get_recommended_jobs():

    jobs = load_csv(ANALYSIS_FILE)

    if not jobs:
        return []

    statuses = get_application_statuses()

    recommended = []

    # Jobs with these statuses must never be
    # automatically offered again.
    blocked_statuses = {
        "APPLIED",
        "SUBMITTED",
        "INTERVIEW",
        "REJECTED",
        "WITHDRAWN",
    }

    for job in jobs:

        # ---------------------------------------
        # Match score
        # ---------------------------------------

        try:
            score = float(
                str(
                    job.get(
                        "Match Score",
                        "0"
                    )
                ).replace("%", "").strip()
            )

        except (ValueError, AttributeError):
            score = 0

        # ---------------------------------------
        # Basic job information
        # ---------------------------------------

        title = (
            job.get(
                "Title",
                ""
            )
            or ""
        ).strip()

        link = (
            job.get(
                "Link",
                ""
            )
            or ""
        ).strip()

        if not title or not link:
            continue

        # ---------------------------------------
        # Get application status
        # ---------------------------------------

        key = _job_key(job)

        status = statuses.get(
            key,
            "NOT APPLIED"
        )

        status = (
            status
            or "NOT APPLIED"
        ).strip().upper()

        # ---------------------------------------
        # Filter 1:
        # Minimum match score
        # ---------------------------------------

        if score < MIN_MATCH_SCORE:
            continue

        # ---------------------------------------
        # Filter 2:
        # Already applied / progressed jobs
        # ---------------------------------------

        if status in blocked_statuses:
            continue

        # ---------------------------------------
        # Add job
        # ---------------------------------------

        recommended.append(job)

    # ---------------------------------------
    # Highest score first
    # ---------------------------------------

    recommended.sort(
        key=lambda job: float(
            str(
                job.get(
                    "Match Score",
                    "0"
                )
            ).replace("%", "").strip()
            or 0
        ),
        reverse=True
    )

    return recommended


# ---------------------------------------
# Tracker helpers
# ---------------------------------------

def update_tracker_status(job, status):
    """
    Update the tracker row for the exact LinkedIn job.
    Matching is done by job ID, not title, so duplicate titles are safe.
    """
    if not os.path.exists(TRACKER_FILE):
        return False

    try:
        with open(TRACKER_FILE, "r", newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
            fieldnames = list(rows[0].keys()) if rows else []

        if not rows or not fieldnames:
            return False

        if "Status" not in fieldnames:
            fieldnames.append("Status")

        if "Application Status" not in fieldnames:
            fieldnames.append("Application Status")

        if "Applied Date" not in fieldnames:
            fieldnames.append("Applied Date")

        target_key = _job_key(job)
        today = __import__("datetime").date.today().isoformat()

        updated = False

        for row in rows:
            if _job_key(row) != target_key:
                continue

            row["Status"] = status

            # Keep both status columns consistent because older tracker
            # files contain both fields.
            row["Application Status"] = status

            if status in {"APPLIED", "SUBMITTED"}:
                row["Applied Date"] = today

            updated = True
            break

        if not updated:
            return False

        with open(TRACKER_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=fieldnames,
                extrasaction="ignore"
            )
            writer.writeheader()
            writer.writerows(rows)

        print(f"Tracker updated: {status}")
        return True

    except Exception as e:
        print(f"Tracker update failed: {e}")
        return False


def page_shows_submitted(page):
    """
    Detect LinkedIn's explicit post-submission state.
    """
    try:
        text = page.locator("body").inner_text().lower()
    except Exception:
        return False

    submitted_signals = [
        "application submitted",
        "your application has been submitted",
        "application was submitted",
        "you applied",
        "applied to this job",
    ]

    return any(signal in text for signal in submitted_signals)


def page_shows_already_applied(page):
    """
    Detect an already-submitted application before trying to click Apply.
    """
    return page_shows_submitted(page)


def interpret_application_result(result):
    """
    Normalize application_form.py's return value without assuming a
    particular return type.
    """
    if isinstance(result, str):
        value = result.strip().upper()
    elif isinstance(result, dict):
        value = str(
            result.get("status")
            or result.get("result")
            or ""
        ).strip().upper()
    else:
        value = str(result or "").strip().upper()

    if "SUBMITTED" in value or "APPLIED" in value:
        return "SUBMITTED"

    if "READY_FOR_REVIEW" in value:
        return "READY_FOR_REVIEW"

    if "SKIPPED" in value:
        return "SKIPPED"

    if "STOPPED" in value:
        return "STOPPED"

    return value


# ---------------------------------------
# Display Jobs
# ---------------------------------------

def display_jobs(jobs):

    print()
    print("=" * 70)
    print("RECOMMENDED EASY APPLY JOBS")
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
# Find Easy Apply Button
# ---------------------------------------

def find_easy_apply_button(page):
    """
    Find the MAIN LinkedIn application control.

    LinkedIn can expose the main control as "Apply" rather than
    "Easy Apply". Never select an Apply button from a related-job card.
    """

    def is_visible(element):
        try:
            return element.is_visible()
        except Exception:
            return False

    def attrs(element):
        try:
            text = (element.inner_text() or "").strip()
        except Exception:
            text = ""
        aria = element.get_attribute("aria-label") or ""
        title = element.get_attribute("title") or ""
        return text, aria, title

    def is_main_apply(element):
        text, aria, title = attrs(element)
        combined = f"{text} {aria} {title}".lower()

        if "easy apply" in combined:
            return True

        if "linkedin apply to this job" in combined:
            return True

        if text.lower().strip() != "apply":
            return False

        # Prefer the actual job-details/top-card area.
        scoped = [
            "xpath=ancestor::main[1]",
            "xpath=ancestor::*[contains(@class,'jobs-details')][1]",
            "xpath=ancestor::*[contains(@class,'jobs-unified-top-card')][1]",
            "xpath=ancestor::*[contains(@class,'job-details')][1]",
        ]

        for selector in scoped:
            try:
                ancestor = element.locator(selector).first
                if ancestor.count() > 0 and ancestor.is_visible():
                    return True
            except Exception:
                pass

        # Explicitly reject common related-job/search-card ancestors.
        related = [
            "xpath=ancestor::*[contains(@class,'job-card')][1]",
            "xpath=ancestor::*[contains(@class,'jobs-search-results')][1]",
            "xpath=ancestor::*[contains(@class,'base-card')][1]",
            "xpath=ancestor::*[contains(@class,'jobs-home-job-card')][1]",
        ]

        for selector in related:
            try:
                ancestor = element.locator(selector).first
                if ancestor.count() > 0:
                    return False
            except Exception:
                pass

        return False

    def scan(selector):
        try:
            elements = page.locator(selector)
            for i in range(elements.count()):
                try:
                    element = elements.nth(i)
                    if is_visible(element) and is_main_apply(element):
                        return element
                except Exception:
                    continue
        except Exception:
            pass
        return None

    # First pass: explicit controls and main-job Apply controls.
    for selector in [
        "button",
        "[role='button']",
        "a",
    ]:
        found = scan(selector)
        if found is not None:
            print("LinkedIn main application control found.")
            return found

    try:
        body = page.locator("body").inner_text()
    except Exception:
        body = ""

    body_lower = body.lower()

    external_signals = [
        "apply on company website",
        "apply on the company website",
        "apply externally",
        "application on company website",
        "apply via company website",
    ]

    if any(signal in body_lower for signal in external_signals):
        print("External application detected.")
        return None

    easy_apply_signals = [
        "easy apply button",
        "submit your application through the easy apply button",
        "apply through the easy apply button",
        "easy apply",
    ]

    if not any(signal in body_lower for signal in easy_apply_signals):
        return None

    print("Easy Apply confirmed from job description.")

    # LinkedIn can render the top-card control asynchronously.
    try:
        page.wait_for_timeout(1500)
    except Exception:
        pass

    for selector in [
        "main button",
        "main [role='button']",
        "main a",
        ".jobs-details button",
        ".jobs-details [role='button']",
        ".jobs-details a",
        ".jobs-unified-top-card button",
        ".jobs-unified-top-card [role='button']",
        ".jobs-unified-top-card a",
    ]:
        found = scan(selector)
        if found is not None:
            print("LinkedIn main application control found.")
            return found

    return None


# ---------------------------------------
# Check Whether Job Is Closed
# ---------------------------------------

def is_job_closed(body_text):

    closed_messages = [

        "No longer accepting applications",

        "This job is no longer accepting applications",

        "Job is no longer accepting applications"
    ]

    text = body_text.lower()

    for message in closed_messages:

        if message.lower() in text:

            return True

    return False


# ---------------------------------------
# Print Application Controls
# ---------------------------------------

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

        try:

            page.goto(
                link,
                wait_until="domcontentloaded",
                timeout=30000
            )

            page.wait_for_timeout(
                5000
            )

        except Exception as e:

            print()
            print(
                f"Could not open job: {e}"
            )

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

            # A submitted application no longer has an Apply button.
            # Detect that state before reporting Easy Apply as unavailable.
            if page_shows_already_applied(page):

                print()
                print("=" * 70)
                print("APPLICATION ALREADY SUBMITTED")
                print("=" * 70)

                print(
                    "LinkedIn indicates that this job "
                    "has already been applied to."
                )

                update_tracker_status(
                    job,
                    "APPLIED"
                )

                return False

            print()
            print("=" * 70)
            print("EASY APPLY NOT FOUND")
            print("=" * 70)

            print()
            print(
                "LinkedIn did not expose an "
                "Easy Apply control."
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
        # Wait for application form
        # ---------------------------------------

        page.wait_for_timeout(
            3000
        )

        print()
        print("=" * 70)
        print("EASY APPLY FORM OPENED")
        print("=" * 70)

        # ---------------------------------------
        # Run application form automation
        # ---------------------------------------

        try:

            form_result = inspect_and_prepare_form(
                page
            )

        except Exception as e:

            print()
            print(
                "Application form automation "
                "failed:"
            )

            print(e)

            update_tracker_status(
                job,
                "FAILED"
            )

            return False

        # Always check the actual LinkedIn page after the form handler.
        # This is the strongest signal that submission really happened.
        if page_shows_submitted(page):

            print()
            print("=" * 70)
            print("APPLICATION SUBMITTED")
            print("=" * 70)

            update_tracker_status(
                job,
                "APPLIED"
            )

            return True

        result_status = interpret_application_result(
            form_result
        )

        print()
        print(
            f"Application form result: "
            f"{result_status or 'UNKNOWN'}"
        )

        if result_status == "SUBMITTED":

            update_tracker_status(
                job,
                "APPLIED"
            )

            return True

        if result_status == "READY_FOR_REVIEW":

            update_tracker_status(
                job,
                "READY_FOR_REVIEW"
            )

            print(
                "Application is prepared but was "
                "NOT confirmed as submitted."
            )

            return False

        if result_status in {
            "SKIPPED",
            "STOPPED",
            "FAILED",
        }:

            print(
                "Application was NOT confirmed "
                "as submitted."
            )

            return False

        print(
            "Application submission could not be "
            "confirmed. Tracker will not be marked APPLIED."
        )

        return False


# ---------------------------------------
# Main
# ---------------------------------------

def main():

    print()
    print("=" * 70)
    print("AI JOB AUTOMATION - EASY APPLY")
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
            print("APPLICATION COMPLETED")
            print("=" * 70)

            print(
                "The application was confirmed as submitted."
            )

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