"""Opt-in local-only Playwright smoke test for the extracted route guard.

Set RUN_ISOLATED_ROUTE_BROWSER_SMOKE=1 to request a disposable browser run.
The test uses only a loopback HTTP server and never calls the production audit
entry point. It skips if the configured Chromium binary is unavailable. An
optional ROUTE_AUDIT_TEST_BROWSER_CHANNEL=chrome|msedge selects an installed
branded browser, launched by Playwright with a fresh temporary profile.
"""

import os
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from playwright.sync_api import sync_playwright

import route_audit


_RUN_SMOKE = os.environ.get("RUN_ISOLATED_ROUTE_BROWSER_SMOKE") == "1"
_TEST_BROWSER_CHANNEL = os.environ.get("ROUTE_AUDIT_TEST_BROWSER_CHANNEL", "").strip()


def _launch_test_browser_context(playwright):
    """Create an isolated context, optionally using an installed browser channel."""
    if not _TEST_BROWSER_CHANNEL:
        return route_audit._create_isolated_browser_context(playwright)
    if _TEST_BROWSER_CHANNEL not in {"chrome", "msedge"}:
        raise ValueError("ROUTE_AUDIT_TEST_BROWSER_CHANNEL must be chrome or msedge")

    browser = playwright.chromium.launch(channel=_TEST_BROWSER_CHANNEL)
    try:
        context = browser.new_context(service_workers="block")
    except Exception:
        try:
            browser.close()
        except Exception:
            pass
        raise
    return browser, context


@unittest.skipUnless(_RUN_SMOKE, "opt-in local browser smoke test")
class IsolatedRouteGuardBrowserSmokeTests(unittest.TestCase):
    def test_local_approved_navigation_and_unapproved_navigation_block(self):
        requested_paths = []
        server = None
        server_thread = None
        playwright = None
        browser = None
        context = None
        page = None
        guard_handler = None
        blocked = []

        class LocalHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                requested_paths.append(self.path)
                if self.path == "/approved":
                    body = (
                        "<!doctype html><meta charset='utf-8'>"
                        "<title>local route guard test</title>"
                        "<script>setTimeout(() => location.assign('/unapproved'), 50)</script>"
                    ).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                else:
                    body = b"unexpected local path served"
                    self.send_response(200)
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)

            def log_message(self, _format, *_args):
                return

        manager = sync_playwright()
        try:
            playwright = manager.start()
            if not _TEST_BROWSER_CHANNEL:
                executable = Path(playwright.chromium.executable_path)
                if not executable.is_file():
                    self.skipTest(f"Playwright Chromium binary is unavailable: {executable}")

            server = HTTPServer(("127.0.0.1", 0), LocalHandler)
            server_thread = threading.Thread(target=server.serve_forever, daemon=True)
            server_thread.start()
            base_url = f"http://127.0.0.1:{server.server_port}"
            approved_url = f"{base_url}/approved"

            browser, context = _launch_test_browser_context(playwright)
            page_ref = {"value": None}
            initial_navigation_pending = {"value": True}
            preexisting_pages = set(context.pages)
            guard_handler, _record_blocked = route_audit._install_test_navigation_guard(
                context,
                approved_url=approved_url,
                preexisting_pages=preexisting_pages,
                page_ref=page_ref,
                initial_navigation_pending=initial_navigation_pending,
                blocked=blocked,
            )
            page = context.new_page()
            page_ref["value"] = page

            response = page.goto(approved_url, wait_until="domcontentloaded", timeout=5000)
            self.assertEqual(response.status, 200)

            for _ in range(60):
                if blocked:
                    break
                page.wait_for_timeout(50)

            # Aborting a client-side navigation may leave the original page in
            # place or show the browser's local error document. In either case,
            # the blocked destination must never become the page URL.
            self.assertNotEqual(page.url, f"{base_url}/unapproved")
            self.assertEqual(len(blocked), 1)
            self.assertEqual(blocked[0], {
                "url": f"{base_url}/unapproved",
                "source": "audit-page-navigation",
            })
            self.assertIn("/approved", requested_paths)
            self.assertNotIn("/unapproved", requested_paths)
        finally:
            if context is not None and guard_handler is not None:
                try:
                    context.unroute("**/*", guard_handler)
                except Exception:
                    pass
            if page is not None:
                try:
                    page.close()
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
            if server is not None:
                server.shutdown()
                server.server_close()
            if server_thread is not None:
                server_thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
