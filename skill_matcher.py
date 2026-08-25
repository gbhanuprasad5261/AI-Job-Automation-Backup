import re

try:
    from profile import PROFILE

    resume_skills = {
        str(s).strip().lower()
        for s in PROFILE.get("skills", [])
        if str(s).strip()
    }

except Exception:

    resume_skills = {
        "java",
        "spring",
        "spring boot",
        "spring mvc",
        "spring data jpa",
        "hibernate",
        "jdbc",
        "sql",
        "mysql",
        "rest api",
        "microservices",
        "git",
        "github",
        "maven",
        "postman",
        "junit",
        "mockito",
    }


# ============================================================
# SKILL CATEGORIES
# ============================================================

# These are the most important skills for your target:
# Java Backend / Software Engineer roles.

CORE_SKILLS = {
    "java",
    "spring",
    "spring boot",
    "spring mvc",
    "spring data jpa",
    "hibernate",
    "jdbc",
    "sql",
    "mysql",
    "postgresql",
    "rest api",
    "microservices",
    "oop",
    "multithreading",
    "dsa",
}

SUPPORTING_SKILLS = {
    "git",
    "github",
    "maven",
    "postman",
    "junit",
    "mockito",
    "mongodb",
    "redis",
    "kafka",
    "rabbitmq",
    "linux",
    "sdlc",
    "agile",
    "docker",
    "ci/cd",
    "jenkins",
    "deployment",
    "monitoring",
    "authentication",
    "authorization",
    "oauth",
}

OPTIONAL_SKILLS = {
    "aws",
    "azure",
    "gcp",
    "kubernetes",
    "javascript",
    "typescript",
    "html",
    "css",
    "angular",
    "react",
    "python",
    "c#",
    "golang",
    "waterfall",
}


# ============================================================
# WEIGHTS
# ============================================================

# Core Java/backend skills have the strongest influence.

job_skill_weights = {

    # Core Java Backend
    "java": 10,
    "spring": 8,
    "spring boot": 10,
    "spring mvc": 7,
    "spring data jpa": 8,
    "hibernate": 7,
    "jdbc": 6,
    "rest api": 8,
    "microservices": 10,

    # Java fundamentals
    "oop": 5,
    "multithreading": 6,
    "dsa": 5,

    # Databases
    "sql": 8,
    "mysql": 6,
    "postgresql": 6,
    "mongodb": 4,
    "redis": 4,

    # Cloud
    "aws": 4,
    "azure": 3,
    "gcp": 3,

    # DevOps
    "docker": 4,
    "kubernetes": 4,
    "jenkins": 3,
    "ci/cd": 3,
    "linux": 3,

    # Messaging
    "kafka": 4,
    "rabbitmq": 4,

    # Development tools
    "git": 3,
    "github": 2,
    "maven": 3,
    "postman": 2,

    # Testing
    "junit": 3,
    "mockito": 3,

    # Frontend
    "javascript": 2,
    "typescript": 2,
    "html": 1,
    "css": 1,
    "angular": 2,
    "react": 2,

    # Other languages
    "python": 2,
    "c#": 2,
    "golang": 2,

    # Development practices
    "sdlc": 2,
    "agile": 2,
    "waterfall": 1,

    # Generic / secondary concepts
    "database": 1,
    "deployment": 1,
    "monitoring": 1,
    "authentication": 2,
    "authorization": 2,
    "oauth": 2,
}


# ============================================================
# SKILL ALIASES
# ============================================================

SKILL_ALIASES = {

    "java": [
        "java",
        "core java",
        "java programming",
    ],

    "spring": [
        "spring",
        "spring framework",
    ],

    "spring boot": [
        "spring boot",
        "springboot",
        "spring-boot",
    ],

    "spring mvc": [
        "spring mvc",
    ],

    "spring data jpa": [
        "spring data jpa",
        "spring-data-jpa",
    ],

    "hibernate": [
        "hibernate",
    ],

    "jdbc": [
        "jdbc",
    ],

    "sql": [
        "sql",
        "sql database",
        "sql databases",
    ],

    "mysql": [
        "mysql",
        "my sql",
    ],

    "postgresql": [
        "postgresql",
        "postgres",
        "postgre sql",
    ],

    "mongodb": [
        "mongodb",
        "mongo db",
        "mongo",
    ],

    "redis": [
        "redis",
        "redis cache",
        "redis caching",
    ],

    "rest api": [
        "rest api",
        "rest apis",
        "restful api",
        "restful apis",
        "restful web service",
        "restful web services",
    ],

    "microservices": [
        "microservices",
        "micro-services",
        "micro service architecture",
    ],

    "dsa": [
        "dsa",
        "data structures and algorithms",
        "data structure and algorithms",
        "algorithmic problem solving",
    ],

    "oop": [
        "oop",
        "object oriented programming",
        "object-oriented programming",
        "object oriented design",
    ],

    "multithreading": [
        "multithreading",
        "multi-threading",
        "multi threading",
        "concurrency",
        "concurrent programming",
    ],

    "git": [
        "git",
        "git version control",
    ],

    "github": [
        "github",
        "git hub",
    ],

    "maven": [
        "maven",
        "apache maven",
    ],

    "postman": [
        "postman",
    ],

    "junit": [
        "junit",
        "junit 4",
        "junit 5",
    ],

    "mockito": [
        "mockito",
    ],

    "aws": [
        "aws",
        "amazon web services",
    ],

    "azure": [
        "azure",
        "microsoft azure",
    ],

    "gcp": [
        "gcp",
        "google cloud",
        "google cloud platform",
    ],

    "docker": [
        "docker",
        "containerization",
        "containerized applications",
        "containerised applications",
    ],

    "kubernetes": [
        "kubernetes",
        "k8s",
    ],

    "jenkins": [
        "jenkins",
    ],

    "ci/cd": [
        "ci/cd",
        "ci cd",
        "cicd",
        "continuous integration",
        "continuous delivery",
        "continuous deployment",
    ],

    "linux": [
        "linux",
        "unix",
    ],

    "kafka": [
        "kafka",
        "apache kafka",
    ],

    "rabbitmq": [
        "rabbitmq",
        "rabbit mq",
    ],

    "javascript": [
        "javascript",
        "java script",
    ],

    "typescript": [
        "typescript",
        "type script",
    ],

    "html": [
        "html",
        "html5",
    ],

    "css": [
        "css",
        "css3",
    ],

    "angular": [
        "angular",
        "angular.js",
        "angularjs",
    ],

    "react": [
        "react",
        "react.js",
        "reactjs",
    ],

    "python": [
        "python",
        "python3",
    ],

    "c#": [
        "c#",
        "c sharp",
        "c-sharp",
    ],

    "golang": [
        "golang",
        "go programming language",
    ],

    "sdlc": [
        "sdlc",
        "software development life cycle",
        "software development lifecycle",
    ],

    "agile": [
        "agile",
        "agile methodology",
        "agile development",
    ],

    "waterfall": [
        "waterfall",
        "waterfall model",
    ],

    "database": [
        "database",
        "databases",
        "database systems",
        "database management",
    ],

    "deployment": [
        "deployment",
        "deployments",
        "application deployment",
        "software deployment",
    ],

    "monitoring": [
        "monitoring",
        "application monitoring",
        "system monitoring",
    ],

    "authentication": [
        "authentication",
        "user authentication",
        "api authentication",
    ],

    "authorization": [
        "authorization",
        "authorisation",
        "access control",
    ],

    "oauth": [
        "oauth",
        "oauth2",
        "oauth 2.0",
    ],
}


# ============================================================
# GENERIC SKILL SUPPRESSION
# ============================================================

GENERIC_SUPPRESSION = {

    "database": {
        "sql",
        "mysql",
        "postgresql",
        "mongodb",
    },

    "deployment": {
        "docker",
        "kubernetes",
        "jenkins",
        "ci/cd",
    },

    "monitoring": {
        "kubernetes",
        "aws",
        "azure",
        "gcp",
    },
}


# ============================================================
# TEXT NORMALIZATION
# ============================================================

def normalize_text(text):

    if not text:
        return ""

    text = str(text).lower()

    text = (
        text
        .replace("–", "-")
        .replace("—", "-")
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    text = re.sub(
        r"\bci\s*/\s*cd\b",
        "ci/cd",
        text
    )

    text = re.sub(
        r"\bcicd\b",
        "ci/cd",
        text
    )

    return text.strip()


# ============================================================
# PHRASE DETECTION
# ============================================================

def phrase_present(text, phrase):

    phrase = normalize_text(phrase)

    if not phrase:
        return False

    return bool(
        re.search(
            r"(?<!\w)"
            + re.escape(phrase)
            + r"(?!\w)",
            text
        )
    )


# ============================================================
# EXTRACT JOB SKILLS
# ============================================================

def extract_job_skills(text):

    normalized = normalize_text(text)

    found = set()

    for canonical, aliases in SKILL_ALIASES.items():

        for alias in aliases:

            if phrase_present(
                normalized,
                alias
            ):

                found.add(canonical)
                break

    # Remove generic skills when a concrete
    # technology already represents them.

    for generic, concrete in GENERIC_SUPPRESSION.items():

        if (
            generic in found
            and found.intersection(concrete)
        ):

            found.discard(generic)

    return found


# ============================================================
# NORMALIZE RESUME SKILLS
# ============================================================

def normalize_resume_skills(skills):

    normalized = set()

    for raw in skills:

        value = normalize_text(raw)

        if not value:
            continue

        canonical = None

        for name, aliases in SKILL_ALIASES.items():

            if (
                value == normalize_text(name)
                or any(
                    value == normalize_text(alias)
                    for alias in aliases
                )
            ):

                canonical = name
                break

        normalized.add(
            canonical or value
        )

    return normalized


canonical_resume_skills = normalize_resume_skills(
    resume_skills
)


# ============================================================
# SCORE HELPERS
# ============================================================

def skill_category(skill):

    if skill in CORE_SKILLS:
        return "core"

    if skill in SUPPORTING_SKILLS:
        return "supporting"

    if skill in OPTIONAL_SKILLS:
        return "optional"

    return "other"


def skill_weight(skill):

    return job_skill_weights.get(
        skill,
        1
    )


# ============================================================
# MATCH RESUME
# ============================================================

def match_resume(job_description):

    job_skills = extract_job_skills(
        job_description
    )

    if not job_skills:

        return (
            0,
            set(),
            set()
        )

    matched = (
        canonical_resume_skills
        .intersection(job_skills)
    )

    missing = (
        job_skills
        - canonical_resume_skills
    )

    # --------------------------------------------------------
    # Calculate weighted score
    #
    # Core skills are most important.
    # Supporting skills matter, but less.
    # Optional technologies have a smaller impact.
    # --------------------------------------------------------

    total_weight = 0
    matched_weight = 0

    for skill in job_skills:

        base_weight = skill_weight(
            skill
        )

        category = skill_category(
            skill
        )

        if category == "core":

            weight = base_weight

        elif category == "supporting":

            weight = round(
                base_weight * 0.65,
                2
            )

        elif category == "optional":

            weight = round(
                base_weight * 0.35,
                2
            )

        else:

            weight = base_weight

        total_weight += weight

        if skill in matched:

            matched_weight += weight

    if total_weight == 0:

        return (
            0,
            matched,
            missing
        )

    score = round(
        (
            matched_weight
            / total_weight
        )
        * 100
    )

    # --------------------------------------------------------
    # Core skill protection
    #
    # A strong Java backend match should not be heavily
    # penalized simply because the job mentions many optional
    # technologies.
    # --------------------------------------------------------

    core_job_skills = (
        job_skills
        .intersection(CORE_SKILLS)
    )

    core_matched_skills = (
        matched
        .intersection(CORE_SKILLS)
    )

    if core_job_skills:

        core_score = round(
            (
                len(core_matched_skills)
                / len(core_job_skills)
            )
            * 100
        )

        # If the candidate matches at least 70% of the
        # core Java/backend requirements, prevent optional
        # technologies from pushing the overall score too low.

        if core_score >= 70:

            score = max(
                score,
                round(
                    55
                    + (
                        core_score
                        * 0.35
                    )
                )
            )

    return (
        score,
        matched,
        missing
    )


# ============================================================
# EXPLAIN MATCH
# ============================================================

def explain_match(job_description):

    score, matched, missing = match_resume(
        job_description
    )

    job_skills = extract_job_skills(
        job_description
    )

    return {

        "score": score,

        "job_skills": sorted(
            job_skills
        ),

        "matched_skills": sorted(
            matched
        ),

        "missing_skills": sorted(
            missing
        ),

        "resume_skills": sorted(
            canonical_resume_skills
        ),

        "core_job_skills": sorted(
            job_skills.intersection(
                CORE_SKILLS
            )
        ),

        "core_matched_skills": sorted(
            matched.intersection(
                CORE_SKILLS
            )
        ),

        "supporting_job_skills": sorted(
            job_skills.intersection(
                SUPPORTING_SKILLS
            )
        ),

        "optional_job_skills": sorted(
            job_skills.intersection(
                OPTIONAL_SKILLS
            )
        ),
    }


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    test = """
    Java backend developer with Spring Boot,
    RESTful APIs, SQL databases, Git, Docker,
    data structures and algorithms, and CI/CD.
    """

    result = explain_match(
        test
    )

    print("=" * 60)
    print("SKILL MATCHER TEST")
    print("=" * 60)

    print(
        f"Score: {result['score']} %"
    )

    print(
        "Job skills:",
        ", ".join(
            result["job_skills"]
        )
    )

    print(
        "Matched:",
        ", ".join(
            result["matched_skills"]
        )
    )

    print(
        "Missing:",
        ", ".join(
            result["missing_skills"]
        )
    )

    print(
        "Core job skills:",
        ", ".join(
            result["core_job_skills"]
        )
    )

    print(
        "Core matched:",
        ", ".join(
            result["core_matched_skills"]
        )
    )

    print("=" * 60)