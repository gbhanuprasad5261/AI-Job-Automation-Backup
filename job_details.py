import csv
import json
import os
import re

from playwright.sync_api import sync_playwright
from config import CHROME_CDP_URL


INPUT_FILE = "jobs.csv"
OUTPUT_FILE = "data/job_details.csv"
DIAGNOSTICS_FILE = "data/job_details_diagnostics.json"
SDUI_DESCRIPTION_WAIT_MS = 2000


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

    Uses current-job header selectors first, then company links,
    and finally the LinkedIn page title as a reliable fallback.
    """

    selectors = [
        "div.job-details-jobs-unified-top-card__company-name a",
        "div.job-details-jobs-unified-top-card__company-name",
        "a.job-details-jobs-unified-top-card__company-name",
        "div.jobs-unified-top-card__company-name a",
        "div.jobs-unified-top-card__company-name",
    ]

    # 1. Current-job header selectors
    value = extract_text(page, selectors)
    if value:
        return value

    # 2. Current LinkedIn layout: company exposed as /company/ link
    try:
        links = page.locator("a[href*='/company/']")

        for i in range(links.count()):
            link = links.nth(i)

            if not link.is_visible():
                continue

            text = re.sub(
                r"\s+",
                " ",
                link.inner_text() or ""
            ).strip()

            if text and len(text) <= 150:
                return text

    except Exception:
        pass

    # 3. Locate company link near the current job title
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

    # 4. Last DOM-position fallback
    try:
        links = page.locator("a[href*='/company/']")
        h1 = page.locator("h1").first

        h1_box = h1.bounding_box()

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

                distance = abs(box["y"] - h1_box["y"])

                if distance <= 350:
                    candidates.append((distance, text))

            if candidates:
                candidates.sort(key=lambda x: x[0])
                return candidates[0][1]

    except Exception:
        pass

    # 5. LinkedIn page-title fallback
    # Example:
    # "Software Engineer Intern | SentLogic | LinkedIn"
    try:
        page_title = page.title().strip()

        if page_title:
            parts = [
                re.sub(r"\s+", " ", part).strip()
                for part in page_title.split("|")
            ]

            if len(parts) >= 3:
                company = parts[-2].strip()

                if (
                    company
                    and company.lower() != "linkedin"
                    and len(company) <= 150
                ):
                    return company

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


def _extract_sdui_description_content(locator):
    """Read the existing paragraph/expandable-box structure without clicking it."""
    text = ""
    content_selector = "p"
    ui_tail_excluded = False
    winner_suffix = " > p"

    paragraphs = locator.locator(content_selector)
    if paragraphs.count() > 0:
        paragraph = paragraphs.first
        expandable_box = paragraph.locator(
            '[data-testid="expandable-text-box"]'
        )
        if expandable_box.count() > 0:
            extraction = expandable_box.first.evaluate("""element => {
                const content = element.cloneNode(true);
                const parent = element.parentNode;
                if (!parent) {
                    return {text: element.innerText.trim(), ui_tail_excluded: false};
                }

                parent.insertBefore(content, element.nextSibling);
                try {
                    const button = content.querySelector(
                        '[data-testid="expandable-text-button"]'
                    );

                    if (button) {
                        const tailNode = button.previousSibling;
                        if (tailNode && tailNode.nodeType === Node.TEXT_NODE && tailNode.nodeValue) {
                            tailNode.remove();
                        }
                        button.remove();
                        return {
                            text: content.innerText.trimEnd(),
                            ui_tail_excluded: true
                        };
                    }

                    return {text: content.innerText.trim(), ui_tail_excluded: false};
                } finally {
                    content.remove();
                }
            }""")
            text = extraction["text"]
            ui_tail_excluded = extraction["ui_tail_excluded"]
            content_selector += ' > [data-testid="expandable-text-box"]'
            winner_suffix += ' > [data-testid="expandable-text-box"]'
            if ui_tail_excluded:
                winner_suffix += " (before expandable-text-button tail)"
        else:
            text = paragraph.inner_text().strip()

    return text, content_selector, ui_tail_excluded, winner_suffix


def extract_description(page, diagnostics=None):
    description = ""
    winner = None

    if diagnostics is None:
        diagnostics = {}

    diagnostics.update({
        "candidates": [],
        "body_fallback_reached": False,
        "body_contains_about_the_job": None,
        "body_text_length": None,
        "sdui_component_present": False,
        "winner": None,
        "selected_description_length": 0,
    })

    sdui_selector = 'div[data-sdui-component="com.linkedin.sdui.generated.jobseeker.dsl.impl.aboutTheJob"]'
    job_id_match = re.search(r"/jobs/view/(\d+)", page.url)
    current_job_description_selector = (
        f'div[id="JobDetails_AboutTheJob_{job_id_match.group(1)}"]'
        if job_id_match
        else 'div[id^="JobDetails_AboutTheJob_"]'
    )
    sdui_selectors = (current_job_description_selector, sdui_selector)
    selectors = [
        *sdui_selectors,
        "div.jobs-description__content",
        "div.jobs-box__html-content",
        "div#job-details",
        "article",
    ]

    sdui_description = ""
    sdui_winner_selector = None
    sdui_winner_suffix = " > p"
    compatibility_description = ""
    compatibility_winner = None
    job_specific_sdui_present = False
    job_specific_candidate_diagnostic = None

    for selector in selectors:
        match_count = 0
        text = ""
        content_selector = None
        ui_tail_excluded = False

        try:
            matches = page.locator(selector)
            match_count = matches.count()

            if match_count > 0:
                locator = matches.first
                if selector in sdui_selectors:
                    diagnostics["sdui_component_present"] = True
                    if selector == current_job_description_selector:
                        job_specific_sdui_present = True
                    (
                        text,
                        content_selector,
                        ui_tail_excluded,
                        candidate_winner_suffix,
                    ) = _extract_sdui_description_content(locator)
                else:
                    text = locator.inner_text().strip()
                    candidate_winner_suffix = None

                if text:
                    if selector in sdui_selectors and not sdui_description:
                        sdui_description = text
                        sdui_winner_selector = selector
                        sdui_winner_suffix = candidate_winner_suffix
                    elif len(text) > len(compatibility_description):
                        compatibility_description = text
                        compatibility_winner = selector
        except Exception:
            pass

        candidate_diagnostic = {
            "selector": selector,
            "matching_elements": match_count,
            "first_match_has_nonempty_text": bool(text),
            "text_length": len(text),
            "text_preview": text[:150],
            "contains_about_the_job": "About the job" in text,
        }
        if content_selector:
            candidate_diagnostic["description_content_selector"] = content_selector
        if selector in sdui_selectors:
            candidate_diagnostic["ui_tail_excluded"] = ui_tail_excluded
        diagnostics["candidates"].append(candidate_diagnostic)
        if selector == current_job_description_selector and match_count > 0:
            job_specific_candidate_diagnostic = candidate_diagnostic

    if job_specific_sdui_present:
        if sdui_description:
            diagnostics["sdui_wait_status"] = "available_immediately"
        elif compatibility_description:
            diagnostics["sdui_wait_status"] = "fallback_available_without_wait"
        else:
            try:
                page.wait_for_function(
                    """selector => {
                        const root = document.querySelector(selector);
                        const box = root && root.querySelector(
                            'p [data-testid="expandable-text-box"]'
                        );
                        return Boolean(box && (
                            (box.innerText || box.textContent || "").trim()
                        ));
                    }""",
                    arg=current_job_description_selector,
                    timeout=SDUI_DESCRIPTION_WAIT_MS,
                )
            except Exception:
                diagnostics["sdui_wait_status"] = "wait_expired_empty"
            else:
                diagnostics["sdui_wait_status"] = "wait_expired_empty"
                try:
                    locator = page.locator(current_job_description_selector).first
                    (
                        text,
                        content_selector,
                        ui_tail_excluded,
                        candidate_winner_suffix,
                    ) = _extract_sdui_description_content(locator)
                    if text:
                        sdui_description = text
                        sdui_winner_selector = current_job_description_selector
                        sdui_winner_suffix = candidate_winner_suffix
                        diagnostics["sdui_wait_status"] = "appeared_after_wait"
                        if job_specific_candidate_diagnostic is not None:
                            job_specific_candidate_diagnostic.update({
                                "first_match_has_nonempty_text": True,
                                "text_length": len(text),
                                "text_preview": text[:150],
                                "description_content_selector": content_selector,
                                "ui_tail_excluded": ui_tail_excluded,
                            })
                    else:
                        diagnostics["sdui_wait_status"] = "wait_completed_but_unusable"
                except Exception:
                    diagnostics["sdui_wait_status"] = "wait_completed_but_unusable"

    if sdui_description:
        description = sdui_description
        winner = sdui_winner_selector + sdui_winner_suffix
    elif compatibility_description:
        description = compatibility_description
        winner = compatibility_winner

    # Body fallback is reserved for pages where no scoped candidate yielded text.
    if not description and not diagnostics["sdui_component_present"]:
        diagnostics["body_fallback_reached"] = True
        try:
            body_text = page.locator("body").inner_text()
            body_has_description = "About the job" in body_text
            diagnostics["body_contains_about_the_job"] = body_has_description
            diagnostics["body_text_length"] = len(body_text)

            if body_has_description:
                description = body_text
                winner = "body.inner_text() fallback"
        except Exception:
            pass

    diagnostics["winner"] = winner
    diagnostics["selected_description_length"] = len(description)

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
    description_diagnostics = []

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(
            CHROME_CDP_URL
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
            job_diagnostic = {
                "job_url": link,
                "title": title,
            }

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
                description = extract_description(page, job_diagnostic)
                description_diagnostics.append(job_diagnostic)

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

                if not any(
                    item is job_diagnostic
                    for item in description_diagnostics
                ):
                    job_diagnostic["error"] = str(e)
                    description_diagnostics.append(job_diagnostic)

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

    with open(
        DIAGNOSTICS_FILE,
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(description_diagnostics, file, ensure_ascii=False, indent=2)

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



