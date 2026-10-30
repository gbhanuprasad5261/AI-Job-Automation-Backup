import csv
import hashlib
import os
import re
import tempfile
import time
from collections import Counter
from datetime import datetime

import config
from execution_policy import EXECUTION_POLICY
from application_form import get_application_container, inspect_and_prepare_form
from external_app import (
    find_external_apply_link,
    inspect_external_apply_link,
    _control_job_association_status,
    is_safe_external_application_url,
    is_safe_external_application_redirect,
    check_external_eligibility,
    prepare_external_application_page,
)
from playwright.sync_api import sync_playwright
from runtime_diagnostics import (
    element_diagnostic,
    page_diagnostic,
    selector_diagnostics,
    write_diagnostic,
)


# ---------------------------------------
# Configuration
# ---------------------------------------

ANALYSIS_FILE = "data/job_analysis.csv"
DETAILS_FILE = "data/job_details.csv"
JOBS_FILE = "jobs.csv"
TRACKER_FILE = "data/application_tracker.csv"
APPLICATION_HISTORY_FILE = "data/application_history.csv"

MAX_CANDIDATE_JOBS_PER_RUN = 30

ALLOWED_LOCATION_KEYWORDS = (
    "bengaluru",
    "bangalore",
    "hyderabad",
    "chennai",
    "remote",
)

ALLOW_EXTERNAL_APPLICATIONS = True


def _atomic_write_csv(file_path, fieldnames, rows):
    """Write CSV rows beside the destination, then atomically replace it."""
    directory = os.path.dirname(file_path) or "."
    prefix = f".{os.path.basename(file_path)}."
    temp_path = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            dir=directory,
            prefix=prefix,
            suffix=".tmp",
            delete=False,
        ) as temp_file:
            temp_path = temp_file.name
            writer = csv.DictWriter(temp_file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
            temp_file.flush()
            os.fsync(temp_file.fileno())

        os.replace(temp_path, file_path)
        temp_path = None
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass

EASY_APPLY_MODAL_SELECTORS = (
    ".jobs-easy-apply-modal",
    ".jobs-easy-apply-content",
    "[class*='jobs-easy-apply']",
    ".artdeco-modal[role='dialog']",
    "[aria-modal='true']",
    "[role='dialog']",
)
EASY_APPLY_SDUI_SELECTOR = (
    'div[data-sdui-screen="'
    'com.linkedin.sdui.flagshipnav.jobs.easyapply.EasyApply"]'
)


def _sdui_easy_apply_diagnostics(candidate_page):
    """Summarize the observed SDUI Easy Apply screen without accepting its button."""
    result = {
        "selector": EASY_APPLY_SDUI_SELECTOR,
        "match_count": 0,
        "visible_match_count": 0,
        "candidates": [],
    }
    try:
        locator = candidate_page.locator(EASY_APPLY_SDUI_SELECTOR)
        result["match_count"] = locator.count()
        for index in range(result["match_count"]):
            element = locator.nth(index)
            try:
                if not element.is_visible():
                    continue
            except Exception:
                continue
            result["visible_match_count"] += 1
            if len(result["candidates"]) >= 3:
                continue
            try:
                class_name = element.get_attribute("class") or ""
            except Exception:
                class_name = ""
            try:
                text_preview = " ".join((element.inner_text() or "").split())[:240]
            except Exception:
                text_preview = ""
            result["candidates"].append({
                "class": class_name,
                "text_preview": text_preview,
            })
    except Exception:
        pass
    return result


def _detect_easy_apply_container(candidate_page):
    """Return the existing legacy detection or the visible SDUI screen signal."""
    for selector in EASY_APPLY_MODAL_SELECTORS:
        try:
            locator = candidate_page.locator(selector)
            for index in range(locator.count()):
                element = locator.nth(index)
                if not element.is_visible():
                    continue
                try:
                    text = (element.inner_text() or "").lower()
                except Exception:
                    text = ""
                try:
                    class_name = element.get_attribute("class") or ""
                except Exception:
                    class_name = ""
                if any(token in text for token in (
                    "resume", "contact info",
                    "contact information", "work experience", "education",
                    "review your application", "review application",
                    "continue to next step", "application questions",
                    "application form",
                )) or "jobs-easy-apply" in class_name:
                    return {
                        "detected": True,
                        "source": "legacy",
                        "sdui_diagnostics": None,
                    }
        except Exception:
            continue

    sdui_diagnostics = _sdui_easy_apply_diagnostics(candidate_page)
    if sdui_diagnostics["visible_match_count"]:
        return {
            "detected": True,
            "source": "sdui",
            "sdui_diagnostics": sdui_diagnostics,
        }
    return {
        "detected": False,
        "source": None,
        "sdui_diagnostics": sdui_diagnostics,
    }


def _has_specific_application_container_signal(container):
    """Reject generic Submit-only wrappers returned by broad container scans."""
    try:
        if not container.is_visible():
            return False

        attrs = " ".join(
            (container.get_attribute(name) or "")
            for name in ("class", "id", "aria-label", "data-test-modal", "role")
        ).lower()
        if any(marker in attrs for marker in (
            "jobs-easy-apply", "easy-apply", "easyapply",
        )):
            return True

        text = " ".join((container.inner_text() or "").lower().split())
        return any(signal in text for signal in (
            "contact info", "contact information", "resume", "work experience",
            "education", "review your application", "review application",
            "continue to next step", "application questions", "application form",
            "phone number", "cover letter", "additional questions",
            "screening questions",
        ))
    except Exception:
        return False


def _eligible_easy_apply_pages(original_page, pages):
    """Keep detection on the clicked page and LinkedIn popup pages only."""
    candidates = [original_page]
    for candidate_page in pages:
        if candidate_page is original_page:
            continue
        try:
            if "linkedin.com" in (candidate_page.url or "").lower():
                candidates.append(candidate_page)
        except Exception:
            continue
    return candidates


def _find_validated_application_container(candidate_pages, wait_seconds=12):
    """Wait for a validated application container on the eligible pages."""
    for candidate_page in candidate_pages:
        try:
            container = get_application_container(
                candidate_page,
                wait_seconds=wait_seconds,
            )
        except Exception:
            continue
        if container is not None and _has_specific_application_container_signal(container):
            return candidate_page, container
    return None, None

# ---------------------------------------
# Navigation helper
# ---------------------------------------

def navigate_page(page, url, timeout=30000, settle_ms=5000, required_url_fragment=None):
    """Navigate while tolerating slow post-navigation page loading."""
    if not EXECUTION_POLICY.allows_browser_actions():
        print("DRY_RUN: browser navigation skipped.")
        return False

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


class DailyApplicationCountUnavailable(RuntimeError):
    """Raised when both stores cannot provide a trustworthy daily count."""


def _read_daily_limit_rows(file_path, source_name):
    try:
        with open(file_path, "r", encoding="utf-8", newline="") as file:
            reader = csv.DictReader(file)
            columns = {
                (name or "").strip().casefold(): name
                for name in (reader.fieldnames or [])
            }
            fieldnames = reader.fieldnames or []
            if (
                not fieldnames
                or any(not isinstance(name, str) or not name.strip() for name in fieldnames)
                or len({name.strip().casefold() for name in fieldnames}) != len(fieldnames)
            ):
                raise DailyApplicationCountUnavailable(
                    f"{source_name} has an invalid or duplicate CSV header."
                )
            status_columns = [
                columns[name]
                for name in ("status", "application status")
                if name in columns
            ]
            date_column = columns.get("applied date")
            url_columns = [
                columns[name]
                for name in ("url", "link")
                if name in columns
            ]
            if not status_columns or not date_column or not url_columns:
                raise DailyApplicationCountUnavailable(
                    f"{source_name} is missing Status, Applied Date, or URL/Link columns."
                )
            rows = list(reader)
            if any(
                None in row or any(value is None for value in row.values())
                for row in rows
            ):
                raise DailyApplicationCountUnavailable(
                    f"{source_name} contains a malformed CSV row."
                )
            return rows, status_columns, date_column, url_columns
    except DailyApplicationCountUnavailable:
        raise
    except (OSError, csv.Error, UnicodeError) as exc:
        raise DailyApplicationCountUnavailable(
            f"Could not read {source_name} ({exc})."
        ) from exc


def get_today_applied_count():
    """Count today's confirmed applications across tracker and history once."""
    today = datetime.now().strftime("%Y-%m-%d")
    confirmed_urls = set()
    for file_path, source_name in (
        (APPLICATION_HISTORY_FILE, "application history"),
        (TRACKER_FILE, "application tracker"),
    ):
        rows, status_columns, date_column, url_columns = _read_daily_limit_rows(
            file_path,
            source_name,
        )
        for row in rows:
            statuses = {
                (row.get(column) or "").strip().upper()
                for column in status_columns
            }
            # The persistence path requires submission confirmation and
            # normalizes SUBMITTED to APPLIED before writing. A raw legacy
            # SUBMITTED value alone is not sufficient confirmation.
            if "APPLIED" not in statuses:
                continue
            applied_date = (row.get(date_column) or "").strip()
            if not applied_date:
                raise DailyApplicationCountUnavailable(
                    f"A confirmed record in {source_name} has no Applied Date."
                )
            try:
                datetime.strptime(applied_date, "%Y-%m-%d")
            except ValueError as exc:
                raise DailyApplicationCountUnavailable(
                    f"{source_name} contains an invalid Applied Date."
                ) from exc
            if applied_date != today:
                continue

            job_url = _normalize_url(
                convert_to_job_url(
                    next((row.get(column) for column in url_columns if row.get(column)), "")
                )
            )
            if not job_url:
                raise DailyApplicationCountUnavailable(
                    f"A confirmed today's record in {source_name} has no usable job URL."
                )
            confirmed_urls.add(job_url)

    return len(confirmed_urls)


def _history_status_for_job(job):
    """Return APPLIED when this exact job is already in submission history."""
    job_url = _normalize_url(
        convert_to_job_url(job.get("Link", "") or job.get("URL", ""))
    )
    title = _normalize_text(job.get("Title", ""))
    company = _normalize_text(job.get("Company", ""))

    rows = _load_application_history()
    for row in rows:
        status = (row.get("Status") or "").strip().upper()
        if status != "APPLIED":
            continue

        row_url = _normalize_url(
            convert_to_job_url(row.get("URL") or row.get("Link") or "")
        )

        if job_url and row_url and job_url == row_url:
            return "APPLIED"

    row = _unique_title_company_match(rows, title, company, job_url)
    if row and (row.get("Status") or "").strip().upper() == "APPLIED":
        return "APPLIED"

    return "NOT APPLIED"


def _record_application_history(job, status, submission_confirmed=False):
    """Persist confirmed application status in one shared history CSV."""
    if not EXECUTION_POLICY.allows_persistence():
        print("DRY_RUN: application history write skipped.")
        return False

    if status != "APPLIED":
        return True
    if not submission_confirmed:
        print("Application history write blocked: submission is not confirmed.")
        return False

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

    # Prefer exact URLs; use title/company only for a unique, non-conflicting row.
    for row in rows:
        row_url = _normalize_url(
            convert_to_job_url(row.get("URL") or row.get("Link") or "")
        )
        if job_url and row_url and job_url == row_url:
            row["Status"] = "APPLIED"
            row["Applied Date"] = row.get("Applied Date") or datetime.now().strftime("%Y-%m-%d")
            return _write_application_history(rows, fields)

    row = _unique_title_company_match(rows, title, company, job_url)
    if row:
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
    if not EXECUTION_POLICY.allows_persistence():
        print("DRY_RUN: application history write skipped.")
        return False

    try:
        _atomic_write_csv(APPLICATION_HISTORY_FILE, fields, rows)
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

def _unique_title_company_match(rows, title, company, job_url=""):
    """Return a sole title/company candidate unless its URL conflicts."""
    if not title or not company:
        return None

    candidates = [
        row
        for row in rows
        if _normalize_text(row.get("Title")) == title
        and _normalize_text(row.get("Company")) == company
    ]
    if len(candidates) != 1:
        return None

    candidate = candidates[0]
    candidate_url = _normalize_url(
        convert_to_job_url(candidate.get("URL") or candidate.get("Link") or "")
    )
    if job_url and candidate_url and job_url != candidate_url:
        return None

    return candidate

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

    row = _unique_title_company_match(tracker, title, company, job_url)
    if row and _effective_tracker_status(row) == "APPLIED":
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

def _read_job_identities(file_path):
    """Read order-independent job identities from a pipeline-stage CSV."""
    try:
        with open(file_path, "r", encoding="utf-8", newline="") as csv_file:
            reader = csv.DictReader(csv_file)
            fieldnames = reader.fieldnames or []
            columns = {name.strip().casefold(): name for name in fieldnames}
            url_column = columns.get("link") or columns.get("url")
            if not url_column:
                print(
                    f"Cannot verify job identity in {file_path}: missing "
                    "Link/URL column. No application candidates selected."
                )
                return None

            id_column = next(
                (
                    columns[name]
                    for name in ("job id", "jobid", "job_id")
                    if name in columns
                ),
                None,
            )
            identities = Counter()
            for row in reader:
                raw_url = (row.get(url_column) or "").strip()
                normalized_url = _normalize_url(convert_to_job_url(raw_url))
                raw_id = (row.get(id_column) or "").strip() if id_column else ""
                url_id = re.search(r"/jobs/view/(\d+)(?:/|$)", normalized_url)
                if raw_id and url_id and raw_id != url_id.group(1):
                    print(
                        f"Cannot verify job identity in {file_path}: a job ID "
                        "does not match its URL. No application candidates selected."
                    )
                    return None
                job_id = raw_id or (url_id.group(1) if url_id else "")

                if job_id:
                    identities[("job_id", job_id)] += 1
                elif normalized_url:
                    identities[("url", normalized_url)] += 1
                else:
                    print(
                        f"Cannot verify job identity in {file_path}: a row has "
                        "no usable job URL or ID. No application candidates selected."
                    )
                    return None

            if not identities:
                print(
                    f"Cannot verify job identity in {file_path}: no job rows "
                    "were found. No application candidates selected."
                )
                return None
            return identities
    except (OSError, csv.Error, UnicodeError) as exc:
        print(
            f"Could not read job identities from {file_path} ({exc}); "
            "no application candidates selected."
        )
        return None


def _analysis_matches_details():
    """Fail closed unless jobs, details, and analysis are consistent stages."""
    paths = (JOBS_FILE, DETAILS_FILE, ANALYSIS_FILE)
    labels = {
        JOBS_FILE: "Source jobs file",
        DETAILS_FILE: "Details file",
        ANALYSIS_FILE: "Analysis file",
    }
    for file_path in paths:
        if not os.path.exists(file_path):
            print(
                f"{labels[file_path]} not found: {file_path}; "
                "cannot verify source-stage consistency. No application "
                "candidates selected."
            )
            return False

    try:
        jobs_mtime = os.path.getmtime(JOBS_FILE)
        details_mtime = os.path.getmtime(DETAILS_FILE)
        analysis_mtime = os.path.getmtime(ANALYSIS_FILE)
    except OSError as exc:
        print(
            f"Could not verify source-stage timestamps ({exc}); "
            "no application candidates selected."
        )
        return False

    if jobs_mtime > details_mtime:
        print(
            f"{JOBS_FILE} is newer than {DETAILS_FILE}; rerun job_details.py "
            "before selecting application candidates."
        )
        return False

    if details_mtime > analysis_mtime:
        print(
            f"{DETAILS_FILE} is newer than {ANALYSIS_FILE}; "
            "rerun job_analyzer.py before selecting application candidates."
        )
        return False

    jobs_identities = _read_job_identities(JOBS_FILE)
    details_identities = _read_job_identities(DETAILS_FILE)
    analysis_identities = _read_job_identities(ANALYSIS_FILE)
    if any(identities is None for identities in (
        jobs_identities,
        details_identities,
        analysis_identities,
    )):
        return False

    if jobs_identities != details_identities:
        print(
            f"Job identities in {JOBS_FILE} do not match {DETAILS_FILE}; "
            "rerun job_details.py before selecting application candidates."
        )
        return False

    if details_identities != analysis_identities:
        print(
            f"Job identities in {DETAILS_FILE} do not match {ANALYSIS_FILE}; "
            "rerun job_analyzer.py before selecting application candidates."
        )
        return False

    return True


def get_recommended_jobs():
    if not _analysis_matches_details():
        return []

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

        if score < config.MIN_MATCH_SCORE:
            continue

        if not is_allowed_location(location):
            continue

        if status != "NOT APPLIED":
            continue

        if (job.get("Application Eligible") or "").strip().casefold() != "yes":
            continue

        if (job.get("Experience Skip") or "").strip().casefold() == "yes":
            continue

        if (
            "Data Status" in job
            and (job.get("Data Status") or "").strip().upper() != "OK"
        ):
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
            f"{config.MIN_MATCH_SCORE}%"
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


def _target_job_is_closed(page, target_job, expected_id):
    """Detect an unavailable message only inside the verified target job card."""
    target_url = str((target_job or {}).get("Link") or (target_job or {}).get("URL") or "")
    target_match = re.search(r"/jobs/view/(\d+)", target_url, re.IGNORECASE)
    current_match = re.search(r"/jobs/view/(\d+)", str(getattr(page, "url", "")), re.IGNORECASE)
    if (
        not expected_id
        or not target_match
        or not current_match
        or target_match.group(1) != expected_id
        or current_match.group(1) != expected_id
    ):
        return False

    title = _normalize_text(str((target_job or {}).get("Title") or ""))
    company = _normalize_text(str((target_job or {}).get("Company") or ""))
    if not title or not company:
        return False

    try:
        cards = page.locator(
            ".jobs-details__main-content .job-details-jobs-unified-top-card"
        )
        if cards.count() != 1:
            return False
        card = cards.nth(0)
        if not card.is_visible():
            return False

        titles = card.locator("h1.job-details-jobs-unified-top-card__job-title")
        companies = card.locator(".job-details-jobs-unified-top-card__company-name")
        if titles.count() != 1 or companies.count() != 1:
            return False
        title_node = titles.nth(0)
        company_node = companies.nth(0)
        if not title_node.is_visible() or not company_node.is_visible():
            return False
        if (
            title not in _normalize_text(title_node.inner_text())
            or company not in _normalize_text(company_node.inner_text())
        ):
            return False
        return is_job_closed(card.inner_text() or "")
    except Exception:
        return False


def inspect_easy_apply_control(page, target_job) -> dict:
    """Return structured evidence for one target-associated Easy Apply control."""
    target_url = str((target_job or {}).get("Link") or (target_job or {}).get("URL") or "")
    expected_id_match = re.search(r"/jobs/view/(\d+)", target_url, re.IGNORECASE)
    current_id_match = re.search(r"/jobs/view/(\d+)", getattr(page, "url", ""), re.IGNORECASE)
    result = {
        "status": "NONE",
        "reason": "No target-specific Easy Apply control was found.",
        "candidate_count": 0,
        "target_candidate_count": 0,
        "similar_job_candidate_count": 0,
        "ambiguous_candidate_count": 0,
        "duplicate_candidate_count": 0,
        "control_evidence": [],
        "control": None,
    }
    if not expected_id_match or not current_id_match or expected_id_match.group(1) != current_id_match.group(1):
        result.update(status="IDENTITY_MISMATCH", reason="Selected job ID does not match the open LinkedIn page.")
        return result

    title = str((target_job or {}).get("Title") or "").strip()
    company = str((target_job or {}).get("Company") or "").strip()
    if not title or not company:
        result.update(status="IDENTITY_MISMATCH", reason="Selected job title or company is missing.")
        return result

    def is_easy_apply(element):
        try:
            label = " ".join((
                element.inner_text() or "",
                element.get_attribute("aria-label") or "",
                element.get_attribute("title") or "",
                element.get_attribute("href") or "",
                element.get_attribute("class") or "",
            )).casefold()
        except Exception:
            return False
        return any(signal in label for signal in (
            "easy apply", "linkedin apply to", "opensduiapplyflow=true", "jobs-apply-button",
        ))

    try:
        controls = page.locator("button, a, [role='button'], [role='link']")
        for index in range(controls.count()):
            control = controls.nth(index)
            try:
                if not control.is_visible() or not is_easy_apply(control):
                    continue
                result["candidate_count"] += 1
                association = _control_job_association_status(
                    control, title, company, expected_id_match.group(1)
                )
                evidence = {
                    "association": association,
                    "tag": control.evaluate("el => el.tagName.toLowerCase()"),
                    "text": (control.inner_text() or "").strip()[:160],
                    "aria_label": control.get_attribute("aria-label") or "",
                    "href": control.get_attribute("href") or "",
                }
                result["control_evidence"].append(evidence)
                if association == "SIMILAR_JOB":
                    result["similar_job_candidate_count"] += 1
                elif association == "DUPLICATE_CONTROLS":
                    result["duplicate_candidate_count"] += 1
                elif association == "TARGET_ASSOCIATED":
                    result["target_candidate_count"] += 1
                    result["control"] = control
                else:
                    result["ambiguous_candidate_count"] += 1
            except Exception:
                result["ambiguous_candidate_count"] += 1
    except Exception as exc:
        result.update(status="INSPECTION_ERROR", reason=f"Could not inspect page controls: {type(exc).__name__}.")
        result["control"] = None
        return result

    if result["duplicate_candidate_count"] or result["target_candidate_count"] > 1:
        result.update(status="DUPLICATE", reason="Multiple target-associated Easy Apply controls were found.", control=None)
    elif result["ambiguous_candidate_count"]:
        result.update(status="AMBIGUOUS", reason="An Easy Apply candidate could not be associated uniquely with the target job.", control=None)
    elif result["target_candidate_count"] == 1:
        result.update(status="VALIDATED", reason="One target-associated Easy Apply control was found.")
    elif result["similar_job_candidate_count"]:
        result["reason"] = "Only similar-job Easy Apply controls were found; they were rejected."
    return result


def inspect_application_route(page, target_job, *, navigation_succeeded=True, http_status=None) -> dict:
    """Classify current route evidence without navigating or changing page state.

    A detected control means only that a target-associated control was found;
    it does not establish that the employer is accepting applications.
    """
    job = target_job if isinstance(target_job, dict) else {}
    target_url = str(job.get("Link") or job.get("URL") or "")
    target_match = re.search(r"/jobs/view/(\d+)", target_url, re.IGNORECASE)
    expected_id = target_match.group(1) if target_match else ""
    try:
        observed_url = str(page.url or "")
        title = str(page.title() or "")
        body = str(page.locator("body").inner_text() or "")
    except Exception as exc:
        return {
            "selected_job_id": expected_id or None,
            "saved_easy_apply_hint": job.get("Easy Apply"),
            "observed_page_url": str(getattr(page, "url", "") or ""),
            "observed_page_title": "",
            "inspection_outcome": "PAGE_READ_FAILED",
            "classification": "INACCESSIBLE",
            "reason": f"Page metadata or body could not be read ({type(exc).__name__}).",
            "control_type": None,
            "control_evidence": [],
            "validated_external_href": None,
        }

    base = {
        "selected_job_id": expected_id or None,
        "saved_easy_apply_hint": job.get("Easy Apply"),
        "observed_page_url": observed_url,
        "observed_page_title": title,
        "inspection_outcome": "PAGE_INSPECTED",
        "classification": None,
        "reason": "",
        "control_type": None,
        "control_evidence": [],
        "validated_external_href": None,
    }
    current_match = re.search(r"/jobs/view/(\d+)", observed_url, re.IGNORECASE)
    try:
        status_error = http_status is not None and int(http_status) >= 400
    except (TypeError, ValueError):
        status_error = True
    if not navigation_succeeded or status_error:
        base.update(inspection_outcome="NAVIGATION_FAILED", classification="INACCESSIBLE", reason="The LinkedIn job page could not be loaded successfully.")
        return base
    if not current_match or not expected_id:
        base.update(inspection_outcome="TARGET_ID_UNVERIFIED", classification="INACCESSIBLE", reason="The observed page URL does not establish the selected LinkedIn job.")
        return base
    if current_match.group(1) != expected_id:
        base.update(inspection_outcome="JOB_ID_MISMATCH", classification="AMBIGUOUS", reason="The open LinkedIn job ID differs from the selected job ID.")
        return base
    if not title or not body.strip():
        base.update(inspection_outcome="PAGE_CONTENT_UNAVAILABLE", classification="INACCESSIBLE", reason="The page title or visible body content is unavailable.")
        return base
    page_title = " ".join(title.casefold().split())
    normalized_title = " ".join(str(job.get("Title") or "").casefold().split())
    normalized_company = " ".join(str(job.get("Company") or "").casefold().split())
    title_establishes_target = bool(
        normalized_title and normalized_company
        and normalized_title in page_title
        and normalized_company in page_title
    )
    try:
        password_count = page.locator('input[type="password"]').count()
    except Exception:
        password_count = 0
    if (
        any(token in page_title for token in ("sign in", "log in", "join linkedin"))
        or re.search(r"/login(?:/|$)|/authwall", observed_url, re.IGNORECASE)
        or password_count > 0
    ):
        base.update(inspection_outcome="AUTHENTICATION_OR_INTERSTITIAL", classification="INACCESSIBLE", reason="The page is an authentication or interstitial screen, not an inspectable job page.")
        return base
    if not title_establishes_target:
        base.update(inspection_outcome="TARGET_PAGE_UNVERIFIED", classification="INACCESSIBLE", reason="The page title does not establish the selected job and company.")
        return base

    easy = inspect_easy_apply_control(page, job)
    external = inspect_external_apply_link(page, job)
    easy_valid = easy["status"] == "VALIDATED"
    external_valid = external["status"] == "VALIDATED"
    target_unavailable = _target_job_is_closed(page, job, expected_id)
    inspection_failed = easy["status"] == "INSPECTION_ERROR" or external["status"] == "INSPECTION_ERROR"
    problematic = easy["status"] in {"DUPLICATE", "AMBIGUOUS", "IDENTITY_MISMATCH"} or external["status"] in {"DUPLICATE", "AMBIGUOUS", "IDENTITY_MISMATCH", "INVALID_URL"}
    any_target_route = easy_valid or external_valid
    if inspection_failed:
        base.update(inspection_outcome="CONTROL_INSPECTION_FAILED", classification="INACCESSIBLE", reason="The page could not be inspected reliably.")
    elif (easy_valid and external_valid) or (target_unavailable and (any_target_route or problematic)) or problematic:
        base.update(classification="AMBIGUOUS", reason="Route evidence conflicts, contains duplicates/invalid data, or cannot be associated uniquely with the target job.")
    elif target_unavailable:
        base.update(classification="EXPLICITLY_UNAVAILABLE", reason="The target page contains an explicit no-longer-accepting/unavailable message.")
    elif easy_valid:
        base.update(classification="LINKEDIN_EASY_APPLY_CONTROL_DETECTED", reason=easy["reason"], control_type="LINKEDIN_EASY_APPLY", control_evidence=easy["control_evidence"])
    elif external_valid:
        base.update(classification="EXTERNAL_APPLY_CONTROL_DETECTED_VALIDATED", reason=external["reason"], control_type="EXTERNAL_APPLY", control_evidence=external["candidates"], validated_external_href=external["validated_href"])
    else:
        base.update(classification="NO_TARGET_APPLICATION_CONTROL", reason="The target page was inspectable, but neither detector found a target-specific application control.")
    base["easy_apply_inspection"] = {key: value for key, value in easy.items() if key != "control"}
    base["external_apply_inspection"] = external
    return base


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
    if not EXECUTION_POLICY.allows_diagnostic_artifacts():
        print("DRY_RUN: diagnostic screenshot write skipped.")
        return False

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

def _write_tracker_application_status(job, status):
    if not os.path.exists(TRACKER_FILE):
        print(f"Tracker file not found: {TRACKER_FILE}")
        return False

    with open(TRACKER_FILE, "r", encoding="utf-8", newline="") as f:
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

    if job_url:
        for row in rows:
            row_url = _normalize_url(row.get("URL") or row.get("Link") or "")
            if row_url == job_url:
                row["Status"] = status
                if "Application Status" in fieldnames:
                    row["Application Status"] = status
                if status == "APPLIED" and "Applied Date" in fieldnames:
                    row["Applied Date"] = datetime.now().strftime("%Y-%m-%d")
                updated = True
                break

    if not updated:
        row = _unique_title_company_match(rows, title, company, job_url)
        if row:
            row["Status"] = status
            if "Application Status" in fieldnames:
                row["Application Status"] = status
            if status == "APPLIED" and "Applied Date" in fieldnames:
                row["Applied Date"] = datetime.now().strftime("%Y-%m-%d")
            updated = True

    if not updated:
        new_row = {field: "" for field in fieldnames}
        new_row["Title"] = job.get("Title", "")
        new_row["Company"] = job.get("Company", "")
        new_row["Location"] = job.get("Location", "")
        new_row["Status"] = status
        if "Application Status" in fieldnames:
            new_row["Application Status"] = status
        job_link = job.get("URL", "") or job.get("Link", "")
        for link_field in ("URL", "Link"):
            if link_field in fieldnames:
                new_row[link_field] = job_link
        if status == "APPLIED" and "Applied Date" in fieldnames:
            new_row["Applied Date"] = datetime.now().strftime("%Y-%m-%d")
        rows.append(new_row)

    _atomic_write_csv(TRACKER_FILE, fieldnames, rows)

    print(f"Application tracker updated: {status}")
    return True


def record_application_status(job, status, submission_confirmed=False):
    """
    Persist an application result to the tracker and, for confirmed APPLIED,
    independently to history. Either sink is useful for later daily counting.
    """
    if not EXECUTION_POLICY.allows_persistence():
        print("DRY_RUN: application tracker/history write skipped.")
        return False

    status = str(status or "").strip().upper()
    if status in {"APPLIED", "SUBMITTED"} and not submission_confirmed:
        print("Application status write blocked: submission is not confirmed.")
        return False
    if status == "SUBMITTED":
        status = "APPLIED"

    try:
        tracker_updated = _write_tracker_application_status(job, status)
    except Exception as exc:
        print(f"Could not update application tracker: {exc}")
        tracker_updated = False

    if status != "APPLIED":
        return tracker_updated

    try:
        history_updated = _record_application_history(
            job,
            "APPLIED",
            submission_confirmed=True,
        )
    except Exception as exc:
        print(f"Could not update application history: {exc}")
        history_updated = False

    if not history_updated:
        print("Warning: application history update failed.")
    if not tracker_updated:
        print("Warning: application tracker update failed.")

    # These booleans describe persistence only. The confirmed submission is
    # still countable by the active run even when both sinks fail; a later
    # process cannot recover it unless at least one existing sink persisted it.
    return tracker_updated or history_updated


# ---------------------------------------
# Open Easy Apply
# ---------------------------------------

def open_easy_apply(job):
    if not EXECUTION_POLICY.allows_browser_actions():
        print("DRY_RUN: browser execution intentionally skipped for selected job.")
        return EXECUTION_POLICY.dry_run_result(job)

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

    job_id_for_approval = job.get("Job ID") or job.get("JobID") or ""
    if job_id_for_approval:
        application_identity = f"linkedin-job:{str(job_id_for_approval).strip()}"
    else:
        link_fingerprint = hashlib.sha256(link.strip().encode("utf-8")).hexdigest()
        application_identity = f"linkedin-link-sha256:{link_fingerprint}"
    application_title = str(job.get("Title") or "").strip()
    application_company = str(job.get("Company") or "").strip()

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
                    config.CHROME_CDP_URL
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
            record_application_status(
                job,
                "APPLIED",
                submission_confirmed=True,
            )
            # The live site has confirmed an existing submission, and the
            # recorder dates this newly discovered confirmation today. Count
            # it in this run so another job cannot consume the same daily slot.
            return True

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

                external_link = find_external_apply_link(page, job)

                if external_link:
                    if not is_safe_external_application_url(external_link):
                        print("External application URL is not a valid HTTP(S) destination; stopping for manual review.")
                        record_application_status(job, "READY_FOR_REVIEW")
                        return False

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

                    if not is_safe_external_application_redirect(external_link, page.url or ""):
                        print("External application redirected to an unvalidated destination; stopping for manual review.")
                        record_application_status(job, "READY_FOR_REVIEW")
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

                    if result == "SUBMITTED":
                        persistence_success = record_application_status(
                            job,
                            "APPLIED",
                            submission_confirmed=True,
                        )
                        if persistence_success:
                            print("Confirmed external submission was persisted.")
                            return True
                        print("External submission was confirmed, but application tracking failed.")
                        # Submission confirmation is the countable event. Do
                        # not let a later tracker/history write failure cause
                        # the active runner to attempt another application.
                        return True

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

                    if result == "FORM_NOT_FOUND":
                        print()
                        print("No recognizable external application form was reached.")
                        print("No external submission was performed.")
                        record_application_status(job, "FORM_NOT_FOUND")
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

        job_id = job.get("Job ID") or job.get("JobID") or ""
        if not job_id:
            job_id_match = re.search(r"/jobs/view/(\d+)", link)
            job_id = job_id_match.group(1) if job_id_match else ""

        control_diagnostic = element_diagnostic(easy_apply)
        control_diagnostic["text_or_label"] = (
            control_diagnostic.get("text_preview")
            or control_diagnostic.get("aria_label")
            or control_diagnostic.get("title")
        )
        write_diagnostic({
            "event": "easy_apply_control_before_click",
            "job_id": str(job_id),
            "page": page_diagnostic(page),
            "control": control_diagnostic,
        })

        try:

            easy_apply.scroll_into_view_if_needed()

            page.wait_for_timeout(
                500
            )

            click_started = time.perf_counter()
            easy_apply.click(
                timeout=10000
            )
            click_method = "locator_click"

        except Exception as e:

            if "click_started" not in locals():
                click_started = time.perf_counter()

            write_diagnostic({
                "event": "easy_apply_click_attempt",
                "job_id": str(job_id),
                "click_result": "locator_click_exception",
                "exception_type": type(e).__name__,
                "exception_message": str(e)[:500],
                "page": page_diagnostic(page, include_page_count=True),
                "control": control_diagnostic,
            })

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
                click_method = "javascript_click"

            except Exception as js_error:

                write_diagnostic({
                    "event": "easy_apply_click_result",
                    "job_id": str(job_id),
                    "click_result": "failed",
                    "click_method": "javascript_click",
                    "exception_type": type(js_error).__name__,
                    "exception_message": str(js_error)[:500],
                    "elapsed_seconds": round(
                        time.perf_counter() - click_started, 3
                    ),
                    "page": page_diagnostic(page, include_page_count=True),
                    "control": control_diagnostic,
                })

                print(
                    "JavaScript click failed:"
                )

                print(
                    js_error
                )

                return False

        write_diagnostic({
            "event": "easy_apply_click_result",
            "job_id": str(job_id),
            "click_result": "success",
            "click_method": click_method,
            "elapsed_seconds": round(
                time.perf_counter() - click_started, 3
            ),
            "page": page_diagnostic(page, include_page_count=True),
            "control": control_diagnostic,
        })

        # ---------------------------------------
        # Resolve the actual Easy Apply UI
        # ---------------------------------------
        original_page = page
        page.wait_for_timeout(3000)

        modal_selectors = EASY_APPLY_MODAL_SELECTORS

        modal_probe = []
        diagnostic_pages = _eligible_easy_apply_pages(
            original_page,
            context.pages,
        )

        for candidate_page in diagnostic_pages:
            modal_probe.append({
                "page": page_diagnostic(
                    candidate_page,
                    include_page_count=True,
                ),
                "selectors": selector_diagnostics(
                    candidate_page,
                    modal_selectors,
                ),
            })

        sdui_diagnostics_logged = set()

        def has_application_ui(candidate_page):
            detection = _detect_easy_apply_container(candidate_page)
            sdui = detection["sdui_diagnostics"]
            page_key = id(candidate_page)
            if detection["source"] == "sdui" and page_key not in sdui_diagnostics_logged:
                sdui_diagnostics_logged.add(page_key)
                write_diagnostic({
                    "event": "easy_apply_sdui_container_detected",
                    "job_id": str(job_id),
                    "page": page_diagnostic(
                        candidate_page,
                        include_page_count=True,
                    ),
                    "selector": sdui["selector"],
                    "match_count": sdui["match_count"],
                    "visible_match_count": sdui["visible_match_count"],
                    "candidates": sdui["candidates"],
                })
            return detection["detected"]

        application_ui_found = False
        if has_application_ui(original_page):
            page = original_page
            application_ui_found = True
            print("Easy Apply modal detected on the original LinkedIn job page.")
        else:
            # Check actual popups/new tabs only. Never switch to an arbitrary
            # LinkedIn page such as a company-home tab.
            for candidate_page in diagnostic_pages[1:]:
                if has_application_ui(candidate_page):
                    page = candidate_page
                    application_ui_found = True
                    print("Easy Apply modal detected on an additional LinkedIn page.")
                    break

        if not application_ui_found:
            # Keep the current immediate checks as a fast path. If they miss a
            # delayed SDUI/modal render, reuse the form processor's bounded,
            # signal-validated detector on only the clicked page and eligible
            # LinkedIn popup pages.
            validated_page, validated_container = _find_validated_application_container(
                diagnostic_pages,
                wait_seconds=12,
            )
            if validated_container is not None:
                page = validated_page
                application_ui_found = True
                print("Easy Apply container detected by the bounded application-form check.")
                # Emit SDUI diagnostics if the exact visible SDUI root was the
                # signal that became available during the bounded wait.
                has_application_ui(page)

        if not application_ui_found:
            print()
            print("EASY APPLY MODAL NOT DETECTED")
            print(f"Current page URL after click: {page.url}")
            print("The automation will NOT process this page.")
            print("No form navigation or submission will be performed.")
            write_diagnostic({
                "event": "easy_apply_modal_detection",
                "detected": False,
                "job_id": str(job_id),
                "page": page_diagnostic(page, include_page_count=True),
                "elapsed_seconds": round(
                    time.perf_counter() - click_started, 3
                ),
                "candidate_pages": modal_probe,
            })
            save_diagnostic_screenshot(original_page)
            return False

        write_diagnostic({
            "event": "easy_apply_modal_detection",
            "detected": True,
            "job_id": str(job_id),
            "page": page_diagnostic(page, include_page_count=True),
            "elapsed_seconds": round(
                time.perf_counter() - click_started, 3
            ),
            "candidate_pages": modal_probe,
        })

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
                page,
                application_identity=application_identity,
                title=application_title,
                company=application_company,
            )

            if application_result == "SUBMITTED":
                persistence_success = record_application_status(
                    job,
                    "APPLIED",
                    submission_confirmed=True,
                )

                if persistence_success:
                    print(
                        "\nConfirmed submission was persisted."
                    )
                    return True

                print(
                    "\nSubmission was reported, but application tracking failed."
                )
                # The submission itself is confirmed even though persistence
                # failed. Return success so main() consumes the daily slot.
                return True

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

    if EXECUTION_POLICY.dry_run:
        results = [EXECUTION_POLICY.dry_run_result(job) for job in jobs]
        print(f"DRY_RUN: selected jobs: {len(jobs)}")
        for result in results:
            route = result["route_hint"] or "No saved routing hint"
            print(
                "DRY_RUN_SKIPPED_BROWSER: "
                f"{result['job_title']} | {result['company']} | "
                f"score={result['match_score']} | route hint={route}"
            )
        return results

    try:
        today_applied = get_today_applied_count()
    except DailyApplicationCountUnavailable as exc:
        print(f"Daily application count unavailable; stopping safely: {exc}")
        return
    daily_limit = config.DAILY_APPLICATION_LIMIT
    daily_remaining = daily_limit - today_applied

    print()
    print(
        f"Eligible jobs: {len(jobs)}"
    )
    print(
        f"Applications already submitted today: "
        f"{today_applied}/{daily_limit}"
    )

    if daily_remaining <= 0:
        print()
        print("=" * 70)
        print("DAILY APPLICATION LIMIT REACHED")
        print("=" * 70)
        print(
            f"Confirmed applications today: "
            f"{today_applied}/{daily_limit}"
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
                f"{today_applied + applications_this_run}/{daily_limit}"
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
