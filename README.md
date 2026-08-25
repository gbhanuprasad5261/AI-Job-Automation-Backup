# 🤖 AI Job Automation

<div align="center">

### AI-Powered LinkedIn Job Search, Resume Matching & Application Automation

Automate job discovery, analyze resume compatibility, identify skill gaps, rank suitable opportunities, and streamline supported LinkedIn Easy Apply applications using Python and Playwright.

</div>

---

## 📖 Overview

Applying for software engineering jobs manually is repetitive and time-consuming.

**AI Job Automation** is a Python-based personal job search automation system designed to reduce the repetitive work involved in:

- Finding relevant jobs
- Collecting job information
- Extracting job descriptions
- Comparing jobs with a resume
- Calculating resume-to-job match scores
- Identifying missing skills
- Ranking suitable opportunities
- Detecting Easy Apply availability
- Filling supported application fields
- Tracking submitted applications

The project uses **Python, Playwright, Chrome DevTools Protocol (CDP), PDF parsing, CSV-based data processing, and rule-based resume/job matching**.

The long-term goal is to build a personal AI-powered job assistant that can handle the repetitive parts of the job search process while keeping the user in control of uncertain or important application decisions.

---

# 🎯 Project Goal

The main goal of this project is to reduce the repetitive work involved in applying for software engineering jobs.

### Current workflow

```text
LinkedIn
   │
   ▼
Job Search
   │
   ▼
Job Collection
   │
   ▼
Job Details Extraction
   │
   ▼
Resume & Skill Matching
   │
   ▼
Match Score
   │
   ▼
Job Ranking
   │
   ▼
Eligibility Filtering
   │
   ▼
Easy Apply Detection
   │
   ▼
Application Form
   │
   ▼
Supported Form Filling
   │
   ▼
Required Field Validation
   │
   ▼
Review
   │
   ▼
Application Submission
   │
   ▼
Application Tracking


---

## Current production safety rules

- Target locations: Bengaluru, Hyderabad, Chennai, and Remote.
- Minimum match score is configurable (`MIN_MATCH_SCORE`, default 70).
- Confirmed applications are limited per day (`DAILY_APPLICATION_LIMIT`, default 15).
- LinkedIn applications are marked `APPLIED` only after a visible submission confirmation.
- Unknown required questions are never guessed; the job is skipped safely.
- Tracker matching prefers the stable LinkedIn job ID/URL instead of title alone.
- External ATS detection is separated from the proven LinkedIn flow. The current external module prepares obvious fields but does **not** auto-submit unknown external forms.

## Recommended commands

```powershell
python job_search.py
python job_details.py
python job_analyzer.py
.\start_chrome.bat
python easy_apply.py
python application_tracker.py
```

For LinkedIn automation, keep the Chrome CDP session running on port 9222.
