"""Central execution policy for read-only dry runs."""

import config


DRY_RUN_SKIPPED_BROWSER = "DRY_RUN_SKIPPED_BROWSER"


class ExecutionPolicy:
    """Centralize dry-run decisions and in-memory candidate results."""

    @property
    def dry_run(self) -> bool:
        return bool(config.DRY_RUN)

    def allows_browser_actions(self) -> bool:
        return not self.dry_run

    def allows_persistence(self) -> bool:
        return not self.dry_run

    def allows_diagnostic_artifacts(self) -> bool:
        return not self.dry_run

    def dry_run_result(self, job: dict) -> dict:
        hint = str(job.get("Easy Apply") or "").strip()
        normalized_hint = hint.casefold()

        if normalized_hint in {"yes", "true", "1"}:
            route_hint = "LinkedIn Easy Apply"
        elif normalized_hint in {"no", "false", "0"}:
            route_hint = "External application candidate"
        else:
            route_hint = None

        return {
            "status": DRY_RUN_SKIPPED_BROWSER,
            "job_title": job.get("Title", ""),
            "company": job.get("Company", ""),
            "job_url": job.get("Link") or job.get("URL") or "",
            "match_score": job.get("Match Score", ""),
            "application_eligible": job.get("Application Eligible", ""),
            "experience_skip": job.get("Experience Skip", ""),
            "easy_apply_saved_hint": hint or None,
            "route_hint": route_hint,
            "route_hint_source": "saved CSV" if route_hint else None,
            "live_route_confirmed": False,
        }


EXECUTION_POLICY = ExecutionPolicy()
