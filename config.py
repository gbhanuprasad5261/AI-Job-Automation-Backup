from dotenv import load_dotenv
import os

load_dotenv()

LINKEDIN_EMAIL = os.getenv("LINKEDIN_EMAIL")
LINKEDIN_PASSWORD = os.getenv("LINKEDIN_PASSWORD")

# ---------------------------------------------------------------------------
# Job targeting
# ---------------------------------------------------------------------------
TARGET_LOCATIONS = (
    "bengaluru",
    "bangalore",
    "hyderabad",
    "chennai",
    "remote",
    "india (remote)",
)

TARGET_LOCATION_DISPLAY = "Bengaluru / Hyderabad / Chennai / Remote"

# Minimum resume match required before an application is considered.
MIN_MATCH_SCORE = int(os.getenv("MIN_MATCH_SCORE", "70"))

# Maximum confirmed applications per calendar day.
DAILY_APPLICATION_LIMIT = int(os.getenv("DAILY_APPLICATION_LIMIT", "15"))

# Number of jobs collected by each search pass.
MAX_JOBS = int(os.getenv("MAX_JOBS", "30"))

# Search configuration.
SEARCH_KEYWORDS = (
    "Java Backend Developer",
    "Java Software Engineer",
    "Software Engineer Backend",
    "Junior Software Engineer",
)

EASY_APPLY_FILTER = False

# Application safety.
AUTO_SUBMIT = os.getenv("AUTO_SUBMIT", "true").strip().lower() == "true"
UNKNOWN_QUESTIONS_POLICY = "SKIP"

CHROME_CDP_URL = os.getenv(
    "CHROME_CDP_URL",
    "http://127.0.0.1:9222",
)
