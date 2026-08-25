import csv
import re
from urllib.parse import quote

from playwright.sync_api import sync_playwright

try:
    from config import (
        SEARCH_KEYWORDS,
        MAX_JOBS,
        EASY_APPLY_FILTER,
        TARGET_LOCATIONS,
        CHROME_CDP_URL,
    )
except ImportError:
    SEARCH_KEYWORDS = ("Java Backend Developer",)
    MAX_JOBS = 20
    EASY_APPLY_FILTER = True
    TARGET_LOCATIONS = ("bengaluru", "bangalore", "hyderabad", "chennai", "remote")
    CHROME_CDP_URL = "http://127.0.0.1:9222"

SEARCH_KEYWORD = SEARCH_KEYWORDS[0]
OUTPUT_FILE = "jobs.csv"


# =======================================
# Build LinkedIn Search URL
# =======================================

def build_search_url(location=None):

    keyword = quote(SEARCH_KEYWORD)

    url = (
        "https://www.linkedin.com/jobs/search/"
        f"?keywords={keyword}"
    )

    if location:
        url += f"&location={quote(location)}"

    if EASY_APPLY_FILTER:

        url += "&f_AL=true"

    return url


# =======================================
# Extract Job ID
# =======================================

def extract_job_id(url):

    if not url:
        return ""

    # Example:
    # ?currentJobId=4452950405

    match = re.search(
        r"currentJobId=(\d+)",
        url
    )

    if match:
        return match.group(1)

    # Example:
    # /jobs/view/4452950405/

    match = re.search(
        r"/jobs/view/(\d+)",
        url
    )

    if match:
        return match.group(1)

    return ""


# =======================================
# Build Job URL
# =======================================

def build_job_url(job_id):

    if not job_id:
        return ""

    return (
        "https://www.linkedin.com/jobs/view/"
        f"{job_id}/"
    )


# =======================================
# Extract Company
# =======================================

def extract_company(page):

    selectors = [

        "a[href*='/company/']",

        "div.job-details-jobs-unified-top-card__company-name a",

        "div.job-details-jobs-unified-top-card__company-name",

        "a.jobs-unified-top-card__company-name"
    ]

    for selector in selectors:

        try:

            locator = page.locator(
                selector
            ).first

            if locator.count() == 0:
                continue

            if not locator.is_visible():
                continue

            value = (
                locator
                .inner_text()
                .strip()
            )

            if value:
                return value

        except Exception:

            continue

    return ""


# =======================================
# Extract Location
# =======================================

def extract_location(page, body=""):

    # ---------------------------------------
    # First try known LinkedIn selectors
    # ---------------------------------------

    selectors = [

        "div.job-details-jobs-unified-top-card__primary-description-container",

        "div.job-details-jobs-unified-top-card__primary-description",

        "span.jobs-unified-top-card__bullet",

        "div.jobs-unified-top-card__primary-description",

        "span.topcard__flavor--bullet",

        "span.jobs-unified-top-card__bullet"
    ]

    for selector in selectors:

        try:

            locator = page.locator(
                selector
            ).first

            if locator.count() == 0:
                continue

            if not locator.is_visible():
                continue

            value = (
                locator
                .inner_text()
                .strip()
            )

            if value:

                # LinkedIn may return:
                #
                # India · 6 days ago · Over 100 applicants
                #
                # We only want the first part.

                first_part = (
                    value
                    .split("·")[0]
                    .strip()
                )

                if first_part:
                    return first_part

        except Exception:

            continue

    # ---------------------------------------
    # Fallback: inspect body text
    # ---------------------------------------

    if body:

        try:

            lines = [
                line.strip()
                for line in body.splitlines()
                if line.strip()
            ]

            for line in lines:

                lower = line.lower()

                # Common LinkedIn format:
                #
                # India · 6 days ago · Over 100 applicants
                #
                if (
                    "·" in line
                    and (
                        "ago" in lower
                        or "applicant" in lower
                    )
                ):

                    possible_location = (
                        line
                        .split("·")[0]
                        .strip()
                    )

                    if (
                        possible_location
                        and len(possible_location) < 150
                    ):

                        return possible_location

        except Exception:

            pass

    return ""


# =======================================
# Extract Job Title
# =======================================

def extract_job_title(page):

    # ---------------------------------------
    # Method 1: h1
    # ---------------------------------------

    selectors = [

        "h1",

        "h1.t-24",

        "h1.jobs-unified-top-card__job-title",

        "h1.job-details-jobs-unified-top-card__job-title"
    ]

    for selector in selectors:

        try:

            locator = page.locator(
                selector
            ).first

            if locator.count() == 0:
                continue

            if not locator.is_visible():
                continue

            value = (
                locator
                .inner_text()
                .strip()
            )

            if value:
                return value

        except Exception:

            continue

    # ---------------------------------------
    # Method 2: Page title
    # ---------------------------------------

    try:

        browser_title = (
            page.title()
            .strip()
        )

        if browser_title:

            # Example:
            #
            # Software Engineer | Remote |
            # CodeGeniusRecruit | LinkedIn
            #
            # We want:
            #
            # Software Engineer | Remote

            if "|" in browser_title:

                parts = [
                    part.strip()
                    for part
                    in browser_title.split("|")
                ]

                if parts:

                    # Remove company and LinkedIn
                    # from the end when possible.

                    if (
                        len(parts) >= 3
                        and parts[-1].lower()
                        == "linkedin"
                    ):

                        title_parts = parts[:-2]

                    else:

                        title_parts = parts[:-1]

                    title = (
                        " | ".join(
                            title_parts
                        )
                        .strip()
                    )

                    if title:
                        return title

            return browser_title

    except Exception:

        pass

    # ---------------------------------------
    # Method 3: Body text
    # ---------------------------------------

    try:

        body = page.locator(
            "body"
        ).inner_text()

        lines = [
            line.strip()
            for line in body.splitlines()
            if line.strip()
        ]

        # Look near the beginning of
        # the job page for a likely title.

        for index, line in enumerate(lines):

            if (
                line.lower()
                in [
                    "apply",
                    "save",
                    "easy apply"
                ]
            ):

                if index > 0:

                    candidate = (
                        lines[index - 1]
                        .strip()
                    )

                    if (
                        candidate
                        and len(candidate) < 200
                    ):

                        return candidate

    except Exception:

        pass

    return "Unknown Job"


# =======================================
# Detect LIVE Easy Apply
# =======================================

def detect_easy_apply(page):

    """
    Detect whether the current LinkedIn job
    supports LinkedIn Easy Apply.

    LinkedIn may display the visible button
    simply as "Apply", so button text alone
    is NOT enough.

    We use:

    1. Explicit "Easy Apply" text
    2. Job description mentioning
       "Easy Apply button"
    3. Reject explicit external application
    4. Inspect visible controls
    """

    try:

        body = (
            page.locator(
                "body"
            ).inner_text()
        )

    except Exception:

        return False

    body_lower = body.lower()

    # ---------------------------------------
    # External application signals
    # ---------------------------------------

    external_signals = [

        "apply on company website",

        "apply on the company website",

        "apply externally",

        "application on company website",

        "apply via company website"
    ]

    for signal in external_signals:

        if signal in body_lower:

            return False

    # ---------------------------------------
    # Strong Easy Apply signals
    # ---------------------------------------

    strong_signals = [

        "easy apply button",

        "easy apply",

        "apply through the easy apply button",

        "submit your application through the easy apply button"
    ]

    for signal in strong_signals:

        if signal in body_lower:

            return True

    # ---------------------------------------
    # Inspect visible controls
    # ---------------------------------------

    selectors = [

        "button",

        "[role='button']",

        "a"
    ]

    for selector in selectors:

        try:

            elements = page.locator(
                selector
            )

            count = elements.count()

            for index in range(count):

                try:

                    element = elements.nth(
                        index
                    )

                    if not element.is_visible():
                        continue

                    text = (
                        element
                        .inner_text()
                        .strip()
                        .lower()
                    )

                    aria = (
                        element
                        .get_attribute(
                            "aria-label"
                        )
                        or ""
                    ).lower()

                    title = (
                        element
                        .get_attribute(
                            "title"
                        )
                        or ""
                    ).lower()

                    combined = (
                        text
                        + " "
                        + aria
                        + " "
                        + title
                    )

                    if "easy apply" in combined:

                        return True

                except Exception:

                    continue

        except Exception:

            continue

    return False


# =======================================
# Detect Active Reviewing
# =======================================

def detect_actively_reviewing(body):

    if not body:
        return False

    return (
        "actively reviewing applicants"
        in body.lower()
    )


# =======================================
# Detect Closed Job
# =======================================

def detect_closed(body):

    if not body:
        return False

    body_lower = body.lower()

    closed_messages = [

        "no longer accepting applications",

        "this job is no longer accepting applications",

        "applications are closed",

        "no longer accepting"
    ]

    for message in closed_messages:

        if message in body_lower:

            return True

    return False


# =======================================
# Extract Job Links
# =======================================

def get_job_links(page):

    links = []

    seen_ids = set()

    selectors = [

        "a[href*='/jobs/view/']",

        "a[href*='currentJobId=']"
    ]

    for selector in selectors:

        try:

            elements = page.locator(
                selector
            )

            count = elements.count()

            for index in range(count):

                try:

                    element = elements.nth(
                        index
                    )

                    href = (
                        element
                        .get_attribute(
                            "href"
                        )
                        or ""
                    )

                    job_id = extract_job_id(
                        href
                    )

                    if not job_id:
                        continue

                    if job_id in seen_ids:
                        continue

                    seen_ids.add(
                        job_id
                    )

                    job_url = (
                        build_job_url(
                            job_id
                        )
                    )

                    links.append(
                        job_url
                    )

                    if (
                        len(links)
                        >= MAX_JOBS
                    ):

                        return links

                except Exception:

                    continue

        except Exception:

            continue

    return links


# =======================================
# Search Jobs
# =======================================

def location_allowed(location):
    text = (location or "").strip().lower()
    return bool(text) and any(target in text for target in TARGET_LOCATIONS)


def search_jobs():


    with sync_playwright() as p:

        # ---------------------------------------
        # Connect to Chrome
        # ---------------------------------------

        try:

            browser = (
                p.chromium
                .connect_over_cdp(
                    CHROME_CDP_URL
                )
            )

        except Exception as e:

            print()
            print(
                "Could not connect to Chrome."
            )

            print()
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

            return

        if not browser.contexts:

            print(
                "No browser context found."
            )

            return

        context = (
            browser.contexts[0]
        )

        if context.pages:

            page = context.pages[0]

        else:

            page = context.new_page()

        print(
            "Connected to:",
            page.title()
        )

        # ---------------------------------------
        # Build search URL
        # ---------------------------------------

        search_url = (
            build_search_url()
        )

        print()
        print(
            "=" * 70
        )

        print(
            "LINKEDIN JOB SEARCH"
        )

        print(
            "=" * 70
        )

        print()
        print(
            f"Searching for: "
            f"{SEARCH_KEYWORD}"
        )

        print(
            "Easy Apply filter: "
            f"{'ON' if EASY_APPLY_FILTER else 'OFF'}"
        )

        print()
        print(
            f"Search URL: "
            f"{search_url}"
        )

        # ---------------------------------------
        # Open Search
        # ---------------------------------------

        try:

            page.goto(
                search_url,
                wait_until="domcontentloaded",
                timeout=30000
            )

            page.wait_for_timeout(
                5000
            )

        except Exception as e:

            print()
            print(
                f"Could not open search: {e}"
            )

            return

        print()
        print(
            f"Current URL: "
            f"{page.url}"
        )

        # ---------------------------------------
        # Login Check
        # ---------------------------------------

        if "login" in page.url:

            print()
            print(
                "LinkedIn login required."
            )

            input(
                "Login manually and press ENTER..."
            )

            try:

                page.goto(
                    search_url,
                    wait_until="domcontentloaded",
                    timeout=30000
                )

                page.wait_for_timeout(
                    4000
                )

            except Exception as e:

                print(
                    f"Could not reopen search: {e}"
                )

                return

        # ---------------------------------------
        # Save screenshot
        # ---------------------------------------

        try:

            page.screenshot(
                path="search_results.png",
                full_page=True
            )

        except Exception:

            pass

        # ---------------------------------------
        # Find job links
        # ---------------------------------------

        print()
        print(
            "Finding job results..."
        )

        # Scroll to load more jobs.

        for _ in range(3):

            try:

                page.mouse.wheel(
                    0,
                    1500
                )

                page.wait_for_timeout(
                    1500
                )

            except Exception:

                break

        job_links = (
            get_job_links(page)
        )

        print()
        print(
            f"Potential jobs found: "
            f"{len(job_links)}"
        )

        if not job_links:

            print()
            print(
                "No LinkedIn job links found."
            )

            print()
            print(
                "LinkedIn may have changed "
                "its page structure."
            )

            return

        # ---------------------------------------
        # Process Jobs
        # ---------------------------------------

        jobs = []

        seen_links = set()

        for index, job_link in enumerate(
            job_links,
            start=1
        ):

            if len(jobs) >= MAX_JOBS:

                break

            try:

                print()
                print(
                    "=" * 70
                )

                print(
                    f"Processing job "
                    f"{index}/{len(job_links)}"
                )

                print(
                    f"URL: {job_link}"
                )

                # ---------------------------------------
                # Open Job
                # ---------------------------------------

                page.goto(
                    job_link,
                    wait_until="domcontentloaded",
                    timeout=30000
                )

                page.wait_for_timeout(
                    3000
                )

                current_url = page.url

                # ---------------------------------------
                # Job ID
                # ---------------------------------------

                job_id = (
                    extract_job_id(
                        current_url
                    )
                )

                if not job_id:

                    job_id = (
                        extract_job_id(
                            job_link
                        )
                    )

                if not job_id:

                    print(
                        "Job ID not found."
                    )

                    continue

                normalized_link = (
                    build_job_url(
                        job_id
                    )
                )

                if (
                    normalized_link
                    in seen_links
                ):

                    continue

                seen_links.add(
                    normalized_link
                )

                # ---------------------------------------
                # Body
                # ---------------------------------------

                try:

                    body = (
                        page.locator(
                            "body"
                        ).inner_text()
                    )

                except Exception:

                    body = ""

                # ---------------------------------------
                # Closed Job
                # ---------------------------------------

                if detect_closed(body):

                    print(
                        "Status : CLOSED"
                    )

                    print(
                        "Skipping."
                    )

                    continue

                # ---------------------------------------
                # Title
                # ---------------------------------------

                actual_title = (
                    extract_job_title(
                        page
                    )
                )

                # ---------------------------------------
                # Company
                # ---------------------------------------

                company = (
                    extract_company(
                        page
                    )
                )

                # ---------------------------------------
                # Location
                # ---------------------------------------

                location = (
                    extract_location(
                        page,
                        body
                    )
                )

                if not location_allowed(location):
                    print(f"Outside target locations: {location or 'Unknown'}")
                    print("Skipping.")
                    continue

                # ---------------------------------------
                # Easy Apply
                # ---------------------------------------

                easy_apply = (
                    detect_easy_apply(
                        page
                    )
                )

                # ---------------------------------------
                # Active Reviewing
                # ---------------------------------------

                actively_reviewing = (
                    detect_actively_reviewing(
                        body
                    )
                )

                # ---------------------------------------
                # Display
                # ---------------------------------------

                print()
                print(
                    f"Title   : "
                    f"{actual_title}"
                )

                print(
                    f"Company : "
                    f"{company or 'Not available'}"
                )

                print(
                    f"Location: "
                    f"{location or 'Not available'}"
                )

                print(
                    f"Easy Apply: "
                    f"{'Yes' if easy_apply else 'No'}"
                )

                print(
                    f"Actively Reviewing: "
                    f"{'Yes' if actively_reviewing else 'No'}"
                )

                print(
                    f"URL: "
                    f"{normalized_link}"
                )

                # ---------------------------------------
                # Only keep Easy Apply jobs
                # ---------------------------------------

                if (
                    EASY_APPLY_FILTER
                    and not easy_apply
                ):

                    print()
                    print(
                        "Not currently Easy Apply."
                    )

                    print(
                        "Skipping."
                    )

                    continue

                # ---------------------------------------
                # Save Job
                # ---------------------------------------

                jobs.append({

                    "Title":
                        actual_title,

                    "Company":
                        company,

                    "Location":
                        location,

                    "Easy Apply":
                        "Yes"
                        if easy_apply
                        else "No",

                    "Actively Reviewing":
                        "Yes"
                        if actively_reviewing
                        else "No",

                    "Link":
                        normalized_link
                })

            except Exception as e:

                print()
                print(
                    f"Skipped job: {e}"
                )

        # ---------------------------------------
        # Save CSV
        # ---------------------------------------

        with open(
            OUTPUT_FILE,
            "w",
            newline="",
            encoding="utf-8"
        ) as file:

            writer = csv.DictWriter(
                file,
                fieldnames=[

                    "Title",

                    "Company",

                    "Location",

                    "Easy Apply",

                    "Actively Reviewing",

                    "Link"
                ]
            )

            writer.writeheader()

            writer.writerows(
                jobs
            )

        # ---------------------------------------
        # Summary
        # ---------------------------------------

        easy_apply_count = sum(

            1

            for job in jobs

            if job["Easy Apply"] == "Yes"
        )

        print()
        print(
            "=" * 70
        )

        print(
            "JOB SEARCH COMPLETED"
        )

        print(
            "=" * 70
        )

        print(
            f"Jobs collected      : "
            f"{len(jobs)}"
        )

        print(
            f"Easy Apply jobs     : "
            f"{easy_apply_count}"
        )

        print(
            f"Saved file          : "
            f"{OUTPUT_FILE}"
        )

        print(
            "=" * 70
        )

        input(
            "\nPress ENTER to finish..."
        )


# =======================================
# Entry Point
# =======================================

if __name__ == "__main__":

    search_jobs()