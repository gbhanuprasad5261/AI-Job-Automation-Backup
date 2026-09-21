"""External ATS application helpers.

The module handles external application pages generically. It fills only
known candidate data, never guesses unknown required questions, and submits
only when AUTO_SUBMIT is enabled and a final submission can be verified.
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
RESUME_PATH = os.getenv("RESUME_PATH", "resume/resume.pdf")
SUCCESSFACTORS_PASSWORD = os.getenv("SUCCESSFACTORS_PASSWORD", "").strip()
AUTO_SUBMIT = os.getenv("AUTO_SUBMIT", "true").strip().lower() == "true"


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
    if "successfactors.eu" in value or "successfactors.com" in value or "career5.successfactors.eu" in value:
        return "SUCCESSFACTORS"
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

    Values are supplied by the candidate or directly supported by the resume.
    Unknown questions are deliberately left untouched.
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
            "hidden", "file", "radio", "checkbox", "submit", "button", "password"
        }:
            continue

        try:
            current = element.input_value().strip()
        except Exception:
            current = ""

        q = _google_question_text(element)
        if not q:
            q = _field_text(element)

        normalized_q = " ".join(q.split()).lower()
        value = None

        if "email" in normalized_q:
            value = email
        elif "full name" in normalized_q or re.search(r"(^|\s)name(\s|$)", normalized_q):
            value = name
        elif "first name" in normalized_q or "firstname" in normalized_q:
            value = name.split()[0] if name else ""
        elif "last name" in normalized_q or "lastname" in normalized_q or "surname" in normalized_q:
            value = " ".join(name.split()[1:]) if len(name.split()) > 1 else ""
        elif "phone" in normalized_q or "mobile" in normalized_q or "telephone" in normalized_q:
            value = phone
        elif "current location" in normalized_q:
            value = current_location
        elif "year of graduation" in normalized_q:
            value = "2025"
        elif "cgpa" in normalized_q:
            value = "7.29"
        elif "college" in normalized_q:
            value = "Siddhartha Institute of Science and Technology"

        if value is None or current == value:
            continue

        if _fill(page.locator("input, textarea").nth(i), value):
            print(f"Google Form known field filled: {normalized_q[:90]} -> {value}")
            count += 1

    return count


def _google_forms_confirmed_radio_answers(page: Page) -> int:
    """Select only Google Form radio answers explicitly confirmed by the candidate."""
    answers = {
        "will you available for 6 months internship": "Yes",
        "will you be available for an in-office internship from in hsr location, 5 days a week": "Yes",
        "how soon are you available to join": "Immediate",
        "any prior internship experience": "Yes",
        "do you have project experience with node.js": "No",
        "do you have project experience with postgresql": "No",
        "do you have project experience with react.js": "No",
    }

    count = 0
    processed = set()

    try:
        radios = page.locator("[role='radio'], input[type='radio']")
        total = radios.count()
    except Exception:
        return 0

    for i in range(total):
        radio = radios.nth(i)
        if not _visible(radio):
            continue

        question = _google_question_text(radio)
        normalized = " ".join(question.split()).lower()
        desired = None
        matched_key = None

        for question_key, answer in answers.items():
            if question_key in normalized:
                desired = answer
                matched_key = question_key
                break

        if desired is None or matched_key in processed:
            continue

        processed.add(matched_key)

        try:
            item = radio.locator("xpath=ancestor::*[@role='listitem'][1]")
            if not item.count():
                item = radio.locator("xpath=..")
        except Exception:
            item = radio.locator("xpath=..")

        clicked = False

        # Google Forms custom radios expose each option as role=radio.
        try:
            options = item.locator("[role='radio']")
            for j in range(options.count()):
                option = options.nth(j)
                if not _visible(option):
                    continue
                label = (
                    option.get_attribute("aria-label")
                    or option.inner_text()
                    or ""
                ).strip()
                if label.lower() == desired.lower():
                    option.click()
                    page.wait_for_timeout(150)
                    clicked = True
                    break
        except Exception:
            pass

        # Fallback for native radio inputs/labels.
        if not clicked:
            try:
                labels = item.locator("label")
                for j in range(labels.count()):
                    label = labels.nth(j)
                    if not _visible(label):
                        continue
                    if (label.inner_text() or "").strip().lower() == desired.lower():
                        label.click()
                        page.wait_for_timeout(150)
                        clicked = True
                        break
            except Exception:
                pass

        if clicked:
            print(
                f"Google Form confirmed answer selected: "
                f"{normalized[:90]} -> {desired}"
            )
            count += 1

    return count


def _google_forms_required_empty_count(page: Page) -> int:
    """Count required Google Forms questions that are actually unanswered.

    Google Forms commonly puts aria-required on a question container while its
    individual custom radio options use aria-checked. The old implementation
    inspected the container as though it were an input, which falsely reported
    selected radio questions as unanswered.
    """
    count = 0
    seen_items = set()

    try:
        required = page.locator("[aria-required='true']")
        total = required.count()
    except Exception:
        return 0

    for i in range(total):
        element = required.nth(i)
        if not _visible(element):
            continue

        try:
            item = element.locator("xpath=ancestor::*[@role='listitem'][1]")
            if not item.count() or not _visible(item.first):
                item = element.locator("xpath=..")
            item = item.first
        except Exception:
            item = element.locator("xpath=..").first

        try:
            item_key = (
                item.get_attribute("data-params")
                or item.get_attribute("data-item-id")
                or str(i)
            )
        except Exception:
            item_key = str(i)

        if item_key in seen_items:
            continue
        seen_items.add(item_key)

        answered = False

        # Custom Google Forms radio group: any option with aria-checked=true
        # means the question has been answered.
        try:
            role_radios = item.locator("[role='radio']")
            for j in range(role_radios.count()):
                option = role_radios.nth(j)
                if not _visible(option):
                    continue
                if (option.get_attribute("aria-checked") or "").lower() == "true":
                    answered = True
                    break
        except Exception:
            pass

        # Native radio/checkbox fallback.
        if not answered:
            try:
                native_choices = item.locator("input[type='radio'], input[type='checkbox']")
                for j in range(native_choices.count()):
                    choice = native_choices.nth(j)
                    try:
                        if choice.is_checked():
                            answered = True
                            break
                    except Exception:
                        continue
            except Exception:
                pass

        # File upload: a selected file is an answer.
        if not answered:
            try:
                files = item.locator("input[type='file']")
                for j in range(files.count()):
                    file_input = files.nth(j)
                    file_count = int(file_input.evaluate("el => el.files ? el.files.length : 0") or 0)
                    if file_count > 0:
                        answered = True
                        break
            except Exception:
                pass

        # Text/select controls.
        if not answered:
            try:
                controls = item.locator("input:not([type='radio']):not([type='checkbox']):not([type='hidden']):not([type='submit']):not([type='button']):not([type='file']), textarea, select")
                for j in range(controls.count()):
                    control = controls.nth(j)
                    if not _visible(control):
                        continue
                    value = control.input_value().strip()
                    if value and value.lower() not in {"select", "select..."}:
                        answered = True
                        break
            except Exception:
                pass

        if answered:
            continue

        try:
            question = item.inner_text().strip()
        except Exception:
            question = _google_question_text(element)

        print("Google Form required question still unanswered:")
        print(f"  Question: {question or '(not detected)'}")
        count += 1

    return count



def _prepare_google_form(
    page: Page,
    name: str,
    email: str,
    phone: str,
    current_location: str,
    current_company: str,
    resume_path: str = RESUME_PATH,
) -> str:
    """Prepare and, when safe, submit a Google Form using known candidate data.

    Unknown questions are left untouched. Submission occurs only when no
    required question remains unanswered and AUTO_SUBMIT is enabled.
    """
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

    confirmed_answers = _google_forms_confirmed_radio_answers(page)
    print(f"Google Form confirmed answers selected: {confirmed_answers}")

    configured_resume = resume_path or RESUME_PATH
    uploaded = _upload_google_forms_resume(page, configured_resume)
    print(
        f"Resume uploaded: {'Yes' if uploaded else 'No / upload not verified'}"
    )

    # Give Google Forms a moment to update aria-checked / upload state.
    try:
        page.wait_for_timeout(500)
    except Exception:
        time.sleep(0.5)

    required = _google_forms_required_empty_count(page)
    print(f"Google Form required questions still unanswered: {required}")

    if required:
        print(
            "Required Google Form questions remain unanswered; "
            "manual review is required."
        )
    else:
        print("No detectable unanswered required Google Form questions on this page.")

    print("Google Form prepared with known candidate data.")
    return _auto_submit_google_form(page)



def _auto_submit_google_form(page: Page) -> str:
    """Submit Google Forms only after required-question verification."""
    if not AUTO_SUBMIT:
        print("AUTO_SUBMIT disabled: Google Form submission was not performed.")
        return "READY_FOR_REVIEW"

    required = _google_forms_required_empty_count(page)
    if required:
        print("Google Form required questions remain unanswered; submission stopped safely.")
        return "READY_FOR_REVIEW"

    controls = page.locator(
        "[role='button'], button, input[type='submit'], input[type='button']"
    )
    submit = None
    for i in range(controls.count()):
        control = controls.nth(i)
        if not _visible(control):
            continue
        label = _normalized_control_label(control)
        if label == "submit":
            try:
                disabled = control.is_disabled()
            except Exception:
                disabled = False
            if not disabled:
                submit = control
                break

    if submit is None:
        print("Google Form final Submit control was not found.")
        return "READY_FOR_REVIEW"

    previous_url = page.url
    print("AUTO_SUBMIT enabled: submitting Google Form...")
    try:
        submit.click()
    except Exception as exc:
        print(f"Google Form submission click failed: {exc}")
        return "FAILED"

    success_phrases = (
        "your response has been recorded",
        "response has been recorded",
        "your response was recorded",
        "thanks for submitting",
        "thank you for submitting",
        "form submitted",
        "response recorded",
    )
    for _ in range(20):
        body = _text(page).lower()
        if any(phrase in body for phrase in success_phrases) or "/formresponse" in page.url.lower():
            print("Google Form submission verified: response recorded.")
            return "SUBMITTED"
        try:
            page.wait_for_timeout(500)
        except Exception:
            time.sleep(0.5)

    print("Google Form submission could not be verified; application status was not marked APPLIED.")
    return "READY_FOR_REVIEW"

def _resolve_resume_path(resume_path: str) -> str:
    """Resolve and validate the configured local resume path."""
    if not resume_path:
        return ""

    raw = os.path.expandvars(os.path.expanduser(str(resume_path).strip()))
    if not raw:
        return ""

    candidates = []
    if os.path.isabs(raw):
        candidates.append(raw)
    else:
        candidates.append(os.path.abspath(raw))
        candidates.append(
            os.path.abspath(os.path.join(os.path.dirname(__file__), raw))
        )

    seen = set()
    for candidate in candidates:
        candidate = os.path.normpath(candidate)
        if candidate in seen:
            continue
        seen.add(candidate)
        try:
            if os.path.isfile(candidate) and os.path.getsize(candidate) > 0:
                return candidate
        except OSError:
            continue

    return ""


def _upload_google_forms_resume(page: Page, resume_path: str) -> bool:
    """Upload a Google Forms file question through its Add file/Browse UI.

    Google Forms may render the upload dialog in a child frame. The native
    file chooser must be handled with Playwright's file-chooser event; typing
    a Windows path into the web page is not reliable and is intentionally not
    used here.
    """
    resolved_path = _resolve_resume_path(resume_path)
    if not resolved_path:
        print(f"Resume file not found: {resume_path or '(empty path)'}")
        return False

    filename = os.path.basename(resolved_path)

    def all_frames():
        try:
            return page.frames
        except Exception:
            return [page]

    def visible_text(element):
        try:
            return (
                (element.get_attribute("aria-label") or "") + " " +
                (element.get_attribute("title") or "") + " " +
                (element.inner_text() or "")
            ).strip().lower()
        except Exception:
            return ""

    # Fast path: if Google Forms exposes a real file input anywhere, set it.
    for frame in all_frames():
        try:
            inputs = frame.locator("input[type='file']")
            for i in range(inputs.count()):
                element = inputs.nth(i)
                try:
                    element.set_input_files(resolved_path)
                    verified_name = element.evaluate(
                        "el => el.files && el.files.length ? el.files[0].name : ''"
                    ) or ""
                    verified_size = element.evaluate(
                        "el => el.files && el.files.length ? el.files[0].size : 0"
                    ) or 0
                    if verified_name == filename and int(verified_size) > 0:
                        print(
                            f"Resume uploaded and verified: {verified_name} "
                            f"({int(verified_size)} bytes)"
                        )
                        return True
                except Exception:
                    continue
        except Exception:
            continue

    # Find Add file across the main page and all child frames.
    add_file = None
    add_file_frame = None
    for frame in all_frames():
        try:
            controls = frame.locator("[role='button'], button")
            for i in range(controls.count()):
                control = controls.nth(i)
                if not _visible(control):
                    continue
                label = visible_text(control)
                if "add file" in label:
                    add_file = control
                    add_file_frame = frame
                    break
        except Exception:
            continue
        if add_file is not None:
            break

    if add_file is None:
        print("Google Forms resume 'Add file' control was not found.")
        return False

    try:
        add_file.scroll_into_view_if_needed()
    except Exception:
        pass

    # Open the Google Forms upload dialog.
    try:
        add_file.click()
        page.wait_for_timeout(800)
    except Exception as exc:
        print(f"Could not click Google Forms 'Add file': {exc}")
        return False

    # After the picker opens, some Google Forms versions expose the actual
    # file input directly (usually hidden). Prefer it when available because
    # it avoids depending on the visual Browse control.
    for frame in all_frames():
        try:
            inputs = frame.locator("input[type='file']")
            for i in range(inputs.count()):
                element = inputs.nth(i)
                try:
                    element.set_input_files(resolved_path)
                    verified_name = element.evaluate(
                        "el => el.files && el.files.length ? el.files[0].name : ''"
                    ) or ""
                    verified_size = element.evaluate(
                        "el => el.files && el.files.length ? el.files[0].size : 0"
                    ) or 0
                    if verified_name == filename and int(verified_size) > 0:
                        print(
                            f"Resume uploaded and verified: {verified_name} "
                            f"({int(verified_size)} bytes)"
                        )
                        return True
                except Exception:
                    continue
        except Exception:
            continue

    # Google Forms can put the upload dialog in a child frame. Search every
    # frame for the actual Browse control.
    browse = None
    browse_frame = None
    for _ in range(20):
        for frame in all_frames():
            try:
                controls = frame.locator("[role='button'], button, [role='link']")
                for i in range(controls.count()):
                    control = controls.nth(i)
                    if not _visible(control):
                        continue
                    label = visible_text(control)
                    if re.search(r"\bbrowse\b", label):
                        browse = control
                        browse_frame = frame
                        break
            except Exception:
                continue
            if browse is not None:
                break
        if browse is not None:
            break
        try:
            page.wait_for_timeout(250)
        except Exception:
            time.sleep(0.25)

    if browse is None:
        print("Google Forms 'Browse' control was not found after clicking Add file.")
        return False

    # The Browse button opens the OS file picker. Capture that event and provide
    # the already-verified local PDF path directly to Playwright.
    try:
        with page.expect_file_chooser(timeout=15000) as chooser_info:
            browse.click()
        chooser = chooser_info.value
        chooser.set_files(resolved_path)
        page.wait_for_timeout(1800)
        print(f"Google Forms file chooser received: {filename}")
    except Exception as exc:
        print(f"Google Forms Browse/file chooser attempt failed: {exc}")

        # Fallback: the Browse click may reveal a hidden file input without
        # exposing a Playwright file-chooser event.
        for frame in all_frames():
            try:
                inputs = frame.locator("input[type='file']")
                for i in range(inputs.count()):
                    element = inputs.nth(i)
                    try:
                        element.set_input_files(resolved_path)
                        verified_name = element.evaluate(
                            "el => el.files && el.files.length ? el.files[0].name : ''"
                        ) or ""
                        verified_size = element.evaluate(
                            "el => el.files && el.files.length ? el.files[0].size : 0"
                        ) or 0
                        if verified_name == filename and int(verified_size) > 0:
                            print(
                                f"Resume uploaded and verified: {verified_name} "
                                f"({int(verified_size)} bytes)"
                            )
                            return True
                    except Exception:
                        continue
            except Exception:
                continue

    # Verify the upload. The file input may live in the dialog frame or may be
    # replaced after the chooser closes, so inspect every current frame.
    for frame in all_frames():
        try:
            inputs = frame.locator("input[type='file']")
            for i in range(inputs.count()):
                element = inputs.nth(i)
                verified_name = element.evaluate(
                    "el => el.files && el.files.length ? el.files[0].name : ''"
                ) or ""
                verified_size = element.evaluate(
                    "el => el.files && el.files.length ? el.files[0].size : 0"
                ) or 0
                if verified_name == filename and int(verified_size) > 0:
                    print(
                        f"Resume uploaded and verified: {verified_name} "
                        f"({int(verified_size)} bytes)"
                    )
                    return True
        except Exception:
            continue

    # Final UI-level verification: Google Forms often displays the uploaded
    # filename even when its internal file input is not accessible to us.
    try:
        for frame in all_frames():
            body = (frame.locator("body").inner_text() or "").lower()
            if filename.lower() in body:
                print(f"Resume uploaded and verified in Google Forms: {filename}")
                return True
    except Exception:
        pass

    print("Google Forms resume upload could not be verified.")
    return False


def _upload_resume(page: Page, resume_path: str) -> bool:
    """Upload the configured resume through a generic ATS file input/control.

    Only real file inputs or clearly labeled upload controls are used. No
    unrelated buttons are clicked and no application is submitted here.
    """
    resolved_path = _resolve_resume_path(resume_path or RESUME_PATH)
    if not resolved_path:
        print(f"Resume file not found: {resume_path or RESUME_PATH}")
        return False

    filename = os.path.basename(resolved_path)

    def frames():
        try:
            return page.frames
        except Exception:
            return [page]

    def control_text(element):
        try:
            return " ".join([
                _attr(element, "aria-label"),
                _attr(element, "title"),
                element.inner_text() or "",
            ]).strip().lower()
        except Exception:
            return ""

    # Fast path: any actual file input is unambiguous.
    for frame in frames():
        try:
            inputs = frame.locator("input[type='file']")
            for i in range(inputs.count()):
                element = inputs.nth(i)
                try:
                    element.set_input_files(resolved_path)
                    verified_name = element.evaluate(
                        "el => el.files && el.files.length ? el.files[0].name : ''"
                    ) or ""
                    verified_size = element.evaluate(
                        "el => el.files && el.files.length ? el.files[0].size : 0"
                    ) or 0
                    if verified_name == filename and int(verified_size) > 0:
                        print(
                            f"Resume uploaded and verified: {verified_name} "
                            f"({int(verified_size)} bytes)"
                        )
                        return True
                except Exception:
                    continue
        except Exception:
            continue

    # Otherwise use only a clearly labeled upload/add-file/browse control.
    upload_control = None
    for frame in frames():
        try:
            controls = frame.locator("button, [role='button'], [role='link'], a")
            for i in range(controls.count()):
                control = controls.nth(i)
                if not _visible(control):
                    continue
                label = control_text(control)
                if any(term in label for term in (
                    "upload resume", "upload cv", "upload your resume",
                    "add resume", "add file", "upload file", "browse",
                )):
                    upload_control = control
                    break
        except Exception:
            continue
        if upload_control is not None:
            break

    if upload_control is None:
        print("External ATS resume file input/control was not found.")
        return False

    try:
        with page.expect_file_chooser(timeout=10000) as chooser_info:
            upload_control.click()
        chooser_info.value.set_files(resolved_path)
        page.wait_for_timeout(1000)
    except Exception as exc:
        print(f"External ATS file chooser attempt failed: {exc}")
        # Some ATS pages reveal a file input after clicking the upload control.
        for frame in frames():
            try:
                inputs = frame.locator("input[type='file']")
                for i in range(inputs.count()):
                    element = inputs.nth(i)
                    try:
                        element.set_input_files(resolved_path)
                        verified_name = element.evaluate(
                            "el => el.files && el.files.length ? el.files[0].name : ''"
                        ) or ""
                        verified_size = element.evaluate(
                            "el => el.files && el.files.length ? el.files[0].size : 0"
                        ) or 0
                        if verified_name == filename and int(verified_size) > 0:
                            print(
                                f"Resume uploaded and verified: {verified_name} "
                                f"({int(verified_size)} bytes)"
                            )
                            return True
                    except Exception:
                        continue
            except Exception:
                continue

    # Verify the file input or visible filename after the upload.
    for frame in frames():
        try:
            inputs = frame.locator("input[type='file']")
            for i in range(inputs.count()):
                element = inputs.nth(i)
                verified_name = element.evaluate(
                    "el => el.files && el.files.length ? el.files[0].name : ''"
                ) or ""
                verified_size = element.evaluate(
                    "el => el.files && el.files.length ? el.files[0].size : 0"
                ) or 0
                if verified_name == filename and int(verified_size) > 0:
                    print(
                        f"Resume uploaded and verified: {verified_name} "
                        f"({int(verified_size)} bytes)"
                    )
                    return True
        except Exception:
            continue

    try:
        body = _text(page).lower()
        if filename.lower() in body:
            print(f"Resume upload verified by visible filename: {filename}")
            return True
    except Exception:
        pass

    print("External ATS resume upload could not be verified.")
    return False


def _looks_like_application_form(page: Page) -> bool:
    """Return True only when an actual application interface is visible."""

    try:
        url = (page.url or "").lower()
    except Exception:
        url = ""

    body = _text(page).lower()

    # Known ATS/platform indicators.
    if any(domain in url for domain in (
        "successfactors.eu",
        "successfactors.com",
        "greenhouse.io",
        "lever.co",
        "myworkdayjobs.com",
        "ashbyhq.com",
        "smartrecruiters.com",
        "jobvite.com",
    )):
        if any(term in body for term in (
            "apply for this position",
            "application form",
            "complete your application",
            "candidate information",
            "personal information",
            "upload resume",
            "upload cv",
            "submit application",
            "contact information",
        )):
            return True

    strong_phrases = (
        "application form",
        "apply for this position",
        "apply for this job",
        "complete your application",
        "candidate information",
        "candidate details",
        "personal information",
        "contact information",
        "upload resume",
        "upload your resume",
        "upload cv",
        "submit application",
        "employment application",
    )

    if any(phrase in body for phrase in strong_phrases):
        return True

    try:
        inputs = page.locator(
            "input:not([type='hidden']):not([type='submit']), "
            "textarea, select, input[type='file']"
        )
        visible_count = 0
        for i in range(min(inputs.count(), 120)):
            if _visible(inputs.nth(i)):
                visible_count += 1
                if visible_count >= 2:
                    return True
    except Exception:
        pass

    if _iframe_contains_application_form(page):
        return True

    return False


def _iframe_contains_application_form(page: Page) -> bool:
    """Detect an application form rendered inside a visible iframe."""
    try:
        for frame in page.frames:
            if frame == page.main_frame:
                continue

            try:
                body_text = (
                    frame.locator("body").inner_text(timeout=1500) or ""
                ).lower()
            except Exception:
                body_text = ""

            if any(term in body_text for term in (
                "application form",
                "apply for this position",
                "complete your application",
                "submit application",
                "candidate information",
                "personal information",
                "upload resume",
                "upload cv",
            )):
                return True

            try:
                controls = frame.locator(
                    "input:not([type='hidden']), "
                    "textarea, select, input[type='file']"
                )
                visible = 0
                for i in range(min(controls.count(), 30)):
                    if controls.nth(i).is_visible():
                        visible += 1
                        if visible >= 2:
                            return True
            except Exception:
                continue
    except Exception:
        pass

    return False


def _all_application_pages(page: Page):
    """Return open pages in the current browser context."""
    pages = []

    try:
        context = page.context
        for candidate in context.pages:
            try:
                if not candidate.is_closed():
                    pages.append(candidate)
            except Exception:
                continue
    except Exception:
        pass

    if page not in pages:
        pages.insert(0, page)

    return pages


def _wait_for_external_application(
    page: Page,
    timeout_ms: int = 12000,
    baseline_pages=None,
):
    """Wait for an application form without adopting stale pages from earlier jobs."""
    baseline_pages = set(baseline_pages or ())
    deadline = time.time() + (timeout_ms / 1000)

    while time.time() < deadline:
        candidates = [page]

        try:
            for candidate in page.context.pages:
                if candidate is page or candidate in baseline_pages:
                    continue
                try:
                    if not candidate.is_closed():
                        candidates.append(candidate)
                except Exception:
                    continue
        except Exception:
            pass

        for candidate in candidates:
            try:
                if _looks_like_application_form(candidate):
                    return candidate
            except Exception:
                continue

        try:
            page.wait_for_timeout(500)
        except Exception:
            time.sleep(0.5)

    return page


def _click_external_application_start(page: Page):
    """
    Find and click a clearly identifiable application-start control.

    Handles same-tab navigation, popup/new-tab application flows,
    delayed JavaScript navigation, and broader company-site Apply labels.
    """
    if _looks_like_application_form(page):
        return page

    allowed_terms = (
        "apply now",
        "apply",
        "apply for this job",
        "apply for this position",
        "apply online",
        "start application",
        "begin application",
        "submit application",
        "continue application",
        "apply to this job",
    )

    candidates = page.locator(
        "button, [role='button'], a, [role='link'], "
        "input[type='submit'], input[type='button']"
    )

    try:
        total = candidates.count()
    except Exception:
        total = 0

    for i in range(total):
        control = candidates.nth(i)

        if not _visible(control):
            continue

        label = " ".join([
            _attr(control, "aria-label"),
            _attr(control, "title"),
            (control.inner_text() or ""),
            _attr(control, "value"),
        ])
        normalized = " ".join(label.lower().split())

        if not any(
            term == normalized or term in normalized
            for term in allowed_terms
        ):
            continue

        print(f"Application-start control found: {normalized[:120]}")

        before_pages = set(_all_application_pages(page))

        try:
            control.scroll_into_view_if_needed()
        except Exception:
            pass

        try:
            control.click(timeout=5000)
        except Exception as exc:
            print(f"Application control click failed: {exc}")
            continue

        try:
            page.wait_for_timeout(1000)
        except Exception:
            pass

        active_page = _wait_for_external_application(
            page,
            timeout_ms=12000,
            baseline_pages=before_pages,
        )

        if active_page is not page:
            try:
                if _looks_like_application_form(active_page):
                    print("Application form detected in newly opened page.")
                    return active_page
            except Exception:
                pass

        return active_page

    print("No recognizable external application-start control found.")
    return page


def _normalized_control_label(element) -> str:
    try:
        raw = " ".join([
            _attr(element, "aria-label"),
            _attr(element, "title"),
            element.inner_text() or "",
            _attr(element, "value"),
        ])
        return " ".join(raw.split()).strip().lower()
    except Exception:
        return ""


def _find_final_submit_control(page: Page):
    """Find an explicit final application-submit control, never a consent control."""
    allowed = {
        "submit",
        "submit application",
        "submit your application",
        "send application",
        "apply now",
        "complete application",
        "finish application",
    }
    controls = page.locator(
        "button, [role='button'], input[type='submit'], input[type='button'], a"
    )
    for i in range(controls.count()):
        control = controls.nth(i)
        if not _visible(control):
            continue
        label = _normalized_control_label(control)
        if label not in allowed:
            continue
        # Never treat consent/cookie controls as application submission.
        if any(term in label for term in ("accept", "agree", "consent", "cookie")):
            continue
        return control
    return None


def _external_submission_verified(page: Page, previous_url: str) -> bool:
    """Verify a submitted external application using explicit confirmation evidence."""
    success_phrases = (
        "application submitted",
        "application received",
        "successfully submitted",
        "successfully applied",
        "we received your application",
        "thank you for applying",
        "thanks for applying",
        "thank you for your application",
        "your application has been received",
        "application complete",
        # Microsoft Forms confirmation wording.
        "your response has been recorded",
        "response has been recorded",
        "your response was recorded",
        "thanks for submitting",
        "thank you for submitting",
        "response recorded",
        "form submitted",
    )

    previous_url = (previous_url or "").lower()

    for _ in range(24):
        body = _text(page).lower()
        if any(phrase in body for phrase in success_phrases):
            return True

        try:
            current_url = (page.url or "").lower()
            if current_url != previous_url:
                # Only accept URL evidence when the destination itself is a
                # conventional confirmation/success page. A generic URL
                # change is not enough to mark an application as submitted.
                if any(token in current_url for token in (
                    "thank", "success", "confirmation", "complete", "submitted",
                    "formresponse", "responsepage",
                )):
                    # Microsoft Forms can keep responsepage.aspx while changing
                    # its body to the recorded-response confirmation. The body
                    # check above remains the primary proof.
                    if any(token in current_url for token in (
                        "thank", "success", "confirmation", "complete", "submitted",
                        "formresponse",
                    )):
                        return True
        except Exception:
            pass

        try:
            page.wait_for_timeout(500)
        except Exception:
            time.sleep(0.5)

    return False


def _auto_submit_external_application(page: Page) -> str:
    """Submit only a fully populated external application when AUTO_SUBMIT is enabled."""
    if not AUTO_SUBMIT:
        print("AUTO_SUBMIT disabled: external submission was not performed.")
        return "READY_FOR_REVIEW"

    required = _required_empty_count(page)
    print(f"Visible required fields before external submit: {required}")
    if required:
        print("Unknown/required fields remain unanswered; submission stopped safely.")
        return "READY_FOR_REVIEW"

    submit_control = _find_final_submit_control(page)
    if submit_control is None:
        print("No unambiguous final application Submit control was found.")
        return "READY_FOR_REVIEW"

    previous_url = page.url
    print(f"AUTO_SUBMIT enabled: submitting via '{_normalized_control_label(submit_control)}'...")
    try:
        submit_control.scroll_into_view_if_needed()
    except Exception:
        pass

    try:
        submit_control.click()
    except Exception as exc:
        print(f"External submission click failed: {exc}")
        return "FAILED"

    if _external_submission_verified(page, previous_url):
        print("External application submission verified.")
        return "SUBMITTED"

    print("External submission could not be verified; application status was not marked APPLIED.")
    return "READY_FOR_REVIEW"


def _prepare_successfactors_account(page: Page) -> str:
    """Complete the generic SuccessFactors account-creation step.

    The password is supplied through SUCCESSFACTORS_PASSWORD (with the
    configured candidate value as fallback). The country/region code is
    selected only when India/+91 is an available option. Unknown required
    fields are never guessed.
    """
    password = SUCCESSFACTORS_PASSWORD.strip()
    if not password:
        print("SuccessFactors password is not configured; stopping safely.")
        return "READY_FOR_REVIEW"

    filled = 0

    password_fields = page.locator(
        "input[type='password'], input[name*='pwd' i], input[id*='pwd' i]"
    )
    seen = set()
    for i in range(password_fields.count()):
        field = password_fields.nth(i)
        if not _visible(field):
            continue
        try:
            key = field.get_attribute("id") or field.get_attribute("name") or str(i)
        except Exception:
            key = str(i)
        if key in seen:
            continue
        seen.add(key)
        try:
            field.fill(password)
            filled += 1
        except Exception:
            continue

    if filled:
        print(f"SuccessFactors password fields filled: {filled}")

    # Country/region code: choose India/+91 only when the option is explicitly
    # present. Never select an arbitrary numeric code.
    selects = page.locator("select")
    country_selected = False
    for i in range(selects.count()):
        select = selects.nth(i)
        if not _visible(select):
            continue
        metadata = _field_text(select)
        if not any(term in metadata for term in (
            "country", "region code", "country/region code", "itu code", "phone code"
        )):
            continue
        try:
            options = select.locator("option")
            for j in range(options.count()):
                option = options.nth(j)
                label = " ".join([
                    _attr(option, "label"),
                    option.inner_text() or "",
                    _attr(option, "value"),
                ]).strip().lower()
                if "india" in label and "+91" in label:
                    select.select_option(index=j)
                    country_selected = True
                    break
            if country_selected:
                print("SuccessFactors country/region code selected: India (+91)")
                break
        except Exception:
            continue

    if not country_selected:
        # Some SuccessFactors pages expose +91 as the value without the word
        # India. Only use an option explicitly containing +91.
        for i in range(selects.count()):
            select = selects.nth(i)
            if not _visible(select):
                continue
            try:
                options = select.locator("option")
                for j in range(options.count()):
                    option = options.nth(j)
                    label = " ".join([
                        _attr(option, "label"),
                        option.inner_text() or "",
                        _attr(option, "value"),
                    ]).strip().lower()
                    if "+91" in label:
                        select.select_option(index=j)
                        country_selected = True
                        print("SuccessFactors country/region code selected: +91")
                        break
                if country_selected:
                    break
            except Exception:
                continue

    if not country_selected:
        print("SuccessFactors India/+91 country code option was not found.")

    # Ensure password fields are no longer considered empty by the generic
    # required-field checker.
    required = _required_empty_count(page)
    print(f"SuccessFactors required fields still empty: {required}")
    if required:
        print("Unknown required SuccessFactors fields remain; they will not be guessed.")
        return "READY_FOR_REVIEW"

    # Account creation is an explicit platform step, not a generic unknown
    # question. Only click an exact Register/Create Account control.
    controls = page.locator(
        "button, [role='button'], input[type='submit'], input[type='button']"
    )
    allowed = {"register", "create account", "create profile"}
    for i in range(controls.count()):
        control = controls.nth(i)
        if not _visible(control):
            continue
        label = _normalized_control_label(control)
        if label not in allowed:
            continue
        previous_url = page.url
        print(f"SuccessFactors account step: clicking '{label}'...")
        try:
            control.scroll_into_view_if_needed()
            control.click()
            page.wait_for_timeout(2000)
        except Exception as exc:
            print(f"SuccessFactors account-step click failed: {exc}")
            return "FAILED"

        if page.url != previous_url or _looks_like_application_form(page):
            print("SuccessFactors account step completed; continuing application preparation.")
            return "CONTINUE"

        body = _text(page).lower()
        if any(term in body for term in (
            "account created", "registration successful", "profile created",
            "complete your application", "candidate information"
        )):
            print("SuccessFactors account step completed; continuing application preparation.")
            return "CONTINUE"

        print("SuccessFactors account step could not be verified; stopping safely.")
        return "READY_FOR_REVIEW"

    print("No unambiguous SuccessFactors Register/Create Account control was found.")
    return "READY_FOR_REVIEW"

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


def _wait_for_manual_consent(page: Page, detection_timeout_ms=8000, wait_timeout_ms=10000) -> bool:
    """Automatically accept clearly identified cookie/privacy banners.

    This helper is intentionally conservative about WHAT it clicks:
      * It only considers visible cookie/privacy consent containers or
        controls whose surrounding text clearly indicates cookie/privacy
        consent.
      * It prefers labels such as Accept All Cookies / Accept All / Accept.
      * It never clicks Reject, Save Preferences, application terms,
        declarations, or arbitrary buttons.

    It is safe to call after every page navigation.
    """

    consent_phrases = (
        "we use cookies",
        "we use cookies to",
        "cookie preferences",
        "cookie preference",
        "cookie consent",
        "cookie policy",
        "cookies necessary",
        "cookies are used",
        "accept cookies",
        "use cookies",
        "your cookie choices",
        "privacy preferences",
        "privacy preference",
        "privacy notice",
        "privacy agreement",
        "data privacy",
        "consent agreement",
        "your choices will be recorded",
    )

    reject_words = (
        "reject",
        "decline",
        "deny",
        "do not accept",
        "necessary only",
        "only necessary",
    )

    def control_label(control):
        try:
            values = [
                control.inner_text() or "",
                control.get_attribute("aria-label") or "",
                control.get_attribute("title") or "",
                control.get_attribute("value") or "",
                control.get_attribute("data-testid") or "",
            ]
            label = " ".join(v.strip().lower() for v in values if v)
            label = re.sub(r"\s+", " ", label).strip()
            return label
        except Exception:
            return ""

    def is_accept_label(label):
        if not label or any(word in label for word in reject_words):
            return False

        # Covers:
        # Accept
        # Accept All
        # Accept All Cookies
        # Accept Cookies
        # Allow All
        # Allow All Cookies
        # I Agree / Agree
        return bool(
            re.search(
                r"\b("
                r"accept(?:\s+all)?(?:\s+(?:cookies?|tracking|optional))?"
                r"|allow(?:\s+all)?(?:\s+(?:cookies?|tracking|optional))?"
                r"|agree"
                r"|i\s+agree"
                r"|consent"
                r")\b",
                label,
                re.I,
            )
        )

    def has_cookie_context(text):
        text = (text or "").lower()
        return any(phrase in text for phrase in consent_phrases)

    def find_consent_control():
        # 1. Strongest signal: visible cookie/privacy overlays/dialogs.
        try:
            containers = page.locator(
                "dialog, [role='dialog'], [aria-modal='true'], "
                "[id*='cookie' i], [class*='cookie' i], "
                "[id*='consent' i], [class*='consent' i], "
                "[id*='privacy' i], [class*='privacy' i]"
            )

            for i in range(containers.count()):
                container = containers.nth(i)
                if not _visible(container):
                    continue

                try:
                    text = container.inner_text() or ""
                except Exception:
                    text = ""

                if not has_cookie_context(text):
                    continue

                controls = container.locator(
                    "button, [role='button'], input[type='button'], "
                    "input[type='submit'], a"
                )

                for j in range(controls.count()):
                    control = controls.nth(j)
                    if not _visible(control):
                        continue

                    label = control_label(control)
                    if is_accept_label(label):
                        return control

        except Exception:
            pass

        # 2. Fallback for banners that do not have dialog/overlay markup.
        try:
            body = page.locator("body").inner_text() or ""
            if has_cookie_context(body):
                controls = page.locator(
                    "button, [role='button'], input[type='button'], "
                    "input[type='submit'], a"
                )

                candidates = []
                for i in range(controls.count()):
                    control = controls.nth(i)
                    if not _visible(control):
                        continue

                    label = control_label(control)
                    if is_accept_label(label):
                        candidates.append(control)

                # Prefer an explicit cookie-labelled accept control.
                for control in candidates:
                    label = control_label(control)
                    if "cookie" in label or "cookies" in label:
                        return control

                # If the page itself clearly says it uses cookies, an
                # unambiguous Accept/Allow/Agree control is safe to use.
                if len(candidates) == 1:
                    return candidates[0]

                # Prefer "Accept All" over generic Accept when multiple
                # consent controls are present.
                for control in candidates:
                    label = control_label(control)
                    if "accept all" in label or "allow all" in label:
                        return control

        except Exception:
            pass

        return None

    deadline = time.time() + detection_timeout_ms / 1000

    while time.time() < deadline:
        control = find_consent_control()

        if control is not None:
            label = control_label(control)

            print()
            print("=" * 70)
            print("COOKIE / PRIVACY CONSENT DETECTED")
            print("=" * 70)
            print(f"Automatically accepting: {label or 'consent control'}")

            try:
                control.scroll_into_view_if_needed(timeout=3000)
            except Exception:
                pass

            try:
                control.click(timeout=5000)
            except Exception:
                try:
                    control.click(force=True, timeout=5000)
                except Exception as exc:
                    print(f"Automatic cookie consent click failed: {exc}")
                    return False

            try:
                page.wait_for_timeout(1000)
            except Exception:
                time.sleep(1)

            # Verify briefly that the same consent control/banner disappeared.
            verify_deadline = time.time() + wait_timeout_ms / 1000
            while time.time() < verify_deadline:
                if find_consent_control() is None:
                    print("Cookie/privacy consent accepted automatically.")
                    return True

                try:
                    page.wait_for_timeout(300)
                except Exception:
                    time.sleep(0.3)

            # Some CMPs keep a hidden/duplicate control in the DOM after
            # accepting. The click itself succeeded, so don't block the job.
            print("Cookie consent click completed; continuing.")
            return True

        try:
            page.wait_for_timeout(300)
        except Exception:
            time.sleep(0.3)

    return True


def _external_page_has_error(page: Page) -> bool:
    """Detect obvious external job/application error pages before filling anything."""
    try:
        title = page.title().lower()
    except Exception:
        title = ""
    body = _text(page).lower()

    strong_errors = (
        "custom job error",
        "job not found",
        "position not found",
        "position no longer available",
        "job no longer available",
        "this job is no longer available",
        "page not found",
        "404 not found",
    )

    if any(message in title or message in body for message in strong_errors):
        return True

    # Avoid treating ordinary career pages as errors merely because they
    # contain the number 404 or generic error language.
    return False


def prepare_external_application_page(
    page: Page,
    resume_path: str = "",
    name: str = "",
    email: str = "",
    phone: str = "",
    current_location: str = CURRENT_LOCATION,
    current_company: str = CURRENT_COMPANY,
):
    """Handle an external ATS page without guessing unknown questions."""
    body = _text(page)
    ats = detect_ats(page.url, body)
    print(f"External ATS detected: {ats}")
    print(f"External page: {page.url}")
    print("Preparing external application page...")

    if _external_page_has_error(page):
        print("External application page shows a job/application error; stopping safely.")
        return "FAILED"

    consent_completed = _wait_for_manual_consent(page)
    if not consent_completed:
        print("External application requires consent handling.")
        print("No application submission was performed.")
        print("Automation will skip this application and continue.")
        return "READY_FOR_REVIEW"

    # On unknown company career pages, first follow an unambiguous Apply control
    # to reach the actual application form. This is generic and not job-specific.
    if ats != "GOOGLE_FORMS":
        page = _click_external_application_start(page)
        try:
            page.wait_for_load_state("domcontentloaded", timeout=10000)
        except Exception:
            pass
        try:
            page.wait_for_timeout(1500)
        except Exception:
            pass

        # _click_external_application_start already isolates newly opened
        # pages from tabs left behind by earlier jobs. Do not scan the entire
        # browser context again here, or a stale ATS page can be adopted.
        try:
            page.wait_for_load_state("domcontentloaded", timeout=10000)
        except Exception:
            pass
        try:
            page.wait_for_timeout(750)
        except Exception:
            pass

        if _external_page_has_error(page):
            print("External application page shows a job/application error; stopping safely.")
            return "FAILED"

        body = _text(page)
        ats = detect_ats(page.url, body)
        print(f"External application page after Apply control: {page.url}")
        print(f"External ATS detected after navigation: {ats}")

        # The company page can open the SuccessFactors form in the same tab
        # while its cookie banner appears only after navigation. Handle that
        # banner before inspecting/filing the form.
        consent_completed = _wait_for_manual_consent(page)
        if not consent_completed:
            print("External application requires consent handling.")
            print("No application submission was performed.")
            print("Automation will skip this application and continue.")
            return "READY_FOR_REVIEW"

        # Re-detect after consent because the banner can obscure the form and
        # the first body snapshot may have been taken before the form rendered.
        body = _text(page)
        ats = detect_ats(page.url, body)
        print(f"External ATS detected after consent: {ats}")

    consent_completed = _wait_for_manual_consent(page)
    if not consent_completed:
        print("External application requires consent handling.")
        print("No application submission was performed.")
        print("Automation will skip this application and continue.")
        return "READY_FOR_REVIEW"

    if ats == "GOOGLE_FORMS":
        return _prepare_google_form(
            page,
            name,
            email,
            phone,
            current_location,
            current_company,
            resume_path or RESUME_PATH,
        )

    if ats == "SUCCESSFACTORS" or "successfactors.eu" in (page.url or "").lower() or "successfactors.com" in (page.url or "").lower():
        account_result = _prepare_successfactors_account(page)
        if account_result == "FAILED":
            return "FAILED"
        if account_result == "READY_FOR_REVIEW":
            return "READY_FOR_REVIEW"
        # CONTINUE means the account step completed. The same generic
        # application handling below now operates on the resulting page.
        body = _text(page)
        ats = detect_ats(page.url, body)

    if not _looks_like_application_form(page):
        print("No recognizable external application form was reached.")
        print("No external submission was performed.")
        return "READY_FOR_REVIEW"

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
        print("Required fields remain empty; unknown required questions will not be guessed.")
        return "READY_FOR_REVIEW"

    print("No visible required fields remain empty.")
    return _auto_submit_external_application(page)

def external_apply(*args, **kwargs):
    """Compatibility wrapper for generic external application handling."""
    page = kwargs.get("page") or (args[0] if args else None)
    if page is None:
        return "FAILED"
    remaining = list(args[1:])
    while len(remaining) < 4:
        remaining.append("")
    return prepare_external_application_page(page, *remaining[:4])
