# AI Job Automation - Updated

This package contains the current project modules with the latest application-form
and daily-limit fixes.

## Updated behavior

- Minimum match score: 70%
- Daily confirmed application limit: 15
- Uses LinkedIn job ID for tracker identity
- Avoids re-offering APPLIED / SUBMITTED / INTERVIEW / REJECTED / WITHDRAWN jobs
- Handles LinkedIn navigation timeouts more gracefully
- Auto-submit follows `AUTO_SUBMIT`
- Application form knows the supplied contact, education, CTC, notice period,
  work-eligibility, relocation, internship, shift/weekend, disability/criminal-history,
  and technology-experience answers
- Unknown required questions remain a safety stop

## Replace

Copy these files into the project root:

- config.py
- application_tracker.py
- job_analyzer.py
- skill_matcher.py
- application_form.py
- easy_apply.py

Keep your existing `.env`, `resume/resume.pdf`, `data/`, and other project files.

## Test

PowerShell:

```powershell
.\venv\Scripts\python.exe -m py_compile config.py application_tracker.py job_analyzer.py skill_matcher.py application_form.py easy_apply.py
.\venv\Scripts\python.exe skill_matcher.py
.\venv\Scripts\python.exe job_analyzer.py
.\start_chrome.bat
.\venv\Scripts\python.exe easy_apply.py
```

Do not commit `.env`, LinkedIn credentials, or private resume files to GitHub.
