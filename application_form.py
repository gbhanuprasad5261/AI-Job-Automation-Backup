import os
import re
from playwright.sync_api import Page


# ============================================================
# APPLICATION FORM AUTOMATION
# ============================================================

# ------------------------------------------------------------
# Configuration
# ------------------------------------------------------------

RESUME_PATH = os.path.abspath(
    os.path.join("resume", "resume.pdf")
)

# IMPORTANT:
# Put your real details here if they are not already available
# through your config.py / environment variables.

APPLICANT_NAME = os.getenv(
    "APPLICANT_NAME",
    "G Bhanu Prasad"
)

EMAIL = os.getenv(
    "APPLICANT_EMAIL",
    "gbhanuprasad1236@gmail.com"
)

PHONE = os.getenv(
    "APPLICANT_PHONE",
    "9392801041"
)

YEARS_OF_EXPERIENCE = os.getenv(
    "YEARS_OF_EXPERIENCE",
    "0"
)

CITY = os.getenv(
    "APPLICANT_CITY",
    "Bengaluru"
)

COUNTRY = os.getenv(
    "APPLICANT_COUNTRY",
    "India"
)

STATE = os.getenv("APPLICANT_STATE", "Karnataka")
DEGREE = os.getenv("APPLICANT_DEGREE", "B.Tech")
FIELD_OF_STUDY = os.getenv("APPLICANT_FIELD_OF_STUDY", "Computer Science and Engineering(AI&DS)")
UNIVERSITY = os.getenv("APPLICANT_UNIVERSITY", "Siddartha Institute of Science and Technology")
GRADUATION_YEAR = os.getenv("GRADUATION_YEAR", "2025")
EDUCATION_START_MONTH = os.getenv("EDUCATION_START_MONTH", "June")
EDUCATION_START_YEAR = os.getenv("EDUCATION_START_YEAR", "2021")
EDUCATION_END_MONTH = os.getenv("EDUCATION_END_MONTH", "April")
EDUCATION_END_YEAR = os.getenv("EDUCATION_END_YEAR", "2025")

# SSC / High School education entry. This entry is handled separately so the
# existing B.Tech and Intermediate entries are never modified by the SSC fix.
SSC_SCHOOL_NAME = os.getenv("SSC_SCHOOL_NAME", "Zilla Parishad High School")
SSC_FIELD_OF_STUDY = os.getenv("SSC_FIELD_OF_STUDY", "English")
SSC_START_MONTH = os.getenv("SSC_START_MONTH", "March")
SSC_START_YEAR = os.getenv("SSC_START_YEAR", "2018")
SSC_END_MONTH = os.getenv("SSC_END_MONTH", "March")
SSC_END_YEAR = os.getenv("SSC_END_YEAR", "2019")

CGPA = os.getenv("CGPA", "7.29")
CURRENT_CTC = os.getenv("CURRENT_CTC", "0")
EXPECTED_CTC = os.getenv("EXPECTED_CTC", "500000")
NOTICE_PERIOD = os.getenv("NOTICE_PERIOD", "0")
WORK_AUTHORIZED = os.getenv("WORK_AUTHORIZED", "Yes")
REQUIRES_SPONSORSHIP = os.getenv("REQUIRES_SPONSORSHIP", "No")
WILLING_TO_RELOCATE = os.getenv("WILLING_TO_RELOCATE", "Yes")
WILLING_ONSITE = os.getenv("WILLING_ONSITE", "Yes")
INTERNSHIP_EXPERIENCE = os.getenv("INTERNSHIP_EXPERIENCE", "Yes")
SHIFT_COMFORT = os.getenv("SHIFT_COMFORT", "Yes")
WEEKEND_COMFORT = os.getenv("WEEKEND_COMFORT", "Yes")
WORK_PERMIT = os.getenv("WORK_PERMIT", "Yes")
DISABILITY = os.getenv("DISABILITY", "No")
CRIMINAL_HISTORY = os.getenv("CRIMINAL_HISTORY", "No")
FRESHER = os.getenv("FRESHER", "Yes")
BACHELORS_COMPLETED = os.getenv("BACHELORS_COMPLETED", "Yes")
LINKEDIN_PROFILE_URL = os.getenv(
    "LINKEDIN_PROFILE_URL",
    "https://www.linkedin.com/in/g-bhanu-prasad-66ab1b225"
)

TECH_EXPERIENCE = {
    "java": "1", "spring boot": "1", "sql": "1", "mysql": "1",
    "nosql": "1", "aws": "1", "docker": "1", "linux": "1",
    "microservices": "1", "rest api": "1", "git": "1", "github": "1",
    "spring mvc": "1", "hibernate": "1", "jpa": "1", "maven": "1",
    "junit": "1", "mockito": "1", "postman": "1",
}

# ------------------------------------------------------------
# Safety switch
# ------------------------------------------------------------
# False = fill and navigate, but STOP before final submission.
# True  = allow final Submit button to be clicked.
#
# Keep this FALSE during testing.

AUTO_SUBMIT = False  # SAFETY: final Submit is always manual.


# ============================================================
# Utility Functions
# ============================================================

def safe_text(element):

    try:
        return element.inner_text().strip()
    except Exception:
        return ""


def safe_attribute(element, attribute):

    try:
        return element.get_attribute(attribute) or ""
    except Exception:
        return ""


def is_visible(element):

    try:
        return element.is_visible()
    except Exception:
        return False


def fill_if_empty(locator, value):

    if not value:
        return False

    try:

        if locator.count() == 0:
            return False

        element = locator.first

        if not element.is_visible():
            return False

        current_value = ""

        try:
            current_value = element.input_value().strip()
        except Exception:
            pass

        if current_value:
            return True

        element.fill(value)

        return True

    except Exception:

        return False


# ============================================================
# Detect Application Modal
# ============================================================

def get_application_container(page: Page):

    # LinkedIn normally uses a dialog/modal for Easy Apply.

    try:

        dialogs = page.get_by_role("dialog")

        if dialogs.count() > 0:

            for i in range(dialogs.count()):

                dialog = dialogs.nth(i)

                if dialog.is_visible():
                    return dialog

    except Exception:
        pass

    # Fallback to page itself

    return page


# ============================================================
# Print Application Status
# ============================================================

def print_application_status(page: Page):

    try:

        body = page.locator("body").inner_text()

        match = re.search(
            r"(\d+)\s*/\s*(\d+)",
            body
        )

        if match:

            current = match.group(1)
            total = match.group(2)

            print(
                f"Application page: {current}/{total}"
            )

            return

    except Exception:
        pass

    print("Application page: unknown")

def get_application_step(page: Page):
    """
    Return the current LinkedIn Easy Apply step as:
        (current_page, total_pages)

    Example:
        1/4 -> (1, 4)
        2/4 -> (2, 4)
    """

    try:
        body = page.locator("body").inner_text()

        # Prefer the application page indicator.
        patterns = [
            r"Application page\s*:?\s*(\d+)\s*/\s*(\d+)",
            r"(\d+)\s*/\s*(\d+)"
        ]

        for pattern in patterns:
            match = re.search(
                pattern,
                body,
                re.IGNORECASE
            )

            if match:
                return (
                    int(match.group(1)),
                    int(match.group(2))
                )

    except Exception:
        pass

    return None


# ============================================================
# Fill Name
# ============================================================

def fill_name(container):

    print()
    print("Checking name fields...")

    selectors = [

        "input[name*='firstName' i]",
        "input[id*='firstName' i]",
        "input[autocomplete='given-name']",
        "input[name*='name' i]",
        "input[id*='name' i]",

    ]

    # First name / last name handling

    first_name = "G"
    last_name = "Bhanu Prasad"

    filled = False

    for selector in selectors:

        try:

            locator = container.locator(selector)

            if locator.count() == 0:
                continue

            for i in range(locator.count()):

                element = locator.nth(i)

                if not element.is_visible():
                    continue

                placeholder = safe_attribute(
                    element,
                    "placeholder"
                ).lower()

                name = safe_attribute(
                    element,
                    "name"
                ).lower()

                element_id = safe_attribute(
                    element,
                    "id"
                ).lower()

                combined = (
                    placeholder
                    + " "
                    + name
                    + " "
                    + element_id
                )

                if "first" in combined:

                    if fill_if_empty(
                        element,
                        first_name
                    ):
                        print("First name filled.")
                        filled = True

                elif "last" in combined:

                    if fill_if_empty(
                        element,
                        last_name
                    ):
                        print("Last name filled.")
                        filled = True

        except Exception:
            pass

    return filled


# ============================================================
# Fill Email
# ============================================================

def fill_email(container):

    print()
    print("Checking email field...")

    if not EMAIL:

        print(
            "EMAIL is empty."
        )

        print(
            "Set APPLICANT_EMAIL before running."
        )

        return False

    try:

        locator = container.locator(
            "input[type='email']"
        )

        if locator.count() > 0:

            if fill_if_empty(
                locator,
                EMAIL
            ):

                print("Email filled.")
                return True

    except Exception:
        pass

    return False


# ============================================================
# Fill Phone
# ============================================================

def select_india_country_code(container):
    """
    LinkedIn may render the phone country-code control as a custom
    combobox/button instead of a native <select>.

    We only select India (+91). We do NOT guess any other country.
    """
    print()
    print("Checking phone country code...")

    # Native select, if LinkedIn happens to expose one.
    try:
        selects = container.locator("select")
        for i in range(selects.count()):
            select = selects.nth(i)

            try:
                options = select.locator("option")
                for j in range(options.count()):
                    option = options.nth(j)
                    text = safe_text(option)
                    value = safe_attribute(option, "value")

                    if "India" in text and "+91" in text:
                        select.select_option(value=value)
                        print("Phone country code selected: India (+91)")
                        return True
            except Exception:
                continue
    except Exception:
        pass

    # Custom LinkedIn control.
    candidate_selectors = [
        "button[aria-label*='country' i]",
        "button[aria-label*='phone' i]",
        "[role='combobox'][aria-label*='country' i]",
        "[role='combobox'][aria-label*='phone' i]",
    ]

    for selector in candidate_selectors:
        try:
            controls = container.locator(selector)

            for i in range(controls.count()):
                control = controls.nth(i)

                if not control.is_visible():
                    continue

                current = (
                    safe_text(control)
                    + " "
                    + safe_attribute(control, "aria-label")
                ).lower()

                # If already India/+91, no action is necessary.
                if "india" in current or "+91" in current:
                    print("Phone country code already appears to be India (+91).")
                    return True

                control.click()
                container.page.wait_for_timeout(500)

                india = container.get_by_text(
                    re.compile(r"^India\s*\(\+91\)$", re.IGNORECASE)
                ).first

                if india.count() > 0 and india.is_visible():
                    india.click()
                    container.page.wait_for_timeout(300)
                    print("Phone country code selected: India (+91)")
                    return True

        except Exception:
            continue

    print("Could not explicitly select India (+91).")
    print("Please verify the country code before submitting.")
    return False


def fill_phone(container):

    print()
    print("Checking phone field...")

    if not PHONE:
        print("PHONE is empty.")
        print("Set APPLICANT_PHONE before running.")
        return False

    selectors = [
        "input[type='tel']",
        "input[name*='phone' i]",
        "input[id*='phone' i]",
        "input[autocomplete='tel']",
    ]

    phone_locator = None

    for selector in selectors:
        try:
            locator = container.locator(selector)

            if locator.count() > 0:
                phone_locator = locator
                break

        except Exception:
            pass

    if phone_locator is None:
        print("No phone field found on this page.")
        return False

    print("Checking phone country code...")
    select_india_country_code(container)

    try:
        if fill_if_empty(phone_locator, PHONE):
            print("Phone filled.")
            return True
    except Exception:
        pass

    return False


# ============================================================
# Upload Resume
# ============================================================

def upload_resume(container):

    print()
    print("Checking resume upload...")

    if not os.path.exists(RESUME_PATH):

        print(
            f"Resume not found: {RESUME_PATH}"
        )

        return False

    try:

        file_inputs = container.locator(
            "input[type='file']"
        )

        if file_inputs.count() == 0:

            print(
                "No file upload field found."
            )

            return False

        for i in range(
            file_inputs.count()
        ):

            element = file_inputs.nth(i)

            if not element.is_visible():

                # File inputs may be hidden.
                # They can still accept set_input_files().
                pass

            try:

                element.set_input_files(
                    RESUME_PATH
                )

                print(
                    "Resume uploaded:"
                )

                print(
                    f"  {RESUME_PATH}"
                )

                return True

            except Exception:
                continue

    except Exception as e:

        print(
            f"Resume upload error: {e}"
        )

    return False


# ============================================================
# Fill Education Editor
# ============================================================

def _visible_text_matches(container, text):
    """Return visible elements whose rendered text matches exactly."""
    matches = []
    try:
        locator = container.get_by_text(text, exact=True)
        for i in range(locator.count()):
            element = locator.nth(i)
            if element.is_visible():
                matches.append(element)
    except Exception:
        pass
    return matches


def _fill_labeled_input(scope, label_patterns, value):
    """Fill an input associated with one of the supplied label patterns."""
    if not value:
        return False

    try:
        inputs = scope.locator("input, textarea")
        for i in range(inputs.count()):
            element = inputs.nth(i)
            if not element.is_visible():
                continue

            metadata = _field_metadata(element)
            if any(pattern in metadata for pattern in label_patterns):
                try:
                    current = element.input_value().strip()
                except Exception:
                    current = ""
                if current == value:
                    return True
                element.fill(value)
                return True
    except Exception:
        pass

    return False


def _select_custom_education_option(scope, label_patterns, value):
    """Select a custom education dropdown only after an exact option match."""
    if not value:
        return False

    try:
        combos = scope.locator("[role='combobox'], button")
        for i in range(combos.count()):
            combo = combos.nth(i)
            if not combo.is_visible():
                continue

            metadata = (
                _field_metadata(combo)
                + " "
                + safe_text(combo).lower()
            )
            if not any(pattern in metadata for pattern in label_patterns):
                continue

            try:
                current = combo.input_value().strip()
            except Exception:
                current = safe_text(combo).strip()

            if current.lower() == value.lower():
                return True

            try:
                combo.click(timeout=5000)
            except Exception:
                continue

            scope.page.wait_for_timeout(300)

            options = scope.page.locator(
                "[role='option'], li[role='option'], [role='listbox'] li"
            )
            for j in range(options.count()):
                option = options.nth(j)
                if not option.is_visible():
                    continue
                option_text = re.sub(
                    r"\s+", " ", safe_text(option)
                ).strip()
                if option_text.lower() == value.lower():
                    try:
                        option.click(timeout=5000)
                        return True
                    except Exception:
                        try:
                            option.evaluate("(el) => el.click()")
                            return True
                        except Exception:
                            pass
    except Exception:
        pass

    return False


def _select_education_date_dropdowns(dialog, values):
    """Select exactly the four SSC Month/Year controls in editor order.

    LinkedIn renders these as custom buttons whose visible text is simply
    ``Month`` or ``Year``.  We intentionally collect only buttons with those
    exact visible labels, in DOM order, so unrelated controls from the B.Tech
    or Intermediate entries cannot be touched.
    """
    if len(values) != 4:
        return 0

    try:
        date_controls = []
        buttons = dialog.locator("button")

        for i in range(buttons.count()):
            button = buttons.nth(i)
            if not button.is_visible():
                continue
            text = re.sub(r"\s+", " ", safe_text(button)).strip().lower()
            if text in {"month", "year"}:
                date_controls.append(button)

        if len(date_controls) < 4:
            return 0

        selected = 0

        for button, value in zip(date_controls[:4], values):
            current = re.sub(r"\s+", " ", safe_text(button)).strip().lower()
            if current == value.lower():
                selected += 1
                continue

            try:
                button.click(timeout=5000)
            except Exception:
                continue

            dialog.page.wait_for_timeout(250)

            options = dialog.page.locator(
                "[role='option']:visible, [role='listbox']:visible li, li[role='option']:visible"
            )
            matched = False

            for j in range(options.count()):
                option = options.nth(j)
                option_text = re.sub(r"\s+", " ", safe_text(option)).strip()
                if option_text.lower() != value.lower():
                    continue

                try:
                    option.click(timeout=5000)
                    matched = True
                    break
                except Exception:
                    try:
                        option.evaluate("(el) => el.click()")
                        matched = True
                        break
                    except Exception:
                        pass

            if matched:
                selected += 1

        return selected
    except Exception:
        return 0


def _fill_ssc_major_field(dialog, value):
    """Fill only the SSC Major / Field of study input.

    Do not use generic text-question matching here because the education
    editor contains multiple entries and several blank text inputs.
    """
    if not value:
        return False

    try:
        # First use Playwright's accessible-label association when available.
        for pattern in [
            re.compile(r"major\s*/\s*field of study", re.I),
            re.compile(r"field of study", re.I),
        ]:
            try:
                field = dialog.get_by_label(pattern).first
                if field.count() > 0 and field.is_visible():
                    field.fill(value)
                    return True
            except Exception:
                pass

        # Fallback: inspect visible text inputs and use their nearest label
        # text. This is limited to the currently matched SSC dialog.
        inputs = dialog.locator("input:not([type='hidden']):not([type='checkbox']):not([type='radio']), textarea")
        for i in range(inputs.count()):
            element = inputs.nth(i)
            if not element.is_visible():
                continue

            try:
                current = element.input_value().strip()
            except Exception:
                current = ""

            if current == value:
                return True

            try:
                label_text = element.evaluate("""el => {
                    let node = el;
                    for (let i = 0; i < 6 && node; i++, node = node.parentElement) {
                        const labels = node.querySelectorAll ? node.querySelectorAll('label') : [];
                        for (const label of labels) {
                            const t = (label.innerText || '').trim().toLowerCase();
                            if (t.includes('major / field of study') || t === 'field of study') return t;
                        }
                    }
                    return '';
                }""")
            except Exception:
                label_text = ""

            if "major / field of study" in label_text or label_text == "field of study":
                element.fill(value)
                return True

    except Exception:
        pass

    return False


def _find_ssc_education_scope(page):
    """Find the visible SSC education card by its existing school value."""
    normalized_target = re.sub(
        r"\s+",
        " ",
        SSC_SCHOOL_NAME,
    ).strip().lower()

    try:
        fields = page.locator("input, textarea")

        for i in range(fields.count()):
            field = fields.nth(i)
            if not field.is_visible():
                continue

            try:
                value = field.input_value().strip()
            except Exception:
                value = safe_text(field).strip()

            if re.sub(r"\s+", " ", value).strip().lower() != normalized_target:
                continue

            scope = field
            for _ in range(12):
                try:
                    scope = scope.locator("xpath=..")
                    if scope.count() == 0:
                        break

                    scope_text = re.sub(
                        r"\s+",
                        " ",
                        safe_text(scope),
                    ).strip().lower()

                    if "major / field of study" not in scope_text:
                        continue

                    buttons = scope.locator("button")
                    date_count = 0

                    for j in range(buttons.count()):
                        button = buttons.nth(j)
                        if not button.is_visible():
                            continue
                        label = re.sub(
                            r"\s+",
                            " ",
                            safe_text(button),
                        ).strip().lower()
                        if label in {"month", "year"}:
                            date_count += 1

                    if date_count >= 4:
                        return scope
                except Exception:
                    break
    except Exception:
        pass

    return None


def fill_education_editor(page: Page):
    """Fix only the SSC/High School education entry.

    The B.Tech and Intermediate entries are already correct and must not be
    touched. The SSC entry is identified by its existing school name rather
    than by its position in the education list.
    """
    try:
        scope = _find_ssc_education_scope(page)

        if scope is None:
            # Preserve the older dialog-based route as a fallback, but only
            # when the existing school value exactly matches the SSC school.
            dialogs = page.get_by_role("dialog")

            for i in range(dialogs.count()):
                dialog = dialogs.nth(i)
                if not dialog.is_visible():
                    continue

                text = safe_text(dialog).lower()
                if "edit education" not in text:
                    continue

                school_value = ""
                inputs = dialog.locator("input, textarea")

                for j in range(inputs.count()):
                    element = inputs.nth(j)
                    if not element.is_visible():
                        continue

                    metadata = _field_metadata(element)
                    if not any(
                        pattern in metadata
                        for pattern in (
                            "school",
                            "school name",
                            "institution",
                        )
                    ):
                        continue

                    try:
                        school_value = element.input_value().strip()
                    except Exception:
                        school_value = safe_text(element).strip()

                    if school_value:
                        break

                normalized_school = re.sub(
                    r"\s+",
                    " ",
                    school_value,
                ).strip().lower()

                normalized_ssc = re.sub(
                    r"\s+",
                    " ",
                    SSC_SCHOOL_NAME,
                ).strip().lower()

                if normalized_school == normalized_ssc:
                    scope = dialog
                    break

        if scope is None:
            return False

        print()
        print("SSC / High School education entry detected.")
        print(f"SSC school matched: {SSC_SCHOOL_NAME}")
        print("B.Tech and Intermediate entries are not modified.")

        # SSC-only fields. School name and degree are deliberately not
        # changed because they are already correct.
        major_filled = _fill_ssc_major_field(
            scope,
            SSC_FIELD_OF_STUDY,
        )

        selected_dates = _select_education_date_dropdowns(
            scope,
            [
                SSC_START_MONTH,
                SSC_START_YEAR,
                SSC_END_MONTH,
                SSC_END_YEAR,
            ],
        )

        if major_filled:
            print(f"SSC field of study set: {SSC_FIELD_OF_STUDY}")
        else:
            print(
                "SSC field of study was already populated or could not be filled."
            )

        print(
            f"SSC education date dropdowns selected: "
            f"{selected_dates}/4"
        )
        print(
            f"SSC education dates configured: "
            f"{SSC_START_MONTH}/{SSC_START_YEAR} - "
            f"{SSC_END_MONTH}/{SSC_END_YEAR}"
        )

        return True

    except Exception as e:
        print(f"SSC education handling error: {e}")

    return False


# ============================================================
# Fill Common Text Fields
# ============================================================

def _field_metadata(element):
    return " ".join([
        safe_attribute(element, "placeholder"),
        safe_attribute(element, "aria-label"),
        safe_attribute(element, "name"),
        safe_attribute(element, "id"),
    ]).lower()


def _value_for_text_question(combined):
    """
    Return the configured candidate value for a known text question.

    Matching is intentionally conservative: only recognizable question
    metadata is mapped. Unknown fields return None and are never guessed.
    """
    q = (combined or "").lower()

    # Compensation / availability
    if (
        "current salary" in q
        or "current annual salary" in q
        or "current annual ctc" in q
        or "current ctc" in q
        or "current compensation" in q
    ):
        return CURRENT_CTC

    if (
        "expected annual ctc" in q
        or "expected ctc" in q
        or "expected salary" in q
        or "expected compensation" in q
    ):
        return EXPECTED_CTC

    if "notice period" in q:
        return NOTICE_PERIOD

    # Experience
    if (
        "years of experience" in q
        or "years experience" in q
        or "total experience" in q
        or "professional experience" in q
        or "dsgn experience" in q
    ):
        # Confirmed by the user: DSGN experience should be entered as 0.
        if "dsgn experience" in q:
            return "0"
        return YEARS_OF_EXPERIENCE

    # Education
    if "degree" in q or "highest qualification" in q:
        return DEGREE

    if (
        "field of study" in q
        or "specialization" in q
        or "specialisation" in q
        or "major" in q
    ):
        return FIELD_OF_STUDY

    if (
        "university" in q
        or "college" in q
        or "institution" in q
    ):
        return UNIVERSITY

    if (
        "graduation year" in q
        or "year graduated" in q
        or "year of graduation" in q
    ):
        return GRADUATION_YEAR

    if (
        "cgpa" in q
        or "gpa" in q
        or "percentage" in q
    ):
        return CGPA

    # Location
    if "city" in q:
        return CITY

    if "state" in q:
        return STATE

    if "country" in q:
        return COUNTRY

    # LinkedIn profile URL
    if "linkedin profile" in q or "linkedin url" in q or ("profile" in q and "linkedin" in q):
        return LINKEDIN_PROFILE_URL

    # Technical experience fields.
    aliases = {
        "spring mvc": ["spring mvc"],
        "spring boot": ["spring boot", "springboot"],
        "hibernate": ["hibernate"],
        "jpa": ["jpa", "java persistence"],
        "maven": ["maven"],
        "junit": ["junit"],
        "mockito": ["mockito"],
        "postman": ["postman"],
        "microservices": ["microservices", "micro-services"],
        "rest api": ["rest api", "restful api"],
        "github": ["github"],
        "git": ["git"],
        "mysql": ["mysql", "my sql"],
        "sql": ["sql"],
        "nosql": ["nosql", "no sql"],
        "aws": ["aws", "amazon web services"],
        "docker": ["docker"],
        "linux": ["linux", "unix"],
        "java": ["java"],
    }

    if "experience" in q:
        for key, words in aliases.items():
            if any(word in q for word in words):
                return TECH_EXPERIENCE[key]

    return None


def _candidate_values_for_field(element, value, combined):
    """Return safe representations for common numeric/text LinkedIn fields."""
    raw = str(value or "").strip()
    q = (combined or "").lower()
    candidates = [raw]

    if "expected" in q and ("ctc" in q or "salary" in q):
        # 5 LPA means INR 500,000 annually. Prefer a numeric value for
        # number inputs and fall back to the configured text value.
        digits = re.sub(r"[^0-9.]", "", raw)
        if digits:
            try:
                n = float(digits)
                if n < 1000 and ("lpa" in raw.lower() or "lakh" in raw.lower()):
                    n *= 100000
                numeric = str(int(n)) if n.is_integer() else str(n)
                candidates.insert(0, numeric)
            except Exception:
                pass
        candidates.extend(["500000", "5"] )

    if "notice" in q and "period" in q:
        # Immediate is 0 days when the field requires a number.
        if raw.lower() in {"immediate", "immediately", "0 days", "0 day"}:
            candidates.insert(0, "0")
        candidates.extend(["0", "Immediate"])

    # De-duplicate while preserving priority.
    out = []
    for candidate in candidates:
        candidate = str(candidate).strip()
        if candidate and candidate not in out:
            out.append(candidate)
    return out


def _fill_value_and_validate(element, value, combined):
    """Fill a field and verify browser constraint validity before continuing."""
    for candidate in _candidate_values_for_field(element, value, combined):
        try:
            element.fill(candidate)
            page = element.page
            page.wait_for_timeout(150)
            valid = element.evaluate("el => !el.validity || el.validity.valid")
            if valid:
                return candidate
            # Try the next representation if browser validation rejects it.
            element.fill("")
        except Exception:
            try:
                element.fill("")
            except Exception:
                pass
    return None


def audit_configured_text_fields(container):
    """
    Report which configured text-field questions are visible on the current
    page and whether they are populated.

    This is diagnostic only. It does not guess or modify unknown fields.
    """
    print()
    print("Configured text-field audit:")

    fields = container.locator("input, textarea")
    found = 0

    for i in range(fields.count()):
        try:
            element = fields.nth(i)
            field_type = safe_attribute(element, "type").lower()

            if field_type in {
                "hidden", "file", "radio", "checkbox",
                "submit", "button", "password"
            }:
                continue

            if not element.is_visible():
                continue

            combined = _field_metadata(element)
            value = _value_for_text_question(combined)

            if value is None:
                continue

            found += 1

            current = ""
            try:
                current = element.input_value().strip()
            except Exception:
                pass

            label = combined[:100] or "<field metadata unavailable>"

            if current:
                print(f"  ✓ Present/populated: {label} -> {current}")
            else:
                print(f"  ! Known field empty: {label} -> expected {value}")

        except Exception:
            continue

    if found == 0:
        print("  No configured text fields detected on this page.")

    return found


def _select_location_autocomplete(element, value):
    """Select a visible LinkedIn location suggestion after filling a location field."""
    try:
        page = element.page
        target = str(value or "").strip().lower()
        if not target:
            return False

        # LinkedIn renders the location suggestions asynchronously.
        page.wait_for_timeout(700)

        selectors = [
            "[role='option']:visible",
            "[role='listbox']:visible [role='option']",
            "[role='listbox']:visible li",
        ]

        candidates = []
        seen = set()

        for selector in selectors:
            try:
                options = page.locator(selector)
                for i in range(options.count()):
                    option = options.nth(i)
                    if not option.is_visible():
                        continue

                    text = safe_text(option).strip()
                    if not text:
                        continue

                    identity = text.lower()
                    if identity in seen:
                        continue
                    seen.add(identity)

                    low = identity
                    if target == low:
                        candidates.insert(0, option)
                    elif target in low:
                        candidates.append(option)
            except Exception:
                continue

        if not candidates:
            print("No visible location autocomplete suggestion found.")
            return False

        suggestion = candidates[0]
        suggestion_text = safe_text(suggestion).strip()

        try:
            suggestion.scroll_into_view_if_needed()
        except Exception:
            pass

        page.wait_for_timeout(200)

        try:
            suggestion.click(timeout=5000)
            page.wait_for_timeout(300)
            print(f"Selected location suggestion: {suggestion_text}")
            return True
        except Exception as click_error:
            print(f"Location suggestion click failed: {click_error}")

        # Keyboard fallback is used only after a matching visible suggestion
        # has been confirmed. It is not used when no suggestion is present.
        try:
            element.press("ArrowDown")
            page.wait_for_timeout(100)
            element.press("Enter")
            page.wait_for_timeout(300)
            print(f"Selected location suggestion with keyboard: {suggestion_text}")
            return True
        except Exception as keyboard_error:
            print(f"Location autocomplete keyboard selection failed: {keyboard_error}")
            return False

    except Exception as e:
        print(f"Location autocomplete selection skipped: {e}")
        return False


def fill_common_text_fields(container):
    print()
    print("Checking common application fields...")

    fields = container.locator("input, textarea")
    filled_count = 0

    for i in range(fields.count()):
        try:
            element = fields.nth(i)
            field_type = safe_attribute(element, "type").lower()

            if field_type in {"hidden", "file", "radio", "checkbox", "submit", "button", "password"}:
                continue
            if not element.is_visible():
                continue

            current = ""
            try:
                current = element.input_value().strip()
            except Exception:
                pass
            if current:
                continue

            combined = _field_metadata(element)
            value = _value_for_text_question(combined)

            if value is not None:
                # Only fill an empty field; then verify native HTML validity.
                filled_value = _fill_value_and_validate(element, value, combined)
                if filled_value is not None:
                    print(f"Filled field: {combined[:100]} -> {filled_value}")

                    # LinkedIn location inputs can leave an autocomplete portal
                    # open after text entry. Commit a matching suggestion before
                    # navigation so that the suggestion overlay does not block
                    # the Next control. Unknown fields are never touched.
                    location_question = any(
                        word in combined.lower()
                        for word in (
                            "city",
                            "location",
                            "current location",
                            "address",
                        )
                    )

                    if location_question:
                        _select_location_autocomplete(element, filled_value)

                    filled_count += 1
                else:
                    print(
                        f"Could not find a valid representation for: "
                        f"{combined[:100]}"
                    )

        except Exception:
            continue

    print(f"Known text application answers filled: {filled_count}")
    audit_configured_text_fields(container)
    return filled_count


# ============================================================
# Handle Radio Buttons
# ============================================================

def _radio_controls(group):
    """Return the actual radio controls belonging to one radio group."""
    try:
        role_radios = group.locator("[role='radio']")
        if role_radios.count() > 0:
            return role_radios
    except Exception:
        pass
    try:
        return group.locator("input[type='radio']")
    except Exception:
        return group.locator("input[type='radio']")


def _radio_label_text(container, radio):
    """Return the visible answer label for native or custom radio controls.

    LinkedIn custom radios may expose the QUESTION as aria-label while the
    actual answer (for example Yes/No) is rendered as child text. Prefer that
    visible child text when it is available.
    """
    try:
        text = safe_text(radio).strip()
        if text and len(text) <= 120:
            return text
    except Exception:
        pass

    radio_id = safe_attribute(radio, "id")
    if radio_id:
        try:
            label = container.locator(f"label[for='{radio_id}']").first
            if label.count() > 0:
                text = safe_text(label)
                if text:
                    return text
        except Exception:
            pass

    aria_label = safe_attribute(radio, "aria-label").strip()
    if aria_label:
        return aria_label

    for xpath in [
        "xpath=ancestor::label[1]",
        "xpath=parent::*",
        "xpath=following-sibling::*[1]",
    ]:
        try:
            item = radio.locator(xpath).first
            if item.count() > 0:
                text = safe_text(item)
                if text and len(text) <= 120:
                    return text
        except Exception:
            continue

    return safe_text(radio)


def _click_radio_answer(group, answer):
    """Click a radio option only when its label exactly/clearly matches."""
    if group is None or not answer:
        return False

    target = re.sub(r"\s+", " ", str(answer)).strip().lower()

    try:
        controls = _radio_controls(group)
        for i in range(controls.count()):
            radio = controls.nth(i)

            try:
                label = _radio_label_text(group, radio)
            except Exception:
                label = ""

            label_normalized = re.sub(
                r"\s+", " ", str(label or "")
            ).strip().lower()

            if not label_normalized:
                continue

            if (
                label_normalized != target
                and target not in label_normalized
            ):
                continue

            try:
                if radio.is_checked():
                    return True
            except Exception:
                if safe_attribute(radio, "aria-checked").lower() == "true":
                    return True

            try:
                radio.scroll_into_view_if_needed()
            except Exception:
                pass

            try:
                radio.click(timeout=5000)
            except Exception:
                try:
                    radio.evaluate("(el) => el.click()")
                except Exception:
                    radio_id = safe_attribute(radio, "id")
                    if radio_id:
                        try:
                            label_element = group.locator(
                                f"label[for='{radio_id}']"
                            ).first
                            if label_element.count() > 0:
                                label_element.click(timeout=5000)
                            else:
                                continue
                        except Exception:
                            continue
                    else:
                        continue

            group.page.wait_for_timeout(150)

            try:
                if radio.is_checked():
                    return True
            except Exception:
                if safe_attribute(radio, "aria-checked").lower() == "true":
                    return True

    except Exception:
        pass

    return False


def _radio_question_container_from_text(container, question_patterns):
    """Find the exact radio group associated with a known question.

    Do not walk arbitrary ancestors looking for two radios: a LinkedIn form
    can contain multiple radio groups inside one shared wrapper. Instead,
    inspect each radiogroup independently and derive its own question text.
    """
    try:
        groups = container.locator("fieldset[role='radiogroup'], [role='radiogroup']")
        for i in range(groups.count()):
            group = groups.nth(i)
            if not group.is_visible():
                continue

            controls = _radio_controls(group)
            if controls.count() < 2:
                continue

            question = _radio_question_text(group).lower()
            if question and any(pattern.lower() in question for pattern in question_patterns):
                return group
    except Exception:
        pass

    return None


def _find_preferred_work_location_group(container):
    """Find the preferred-work-location radio group when ARIA grouping is absent."""
    try:
        question_nodes = container.locator(
            "text=/preferred work location|prefer to work|preferred location/i"
        )

        for i in range(question_nodes.count()):
            node = question_nodes.nth(i)
            if not node.is_visible():
                continue

            current = node
            for _ in range(10):
                try:
                    current = current.locator("xpath=..")
                    if current.count() == 0 or not current.is_visible():
                        break

                    group_text = re.sub(
                        r"\s+",
                        " ",
                        safe_text(current),
                    ).strip().lower()

                    if not any(
                        phrase in group_text
                        for phrase in (
                            "preferred work location",
                            "prefer to work",
                            "preferred location",
                        )
                    ):
                        continue

                    controls = _radio_controls(current)
                    if controls.count() >= 2:
                        return current
                except Exception:
                    break
    except Exception:
        pass

    return None


def _choose_preferred_work_location(group):
    """Choose Bengaluru/Bangalore, then Hyderabad, then Chennai if offered."""
    if group is None:
        return None

    priorities = (
        "bengaluru",
        "bangalore",
        "hyderabad",
        "chennai",
    )

    try:
        controls = _radio_controls(group)
        available = []

        for i in range(controls.count()):
            radio = controls.nth(i)
            if not radio.is_visible():
                continue

            label = _radio_label_text(group, radio).strip()
            if label:
                available.append(label)

        for keyword in priorities:
            for label in available:
                if keyword in label.lower():
                    return label
    except Exception:
        pass

    return None


def _answer_known_radio_questions(container):
    """Answer known LinkedIn radio questions by their actual question text."""
    known = [
        (
            ["bachelor's degree", "bachelors degree", "bachelor degree",
             "completed the following level of education"],
            BACHELORS_COMPLETED,
            "Bachelor's Degree completed",
        ),
        (
            ["are you a fresher", "are you fresher", "fresher"],
            FRESHER,
            "Are you a fresher",
        ),
    ]

    answered = 0
    failures = 0

    for patterns, answer, display_name in known:
        wrapper = _radio_question_container_from_text(container, patterns)
        if wrapper is None:
            continue

        if _click_radio_answer(wrapper, answer):
            print(f"Selected safe answer: {display_name} -> {answer}")
            answered += 1
        else:
            print(f"Could not select safe answer: {display_name} -> {answer}")
            failures += 1

    # Preferred work location:
    # Priority is Bengaluru/Bangalore first, Hyderabad second, Chennai third.
    # If none of these three locations is offered, do not guess another
    # location. This question is handled only when its own question text can
    # be identified, so unrelated radio groups are never affected.
    preferred_location_group = _radio_question_container_from_text(
        container,
        ["preferred work location", "prefer to work", "preferred location"],
    )

    if preferred_location_group is None:
        preferred_location_group = _find_preferred_work_location_group(
            container
        )

    if preferred_location_group is not None:
        preferred_answer = _choose_preferred_work_location(
            preferred_location_group
        )

        if preferred_answer and _click_radio_answer(
            preferred_location_group,
            preferred_answer,
        ):
            print(
                f"Selected preferred work location: {preferred_answer}"
            )
            answered += 1
        elif preferred_answer:
            print(
                f"Could not select preferred work location: "
                f"{preferred_answer}"
            )
            failures += 1
        else:
            print(
                "No Bengaluru/Bangalore, Hyderabad, or Chennai option "
                "was offered; preferred location left unchanged."
            )

    return answered, failures


def _radio_question_text(group_container):
    """Extract the question text belonging only to one radio group."""
    if group_container is None:
        return ""

    try:
        # Prefer explicit accessibility relationships when present.
        for attr in ("aria-labelledby", "aria-describedby"):
            ids = safe_attribute(group_container, attr).strip()
            if ids:
                parts = []
                for token in ids.split():
                    try:
                        ref = group_container.locator(f"#{token}").first
                        if ref.count() > 0:
                            text = safe_text(ref).strip()
                            if text:
                                parts.append(text)
                    except Exception:
                        continue
                if parts:
                    text = " ".join(parts)
                    if "required" not in text.lower():
                        return re.sub(r"\s+", " ", text).strip()

        # A legend is the most reliable semantic question label.
        try:
            legend = group_container.locator("legend").first
            if legend.count() > 0 and legend.is_visible():
                text = safe_text(legend).strip()
                if text:
                    return re.sub(r"\s+", " ", text).strip()
        except Exception:
            pass

        # For LinkedIn custom groups, visible text usually appears as:
        # question, option, option. Remove the actual option labels.
        controls = _radio_controls(group_container)
        option_texts = []
        for i in range(controls.count()):
            label = _radio_label_text(group_container, controls.nth(i)).strip()
            if label:
                option_texts.append(label.lower())

        text = safe_text(group_container)
        if not text:
            return ""

        lines = [re.sub(r"\s+", " ", x).strip() for x in text.splitlines() if x.strip()]
        for line in lines:
            low = line.lower()
            if low in option_texts:
                continue
            if low in {"yes", "no", "true", "false"}:
                continue
            if low in {"this field is required", "field is required"}:
                continue
            if line:
                return line

        return lines[0] if lines else ""
    except Exception:
        return ""


def _choose_safe_radio_answer(question, answers):
    """
    Return a safe answer only when the question matches a known profile rule.

    Unknown questions return None and are handled by the required-question
    safety gate. No answer is guessed.
    """
    q = (question or "").lower()

    normalized = [
        (a, (a or "").strip().lower())
        for a in answers
    ]

    def find(value):
        value = value.lower()

        for label, low in normalized:
            if low == value:
                return label

        for label, low in normalized:
            if value in low:
                return label

        return None

    if any(x in q for x in [
        "authorized to work",
        "legally authorized",
        "right to work",
        "eligible to work",
        "work authorization"
    ]):
        return find(WORK_AUTHORIZED)

    if any(x in q for x in [
        "work permit",
        "valid permit",
        "permit for india"
    ]):
        return find(WORK_PERMIT)

    if any(x in q for x in [
        "require sponsorship",
        "need sponsorship",
        "future sponsorship",
        "visa sponsorship",
        "sponsor now",
        "sponsor in the future"
    ]):
        return find(REQUIRES_SPONSORSHIP)

    if any(x in q for x in [
        "willing to relocate",
        "willingness to relocate",
        "relocate for the role",
        "relocation"
    ]):
        return find(WILLING_TO_RELOCATE)

    if any(x in q for x in [
        "onsite",
        "on-site",
        "on site",
        "hybrid",
        "work from office"
    ]):
        return find(WILLING_ONSITE)

    if "commut" in q or "commute" in q:
        return find(WILLING_ONSITE)

    if "internship" in q:
        return find(INTERNSHIP_EXPERIENCE)

    if any(x in q for x in [
        "bachelor's degree",
        "bachelors degree",
        "bachelor degree",
        "completed the following level of education"
    ]):
        return find(BACHELORS_COMPLETED)

    if any(x in q for x in [
        "are you a fresher",
        "are you fresher",
        "fresher?",
        "fresh graduate",
        "recent graduate"
    ]):
        return find(FRESHER)

    # Known LinkedIn Yes/No question:
    # "Paste a link to code you have written*"
    if any(x in q for x in [
        "paste a link to code",
        "link to code you have written",
        "code you have written"
    ]):
        return find("Yes")

    if (
        "professional experience" in q
        or "previous professional experience" in q
    ):
        return find("No")

    if any(x in q for x in [
        "years of experience",
        "years experience"
    ]):
        for label, low in normalized:
            if (
                re.search(r"(^|\D)0(\D|$)", low)
                or "no experience" in low
                or "fresher" in low
            ):
                return label

            if "less than 1" in low or "0-1" in low:
                return label

    if "shift" in q:
        return find(SHIFT_COMFORT)

    if "weekend" in q:
        return find(WEEKEND_COMFORT)

    if "disab" in q:
        return find(DISABILITY)

    if (
        "criminal" in q
        or "conviction" in q
        or "offense" in q
        or "offence" in q
    ):
        return find(CRIMINAL_HISTORY)

    return None


def inspect_radio_buttons(container):
    """Answer known radio questions; block unknown required radio questions."""
    print()
    print("Checking radio buttons...")

    radios = container.locator("input[type='radio'], [role='radio']")
    total = radios.count()
    if total == 0:
        print("No radio buttons found.")
        return 0

    answered, failures = _answer_known_radio_questions(container)

    radios = container.locator("input[type='radio'], [role='radio']")
    print(f"Radio controls found: {radios.count()}")
    if answered:
        print(f"Known radio questions answered: {answered}")

    unresolved = failures
    seen = set()

    # Inspect each radiogroup independently. This prevents one question's
    # label/options from being paired with a neighboring question.
    groups = container.locator("fieldset[role='radiogroup'], [role='radiogroup']")
    processed_groups = 0

    for i in range(groups.count()):
        try:
            group = groups.nth(i)
            if not group.is_visible():
                continue

            controls = _radio_controls(group)
            if controls.count() < 2:
                continue

            processed_groups += 1
            question = _radio_question_text(group).strip()
            group_text = re.sub(r"\s+", " ", safe_text(group)).strip()
            if not question:
                question = group_text

            # A required marker can be on the question, the group, or its
            # validation message. Do not require the radio input itself to
            # carry [required].
            required_marker = bool(re.search(r"\*\s*$", question))
            required_marker = required_marker or bool(
                re.search(r"\*\s*$", group_text)
            )
            required_marker = required_marker or "this field is required" in group_text.lower()
            required_marker = required_marker or safe_attribute(group, "aria-required").lower() == "true"

            if not required_marker:
                # Unknown optional radio groups are intentionally skipped.
                continue

            key = re.sub(r"[^a-z0-9]+", " ", question.lower()).strip()
            if key in seen:
                continue
            seen.add(key)

            checked = False
            for j in range(controls.count()):
                try:
                    if controls.nth(j).is_checked():
                        checked = True
                        break
                except Exception:
                    if safe_attribute(controls.nth(j), "aria-checked").lower() == "true":
                        checked = True
                        break
            if checked:
                continue

            answers = []
            for j in range(controls.count()):
                label = _radio_label_text(group, controls.nth(j)).strip()
                if label and label not in answers:
                    answers.append(label)

            chosen = _choose_safe_radio_answer(question, answers)
            if chosen and _click_radio_answer(group, chosen):
                print(f"Selected safe answer: {question} -> {chosen}")
                continue

            print()
            print("UNKNOWN REQUIRED RADIO QUESTION DETECTED.")
            print("QUESTION:", question)
            print("ANSWERS:")
            for answer in answers:
                print("  -", answer)
            print("Automation will STOP here.")
            print("No answer was guessed.")
            unresolved += 1

        except Exception:
            continue

    if processed_groups == 0:
        # Preserve the safety behavior if a site exposes radios without a
        # semantic radiogroup container: do not guess anything.
        print("Radio groups could not be identified semantically.")

    if unresolved == 0:
        print("All radio questions were answered safely.")
    else:
        print(f"Unknown required radio questions blocking navigation: {unresolved}")

    return unresolved


def inspect_checkboxes(container):

    print()
    print(
        "Checking checkboxes..."
    )

    checkboxes = container.locator(
        "input[type='checkbox']"
    )

    if checkboxes.count() == 0:

        print(
            "No checkboxes found."
        )

        return

    print(
        f"Checkboxes found: "
        f"{checkboxes.count()}"
    )

    for i in range(
        checkboxes.count()
    ):

        try:

            checkbox = checkboxes.nth(i)

            if not checkbox.is_visible():
                continue

            print()
            print(
                f"CHECKBOX {i + 1}"
            )

            print(
                "Name:",
                safe_attribute(
                    checkbox,
                    "name"
                )
            )

            print(
                "ID:",
                safe_attribute(
                    checkbox,
                    "id"
                )
            )

            print(
                "Checked:",
                checkbox.is_checked()
            )

        except Exception:
            pass


# ============================================================
# Handle Selects
# ============================================================

def inspect_selects(container):

    print()
    print(
        "Checking dropdowns..."
    )

    selects = container.locator(
        "select"
    )

    if selects.count() == 0:

        print(
            "No native dropdowns found."
        )

        return

    print(
        f"Dropdowns found: "
        f"{selects.count()}"
    )

    for i in range(
        selects.count()
    ):

        try:

            select = selects.nth(i)

            if not select.is_visible():
                continue

            print()
            print(
                f"DROPDOWN {i + 1}"
            )

            print(
                "Name:",
                safe_attribute(
                    select,
                    "name"
                )
            )

            print(
                "ID:",
                safe_attribute(
                    select,
                    "id"
                )
            )

            options = select.locator(
                "option"
            )

            option_texts = []
            for j in range(options.count()):
                option_texts.append(safe_text(options.nth(j)).strip())

            # Safe known experience values for this fresher profile.
            # Only act when the dropdown explicitly exposes the matching
            # zero-year/zero-month option; unknown dropdowns are untouched.
            normalized_options = {text.lower() for text in option_texts}
            if "0 year" in normalized_options:
                try:
                    zero_year = options.nth(
                        option_texts.index("0 year")
                    )
                    value = safe_attribute(zero_year, "value")
                    if value:
                        select.select_option(value=value)
                    else:
                        select.select_option(label="0 year")
                    print("Selected experience: 0 year")
                except Exception as e:
                    print(f"Could not select 0 year: {e}")

            elif "0 month" in normalized_options:
                try:
                    zero_month = options.nth(
                        option_texts.index("0 month")
                    )
                    value = safe_attribute(zero_month, "value")
                    if value:
                        select.select_option(value=value)
                    else:
                        select.select_option(label="0 month")
                    print("Selected experience: 0 month")
                except Exception as e:
                    print(f"Could not select 0 month: {e}")

            for j in range(
                min(options.count(), 15)
            ):

                option = options.nth(j)

                print(
                    "  -",
                    safe_text(option)
                )

        except Exception:
            pass


# ============================================================
# Inspect Required Fields
# ============================================================

def inspect_required_fields(container):

    print()
    print(
        "=" * 70
    )

    print(
        "CHECKING REQUIRED FIELDS"
    )

    print(
        "=" * 70
    )

    required = container.locator(
        "[required]"
    )

    print(
        f"Required elements found: "
        f"{required.count()}"
    )

    unanswered = 0

    for i in range(
        required.count()
    ):

        try:

            element = required.nth(i)

            tag = element.evaluate(
                "(el) => el.tagName"
            )

            field_type = (
                safe_attribute(
                    element,
                    "type"
                ).lower()
            )

            if field_type in [
                "hidden"
            ]:

                continue

            # Radio groups: consider the group answered when any
            # radio in the same name group is checked.
            if field_type == "radio":

                group_name = safe_attribute(
                    element,
                    "name"
                )

                if group_name:
                    try:
                        checked = container.locator(
                            f"input[type='radio'][name='{group_name}']:checked"
                        )

                        if checked.count() > 0:
                            continue
                    except Exception:
                        pass

                if element.is_checked():
                    continue

            # Checkbox: required means it must be checked.
            if field_type == "checkbox":

                if element.is_checked():
                    continue

                value = ""
            else:

                value = ""

                try:

                    value = (
                        element
                        .input_value()
                        .strip()
                    )

                except Exception:
                    pass

                # Native select.
                if tag == "SELECT":
                    try:
                        value = (
                            element
                            .input_value()
                            .strip()
                        )
                    except Exception:
                        pass

            invalid = False
            validation_message = ""
            try:
                if field_type not in {"radio", "checkbox"} and element.is_visible():
                    invalid = not element.evaluate("el => !el.validity || el.validity.valid")
                    if invalid:
                        validation_message = element.evaluate("el => el.validationMessage || ''") or "Invalid input"
            except Exception:
                pass

            if not value or invalid:

                unanswered += 1

                print()
                print(
                    f"REQUIRED FIELD "
                    f"{unanswered}"
                )

                print(
                    "Tag:",
                    tag
                )

                print(
                    "Type:",
                    field_type
                )

                print(
                    "Name:",
                    safe_attribute(
                        element,
                        "name"
                    )
                )

                print(
                    "ID:",
                    safe_attribute(
                        element,
                        "id"
                    )
                )

                print(
                    "Placeholder:",
                    safe_attribute(
                        element,
                        "placeholder"
                    )
                )

                print(
                    "Aria:",
                    safe_attribute(
                        element,
                        "aria-label"
                    )
                )

                if invalid:
                    print(
                        "Validation:",
                        validation_message
                    )

        except Exception:
            pass

    print()

    if unanswered == 0:

        print(
            "No empty required fields detected."
        )

    else:

        print(
            f"Empty required fields: "
            f"{unanswered}"
        )

    return unanswered


# ============================================================
# Find Application Navigation Controls
# ============================================================

def _control_text(element):
    """Return the useful accessible/text attributes of a control."""
    parts = []
    for attr in ("aria-label", "title", "data-control-name", "name"):
        value = safe_attribute(element, attr).strip()
        if value:
            parts.append(value)
    text = safe_text(element).strip()
    if text:
        parts.append(text)
    return " ".join(parts).strip().lower()


def _find_button_in_scope(scope, purpose="next"):
    """Find a navigation control using several LinkedIn DOM variants."""
    if purpose == "submit":
        patterns = [
            r"\bsubmit\b",
            r"submit\s+application",
            r"send\s+application",
        ]
        reject = ("search", "job", "profile", "similar", "notification")
    else:
        patterns = [
            r"^next$",
            r"^continue$",
            r"^review$",
            r"\bnext\s*(step|page)?\b",
            r"\bcontinue\s*(to\s*)?(next\s*)?(step|page)?\b",
            r"\breview\s*(application|your application)?\b",
        ]
        reject = ("search", "job", "profile", "similar", "notification", "save")

    # Prefer explicit LinkedIn application attributes when available.
    selectors = [
        '[data-easy-apply-next-button]',
        '[data-control-name*="easy_apply" i]',
        '[data-control-name*="continue" i]',
        '[data-control-name*="next" i]',
        '[data-control-name*="review" i]',
        'button',
        '[role="button"]',
    ]

    candidates = []
    seen = set()

    for selector in selectors:
        try:
            locator = scope.locator(selector)
            for i in range(locator.count()):
                element = locator.nth(i)
                try:
                    if not element.is_visible():
                        continue
                    key = None
                    try:
                        key = element.evaluate("e => e")
                    except Exception:
                        key = f"{selector}:{i}"
                    # Locator identity cannot reliably be hashed, so use DOM attributes.
                    identity = (
                        safe_attribute(element, "data-control-name"),
                        safe_attribute(element, "aria-label"),
                        safe_attribute(element, "id"),
                        safe_text(element)[:120],
                    )
                    if identity in seen:
                        continue
                    seen.add(identity)

                    combined = _control_text(element)
                    if not combined:
                        continue
                    if any(word in combined for word in reject):
                        continue
                    if not any(re.search(pattern, combined, re.IGNORECASE) for pattern in patterns):
                        continue

                    score = 0
                    if "data-easy-apply-next-button" in selector:
                        score += 100
                    if "data-control-name" in selector:
                        score += 40
                    if purpose == "submit" and "submit" in combined:
                        score += 30
                    if purpose != "submit" and re.search(r"\b(next|continue|review)\b", combined):
                        score += 30
                    if safe_attribute(element, "type").lower() == "submit":
                        score += 5
                    if safe_attribute(element, "class") and "artdeco-button" in safe_attribute(element, "class"):
                        score += 5

                    try:
                        if not element.is_enabled():
                            continue
                    except Exception:
                        pass

                    candidates.append((score, element, combined))
                except Exception:
                    continue
        except Exception:
            continue

    if candidates:
        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[0][1]

    return None


def find_next_button(container, page=None):
    """Find LinkedIn's application navigation button in the modal or page."""
    button = _find_button_in_scope(container, "next")
    if button is not None:
        return button

    if page is not None and container is not page:
        button = _find_button_in_scope(page, "next")
        if button is not None:
            print("Navigation button found in full page scope.")
            return button

    return None


# ============================================================
# Find Submit Button
# ============================================================

def find_submit_button(container, page=None):
    """Find the final submit control in the application scope."""
    button = _find_button_in_scope(container, "submit")
    if button is not None:
        return button

    if page is not None and container is not page:
        button = _find_button_in_scope(page, "submit")
        if button is not None:
            print("Submit button found in full page scope.")
            return button

    return None


# ============================================================
# Detect Closed Job
# ============================================================

def job_is_closed(page):

    try:

        body = page.locator(
            "body"
        ).inner_text().lower()

        closed_messages = [

            "no longer accepting applications",
            "job is no longer accepting applications",
            "this job is no longer available",
            "applications are closed",
            "job has been closed"

        ]

        for message in closed_messages:

            if message in body:

                return True

    except Exception:
        pass

    return False


# ============================================================
# Prepare Current Application Page
# ============================================================

def prepare_current_page(page: Page):

    print()
    print(
        "=" * 70
    )

    print(
        "PREPARING APPLICATION PAGE"
    )

    print(
        "=" * 70
    )

    print_application_status(page)

    container = get_application_container(
        page
    )

    # --------------------------------------------------------
    # Education editor
    # --------------------------------------------------------

    fill_education_editor(page)

    # --------------------------------------------------------
    # Contact information
    # --------------------------------------------------------

    fill_name(
        container
    )

    fill_email(
        container
    )

    fill_phone(
        container
    )

    # --------------------------------------------------------
    # Resume
    # --------------------------------------------------------

    upload_resume(
        container
    )

    # --------------------------------------------------------
    # Common fields
    # --------------------------------------------------------

    fill_common_text_fields(
        container
    )

    # --------------------------------------------------------
    # Other controls
    # --------------------------------------------------------

    unresolved_radios = inspect_radio_buttons(
        container
    )

    inspect_checkboxes(
        container
    )

    inspect_selects(
        container
    )

    # --------------------------------------------------------
    # Required fields
    # --------------------------------------------------------

    unanswered = (
        inspect_required_fields(
            container
        )
    )

    # Unknown optional radio questions are skipped. Unknown required radio
    # questions return a blocking count and therefore stop navigation.
    if unresolved_radios > 0:
        print(
            f"Unknown required radio questions blocking navigation: "
            f"{unresolved_radios}"
        )

    # Radio questions are part of the required-field safety gate.
    return unanswered + unresolved_radios


# ============================================================
# Move To Next Page
# ============================================================

def _form_fingerprint(page):
    """Capture stable form content without treating UI/portal changes as navigation."""
    try:
        container = get_application_container(page)

        # Prefer the visible question/field content inside the application form.
        elements = container.locator(
            "input, textarea, select, [role='combobox'], "
            "[role='radio'], [role='checkbox'], label"
        )

        parts = []

        for i in range(elements.count()):
            try:
                element = elements.nth(i)

                if not element.is_visible():
                    continue

                tag = element.evaluate("(el) => el.tagName").lower()

                if tag in {"input", "textarea", "select"}:
                    value = element.input_value(timeout=1000)
                    aria = element.get_attribute("aria-label") or ""
                    name = element.get_attribute("name") or ""
                    parts.append(f"{tag}|{aria}|{name}|{value}")

                else:
                    text = element.inner_text(timeout=1000).strip()
                    aria = element.get_attribute("aria-label") or ""
                    if text or aria:
                        parts.append(f"{tag}|{aria}|{text}")

            except Exception:
                continue

        # If no form controls were found, return empty rather than
        # treating arbitrary container/UI changes as a page transition.
        if not parts:
            return ""

        text = " || ".join(parts)

        # Remove dynamic counters and normalize whitespace.
        text = re.sub(r"\b\d+\s*/\s*\d+\b", "", text)
        text = re.sub(r"\s+", " ", text).strip().lower()

        return text

    except Exception:
        return ""


def move_to_next_page(page: Page):
    """Click application navigation once and verify a real transition."""
    container = get_application_container(page)
    before = get_application_step(page)

    # Only use fingerprint fallback when LinkedIn does not expose
    # a usable application page indicator.
    before_fingerprint = ""
    if not before:
        before_fingerprint = _form_fingerprint(page)

    button = find_next_button(container, page)

    if button is None:
        print()
        print("=" * 70)
        print("NEXT BUTTON NOT FOUND")
        print("=" * 70)
        print("No safe LinkedIn application navigation control was detected.")
        return False

    print(f"Navigation control: {_control_text(button)}")

    # Attempt 1: normal Playwright click
    try:
        button.scroll_into_view_if_needed()
        page.wait_for_timeout(300)
        button.click(timeout=10000)
        print("Next button clicked normally.")

    except Exception as normal_error:
        print(f"Normal Next click failed: {normal_error}")
        print("Trying safe fallback click...")

        # Attempt 2: DOM click fallback.
        # This is only for Next/navigation, never final Submit.
        try:
            button.evaluate("(element) => element.click()")
            print("Fallback Next click completed.")

        except Exception as fallback_error:
            print(f"Fallback Next click failed: {fallback_error}")
            return False

    # ------------------------------------------------------------
    # Verify actual transition
    # ------------------------------------------------------------
    for _ in range(30):
        page.wait_for_timeout(500)

        after = get_application_step(page)

        # If LinkedIn exposes the page indicator, require an actual
        # increase in the application page number.
        if before:
            if (
                after
                and after[1] == before[1]
                and after[0] > before[0]
            ):
                print(
                    f"Moved to next application page: "
                    f"{after[0]}/{after[1]}"
                )
                return True

            continue

        # Only use fingerprint comparison when there was no usable
        # page indicator before navigation.
        after_fingerprint = _form_fingerprint(page)

        if (
            before_fingerprint
            and after_fingerprint
            and after_fingerprint != before_fingerprint
        ):
            print("Application form content changed after navigation.")
            return True

    # ------------------------------------------------------------
    # Navigation did not actually advance
    # ------------------------------------------------------------
    current = get_application_step(page)

    print()
    print("=" * 70)
    print("APPLICATION PAGE DID NOT ADVANCE")
    print("=" * 70)

    if before:
        print(f"Before: {before[0]}/{before[1]}")

    if current:
        print(f"After : {current[0]}/{current[1]}")

    print("Stopping safely instead of clicking navigation repeatedly.")
    return False


def handle_final_submission(page: Page):
    """Never submit employment applications automatically.

    The form may be fully prepared, but final submission always requires
    explicit human action.
    """
    print()
    print("=" * 70)
    print("FINAL APPLICATION REVIEW REQUIRED")
    print("=" * 70)
    print("All detected required fields are filled.")
    print("AUTO_SUBMIT is disabled for safety.")
    print("No Submit button was clicked by automation.")
    print("Please review the application in the browser and submit manually if appropriate.")
    return False



def inspect_and_prepare_form(
    page: Page
):

    print()
    print(
        "=" * 70
    )

    print(
        "APPLICATION FORM AUTOMATION"
    )

    print(
        "=" * 70
    )

    if job_is_closed(page):

        print()
        print(
            "JOB IS CLOSED."
        )

        return False

    print()
    print(
        "Resume:",
        RESUME_PATH
    )

    print(
        "Auto Submit:",
        AUTO_SUBMIT
    )

    # --------------------------------------------------------
    # Process multiple application pages
    # --------------------------------------------------------

    max_pages = 10

    for page_number in range(
        1,
        max_pages + 1
    ):

        print()
        print(
            "=" * 70
        )

        print(
            f"PROCESSING APPLICATION PAGE "
            f"{page_number}"
        )

        print(
            "=" * 70
        )

        if job_is_closed(page):

            print(
                "Job/application is closed."
            )

            return False

        unanswered = (
            prepare_current_page(
                page
            )
        )

        # ----------------------------------------------------
        # If required fields remain unanswered
        # ----------------------------------------------------

        if unanswered > 0:

            print()
            print(
                "REQUIRED INFORMATION IS MISSING."
            )

            print(
                "Automation will stop here."
            )

            print(
                "Please inspect the fields above."
            )

            return False

        # ----------------------------------------------------
        # Check if Submit is already available
        # ----------------------------------------------------

        container = get_application_container(
            page
        )

        submit_button = find_submit_button(
            container,
            page
        )

        if submit_button is not None:

            print()
            print(
                "Final application page detected."
            )

            return handle_final_submission(
                page
            )

        # ----------------------------------------------------
        # Move to next page
        # ----------------------------------------------------

        navigation_button = find_next_button(
            container,
            page
        )

        if navigation_button is not None and re.search(
            r"\breview\b",
            _control_text(navigation_button),
            re.IGNORECASE,
        ):
            print()
            print("Review navigation detected.")
            print("Clicking Review once to enter the final review stage.")
            try:
                navigation_button.scroll_into_view_if_needed()
                page.wait_for_timeout(300)
                navigation_button.click(timeout=10000)
                page.wait_for_timeout(1500)
            except Exception as e:
                print(f"Could not open the review stage: {e}")
                return False

            print()
            print("=" * 70)
            print("FINAL APPLICATION REVIEW REQUIRED")
            print("=" * 70)
            print("All detected required fields are filled.")
            print("AUTO_SUBMIT is disabled for safety.")
            print("No Submit button will be clicked by automation.")
            return handle_final_submission(page)

        moved = move_to_next_page(
            page
        )

        if not moved:

            print()
            print(
                "Could not find another page."
            )

            print(
                "Stopping automation."
            )

            return False

        page.wait_for_timeout(
            1500
        )

    print()
    print(
        "Maximum application pages reached."
    )

    print(
        "Stopping automation for safety."
    )

    return False


# ============================================================
# End
# ============================================================

if __name__ == "__main__":

    print()
    print(
        "=" * 70
    )

    print(
        "APPLICATION FORM MODULE"
    )

    print(
        "=" * 70
    )

    print()
    print(
        "This module is called by easy_apply.py."
    )

    print(
        "Run easy_apply.py to start the application."
    )

    print()