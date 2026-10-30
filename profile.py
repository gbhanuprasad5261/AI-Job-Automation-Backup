import os
# ============================================
# USER APPLICATION PROFILE
# ============================================

PROFILE = {

    # Personal Information
    "first_name": "Bhanu",
    "last_name": "Prasad",

    "phone": "",
    "email": "",

    # Location
    "city": "Chittoor",
    "state": "Andhra Pradesh",
    "country": "India",

    # Education
    "degree": "Bachelor of Technology",
    "field_of_study": "Computer Science and Engineering",
    "specialization": "Artificial Intelligence and Data Science",
    "graduation_year": "2025",

    # Experience
    "experience_years": "0",

    # Skills
    "skills": [
        "Java",
        "Spring",
        "Spring Boot",
        "Spring MVC",
        "Spring Data JPA",
        "Hibernate",
        "JDBC",
        "SQL",
        "MySQL",
        "REST API",
        "Microservices",
        "Git",
        "GitHub",
        "Maven",
        "Postman",
        "JUnit",
        "Mockito"
    ],

    # Resume
    "resume_path": "resume/resume.pdf"
}

def get_application_profile():
    """Return normalized contact/resume values from the shared profile.

    Explicit existing environment overrides retain precedence for location,
    company, and resume path. Missing profile fields remain empty; this helper
    never invents contact or employment values.
    """
    def text_value(value):
        return value.strip() if isinstance(value, str) else ""

    def environment_or_profile(environment_name, profile_value):
        if environment_name in os.environ:
            return text_value(os.environ[environment_name])
        return profile_value

    profile_name = " ".join(
        part for part in (
            text_value(PROFILE.get("first_name")),
            text_value(PROFILE.get("last_name")),
        ) if part
    )
    name = environment_or_profile("APPLICANT_NAME", profile_name)
    name_parts = name.split(maxsplit=1)
    first_name = name_parts[0] if name_parts else ""
    last_name = name_parts[1] if len(name_parts) > 1 else ""

    city = environment_or_profile(
        "APPLICANT_CITY", text_value(PROFILE.get("city"))
    )
    state = environment_or_profile(
        "APPLICANT_STATE", text_value(PROFILE.get("state"))
    )
    country = environment_or_profile(
        "APPLICANT_COUNTRY", text_value(PROFILE.get("country"))
    )
    profile_location = ", ".join(part for part in (city, state, country) if part)
    degree = environment_or_profile(
        "APPLICANT_DEGREE", text_value(PROFILE.get("degree"))
    )
    field_of_study = environment_or_profile(
        "APPLICANT_FIELD_OF_STUDY", text_value(PROFILE.get("field_of_study"))
    )
    graduation_year = environment_or_profile(
        "GRADUATION_YEAR", text_value(PROFILE.get("graduation_year"))
    )
    experience_years = environment_or_profile(
        "YEARS_OF_EXPERIENCE", text_value(PROFILE.get("experience_years"))
    )

    return {
        "name": name,
        "first_name": first_name,
        "last_name": last_name,
        "email": environment_or_profile(
            "APPLICANT_EMAIL", text_value(PROFILE.get("email"))
        ),
        "phone": environment_or_profile(
            "APPLICANT_PHONE", text_value(PROFILE.get("phone"))
        ),
        "city": city,
        "state": state,
        "country": country,
        "degree": degree,
        "field_of_study": field_of_study,
        "graduation_year": graduation_year,
        "experience_years": experience_years,
        "current_location": environment_or_profile(
            "CURRENT_LOCATION", profile_location
        ),
        "current_company": environment_or_profile(
            "CURRENT_COMPANY", text_value(PROFILE.get("current_company"))
        ),
        "resume_path": environment_or_profile(
            "RESUME_PATH", text_value(PROFILE.get("resume_path"))
        ),
    }


_PROFILE_COMPLETENESS_FIELDS = frozenset(PROFILE) | frozenset(
    {
        "name", "current_location", "current_company", "street_address",
        "employment_history", "internship_history", "project_experience",
        "availability",
    }
)


def validate_profile_completeness(required_fields=(), optional_fields=()):
    """Classify requested profile fields without returning their values.

    Required known fields with absent or blank data are reported as missing.
    Blank optional fields are reported separately. Unknown field names are
    unsupported; this helper never supplies defaults or edits the profile.
    """
    def field_names(fields):
        if isinstance(fields, str):
            fields = (fields,)
        try:
            iterator = iter(fields)
        except TypeError:
            return (None,)

        names = []
        for field in iterator:
            if not isinstance(field, str):
                names.append(None)
                continue
            name = field.strip().lower()
            if name and name not in names:
                names.append(name)
        return tuple(names)

    required = field_names(required_fields)
    optional = field_names(optional_fields)
    required_set = set(required)
    optional = tuple(field for field in optional if field not in required_set)

    profile_values = dict(PROFILE)
    profile_values.update(get_application_profile())

    def is_configured(value):
        if value is None:
            return False
        if isinstance(value, str):
            return bool(value.strip())
        if isinstance(value, (list, tuple, set, dict)):
            return bool(value)
        return True

    result = {"configured": [], "missing": [], "optional": [], "unsupported": []}
    for field in (*required, *optional):
        if field is None:
            result["unsupported"].append("<invalid-field-name>")
            continue
        if field not in _PROFILE_COMPLETENESS_FIELDS:
            result["unsupported"].append(field)
            continue

        if is_configured(profile_values.get(field)):
            result["configured"].append(field)
        elif field in required_set:
            result["missing"].append(field)
        else:
            result["optional"].append(field)

    for values in result.values():
        values[:] = sorted(set(values))
    return result
