from playwright.sync_api import sync_playwright
from dotenv import load_dotenv
from pathlib import Path
import csv
import os
import re


# ============================================================
# CONFIGURATION
# ============================================================

load_dotenv()

INPUT_OUTPUT_FILE = "jobs.csv"
DEFAULT_CDP_URL = "http://127.0.0.1:9222"

# Target locations for this project.
# We intentionally do NOT include all of India.
TARGET_LOCATIONS = [
    "bengaluru",
    "bangalore",
    "hyderabad",
    "chennai",
    "remote",
]


# ============================================================
# TEXT HELPERS
# ============================================================

def clean_text(text):
    """Clean extra whitespace from text."""
    return re.sub(r"\s+", " ", text or "").strip()


def extract_job_id(href):
    """
    Extract LinkedIn job ID.

    Supports both:
        currentJobId=123456
    and:
        /jobs/view/123456/
    """

    if not href:
        return ""

    # Search-result URL format.
    match = re.search(r"currentJobId=(\d+)", href)

    if match:
        return match.group(1)

    # Direct LinkedIn job URL format.
    match = re.search(r"/jobs/view/(\d+)", href)

    if match:
        return match.group(1)

    return ""


def make_direct_job_url(job_id):
    """Create a direct LinkedIn job URL."""
    if not job_id:
        return ""

    return f"https://www.linkedin.com/jobs/view/{job_id}/"


# ============================================================
# LOCATION
# ============================================================

def extract_location(text):
    """Extract a likely location from the job card."""

    locations = [
        "Bengaluru",
        "Bangalore",
        "Hyderabad",
        "Chennai",
        "Remote",
        "Pune",
        "Mumbai",
        "Delhi",
        "Gurugram",
        "Gurgaon",
        "Noida",
        "Kolkata",
        "India",
        "Ahmedabad",
        "Jaipur",
        "Chandigarh",
        "Kochi",
        "Visakhapatnam",
        "Puttur",
    ]

    lines = [
        clean_text(line)
        for line in text.splitlines()
        if clean_text(line)
    ]

    for line in lines:

        for location in locations:

            if location.lower() in line.lower():
                return line

    return ""


def is_target_location(location):
    """
    Return True when the job is in one of the locations
    required for this project.

    Target:
        Bengaluru
        Hyderabad
        Chennai
        Remote
    """

    normalized = clean_text(location).lower()

    if not normalized:
        return False

    return any(
        target in normalized
        for target in TARGET_LOCATIONS
    )


# ============================================================
# COMPANY
# ============================================================

def extract_company(text):
    """
    Extract company name from a LinkedIn job card.

    Handles cards where LinkedIn adds "(Verified job)"
    to the displayed job title.

    Examples:

        Java Developer
        Java Developer
        Data Eminence
        •
        India (Remote)

    and:

        Software Engineer (Verified job)
        Software Engineer
        Swish
        •
        Bengaluru (On-site)
    """

    lines = [
        clean_text(line)
        for line in text.splitlines()
        if clean_text(line)
    ]

    if len(lines) < 2:
        return ""

    # Normalize the displayed title by removing LinkedIn's
    # verification suffix.
    title = re.sub(
        r"\s*\(verified job\)\s*$",
        "",
        lines[0],
        flags=re.IGNORECASE,
    ).strip()

    candidates = []

    for line in lines[1:]:

        candidate = clean_text(line)

        if not candidate:
            continue

        # Separator.
        if candidate == "•":
            continue

        # Repeated job title.
        if candidate.lower() == title.lower():
            continue

        # LinkedIn status/action text.
        if candidate.lower() in {
            "promoted",
            "actively reviewing applicants",
            "viewed",
            "easy apply",
            "apply",
            "save",
        }:
            continue

        # Location/status lines.
        if any(
            location in candidate.lower()
            for location in [
                "bengaluru",
                "bangalore",
                "hyderabad",
                "chennai",
                "pune",
                "mumbai",
                "delhi",
                "gurugram",
                "gurgaon",
                "noida",
                "india",
                "remote",
            ]
        ):
            continue

        candidates.append(candidate)

    if not candidates:
        return ""

    return candidates[0]


# ============================================================
# FIND LINKEDIN JOBS PAGE
# ============================================================

def find_linkedin_jobs_page(context):
    """
    Find an already-open LinkedIn Jobs page.

    Returns:
        Playwright Page

    Raises:
        RuntimeError if no LinkedIn Jobs page exists.
    """

    for page in context.pages:

        try:

            url = page.url.lower()

            if "linkedin.com/jobs" in url:
                return page

        except Exception:
            continue

    return None


# ============================================================
# SCRAPE JOBS
# ============================================================

def scrape_jobs(
    cdp_url=None,
    output_file=INPUT_OUTPUT_FILE,
):
    """
    Connect to an existing Chrome session and scrape LinkedIn jobs.

    IMPORTANT:
    Chrome is connected ONLY when this function is called.

    Importing this module does NOT connect to Chrome.
    """

    cdp_url = (
        cdp_url
        or os.getenv("CHROME_CDP_URL")
        or DEFAULT_CDP_URL
    )

    print()
    print("=" * 60)
    print("LINKEDIN JOB SCRAPER")
    print("=" * 60)

    print(f"CDP URL : {cdp_url}")
    print()

    jobs = []
    seen_job_ids = set()

    with sync_playwright() as p:

        # ----------------------------------------------------
        # CONNECT TO EXISTING CHROME
        # ----------------------------------------------------

        print("Connecting to Chrome...")

        try:

            browser = p.chromium.connect_over_cdp(cdp_url)

        except Exception as e:

            print()
            print("=" * 60)
            print("CHROME CONNECTION FAILED")
            print("=" * 60)

            print()
            print("Could not connect to Chrome through CDP.")
            print(f"CDP URL: {cdp_url}")

            print()
            print("Make sure Chrome is started with:")
            print("  --remote-debugging-port=9222")

            print()
            print("Original error:")
            print(e)

            print("=" * 60)

            return []

        print("Chrome connection successful.")

        # ----------------------------------------------------
        # FIND CONTEXT
        # ----------------------------------------------------

        if not browser.contexts:

            print("No browser context found.")

            browser.close()

            return []

        context = browser.contexts[0]

        # ----------------------------------------------------
        # FIND LINKEDIN JOBS PAGE
        # ----------------------------------------------------

        page = find_linkedin_jobs_page(context)

        if page is None:

            print()
            print("=" * 60)
            print("LINKEDIN JOBS PAGE NOT FOUND")
            print("=" * 60)

            print()
            print("Open LinkedIn Jobs in the connected Chrome window")
            print("before running the scraper.")

            browser.close()

            return []

        print()
        print("Connected to:")
        print(page.title())

        print("URL:")
        print(page.url)

        # ----------------------------------------------------
        # COLLECT JOB LINKS
        # ----------------------------------------------------

        print()
        print("=" * 60)
        print("COLLECTING LINKEDIN JOBS")
        print("=" * 60)

        links = page.locator("a")

        total_links = links.count()

        print(f"Links found on page: {total_links}")

        for i in range(total_links):

            try:

                link = links.nth(i)

                if not link.is_visible():
                    continue

                href = link.get_attribute("href")

                if not href:
                    continue

                # Only process LinkedIn job links.
                if (
                    "currentJobId=" not in href
                    and "/jobs/view/" not in href
                ):
                    continue

                text = link.inner_text().strip()

                if not text:
                    continue

                # ------------------------------------------------
                # JOB ID
                # ------------------------------------------------

                job_id = extract_job_id(href)

                if not job_id:
                    continue

                # ------------------------------------------------
                # DUPLICATE CHECK
                # ------------------------------------------------

                if job_id in seen_job_ids:
                    continue

                seen_job_ids.add(job_id)

                # ------------------------------------------------
                # CARD DATA
                # ------------------------------------------------

                lines = [
                    clean_text(line)
                    for line in text.splitlines()
                    if clean_text(line)
                ]

                title = lines[0] if lines else ""

                company = extract_company(text)

                location = extract_location(text)

                easy_apply = (
                    "Yes"
                    if "Easy Apply" in text
                    else "No"
                )

                direct_url = make_direct_job_url(job_id)

                # ------------------------------------------------
                # LOCATION FILTER
                # ------------------------------------------------

                if not is_target_location(location):

                    print()
                    print(f"Skipping job #{job_id}")
                    print(f"Title    : {title}")
                    print(
                        f"Location : "
                        f"{location or 'Not detected'}"
                    )
                    print("Reason   : Outside target locations")

                    continue

                # ------------------------------------------------
                # SAVE JOB
                # ------------------------------------------------

                jobs.append([
                    title,
                    company,
                    location,
                    easy_apply,
                    direct_url,
                ])

                print()
                print(f"Job #{len(jobs)}")
                print(f"Title     : {title}")
                print(
                    f"Company   : "
                    f"{company or 'Not detected'}"
                )
                print(
                    f"Location  : "
                    f"{location or 'Not detected'}"
                )
                print(f"Easy Apply: {easy_apply}")
                print(f"Job ID    : {job_id}")
                print(f"URL       : {direct_url}")

            except Exception as e:

                print(
                    f"Skipping link {i} because of error: {e}"
                )

        # ----------------------------------------------------
        # CLOSE PLAYWRIGHT CONNECTION
        # ----------------------------------------------------

        try:
            browser.close()
        except Exception:
            pass

    # ========================================================
    # SAVE CSV
    # ========================================================

    with open(
        output_file,
        "w",
        newline="",
        encoding="utf-8",
    ) as file:

        writer = csv.writer(file)

        writer.writerow([
            "Title",
            "Company",
            "Location",
            "Easy Apply",
            "Link",
        ])

        writer.writerows(jobs)

    # ========================================================
    # SUMMARY
    # ========================================================

    print()
    print("=" * 60)
    print("JOB SCRAPING COMPLETED")
    print("=" * 60)

    print(f"Jobs collected : {len(jobs)}")
    print(f"Unique job IDs : {len(seen_job_ids)}")
    print(f"Saved file     : {output_file}")

    print()
    print("Target locations:")
    print("  - Bengaluru")
    print("  - Hyderabad")
    print("  - Chennai")
    print("  - Remote")

    print("=" * 60)

    return jobs


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    scrape_jobs()