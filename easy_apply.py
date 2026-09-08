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
MAX_APPLICATIONS_PER_RUN = 15

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
# Get Application Status
# ---------------------------------------

def get_application_statuses():
    tracker = load_csv(TRACKER_FILE)
    statuses = {}

    for row in tracker:
        title = (row.get("Title") or "").strip()

        application_status = (
            row.get("Application Status") or ""
        ).strip().upper()

        status = (
            row.get("Status") or ""
        ).strip().upper()

        # Application Status is authoritative when present. This fixes the
        # old inconsistent state where Application Status was NOT APPLIED
        # but Status was APPLIED.
        effective_status = (
            application_status
            if application_status
            else (status or "NOT APPLIED")
        )

        if title:
            statuses[title] = effective_status

    return statuses


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

    statuses = get_application_statuses()
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

        status = statuses.get(
            title,
            "NOT APPLIED"
        )

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

    return recommended[:MAX_APPLICATIONS_PER_RUN]




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
# Find Easy Apply Button
# ---------------------------------------

def find_easy_apply_button(page):
    """
    Find the application control for the CURRENT LinkedIn job.

    Priority:
      1. Explicit Easy Apply control.
      2. LinkedIn's accessibility label "LinkedIn Apply to this job".
      3. A generic Apply control only when exactly ONE visible Apply
         control exists on the page.

    This prevents clicking Apply buttons belonging to recommended jobs.
    """

    def visible(element):
        try:
            return element.is_visible()
        except Exception:
            return False

    def details(element):
        try:
            text = (element.inner_text() or "").strip()
        except Exception:
            text = ""

        aria = element.get_attribute("aria-label") or ""
        title = element.get_attribute("title") or ""
        return text, aria, title

    # -------------------------------------------------------
    # 1. Explicit Easy Apply controls
    # -------------------------------------------------------
    try:
        elements = page.locator("button, [role='button'], a")

        for i in range(elements.count()):
            element = elements.nth(i)

            if not visible(element):
                continue

            text, aria, title = details(element)
            combined = f"{text} {aria} {title}".lower()

            if "easy apply" in combined:
                print("Explicit Easy Apply control found.")
                return element

    except Exception:
        pass

    # -------------------------------------------------------
    # 2. Strong LinkedIn accessibility signal
    #
    # IMPORTANT:
    # LinkedIn may expose the current-job Apply button as:
    #   aria-label="LinkedIn Apply to this job"
    # without using the words "Easy Apply" anywhere in the
    # visible job description.
    #
    # This check MUST happen before external-application
    # detection and before requiring "easy apply" text.
    # -------------------------------------------------------
    try:
        elements = page.locator("button, [role='button'], a")

        for i in range(elements.count()):
            element = elements.nth(i)

            if not visible(element):
                continue

            text, aria, title = details(element)
            combined = f"{text} {aria} {title}".lower()

            if "linkedin apply to this job" in combined:
                print("LinkedIn Apply control found.")
                return element

    except Exception:
        pass

    # LinkedIn can finish rendering the top-card control after
    # the page initially loads.
    try:
        page.wait_for_timeout(1500)
    except Exception:
        pass

    try:
        elements = page.locator("button, [role='button'], a")

        for i in range(elements.count()):
            element = elements.nth(i)

            if not visible(element):
                continue

            text, aria, title = details(element)
            combined = f"{text} {aria} {title}".lower()

            if "linkedin apply to this job" in combined:
                print("LinkedIn Apply control found after render.")
                return element

    except Exception:
        pass

    # -------------------------------------------------------
    # 3. Inspect page text for Easy Apply / external evidence
    # -------------------------------------------------------
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

    has_easy_apply_evidence = any(
        signal in body_lower
        for signal in easy_apply_signals
    )

    if not has_easy_apply_evidence:
        return None

    print("Easy Apply confirmed from job description.")

    # -------------------------------------------------------
    # 4. Re-check LinkedIn accessibility signal
    # -------------------------------------------------------
    try:
        elements = page.locator("button, [role='button'], a")

        for i in range(elements.count()):
            element = elements.nth(i)

            if not visible(element):
                continue

            text, aria, title = details(element)
            combined = f"{text} {aria} {title}".lower()

            if "linkedin apply to this job" in combined:
                print("LinkedIn Apply control found.")
                return element

    except Exception:
        pass

    # LinkedIn can finish rendering the top-card control after the page
    # initially loads.
    try:
        page.wait_for_timeout(1500)
    except Exception:
        pass

    try:
        elements = page.locator("button, [role='button'], a")

        for i in range(elements.count()):
            element = elements.nth(i)

            if not visible(element):
                continue

            text, aria, title = details(element)
            combined = f"{text} {aria} {title}".lower()

            if "linkedin apply to this job" in combined:
                print("LinkedIn Apply control found after render.")
                return element

    except Exception:
        pass

    # -------------------------------------------------------
    # 4. Generic Apply fallback — ONLY if unique
    # -------------------------------------------------------
    apply_candidates = []

    try:
        elements = page.locator("button, [role='button'], a")

        for i in range(elements.count()):
            element = elements.nth(i)

            if not visible(element):
                continue

            text, aria, title = details(element)

            if text.strip().lower() == "apply":
                apply_candidates.append(element)

    except Exception:
        pass

    if len(apply_candidates) == 1:
        print("Unique LinkedIn Apply control found.")
        return apply_candidates[0]

    if len(apply_candidates) > 1:
        print(
            f"Found {len(apply_candidates)} generic Apply controls; "
            "refusing to guess which one belongs to the current job."
        )

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
# Record Application Status
# ---------------------------------------

def record_application_status(job, status):
    """
    Update the tracker for the job after a confirmed application result.

    The function adapts to the existing CSV headers instead of assuming
    a fixed tracker schema.
    """

    try:
        if not os.path.exists(TRACKER_FILE):
            print(
                f"Tracker file not found: {TRACKER_FILE}"
            )
            return False

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

        title = (
            job.get("Title", "")
            .strip()
            .lower()
        )

        company = (
            job.get("Company", "")
            .strip()
            .lower()
        )

        updated = False

        for row in rows:
            row_title = (
                row.get("Title", "")
                .strip()
                .lower()
            )

            row_company = (
                row.get("Company", "")
                .strip()
                .lower()
            )

            title_match = title and row_title == title
            company_match = (
                not company
                or not row_company
                or row_company == company
            )

            if title_match and company_match:
                row["Status"] = status

                if "Application Status" in fieldnames:
                    row["Application Status"] = status

                if status == "APPLIED" and "Applied Date" in fieldnames:
                    from datetime import datetime
                    row["Applied Date"] = datetime.now().strftime("%Y-%m-%d")

                updated = True
                break

        if not updated:
            new_row = {
                field: ""
                for field in fieldnames
            }

            new_row["Title"] = job.get("Title", "")
            new_row["Company"] = job.get("Company", "")
            new_row["Location"] = job.get("Location", "")
            new_row["Status"] = status

            if "Application Status" in fieldnames:
                new_row["Application Status"] = status

            if "URL" in fieldnames:
                new_row["URL"] = job.get("URL", "")

            if status == "APPLIED" and "Applied Date" in fieldnames:
                from datetime import datetime
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

        print()
        print(
            f"Application tracker updated: {status}"
        )
        return True

    except Exception as e:
        print(
            f"Could not update application tracker: {e}"
        )
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
                    "\nForm reached final review."
                )
                print(
                    "AUTO_SUBMIT is disabled, so tracker remains NOT APPLIED."
                )
                print()
                print("The browser will remain open on the final review page.")
                print("Review the application and submit manually if appropriate.")
                input("Press Enter only after you finish reviewing the application...")

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