import csv
from dataclasses import dataclass
from enum import Enum
import os
import re
import tempfile
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

JOB_CSV_FIELDS = (
    "Title",
    "Company",
    "Location",
    "Easy Apply",
    "Actively Reviewing",
    "Link",
)


class CollectionStatus(str, Enum):
    COMPLETE = "COMPLETE"
    COMPLETE_EMPTY = "COMPLETE_EMPTY"
    INCOMPLETE = "INCOMPLETE"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class CollectionOutcome:
    status: CollectionStatus
    jobs: tuple
    issues: tuple = ()
    bounded_by_limit: bool = False


@dataclass(frozen=True)
class JobLinkResult:
    links: tuple
    errors: tuple = ()
    bounded_by_limit: bool = False


def _collection_outcome(jobs, issues=(), fatal=False, bounded_by_limit=False):
    """Classify only outcomes supported by observed collection evidence."""
    if fatal:
        status = CollectionStatus.FAILED
    elif issues:
        status = CollectionStatus.INCOMPLETE
    else:
        # Current search pages expose no verified completion or empty-result
        # signal. A clean navigation and parser pass therefore remains unknown.
        status = CollectionStatus.UNKNOWN

    return CollectionOutcome(
        status=status,
        jobs=tuple(jobs),
        issues=tuple(issues),
        bounded_by_limit=bounded_by_limit,
    )


def _record_issue(issues, message):
    if issues is not None:
        issues.append(message)


def _write_jobs_csv_atomically(jobs, output_file):
    output_file = os.path.abspath(output_file)
    output_dir = os.path.dirname(output_file)
    output_name = os.path.basename(output_file)
    temporary_path = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            newline="",
            encoding="utf-8",
            dir=output_dir,
            prefix=f".{output_name}.",
            suffix=".tmp",
            delete=False,
        ) as file:
            temporary_path = file.name
            writer = csv.DictWriter(file, fieldnames=JOB_CSV_FIELDS)
            writer.writeheader()
            writer.writerows(jobs)
            file.flush()
            os.fsync(file.fileno())

        os.replace(temporary_path, output_file)
        temporary_path = None
        return True
    finally:
        if temporary_path and os.path.exists(temporary_path):
            try:
                os.remove(temporary_path)
            except OSError:
                pass


def publish_collection(outcome, output_file=OUTPUT_FILE):
    """Atomically publish only explicitly verified complete outcomes."""
    if outcome.status not in {
        CollectionStatus.COMPLETE,
        CollectionStatus.COMPLETE_EMPTY,
    }:
        return False

    _write_jobs_csv_atomically(outcome.jobs, output_file)
    return True


# =======================================
# Build LinkedIn Search URL
# =======================================

def build_search_url(location=None, keyword=None):

    keyword = quote(keyword or SEARCH_KEYWORD)

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

def extract_company(page, issues=None):

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

        except Exception as exc:
            _record_issue(issues, f"Company parser failed for {selector!r}: {exc}")
            continue

    return ""


# =======================================
# Extract Location
# =======================================

def extract_location(page, body="", issues=None):

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
                # India Â· 6 days ago Â· Over 100 applicants
                #
                # We only want the first part.

                first_part = (
                    value
                    .split("Â·")[0]
                    .strip()
                )

                if first_part:
                    return first_part

        except Exception as exc:
            _record_issue(issues, f"Location parser failed for {selector!r}: {exc}")
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
                # India Â· 6 days ago Â· Over 100 applicants
                #
                if (
                    "Â·" in line
                    and (
                        "ago" in lower
                        or "applicant" in lower
                    )
                ):

                    possible_location = (
                        line
                        .split("Â·")[0]
                        .strip()
                    )

                    if (
                        possible_location
                        and len(possible_location) < 150
                    ):

                        return possible_location

        except Exception as exc:
            _record_issue(issues, f"Location body parser failed: {exc}")
            pass

    return ""


# =======================================
# Extract Job Title
# =======================================

def extract_job_title(page, issues=None):

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

        except Exception as exc:
            _record_issue(issues, f"Job-title selector parser failed for {selector!r}: {exc}")
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

    except Exception as exc:
        _record_issue(issues, f"Job-title page-title parser failed: {exc}")
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

    except Exception as exc:
        _record_issue(issues, f"Job-title body parser failed: {exc}")
        pass

    return "Unknown Job"


# =======================================
# Detect LIVE Easy Apply
# =======================================

def detect_easy_apply(page, issues=None):
    """Detect a real, visible LinkedIn Easy Apply control.

    This intentionally does NOT treat ordinary "Apply" buttons or text in
    the job description as Easy Apply. LinkedIn can mention Easy Apply in
    descriptions even when the actual application is external.
    """
    selectors = [
        "[aria-label*='LinkedIn Apply to this job' i]",
        "button[aria-label*='Easy Apply' i]",
        "[role='button'][aria-label*='Easy Apply' i]",
        "button[title*='Easy Apply' i]",
        "[role='button'][title*='Easy Apply' i]",
        "button:has-text('Easy Apply')",
        "[role='button']:has-text('Easy Apply')",
    ]

    for selector in selectors:
        try:
            elements = page.locator(selector)
            count = elements.count()
            for index in range(count):
                element = elements.nth(index)
                if not element.is_visible():
                    continue

                text = (element.inner_text() or "").strip().lower()
                aria = (element.get_attribute("aria-label") or "").strip().lower()
                title = (element.get_attribute("title") or "").strip().lower()
                combined = f"{text} {aria} {title}"

                # The exact LinkedIn Apply control is a strong positive signal.
                if "linkedin apply to this job" in aria:
                    return True

                if "easy apply" in combined:
                    return True
        except Exception as exc:
            _record_issue(issues, f"Easy Apply parser failed for {selector!r}: {exc}")
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

def get_job_links(page, max_links=None):

    links = []

    seen_ids = set()

    selectors = [

        "a[href*='/jobs/view/']",

        "a[href*='currentJobId=']"
    ]

    link_limit = max_links or MAX_JOBS

    errors = []

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
                        errors.append(
                            f"Result selector {selector!r} returned an unrecognized job URL."
                        )
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

                    if len(links) >= link_limit:
                        return JobLinkResult(
                            tuple(links),
                            tuple(errors),
                            bounded_by_limit=True,
                        )

                except Exception as exc:
                    errors.append(
                        f"Could not parse result {index} for selector {selector!r}: {exc}"
                    )
                    continue

        except Exception as exc:
            errors.append(f"Could not inspect result selector {selector!r}: {exc}")
            continue

    return JobLinkResult(tuple(links), tuple(errors))


# =======================================
# Search Jobs
# =======================================

def location_allowed(location):
    text = (location or "").strip().lower()
    return bool(text) and any(target in text for target in TARGET_LOCATIONS)


def _collect_search_jobs():

    issues = []
    bounded_by_limit = False

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
            return _collection_outcome([], issues, fatal=True)

        if not browser.contexts:

            print(
                "No browser context found."
            )
            return _collection_outcome([], issues, fatal=True)

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
        # LinkedIn multi-keyword + location search
        # ---------------------------------------

        print()
        print("=" * 70)
        print("LINKEDIN JOB SEARCH")
        print("=" * 70)

        print()
        print(
            "Easy Apply filter: "
            f"{'ON' if EASY_APPLY_FILTER else 'OFF'}"
        )
        print(
            "Freshness filter: last 30 days"
        )

        all_job_links = []
        seen_job_ids = set()
        job_search_locations = {}

        keywords = SEARCH_KEYWORDS or (
            SEARCH_KEYWORD,
        )

        # Use clean display names for LinkedIn's location search.
        # The final job-page location check still uses TARGET_LOCATIONS.
        search_locations = []
        for location in TARGET_LOCATIONS:
            location_text = str(location).strip()
            if not location_text:
                continue

            lower = location_text.lower()
            if lower in ("bengaluru", "bangalore"):
                display_location = "Bengaluru"
            elif lower == "hyderabad":
                display_location = "Hyderabad"
            elif lower == "chennai":
                display_location = "Chennai"
            elif "remote" in lower:
                display_location = "Remote"
            else:
                display_location = location_text

            if display_location.lower() not in [
                item.lower() for item in search_locations
            ]:
                search_locations.append(
                    display_location
                )

        if not search_locations:
            search_locations = ["India"]

        # A small per-search cap keeps the final pool diverse instead of
        # allowing the first keyword/location pair to consume all MAX_JOBS.
        per_search_limit = min(
            8,
            max(3, MAX_JOBS // max(1, len(keywords)))
        )

        search_counter = 0

        for keyword_index, keyword in enumerate(
            keywords,
            start=1
        ):

            for location_index, location in enumerate(
                search_locations,
                start=1
            ):

                if len(all_job_links) >= MAX_JOBS:
                    break

                search_counter += 1

                print()
                print("=" * 70)
                print(
                    f"SEARCH {search_counter} | "
                    f"Keyword {keyword_index}/{len(keywords)} | "
                    f"Location {location_index}/{len(search_locations)}"
                )
                print("=" * 70)
                print()
                print(
                    f"Searching for: {keyword}"
                )
                print(
                    f"Location: {location}"
                )

                search_url = build_search_url(
                    keyword=keyword,
                    location=location
                )

                # Prefer recently posted jobs so stale/closed listings are
                # less likely to dominate the candidate pool.
                separator = "&" if "?" in search_url else "?"
                search_url += (
                    f"{separator}sortBy=DD&f_TPR=r2592000"
                )

                print(
                    f"Search URL: {search_url}"
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
                        f"Could not open search for "
                        f"'{keyword}' in '{location}': {e}"
                    )
                    issues.append(
                        f"Search navigation failed for {keyword!r} in {location!r}: {e}"
                    )
                    continue

                print()
                print(
                    f"Current URL: {page.url}"
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
                        issues.append(
                            f"Could not retry search after login for {keyword!r} in {location!r}: {e}"
                        )
                        continue

                # ---------------------------------------
                # Save screenshot
                # ---------------------------------------

                try:

                    page.screenshot(
                        path=(
                            f"search_results_{search_counter}.png"
                        ),
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

                for scroll_index in range(3):

                    try:

                        page.mouse.wheel(
                            0,
                            1500
                        )

                        page.wait_for_timeout(
                            1500
                        )

                    except Exception as e:
                        issues.append(
                            f"Scrolling failed on search {keyword!r} in {location!r} "
                            f"(attempt {scroll_index + 1}): {e}"
                        )
                        break

                link_result = get_job_links(
                    page,
                    max_links=per_search_limit
                )
                keyword_job_links = link_result.links
                issues.extend(link_result.errors)
                bounded_by_limit = (
                    bounded_by_limit or link_result.bounded_by_limit
                )

                print()
                print(
                    f"Potential jobs found for "
                    f"'{keyword}' in '{location}': "
                    f"{len(keyword_job_links)}"
                )

                # ---------------------------------------
                # Combine results and remove duplicates
                # ---------------------------------------

                added = 0

                for job_link in keyword_job_links:

                    job_id = extract_job_id(
                        job_link
                    )

                    if not job_id:
                        continue

                    if job_id in seen_job_ids:
                        continue

                    seen_job_ids.add(job_id)

                    normalized_job_url = build_job_url(job_id)

                    all_job_links.append(
                        normalized_job_url
                    )

                    # Remember the LinkedIn search location that produced this
                    # job. LinkedIn sometimes hides the location on the detail
                    # page, so this is used as a reliable fallback.
                    job_search_locations[normalized_job_url] = location

                    added += 1

                    if len(all_job_links) >= MAX_JOBS:
                        bounded_by_limit = True
                        break

                print(
                    f"New unique jobs added: {added}"
                )
                print(
                    f"Total unique jobs: "
                    f"{len(all_job_links)}/{MAX_JOBS}"
                )

            if len(all_job_links) >= MAX_JOBS:
                bounded_by_limit = True
                break

        # ---------------------------------------
        # Final combined job links
        # ---------------------------------------

        job_links = all_job_links[:MAX_JOBS]

        print()
        print("=" * 70)
        print(
            f"Total unique potential jobs: "
            f"{len(job_links)}"
        )
        print("=" * 70)

        if not job_links:

            print()
            print(
                "No LinkedIn job links found."
            )
            print()
            print(
                "LinkedIn may have changed its page structure."
            )
            outcome = _collection_outcome(
                [],
                issues,
                bounded_by_limit=bounded_by_limit,
            )
            print(f"Collection outcome: {outcome.status.value}")
            print("Existing jobs.csv was preserved.")
            return outcome

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

                # Re-create the page if LinkedIn closed the current tab.
                try:
                    if page.is_closed():
                        page = context.new_page()
                except Exception:
                    if browser.is_connected():
                        try:
                            if not context.pages:
                                page = context.new_page()
                            else:
                                page = context.pages[0]
                        except Exception:
                            pass

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
                    issues.append(
                        f"Could not identify a job ID for candidate {job_link}."
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

                except Exception as e:

                    body = ""
                    issues.append(
                        f"Could not read the job page body for {job_link}: {e}"
                    )

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
                        page,
                        issues=issues,
                    )
                )
                if actual_title == "Unknown Job":
                    issues.append(
                        f"Could not extract a title for candidate {job_link}."
                    )

                # ---------------------------------------
                # Company
                # ---------------------------------------

                company = (
                    extract_company(
                        page,
                        issues=issues,
                    )
                )

                # ---------------------------------------
                # Location
                # ---------------------------------------

                extracted_location = (
                    extract_location(
                        page,
                        body,
                        issues=issues,
                    )
                )

                # LinkedIn can hide or delay the location on the job-detail page.
                # We already know the location used for the search that found this job,
                # so use that as a safe fallback rather than discarding a valid result.
                search_location = job_search_locations.get(normalized_link, "")

                generic_locations = {
                    "",
                    "unknown",
                    "india",
                    "india ·",
                    "india · remote",
                }

                if extracted_location.strip().lower() in generic_locations:
                    location = search_location
                else:
                    location = extracted_location or search_location

                if not location_allowed(location):
                    print(
                        f"Outside target locations: "
                        f"{location or 'Unknown'}"
                    )
                    print("Skipping.")
                    continue

                # ---------------------------------------
                # Easy Apply
                # ---------------------------------------

                easy_apply = (
                    detect_easy_apply(
                        page,
                        issues=issues,
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
                if not extracted_location and search_location:
                    print("Location source: search location fallback")

                print(
                    f"Easy Apply: "
                    f"{'Yes' if easy_apply else 'No'}"
                )

                print(
                    f"Actively Reviewing: "
                    f"{'Yes' if actively_reviewing else 'No'}"
                )

                print(
                    f"URL: {normalized_link}"
                )

                # ---------------------------------------
                # Only keep Easy Apply jobs when explicitly enabled
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
                issues.append(
                    f"Candidate-page processing failed for {job_link}: {e}"
                )
                # Keep the run alive if a job navigation closes the current tab.
                try:
                    if browser.is_connected() and (page.is_closed() or not context.pages):
                        page = context.new_page()
                except Exception:
                    pass

        outcome = _collection_outcome(
            jobs,
            issues,
            bounded_by_limit=bounded_by_limit,
        )
        published = publish_collection(outcome, OUTPUT_FILE)

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
            f"JOB SEARCH OUTCOME: {outcome.status.value}"
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
            f"Published           : "
            f"{'Yes' if published else 'No; existing file preserved'}"
        )

        print(
            "=" * 70
        )

        input(
            "\nPress ENTER to finish..."
        )

        return outcome


def search_jobs():
    """Run collection and convert unexpected failures into FAILED outcomes."""
    try:
        return _collect_search_jobs()
    except Exception as exc:
        outcome = _collection_outcome([], [str(exc)], fatal=True)
        print(f"Collection outcome: {outcome.status.value}: {exc}")
        print("Existing jobs.csv was preserved.")
        return outcome


# =======================================
# Entry Point
# =======================================

if __name__ == "__main__":

    search_jobs()
    
