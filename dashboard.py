import csv
import os
from collections import Counter


TRACKER_FILE = "data/application_tracker.csv"


def load_jobs():

    if not os.path.exists(TRACKER_FILE):
        print("application_tracker.csv not found.")
        print("Run application_tracker.py first.")
        return []

    with open(
        TRACKER_FILE,
        "r",
        encoding="utf-8"
    ) as file:

        reader = csv.DictReader(file)

        return list(reader)


def get_score(job):

    try:
        return int(
            job.get(
                "Match Score",
                "0%"
            ).replace("%", "")
        )
    except ValueError:
        return 0


def show_dashboard(jobs):

    total_jobs = len(jobs)

    high_priority = sum(
        1 for job in jobs
        if job.get("Priority") == "HIGH"
    )

    medium_priority = sum(
        1 for job in jobs
        if job.get("Priority") == "MEDIUM"
    )

    low_priority = sum(
        1 for job in jobs
        if job.get("Priority") == "LOW"
    )

    status_counter = Counter(
        job.get(
            "Application Status",
            "NOT APPLIED"
        )
        for job in jobs
    )

    # ---------------------------------------
    # Dashboard Header
    # ---------------------------------------

    print()
    print("=" * 65)
    print("AI JOB AUTOMATION DASHBOARD")
    print("=" * 65)

    # ---------------------------------------
    # Job Statistics
    # ---------------------------------------

    print()
    print("JOB STATISTICS")
    print("-" * 65)

    print(f"Total Jobs          : {total_jobs}")
    print(f"High Priority       : {high_priority}")
    print(f"Medium Priority     : {medium_priority}")
    print(f"Low Priority        : {low_priority}")

    # ---------------------------------------
    # Application Statistics
    # ---------------------------------------

    print()
    print("APPLICATION PIPELINE")
    print("-" * 65)

    print(
        f"Not Applied         : "
        f"{status_counter.get('NOT APPLIED', 0)}"
    )

    print(
        f"Applied             : "
        f"{status_counter.get('APPLIED', 0)}"
    )

    print(
        f"Assessment          : "
        f"{status_counter.get('ASSESSMENT', 0)}"
    )

    print(
        f"Interview           : "
        f"{status_counter.get('INTERVIEW', 0)}"
    )

    print(
        f"Offers              : "
        f"{status_counter.get('OFFER', 0)}"
    )

    print(
        f"Rejected            : "
        f"{status_counter.get('REJECTED', 0)}"
    )

    # ---------------------------------------
    # Top Jobs
    # ---------------------------------------

    ranked_jobs = sorted(
        jobs,
        key=get_score,
        reverse=True
    )

    print()
    print("TOP JOB RECOMMENDATIONS")
    print("-" * 65)

    if ranked_jobs:

        for index, job in enumerate(
            ranked_jobs[:5],
            start=1
        ):

            print()
            print(
                f"{index}. "
                f"{job.get('Title', 'Unknown')}"
            )

            print(
                f"   Score    : "
                f"{job.get('Match Score', '0%')}"
            )

            print(
                f"   Priority : "
                f"{job.get('Priority', 'LOW')}"
            )

            print(
                f"   Location : "
                f"{job.get('Location') or 'Not available'}"
            )

            print(
                f"   Status   : "
                f"{job.get('Application Status', 'NOT APPLIED')}"
            )

    # ---------------------------------------
    # Easy Apply Jobs
    # ---------------------------------------

    easy_apply_jobs = [
        job for job in jobs
        if job.get(
            "Easy Apply",
            ""
        ).strip().lower() == "yes"
    ]

    print()
    print("EASY APPLY")
    print("-" * 65)

    print(
        f"Easy Apply Jobs     : "
        f"{len(easy_apply_jobs)}"
    )

    # ---------------------------------------
    # Application Rate
    # ---------------------------------------

    applied_count = (
        status_counter.get("APPLIED", 0)
        + status_counter.get("ASSESSMENT", 0)
        + status_counter.get("INTERVIEW", 0)
        + status_counter.get("OFFER", 0)
        + status_counter.get("REJECTED", 0)
    )

    if total_jobs > 0:

        application_rate = round(
            (applied_count / total_jobs) * 100
        )

    else:

        application_rate = 0

    print()
    print("APPLICATION RATE")
    print("-" * 65)

    print(
        f"Jobs with application activity : "
        f"{applied_count}/{total_jobs}"
    )

    print(
        f"Application Rate                : "
        f"{application_rate}%"
    )

    print()
    print("=" * 65)
    print("DASHBOARD COMPLETE")
    print("=" * 65)


def main():

    jobs = load_jobs()

    if not jobs:
        return

    show_dashboard(jobs)


if __name__ == "__main__":
    main()