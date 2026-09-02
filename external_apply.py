"""External ATS application helpers.

The module prepares external applications for review. It deliberately does
not submit external applications automatically because ATS forms vary and
unknown questions must never be guessed.
"""

import os
import re
from urllib.parse import parse_qs, unquote, urlparse

from playwright.sync_api import Page

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

CURRENT_LOCATION = os.getenv("CURRENT_LOCATION", "Bengaluru")
CURRENT_COMPANY = os.getenv("CURRENT_COMPANY", "N/A")
GITHUB_URL = os.getenv("GITHUB_URL", "https://github.com/gbhanuprasad5261")


def _text(page):
    try:
        return page.locator("body").inner_text().strip()
    except Exception:
        return ""


def _attr(element, name):
    try:
        return element.get_attribute(name) or ""
    except Exception:
        return ""


def _visible(element):
    try:
        return element.is_visible()
    except Exception:
        return False


def unwrap_linkedin_external_url(url: str) -> str:
    """Extract the real destination from LinkedIn /safety/go/?url=... redirects."""
    if not url:
        return ""

    current = url
    for _ in range(3):
        parsed = urlparse(current)
        query = parse_qs(parsed.query)
        candidates = query.get("url", []) + query.get("target", [])
        if not candidates:
            break
        candidate = unquote(candidates[0]).strip()
        if not candidate or candidate == current:
            break
        current = candidate

    return current


def detect_ats(url: str, body: str = "") -> str:
    value = f"{url} {body}".lower()
    if "greenhouse.io" in value or "boards.greenhouse" in value:
        return "GREENHOUSE"
    if "lever.co" in value:
        return "LEVER"
    if "myworkdayjobs.com" in value or "workday.com" in value:
        return "WORKDAY"
    if "ashbyhq.com" in value:
        return "ASHBY"
    if "smartrecruiters.com" in value:
        return "SMARTRECRUITERS"
    if "cutshort.io" in value:
        return "CUTSHORT"
    return "UNKNOWN"


def find_external_apply_link(page: Page) -> str:
    """Find an external application destination without guessing among unrelated links."""
    # Prefer explicit hrefs attached to application controls.
    selectors = [
        "a[href]",
        "button",
        "[role='button']",
        "[role='link']",
    ]
    for selector in selectors:
        try:
            elements = page.locator(selector)
            for i in range(elements.count()):
                element = elements.nth(i)
                if not _visible(element):
                    continue
                text = (_attr(element, "aria-label") + " " + _attr(element, "title") + " " + (element.inner_text() or "")).lower()
                href = _attr(element, "href")
                if any(s in text for s in (
                    "apply on company website",
                    "apply on the company website",
                    "apply externally",
                )) and href:
                    return unwrap_linkedin_external_url(href)
        except Exception:
            continue

    # Inspect all hrefs for known ATS domains. This is safe because the domain
    # itself identifies the application destination.
    try:
        links = page.locator("a[href]")
        for i in range(links.count()):
            link = links.nth(i)
            href = unwrap_linkedin_external_url(_attr(link, "href"))
            if any(domain in href.lower() for domain in (
                "greenhouse.io", "lever.co", "myworkdayjobs.com",
                "ashbyhq.com", "smartrecruiters.com", "cutshort.io",
            )):
                return href
    except Exception:
        pass

    return ""


def check_external_eligibility(page: Page) -> str:
    """Return INELIGIBLE only for an explicit numeric minimum above candidate experience."""
    body = _text(page)
    lower = body.lower()

    # Do not interpret generic words such as 'experience' as a requirement.
    patterns = [
        r"(?:minimum|required|at least|minimum of)\D{0,60}(\d+)\+?\s*years?",
        r"(\d+)\+?\s*years?\s*(?:of\s*)?(?:professional\s*)?experience\s*(?:required|minimum|needed)",
    ]
    years = []
    for pattern in patterns:
        for match in re.finditer(pattern, lower):
            try:
                years.append(int(match.group(1)))
            except ValueError:
                pass

    candidate_years = 0
    if any(year > candidate_years for year in years):
        required = max(years)
        print(f"External requirement : {required}+ years")
        return "INELIGIBLE"

    print("External requirement  : Not specified")
    print("No explicit minimum experience requirement detected.")
    return "UNKNOWN"


def _fill(locator, value) -> bool:
    if not value:
        return False
    try:
        for i in range(locator.count()):
            element = locator.nth(i)
            if not _visible(element):
                continue
            current = ""
            try:
                current = element.input_value().strip()
            except Exception:
                pass
            if current:
                return True
            element.fill(value)
            return True
    except Exception:
        pass
    return False


def _field_text(element) -> str:
    """Return field metadata plus associated label text for ATS forms."""
    parts = [
        _attr(element, "placeholder"),
        _attr(element, "aria-label"),
        _attr(element, "name"),
        _attr(element, "id"),
    ]

    # Lever commonly renders the visible field name in a separate <label>.
    # Include associated labels so fields such as Current location/company are
    # identified even when the input has no useful placeholder/name.
    try:
        label_text = element.evaluate(
            """el => {
                const labels = el.labels ? Array.from(el.labels) : [];
                if (labels.length) return labels.map(x => x.innerText || x.textContent || '').join(' ');
                const parent = el.closest('label');
                return parent ? (parent.innerText || parent.textContent || '') : '';
            }"""
        ) or ""
        parts.append(label_text)
    except Exception:
        pass

    return " ".join(str(x) for x in parts if x).lower()


def _fill_known_fields(
    page: Page,
    name: str,
    email: str,
    phone: str,
    current_location: str = CURRENT_LOCATION,
    current_company: str = CURRENT_COMPANY,
) -> int:
    count = 0
    fields = page.locator("input, textarea")
    for i in range(fields.count()):
        element = fields.nth(i)
        if not _visible(element):
            continue
        field_type = _attr(element, "type").lower()
        if field_type in {"hidden", "file", "radio", "checkbox", "submit", "button", "password"}:
            continue
        current = ""
        try:
            current = element.input_value().strip()
        except Exception:
            pass
        q = _field_text(element)

        # "Current company" must reflect present employment status, not a
        # past internship/training entry from the resume or browser autofill.
        # For this candidate the intended answer is N/A, so overwrite any
        # prefilled value such as QSpiders.
        if "current company" in q or ("company" in q and "current" in q):
            value = current_company or "N/A"
            try:
                element.fill(value)
                count += 1
            except Exception:
                pass
            continue

        # Lever's Current location is a Google/Lever autocomplete field.
        # The browser must select an autocomplete suggestion; simply setting
        # input.value is not sufficient because Lever validates the selected
        # location state, not just the visible text.
        if "current location" in q or ("location" in q and "current" in q):
            value = current_location or "Bengaluru"
            try:
                element.scroll_into_view_if_needed()
            except Exception:
                pass

            selected = False

            try:
                element.click()
                element.press("Control+A")
                element.fill(value)

                # Give the autocomplete provider time to render suggestions.
                page.wait_for_timeout(1200)

                # Google Places autocomplete, used by many Lever forms.
                suggestion_selectors = [
                    ".pac-container .pac-item:visible",
                    ".pac-container .pac-item",
                    "[role='listbox'] [role='option']:visible",
                    "[role='option']:visible",
                    "ul[role='listbox'] li:visible",
                ]

                wanted_terms = [
                    value.lower(),
                    "bengaluru",
                    "bangalore",
                    "karnataka",
                    "india",
                ]

                for selector in suggestion_selectors:
                    options = page.locator(selector)
                    try:
                        total = options.count()
                    except Exception:
                        total = 0

                    if total == 0:
                        continue

                    # Prefer a suggestion containing Bengaluru/Bangalore.
                    chosen = None
                    for j in range(min(total, 20)):
                        option = options.nth(j)
                        try:
                            if not _visible(option):
                                continue
                            txt = (option.inner_text() or "").strip()
                            low = txt.lower()
                            if (
                                "bengaluru" in low
                                or "bangalore" in low
                                or value.lower() in low
                            ):
                                chosen = option
                                break
                        except Exception:
                            continue

                    if chosen is None:
                        chosen = options.first

                    try:
                        chosen.scroll_into_view_if_needed()
                    except Exception:
                        pass

                    try:
                        chosen.click()
                        page.wait_for_timeout(500)
                        selected = True
                        break
                    except Exception:
                        pass

                # Keyboard fallback for Google/Lever autocomplete.
                if not selected:
                    try:
                        element.press("ArrowDown")
                        page.wait_for_timeout(200)
                        element.press("Enter")
                        page.wait_for_timeout(500)
                        selected = True
                    except Exception:
                        pass

            except Exception:
                pass

            # Final normal fill fallback. This is only used if the widget did
            # not expose a selectable suggestion.
            try:
                actual = element.input_value().strip()
            except Exception:
                actual = ""

            if not actual:
                try:
                    element.fill(value)
                    element.press("Tab")
                    page.wait_for_timeout(300)
                except Exception:
                    pass

            # Verify both the native input and the visible field container.
            try:
                final_value = element.input_value().strip()
            except Exception:
                final_value = ""

            if final_value:
                count += 1
            else:
                try:
                    field_text = element.evaluate(
                        """el => {
                            const row = el.closest('div.field, div, li, label');
                            return row ? (row.innerText || row.textContent || '') : '';
                        }"""
                    ) or ""
                except Exception:
                    field_text = ""

                low = field_text.lower()
                if (
                    "bengaluru" in low
                    or "bangalore" in low
                    or value.lower() in low
                ):
                    count += 1

            continue

        if current:
            continue

        value = None
        if "email" in q:
            value = email
        elif "phone" in q or "mobile" in q or "telephone" in q:
            value = phone
        elif "first name" in q or "firstname" in q:
            value = name.split()[0] if name else ""
        elif "last name" in q or "lastname" in q or "surname" in q:
            value = " ".join(name.split()[1:]) if len(name.split()) > 1 else ""
        elif "current location" in q or "location" in q and "current" in q:
            value = current_location
        elif "current company" in q or "company" in q and "current" in q:
            value = current_company
        elif re.search(r"(^|\s)name(\s|$)", q) or "full name" in q:
            value = name
        if value and _fill(fields.nth(i), value):
            count += 1
    return count


def _fill_known_profile_links(page: Page, github_url: str = GITHUB_URL) -> int:
    """Fill the GitHub URL field on ATS forms and verify the value actually stuck."""
    if not github_url:
        return 0

    # Lever normally gives the label a `for` attribute pointing directly to
    # the real input. This is more reliable than guessing from sibling nodes.
    try:
        labels = page.locator("label")
        for i in range(labels.count()):
            label = labels.nth(i)
            if not _visible(label):
                continue

            try:
                label_text = (label.inner_text() or "").strip().lower()
            except Exception:
                label_text = ""

            if "github" not in label_text:
                continue

            target = None

            try:
                for_id = (label.get_attribute("for") or "").strip()
                if for_id:
                    target = page.locator(
                        f"#{for_id.replace(':', r'\\:')}"
                    ).first
                    if not target.count() or not _visible(target):
                        target = None
            except Exception:
                target = None

            # Fallback: the input is usually inside the same form row.
            if target is None:
                try:
                    row = label.locator("xpath=..")
                    candidates = row.locator("input, textarea")
                    for j in range(candidates.count()):
                        candidate = candidates.nth(j)
                        if _visible(candidate):
                            target = candidate
                            break
                except Exception:
                    pass

            # Final fallback: nearest following visible text input.
            if target is None:
                try:
                    candidate = label.locator(
                        "xpath=following::input[not(@type='hidden') and "
                        "not(@type='file')][1]"
                    )
                    if candidate.count() and _visible(candidate.first):
                        target = candidate.first
                except Exception:
                    pass

            if target is None:
                continue

            try:
                current = target.input_value().strip()
            except Exception:
                current = ""

            if current == github_url:
                print(f"Known profile link already filled: GitHub -> {github_url}")
                return 0

            try:
                target.scroll_into_view_if_needed()
            except Exception:
                pass

            try:
                target.fill(github_url)
            except Exception:
                try:
                    target.click()
                    target.press("Control+A")
                    target.type(github_url)
                except Exception:
                    continue

            # Trigger the same events used by normal browser typing and then
            # verify the actual DOM value.
            try:
                target.evaluate(
                    """(el, value) => {
                        el.value = value;
                        el.dispatchEvent(new Event('input', {bubbles:true}));
                        el.dispatchEvent(new Event('change', {bubbles:true}));
                        el.dispatchEvent(new Event('blur', {bubbles:true}));
                    }""",
                    github_url,
                )
            except Exception:
                pass

            try:
                page.wait_for_timeout(300)
            except Exception:
                pass

            try:
                verified = target.input_value().strip()
            except Exception:
                verified = ""

            if verified == github_url:
                print(f"Known profile link filled: GitHub -> {github_url}")
                return 1

            print(
                "GitHub field was located but value could not be verified "
                f"(current value: {verified!r})."
            )
            return 0

    except Exception:
        pass

    return 0

def _upload_resume(page: Page, resume_path: str) -> bool:
    if not resume_path or not os.path.exists(resume_path):
        return False
    try:
        inputs = page.locator("input[type='file']")
        for i in range(inputs.count()):
            try:
                inputs.nth(i).set_input_files(resume_path)
                return True
            except Exception:
                continue
    except Exception:
        pass
    return False


def _select_known_dropdowns(page: Page) -> int:
    """Select known safe dropdown values without guessing unknown questions."""
    count = 0
    selects = page.locator("select")

    try:
        for i in range(selects.count()):
            element = selects.nth(i)
            if not _visible(element):
                continue

            q = _field_text(element)

            # Brillio/Lever demographic survey: the required dropdown is
            # explicitly "What is your location?" and its country options
            # include India. This is a known candidate-profile value.
            if "what is your location" in q:
                try:
                    current = element.input_value().strip()
                except Exception:
                    current = ""

                if current and current.lower() not in {"select", "select..."}:
                    continue

                try:
                    element.select_option(label="India")
                    print("Selected known dropdown: What is your location? -> India")
                    count += 1
                    continue
                except Exception as e:
                    print(f"Could not select India for location dropdown: {e}")

    except Exception:
        pass

    return count


def _required_empty_count(page: Page) -> int:
    """Count visible empty required user-entry fields.

    File inputs are excluded because an uploaded file is not represented by
    input_value() in the same way as text fields. Resume upload is checked
    separately by _upload_resume().
    """
    count = 0
    try:
        required = page.locator(
            "input[required], textarea[required], select[required], "
            "[aria-required='true']"
        )

        for i in range(required.count()):
            element = required.nth(i)
            if not _visible(element):
                continue

            try:
                tag = element.evaluate("e => e.tagName")
            except Exception:
                tag = "UNKNOWN"

            field_type = _attr(element, "type").lower()
            if tag == "INPUT" and field_type == "file":
                continue

            try:
                if tag in {"INPUT", "TEXTAREA", "SELECT"}:
                    value = element.input_value().strip()
                else:
                    value = element.inner_text().strip()
            except Exception:
                value = ""

            # Some autocomplete widgets expose their selected display value
            # through attributes while input_value() is temporarily empty.
            if not value:
                try:
                    value = (element.get_attribute("aria-label") or "").strip()
                except Exception:
                    pass

            if not value:
                # Lever can keep the selected location in an associated
                # autocomplete/hidden state while the text input itself has
                # no native value. Inspect nearby DOM text before declaring it
                # empty.
                field_meta = _field_text(element)
                if "current location" in field_meta:
                    try:
                        nearby = element.evaluate(
                            """el => {
                                const row = el.closest('div.field, div, li, label');
                                return row ? (row.innerText || row.textContent || '') : '';
                            }"""
                        ) or ""
                    except Exception:
                        nearby = ""

                    nearby_lower = nearby.strip().lower()
                    if (
                        "bengaluru" in nearby_lower
                        or "bangalore" in nearby_lower
                        or "karnataka" in nearby_lower
                        or "bengaluru, ind" in nearby_lower
                    ):
                        continue

                count += 1

                try:
                    label = _field_text(element).strip()
                except Exception:
                    label = ""

                print("Required field still empty:")
                print(f"  Label       : {label or '(not detected)'}")
                print(f"  Tag         : {tag}")
                print(f"  Name        : {_attr(element, 'name') or '(none)'}")
                print(f"  ID          : {_attr(element, 'id') or '(none)'}")
                print(
                    f"  Placeholder : "
                    f"{_attr(element, 'placeholder') or '(none)'}"
                )

    except Exception:
        pass

    return count

def prepare_external_application_page(
    page: Page,
    resume_path: str = "",
    name: str = "",
    email: str = "",
    phone: str = "",
    current_location: str = CURRENT_LOCATION,
    current_company: str = CURRENT_COMPANY,
):
    """Fill only known external fields and stop for manual review.

    Unknown fields are deliberately untouched. External ATS submission is not
    performed here.
    """
    body = _text(page)
    ats = detect_ats(page.url, body)
    print(f"External ATS detected: {ats}")
    print(f"External page: {page.url}")
    print("Preparing external application page...")

    filled = _fill_known_fields(
        page,
        name,
        email,
        phone,
        current_location,
        current_company,
    )
    print(f"Known contact fields filled: {filled}")

    uploaded = _upload_resume(page, resume_path)
    print(f"Resume uploaded: {'Yes' if uploaded else 'No / not required yet'}")

    profile_links_filled = _fill_known_profile_links(page)
    if profile_links_filled:
        print(f"Known profile links filled: {profile_links_filled}")

    dropdowns_filled = _select_known_dropdowns(page)
    if dropdowns_filled:
        print(f"Known dropdowns filled: {dropdowns_filled}")

    required = _required_empty_count(page)
    print(f"Visible required fields still empty: {required}")
    if required:
        print("Required fields remain empty; manual review is required.")
    else:
        print("No visible required fields remain empty.")

    print("External application prepared for manual review.")
    print("No external submission was performed.")
    return "READY_FOR_REVIEW"


def external_apply(*args, **kwargs):
    """Compatibility wrapper: prepare the page but never submit externally."""
    page = kwargs.get("page") or (args[0] if args else None)
    if page is None:
        return "FAILED"
    remaining = list(args[1:])
    while len(remaining) < 4:
        remaining.append("")
    return prepare_external_application_page(page, *remaining[:4])
