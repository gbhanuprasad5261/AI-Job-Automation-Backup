import csv
import os
from datetime import datetime, date

INPUT_FILE = "data/job_analysis.csv"
OUTPUT_FILE = "data/application_tracker.csv"

STATUSES = [
    "NOT APPLIED", "APPLIED", "ASSESSMENT",
    "INTERVIEW", "OFFER", "REJECTED"
]

FIELDS = [
    "Title", "Company", "Location", "Match Score", "Priority",
    "Easy Apply", "Application Status", "Applied Date", "Link", "Status",
]


def load_tracker():
    if not os.path.exists(OUTPUT_FILE):
        print("application_tracker.csv not found.")
        return []
    with open(OUTPUT_FILE, "r", encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))
    for row in rows:
        status = (row.get("Status") or row.get("Application Status") or "NOT APPLIED").strip().upper()
        row["Status"] = status
        row["Application Status"] = status
    return rows


def save_tracker(jobs):
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        for row in jobs:
            status = (row.get("Status") or row.get("Application Status") or "NOT APPLIED").strip().upper()
            row["Status"] = status
            row["Application Status"] = status
            writer.writerow({field: row.get(field, "") for field in FIELDS})


def count_confirmed_today():
    today = date.today().isoformat()
    return sum(
        1 for row in load_tracker()
        if (row.get("Status") or "").upper() in {"APPLIED", "SUBMITTED"}
        and (row.get("Applied Date") or "") == today
    )


def show_jobs(jobs):
    print("\n" + "=" * 70)
    print("APPLICATION TRACKER")
    print("=" * 70)
    for index, job in enumerate(jobs, start=1):
        print(f"\n{index}. {job.get('Title','')}")
        print(f"   Company : {job.get('Company') or 'Not available'}")
        print(f"   Location: {job.get('Location') or 'Not available'}")
        print(f"   Score   : {job.get('Match Score','')}")
        print(f"   Priority: {job.get('Priority','')}")
        print(f"   Status  : {job.get('Application Status','NOT APPLIED')}")


def update_status(jobs):
    show_jobs(jobs)
    print("\n" + "=" * 70)
    print("UPDATE APPLICATION STATUS")
    print("=" * 70)
    try:
        choice = int(input(f"\nEnter job number (1-{len(jobs)}): "))
        if not 1 <= choice <= len(jobs):
            print("Invalid job number."); return
    except ValueError:
        print("Please enter a valid number."); return

    job = jobs[choice - 1]
    print(f"\nSelected: {job['Title']}")
    for index, status in enumerate(STATUSES, 1):
        print(f"{index}. {status}")
    try:
        status_choice = int(input("\nSelect status: "))
        if not 1 <= status_choice <= len(STATUSES):
            print("Invalid status."); return
    except ValueError:
        print("Please enter a valid number."); return

    new_status = STATUSES[status_choice - 1]
    job["Application Status"] = new_status
    job["Status"] = new_status

    if new_status in {"APPLIED", "ASSESSMENT", "INTERVIEW", "OFFER"} and not job.get("Applied Date"):
        job["Applied Date"] = datetime.now().strftime("%Y-%m-%d")
    elif new_status == "NOT APPLIED":
        job["Applied Date"] = ""

    save_tracker(jobs)
    print("\nSTATUS UPDATED")
    print(f"Job    : {job['Title']}")
    print(f"Status : {new_status}")
    print(f"Date   : {job.get('Applied Date') or 'Not applied'}")


def show_summary(jobs):
    counts = {status: 0 for status in STATUSES}
    for job in jobs:
        status = job.get("Application Status", "NOT APPLIED")
        if status in counts:
            counts[status] += 1
    print("\n" + "=" * 70)
    print("APPLICATION SUMMARY")
    print("=" * 70)
    print(f"Total Jobs   : {len(jobs)}")
    for status in STATUSES:
        print(f"{status.title():12}: {counts[status]}")


def main():
    jobs = load_tracker()
    if not jobs:
        return
    while True:
        print("\n" + "=" * 70)
        print("AI JOB APPLICATION TRACKER")
        print("=" * 70)
        print("\n1. View Jobs\n2. Update Status\n3. View Summary\n4. Exit")
        choice = input("\nChoose an option: ").strip()
        if choice == "1":
            show_jobs(jobs)
        elif choice == "2":
            update_status(jobs); jobs = load_tracker()
        elif choice == "3":
            show_summary(jobs)
            print(f"\nConfirmed applications today: {count_confirmed_today()}")
        elif choice == "4":
            print("\nExiting tracker..."); break
        else:
            print("\nInvalid option. Please choose 1-4.")


if __name__ == "__main__":
    main()
