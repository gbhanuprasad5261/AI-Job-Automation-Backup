import csv
import os
from datetime import datetime, date

INPUT_FILE = "data/job_analysis.csv"
OUTPUT_FILE = "data/application_tracker.csv"

# Normal application lifecycle statuses.
STATUSES = [
    "NOT APPLIED",
    "LOGIN_REQUIRED",
    "INELIGIBLE",
    "APPLIED",
    "ASSESSMENT",
    "INTERVIEW",
    "OFFER",
    "REJECTED",
]

# Technical/automation states.
TECHNICAL_STATUSES = [
    "READY_FOR_REVIEW",
    "LOGIN_REQUIRED",
    "FAILED",
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


def normalize_status(row):
    """
    Keep Status and Application Status synchronized.
    """
    status = (
        row.get("Status")
        or row.get("Application Status")
        or "NOT APPLIED"
    )

    status = str(status).strip().upper()

    row["Status"] = status
    row["Application Status"] = status

    return status


def load_tracker():
    if not os.path.exists(OUTPUT_FILE):
        print("application_tracker.csv not found.")
        return []

    try:
        with open(
            OUTPUT_FILE,
            "r",
            encoding="utf-8",
            newline=""
        ) as file:
            rows = list(csv.DictReader(file))
    except Exception as e:
        print(f"Could not read application tracker: {e}")
        return []

    for row in rows:
        normalize_status(row)

    return rows


def save_tracker(jobs):
    """
    Safely save tracker data.

    Uses a temporary file and os.replace() so an interrupted write
    cannot leave application_tracker.csv empty/corrupted.
    """
    directory = os.path.dirname(OUTPUT_FILE) or "."
    os.makedirs(directory, exist_ok=True)

    temp_file = OUTPUT_FILE + ".tmp"

    try:
        with open(
            temp_file,
            "w",
            newline="",
            encoding="utf-8"
        ) as file:

            writer = csv.DictWriter(
                file,
                fieldnames=FIELDS,
                extrasaction="ignore",
            )

            writer.writeheader()

            for row in jobs:
                normalize_status(row)

                writer.writerow({
                    field: row.get(field, "")
                    for field in FIELDS
                })

            # Force buffered data to disk before replacement.
            file.flush()
            os.fsync(file.fileno())

        # Atomic replacement.
        os.replace(temp_file, OUTPUT_FILE)

    except Exception as e:
        print(f"Could not save application tracker: {e}")

        # Remove incomplete temporary file if it exists.
        try:
            if os.path.exists(temp_file):
                os.remove(temp_file)
        except Exception:
            pass

        raise


def count_confirmed_today():
    today = date.today().isoformat()

    return sum(
        1
        for row in load_tracker()
        if (row.get("Status") or "").upper()
        in {"APPLIED", "SUBMITTED"}
        and (row.get("Applied Date") or "") == today
    )


def show_jobs(jobs):
    print("\n" + "=" * 70)
    print("APPLICATION TRACKER")
    print("=" * 70)

    for index, job in enumerate(jobs, start=1):
        print(f"\n{index}. {job.get('Title', '')}")
        print(
            f"   Company : "
            f"{job.get('Company') or 'Not available'}"
        )
        print(
            f"   Location: "
            f"{job.get('Location') or 'Not available'}"
        )
        print(
            f"   Score   : "
            f"{job.get('Match Score', '')}"
        )
        print(
            f"   Priority: "
            f"{job.get('Priority', '')}"
        )
        print(
            f"   Status  : "
            f"{job.get('Application Status', 'NOT APPLIED')}"
        )


def update_status(jobs):
    show_jobs(jobs)

    print("\n" + "=" * 70)
    print("UPDATE APPLICATION STATUS")
    print("=" * 70)

    try:
        choice = int(
            input(
                f"\nEnter job number (1-{len(jobs)}): "
            )
        )

        if not 1 <= choice <= len(jobs):
            print("Invalid job number.")
            return

    except ValueError:
        print("Please enter a valid number.")
        return

    job = jobs[choice - 1]

    print(
        f"\nSelected: "
        f"{job.get('Title', '')}"
    )

    all_statuses = STATUSES + TECHNICAL_STATUSES

    for index, status in enumerate(
        all_statuses,
        1
    ):
        print(f"{index}. {status}")

    try:
        status_choice = int(
            input("\nSelect status: ")
        )

        if not 1 <= status_choice <= len(all_statuses):
            print("Invalid status.")
            return

    except ValueError:
        print("Please enter a valid number.")
        return

    new_status = all_statuses[status_choice - 1]

    job["Application Status"] = new_status
    job["Status"] = new_status

    if new_status in {
        "APPLIED",
        "ASSESSMENT",
        "INTERVIEW",
        "OFFER",
    }:
        if not job.get("Applied Date"):
            job["Applied Date"] = datetime.now().strftime(
                "%Y-%m-%d"
            )

    elif new_status == "NOT APPLIED":
        job["Applied Date"] = ""

    save_tracker(jobs)

    print("\nSTATUS UPDATED")
    print(
        f"Job    : "
        f"{job.get('Title', '')}"
    )
    print(
        f"Status : "
        f"{new_status}"
    )
    print(
        f"Date   : "
        f"{job.get('Applied Date') or 'Not applied'}"
    )


def show_summary(jobs):
    all_statuses = STATUSES + TECHNICAL_STATUSES

    counts = {
        status: 0
        for status in all_statuses
    }

    for row in jobs:
        status = normalize_status(row)

        if status in counts:
            counts[status] += 1

    print("\n" + "=" * 70)
    print("APPLICATION SUMMARY")
    print("=" * 70)

    print(
        f"Total Jobs   : "
        f"{len(jobs)}"
    )

    print("\nApplication statuses:")

    for status in STATUSES:
        print(
            f"{status.title():18}: "
            f"{counts[status]}"
        )

    print("\nAutomation states:")

    for status in TECHNICAL_STATUSES:
        print(
            f"{status.title():18}: "
            f"{counts[status]}"
        )


def main():
    jobs = load_tracker()

    if not jobs:
        print("No application tracker records found.")
        return

    while True:

        print("\n" + "=" * 70)
        print("AI JOB APPLICATION TRACKER")
        print("=" * 70)

        print(
            "\n1. View Jobs"
            "\n2. Update Status"
            "\n3. View Summary"
            "\n4. Exit"
        )

        choice = input(
            "\nChoose an option: "
        ).strip()

        if choice == "1":
            show_jobs(jobs)

        elif choice == "2":
            update_status(jobs)
            jobs = load_tracker()

        elif choice == "3":
            show_summary(jobs)

            print(
                f"\nConfirmed applications today: "
                f"{count_confirmed_today()}"
            )

        elif choice == "4":
            print("\nExiting tracker...")
            break

        else:
            print("\nInvalid option. Please choose 1-4.")


if __name__ == "__main__":
    main()