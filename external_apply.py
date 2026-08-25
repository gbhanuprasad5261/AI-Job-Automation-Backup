"""
External ATS discovery and safe form preparation.

This module handles the first layer for company career-page applications:
- detects common ATS providers from an apply URL;
- opens the external application page;
- fills obvious contact fields and resume upload;
- never guesses required screening questions;
- never submits unless an explicit, verified submit confirmation is available.

Use this as a separate path from the proven LinkedIn Easy Apply flow.
"""

import re
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright


ATS_DOMAINS = {
    "greenhouse.io": "GREENHOUSE",
    "boards.greenhouse.io": "GREENHOUSE",
    "lever.co": "LEVER",
    "jobs.lever.co": "LEVER",
    "myworkdayjobs.com": "WORKDAY",
    "workday.com": "WORKDAY",
    "ashbyhq.com": "ASHBY",
    "smartrecruiters.com": "SMARTRECRUITERS",
}

def detect_ats(url):
    host = urlparse(url).netloc.lower()
    for domain, name in ATS_DOMAINS.items():
        if host == domain or host.endswith("." + domain):
            return name
    return "UNKNOWN"

def find_external_apply_link(page):
    """Return the strongest visible external application link."""
    selectors = [
        'a[href*="greenhouse"]',
        'a[href*="lever.co"]',
        'a[href*="myworkdayjobs"]',
        'a[href*="ashbyhq"]',
        'a[href*="smartrecruiters"]',
    ]

    for selector in selectors:
        links = page.locator(selector)
        for i in range(links.count()):
            link = links.nth(i)
            if not link.is_visible():
                continue
            href = link.get_attribute("href") or ""
            if href.startswith("http"):
                return href

    # Generic apply links, only when their URL is external to LinkedIn.
    links = page.locator("a[href]")
    for i in range(links.count()):
        link = links.nth(i)
        if not link.is_visible():
            continue
        text = (link.inner_text() or "").strip().lower()
        href = link.get_attribute("href") or ""
        if "apply" in text and "linkedin.com" not in href.lower():
            return href

    return ""

def _fill_first(page, selectors, value):
    if not value:
        return False
    for selector in selectors:
        fields = page.locator(selector)
        for i in range(fields.count()):
            field = fields.nth(i)
            try:
                if field.is_visible() and not (field.input_value() or "").strip():
                    field.fill(value)
                    return True
            except Exception:
                continue
    return False

def prepare_external_form(page, resume_path, name, email, phone):
    _fill_first(page, ['input[type="email"]', 'input[name*="email" i]'], email)
    _fill_first(page, ['input[type="tel"]', 'input[name*="phone" i]', 'input[name*="mobile" i]'], phone)
    _fill_first(page, ['input[name*="name" i]', 'input[id*="name" i]'], name)

    path = Path(resume_path)
    if path.exists():
        inputs = page.locator('input[type="file"]')
        for i in range(inputs.count()):
            try:
                inputs.nth(i).set_input_files(str(path))
                break
            except Exception:
                continue

def external_apply(url, resume_path, name, email, phone):
    ats = detect_ats(url)
    print(f"External ATS detected: {ats}")
    print(f"Opening: {url}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2500)

        prepare_external_form(page, resume_path, name, email, phone)

        required = page.locator(
            'input[required], textarea[required], select[required], [aria-required="true"]'
        )
        empty = 0
        for i in range(required.count()):
            field = required.nth(i)
            try:
                if field.is_visible():
                    value = field.input_value() if field.evaluate("(e)=>['INPUT','TEXTAREA','SELECT'].includes(e.tagName)") else field.inner_text()
                    if not str(value or "").strip():
                        empty += 1
            except Exception:
                continue

        print(f"Required fields still empty: {empty}")
        print("External ATS application prepared for manual review.")
        print("No external submission was performed.")
        return "READY_FOR_REVIEW"
