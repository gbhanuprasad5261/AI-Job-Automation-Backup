import csv
import os
import re
from collections import Counter

from skill_matcher import match_resume


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

try:
    from config import (
        MIN_MATCH_SCORE,
        TARGET_LOCATIONS,
        EASY_APPLY_FILTER,
    )
except ImportError:
    MIN_MATCH_SCORE = 70
    TARGET_LOCATIONS = (
        "bengaluru",
        "bangalore",
        "hyderabad",
        "chennai",
        "remote",
    )
    EASY_APPLY_FILTER = False


INPUT_FILE = "data/job_details.csv"
OUTPUT_FILE = "data/job_analysis.csv"
TOP_JOBS = 10

# Candidate is a fresher.
CANDIDATE_EXPERIENCE_YEARS = 0


# ---------------------------------------------------------------------------
# Experience detection
# ---------------------------------------------------------------------------

# Explicit experience requirements.
EXPERIENCE_PATTERNS = [
    # 3+ years experience
    r"(\d+)\s*\+\s*years?\s+(?:of\s+)?(?:professional\s+)?experience",

    # minimum 3 years experience
    r"minimum\s+(?:of\s+)?(\d+)\s+years?\s+(?:of\s+)?(?:professional\s+)?experience",

    # at least 3 years experience
    r"at\s+least\s+(\d+)\s+years?\s+(?:of\s+)?(?:professional\s+)?experience",

    # 3-5 years experience / 3 – 5 years experience
    r"(\d+)\s*[-–—]\s*(\d+)\s+years?\s+(?:of\s+)?(?:professional\s+)?experience",

    # 3 years of experience
    r"(\d+)\s+years?\s+(?:of\s+)?(?:professional\s+)?experience",
]


FRESHER_TERMS = (
    "fresher",
    "freshers",
    "fresh graduate",
    "fresh graduates",
    "recent graduate",
    "recent graduates",
    "entry level",
    "entry-level",
    "graduate role",
    "graduate position",
    "no experience required",
    "no prior experience required",
    "experience not required",
    "0 years experience",
    "0 years of experience",
)


def _normalise_description(text):
    """Normalise whitespace and dash characters."""
    text = str(text or "").lower()

    text = (
        text
        .replace("–", "-")
        .replace("—", "-")
    )

    text = re.sub(r"\s+", " ", text)

    return text.strip()


def _is_preferred_experience(text, start, end):
    """
    Determine whether an experience statement appears to be preferred
    rather than mandatory.

    Example:
        '3+ years experience preferred'
        '3+ years experience is a plus'

    These should not automatically exclude a fresher.
    """

    context_start = max(0, start - 80)
    context_end = min(len(text), end + 100)

    context = text[context_start:context_end]

    preferred_terms = (
        "preferred",
        "prefer",
        "nice to have",
        "nice-to-have",
        "plus",
        "bonus",
        "desired",
        "ideal",
        "would be a plus",
    )

    return any(
        term in context
        for term in preferred_terms
    )


def extract_experience_requirement(description):
    """
    Extract the clearest minimum experience requirement.

    Returns:
        required_years:
            Minimum experience clearly required.

        label:
            Human-readable experience requirement.

        skip:
            True when the role clearly requires more experience
            than the candidate has.

    Examples:

        Fresher / Entry Level
            -> 0 years
            -> do not skip

        0-2 years
            -> minimum 0
            -> do not skip

        1-3 years
            -> minimum 1
            -> skip for fresher

        3+ years
            -> minimum 3
            -> skip for fresher
    """

    text = _normalise_description(description)

    if not text:
        return 0, "Not specified", False

    # -----------------------------------------------------------------------
    # First look for explicit fresher/entry-level language.
    # -----------------------------------------------------------------------

    has_fresher_language = any(
        term in text
        for term in FRESHER_TERMS
    )

    # -----------------------------------------------------------------------
    # Find explicit experience requirements.
    # -----------------------------------------------------------------------

    requirements = []

    for pattern in EXPERIENCE_PATTERNS:

        for match in re.finditer(pattern, text):

            groups = match.groups()

            try:
                minimum = int(groups[0])
            except (ValueError, TypeError, IndexError):
                continue

            # For ranges such as 1-3 years, the first number is the
            # minimum required experience.
            maximum = None

            if len(groups) >= 2:
                try:
                    maximum = int(groups[1])
                except (ValueError, TypeError):
                    maximum = None

            # Ignore experience that is explicitly described as preferred,
            # desired, a bonus, etc.
            if _is_preferred_experience(
                text,
                match.start(),
                match.end(),
            ):
                continue

            requirements.append(
                {
                    "minimum": minimum,
                    "maximum": maximum,
                    "text": match.group(0),
                }
            )

    # -----------------------------------------------------------------------
    # No explicit requirement found.
    # -----------------------------------------------------------------------

    if not requirements:

        if has_fresher_language:
            return (
                0,
                "Fresher / Entry Level",
                False,
            )

        return (
            0,
            "Not specified",
            False,
        )

    # -----------------------------------------------------------------------
    # Use the strongest/most demanding explicit minimum requirement.
    # -----------------------------------------------------------------------

    required_years = max(
        item["minimum"]
        for item in requirements
    )

    # If the posting explicitly welcomes freshers but also contains a
    # generic experience statement elsewhere, don't automatically reject it.
    if (
        has_fresher_language
        and required_years == 0
    ):
        return (
            0,
            "Fresher / Entry Level",
            False,
        )

    # -----------------------------------------------------------------------
    # Determine label.
    # -----------------------------------------------------------------------

    labels = []

    for item in requirements:

        minimum = item["minimum"]
        maximum = item["maximum"]

        if maximum is not None:
            labels.append(
                f"{minimum}-{maximum} years"
            )
        else:
            labels.append(
                f"{minimum}+ years"
            )

    # Remove duplicate labels while preserving order.
    labels = list(dict.fromkeys(labels))

    experience_label = ", ".join(labels)

    # -----------------------------------------------------------------------
    # Fresher eligibility.
    # -----------------------------------------------------------------------

    experience_skip = (
        required_years
        > CANDIDATE_EXPERIENCE_YEARS
    )

    return (
        required_years,
        experience_label,
        experience_skip,
    )


# ---------------------------------------------------------------------------
# Location
# ---------------------------------------------------------------------------

def location_allowed(location):
    text = (
        location or ""
    ).strip().lower()

    return bool(text) and any(
        target in text
        for target in TARGET_LOCATIONS
    )


# ---------------------------------------------------------------------------
# Main analysis
# ---------------------------------------------------------------------------

def analyze_jobs():

    if not os.path.exists(INPUT_FILE):

        print("job_details.csv not found.")
        return

    jobs = []

    with open(
        INPUT_FILE,
        "r",
        encoding="utf-8",
        newline="",
    ) as f:

        reader = csv.DictReader(f)

        for row in reader:

            description = row.get(
                "Description",
                "",
            )

            # ---------------------------------------------------------------
            # Resume skill matching
            # ---------------------------------------------------------------

            score, matched, missing = match_resume(
                description
            )

            # ---------------------------------------------------------------
            # Experience analysis
            # ---------------------------------------------------------------

            (
                experience_years,
                experience_label,
                experience_skip,
            ) = extract_experience_requirement(
                description
            )

            # ---------------------------------------------------------------
            # Priority
            # ---------------------------------------------------------------

            if score >= 80:
                priority = "HIGH"

            elif score >= 70:
                priority = "MEDIUM"

            else:
                priority = "LOW"

            # ---------------------------------------------------------------
            # Store analysis
            # ---------------------------------------------------------------

            jobs.append({

                "Title": row.get(
                    "Title",
                    "",
                ),

                "Company": row.get(
                    "Company",
                    "",
                ),

                "Location": row.get(
                    "Location",
                    "",
                ),

                "Easy Apply": row.get(
                    "Easy Apply",
                    "",
                ),

                "Match Score": f"{score}%",

                "Priority": priority,

                "Matched Skills": ", ".join(
                    sorted(matched)
                ),

                "Missing Skills": ", ".join(
                    sorted(missing)
                ),

                "Experience Required": (
                    experience_label
                ),

                "Experience Years": (
                    experience_years
                ),

                "Experience Skip": (
                    "Yes"
                    if experience_skip
                    else "No"
                ),

                "Link": row.get(
                    "Link",
                    "",
                ),
            })

    # -----------------------------------------------------------------------
    # Save analysis CSV
    # -----------------------------------------------------------------------

    output_directory = os.path.dirname(
        OUTPUT_FILE
    )

    if output_directory:
        os.makedirs(
            output_directory,
            exist_ok=True,
        )

    fields = [
        "Title",
        "Company",
        "Location",
        "Easy Apply",
        "Match Score",
        "Priority",
        "Matched Skills",
        "Missing Skills",
        "Experience Required",
        "Experience Years",
        "Experience Skip",
        "Link",
    ]

    with open(
        OUTPUT_FILE,
        "w",
        newline="",
        encoding="utf-8",
    ) as f:

        writer = csv.DictWriter(
            f,
            fieldnames=fields,
        )

        writer.writeheader()
        writer.writerows(jobs)

    # -----------------------------------------------------------------------
    # Recommendation filtering
    # -----------------------------------------------------------------------

    recommended = []

    skipped_experience = 0
    skipped_score = 0
    skipped_location = 0
    skipped_easy_apply = 0

    for job in jobs:

        try:
            score = int(
                str(
                    job.get(
                        "Match Score",
                        "0",
                    )
                )
                .replace("%", "")
                .strip()
            )

        except (ValueError, TypeError):

            score = 0

        # ---------------------------------------------------------------
        # Filter 1: Match score
        # ---------------------------------------------------------------

        if score < MIN_MATCH_SCORE:

            skipped_score += 1
            continue

        # ---------------------------------------------------------------
        # Filter 2: Target location
        # ---------------------------------------------------------------

        if not location_allowed(
            job.get("Location", "")
        ):

            skipped_location += 1
            continue

        # ---------------------------------------------------------------
        # Filter 3: Experience
        # ---------------------------------------------------------------

        if (
            job.get(
                "Experience Skip",
                "No",
            )
            .strip()
            .lower()
            == "yes"
        ):

            skipped_experience += 1
            continue

        # ---------------------------------------------------------------
        # Filter 4: Easy Apply, if enabled
        # ---------------------------------------------------------------

        if (
            EASY_APPLY_FILTER
            and
            job.get(
                "Easy Apply",
                "",
            )
            .strip()
            .lower()
            != "yes"
        ):

            skipped_easy_apply += 1
            continue

        recommended.append(job)

    # -----------------------------------------------------------------------
    # Sort highest score first
    # -----------------------------------------------------------------------

    recommended.sort(
        key=lambda x: int(
            str(
                x.get(
                    "Match Score",
                    "0",
                )
            )
            .replace("%", "")
            .strip()
            or 0
        ),
        reverse=True,
    )

    # -----------------------------------------------------------------------
    # Console output
    # -----------------------------------------------------------------------

    print()
    print("=" * 60)
    print("AI JOB ANALYSIS COMPLETED")
    print("=" * 60)

    print(
        f"Jobs analyzed : {len(jobs)}"
    )

    print(
        f"Saved file    : {OUTPUT_FILE}"
    )

    print()
    print("=" * 60)
    print("TOP JOB RECOMMENDATIONS")
    print("=" * 60)

    if recommended:

        for i, job in enumerate(
            recommended[:TOP_JOBS],
            1,
        ):

            print()
            print(
                f"{i}. {job['Title']}"
            )

            print(
                f"   Company : "
                f"{job['Company']}"
            )

            print(
                f"   Location: "
                f"{job['Location']}"
            )

            print(
                f"   Score   : "
                f"{job['Match Score']}"
            )

            print(
                f"   Priority: "
                f"{job['Priority']}"
            )

            print(
                f"   Experience: "
                f"{job['Experience Required']}"
            )

            print(
                f"   Easy Apply: "
                f"{job['Easy Apply'] or 'Unknown'}"
            )

            print(
                f"   Missing : "
                f"{job['Missing Skills'] or 'None'}"
            )

    else:

        print()
        print(
            f"No jobs currently meet the "
            f"{MIN_MATCH_SCORE}% score, "
            f"location, and experience filters."
        )

    # -----------------------------------------------------------------------
    # Recommendation summary
    # -----------------------------------------------------------------------

    print()
    print("=" * 60)
    print("RECOMMENDATION SUMMARY")
    print("=" * 60)

    print(
        f"Minimum Match Score : "
        f"{MIN_MATCH_SCORE}%"
    )

    print(
        f"Easy Apply Filter   : "
        f"{EASY_APPLY_FILTER}"
    )

    print(
        f"Candidate Experience: "
        f"{CANDIDATE_EXPERIENCE_YEARS} years"
    )

    print(
        f"Recommended Jobs     : "
        f"{len(recommended)}"
    )

    print()
    print(
        f"Skipped by score     : "
        f"{skipped_score}"
    )

    print(
        f"Skipped by location  : "
        f"{skipped_location}"
    )

    print(
        f"Skipped by experience: "
        f"{skipped_experience}"
    )

    if EASY_APPLY_FILTER:

        print(
            f"Skipped Easy Apply   : "
            f"{skipped_easy_apply}"
        )

    # -----------------------------------------------------------------------
    # Skill gap analysis
    # -----------------------------------------------------------------------

    counter = Counter()

    for job in jobs:

        counter.update(
            skill.strip()
            for skill in job.get(
                "Missing Skills",
                "",
            ).split(",")

            if skill.strip()
        )

    print()
    print("=" * 60)
    print("SKILL GAP ANALYSIS")
    print("=" * 60)

    if counter:

        print()
        print(
            "Skills to improve based on "
            "collected jobs:\n"
        )

        for rank, (
            skill,
            count,
        ) in enumerate(
            counter.most_common(10),
            1,
        ):

            print(
                f"{rank}. "
                f"{skill} -> "
                f"{count} job(s)"
            )

        print()
        print("Recommended Focus:")

        print(
            ", ".join(
                skill
                for skill, _
                in counter.most_common(5)
            )
        )

    else:

        print()
        print(
            "No missing skills identified."
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    analyze_jobs()