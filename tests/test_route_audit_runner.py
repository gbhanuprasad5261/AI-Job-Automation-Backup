"""Behavioral tests for the separately invoked read-only route audit."""

import unittest
from unittest.mock import MagicMock, patch

import config
import easy_apply
import external_app
import route_audit


JOB = {
    "Title": "Backend Developer",
    "Company": "Example Corp",
    "Link": "https://www.linkedin.com/jobs/view/1234567890/",
    "Easy Apply": "Yes",
    "Match Score": "88%",
    "Application Eligible": "Yes",
    "Application Status": "NOT APPLIED",
}


class FakeRequest:
    def __init__(self, url, page):
        self.url = url
        self.frame = page.main_frame

    def is_navigation_request(self):
        return True


class FakeRoute:
    def __init__(self, request):
        self.request = request
        self.aborted = False
        self.continued = False

    def abort(self):
        self.aborted = True

    def continue_(self):
        self.continued = True


class FakeResponse:
    status = 200


class FakePage:
    def __init__(self, redirect_map=None, context=None):
        self.url = "about:blank"
        self.redirect_map = redirect_map or {}
        self.context = context
        self.main_frame = type("Frame", (), {"page": self})()
        self.goto_calls = []
        self.route_requests = []
        self.popup_url = None
        self.click = MagicMock()
        self.close = MagicMock()

    def _dispatch_navigation(self, url):
        route = self.context.dispatch(url, self)
        self.route_requests.append((url, route))
        return route

    def goto(self, url, **_kwargs):
        self.goto_calls.append(url)
        initial = self._dispatch_navigation(url)
        if initial.aborted:
            raise RuntimeError("navigation blocked")
        final_url = self.redirect_map.get(url, url)
        if final_url != url:
            redirect = self._dispatch_navigation(final_url)
            if redirect.aborted:
                raise RuntimeError("redirect blocked")
        self.url = final_url
        if self.popup_url:
            self.context.open_popup(self.popup_url)
        return FakeResponse()


class FakeContext:
    def __init__(self, page):
        self.page = page
        self.pages = []
        self.handlers = []
        self.events = {}
        self.operations = []
        self.dispatched = []
        self.close = MagicMock()
        page.context = self

    def route(self, pattern, handler):
        self.operations.append(("route", pattern))
        self.handlers.append((pattern, handler))

    def unroute(self, pattern, handler):
        self.operations.append(("unroute", pattern))
        self.handlers = [item for item in self.handlers if item != (pattern, handler)]

    def on(self, event, handler):
        self.events.setdefault(event, []).append(handler)

    def remove_listener(self, event, handler):
        self.events[event] = [item for item in self.events.get(event, []) if item != handler]

    def dispatch(self, url, page):
        request = FakeRequest(url, page)
        route = FakeRoute(request)
        for _pattern, handler in list(self.handlers):
            handler(route)
        self.dispatched.append((request, route))
        return route

    def open_popup(self, url):
        popup = FakePage(context=self)
        self.pages.append(popup)
        for handler in list(self.events.get("page", [])):
            handler(popup)
        popup._dispatch_navigation(url)

    def new_page(self):
        self.operations.append(("new_page", None))
        self.page.context = self
        self.pages.append(self.page)
        return self.page


class FakeBrowser:
    def __init__(self, context):
        self.context = context
        self.contexts = [context]
        self.close = MagicMock()
        self.new_context_calls = []

    def new_context(self, **kwargs):
        self.new_context_calls.append(kwargs)
        return self.context


class FakeChromium:
    def __init__(self, browser):
        self.browser = browser
        self.launch_calls = []
        self.connect_calls = []

    def launch(self, **kwargs):
        self.launch_calls.append(kwargs)
        return self.browser

    def connect_over_cdp(self, url):
        self.connect_calls.append(url)
        return self.browser


class FakePlaywright:
    def __init__(self, browser):
        self.chromium = FakeChromium(browser)
        self.lifecycle_events = []
        browser.close.side_effect = lambda: self.lifecycle_events.append("browser.close")
        browser.context.close.side_effect = lambda: self.lifecycle_events.append("context.close")
        browser.context.page.close.side_effect = lambda: self.lifecycle_events.append("page.close")

    def start(self):
        self.lifecycle_events.append("playwright.start")
        return self

    def stop(self):
        self.lifecycle_events.append("playwright.stop")


def job(job_id):
    return {**JOB, "Link": f"https://www.linkedin.com/jobs/view/{job_id}/"}



class EmptyLocator:
    def count(self):
        return 0

    def nth(self, _index):
        raise IndexError


class EasyApplyControl:
    def is_visible(self):
        return True

    def inner_text(self):
        return "Easy Apply"

    def get_attribute(self, name):
        return {"aria-label": "Easy Apply to this job"}.get(name, "")


class DetectorContractPage:
    def __init__(self, control):
        self.control = control

    def locator(self, selector):
        if selector == ".jobs-details__main-content [aria-label='Easy Apply to this job']":
            return type("OneLocator", (), {"count": lambda _self: 1, "nth": lambda _self, _i: self.control})()
        if selector == "body":
            return type("BodyLocator", (), {"inner_text": lambda _self: ""})()
        return EmptyLocator()

class RouteAuditRunnerTests(unittest.TestCase):
    def setUp(self):
        self.page = FakePage()
        self.context = FakeContext(self.page)
        self.browser = FakeBrowser(self.context)
        self.playwright = FakePlaywright(self.browser)

    def fake_inspection(self, page, target_job, **_kwargs):
        job_id = target_job["Link"].rstrip("/").split("/")[-1]
        return {
            "selected_job_id": job_id,
            "observed_page_url": page.url,
            "inspection_outcome": "PAGE_INSPECTED",
            "classification": "NO_TARGET_APPLICATION_CONTROL",
            "reason": "test result",
            "control_evidence": [],
            "validated_external_href": None,
        }

    def run_with(self, jobs, inspector=None):
        with (
            patch.object(route_audit, "ROUTE_AUDIT_BROWSER_ENABLED", True),
            patch.object(route_audit, "sync_playwright", return_value=self.playwright),
            patch.object(easy_apply, "inspect_application_route", side_effect=inspector or self.fake_inspection) as inspect,
            patch.object(easy_apply, "open_easy_apply") as open_easy,
            patch.object(easy_apply, "prepare_external_application_page") as prepare_external,
            patch.object(easy_apply, "record_application_status") as record_status,
            patch.object(easy_apply, "_record_application_history") as record_history,
            patch("runtime_diagnostics.write_diagnostic") as write_diagnostic,
        ):
            results = route_audit.audit_recommended_jobs(jobs)
        return results, inspect, open_easy, prepare_external, record_status, record_history, write_diagnostic

    def test_run_route_audit_gets_recommendations_and_stays_out_of_application_handlers(self):
        with (
            patch.object(easy_apply, "get_recommended_jobs", return_value=[JOB]) as get_recommended,
            patch.object(route_audit, "ROUTE_AUDIT_BROWSER_ENABLED", True),
            patch.object(route_audit, "sync_playwright", return_value=self.playwright),
            patch.object(easy_apply, "inspect_application_route", side_effect=self.fake_inspection) as inspect,
            patch.object(easy_apply, "open_easy_apply") as open_easy,
            patch.object(easy_apply, "prepare_external_application_page") as prepare_external,
            patch.object(easy_apply, "record_application_status") as record_status,
            patch.object(easy_apply, "_record_application_history") as record_history,
            patch("runtime_diagnostics.write_diagnostic") as write_diagnostic,
        ):
            result = route_audit.run_route_audit()

        self.assertEqual(len(result), 1)
        inspect.assert_called_once()
        open_easy.assert_not_called()
        prepare_external.assert_not_called()
        record_status.assert_not_called()
        record_history.assert_not_called()
        write_diagnostic.assert_not_called()
        self.assertEqual(self.page.goto_calls, [JOB["Link"]])
        self.page.click.assert_not_called()
        self.assertEqual(self.playwright.chromium.launch_calls, [{}])
        self.assertEqual(self.browser.new_context_calls, [{"service_workers": "block"}])
        self.assertEqual(self.playwright.chromium.connect_calls, [])
        self.context.close.assert_called_once()
        self.browser.close.assert_called_once()
        self.assertEqual(self.playwright.lifecycle_events, [
            "playwright.start", "page.close", "context.close",
            "browser.close", "playwright.stop",
        ])

    def test_result_is_bound_to_each_exact_job_id_and_route_classification_propagates(self):
        classifications = [
            "LINKEDIN_EASY_APPLY_CONTROL_DETECTED",
            "EXTERNAL_APPLY_CONTROL_DETECTED_VALIDATED",
            "EXPLICITLY_UNAVAILABLE",
            "NO_TARGET_APPLICATION_CONTROL",
            "AMBIGUOUS",
            "INACCESSIBLE",
        ]
        jobs = [job(str(1234567800 + i)) for i in range(len(classifications))]

        def inspector(page, target_job, **_kwargs):
            job_id = target_job["Link"].rstrip("/").split("/")[-1]
            index = int(job_id) - 1234567800
            return {
                "selected_job_id": job_id,
                "observed_page_url": page.url,
                "inspection_outcome": "PAGE_INSPECTED",
                "classification": classifications[index],
                "reason": f"reason {index}",
                "control_evidence": [{"id": job_id}],
                "validated_external_href": "https://ats.example.test/apply" if index == 1 else None,
            }

        results, inspect, *_ = self.run_with(jobs, inspector)
        self.assertEqual([r["selected_job_id"] for r in results], [str(1234567800 + i) for i in range(6)])
        self.assertEqual([r["classification"] for r in results], classifications)
        self.assertEqual([r["control_evidence"][0]["id"] for r in results], [str(1234567800 + i) for i in range(6)])
        self.assertEqual(inspect.call_count, 6)
        self.assertEqual(self.page.goto_calls, [j["Link"] for j in jobs])
        self.assertNotIn("https://ats.example.test/apply", self.page.goto_calls)
        self.page.click.assert_not_called()

    def test_different_job_id_redirect_is_blocked_before_route_inspection(self):
        selected = JOB["Link"]
        self.page.redirect_map[selected] = "https://www.linkedin.com/jobs/view/9999999999/"
        results, inspect, *_ = self.run_with([JOB])
        self.assertEqual(results[0]["classification"], "AMBIGUOUS")
        self.assertEqual(results[0]["inspection_outcome"], "UNEXPECTED_NAVIGATION_BLOCKED")
        inspect.assert_not_called()
        self.assertTrue(self.page.route_requests[-1][1].aborted)
        self.assertEqual(self.page.goto_calls, [selected])

    def test_inspector_result_with_mismatched_job_id_fails_closed(self):
        def stale_inspector(page, _target_job, **_kwargs):
            return {
                "selected_job_id": "9999999999",
                "observed_page_url": page.url,
                "inspection_outcome": "PAGE_INSPECTED",
                "classification": "LINKEDIN_EASY_APPLY_CONTROL_DETECTED",
                "reason": "stale result must not be reused",
                "control_evidence": [{"id": "9999999999"}],
                "validated_external_href": "https://ats.example.test/apply",
            }

        (results, inspect, open_easy, prepare_external, record_status,
         record_history, write_diagnostic) = self.run_with([JOB], stale_inspector)

        self.assertEqual(results[0]["selected_job_id"], "1234567890")
        self.assertEqual(results[0]["classification"], "AMBIGUOUS")
        self.assertEqual(results[0]["inspection_outcome"], "INSPECTOR_IDENTITY_MISMATCH")
        self.assertEqual(results[0]["control_evidence"], [])
        self.assertIsNone(results[0]["validated_external_href"])
        inspect.assert_called_once()
        open_easy.assert_not_called()
        prepare_external.assert_not_called()
        record_status.assert_not_called()
        record_history.assert_not_called()
        write_diagnostic.assert_not_called()
        self.page.click.assert_not_called()
        self.assertEqual(self.page.goto_calls, [JOB["Link"]])

    def test_external_redirect_is_aborted_and_never_opened(self):
        selected = JOB["Link"]
        self.page.redirect_map[selected] = "https://careers.example.test/apply/123"
        results, inspect, *_ = self.run_with([JOB])
        self.assertEqual(results[0]["classification"], "AMBIGUOUS")
        self.assertEqual(results[0]["inspection_outcome"], "UNEXPECTED_NAVIGATION_BLOCKED")
        inspect.assert_not_called()
        self.assertTrue(self.page.route_requests[-1][1].aborted)
        self.assertEqual(self.page.goto_calls, [selected])

    def test_context_policy_is_installed_before_audit_page_creation(self):
        self.run_with([JOB])
        self.assertEqual(self.context.operations[:2], [
            ("route", "**/*"), ("new_page", None),
        ])
        self.assertTrue(any(operation[0] == "unroute" for operation in self.context.operations))

    def test_extracted_test_guard_allows_one_exact_destination_then_blocks_other_navigation(self):
        page_ref = {"value": None}
        initial_navigation_pending = {"value": True}
        blocked = []
        approved_url = "http://127.0.0.1:43127/approved"
        handler, _record_blocked = route_audit._install_test_navigation_guard(
            self.context,
            approved_url=approved_url,
            preexisting_pages=set(),
            page_ref=page_ref,
            initial_navigation_pending=initial_navigation_pending,
            blocked=blocked,
        )
        page = self.context.new_page()
        page_ref["value"] = page

        approved_route = FakeRoute(FakeRequest(approved_url, page))
        handler(approved_route)
        self.assertTrue(approved_route.continued)
        self.assertFalse(approved_route.aborted)
        self.assertFalse(initial_navigation_pending["value"])

        unexpected_url = "http://127.0.0.1:43127/unapproved"
        unexpected_route = FakeRoute(FakeRequest(unexpected_url, page))
        handler(unexpected_route)
        self.assertTrue(unexpected_route.aborted)
        self.assertFalse(unexpected_route.continued)
        self.assertEqual(blocked, [{
            "url": unexpected_url,
            "source": "audit-page-navigation",
        }])

    def test_extracted_guard_blocks_repeated_request_to_the_approved_url(self):
        page_ref = {"value": None}
        initial_navigation_pending = {"value": True}
        blocked = []
        approved_url = "http://127.0.0.1:43127/approved"
        handler, _record_blocked = route_audit._install_test_navigation_guard(
            self.context,
            approved_url=approved_url,
            preexisting_pages=set(),
            page_ref=page_ref,
            initial_navigation_pending=initial_navigation_pending,
            blocked=blocked,
        )
        page = self.context.new_page()
        page_ref["value"] = page

        first_request = FakeRoute(FakeRequest(approved_url, page))
        handler(first_request)
        repeated_request = FakeRoute(FakeRequest(approved_url, page))
        handler(repeated_request)

        self.assertTrue(first_request.continued)
        self.assertTrue(repeated_request.aborted)
        self.assertFalse(repeated_request.continued)
        self.assertEqual(blocked, [{
            "url": approved_url,
            "source": "audit-page-navigation",
        }])

    def test_production_runner_never_calls_local_test_matcher(self):
        with patch.object(
            route_audit, "_install_test_navigation_guard",
            side_effect=AssertionError("test matcher reached production runner"),
        ):
            results, *_ = self.run_with([JOB])
        self.assertEqual(results[0]["classification"], "NO_TARGET_APPLICATION_CONTROL")

    def test_exact_approved_url_is_permitted(self):
        results, inspect, *_ = self.run_with([JOB])
        self.assertEqual(results[0]["classification"], "NO_TARGET_APPLICATION_CONTROL")
        inspect.assert_called_once()
        request_url, route = self.page.route_requests[0]
        self.assertEqual(request_url, JOB["Link"])
        self.assertTrue(route.continued)
        self.assertFalse(route.aborted)

    def test_same_job_id_url_variants_are_rejected_before_browser_setup(self):
        invalid_urls = [
            "https://linkedin.com/jobs/view/1234567890/",
            "https://www.linkedin.com/jobs/view/1234567890/extra",
            "https://www.linkedin.com/jobs/view/1234567890/?trk=foo",
            "https://www.linkedin.com/jobs/view/1234567890/#details",
            "http://www.linkedin.com/jobs/view/1234567890/",
            "https://user@www.linkedin.com/jobs/view/1234567890/",
            "https://www.linkedin.com:444/jobs/view/1234567890/",
            "https://www.linkedin.com.evil.test/jobs/view/1234567890/",
        ]
        for invalid_url in invalid_urls:
            with self.subTest(url=invalid_url), patch.object(route_audit, "sync_playwright") as start_browser:
                result = route_audit.audit_recommended_jobs([{**JOB, "Link": invalid_url}])
                self.assertEqual(result[0]["inspection_outcome"], "SELECTED_URL_INVALID")
                self.assertEqual(result[0]["classification"], "AMBIGUOUS")
                start_browser.assert_not_called()

    def test_same_id_unapproved_redirect_is_blocked_and_stops_remaining_audit(self):
        selected = JOB["Link"]
        self.page.redirect_map[selected] = "https://www.linkedin.com/jobs/view/1234567890/?trk=redirect"
        results, inspect, *_ = self.run_with([JOB, job("1234567891")])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["inspection_outcome"], "UNEXPECTED_NAVIGATION_BLOCKED")
        self.assertEqual(results[0]["classification"], "AMBIGUOUS")
        inspect.assert_not_called()
        self.assertEqual(self.page.goto_calls, [selected])

    def test_popup_navigation_is_blocked_and_stops_audit(self):
        self.page.popup_url = "https://careers.example.test/apply"
        results, inspect, *_ = self.run_with([JOB, job("1234567891")])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["inspection_outcome"], "UNEXPECTED_NAVIGATION_BLOCKED")
        self.assertEqual(results[0]["classification"], "AMBIGUOUS")
        self.assertEqual(self.page.goto_calls, [JOB["Link"]])
        self.assertTrue(any(
            request.url == "https://careers.example.test/apply" and route.aborted
            for request, route in self.context.dispatched
        ))
        inspect.assert_not_called()

    def test_invalid_selected_url_fails_closed_without_browser(self):
        bad = {**JOB, "Link": "https://linkedin.com.evil.example/jobs/view/1234567890/"}
        with patch.object(route_audit, "sync_playwright") as start_browser:
            result = route_audit.audit_recommended_jobs([bad])
        self.assertEqual(result[0]["classification"], "AMBIGUOUS")
        self.assertEqual(result[0]["inspection_outcome"], "SELECTED_URL_INVALID")
        start_browser.assert_not_called()

    def test_duplicate_selected_ids_fail_closed_without_inspection(self):
        results, inspect, *_ = self.run_with([JOB, dict(JOB)])
        self.assertEqual([r["classification"] for r in results], ["AMBIGUOUS", "AMBIGUOUS"])
        self.assertTrue(all(r["inspection_outcome"] == "DUPLICATE_SELECTED_ID" for r in results))
        inspect.assert_not_called()
        self.assertEqual(self.page.goto_calls, [])

    def test_dry_run_returns_uninspected_rows_without_connecting_to_browser(self):
        with (
            patch.object(config, "DRY_RUN", True),
            patch.object(route_audit, "sync_playwright") as start_browser,
        ):
            results = route_audit.audit_recommended_jobs([JOB])
        self.assertEqual(results[0]["inspection_outcome"], "DRY_RUN_SKIPPED_BROWSER")
        self.assertIsNone(results[0]["classification"])
        start_browser.assert_not_called()

    def test_live_audit_is_disabled_by_default_before_browser_setup(self):
        with (
            patch.object(route_audit.EXECUTION_POLICY, "allows_browser_actions", return_value=True),
            patch.object(route_audit, "sync_playwright") as start_browser,
        ):
            results = route_audit.audit_recommended_jobs([JOB])
        self.assertEqual(results[0]["inspection_outcome"], "ROUTE_AUDIT_DISABLED")
        self.assertIsNone(results[0]["classification"])
        start_browser.assert_not_called()

    def test_isolated_context_creation_failure_closes_browser_without_cdp_fallback(self):
        self.browser.new_context = MagicMock(side_effect=RuntimeError("context failure"))
        with (
            patch.object(route_audit, "ROUTE_AUDIT_BROWSER_ENABLED", True),
            patch.object(route_audit, "sync_playwright", return_value=self.playwright),
            patch.object(easy_apply, "inspect_application_route") as inspect,
            patch.object(easy_apply, "open_easy_apply") as open_easy,
        ):
            results = route_audit.audit_recommended_jobs([JOB])
        self.assertEqual(results[0]["inspection_outcome"], "ROUTE_AUDIT_FAILED")
        self.assertEqual(results[0]["classification"], "INACCESSIBLE")
        self.browser.close.assert_called_once()
        self.browser.new_context.assert_called_once_with(service_workers="block")
        self.assertEqual(self.playwright.chromium.connect_calls, [])
        inspect.assert_not_called()
        open_easy.assert_not_called()

    def test_isolated_context_and_browser_close_after_inspection_failure(self):
        def broken_inspector(*_args, **_kwargs):
            raise RuntimeError("inspection error")

        self.run_with([JOB], broken_inspector)
        self.page.close.assert_called_once()
        self.context.close.assert_called_once()
        self.browser.close.assert_called_once()

    def test_inspector_exception_is_inaccessible_and_never_falls_through(self):
        def broken_inspector(*_args, **_kwargs):
            raise RuntimeError("inspection error")

        results, inspect, open_easy, prepare_external, *_ = self.run_with([JOB], broken_inspector)
        self.assertEqual(results[0]["classification"], "INACCESSIBLE")
        self.assertEqual(results[0]["inspection_outcome"], "ROUTE_INSPECTION_FAILED")
        inspect.assert_called_once()
        open_easy.assert_not_called()
        prepare_external.assert_not_called()
        self.page.click.assert_not_called()

    def test_easy_apply_detector_keeps_locator_or_none_contract(self):
        control = EasyApplyControl()
        self.assertIs(easy_apply.find_easy_apply_button(DetectorContractPage(control)), control)
        self.assertIsNone(easy_apply.find_easy_apply_button(DetectorContractPage(None)))
    def test_existing_external_link_wrapper_still_returns_its_public_string_contract(self):
        expected = "https://ats.example.test/apply"
        with patch.object(external_app, "inspect_external_apply_link", return_value={
            "status": "VALIDATED", "validated_href": expected,
        }):
            result = external_app.find_external_apply_link(self.page, JOB)
        self.assertEqual(result, expected)
        self.assertIsInstance(result, str)


if __name__ == "__main__":
    unittest.main()
