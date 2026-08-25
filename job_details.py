import csv
import os
import re

from playwright.sync_api import sync_playwright


INPUT_FILE = "jobs.csv"
OUTPUT_FILE = "data/job_details.csv"


def extract_text(page, selectors):
    """
    Try multiple selectors and return the first useful text.
    """
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            if locator.count() > 0:
                text = locator.inner_text().strip()
                if text:
                    return text
        except Exception:
            pass

    return ""


def clean_lines(text):
    return [
        re.sub(r"\s+", " ", line).strip()
        for line in text.splitlines()
        if re.sub(r"\s+", " ", line).strip()
    ]


def extract_company_from_header(page):
    """
    Extract the company belonging to the CURRENT job.

    Important:
    Do not use a random /company/ link from the entire page because
    LinkedIn also displays recommended jobs below the current job.
    First try company links/selectors inside the current job header.
    """
    selectors = [
        "div.job-details-jobs-unified-top-card__company-name a",
        "div.job-details-jobs-unified-top-card__company-name",
        "a.job-details-jobs-unified-top-card__company-name",
        "div.jobs-unified-top-card__company-name a",
        "div.jobs-unified-top-card__company-name",
    ]

    value = extract_text(page, selectors)
    if value:
        return value

        # Current LinkedIn layout: company is exposed as a /company/ link.
    try:
        links = page.locator("a[href*='/company/']")
        for i in range(links.count()):
            link = links.nth(i)
            if not link.is_visible():
                continue

            text = re.sub(r"\s+", " ", link.inner_text() or "").strip()

            if text and len(text) <= 150:
                return text
    except Exception:
        pass

    # Fallback: locate the h1 and inspect only its nearby ancestor.
    try:
        h1 = page.locator("h1").first
        if h1.count() > 0:
            ancestor = h1.locator(
                "xpath=ancestor::*[.//a[contains(@href,'/company/')]][1]"
            ).first

            if ancestor.count() > 0:
                company_link = ancestor.locator(
                    "a[href*='/company/']"
                ).first

                if company_link.count() > 0:
                    value = company_link.inner_text().strip()
                    if value:
                        return value
    except Exception:
        pass

    # Last fallback: first company link that is visually close to the h1.
    # Recommended-job company links are intentionally ignored where possible.
    try:
        links = page.locator("a[href*='/company/']")
        h1_box = page.locator("h1").first.bounding_box()

        if h1_box:
            candidates = []

            for i in range(links.count()):
                link = links.nth(i)

                if not link.is_visible():
                    continue

                box = link.bounding_box()
                text = (link.inner_text() or "").strip()

                if not box or not text:
                    continue

                # Current-job header company normally appears above/near h1.
                distance = abs(box["y"] - h1_box["y"])
                if distance <= 350:
                    candidates.append((distance, text))

            if candidates:
                candidates.sort(key=lambda x: x[0])
                return candidates[0][1]
    except Exception:
        pass

    return ""


def looks_like_location(value):
    """
    Determine whether a text fragment looks like a location rather than
    job metadata.
    """
    if not value:
        return False

    value = re.sub(r"\s+", " ", value).strip()
    lower = value.lower()

    # Things that are definitely not locations.
    invalid = [
        "promoted",
        "applicants",
        "applicant",
        "ago",
        "full-time",
        "part-time",
        "contract",
        "internship",
        "commission",
        "no response insights",
        "actively reviewing applicants",
        "remote",  # handled below when combined with a real place
    ]

    if lower in invalid:
        return False

    if re.fullmatch(r"\d+\s+(day|days|week|weeks|month|months|hour|hours|minute|minutes)\s+ago",
                    lower):
        return False

    # Strong location signals for the user's India-focused job search.
    india_places = [
        "india", "bengaluru", "bangalore", "hyderabad", "chennai",
        "pune", "mumbai", "delhi", "gurugram", "gurgaon", "noida",
        "kolkata", "kochi", "ahmedabad", "jaipur", "chandigarh",
        "mysuru", "mysore", "puducherry", "visakhapatnam", "puttur"
    ]

    if any(place in lower for place in india_places):
        return True

    # Common location/remote patterns.
    if re.search(r"\b(remote|hybrid|on[- ]site|onsite)\b", lower):
        # "Remote" by itself is acceptable.
        return True

    # Country/state/city style strings often contain commas.
    if "," in value and len(value) <= 120:
        return True

    return False


def extract_location_from_header(page):
    """
    Extract the location for the CURRENT job only.

    LinkedIn often puts location, posting age, applicant count and work
    type in one container. We therefore split the container into lines
    and choose the line that actually looks like a location.
    """
    selectors = [
        "span.jobs-unified-top-card__bullet",
        "span.job-details-jobs-unified-top-card__bullet",
    ]

    # Prefer small bullet elements first.
    for selector in selectors:
        try:
            locator = page.locator(selector)

            for i in range(locator.count()):
                element = locator.nth(i)

                if not element.is_visible():
                    continue

                value = element.inner_text().strip()
                for part in clean_lines(value):
                    if looks_like_location(part):
                        return part
        except Exception:
            pass

    # Inspect the current job header around h1.
    try:
        h1 = page.locator("h1").first

        if h1.count() > 0:
            # Try the nearest useful header ancestor.
            ancestor = h1.locator(
                "xpath=ancestor::*[.//a[contains(@href,'/company/')]][1]"
            ).first

            if ancestor.count() > 0:
                lines = clean_lines(ancestor.inner_text())

                # The header commonly looks like:
                # Job title
                # Company
                # India
                # 1 week ago · ...
                # Remote
                # Full-time
                for line in lines:
                    if line == h1.inner_text().strip():
                        continue
                    if looks_like_location(line):
                        return line
    except Exception:
        pass

    # Broader top-card fallback.
    try:
        header_selectors = [
            "div.job-details-jobs-unified-top-card",
            "div.jobs-unified-top-card",
        ]

        for selector in header_selectors:
            locator = page.locator(selector).first

            if locator.count() == 0:
                continue

            lines = clean_lines(locator.inner_text())

            for line in lines:
                if looks_like_location(line):
                    return line
    except Exception:
        pass

    return ""


def extract_description(page):
    description = ""

    selectors = [
        "div.jobs-description__content",
        "div.jobs-box__html-content",
        "div#job-details",
        "article",
    ]

    for selector in selectors:
        try:
            locator = page.locator(selector).first

            if locator.count() > 0:
                text = locator.inner_text().strip()

                if len(text) > len(description):
                    description = text
        except Exception:
            pass

    # Fallback: use body only when it actually contains the job description.
    if not description:
        try:
            body_text = page.locator("body").inner_text()

            if "About the job" in body_text:
                description = body_text
        except Exception:
            pass

    return description


def extract_job_details():
    if not os.path.exists(INPUT_FILE):
        print(f"{INPUT_FILE} not found.")
        return

    os.makedirs("data", exist_ok=True)

    with open(
        INPUT_FILE,
        "r",
        encoding="utf-8"
    ) as file:
        reader = csv.DictReader(file)
        jobs = list(reader)

    print(f"Found {len(jobs)} jobs in {INPUT_FILE}")

    if not jobs:
        print("No jobs found.")
        return

    results = []

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(
            "http://127.0.0.1:9222"
        )

        context = browser.contexts[0]

        if context.pages:
            page = context.pages[0]
        else:
            page = context.new_page()

        for i, job in enumerate(jobs, start=1):
            print()
            print("=" * 50)
            print(f"Processing job {i}/{len(jobs)}")
            print("=" * 50)

            title = job.get("Title", "").strip()
            company = job.get("Company", "").strip()
            location = job.get("Location", "").strip()
            easy_apply = job.get("Easy Apply", "").strip()
            link = job.get("Link", "").strip()

            # Convert LinkedIn search-result URLs to direct job URLs.
            if "currentJobId=" in link:
                match = re.search(r"currentJobId=(\d+)", link)

                if match:
                    job_id = match.group(1)
                    link = (
                        "https://www.linkedin.com/"
                        f"jobs/view/{job_id}/"
                    )

            description = ""

            print(f"Title   : {title}")
            print(f"Company : {company}")

            try:
                if not link:
                    print("No job link found.")
                    continue

                page.goto(
                    link,
                    wait_until="domcontentloaded",
                    timeout=30000
                )

                page.wait_for_timeout(2500)

                # Current title from the actual job page.
                actual_title = extract_text(page, ["h1"])
                if actual_title:
                    title = actual_title

                # Current company.
                linkedin_company = extract_company_from_header(page)

                if linkedin_company:
                    company = linkedin_company

                # Current location.
                linkedin_location = extract_location_from_header(page)

                if linkedin_location:
                    location = linkedin_location

                # Description.
                description = extract_description(page)

                print()

                if company:
                    print(f"Company extracted : {company}")
                else:
                    print("Company not found.")

                if location:
                    print(f"Location extracted: {location}")
                else:
                    print("Location not found.")

                if description:
                    print(
                        "Description extracted: "
                        f"{len(description)} characters"
                    )
                else:
                    print("Description not found.")

                results.append({
                    "Title": title,
                    "Company": company,
                    "Location": location,
                    "Experience": "",
                    "Easy Apply": easy_apply,
                    "Skills": "",
                    "Link": link,
                    "Description": description
                })

            except Exception as e:
                print(f"Error processing job {i}: {e}")

                results.append({
                    "Title": title,
                    "Company": company,
                    "Location": location,
                    "Experience": "",
                    "Easy Apply": easy_apply,
                    "Skills": "",
                    "Link": link,
                    "Description": ""
                })

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
                "Experience",
                "Easy Apply",
                "Skills",
                "Link",
                "Description"
            ],
            quoting=csv.QUOTE_ALL
        )

        writer.writeheader()

        for job in results:
            job["Description"] = (
                job.get("Description", "")
                .replace("\r", " ")
                .replace("\n", " ")
                .strip()
            )

            writer.writerow(job)

    descriptions_found = sum(
        1
        for job in results
        if job.get("Description", "").strip()
    )

    companies_found = sum(
        1
        for job in results
        if job.get("Company", "").strip()
    )

    locations_found = sum(
        1
        for job in results
        if job.get("Location", "").strip()
    )

    print()
    print("=" * 50)
    print("JOB DETAILS EXTRACTION COMPLETED")
    print("=" * 50)
    print(f"Jobs processed       : {len(results)}")
    print(f"Descriptions found   : {descriptions_found}")
    print(f"Companies found      : {companies_found}")
    print(f"Locations found      : {locations_found}")
    print(f"Saved file           : {OUTPUT_FILE}")
    print("=" * 50)


if __name__ == "__main__":
    extract_job_details()

