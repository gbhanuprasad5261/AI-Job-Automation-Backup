import csv

with open("jobs.csv", encoding="utf-8") as f:
    rows = list(csv.DictReader(f))

for i, r in enumerate(rows, 1):
    easy_apply = (r.get("Easy Apply") or "").strip().lower()

    if easy_apply not in ("yes", "true", "1"):
        print(
            f"{i}. {r.get('Title', '')} | "
            f"{r.get('Company', '')} | "
            f"{r.get('Location', '')} | "
            f"Easy Apply={r.get('Easy Apply', '')} | "
            f"{r.get('Link', '')}"
        )
