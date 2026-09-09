"""External ATS application helpers.

The module prepares external applications for review. It deliberately does
not submit external applications automatically because ATS forms vary and
unknown questions must never be guessed.
"""

import os
import re
import time
from urllib.parse import parse_qs, unquote, urlparse

from playwright.sync_api import Page

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

CURRENT_LOCATION = os.getenv("CURRENT_LOCATION", "Bengaluru")
CURRENT_COMPANY = os.getenv("CURRENT_COMPANY", "N/A")
CURRENT_CTC = "0"
EXPECTED_CTC = "5,00,000"
GITHUB_URL = os.getenv("GITHUB_URL", "https://github.com/gbhanuprasad5261")


DEFAULT_COVER_LETTER = """I am a Bachelor of Technology graduate in Computer Science and Engineering with a specialization in Artificial Intelligence and Data Science, graduating in 2025 from Siddartha Institute of Science and Technology. I am actively seeking an entry-level Software Engineer, Java Developer, or Backend Developer opportunity where I can apply my technical foundation, learn from experienced engineers, and contribute to real-world software products.

My core technical skills include Java, Spring, Spring Boot, Spring MVC, Spring Data JPA, Hibernate, JDBC, SQL, MySQL, REST APIs, microservices, Git, GitHub, Maven, Postman, JUnit, and Mockito. Through academic projects, hands-on practice, internship and training experience, I have developed an understanding of object-oriented programming, backend application development, database integration, API development, debugging, testing, and version control. I am comfortable learning new technologies and adapting to development processes used by a professional engineering team.

As a fresher, I bring strong motivation, a willingness to learn, attention to detail, and a disciplined approach to solving technical problems. I understand that professional software development requires clean and maintainable code, effective communication, testing, code reviews, documentation, and continuous improvement. I am prepared to work collaboratively with senior developers, product teams, and other stakeholders while taking ownership of assigned tasks and improving my skills through practical experience. I also value feedback and use it to improve the quality and reliability of my work.

I am particularly interested in opportunities involving Java and Spring Boot backend development, REST services, SQL databases, and scalable application architecture. I am open to working in Bengaluru, Hyderabad, Chennai, or suitable remote opportunities in India, and I am willing to relocate when required.

Thank you for considering my application. I would welcome the opportunity to discuss how my technical skills, learning mindset, and commitment can contribute to your engineering team. I am available to begin my professional career as a dedicated entry-level software engineer and am eager to grow with an organization that values engineering quality, teamwork, and continuous learning.
"""


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
    if "jobvite.com" in value:
        return "JOBVITE"
    if "cutshort.io" in value:
        return "CUTSHORT"
    if "docs.google.com/forms" in value or "forms.gle" in value:
        return "GOOGLE_FORMS"
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
                "ashbyhq.com", "smartrecruiters.com", "jobvite.com",
                "cutshort.io",
            )):
                return href
    except Exception:
        pass

    return ""


def check_external_eligibility(page: Page) -> str:
    """
    Return INELIGIBLE only when the page contains an explicit
    numeric minimum experience requirement above the candidate's
    experience.

    Supported examples:
        Minimum 1 year
        1+ years experience
        1 year experience required
        Work Experience: 1 - 2 Years
        Work Experience 1 to 2 Years
        Experience: 2-4 years

    Generic mentions of "experience" are not treated as requirements.
    """

    body = _text(page)
    lower = body.lower()

    # Candidate is a fresher / 0 years.
    candidate_years = 0

    # --------------------------------------------------
    # Explicit minimum/range experience requirements
    # --------------------------------------------------
    minimum_years = []

    patterns = [
        # Examples:
        # "minimum 1 year"
        # "minimum of 2 years"
        # "at least 1 year"
        # "required 2 years"
        r"(?:minimum|required|at\s+least|minimum\s+of)"
        r"\D{0,60}"
        r"(\d+)\+?\s*years?",

        # Examples:
        # "1+ years of experience"
        # "2 years professional experience required"
        r"(\d+)\+?\s*years?\s*"
        r"(?:of\s*)?"
        r"(?:professional\s*)?"
        r"experience\s*(?:required|minimum|needed)",

        # Examples:
        # "Work Experience 1 - 2 Years"
        # "Work Experience: 1 to 2 Years"
        # "Experience 2-4 Years"
        #
        # IMPORTANT:
        # For a range, the FIRST number is the minimum.
        r"(?:work\s+experience|experience)"
        r"\s*(?::|-)?\s*"
        r"(\d+)\s*"
        r"(?:-|–|—|to)\s*"
        r"(\d+)\s*years?",

        # Examples:
        # "Work Experience: 1 Years"
        # "Experience: 2 Years"
        r"(?:work\s+experience|experience)"
        r"\s*(?::|-)?\s*"
        r"(\d+)\+?\s*years?",
    ]

    for pattern in patterns:
        for match in re.finditer(pattern, lower):
            try:
                # For a range, group 1 is the minimum.
                minimum = int(match.group(1))
                minimum_years.append(minimum)
            except (ValueError, IndexError):
                pass

    # --------------------------------------------------
    # Compare against candidate experience
    # --------------------------------------------------
    if any(year > candidate_years for year in minimum_years):
        required = max(minimum_years)

        print(
            f"External requirement : {required}+ years"
        )
        print(
            f"Candidate experience : {candidate_years} years"
        )
        print(
            "External eligibility  : INELIGIBLE"
        )

        return "INELIGIBLE"

    print(
        "External requirement  : Not specified"
    )
    print(
        "No explicit minimum experience requirement detected."
    )

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


def _fill_known_application_fields(page: Page, name: str) -> int:
    """Fill only unambiguous candidate fields on external ATS forms.

    Safe known values:
      * explicit fresher/years-of-experience fields -> 0
      * explicit CTC/current salary fields -> 0
      * explicit ECTC/expected salary fields -> 5,00,000
      * explicit cover-letter/applicant-letter fields -> profile cover letter

    Other salary fields and unknown questions are deliberately left untouched.
    """
    count = 0
    fields = page.locator("input, textarea")

    for i in range(fields.count()):
        element = fields.nth(i)
        if not _visible(element):
            continue

        field_type = _attr(element, "type").lower()
        if field_type in {"hidden", "file", "radio", "checkbox", "submit", "button", "password"}:
            continue

        q = _field_text(element)
        placeholder = _attr(element, "placeholder").strip().lower()
        name_attr = _attr(element, "name").strip().lower()
        id_attr = _attr(element, "id").strip().lower()
        aria_label = _attr(element, "aria-label").strip().lower()
        combined = f"{q} {placeholder}"

        try:
            current = element.input_value().strip()
        except Exception:
            current = ""

        # Explicit cover-letter field MUST be checked before experience/salary.
        # Some ATS forms place unrelated text such as "experience" around the
        # textarea, so broad parent-label matching must never overwrite it.
        is_cover_letter = (
            "cover letter" in combined
            or "applicant letter" in combined
            or "awsm_applicant_letter" in combined
            or "awsm-cover-letter" in combined
        )
        if is_cover_letter:
            try:
                if current != DEFAULT_COVER_LETTER:
                    element.fill(DEFAULT_COVER_LETTER)
                print(
                    "Known external field filled: cover letter -> "
                    f"{len(DEFAULT_COVER_LETTER.split())} words"
                )
                count += 1
            except Exception:
                pass
            continue

        # Explicit current CTC / current salary field.
        # Match CTC first so it cannot be mistaken for a generic salary field.
        is_current_ctc = (
            "ctc" in combined
            and not any(term in combined for term in (
                "expected ctc", "ectc", "expected salary",
                "desired salary", "salary expectation", "expected compensation",
            ))
        ) or (
            any(term in combined for term in (
                "current ctc", "current salary", "current compensation",
            ))
            and not any(term in combined for term in (
                "expected", "desired", "ectc",
            ))
        )
        if is_current_ctc:
            try:
                if current != CURRENT_CTC:
                    element.fill(CURRENT_CTC)
                print("Known external field filled: CTC -> 0")
                count += 1
            except Exception:
                pass
            continue

        # Explicit expected CTC / expected salary field.
        is_expected_ctc = (
            "ectc" in combined
            or "expected ctc" in combined
            or "expected salary" in combined
            or "desired salary" in combined
            or "salary expectation" in combined
            or "expected compensation" in combined
        )
        if is_expected_ctc:
            try:
                if current != EXPECTED_CTC:
                    element.fill(EXPECTED_CTC)
                print(
                    f"Known external field filled: ECTC -> {EXPECTED_CTC}"
                )
                count += 1
            except Exception:
                pass
            continue

        # Explicit years/experience field. A placeholder such as "6 Years"
        # describes the expected format, not the candidate's experience.
        is_experience = (
            "awsm_text_1" in combined
            or "experience" in combined
            or bool(re.search(r"\byears?\b", placeholder))
        )
        if is_experience and "ctc" not in combined and "salary" not in combined:
            try:
                if current != "0":
                    element.fill("0")
                print("Known external field filled: experience -> 0")
                count += 1
            except Exception:
                pass
            continue

    return count


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

        # Lever's Current location is an autocomplete input. If the
        # browser has prefilled or partially populated it, we still enforce
        # the configured candidate value.
        if "current location" in q or ("location" in q and "current" in q):
            value = current_location
            try:
                element.scroll_into_view_if_needed()
            except Exception:
                pass

            try:
                element.fill(value)
            except Exception:
                try:
                    element.click()
                    element.press("Control+A")
                    element.type(value)
                except Exception:
                    continue

            try:
                element.evaluate(
                    """(el, value) => {
                        el.value = value;
                        el.dispatchEvent(new Event('input', {bubbles:true}));
                        el.dispatchEvent(new Event('change', {bubbles:true}));
                        el.dispatchEvent(new Event('blur', {bubbles:true}));
                    }""",
                    value,
                )
            except Exception:
                pass

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

def _google_question_text(element) -> str:
    """Return the visible Google Forms question text for a field."""
    try:
        text = element.evaluate(
            """el => {
                const item = el.closest('[role="listitem"]');
                if (item) return item.innerText || item.textContent || '';
                const parent = el.parentElement;
                return parent ? (parent.innerText || parent.textContent || '') : '';
            }"""
        ) or ""
    except Exception:
        text = ""
    return " ".join(text.split()).lower()


def _fill_google_forms_known_fields(
    page: Page,
    name: str,
    email: str,
    phone: str,
    current_location: str = CURRENT_LOCATION,
    current_company: str = CURRENT_COMPANY,
) -> int:
    """Fill only clearly identifiable Google Forms fields.

    This intentionally does not click Google Forms consent/record-email
    checkboxes and does not guess answers to unknown questions.
    """
    count = 0
    fields = page.locator("input, textarea")

    try:
        total = fields.count()
    except Exception:
        return 0

    for i in range(total):
        element = fields.nth(i)
        if not _visible(element):
            continue

        field_type = _attr(element, "type").lower()
        if field_type in {
            "hidden", "file", "radio", "checkbox", "submit",
            "button", "password"
        }:
            continue

        try:
            current = element.input_value().strip()
        except Exception:
            current = ""

        q = _google_question_text(element)
        if not q:
            q = _field_text(element)

        value = None

        if "email" in q and field_type == "email":
            value = email
        elif "full name" in q or re.search(r"(^|\\s)name(\\s|$)", q):
            value = name
        elif "first name" in q or "firstname" in q:
            value = name.split()[0] if name else ""
        elif "last name" in q or "lastname" in q or "surname" in q:
            value = " ".join(name.split()[1:]) if len(name.split()) > 1 else ""
        elif "phone" in q or "mobile" in q or "telephone" in q:
            value = phone
        elif "current location" in q:
            value = current_location
        elif "current company" in q:
            value = current_company or "N/A"

        if value is None:
            continue

        # Do not overwrite a Google-managed email value unnecessarily.
        if current:
            continue

        if _fill(page.locator("input, textarea").nth(i), value):
            print(f"Google Form known field filled: {q[:90]} -> {value}")
            count += 1

    return count


def _google_forms_required_empty_count(page: Page) -> int:
    """Count required Google Forms questions that are still unanswered.

    Google Forms often uses aria-required on descendants rather than the
    standard HTML `required` attribute. We inspect the containing question
    block and report its visible text so manual review is actionable.
    """
    count = 0
    seen_items = set()

    try:
        required = page.locator("[aria-required='true']")
        for i in range(required.count()):
            element = required.nth(i)
            if not _visible(element):
                continue

            try:
                item = element.locator("xpath=ancestor::*[@role='listitem'][1]")
                if not item.count() or not _visible(item.first):
                    item = element.locator("xpath=..")
            except Exception:
                item = element.locator("xpath=..")

            try:
                item_key = item.first.get_attribute("data-params") or str(i)
            except Exception:
                item_key = str(i)

            if item_key in seen_items:
                continue
            seen_items.add(item_key)

            try:
                field_type = _attr(element, "type").lower()
                if field_type in {"radio", "checkbox"}:
                    # Unknown required choices/consent questions are not guessed.
                    checked = element.is_checked()
                    if checked:
                        continue
                else:
                    value = element.input_value().strip()
                    if value:
                        continue
            except Exception:
                value = ""

            try:
                question = item.first.inner_text().strip()
            except Exception:
                question = _google_question_text(element)

            print("Google Form required question still unanswered:")
            print(f"  Question: {question or '(not detected)'}")
            count += 1
    except Exception:
        pass

    return count


def _prepare_google_form(page: Page, name: str, email: str, phone: str,
                         current_location: str, current_company: str) -> str:
    """Prepare a Google Form without submitting it."""
    print("Google Form detected: using safe known-field handling.")
    filled = _fill_google_forms_known_fields(
        page,
        name,
        email,
        phone,
        current_location,
        current_company,
    )
    print(f"Google Form known fields filled: {filled}")

    # Google Forms does not normally expose a resume upload as a standard ATS
    # file field. Try the normal upload helper without requiring it.
    uploaded = _upload_resume(page, "")
    print(f"Resume uploaded: {'Yes' if uploaded else 'No / not required here'}")

    required = _google_forms_required_empty_count(page)
    print(f"Google Form required questions still unanswered: {required}")

    if required:
        print("Required Google Form questions remain unanswered; manual review is required.")
    else:
        print("No detectable unanswered required Google Form questions on this page.")

    print("Google Form prepared for manual review.")
    print("No Google Form submission was performed.")
    return "READY_FOR_REVIEW"


def _resolve_resume_path(resume_path: str) -> str:
    """Resolve the configured resume path from either the project CWD or module location."""
    if not resume_path:
        return ""

    candidates = []
    raw = os.path.expanduser(str(resume_path).strip())
    if os.path.isabs(raw):
        candidates.append(raw)
    else:
        candidates.append(os.path.abspath(raw))
        project_root = os.path.dirname(os.path.abspath(__file__))
        candidates.append(os.path.join(project_root, raw))

    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate

    return ""


def _upload_resume(page: Page, resume_path: str) -> bool:
    """Upload the resume and verify that the browser file input actually contains it."""
    resolved_path = _resolve_resume_path(resume_path)
    if not resolved_path:
        print(f"Resume file not found: {resume_path or '(empty path)'}")
        return False

    try:
        inputs = page.locator("input[type='file']")
        total = inputs.count()
    except Exception:
        return False

    for i in range(total):
        element = inputs.nth(i)
        try:
            element.set_input_files(resolved_path)

            # Verify the DOM FileList rather than assuming set_input_files succeeded.
            verified_name = element.evaluate(
                """el => el.files && el.files.length ? el.files[0].name : ''"""
            ) or ""
            verified_size = element.evaluate(
                """el => el.files && el.files.length ? el.files[0].size : 0"""
            ) or 0

            if verified_name and int(verified_size) > 0:
                print(
                    f"Resume uploaded and verified: {verified_name} "
                    f"({int(verified_size)} bytes)"
                )
                return True
        except Exception as exc:
            print(f"Resume upload attempt {i + 1} failed: {exc}")
            continue

    print("Resume upload could not be verified on any file input.")
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


def _check_known_terms_consent(page: Page) -> int:
    """Check the clearly identified data/privacy terms checkbox.

    This is limited to a checkbox whose associated visible text explicitly
    describes agreement to the website's data/privacy storage or handling.
    Unknown checkboxes are never selected.
    """
    count = 0
    checkboxes = page.locator("input[type='checkbox']")

    try:
        total = checkboxes.count()
    except Exception:
        return 0

    for i in range(total):
        checkbox = checkboxes.nth(i)
        if not _visible(checkbox):
            continue

        try:
            if checkbox.is_checked():
                continue
        except Exception:
            pass

        associated_text = _field_text(checkbox).strip().lower()

        # Also inspect the nearest form row/container because some custom
        # checkbox implementations keep the visible agreement text outside
        # the <label> element directly associated with the input.
        try:
            container_text = checkbox.evaluate(
                """el => {
                    const label = el.labels && el.labels.length
                        ? el.labels[0]
                        : el.closest('label');
                    if (label) return label.innerText || label.textContent || '';
                    const row = el.closest('div, p, li, section');
                    return row ? (row.innerText || row.textContent || '') : '';
                }"""
            ) or ""
            associated_text += " " + container_text.strip().lower()
        except Exception:
            pass

        # Match only explicit data/privacy handling agreement language.
        has_data_terms = (
            ("data" in associated_text and "agree" in associated_text)
            or ("data" in associated_text and "storage" in associated_text)
            or ("data" in associated_text and "handling" in associated_text)
            or ("privacy" in associated_text and "agree" in associated_text)
            or "terms and conditions" in associated_text
        )

        if not has_data_terms:
            continue

        try:
            checkbox.check()
            page.wait_for_timeout(250)
            if checkbox.is_checked():
                print("Known terms/privacy checkbox checked.")
                count += 1
                continue
        except Exception:
            # Custom checkbox: click only this specifically identified input.
            try:
                checkbox.click()
                page.wait_for_timeout(250)
                if checkbox.is_checked():
                    print("Known terms/privacy checkbox checked.")
                    count += 1
            except Exception:
                pass

    return count

def _required_empty_count(page: Page) -> int:
    """Count visible required fields that are still empty, including resume files."""
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

            # File inputs cannot be checked with input_value(). Verify the
            # browser FileList instead so a required resume is not falsely
            # reported as complete.
            if tag == "INPUT" and field_type == "file":
                try:
                    file_count = int(
                        element.evaluate(
                            """el => el.files ? el.files.length : 0"""
                        ) or 0
                    )
                except Exception:
                    file_count = 0

                if file_count > 0:
                    continue

                count += 1
                print("Required resume/file field still empty:")
                print(f"  Label       : {_field_text(element).strip() or '(not detected)'}")
                print(f"  Tag         : {tag}")
                print(f"  Name        : {_attr(element, 'name') or '(none)'}")
                print(f"  ID          : {_attr(element, 'id') or '(none)'}")
                print(
                    f"  Accept      : "
                    f"{_attr(element, 'accept') or '(not specified)'}"
                )
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


def _wait_for_manual_consent(page: Page, detection_timeout_ms=3000, wait_timeout_ms=120000) -> bool:
    """
    Detect a visible privacy/consent modal and wait for the human user
    to complete it.

    IMPORTANT:
    This function NEVER clicks Agree/Accept/Consent.
    If no consent modal is detected, it returns immediately so normal
    ATS pages continue without delay.
    """

    consent_phrases = (
        "data privacy agreement",
        "privacy agreement",
        "privacy notice",
        "privacy policy",
        "terms specified",
        "terms and conditions",
        "consent agreement",
    )

    agree_phrases = (
        "i agree",
        "agree",
        "accept",
        "consent",
    )

    def find_consent_dialog():
        try:
            dialogs = page.locator(
                "dialog, [role='dialog'], [aria-modal='true']"
            )

            for i in range(dialogs.count()):
                dialog = dialogs.nth(i)

                try:
                    if not dialog.is_visible():
                        continue

                    text = (
                        dialog.inner_text() or ""
                    ).strip().lower()

                    if not text:
                        continue

                    has_consent_text = any(
                        phrase in text
                        for phrase in consent_phrases
                    )

                    if not has_consent_text:
                        continue

                    buttons = dialog.locator(
                        "button, [role='button'], "
                        "input[type='button'], input[type='submit']"
                    )

                    for j in range(buttons.count()):
                        button = buttons.nth(j)

                        try:
                            if not button.is_visible():
                                continue

                            button_text = (
                                button.inner_text() or ""
                            ).strip().lower()

                            aria = (
                                button.get_attribute("aria-label")
                                or ""
                            ).strip().lower()

                            title = (
                                button.get_attribute("title")
                                or ""
                            ).strip().lower()

                            combined = (
                                f"{button_text} {aria} {title}"
                            )

                            if any(
                                phrase in combined
                                for phrase in agree_phrases
                            ):
                                return dialog

                        except Exception:
                            continue

                except Exception:
                    continue

        except Exception:
            pass

        return None

    # Give a dynamically-rendered consent modal a short opportunity
    # to appear. If none appears, this is a normal ATS page.
    detection_deadline = (
        time.time() + detection_timeout_ms / 1000
    )

    while time.time() < detection_deadline:
        dialog = find_consent_dialog()

        if dialog is not None:
            print()
            print("=" * 70)
            print("PRIVACY / CONSENT AGREEMENT DETECTED")
            print("=" * 70)
            print()
            print(
                "A privacy or consent agreement requires human action."
            )
            print()
            print(
                "Please review the agreement and click the "
                "appropriate button yourself."
            )
            print()
            print(
                'Automation will NOT click "I Agree" / "Accept".'
            )
            print()
            print("Waiting for manual consent...")

            wait_deadline = (
                time.time() + wait_timeout_ms / 1000
            )

            while time.time() < wait_deadline:
                if find_consent_dialog() is None:
                    print()
                    print("Manual consent completed.")
                    print(
                        "Continuing application preparation..."
                    )
                    return True

                try:
                    page.wait_for_timeout(500)
                except Exception:
                    time.sleep(0.5)

            print()
            print("=" * 70)
            print("MANUAL CONSENT TIMEOUT")
            print("=" * 70)
            print(
                "Consent was not completed within the "
                "allowed waiting period."
            )
            print("Stopping safely.")
            return False

        try:
            page.wait_for_timeout(250)
        except Exception:
            time.sleep(0.25)

    # No consent modal was detected. Continue normal ATS processing.
    return True


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
    consent_completed = _wait_for_manual_consent(page)

    if not consent_completed:
        print()
        print("External application requires manual consent.")
        print("No application submission was performed.")
        return "READY_FOR_REVIEW"

    if ats == "GOOGLE_FORMS":
        return _prepare_google_form(
            page,
            name,
            email,
            phone,
            current_location,
            current_company,
        )

    special_fields = _fill_known_application_fields(page, name)
    if special_fields:
        print(f"Known application-specific fields filled: {special_fields}")

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

    terms_checked = _check_known_terms_consent(page)
    print(f"Known terms/privacy checkboxes checked: {terms_checked}")

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
