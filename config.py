from dotenv import load_dotenv
import os

load_dotenv()

LINKEDIN_EMAIL = os.getenv("LINKEDIN_EMAIL")
LINKEDIN_PASSWORD = os.getenv("LINKEDIN_PASSWORD")

TARGET_LOCATIONS = (
    "bengaluru", "bangalore", "hyderabad", "chennai", "remote", "india (remote)",
)
TARGET_LOCATION_DISPLAY = "Bengaluru / Hyderabad / Chennai / Remote"

MIN_MATCH_SCORE = int(os.getenv("MIN_MATCH_SCORE", "70"))
DAILY_APPLICATION_LIMIT = int(os.getenv("DAILY_APPLICATION_LIMIT", "15"))
if DAILY_APPLICATION_LIMIT < 0:
    raise ValueError("DAILY_APPLICATION_LIMIT must be zero or greater")
MAX_JOBS = int(os.getenv("MAX_JOBS", "30"))

SEARCH_KEYWORDS = (
    "Java Backend Developer",
    "Java Software Engineer",
    "Software Engineer Backend",
    "Junior Software Engineer",
)

# Candidate selection may include both Easy Apply and external applications.
EASY_APPLY_FILTER = False

AUTO_SUBMIT = os.getenv("AUTO_SUBMIT", "false").strip().lower() in {"1", "true", "yes", "on"}

# SKIP leaves the job without submission; REVIEW leaves the form for manual completion.
UNKNOWN_QUESTIONS_POLICY = os.getenv("UNKNOWN_QUESTIONS_POLICY", "SKIP").strip().upper()
if UNKNOWN_QUESTIONS_POLICY not in {"SKIP", "REVIEW"}:
    raise ValueError("UNKNOWN_QUESTIONS_POLICY must be SKIP or REVIEW")

CHROME_CDP_URL = os.getenv(
    "CHROME_CDP_URL",
    "http://127.0.0.1:9222",
)
