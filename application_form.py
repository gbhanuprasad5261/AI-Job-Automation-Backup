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

AUTO_SUBMIT = os.getenv("AUTO_SUBMIT", "true").strip().lower() == "true"


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

        print(
            "PHONE is empty."
        )

        print(
            "Set APPLICANT_PHONE before running."
        )

        return False

    # Country code is handled separately because LinkedIn often uses
    # a custom control rather than a normal <select>.
    select_india_country_code(container)

    selectors = [

        "input[type='tel']",
        "input[name*='phone' i]",
        "input[id*='phone' i]",
        "input[autocomplete='tel']",

    ]

    for selector in selectors:

        try:

            locator = container.locator(selector)

            if locator.count() == 0:
                continue

            if fill_if_empty(
                locator,
                PHONE
            ):

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
    q = combined.lower()

    if "current annual ctc" in q or "current ctc" in q:
        return CURRENT_CTC
    if "expected annual ctc" in q or "expected ctc" in q:
        # LinkedIn frequently renders this as a numeric input.
        # Use the configured value and normalize it at fill time if needed.
        return EXPECTED_CTC
    if "notice period" in q:
        # Immediate is represented as 0 days for numeric fields.
        return NOTICE_PERIOD
    if "years of experience" in q or ("experience" in q and "years" in q):
        return YEARS_OF_EXPERIENCE

    if "degree" in q or "highest qualification" in q:
        return DEGREE
    if "field of study" in q or "specialization" in q or "major" in q:
        return FIELD_OF_STUDY
    if "university" in q or "college" in q or "institution" in q:
        return UNIVERSITY
    if "graduation year" in q or "year graduated" in q:
        return GRADUATION_YEAR
    if "cgpa" in q or "gpa" in q or "percentage" in q:
        return CGPA

    if "city" in q:
        return CITY
    if "state" in q:
        return STATE
    if "country" in q:
        return COUNTRY

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
                    filled_count += 1
                else:
                    print(f"Could not find a valid representation for: {combined[:100]}")

        except Exception:
            continue

    print(f"Known text application answers filled: {filled_count}")
    return filled_count


# ============================================================
# Handle Radio Buttons
# ============================================================

def _radio_label_text(container, radio):
    """Return the most useful visible answer label for a radio input."""
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

    try:
        parent = radio.locator("xpath=ancestor::label[1]").first
        if parent.count() > 0:
            text = safe_text(parent)
            if text:
                return text
    except Exception:
        pass

    try:
        # LinkedIn sometimes puts the visible answer text in a sibling/span.
        text = radio.locator("xpath=following-sibling::*[1]").first.inner_text().strip()
        if text:
            return text
    except Exception:
        pass

    return ""


def _radio_question_text(container, radio):
    """Find nearby text that represents the question for a radio group."""
    try:
        fieldset = radio.locator("xpath=ancestor::fieldset[1]").first
        if fieldset.count() > 0:
            legend = fieldset.locator("legend").first
            if legend.count() > 0:
                text = safe_text(legend)
                if text:
                    return text
            text = safe_text(fieldset)
            if text:
                return text
    except Exception:
        pass

    # Walk upward through a few likely LinkedIn question containers.
    for xpath in [
        "xpath=ancestor::*[self::div or self::li][.//input[@type='radio']][1]",
        "xpath=ancestor::*[self::div or self::section][.//input[@type='radio']][1]",
    ]:
        try:
            parent = radio.locator(xpath).first
            if parent.count() == 0:
                continue
            text = safe_text(parent)
            if text:
                # Keep it bounded so debug output remains readable.
                return text[:1200]
        except Exception:
            continue

    return ""


def _choose_safe_radio_answer(question, answers):
    q = (question or "").lower()
    normalized = [(a, (a or "").strip().lower()) for a in answers]

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
        "authorized to work", "legally authorized", "right to work",
        "eligible to work", "work authorization"
    ]):
        return find(WORK_AUTHORIZED)

    if any(x in q for x in [
        "work permit", "valid permit", "permit for india"
    ]):
        return find(WORK_PERMIT)

    if any(x in q for x in [
        "require sponsorship", "need sponsorship", "future sponsorship",
        "visa sponsorship", "sponsor now", "sponsor in the future"
    ]):
        return find(REQUIRES_SPONSORSHIP)

    if any(x in q for x in [
        "willing to relocate", "willingness to relocate",
        "relocate for the role", "relocation"
    ]):
        return find(WILLING_TO_RELOCATE)

    if any(x in q for x in ["onsite", "on-site", "on site", "hybrid", "work from office"]):
        return find(WILLING_ONSITE)

    if "internship" in q:
        return find(INTERNSHIP_EXPERIENCE)

    if "professional experience" in q or "previous professional experience" in q:
        return find("No")

    if any(x in q for x in ["years of experience", "years experience"]):
        for label, low in normalized:
            if re.search(r"(^|\D)0(\D|$)", low) or "no experience" in low or "fresher" in low:
                return label
            if "less than 1" in low or "0-1" in low:
                return label

    if "shift" in q:
        return find(SHIFT_COMFORT)
    if "weekend" in q:
        return find(WEEKEND_COMFORT)
    if "disab" in q:
        return find(DISABILITY)
    if "criminal" in q or "conviction" in q or "offense" in q or "offence" in q:
        return find(CRIMINAL_HISTORY)

    return None


def inspect_radio_buttons(container):
    """Inspect radio groups and safely answer only known questions.

    Returns the number of unknown radio groups that were skipped. Unknown
    questions are never guessed and do not block navigation; genuinely
    required unanswered fields are handled separately by validation.
    """
    print()
    print("Checking radio buttons...")

    radios = container.locator("input[type='radio']")
    total = radios.count()

    if total == 0:
        print("No radio buttons found.")
        return 0

    # Group by name; LinkedIn normally gives all answers in a question the same name.
    groups = {}
    unnamed = []

    for i in range(total):
        try:
            radio = radios.nth(i)
            if not radio.is_visible():
                continue
            name = safe_attribute(radio, "name").strip()
            if name:
                groups.setdefault(name, []).append(radio)
            else:
                unnamed.append(radio)
        except Exception:
            continue

    for radio in unnamed:
        groups.setdefault(f"__unnamed_{len(groups)}", []).append(radio)

    unresolved = 0

    print(f"Radio groups found: {len(groups)}")

    for group_index, group in enumerate(groups.values(), start=1):
        try:
            first = group[0]
            question = _radio_question_text(container, first)
            answers = [_radio_label_text(container, r) for r in group]
            answers = [a for a in answers if a]

            print()
            print(f"RADIO GROUP {group_index}")
            print("Question:", question or "Unknown")
            print("Answers:")
            for n, answer in enumerate(answers, start=1):
                print(f"  {n}. {answer}")

            chosen = _choose_safe_radio_answer(question, answers)

            if chosen:
                # Find the actual radio whose label matched the chosen answer.
                clicked = False
                for radio in group:
                    label = _radio_label_text(container, radio)
                    if label.strip().lower() == chosen.strip().lower():
                        try:
                            radio.check(force=True)
                            clicked = True
                            break
                        except Exception:
                            try:
                                radio.click(force=True)
                                clicked = True
                                break
                            except Exception:
                                pass

                if clicked:
                    print("Selected safe answer:", chosen)
                    continue

            # Unknown radio question:
            # Do NOT guess an answer. Leave it unchanged and continue.
            checked = any(
                radio.is_checked()
                for radio in group
            )

            if checked:
                print(
                    "WARNING: Unknown radio question already has "
                    "a selected option."
                )
                print(
                    "Leaving the existing selection unchanged."
                )
            else:
                print(
                    "Unknown radio question detected."
                )
                print(
                    "Skipping without selecting an answer."
                )

            print(
                "Unknown radio question skipped safely."
            )

            # Unknown questions must NOT block navigation.
            unresolved += 1
            continue

        except Exception as e:
            print(f"Could not inspect radio group: {e}")
            unresolved += 1

    print()
    if unresolved == 0:
        print("All radio questions were answered safely.")
    else:
        print(f"Unknown radio groups skipped: {unresolved}")
        print("Automation will continue without guessing answers.")

    return unresolved


# ============================================================
# Handle Checkboxes
# ============================================================

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

    # Unknown radio questions are intentionally skipped.
    # Only genuinely required fields block navigation.
    if unresolved_radios > 0:
        print(
            f"Skipped unknown radio groups: "
            f"{unresolved_radios}"
        )

    return unanswered


# ============================================================
# Move To Next Page
# ============================================================

def _form_fingerprint(page):
    """Capture stable application-form text to verify a real page transition."""
    try:
        container = get_application_container(page)
        text = container.inner_text()
        # Remove dynamic character counters such as 1/20 and whitespace noise.
        text = re.sub(r"\b\d+\s*/\s*\d+\b", "", text)
        text = re.sub(r"\s+", " ", text).strip().lower()
        return text
    except Exception:
        return ""


def move_to_next_page(page: Page):
    """Click application navigation once and verify a real transition."""
    container = get_application_container(page)
    before = get_application_step(page)
    before_fingerprint = _form_fingerprint(page)

    button = find_next_button(container, page)

    if button is None:
        print()
        print("=" * 70)
        print("NEXT BUTTON NOT FOUND")
        print("=" * 70)
        print("No safe LinkedIn application navigation control was detected.")
        return False

    try:
        print(f"Navigation control: {_control_text(button)}")
        button.scroll_into_view_if_needed()
        page.wait_for_timeout(300)
        button.click(timeout=10000)
    except Exception as e:
        print(f"Could not click navigation button: {e}")
        return False

    for _ in range(30):
        page.wait_for_timeout(500)
        after = get_application_step(page)

        if before and after and after[1] == before[1] and after[0] > before[0]:
            print(f"Moved to next application page: {after[0]}/{after[1]}")
            return True

        after_fingerprint = _form_fingerprint(page)
        if before_fingerprint and after_fingerprint and after_fingerprint != before_fingerprint:
            # Fingerprint change is accepted only when the application container changed.
            print("Application form content changed after navigation.")
            return True

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
    """Handle the final LinkedIn Easy Apply submission safely.

    Returns True only after a submit click is performed successfully.
    When AUTO_SUBMIT is disabled, the form is left ready for manual review.
    """

    container = get_application_container(page)
    submit_button = find_submit_button(container, page)

    if submit_button is None:
        print("Final submit button not found.")
        return False

    if not AUTO_SUBMIT:
        print()
        print("AUTO_SUBMIT is disabled.")
        print("Final application is READY_FOR_REVIEW.")
        return False

    try:
        if not submit_button.is_enabled():
            print("Final submit button is disabled.")
            return False
    except Exception:
        pass

    try:
        print()
        print("Submitting LinkedIn Easy Apply application...")
        submit_button.scroll_into_view_if_needed()
        page.wait_for_timeout(300)
        submit_button.click(timeout=10000)
    except Exception as e:
        print(f"Final submission click failed: {e}")
        return False

    page.wait_for_timeout(2500)

    # Confirm a success signal when LinkedIn exposes one. If the modal closes
    # or the submit control disappears, that is also treated as success.
    try:
        body = page.locator("body").inner_text().lower()
    except Exception:
        body = ""

    success_signals = (
        "application submitted",
        "your application was sent",
        "application has been submitted",
        "you applied",
        "application sent",
    )

    if any(signal in body for signal in success_signals):
        print("Application submitted successfully.")
        return True

    try:
        remaining = find_submit_button(get_application_container(page), page)
    except Exception:
        remaining = None

    if remaining is None:
        print("Submit control disappeared after click; application appears submitted.")
        return True

    print("Submission result could not be confirmed.")
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