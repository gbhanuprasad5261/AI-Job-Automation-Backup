"""Explicit read-only route audit, separate from application execution."""

import re
from urllib.parse import urlsplit

import easy_apply
from execution_policy import EXECUTION_POLICY
from playwright.sync_api import sync_playwright


_APPROVED_HOST = "www.linkedin.com"
_JOB_PATH_CANONICAL = re.compile(r"^/jobs/view/(\d+)/$")
_CONTEXT_ROUTE_PATTERN = "**/*"
# Keep live browser auditing disabled until a separate validation phase
# explicitly authorizes a controlled test. Unit tests may patch this gate.
ROUTE_AUDIT_BROWSER_ENABLED = False


def _normalize_approved_job_url(url):
    """Return the canonical approved destination, rejecting URL variations.

    Saved job URLs use exactly ``https://www.linkedin.com/jobs/view/<id>/``.
    Query strings, fragments, explicit ports, alternate hosts, and path
    variations are intentionally not normalized into that approval.
    """
    try:
        raw_url = str(url or "")
        if raw_url != raw_url.strip() or "?" in raw_url or "#" in raw_url:
            return None
        parsed = urlsplit(raw_url)
    except (TypeError, ValueError):
        return None

    match = _JOB_PATH_CANONICAL.fullmatch(parsed.path or "")
    if (
        parsed.scheme.casefold() != "https"
        or (parsed.hostname or "").casefold() != _APPROVED_HOST
        or parsed.netloc.casefold() != _APPROVED_HOST
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or match is None
    ):
        return None
    return f"https://{_APPROVED_HOST}/jobs/view/{match.group(1)}/"


def _linkedin_job_id(url):
    """Return an ID only for the exact approved LinkedIn URL format."""
    normalized = _normalize_approved_job_url(url)
    if normalized is None:
        return None
    return _JOB_PATH_CANONICAL.fullmatch(urlsplit(normalized).path).group(1)


def _create_isolated_browser_context(playwright):
    """Launch a fresh browser context with Service Workers blocked.

    This deliberately does not attach to CDP, use a persistent profile, or
    transfer authentication state. The caller owns and must close both
    returned objects.
    """
    browser = playwright.chromium.launch()
    try:
        context = browser.new_context(service_workers="block")
    except Exception:
        try:
            browser.close()
        except Exception:
            pass
        raise
    return browser, context


def _install_navigation_guard(context, *, approved_url, page_ref,
                              initial_navigation_pending, blocked,
                              is_approved_destination):
    """Install the shared context request guard and return its callbacks.

    The matcher is private dependency injection. Production and local-smoke
    callers use separate fixed wrappers below; the production audit runner
    cannot supply or configure a test matcher.
    """
    def record_blocked(url, source):
        blocked.append({"url": str(url or ""), "source": source})

    def abort_blocked(route, url, source):
        try:
            record_blocked(url, source)
        except Exception:
            pass
        try:
            route.abort()
        except Exception:
            # A failed abort must never fall through to continue_(). A local
            # response is the last available fail-closed resolution attempt.
            try:
                route.fulfill(status=403, body="Blocked by route-audit policy")
            except Exception:
                pass

    def constrain_context_requests(route):
        request_url = ""
        try:
            request = route.request
            request_url = request.url
            request_page = request.frame.page
            method = request.method.upper()
            resource_type = request.resource_type
            is_navigation = request.is_navigation_request()

            # new_page() may issue this local initialization request before
            # the audit page has been assigned to page_ref. No request is
            # allowed until ownership and policy can be established.
            if page_ref["value"] is None:
                abort_blocked(route, request_url, "unassigned-page")
                return

            audit_page = page_ref["value"]
            if request_page is not audit_page:
                abort_blocked(route, request_url, "unowned-page")
                return

            # No subresource destination has been established as necessary or
            # safe. Permit only one initial, exact-target main-frame GET
            # document request; block every other method/resource/destination.
            if method != "GET":
                abort_blocked(route, request_url, "request-method")
                return
            if not is_navigation or resource_type != "document":
                abort_blocked(route, request_url, "request-resource-type")
                return
            if request.frame != audit_page.main_frame:
                abort_blocked(route, request_url, "non-main-frame-navigation")
                return
            if not initial_navigation_pending["value"]:
                abort_blocked(route, request_url, "audit-page-navigation")
                return
            if not is_approved_destination(request_url, approved_url):
                abort_blocked(route, request_url, "audit-page-navigation")
                return

            initial_navigation_pending["value"] = False
            route.continue_()
        except Exception:
            try:
                if not request_url:
                    request_url = route.request.url
            except Exception:
                pass
            abort_blocked(route, request_url, "route-guard-error")

    context.route(_CONTEXT_ROUTE_PATTERN, constrain_context_requests)
    return constrain_context_requests, record_blocked


def _install_production_navigation_guard(context, *, approved_url,
                                         page_ref,
                                         initial_navigation_pending, blocked):
    """Install the production guard with strict canonical LinkedIn matching."""
    return _install_navigation_guard(
        context,
        approved_url=approved_url,
        page_ref=page_ref,
        initial_navigation_pending=initial_navigation_pending,
        blocked=blocked,
        is_approved_destination=lambda url, approved: (
            _normalize_approved_job_url(url) == approved["value"]
        ),
    )


def _install_test_navigation_guard(context, *, approved_url,
                                   page_ref,
                                   initial_navigation_pending, blocked):
    """Install a test-only guard for one exact local URL.

    The production audit runner never calls this entry point.
    """
    return _install_navigation_guard(
        context,
        approved_url=approved_url,
        page_ref=page_ref,
        initial_navigation_pending=initial_navigation_pending,
        blocked=blocked,
        is_approved_destination=lambda url, approved: url == approved,
    )


def _result(job, job_id, selected_url, outcome, classification, reason,
            observed_url="", inspection=None):
    inspection = inspection or {}
    return {
        "selected_job_id": job_id,
        "selected_job_url": selected_url,
        "observed_page_url": observed_url,
        "classification": classification,
        "reason": reason,
        "control_evidence": inspection.get("control_evidence") or [],
        "inspection_outcome": outcome,
        "saved_easy_apply_hint": job.get("Easy Apply"),
        "validated_external_href": inspection.get("validated_external_href"),
    }


def audit_recommended_jobs(recommendations=None):
    """Inspect selected LinkedIn job pages and return in-memory route evidence.

    Only the selected job-detail URL may be navigated to. Other navigation
    requests are aborted. No application handlers or persistence functions run.
    """
    jobs = easy_apply.get_recommended_jobs() if recommendations is None else list(recommendations)
    targets, results, counts = [], [], {}
    for candidate in jobs:
        job = candidate if isinstance(candidate, dict) else {}
        url = str(job.get("Link") or job.get("URL") or "")
        job_id = _linkedin_job_id(url)
        if job_id is None:
            results.append(_result(
                job, None, url, "SELECTED_URL_INVALID", "AMBIGUOUS",
                "Selected row is not an absolute HTTPS LinkedIn job-detail URL.",
            ))
            continue
        counts[job_id] = counts.get(job_id, 0) + 1
        targets.append((job, job_id, url))

    pending = []
    for job, job_id, url in targets:
        if counts[job_id] > 1:
            results.append(_result(
                job, job_id, url, "DUPLICATE_SELECTED_ID", "AMBIGUOUS",
                "Duplicate selected job ID; no page was inspected.",
            ))
        else:
            pending.append((job, job_id, url))

    if not EXECUTION_POLICY.allows_browser_actions():
        results.extend(_result(
            job, job_id, url, "DRY_RUN_SKIPPED_BROWSER", None,
            "DRY_RUN=True; browser navigation was not attempted.",
        ) for job, job_id, url in pending)
        return results
    if not ROUTE_AUDIT_BROWSER_ENABLED:
        results.extend(_result(
            job, job_id, url, "ROUTE_AUDIT_DISABLED", None,
            "Live route auditing is disabled pending a separately authorized validation phase.",
        ) for job, job_id, url in pending)
        return results
    if not pending:
        return results

    browser = None
    page = None
    context = None
    context_route_handler = None
    page_event_handler = None
    playwright_manager = None
    playwright = None
    try:
        playwright_manager = sync_playwright()
        playwright = playwright_manager.start()
        browser, context = _create_isolated_browser_context(playwright)
        page_ref = {"value": None}
        approved_url = {"value": None}
        initial_navigation_pending = {"value": False}
        blocked = []
        # Context routing is installed before creation/navigation of the
        # audit page so a popup's first document request is covered too.
        context_route_handler, record_blocked = _install_production_navigation_guard(
            context,
            approved_url=approved_url,
            page_ref=page_ref,
            initial_navigation_pending=initial_navigation_pending,
            blocked=blocked,
        )
        page = context.new_page()
        page_ref["value"] = page

        def reject_unexpected_page(new_page):
            if new_page is page:
                return
            try:
                record_blocked(getattr(new_page, "url", ""), "unexpected-page-event")
            except Exception:
                pass
            try:
                new_page.close()
            except Exception:
                pass

        page_event_handler = reject_unexpected_page
        context.on("page", page_event_handler)

        for job, job_id, url in pending:
            approved_url["value"] = _normalize_approved_job_url(url)
            initial_navigation_pending["value"] = True
            blocked.clear()
            try:
                response = page.goto(url, wait_until="domcontentloaded", timeout=30000)
            except Exception as exc:
                unexpected = bool(blocked)
                results.append(_result(
                    job, job_id, url,
                    "UNEXPECTED_NAVIGATION_BLOCKED" if unexpected else "NAVIGATION_FAILED",
                    "AMBIGUOUS" if unexpected else "INACCESSIBLE",
                    ("Unexpected navigation was blocked by the context-level policy; "
                     "the audit stopped without retrying.") if unexpected
                    else f"LinkedIn page navigation failed ({type(exc).__name__}).",
                    str(getattr(page, "url", "") or ""),
                ))
                if unexpected:
                    break
                continue

            if blocked:
                results.append(_result(
                    job, job_id, url, "UNEXPECTED_NAVIGATION_BLOCKED", "AMBIGUOUS",
                    "A popup or unexpected page/navigation was blocked; the audit stopped without retrying.",
                    str(getattr(page, "url", "") or ""),
                ))
                break

            observed_url = str(getattr(page, "url", "") or "")
            if _normalize_approved_job_url(observed_url) != approved_url["value"]:
                results.append(_result(
                    job, job_id, url, "UNEXPECTED_FINAL_URL", "AMBIGUOUS",
                    "Final page URL differs from the exact approved selected-job URL.", observed_url,
                ))
                break

            try:
                inspection = easy_apply.inspect_application_route(
                    page, job, navigation_succeeded=True,
                    http_status=getattr(response, "status", None) if response else None,
                )
            except Exception as exc:
                results.append(_result(
                    job, job_id, url, "ROUTE_INSPECTION_FAILED", "INACCESSIBLE",
                    f"Route inspector failed ({type(exc).__name__}).", observed_url,
                ))
                continue

            inspector_url = str(inspection.get("observed_page_url") or observed_url)
            if (inspection.get("selected_job_id") != job_id
                    or _normalize_approved_job_url(inspector_url) != approved_url["value"]):
                results.append(_result(
                    job, job_id, url, "INSPECTOR_IDENTITY_MISMATCH", "AMBIGUOUS",
                    "Route inspector result did not match the selected job ID and exact approved URL.", inspector_url,
                ))
                break
            if blocked:
                results.append(_result(
                    job, job_id, url, "UNEXPECTED_NAVIGATION_BLOCKED", "AMBIGUOUS",
                    "A popup or unexpected page/navigation was blocked during inspection; "
                    "the audit stopped without retrying.",
                    str(getattr(page, "url", "") or ""),
                ))
                break
            results.append(_result(
                job, job_id, url,
                inspection.get("inspection_outcome") or "PAGE_INSPECTED",
                inspection.get("classification"),
                inspection.get("reason") or "No reason supplied by route inspector.",
                inspector_url, inspection,
            ))
    except Exception as exc:
        completed = {r.get("selected_job_id") for r in results}
        results.extend(_result(
            job, job_id, url, "ROUTE_AUDIT_FAILED", "INACCESSIBLE",
            f"Route-audit session failed ({type(exc).__name__}).",
        ) for job, job_id, url in pending if job_id not in completed)
    finally:
        if context is not None and page_event_handler is not None:
            try:
                context.remove_listener("page", page_event_handler)
            except Exception:
                pass
        if page is not None:
            try:
                page.close()
            except Exception:
                pass
        if context is not None and context_route_handler is not None:
            try:
                context.unroute(_CONTEXT_ROUTE_PATTERN, context_route_handler)
            except Exception:
                pass
        if context is not None:
            try:
                context.close()
            except Exception:
                pass
        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass
        if playwright is not None:
            try:
                playwright.stop()
            except Exception:
                pass
    return results


def run_route_audit():
    """Separately invoked API: select recommendations, then inspect routes."""
    return audit_recommended_jobs(easy_apply.get_recommended_jobs())


def main():
    """CLI entry point; prints in-memory observations and writes no artifacts."""
    results = run_route_audit()
    for result in results:
        state = result.get("classification") or result.get("inspection_outcome")
        print(f"{result.get('selected_job_id') or 'unknown'}: {state} - {result['reason']}")
    return results


if __name__ == "__main__":
    main()
