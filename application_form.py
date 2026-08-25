import os
import re

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

try:
    from profile import PROFILE
except Exception:
    PROFILE = {}
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

# Prefer environment/profile values. Do not keep personal data hardcoded
# in the source when .env/profile.py is available.
_name = str(PROFILE.get("first_name", "")).strip() + " " + str(PROFILE.get("last_name", "")).strip()
APPLICANT_NAME = os.getenv("APPLICANT_NAME", _name.strip())
EMAIL = os.getenv("EMAIL", os.getenv("APPLICANT_EMAIL", "gbhanuprasad1236@gmail.com"))
PHONE = os.getenv("PHONE", os.getenv("APPLICANT_PHONE", "9392801041"))
YEARS_OF_EXPERIENCE = os.getenv(
    "YEARS_OF_EXPERIENCE",
    str(PROFILE.get("experience_years", "0"))
)
CITY = os.getenv("APPLICANT_CITY", str(PROFILE.get("city", "Bengaluru")).strip())
STATE = os.getenv("APPLICANT_STATE", str(PROFILE.get("state", "Karnataka")).strip())
COUNTRY = os.getenv("APPLICANT_COUNTRY", str(PROFILE.get("country", "India")).strip())
DEGREE = os.getenv("APPLICANT_DEGREE", str(PROFILE.get("degree", "B.Tech")).strip())
FIELD_OF_STUDY = os.getenv("APPLICANT_FIELD", str(PROFILE.get("field_of_study", "Computer Science and Engineer(AI&DS)")).strip())
GRADUATION_YEAR = os.getenv("GRADUATION_YEAR", str(PROFILE.get("graduation_year", "2025")).strip())

# Optional answers. Blank means: do not guess; stop for manual review.
APPLICATION_LANGUAGE = os.getenv("APPLICATION_LANGUAGE", "English")
WORK_AUTHORIZED = os.getenv("WORK_AUTHORIZED", "Yes")
REQUIRES_SPONSORSHIP = os.getenv("REQUIRES_SPONSORSHIP", "No")
WILLING_TO_RELOCATE = os.getenv("WILLING_TO_RELOCATE", "Yes")
NOTICE_PERIOD = os.getenv("NOTICE_PERIOD", "Immediate")
EXPECTED_SALARY = os.getenv("EXPECTED_SALARY", "4-5 LPA")

# Explicit user-provided application answers.
CURRENT_CTC = os.getenv("CURRENT_CTC", "0")
EXPECTED_CTC = os.getenv("EXPECTED_CTC", "4-5 LPA")

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
    """
    Return the actual LinkedIn Easy Apply dialog.

    LinkedIn can expose several role="dialog" elements at the same time
    (messaging, accessibility/UI dialogs, and the Easy Apply form). The
    previous implementation returned the first visible dialog, which can
    be the wrong dialog. That is why the application controls such as
    "Next" were not found.

    We score visible dialogs by their application-specific content and
    return the strongest match. If no dialog clearly matches, fall back
    to the page so the automation can still inspect visible controls.
    """
    try:
        dialogs = page.get_by_role("dialog")
        candidates = []

        for i in range(dialogs.count()):
            dialog = dialogs.nth(i)

            try:
                if not dialog.is_visible():
                    continue
            except Exception:
                continue

            text = safe_text(dialog).lower()

            if not text:
                continue

            score = 0

            # Strong indicators that this is the Easy Apply form.
            for term, points in [
                ("apply to ", 8),
                (" pages", 6),
                ("additional questions", 6),
                ("contact info", 4),
                ("resume", 3),
                ("phone", 2),
                ("next", 3),
                ("continue", 3),
                ("review", 3),
                ("submit application", 5),
            ]:
                if term in text:
                    score += points

            candidates.append((score, i, dialog, text[:250]))

        if candidates:
            candidates.sort(key=lambda item: item[0], reverse=True)
            best_score, best_index, best_dialog, preview = candidates[0]

            if best_score > 0:
                print(
                    f"Application dialog detected: "
                    f"dialog {best_index} (score={best_score})"
                )
                return best_dialog

    except Exception as e:
        print(f"Could not inspect application dialogs: {e}")

    # Fallback: the application controls may be rendered directly in the
    # page DOM instead of inside a role=dialog.
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

    name_parts = APPLICANT_NAME.split()
    first_name = name_parts[0] if name_parts else ""
    last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""

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

def fill_common_text_fields(container):

    print()
    print(
        "Checking common application fields..."
    )

    fields = container.locator(
        "input, textarea"
    )

    filled_count = 0

    for i in range(
        fields.count()
    ):

        try:

            element = fields.nth(i)

            tag = element.evaluate(
                "(el) => el.tagName"
            )

            if tag not in [
                "INPUT",
                "TEXTAREA"
            ]:

                continue

            field_type = (
                safe_attribute(
                    element,
                    "type"
                ).lower()
            )

            if field_type in [
                "hidden",
                "file",
                "radio",
                "checkbox",
                "submit",
                "button"
            ]:

                continue

            if not element.is_visible():

                continue

            current = ""

            try:

                current = (
                    element
                    .input_value()
                    .strip()
                )

            except Exception:
                pass

            if current:

                continue

            placeholder = (
                safe_attribute(
                    element,
                    "placeholder"
                ).lower()
            )

            aria = (
                safe_attribute(
                    element,
                    "aria-label"
                ).lower()
            )

            name = (
                safe_attribute(
                    element,
                    "name"
                ).lower()
            )

            element_id = (
                safe_attribute(
                    element,
                    "id"
                ).lower()
            )

            combined = (
                placeholder
                + " "
                + aria
                + " "
                + name
                + " "
                + element_id
            )

            # Years of experience

            if (
                "years of experience"
                in combined
                or "experience" in combined
                and "years" in combined
            ):

                if fill_if_empty(
                    element,
                    YEARS_OF_EXPERIENCE
                ):

                    print(
                        "Filled experience:",
                        YEARS_OF_EXPERIENCE
                    )

                    filled_count += 1

            # City

            elif (
                "city" in combined
                or "location" in combined
            ):

                if fill_if_empty(
                    element,
                    CITY
                ):

                    print(
                        "Filled location:",
                        CITY
                    )

                    filled_count += 1

        except Exception:
            continue

    # Additional profile-backed fields. These are only filled when the
    # field label/metadata clearly identifies the requested value.
    profile_values = {
        "degree": DEGREE,
        "field": FIELD_OF_STUDY,
        "graduation": GRADUATION_YEAR,
    }

    for i in range(fields.count()):
        try:
            element = fields.nth(i)
            if not element.is_visible():
                continue
            current = (element.input_value() or "").strip()
            if current:
                continue
            combined = " ".join([
                safe_attribute(element, "placeholder"),
                safe_attribute(element, "aria-label"),
                safe_attribute(element, "name"),
                safe_attribute(element, "id"),
            ]).lower()
            value = ""
            if "degree" in combined or "qualification" in combined: value = profile_values["degree"]
            elif "field of study" in combined or "major" in combined or "specialization" in combined: value = profile_values["field"]
            elif "graduation" in combined or "graduating year" in combined or "year graduated" in combined: value = profile_values["graduation"]
            if value and fill_if_empty(element, value):
                print("Filled profile field:", value)
                filled_count += 1
        except Exception:
            continue

    return filled_count


# ============================================================
# Job-specific text application answers
# ============================================================

def _element_context(element):
    """Return nearby visible text used to identify a LinkedIn form field."""
    texts = []
    try:
        texts.append(safe_text(element))
    except Exception:
        pass

    for xpath in [
        "xpath=ancestor::fieldset[1]",
        "xpath=ancestor::div[.//label][1]",
        "xpath=ancestor::div[.//input][1]",
        "xpath=ancestor::li[1]",
    ]:
        try:
            loc = element.locator(xpath).first
            if loc.count() and is_visible(loc):
                txt = safe_text(loc)
                if txt:
                    texts.append(txt)
        except Exception:
            continue

    return re.sub(r"\\s+", " ", " ".join(texts)).strip().lower()


def _fill_text_by_context(container, keywords, value, display_name):
    """Fill an empty text/number field whose nearby question matches keywords."""
    if not value:
        return False

    fields = container.locator("input, textarea")
    for i in range(fields.count()):
        field = fields.nth(i)

        if not is_visible(field):
            continue

        field_type = safe_attribute(field, "type").lower()
        if field_type in {
            "hidden", "file", "radio", "checkbox",
            "button", "submit"
        }:
            continue

        context = _element_context(field)
        if not all(keyword.lower() in context for keyword in keywords):
            continue

        if fill_if_empty(field, value):
            print(f"{display_name}: {value}")
            return True

    return False


def fill_known_text_application_questions(container):
    """
    Fill only explicitly configured CTC and notice-period answers.
    No unknown salary/notice values are guessed.
    """
    filled = 0

    # Current CTC: user explicitly provided 0.
    if (
        _fill_text_by_context(
            container,
            ["current", "ctc"],
            CURRENT_CTC,
            "Current CTC",
        )
        or
        _fill_text_by_context(
            container,
            ["current", "salary"],
            CURRENT_CTC,
            "Current CTC",
        )
    ):
        filled += 1

    # Expected CTC: user explicitly provided 4-5 LPA.
    if (
        _fill_text_by_context(
            container,
            ["expected", "ctc"],
            EXPECTED_CTC,
            "Expected CTC",
        )
        or
        _fill_text_by_context(
            container,
            ["expected", "salary"],
            EXPECTED_CTC,
            "Expected CTC",
        )
    ):
        filled += 1

    # Notice period: user explicitly provided Immediate.
    if _fill_text_by_context(
        container,
        ["notice", "period"],
        NOTICE_PERIOD,
        "Notice period",
    ):
        filled += 1

    if filled:
        print(f"Known text application answers filled: {filled}")

    return filled


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
    """Choose only answers explicitly supported by configured profile values."""
    q = (question or "").lower()
    normalized = [(a, (a or "").strip().lower()) for a in answers]

    def choose(configured):
        value = (configured or "").strip().lower()
        if not value:
            return None
        for label, low in normalized:
            if low == value or value in low:
                return label
        return None

    if any(x in q for x in ["require sponsorship", "need sponsorship", "future sponsorship", "visa sponsorship", "sponsorship"]):
        return choose(REQUIRES_SPONSORSHIP)

    if any(x in q for x in ["authorized to work", "legally authorized", "right to work", "eligible to work", "work authorization"]):
        return choose(WORK_AUTHORIZED)

    if any(x in q for x in ["relocate", "relocation", "willing to move"]):
        return choose(WILLING_TO_RELOCATE)

    if any(x in q for x in ["years of experience", "years experience", "professional experience"]):
        for label, low in normalized:
            if re.search(r"(^|\D)0(\D|$)", low) or "no experience" in low or "fresher" in low:
                return label if str(YEARS_OF_EXPERIENCE).strip() == "0" else None

    return None


def inspect_radio_buttons(container):
    """Inspect radio groups and safely answer only known questions.

    Returns the number of unresolved radio groups. A non-zero value prevents
    navigation/submission so the automation never guesses an application answer.
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

            # Never accept an unexplained/default checked answer as a safe answer.
            checked = any(radio.is_checked() for radio in group)
            if checked:
                print("WARNING: A radio option is already selected, but the question was not safely recognized.")
            else:
                print("WARNING: No radio option selected.")

            print("This radio question requires manual review.")
            unresolved += 1

        except Exception as e:
            print(f"Could not inspect radio group: {e}")
            unresolved += 1

    print()
    if unresolved == 0:
        print("All radio questions were answered safely.")
    else:
        print(f"Unresolved radio groups: {unresolved}")
        print("Automation will stop before continuing.")

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


def fill_configured_selects(container):
    """Fill only explicitly configured native selects; never guess unknown dropdowns."""
    if not APPLICATION_LANGUAGE:
        return 0
    filled = 0
    selects = container.locator("select")
    for i in range(selects.count()):
        try:
            select = selects.nth(i)
            if not select.is_visible():
                continue
            text = " ".join([safe_attribute(select, "aria-label"), safe_attribute(select, "name"), safe_attribute(select, "id")]).lower()
            if "language" not in text:
                # Inspect option text when the select has no useful metadata.
                option_text = " ".join([safe_text(select.locator("option").nth(j)) for j in range(min(select.locator("option").count(), 12))]).lower()
                if "english" not in option_text:
                    continue
            options = select.locator("option")
            for j in range(options.count()):
                option = options.nth(j)
                if safe_text(option).strip().lower() == APPLICATION_LANGUAGE.strip().lower():
                    select.select_option(value=safe_attribute(option, "value"))
                    print("Selected configured language:", APPLICATION_LANGUAGE)
                    filled += 1
                    break
        except Exception:
            continue
    return filled


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

            if not value:

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
# Find Next Button
# ============================================================

def _find_button_in_scope(scope):
    """Find a visible navigation button in one Playwright scope."""
    names = [
        "Next",
        "Continue",
        "Review",
    ]

    for name in names:
        try:
            button = scope.get_by_role(
                "button",
                name=re.compile(
                    rf"^\s*{re.escape(name)}\s*$",
                    re.IGNORECASE,
                ),
            ).first

            if button.count() > 0 and button.is_visible():
                return button
        except Exception:
            pass

    # Text/attribute fallback. LinkedIn occasionally changes the accessible
    # name while keeping the visible button text.
    try:
        buttons = scope.locator(
            "button, [role='button'], input[type='button'], input[type='submit']"
        )

        for i in range(buttons.count()):
            button = buttons.nth(i)

            try:
                if not button.is_visible():
                    continue
            except Exception:
                continue

            text = safe_text(button).strip().lower()
            aria = safe_attribute(button, "aria-label").strip().lower()
            title = safe_attribute(button, "title").strip().lower()
            data_testid = safe_attribute(button, "data-testid").strip().lower()

            combined = " ".join(
                [text, aria, title, data_testid]
            ).strip()

            if combined in {"next", "continue", "review"}:
                return button

            # Some controls contain the word as part of a longer accessible
            # label, but we only accept navigation-like labels.
            if any(
                re.fullmatch(
                    rf".*\b{re.escape(name)}\b.*",
                    combined,
                    re.IGNORECASE,
                )
                for name in names
            ):
                if not any(
                    bad in combined
                    for bad in [
                        "job",
                        "profile",
                        "similar",
                        "search",
                        "notification",
                    ]
                ):
                    return button

    except Exception:
        pass

    return None


def find_next_button(container, page=None):
    """
    Find LinkedIn's application navigation button.

    First inspect the actual application dialog. If LinkedIn has placed the
    navigation button outside that dialog, inspect the full page as a
    fallback. This directly handles the DOM structure seen during testing.
    """
    button = _find_button_in_scope(container)

    if button is not None:
        return button

    if page is not None and container is not page:
        button = _find_button_in_scope(page)
        if button is not None:
            print("Navigation button found in full page scope.")
            return button

    return None


# ============================================================
# Find Submit Button
# ============================================================

def find_submit_button(container):

    patterns = [
        r"submit application",
        r"submit",
        r"send application"
    ]

    for pattern in patterns:

        try:

            button = container.get_by_role(
                "button",
                name=re.compile(
                    pattern,
                    re.IGNORECASE
                )
            ).first

            if button.count() > 0:

                if button.is_visible():

                    return button

        except Exception:
            pass

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
    # Explicit user-provided application answers
    # --------------------------------------------------------

    fill_known_text_application_questions(container)

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
    fill_configured_selects(container)

    # --------------------------------------------------------
    # Required fields
    # --------------------------------------------------------

    unanswered = (
        inspect_required_fields(
            container
        )
    )

    # Treat unresolved radio questions as blocking issues.
    if unresolved_radios > 0:
        unanswered += unresolved_radios

    return unanswered


# ============================================================
# Move To Next Page
# ============================================================

def move_to_next_page(page: Page):

    container = get_application_container(
        page
    )

    button = find_next_button(
        container,
        page
    )

    if button is None:

        print()
        print(
            "Next/Continue/Review button "
            "not found."
        )

        return False

    try:

        print()
        print(
            "Next button found."
        )

        button.scroll_into_view_if_needed()

        page.wait_for_timeout(
            500
        )

        button.click()

        page.wait_for_timeout(
            2000
        )

        print(
            "Moved to next application page."
        )

        return True

    except Exception as e:

        print(
            f"Could not move to next page: {e}"
        )

        return False


# ============================================================
# Final Review / Submit
# ============================================================

def handle_final_submission(page: Page):
    """
    Handle the final LinkedIn Easy Apply submission.

    Returns:
        "SUBMITTED"        -> LinkedIn confirmation detected
        "READY_FOR_REVIEW" -> AUTO_SUBMIT is disabled
        False              -> submission failed or confirmation missing
    """

    print()
    print("=" * 70)
    print("FINAL APPLICATION REVIEW")
    print("=" * 70)

    container = get_application_container(page)

    submit_button = find_submit_button(container)

    # Fallback: sometimes the final button is outside the selected dialog.
    if submit_button is None and container is not page:
        submit_button = find_submit_button(page)

    if submit_button is None:
        print("Submit application button not found.")
        return False

    print("Submit application button found.")

    # ------------------------------------------------------------
    # Manual review mode
    # ------------------------------------------------------------

    if not AUTO_SUBMIT:

        print()
        print("AUTO_SUBMIT = False")
        print("Application will NOT be submitted.")
        print("Review the application manually.")

        return "READY_FOR_REVIEW"

    # ------------------------------------------------------------
    # Verify button
    # ------------------------------------------------------------

    try:
        if not submit_button.is_visible():
            print("Submit button is not visible.")
            return False

        if not submit_button.is_enabled():
            print("Submit button is disabled.")
            return False

    except Exception as e:
        print(f"Could not verify submit button: {e}")
        return False

    # ------------------------------------------------------------
    # Capture current page text before submission
    # ------------------------------------------------------------

    try:
        before_text = page.locator("body").inner_text().lower()
    except Exception:
        before_text = ""

    # ------------------------------------------------------------
    # Submit
    # ------------------------------------------------------------

    print()
    print("Submitting application...")

    try:

        submit_button.scroll_into_view_if_needed()

        page.wait_for_timeout(500)

        submit_button.click(timeout=10000)

        print("Submit button clicked.")

    except Exception as e:

        print(f"Normal submit click failed: {e}")
        print("Trying JavaScript click...")

        try:
            submit_button.evaluate(
                "(element) => element.click()"
            )

            print("JavaScript submit click completed.")

        except Exception as js_error:

            print(
                f"JavaScript submit click failed: "
                f"{js_error}"
            )

            return False

    # ------------------------------------------------------------
    # IMPORTANT:
    # LinkedIn confirmation may take several seconds.
    # It may also appear inside a dialog rather than the body.
    # ------------------------------------------------------------

    confirmation_signals = [

        # Main LinkedIn success messages
        "your application was sent",
        "application was sent",
        "application submitted",
        "application sent",
        "you applied",

        # Common LinkedIn wording
        "application has been sent",
        "your application has been submitted",
        "application successfully submitted",

        # Job-specific success wording
        "your application was sent to",

        # Confirmation UI
        "application sent successfully",
        "successfully applied",
    ]

    print()
    print("Waiting for LinkedIn submission confirmation...")

    for attempt in range(1, 11):

        page.wait_for_timeout(1000)

        texts = []

        # --------------------------------------------------------
        # 1. Entire page
        # --------------------------------------------------------

        try:
            texts.append(
                page.locator("body").inner_text().lower()
            )
        except Exception:
            pass

        # --------------------------------------------------------
        # 2. Visible dialogs
        # --------------------------------------------------------

        try:
            dialogs = page.locator(
                "[role='dialog']:visible"
            )

            for i in range(dialogs.count()):

                try:
                    texts.append(
                        dialogs.nth(i).inner_text().lower()
                    )
                except Exception:
                    pass

        except Exception:
            pass

        # --------------------------------------------------------
        # 3. Alerts
        # --------------------------------------------------------

        try:
            alerts = page.locator(
                "[role='alert']:visible"
            )

            for i in range(alerts.count()):

                try:
                    texts.append(
                        alerts.nth(i).inner_text().lower()
                    )
                except Exception:
                    pass

        except Exception:
            pass

        combined_text = "\n".join(texts)

        # --------------------------------------------------------
        # Check confirmation
        # --------------------------------------------------------

        matched_signal = None

        for signal in confirmation_signals:

            if signal in combined_text:

                matched_signal = signal
                break

        if matched_signal:

            print()
            print("=" * 70)
            print("APPLICATION SUBMITTED AND CONFIRMED")
            print("=" * 70)

            print(
                f"Confirmation detected: "
                f"'{matched_signal}'"
            )

            return "SUBMITTED"

        print(
            f"Confirmation check "
            f"{attempt}/10..."
        )

    # ------------------------------------------------------------
    # No confirmation
    # ------------------------------------------------------------

    print()
    print("=" * 70)
    print("SUBMISSION CONFIRMATION NOT DETECTED")
    print("=" * 70)

    print(
        "The Submit button was clicked, "
        "but LinkedIn did not expose a recognizable "
        "confirmation message."
    )

    print(
        "Tracker will NOT automatically mark "
        "this application as APPLIED."
    )

    # Save diagnostic screenshot
    try:

        os.makedirs(
            "screenshots",
            exist_ok=True
        )

        screenshot_path = (
            "screenshots/"
            "submission_confirmation_missing.png"
        )

        page.screenshot(
            path=screenshot_path,
            full_page=True
        )

        print(
            f"Diagnostic screenshot saved: "
            f"{screenshot_path}"
        )

    except Exception as e:

        print(
            f"Could not save screenshot: {e}"
        )

    return False


# ============================================================
# Main Application Automation
# ============================================================

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
            container
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