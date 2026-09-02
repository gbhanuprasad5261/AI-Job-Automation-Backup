import csv
import os

from skill_matcher import match_resume
from profile import PROFILE


# ================================================================
# CONFIGURATION
# ================================================================

INPUT_FILE = "data/job_details.csv"
OUTPUT_FILE = "data/job_analysis.csv"

MIN_MATCH_SCORE = 70

TARGET_LOCATIONS = [
    "bengaluru",
    "bangalore",
    "hyderabad",
    "chennai",
    "remote",
]

try:
    CANDIDATE_EXPERIENCE_YEARS = int(
        PROFILE.get("experience_years", 0)
    )
except (TypeError, ValueError):
    CANDIDATE_EXPERIENCE_YEARS = 0


# ================================================================
# EXPERIENCE EXTRACTION
# ================================================================

def extract_experience_years(text):
    """
    Extract the minimum required professional experience from a job
    description.

    Rules:
        - Explicit fresher / entry-level requirements -> 0
        - 0-1 / 0-2 years -> 0
        - 1+ years -> 1
        - 2+ years -> 2
        - 3+ years -> 3
        - 1-3 years -> 1
        - 2 to 5 years -> 2

    Important:
        Words such as "graduate" or "degree" alone do NOT mean
        the candidate is a fresher.
    """

    if not text:
        return 0

    import re

    text = text.lower()

    # Normalize common variations
    text = re.sub(r"\s+", " ", text)

    # ------------------------------------------------------------
    # 1. Look specifically for experience-related sentences
    # ------------------------------------------------------------

    experience_patterns = [

        # 3+ years experience
        r"(\d+)\s*\+\s*(?:years?|yrs?)\s*(?:of\s*)?(?:relevant\s*)?(?:professional\s*)?experience",

        # 3 or more years experience
        r"(\d+)\s+or\s+more\s+(?:years?|yrs?)\s*(?:of\s*)?(?:relevant\s*)?(?:professional\s*)?experience",

        # 3-5 years experience
        r"(\d+)\s*[-–]\s*(\d+)\s*(?:years?|yrs?)\s*(?:of\s*)?(?:relevant\s*)?(?:professional\s*)?experience",

        # 3 to 5 years experience
        r"(\d+)\s+to\s+(\d+)\s*(?:years?|yrs?)\s*(?:of\s*)?(?:relevant\s*)?(?:professional\s*)?experience",

        # minimum 3 years experience
        r"minimum\s+(?:of\s+)?(\d+)\s*(?:years?|yrs?)",

        # at least 3 years experience
        r"at\s+least\s+(\d+)\s*(?:years?|yrs?)",

        # experience: 3 years
        r"experience\s*[:\-]?\s*(\d+)\s*(?:years?|yrs?)",

        # 3 years of experience
        r"(\d+)\s*(?:years?|yrs?)\s+of\s+(?:relevant\s+|professional\s+|hands[- ]on\s+)?experience",
    ]

    detected_years = []

    for pattern in experience_patterns:

        matches = re.findall(
            pattern,
            text,
        )

        for match in matches:

            if isinstance(match, tuple):

                numbers = []

                for value in match:
                    if value:
                        try:
                            numbers.append(
                                int(value)
                            )
                        except ValueError:
                            pass

                if numbers:
                    detected_years.append(
                        min(numbers)
                    )

            else:

                try:
                    detected_years.append(
                        int(match)
                    )
                except ValueError:
                    pass

    # ------------------------------------------------------------
    # 2. If an explicit numeric experience requirement exists,
    #    trust it over generic words such as "graduate".
    # ------------------------------------------------------------

    if detected_years:

        return min(detected_years)

    # ------------------------------------------------------------
    # 3. Explicit fresher / entry-level language
    # ------------------------------------------------------------

    fresher_patterns = [

        r"\bfresher\b",

        r"\bfreshers\b",

        r"\bfresh graduate\b",

        r"\bfresh graduates\b",

        r"\bentry[- ]level\b",

        r"\b0\s*(?:to|-)\s*1\s*(?:years?|yrs?)",

        r"\b0\s*(?:to|-)\s*2\s*(?:years?|yrs?)",

        r"\b0\s*\+\s*(?:years?|yrs?)",

        r"\b0\s*(?:years?|yrs?)\s+(?:of\s+)?experience",
    ]

    for pattern in fresher_patterns:

        if re.search(
            pattern,
            text,
        ):
            return 0

    # ------------------------------------------------------------
    # 4. No reliable experience requirement found
    # ------------------------------------------------------------

    return 0
# ================================================================
# EXPERIENCE LABEL
# ================================================================

def get_experience_label(years, description):
    """
    Convert extracted experience years into a readable label.

    Numeric professional experience requirements take priority over
    generic fresher/graduate wording.
    """

    if not description:
        return "Not specified"

    import re

    description_lower = description.lower()

    # ------------------------------------------------------------
    # 1. Numeric experience requirement has priority
    # ------------------------------------------------------------

    if years is not None and years > 0:
        if years == 1:
            return "1+ years"

        return f"{years}+ years"

    # ------------------------------------------------------------
    # 2. Explicit fresher / entry-level wording
    # ------------------------------------------------------------

    fresher_patterns = [
        r"\bfresher\b",
        r"\bfreshers\b",
        r"\bfresh graduate\b",
        r"\bfresh graduates\b",
        r"\bentry[- ]level\b",
        r"\b0\s*(?:to|-)\s*1\s*(?:years?|yrs?)",
        r"\b0\s*(?:to|-)\s*2\s*(?:years?|yrs?)",
        r"\b0\s*\+\s*(?:years?|yrs?)",
        r"\b0\s*(?:years?|yrs?)\s+(?:of\s+)?experience",
    ]

    for pattern in fresher_patterns:
        if re.search(pattern, description_lower):
            return "Fresher / Entry Level"

    # ------------------------------------------------------------
    # 3. No reliable requirement
    # ------------------------------------------------------------

    return "Not specified"

# ================================================================
# LOCATION CHECK
# ================================================================

def location_matches(location):
    """
    Check whether a job is in one of the user's target locations.
    """

    if not location:
        return False

    location_lower = location.lower()

    for target in TARGET_LOCATIONS:
        if target in location_lower:
            return True

    return False


# ================================================================
# PRIORITY
# ================================================================

def calculate_priority(score):
    """
    Determine recommendation priority from match score.
    """

    if score >= 85:
        return "HIGH"

    if score >= MIN_MATCH_SCORE:
        return "MEDIUM"

    return "LOW"


# ================================================================
# MAIN ANALYZER
# ================================================================

def analyze_jobs():

    if not os.path.exists(INPUT_FILE):
        print(f"{INPUT_FILE} not found.")
        return

    os.makedirs("data", exist_ok=True)

    # ------------------------------------------------------------
    # Load job details
    # ------------------------------------------------------------

    with open(
        INPUT_FILE,
        "r",
        encoding="utf-8",
    ) as file:

        reader = csv.DictReader(file)
        jobs = list(reader)

    if not jobs:
        print("No jobs found.")
        return

    analyzed_jobs = []

    skipped_score = 0
    skipped_location = 0
    skipped_experience = 0
    skipped_data = 0

    # ============================================================
    # PROCESS JOBS
    # ============================================================

    for job in jobs:

        title = job.get(
            "Title",
            "",
        ).strip()

        company = job.get(
            "Company",
            "",
        ).strip()

        location = job.get(
            "Location",
            "",
        ).strip()

        easy_apply = job.get(
            "Easy Apply",
            "",
        ).strip()

        link = job.get(
            "Link",
            "",
        ).strip()

        description = job.get(
            "Description",
            "",
        ).strip()

        # --------------------------------------------------------
        # DATA QUALITY CHECK
        # --------------------------------------------------------

        if not description:

            score = 0

            matched = set()

            missing = set()

            data_status = "INSUFFICIENT_DATA"

            application_eligible = "No"

            experience_years = 0

            experience_label = "Not specified"

            experience_skip = False

            priority = "LOW"

            skipped_data += 1

        else:

            data_status = "OK"

            # ----------------------------------------------------
            # SKILL MATCHING
            # ----------------------------------------------------

            score, matched, missing = match_resume(
                description
            )

            # ----------------------------------------------------
            # EXPERIENCE
            # ----------------------------------------------------

            experience_years = extract_experience_years(
                description
            )

            experience_label = get_experience_label(
                experience_years,
                description,
            )

            # ----------------------------------------------------
            # EXPERIENCE FILTER
            # ----------------------------------------------------

            experience_skip = (
                experience_years
                > CANDIDATE_EXPERIENCE_YEARS
            )

            if experience_skip:
                skipped_experience += 1

            # ----------------------------------------------------
            # PRIORITY
            # ----------------------------------------------------

            priority = calculate_priority(score)

            # ----------------------------------------------------
            # APPLICATION ELIGIBILITY
            # ----------------------------------------------------

            application_eligible = "Yes"

            if score < MIN_MATCH_SCORE:
                application_eligible = "No"

            if not location_matches(location):
                application_eligible = "No"

            if experience_skip:
                application_eligible = "No"

            if score < MIN_MATCH_SCORE:
                skipped_score += 1

            if not location_matches(location):
                skipped_location += 1

        # ========================================================
        # STORE ANALYZED JOB
        # ========================================================

        analyzed_jobs.append({

            "Title": title,

            "Company": company,

            "Location": location,

            "Easy Apply": easy_apply,

            "Match Score": (
                "N/A"
                if data_status != "OK"
                else f"{score}%"
            ),

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

            "Data Status": data_status,

            "Application Eligible": (
                application_eligible
            ),

            "Link": link,
        })

    # ============================================================
    # SAVE ANALYSIS
    # ============================================================

    fieldnames = [

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

        "Data Status",

        "Application Eligible",

        "Link",
    ]

    with open(
        OUTPUT_FILE,
        "w",
        newline="",
        encoding="utf-8",
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
            quoting=csv.QUOTE_ALL,
        )

        writer.writeheader()

        for job in analyzed_jobs:

            writer.writerow(job)

    # ============================================================
    # TOP RECOMMENDATIONS
    # ============================================================

    recommendations = []

    for job in analyzed_jobs:

        if (
            job["Application Eligible"]
            != "Yes"
        ):
            continue

        score_text = job["Match Score"]

        if not score_text.endswith("%"):
            continue

        try:
            score = int(
                score_text.replace("%", "")
            )
        except ValueError:
            continue

        recommendations.append(
            (score, job)
        )

    recommendations.sort(
        key=lambda item: item[0],
        reverse=True,
    )

    # ============================================================
    # OUTPUT
    # ============================================================

    print()
    print("=" * 60)
    print("AI JOB ANALYSIS COMPLETED")
    print("=" * 60)

    print(
        f"Jobs analyzed : {len(analyzed_jobs)}"
    )

    print(
        f"Saved file    : {OUTPUT_FILE}"
    )

    print()
    print("=" * 60)
    print("TOP JOB RECOMMENDATIONS")
    print("=" * 60)

    if not recommendations:

        print()
        print(
            "No jobs currently meet the requirements."
        )

    else:

        for index, (score, job) in enumerate(
            recommendations[:10],
            start=1,
        ):

            print()

            print(
                f"{index}. "
                f"{job['Title']}"
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
                f"{job['Easy Apply']}"
            )

            missing = job[
                "Missing Skills"
            ]

            print(
                f"   Missing : "
                f"{missing if missing else 'None'}"
            )

    # ============================================================
    # SUMMARY
    # ============================================================

    print()
    print("=" * 60)
    print("RECOMMENDATION SUMMARY")
    print("=" * 60)

    print(
        f"Minimum Match Score : "
        f"{MIN_MATCH_SCORE}%"
    )

    print(
        f"Easy Apply Filter   : False"
    )

    print(
        f"Candidate Experience: "
        f"{CANDIDATE_EXPERIENCE_YEARS} years"
    )

    print(
        f"Recommended Jobs     : "
        f"{len(recommendations)}"
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

    print(
        f"Skipped by data      : "
        f"{skipped_data}"
    )

    # ============================================================
    # SKILL GAP ANALYSIS
    # ============================================================

    skill_frequency = {}

    for job in analyzed_jobs:

        if job["Data Status"] != "OK":
            continue

        missing_skills = job[
            "Missing Skills"
        ]

        if not missing_skills:
            continue

        skills = [
            skill.strip()
            for skill in missing_skills.split(",")
            if skill.strip()
        ]

        for skill in skills:

            skill_frequency[skill] = (
                skill_frequency.get(
                    skill,
                    0,
                )
                + 1
            )

    sorted_skills = sorted(
        skill_frequency.items(),
        key=lambda item: item[1],
        reverse=True,
    )

    print()
    print("=" * 60)
    print("SKILL GAP ANALYSIS")
    print("=" * 60)

    if not sorted_skills:

        print()
        print(
            "No significant skill gaps found."
        )

    else:

        print()
        print(
            "Skills to improve based on "
            "collected jobs:"
        )

        for index, (skill, count) in enumerate(
            sorted_skills[:10],
            start=1,
        ):

            print(
                f"{index}. "
                f"{skill} -> "
                f"{count} job(s)"
            )

        focus_skills = [
            skill
            for skill, count in sorted_skills[:5]
        ]

        print()
        print(
            "Recommended Focus:"
        )

        print(
            ", ".join(focus_skills)
        )

    print()


# ================================================================
# ENTRY POINT
# ================================================================

if __name__ == "__main__":
    analyze_jobs()