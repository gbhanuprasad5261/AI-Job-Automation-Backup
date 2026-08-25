import csv
import os
from datetime import datetime


INPUT_FILE = "data/job_analysis.csv"
OUTPUT_FILE = "data/application_tracker.csv"


STATUSES = [
    "NOT APPLIED",
    "APPLIED",
    "ASSESSMENT",
    "INTERVIEW",
    "OFFER",
    "REJECTED"
]


FIELDS = [
    "Title",
    "Company",
    "Location",
    "Match Score",
    "Priority",
    "Easy Apply",
    "Application Status",
    "Applied Date",
    "Link",
    "Status",
]


def load_tracker():
    if not os.path.exists(OUTPUT_FILE):
        print("application_tracker.csv not found.")
        return []

    with open(OUTPUT_FILE, "r", encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        rows = list(reader)

    for row in rows:
        status = (row.get("Status") or row.get("Application Status") or "NOT APPLIED").strip()
        row["Status"] = status
        row["Application Status"] = status

    return rows


def save_tracker(jobs):
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)

    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=FIELDS,
            extrasaction="ignore",
        )
        writer.writeheader()

        for row in jobs:
            status = (row.get("Status") or row.get("Application Status") or "NOT APPLIED").strip()
            row["Status"] = status
            row["Application Status"] = status
            writer.writerow({field: row.get(field, "") for field in FIELDS})


def show_jobs(jobs):

    print()
    print("=" * 70)
    print("APPLICATION TRACKER")
    print("=" * 70)

    for index, job in enumerate(jobs, start=1):

        print()
        print(f"{index}. {job['Title']}")
        print(f"   Company : {job['Company'] or 'Not available'}")
        print(f"   Location: {job['Location'] or 'Not available'}")
        print(f"   Score   : {job['Match Score']}")
        print(f"   Priority: {job['Priority']}")
        print(f"   Status  : {job['Application Status']}")


def update_status(jobs):

    show_jobs(jobs)

    print()
    print("=" * 70)
    print("UPDATE APPLICATION STATUS")
    print("=" * 70)

    try:
        choice = int(
            input(
                f"\nEnter job number (1-{len(jobs)}): "
            )
        )

        if choice < 1 or choice > len(jobs):
            print("Invalid job number.")
            return

    except ValueError:
        print("Please enter a valid number.")
        return

    job = jobs[choice - 1]

    print()
    print(f"Selected: {job['Title']}")

    print()
    print("Available statuses:")

    for index, status in enumerate(
        STATUSES,
        start=1
    ):
        print(f"{index}. {status}")

    try:
        status_choice = int(
            input(
                "\nSelect status: "
            )
        )

        if status_choice < 1 or status_choice > len(STATUSES):
            print("Invalid status.")
            return

    except ValueError:
        print("Please enter a valid number.")
        return

    new_status = STATUSES[status_choice - 1]

    job["Application Status"] = new_status

    # Add date when application is submitted
    if new_status in [
        "APPLIED",
        "ASSESSMENT",
        "INTERVIEW",
        "OFFER"
    ]:

        if not job["Applied Date"]:
            job["Applied Date"] = (
                datetime.now().strftime("%Y-%m-%d")
            )

    elif new_status == "NOT APPLIED":

        job["Applied Date"] = ""

    save_tracker(jobs)

    print()
    print("=" * 70)
    print("STATUS UPDATED")
    print("=" * 70)

    print(f"Job    : {job['Title']}")
    print(f"Status : {job['Application Status']}")
    print(
        f"Date   : "
        f"{job['Applied Date'] or 'Not applied'}"
    )


def show_summary(jobs):

    counts = {}

    for status in STATUSES:
        counts[status] = 0

    for job in jobs:

        status = job.get(
            "Application Status",
            "NOT APPLIED"
        )

        if status in counts:
            counts[status] += 1

    print()
    print("=" * 70)
    print("APPLICATION SUMMARY")
    print("=" * 70)

    print(f"Total Jobs   : {len(jobs)}")
    print(f"Not Applied  : {counts['NOT APPLIED']}")
    print(f"Applied      : {counts['APPLIED']}")
    print(f"Assessment   : {counts['ASSESSMENT']}")
    print(f"Interview    : {counts['INTERVIEW']}")
    print(f"Offers       : {counts['OFFER']}")
    print(f"Rejected     : {counts['REJECTED']}")


def main():

    jobs = load_tracker()

    if not jobs:
        return

    while True:

        print()
        print("=" * 70)
        print("AI JOB APPLICATION TRACKER")
        print("=" * 70)

        print()
        print("1. View Jobs")
        print("2. Update Status")
        print("3. View Summary")
        print("4. Exit")

        choice = input(
            "\nChoose an option: "
        ).strip()

        if choice == "1":

            show_jobs(jobs)

        elif choice == "2":

            update_status(jobs)

            # Reload latest saved data
            jobs = load_tracker()

        elif choice == "3":

            show_summary(jobs)

        elif choice == "4":

            print("\nExiting tracker...")
            break

        else:

            print(
                "\nInvalid option. "
                "Please choose 1-4."
            )


if __name__ == "__main__":
    main()