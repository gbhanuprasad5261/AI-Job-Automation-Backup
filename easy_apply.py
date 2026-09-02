from datetime import datetime
from urllib.parse import urlparse
import csv
import os
import re

from application_form import inspect_and_prepare_form
from playwright.sync_api import sync_playwright

try:
    from external_apply import unwrap_linkedin_external_url
except ImportError:
    def unwrap_linkedin_external_url(url):
        return url

try:
    from external_apply import (
        external_apply,
        find_external_apply_link,
        prepare_external_application_page,
        check_external_eligibility,
    )
except ImportError:
    external_apply = None
    find_external_apply_link = None
    prepare_external_application_page = None
    check_external_eligibility = None


def get_external_profile():
    """Load the same profile used by LinkedIn Easy Apply.

    Environment variables take precedence, then config.py, then
    application_form.py defaults. This keeps external ATS and LinkedIn
    applications on one candidate profile.
    """
    try:
        import config as _config
    except Exception:
        _config = None

    try:
        import application_form as _form
    except Exception:
        _form = None

    def pick(env_names, config_names, form_names):
        for key in env_names:
            value = os.getenv(key)
            if value:
                return value
        if _config is not None:
            for key in config_names:
                value = getattr(_config, key, "")
                if value:
                    return value
        if _form is not None:
            for key in form_names:
                value = getattr(_form, key, "")
                if value:
                    return value
        return ""

    name = pick(["FULL_NAME", "JOB_NAME", "APPLICANT_NAME"], ["FULL_NAME", "JOB_NAME", "APPLICANT_NAME"], ["APPLICANT_NAME"])
    email = pick(["EMAIL", "JOB_EMAIL", "APPLICANT_EMAIL"], ["EMAIL", "JOB_EMAIL", "APPLICANT_EMAIL"], ["EMAIL"])
    phone = pick(["PHONE", "JOB_PHONE", "APPLICANT_PHONE"], ["PHONE", "JOB_PHONE", "APPLICANT_PHONE"], ["PHONE"])
    resume_path = pick(["RESUME_PATH"], ["RESUME_PATH"], ["RESUME_PATH"])

    if not resume_path:
        resume_path = os.path.abspath(os.path.join("resume", "resume.pdf"))

    return resume_path, name, email, phone


# ---------------------------------------
# Configuration
# ---------------------------------------

ANALYSIS_FILE = "data/job_analysis.csv"
TRACKER_FILE = "data/application_tracker.csv"

MIN_MATCH_SCORE = 70

CHROME_CDP_URL = "http://127.0.0.1:9222"

LAST_APPLICATION_RESULT = ""


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
    """
    Return tracker statuses keyed by LinkedIn job ID when possible,
    with a title fallback for legacy rows.
    """
    tracker = load_csv(TRACKER_FILE)
    statuses = {}

    for row in tracker:
        status = (
            row.get("Status")
            or row.get("Application Status")
            or "NOT APPLIED"
        ).strip().upper()

        link = (
            row.get("Link")
            or row.get("URL")
            or ""
        ).strip()

        match = re.search(
            r"/jobs/view/(\d+)",
            link
        )

        if match:
            statuses[f"id:{match.group(1)}"] = status

        title = (
            row.get("Title")
            or ""
        ).strip().lower()

        if title:
            statuses.setdefault(
                f"title:{title}",
                status
            )

    return statuses


def get_job_application_status(job, statuses=None):
    """Get a job's status using LinkedIn job ID first."""
    if statuses is None:
        statuses = get_application_statuses()

    link = convert_to_job_url(
        job.get("Link", "")
    )

    match = re.search(
        r"/jobs/view/(\d+)",
        link or ""
    )

    if match:
        return statuses.get(
            f"id:{match.group(1)}",
            "NOT APPLIED"
        )

    title = (
        job.get("Title")
        or ""
    ).strip().lower()

    return statuses.get(
        f"title:{title}",
        "NOT APPLIED"
    )


# ---------------------------------------
# Select Recommended Jobs
# ---------------------------------------

def _is_fresher_eligible(job):
    """Return True only when analyzer data confirms a 0-year candidate is eligible."""
    skip = str(job.get("Experience Skip", "") or "").strip().lower()
    years_raw = str(job.get("Experience Years", "") or "").strip()
    required_raw = str(job.get("Experience Required", "") or "").strip().lower()

    if skip in {"yes", "true", "1", "y"}:
        return False

    try:
        years = float(re.sub(r"[^0-9.]", "", years_raw) or "0")
    except (ValueError, TypeError):
        years = 0

    if years > 0:
        return False

    # Defensive check for analyzer text even if numeric columns are malformed.
    if re.search(r"\b[1-9]\d*\+?\s*years?\b", required_raw):
        return False

    return True


def get_recommended_jobs():
    jobs = load_csv(ANALYSIS_FILE)
    if not jobs:
        return []

    statuses = get_application_statuses()
    recommended = []

    for job in jobs:
        try:
            score = float(str(job.get("Match Score", "0")).replace("%", ""))
        except (ValueError, AttributeError, TypeError):
            score = 0

        status = get_job_application_status(job, statuses)

        if score < MIN_MATCH_SCORE:
            continue
        if status != "NOT APPLIED":
            continue
        if not _is_fresher_eligible(job):
            continue

        recommended.append(job)

    recommended.sort(
        key=lambda x: float(str(x.get("Match Score", "0")).replace("%", "") or "0"),
        reverse=True,
    )
    return recommended


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
    """Find an application control for the CURRENT LinkedIn job.

    LinkedIn changes its DOM frequently. Prefer stable job-application
    selectors first, then inspect the current top-card, and only then use
    tightly scoped fallbacks. Never use arbitrary sidebar ``Apply`` links.
    """
    def visible(e):
        try:
            return e.is_visible()
        except Exception:
            return False

    def info(e):
        try:
            text = (e.inner_text() or "").strip()
        except Exception:
            text = ""
        return (
            text,
            (e.get_attribute("aria-label") or "").strip(),
            (e.get_attribute("title") or "").strip(),
            (e.get_attribute("href") or "").strip(),
        )

    # LinkedIn's dedicated application area. These selectors are intentionally
    # checked globally because the apply control can sit outside the visual
    # top-card wrapper in the two-pane layout.
    stable_selectors = (
        ".jobs-s-apply button",
        ".jobs-s-apply a",
        ".jobs-s-apply [role='button']",
        ".jobs-s-apply [role='link']",
        "button.jobs-apply-button",
        "a.jobs-apply-button",
        "[data-control-name*='jobdetails_topcard_inapply' i]",
        "[data-control-name*='jobdetails_topcard_apply' i]",
        "[data-tracking-control-name*='jobdetails_topcard_inapply' i]",
        "[data-tracking-control-name*='jobdetails_topcard_apply' i]",
        "button[aria-label*='Easy Apply' i]",
        "button[aria-label*='Apply to this job' i]",
        "a[aria-label*='Easy Apply' i]",
        "a[aria-label*='Apply to this job' i]",
    )

    for selector in stable_selectors:
        try:
            loc = page.locator(selector)
            for i in range(loc.count()):
                e = loc.nth(i)
                if not visible(e):
                    continue
                text, aria, title, href = info(e)
                combined = f"{text} {aria} {title}".lower()
                if "easy apply" in combined or "apply to this job" in combined:
                    print("LinkedIn application control found in dedicated apply area.")
                    return e
                if selector.startswith(".jobs-s-apply") or "jobs-apply-button" in selector:
                    if text.lower() in {"apply", "easy apply"} or "apply" in combined:
                        print("LinkedIn application control found in dedicated apply area.")
                        return e
        except Exception:
            continue

    card = get_current_job_card(page)
    if card is not None:
        # Explicit controls inside the current top card.
        try:
            els = card.locator("button, a, [role='button'], [role='link']")
            for i in range(els.count()):
                e = els.nth(i)
                if not visible(e):
                    continue
                text, aria, title, href = info(e)
                combined = f"{text} {aria} {title}".lower()
                if "easy apply" in combined or "apply to this job" in combined:
                    print("Explicit Easy Apply control found in current job card.")
                    return e
        except Exception:
            pass

        # External company-website controls in the current card.
        try:
            els = card.locator("button, a, [role='button'], [role='link']")
            for i in range(els.count()):
                e = els.nth(i)
                if not visible(e):
                    continue
                text, aria, title, href = info(e)
                combined = f"{text} {aria} {title}".lower()
                if any(x in combined for x in (
                    "apply on company website",
                    "apply on the company website",
                    "apply externally",
                )):
                    print("External application control found in current job card.")
                    return None
        except Exception:
            pass

        # Plain Apply inside the current job card.
        try:
            els = card.locator("button, a, [role='button'], [role='link']")
            matches = []
            for i in range(els.count()):
                e = els.nth(i)
                if not visible(e):
                    continue
                text, aria, title, href = info(e)
                if text.lower() == "apply" or aria.lower() in {"apply", "apply to this job"}:
                    matches.append(e)
            if len(matches) == 1:
                print("Plain Apply control found in current job card.")
                return matches[0]
        except Exception:
            pass

    return None


# ---------------------------------------
# Check Whether Job Is Closed
# ---------------------------------------

def is_job_closed(body_text):
    """Detect only strong closed-job messages from the current job content.

    LinkedIn pages can contain closed-job wording in recommended/sidebar cards.
    The caller must first inspect real application controls. This helper is
    therefore intentionally conservative and is kept as a final fallback.
    """
    text = " ".join(str(body_text or "").lower().split())
    closed_messages = (
        "this job is no longer accepting applications",
        "this job is no longer available",
        "no longer accepting applications",
        "applications for this job are closed",
        "job is no longer accepting applications",
    )
    return any(message in text for message in closed_messages)


def get_current_job_card(page):
    """Return a narrowly scoped LinkedIn current-job header/card.

    Do not fall back to ``main`` because that can include recommended-job
    cards containing unrelated closed/open application text.
    """
    selectors = (
        "main .jobs-unified-top-card",
        ".jobs-unified-top-card",
        "main .job-details-jobs-unified-top-card",
        ".job-details-jobs-unified-top-card",
        "main .jobs-details-top-card",
        ".jobs-details-top-card",
    )
    for selector in selectors:
        try:
            loc = page.locator(selector)
            for i in range(loc.count()):
                item = loc.nth(i)
                if item.is_visible():
                    return item
        except Exception:
            continue
    return None


def current_job_is_closed(page):
    """Confirm closure only from a narrowly scoped current-job card."""
    try:
        card = get_current_job_card(page)
        if card is None:
            return False
        text = card.inner_text() or ""
        return is_job_closed(text)
    except Exception:
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

            if "URL" in fieldnames:
                new_row["URL"] = job.get("URL", "")

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
    external_page = None
    """
    Open a LinkedIn job and safely handle either:
      1. LinkedIn Easy Apply, or
      2. an external company/ATS application.

    External eligibility is checked before any resume upload or
    application preparation.
    """
    global LAST_APPLICATION_RESULT

    link = convert_to_job_url(
        job.get("Link", "")
    )

    if not link:
        print("Job URL not found.")
        LAST_APPLICATION_RESULT = "FAILED"
        return False

    print()
    print("=" * 70)
    print("OPENING JOB")
    print("=" * 70)
    print(f"Title   : {job.get('Title', '')}")
    print(f"Company : {job.get('Company') or 'Not available'}")
    print(f"Location: {job.get('Location') or 'Not available'}")
    print(f"Score   : {job.get('Match Score', '')}")
    print(f"URL     : {link}")

    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(
                CHROME_CDP_URL
            )
        except Exception as e:
            print()
            print("Could not connect to Chrome.")
            print("Start Chrome using:")
            print(".\\start_chrome.bat")
            print()
            print(f"Error: {e}")
            LAST_APPLICATION_RESULT = "FAILED"
            return False

        if not browser.contexts:
            print("No browser context found.")
            LAST_APPLICATION_RESULT = "FAILED"
            return False

        context = browser.contexts[0]

        # Find an existing LinkedIn tab.
        page = None

        for existing_page in context.pages:
            try:
                if "linkedin.com" in existing_page.url:
                    page = existing_page
                    break
            except Exception:
                continue

        if page is None:
            page = (
                context.pages[0]
                if context.pages
                else context.new_page()
            )

        try:
            page.goto(
                link,
                wait_until="domcontentloaded",
                timeout=30000
            )
            page.wait_for_timeout(5000)
        except Exception as e:
            print()
            print(f"Could not open job: {e}")
            LAST_APPLICATION_RESULT = "FAILED"
            return False

        print()
        print(f"Page title: {page.title()}")
        print(f"Current URL: {page.url}")

        try:
            body_text = page.locator(
                "body"
            ).inner_text()
        except Exception:
            body_text = ""

        print()
        print("Searching for Easy Apply button...")

        # Detect application controls before declaring a job closed.
        # LinkedIn can leave closed-job wording in surrounding/recommended
        # content even when the current job still exposes an Apply control.
        easy_apply_control = find_easy_apply_button(page)

        # --------------------------------------------------
        # External application detection
        # --------------------------------------------------
        external_url = ""

        if find_external_apply_link is not None:
            try:
                external_url = (
                    find_external_apply_link(page)
                    or ""
                )
            except Exception as e:
                print(
                    f"External apply-link detection failed: {e}"
                )

        # Fallback: inspect visible Apply/company-website controls.
        external_control = None

        if not external_url:
            try:
                apply_spans = page.locator(
                    "span,button,a,[role='button'],[role='link']"
                )

                for i in range(apply_spans.count()):
                    element = apply_spans.nth(i)

                    try:
                        if not element.is_visible():
                            continue

                        text_value = (
                            element.inner_text() or ""
                        ).strip().lower()

                        if text_value != "apply":
                            continue

                        # Ask the browser for the first ancestor that carries
                        # LinkedIn's external-application accessibility label.
                        ancestor = element.evaluate(
                            """(el) => {
                                let node = el;
                                for (let i = 0; node && i < 8; i++, node = node.parentElement) {
                                    const aria = (node.getAttribute('aria-label') || '').toLowerCase();
                                    const title = (node.getAttribute('title') || '').toLowerCase();
                                    const role = (node.getAttribute('role') || '').toLowerCase();

                                    if (
                                        aria.includes('apply on company website') ||
                                        aria.includes('apply on the company website') ||
                                        aria.includes('apply externally') ||
                                        title.includes('apply on company website') ||
                                        title.includes('apply on the company website') ||
                                        title.includes('apply externally')
                                    ) {
                                        return node;
                                    }
                                }
                                return null;
                            }"""
                        )

                        if ancestor is not None:
                            # Re-locate the exact DOM node using a JS-backed
                            # locator so Playwright can click it safely.
                            external_control = page.locator(
                                "xpath=//*"
                            ).filter(
                                has=page.locator(
                                    "xpath=."
                                )
                            )

                            # The generic locator above cannot reliably bind
                            # an arbitrary JS node. Instead, keep the original
                            # Apply element and click it; the event bubbles to
                            # LinkedIn's labelled ancestor.
                            external_control = element
                            print(
                                "External application control detected "
                                "through Apply ancestor label."
                            )
                            break

                    except Exception:
                        continue

            except Exception:
                pass

        # Secondary fallback: inspect all visible elements directly for the
        # accessibility label, including elements that are not buttons.
        if not external_url and external_control is None:
            try:
                labelled = page.locator(
                    "[aria-label*='Apply on company website' i],"
                    "[aria-label*='Apply on the company website' i],"
                    "[aria-label*='Apply externally' i],"
                    "[title*='Apply on company website' i],"
                    "[title*='Apply on the company website' i],"
                    "[title*='Apply externally' i]"
                )

                for i in range(labelled.count()):
                    candidate = labelled.nth(i)
                    if candidate.is_visible():
                        external_control = candidate
                        print(
                            "External application control found "
                            "by accessibility label."
                        )
                        break
            except Exception:
                pass

            try:
                elements = page.locator(
                    "a[href], button, [role='button'], span, p"
                )

                for i in range(elements.count()):
                    element = elements.nth(i)

                    try:
                        if not element.is_visible():
                            continue

                        text_value = (
                            element.inner_text() or ""
                        ).strip().lower()

                        aria = (
                            element.get_attribute("aria-label") or ""
                        ).strip().lower()

                        title = (
                            element.get_attribute("title") or ""
                        ).strip().lower()

                        href = (
                            element.get_attribute("href") or ""
                        )

                        combined = f"{text_value} {aria} {title}"

                        external_signal = (
                            "apply on company website" in combined
                            or "apply on the company website" in combined
                            or "apply externally" in combined
                        )

                        if external_signal:
                            if (
                                href
                                and "linkedin.com" not in href.lower()
                            ):
                                external_url = href
                                break

                            if external_control is None:
                                external_control = element

                        # LinkedIn places the visible "Apply" text in a
                        # child span while the accessibility label is often
                        # on a parent button/link.
                        if (
                            not external_signal
                            and text_value == "apply"
                        ):
                            ancestors = element.locator(
                                "xpath=ancestor::*[position() <= 6]"
                            )

                            for j in range(ancestors.count()):
                                ancestor = ancestors.nth(j)

                                try:
                                    ancestor_aria = (
                                        ancestor.get_attribute(
                                            "aria-label"
                                        ) or ""
                                    ).strip().lower()

                                    ancestor_title = (
                                        ancestor.get_attribute(
                                            "title"
                                        ) or ""
                                    ).strip().lower()

                                    ancestor_href = (
                                        ancestor.get_attribute(
                                            "href"
                                        ) or ""
                                    )

                                    ancestor_combined = (
                                        f"{ancestor_aria} "
                                        f"{ancestor_title}"
                                    )

                                    if not (
                                        "apply on company website"
                                        in ancestor_combined
                                        or
                                        "apply on the company website"
                                        in ancestor_combined
                                        or
                                        "apply externally"
                                        in ancestor_combined
                                    ):
                                        continue

                                    if (
                                        ancestor_href
                                        and
                                        "linkedin.com"
                                        not in ancestor_href.lower()
                                    ):
                                        external_url = ancestor_href
                                    else:
                                        external_control = ancestor

                                    break

                                except Exception:
                                    continue

                            if external_url:
                                break

                    except Exception:
                        continue

            except Exception:
                pass

        # Final fallback: LinkedIn's current job card may expose a plain
        # "Apply" button without the accessibility label used by older layouts.
        # Restrict this search to the current job card so recommendation cards
        # do not get mistaken for the current job's application control.
        if not easy_apply_control and not external_url and external_control is None:
            try:
                card = get_current_job_card(page)
                plain_apply = card.get_by_role("button", name=re.compile(r"^\s*apply\s*$", re.I))
                if plain_apply.count() > 0:
                    for i in range(plain_apply.count()):
                        candidate = plain_apply.nth(i)
                        if candidate.is_visible():
                            external_control = candidate
                            print("Plain Apply button found in current job card.")
                            break
            except Exception:
                pass

        # If no application route was found, only then treat a strong LinkedIn
        # closed message as a confirmed CLOSED result. This avoids letting
        # unrelated page/sidebar text prematurely terminate an active job.
        if not easy_apply_control and not external_url and external_control is None:
            if current_job_is_closed(page):
                print()
                print("=" * 70)
                print("JOB CLOSED")
                print("=" * 70)
                print("LinkedIn's current-job card reports that this job is no longer accepting applications.")
                LAST_APPLICATION_RESULT = "CLOSED"
                return False

        # --------------------------------------------------
        # LinkedIn "Apply on company website" button with no href
        # --------------------------------------------------
        # If LinkedIn exposed a real external URL, navigate directly to it.
        # This is more reliable than clicking the child "Apply" span and
        # accidentally landing on LinkedIn's /safety/go/ page.
        if external_url and external_apply is not None:
            resolved_url = unwrap_linkedin_external_url(external_url)
            if resolved_url and "linkedin.com" not in urlparse(resolved_url).netloc.lower():
                try:
                    print()
                    print("External application URL found directly.")
                    print(f"Opening: {resolved_url}")
                    external_page = context.new_page()
                    external_page.goto(
                        resolved_url,
                        wait_until="domcontentloaded",
                        timeout=60000,
                    )
                    external_page.wait_for_timeout(4000)
                except Exception as e:
                    print(f"Direct external navigation failed: {e}")
                    external_page = None

                if external_page is not None:
                    print()
                    print("=" * 70)
                    print("LINKEDIN OPENED EXTERNAL APPLICATION")
                    print("=" * 70)
                    print(f"External URL: {external_page.url}")

                    if check_external_eligibility is not None:
                        try:
                            eligibility = check_external_eligibility(external_page)
                        except Exception as e:
                            print(f"External eligibility check failed: {e}")
                            LAST_APPLICATION_RESULT = "UNKNOWN"
                            return False

                        if eligibility == "INELIGIBLE":
                            record_application_status(job, "INELIGIBLE")
                            LAST_APPLICATION_RESULT = "INELIGIBLE"
                            print("Application skipped - external role requires more experience.")
                            return False

                    if get_external_profile is not None and prepare_external_application_page is not None:
                        try:
                            resume_path, name, email, phone = get_external_profile()
                            result = prepare_external_application_page(
                                external_page, resume_path, name, email, phone
                            )
                            record_application_status(job, result)
                            LAST_APPLICATION_RESULT = result
                            print(f"External application result: {result}")
                            return False
                        except Exception as e:
                            print(f"External application preparation failed: {e}")
                            LAST_APPLICATION_RESULT = "FAILED"
                            return False

        if (
            not external_url
            and external_control is not None
            and external_apply is not None
        ):
            print()
            print("External application control found.")
            print("Opening company application...")

            pages_before_external_click = list(
                context.pages
            )

            try:
                external_control.scroll_into_view_if_needed()
                external_control.click(
                    timeout=10000
                )
            except Exception as e:
                print(
                    f"External control click failed: {e}"
                )
                try:
                    external_control.evaluate(
                        "(element) => element.click()"
                    )
                except Exception as js_error:
                    print(
                        f"External JavaScript click failed: {js_error}"
                    )
                    LAST_APPLICATION_RESULT = "FAILED"
                    return False

            page.wait_for_timeout(4000)

            # LinkedIn may show an intermediate "Continue applying" step
            # before opening the company's external application.
            try:
                continue_apply = page.get_by_text(
                    "Continue applying",
                    exact=True
                )

                if continue_apply.count() > 0:
                    for i in range(continue_apply.count()):
                        candidate_button = continue_apply.nth(i)
                        try:
                            if candidate_button.is_visible():
                                print("LinkedIn confirmation step detected.")
                                print("Clicking Continue applying...")
                                candidate_button.click(timeout=10000)
                                page.wait_for_timeout(5000)
                                break
                        except Exception:
                            continue

            except Exception as e:
                print(f"Continue applying step not clicked: {e}")

            # Prefer a newly opened non-LinkedIn page.
            for candidate in context.pages:
                try:
                    if candidate in pages_before_external_click:
                        continue
                    if "linkedin.com" not in candidate.url.lower():
                        external_page = candidate
                        break
                except Exception:
                    continue

            # If LinkedIn navigated the current page instead of opening a
            # new tab, use that page.
            if "linkedin.com" not in page.url.lower():
                external_page = page

            if external_page is not None:
                # LinkedIn may land on /safety/go/?url=... instead of the ATS.
                # Resolve the destination before ATS detection/eligibility checks.
                resolved_url = unwrap_linkedin_external_url(external_page.url)
                if resolved_url and resolved_url != external_page.url and "linkedin.com/safety/go" in external_page.url.lower():
                    try:
                        print("LinkedIn safety redirect detected.")
                        print(f"Resolved external URL: {resolved_url}")
                        external_page.goto(resolved_url, wait_until="domcontentloaded", timeout=60000)
                        external_page.wait_for_timeout(4000)
                    except Exception as e:
                        print(f"Could not resolve LinkedIn external redirect: {e}")
                        LAST_APPLICATION_RESULT = "FAILED"
                        return False

                print()
                print("=" * 70)
                print("LINKEDIN OPENED EXTERNAL APPLICATION")
                print("=" * 70)
                print(
                    f"External URL: {external_page.url}"
                )

                if check_external_eligibility is not None:
                    try:
                        eligibility = (
                            check_external_eligibility(
                                external_page
                            )
                        )
                    except Exception as e:
                        print()
                        print(
                            "External eligibility check failed:"
                        )
                        print(e)
                        LAST_APPLICATION_RESULT = "UNKNOWN"
                        return False

                    if eligibility == "INELIGIBLE":
                        record_application_status(
                            job,
                            "INELIGIBLE"
                        )
                        LAST_APPLICATION_RESULT = "INELIGIBLE"

                        print()
                        print("=" * 70)
                        print(
                            "APPLICATION SKIPPED - INELIGIBLE"
                        )
                        print("=" * 70)
                        print(
                            "No resume upload or application "
                            "preparation was performed."
                        )
                        print("No application was submitted.")
                        return False

                if get_external_profile is not None:
                    try:
                        (
                            resume_path,
                            name,
                            email,
                            phone
                        ) = get_external_profile()
                    except Exception:
                        resume_path = ""
                        name = ""
                        email = ""
                        phone = ""
                else:
                    resume_path = ""
                    name = ""
                    email = ""
                    phone = ""

                try:
                    external_result = (
                        prepare_external_application_page(
                            external_page,
                            resume_path,
                            name,
                            email,
                            phone,
                        )
                    )
                except Exception as e:
                    print()
                    print(
                        "External application preparation failed:"
                    )
                    print(e)
                    LAST_APPLICATION_RESULT = "FAILED"
                    return False

                result_status = (
                    external_result
                    if isinstance(
                        external_result,
                        str
                    )
                    else "READY_FOR_REVIEW"
                ).strip().upper()

                print()
                print(
                    f"External application result: "
                    f"{result_status or 'UNKNOWN'}"
                )

                if result_status == "READY_FOR_REVIEW":
                    record_application_status(
                        job,
                        "READY_FOR_REVIEW"
                    )
                    LAST_APPLICATION_RESULT = "READY_FOR_REVIEW"
                    return False

                if result_status == "SUBMITTED":
                    record_application_status(
                        job,
                        "APPLIED"
                    )
                    LAST_APPLICATION_RESULT = "SUBMITTED"
                    return True

                if result_status == "INELIGIBLE":
                    record_application_status(
                        job,
                        "INELIGIBLE"
                    )
                    LAST_APPLICATION_RESULT = "INELIGIBLE"
                    return False

                LAST_APPLICATION_RESULT = (
                    result_status or "UNKNOWN"
                )
                return False

        if external_url and external_apply is not None:
            print()
            print("=" * 70)
            print("EXTERNAL APPLICATION DETECTED")
            print("=" * 70)
            print(
                f"External URL: {external_url}"
            )

            # Open external page ourselves. This ensures the eligibility
            # check sees the job-description page before preparation.
            try:
                external_page = context.new_page()

                external_url = unwrap_linkedin_external_url(external_url)
                external_page.goto(
                    external_url,
                    wait_until="domcontentloaded",
                    timeout=60000
                )

                external_page.wait_for_timeout(
                    5000
                )

                print(
                    f"External page: "
                    f"{external_page.url}"
                )

            except Exception as e:
                print()
                print(
                    f"Could not open external application: {e}"
                )
                LAST_APPLICATION_RESULT = "FAILED"
                return False

            # --------------------------------------------------
            # CRITICAL SAFETY GATE
            # --------------------------------------------------
            if check_external_eligibility is not None:
                try:
                    eligibility = (
                        check_external_eligibility(
                            external_page
                        )
                    )
                except Exception as e:
                    print()
                    print(
                        "External eligibility check failed:"
                    )
                    print(e)
                    LAST_APPLICATION_RESULT = "UNKNOWN"
                    return False

                if eligibility == "INELIGIBLE":
                    record_application_status(
                        job,
                        "INELIGIBLE"
                    )

                    LAST_APPLICATION_RESULT = (
                        "INELIGIBLE"
                    )

                    print()
                    print("=" * 70)
                    print(
                        "APPLICATION SKIPPED - INELIGIBLE"
                    )
                    print("=" * 70)
                    print(
                        "No resume upload or application "
                        "preparation was performed."
                    )
                    print(
                        "No application was submitted."
                    )

                    return False

                if eligibility == "UNKNOWN":
                    print()
                    print(
                        "External eligibility could not be "
                        "confirmed."
                    )
                    print(
                        "Continuing only to manual review."
                    )

            # --------------------------------------------------
            # Only now prepare the external application.
            # --------------------------------------------------
            if get_external_profile is not None:
                try:
                    (
                        resume_path,
                        name,
                        email,
                        phone
                    ) = get_external_profile()
                except Exception as e:
                    print()
                    print(
                        f"Could not load external profile: {e}"
                    )
                    resume_path = ""
                    name = ""
                    email = ""
                    phone = ""
            else:
                resume_path = ""
                name = ""
                email = ""
                phone = ""

            if not name or not email or not phone:
                print()
                print(
                    "External profile is incomplete."
                )
                print(
                    "Configure FULL_NAME/EMAIL/PHONE "
                    "in config.py or "
                    "JOB_NAME/JOB_EMAIL/JOB_PHONE "
                    "environment variables."
                )

            try:
                external_result = (
                    prepare_external_application_page(
                        external_page,
                        resume_path,
                        name,
                        email,
                        phone,
                    )
                )
            except Exception as e:
                print()
                print(
                    "External application preparation failed:"
                )
                print(e)
                LAST_APPLICATION_RESULT = "FAILED"
                return False

            result_status = (
                external_result
                if isinstance(
                    external_result,
                    str
                )
                else "READY_FOR_REVIEW"
            )

            result_status = (
                result_status
                .strip()
                .upper()
            )

            print()
            print(
                f"External application result: "
                f"{result_status or 'UNKNOWN'}"
            )

            if result_status == "INELIGIBLE":
                record_application_status(
                    job,
                    "INELIGIBLE"
                )
                LAST_APPLICATION_RESULT = (
                    "INELIGIBLE"
                )
                return False

            if result_status == "LOGIN_REQUIRED":
                record_application_status(
                    job,
                    "LOGIN_REQUIRED"
                )
                LAST_APPLICATION_RESULT = (
                    "LOGIN_REQUIRED"
                )
                return False

            if result_status == "SUBMITTED":
                record_application_status(
                    job,
                    "APPLIED"
                )
                LAST_APPLICATION_RESULT = (
                    "SUBMITTED"
                )
                return True

            if result_status == "READY_FOR_REVIEW":
                record_application_status(
                    job,
                    "READY_FOR_REVIEW"
                )
                LAST_APPLICATION_RESULT = (
                    "READY_FOR_REVIEW"
                )
                return False

            LAST_APPLICATION_RESULT = (
                result_status or "UNKNOWN"
            )
            return False

        # --------------------------------------------------
        # LinkedIn Easy Apply
        # --------------------------------------------------
        if easy_apply_control is None:
            print()
            print("=" * 70)
            print("EASY APPLY / EXTERNAL APPLY NOT FOUND")
            print("=" * 70)

            print_application_controls(page)
            save_diagnostic_screenshot(page)

            LAST_APPLICATION_RESULT = (
                "NOT_AVAILABLE"
            )
            return False

        print()
        print("=" * 70)
        print("EASY APPLY BUTTON FOUND")
        print("=" * 70)

        try:
            easy_apply_control.scroll_into_view_if_needed()
            page.wait_for_timeout(500)

            easy_apply_control.click(
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
                easy_apply_control.evaluate(
                    "(element) => element.click()"
                )
            except Exception as js_error:
                print(
                    "JavaScript click failed:"
                )
                print(js_error)
                LAST_APPLICATION_RESULT = "FAILED"
                return False

        page.wait_for_timeout(3000)

        print()
        print("=" * 70)
        print("EASY APPLY FORM OPENED")
        print("=" * 70)

        try:
            application_success = (
                inspect_and_prepare_form(
                    page
                )
            )

            if application_success:
                record_application_status(
                    job,
                    "APPLIED"
                )
                LAST_APPLICATION_RESULT = (
                    "SUBMITTED"
                )
                return True

        except Exception as e:
            print()
            print(
                "Application form automation failed:"
            )
            print(e)
            LAST_APPLICATION_RESULT = "FAILED"
            return False

        LAST_APPLICATION_RESULT = (
            "READY_FOR_REVIEW"
        )
        return False


# ---------------------------------------
# Daily application limit
# ---------------------------------------

def get_today_applied_count():
    """Return the number of confirmed APPLIED jobs recorded today."""
    if not os.path.exists(TRACKER_FILE):
        return 0

    today = datetime.now().strftime("%Y-%m-%d")
    try:
        with open(TRACKER_FILE, "r", encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
    except Exception:
        return 0

    count = 0
    for row in rows:
        status = (row.get("Status") or row.get("Application Status") or "").strip().upper()
        applied_date = (row.get("Applied Date") or "").strip()
        if status == "APPLIED" and applied_date == today:
            count += 1
    return count


# ---------------------------------------
# Main
# ---------------------------------------

def main():

    print()
    print("=" * 70)
    print("AI JOB AUTOMATION - EASY APPLY")
    print("=" * 70)

    daily_limit = max(1, int(os.getenv("DAILY_APPLICATION_LIMIT", "15")))
    already_applied = get_today_applied_count()
    remaining_today = max(0, daily_limit - already_applied)

    print()
    print(f"Daily application limit : {daily_limit}")
    print(f"Confirmed applications today: {already_applied}")
    print(f"Remaining applications today: {remaining_today}")

    if remaining_today <= 0:
        print("Daily application limit reached.")
        return

    jobs = get_recommended_jobs()

    # Final defense: never put a role marked Experience Skip=Yes or requiring
    # more than 0 years into the application queue, even if CSV data changes.
    jobs = [job for job in jobs if _is_fresher_eligible(job)]

    print()
    print(f"Eligible jobs: {len(jobs)}")

    display_jobs(jobs)

    if not jobs:
        return

    print()
    try:
        choice = int(input(f"Select starting job (1-{len(jobs)}): "))
    except ValueError:
        print("Invalid selection.")
        return

    if choice < 1 or choice > len(jobs):
        print("Invalid job number.")
        return

    confirmed_this_run = 0

    for index in range(choice - 1, len(jobs)):
        if confirmed_this_run >= remaining_today:
            break

        job = jobs[index]

        print()
        print("=" * 70)
        print(f"TRYING JOB {index + 1}/{len(jobs)}")
        print("=" * 70)
        print(f"Title : {job.get('Title', '')}")
        print(f"Score : {job.get('Match Score', '')}")

        success = open_easy_apply(job)

        if success:
            confirmed_this_run += 1
            print()
            print("=" * 70)
            print(f"APPLICATION CONFIRMED ({confirmed_this_run}/{remaining_today} this run)")
            print("=" * 70)
            continue

        # Non-success results are already recorded by open_easy_apply when
        # the result is known (READY_FOR_REVIEW, INELIGIBLE, etc.).
        result = globals().get("LAST_APPLICATION_RESULT", "UNKNOWN")
        print(f"Result: {result}")

        if index + 1 < len(jobs):
            print("Trying next eligible job...")

    print()
    print("=" * 70)
    print("RUN SUMMARY")
    print("=" * 70)
    print(f"Confirmed applications this run : {confirmed_this_run}")
    print(f"Confirmed applications today    : {already_applied + confirmed_this_run}")
    print(f"Daily limit                     : {daily_limit}")

    if confirmed_this_run >= remaining_today:
        print("Daily application limit reached for this run.")
    else:
        print("No more eligible jobs were successfully submitted.")


# ---------------------------------------
# Entry Point
# ---------------------------------------

if __name__ == "__main__":
    main()