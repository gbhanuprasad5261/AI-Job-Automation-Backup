import unittest
from contextlib import redirect_stdout
from io import StringIO
from urllib.parse import parse_qs, quote, urlparse
from unittest.mock import MagicMock, patch

import easy_apply
import external_app


TARGET_JOB = {
    "Title": "Backend Developer",
    "Company": "Example Corp",
    "Link": "https://www.linkedin.com/jobs/view/1234567890/",
}
COGNIZANT_JOB = {
    "Title": "Java Developer(AWS)",
    "Company": "Cognizant",
    "Link": "https://www.linkedin.com/jobs/view/4469471138/",
}
COGNIZANT_DESTINATION = (
    "https://careers.cognizant.com/global-en/jobs/00070527821/java-developer-aws/"
)


class DomNode:
    def __init__(self, tag="div", text="", node_id="", attributes=None):
        self.tag = tag
        self.text = text
        self.node_id = node_id
        self.attributes = dict(attributes or {})
        if node_id:
            self.attributes["id"] = node_id
        self.children = []
        self.parent = None

    def add(self, *children):
        for child in children:
            child.parent = self
            self.children.append(child)
        return self

    def descendants(self):
        for child in self.children:
            yield child
            yield from child.descendants()

    def ancestors(self):
        node = self
        while node is not None:
            yield node
            node = node.parent

    def visible_text(self):
        return " ".join(part for part in (self.text, *(n.text for n in self.descendants())) if part)


class FakeControl(DomNode):
    def __init__(self, href, label="Apply on company website", text="Apply"):
        super().__init__("a", text, attributes={"href": href, "aria-label": label})
        self.href = href
        self.label = label
        self.click = MagicMock()

    def is_visible(self):
        return True

    def get_attribute(self, name):
        return self.attributes.get(name)

    def inner_text(self):
        return self.visible_text()

    def evaluate(self, _script, identity):
        """Return structural DOM evidence consumed by the production policy."""
        records = []
        candidate_ancestors = list(self.ancestors())
        for index, node in enumerate(candidate_ancestors):
            subtree = [node, *node.descendants()]
            similar_slots = [
                item for item in subtree
                if item.node_id.startswith("JobDetailsSimilarJobsSlot_")
            ]
            page_root = candidate_ancestors[-1]
            target_slot_id = f"JobDetailsSimilarJobsSlot_{identity['jobId']}"
            page_has_target_slot = any(
                item.node_id == target_slot_id
                for item in [page_root, *page_root.descendants()]
            )
            inside_similar_slot = any(
                ancestor.node_id.startswith("JobDetailsSimilarJobsSlot_")
                for ancestor in candidate_ancestors[:index + 1]
            )
            # Detect recommendation links by their LinkedIn currentJobId identity.
            linked_job_ids = []
            for item in subtree:
                href = item.get_attribute("href") if isinstance(item, FakeControl) else ""
                if href:
                    linked_job_ids.extend(parse_qs(urlparse(href).query).get("currentJobId", []))

            app_controls = []
            for item in subtree:
                if not isinstance(item, FakeControl) or not item.is_visible():
                    continue
                value = f"{item.label} {item.href}".lower()
                if any(term in value for term in (
                    "apply on company website",
                    "apply on the company website",
                    "apply externally",
                    "greenhouse.io",
                    "lever.co",
                    "myworkdayjobs.com",
                    "workday.com",
                    "ashbyhq.com",
                    "smartrecruiters.com",
                    "jobvite.com",
                    "cutshort.io",
                    "successfactors.eu",
                    "successfactors.com",
                    "docs.google.com/forms",
                    "forms.gle",
                )):
                    app_controls.append(item is self)

            records.append({
                "text": node.visible_text(),
                "pageHasTargetSimilarJobSlot": page_has_target_slot,
                "isBroadContainer": (
                    node.tag.upper() in {"MAIN", "BODY"}
                    or node.attributes.get("data-testid") == "lazy-column"
                ),
                "insideSimilarJobSlot": inside_similar_slot,
                "containsSimilarJobSlot": bool(similar_slots),
                "hasOtherJobCards": any(
                    linked_id != identity["jobId"] for linked_id in linked_job_ids
                ),
                "applicationControls": app_controls,
            })
        return records


class FakeLocator:
    def __init__(self, controls):
        self.controls = controls

    def count(self):
        return len(self.controls)

    def nth(self, index):
        return self.controls[index]


class FakePage:
    def __init__(self, controls, url="https://www.linkedin.com/jobs/view/1234567890/"):
        self.controls = controls
        self.url = url
        self.locator_calls = []
        self.root = DomNode("main")

    def locator(self, selector):
        self.locator_calls.append(selector)
        return FakeLocator(self.controls)


class FakeBody:
    def inner_text(self):
        return "Example job details"


class FakeNavigationPage(FakePage):
    def title(self):
        return "Backend Developer | Example Corp"

    def locator(self, selector):
        if selector == "body":
            return FakeBody()
        return FakeLocator([])


class ExternalDestinationSafetyTests(unittest.TestCase):
    def _target_page(self, *, include_description_root=True):
        target = FakeControl(
            "https://www.linkedin.com/safety/go/?url="
            + quote(COGNIZANT_DESTINATION, safe=""),
            label="Apply on company website",
        )
        header = DomNode(
            "div", f"{COGNIZANT_JOB['Company']} {COGNIZANT_JOB['Title']}"
        ).add(target)
        page = FakePage([target], url=COGNIZANT_JOB["Link"])
        page.root.add(header)
        if include_description_root:
            page.root.add(DomNode("div", "Job description text", "JobDetails_AboutTheJob_4469471138"))
        page.root.add(DomNode("div", "", "JobDetailsSimilarJobsSlot_4469471138"))
        return page, target, header

    def test_target_job_application_control_is_selected(self):
        page, control, _header = self._target_page()

        result = external_app.find_external_apply_link(page, COGNIZANT_JOB)

        self.assertEqual(result, COGNIZANT_DESTINATION)
        self.assertTrue(page.locator_calls)

    def test_similar_job_ats_link_is_rejected_inside_broad_target_ancestor(self):
        similar_job_link = FakeControl(
            "https://boards.greenhouse.io/other-company/jobs/1",
            label="Apply on company website",
        )
        page = FakePage([similar_job_link])
        page.root.add(DomNode("header", "Cognizant Java Developer(AWS)"))
        similar_slot = DomNode("div", "", "JobDetailsSimilarJobsSlot_4469471138")
        similar_slot.add(DomNode("div", "Different Role Other Company").add(similar_job_link))
        page.root.add(similar_slot)
        page.url = COGNIZANT_JOB["Link"]

        self.assertEqual(external_app.find_external_apply_link(page, COGNIZANT_JOB), "")

    def test_unrelated_ats_link_without_target_header_is_rejected(self):
        unrelated = FakeControl("https://boards.greenhouse.io/other-company/jobs/1")
        page = FakePage([unrelated], url=COGNIZANT_JOB["Link"])
        page.root.add(DomNode("div", "", "JobDetailsSimilarJobsSlot_4469471138"))

        self.assertEqual(external_app.find_external_apply_link(page, COGNIZANT_JOB), "")

    def test_unvalidated_layout_without_target_similar_slot_fails_closed(self):
        control = FakeControl(
            "https://careers.example.test/apply",
            label="Apply on company website",
        )
        page = FakePage([control], url=COGNIZANT_JOB["Link"])
        page.root.add(
            DomNode("header", "Cognizant Java Developer(AWS)").add(control)
        )

        self.assertEqual(external_app.find_external_apply_link(page, COGNIZANT_JOB), "")

    def test_duplicate_target_application_controls_fail_closed(self):
        first = FakeControl("https://careers.example.test/apply/123")
        second = FakeControl("https://careers.example.test/apply/123")
        header = DomNode("div", "Cognizant Java Developer(AWS)").add(first, second)
        page = FakePage([first, second], url=COGNIZANT_JOB["Link"])
        page.root.add(header, DomNode("div", "", "JobDetailsSimilarJobsSlot_4469471138"))

        self.assertEqual(external_app.find_external_apply_link(page, COGNIZANT_JOB), "")

    def test_similar_job_link_before_target_header_does_not_hide_target_link(self):
        similar = FakeControl(
            "https://boards.greenhouse.io/other-company/jobs/1",
            label="Apply on company website",
        )
        target = FakeControl(
            "https://www.linkedin.com/safety/go/?url="
            + quote(COGNIZANT_DESTINATION, safe="")
        )
        page = FakePage([similar, target], url=COGNIZANT_JOB["Link"])
        slot = DomNode("div", "", "JobDetailsSimilarJobsSlot_4469471138")
        slot.add(DomNode("div", "Other Role Other Company").add(similar))
        header = DomNode(
            "div", f"{COGNIZANT_JOB['Company']} {COGNIZANT_JOB['Title']}"
        ).add(target)
        page.root.add(slot, header)

        self.assertEqual(
            external_app.find_external_apply_link(page, COGNIZANT_JOB),
            COGNIZANT_DESTINATION,
        )

    def test_description_root_is_separate_from_target_header(self):
        page, _control, _header = self._target_page(include_description_root=True)
        description_root = next(
            node for node in page.root.children
            if node.node_id == "JobDetails_AboutTheJob_4469471138"
        )

        self.assertEqual(description_root.children, [])
        self.assertEqual(
            external_app.find_external_apply_link(page, COGNIZANT_JOB),
            COGNIZANT_DESTINATION,
        )

    def test_target_header_without_unique_application_control_fails_closed(self):
        first = FakeControl("https://careers.example.test/apply/1")
        second = FakeControl("https://careers.example.test/apply/2")
        page = FakePage([first, second], url=COGNIZANT_JOB["Link"])
        page.root.add(DomNode("header", "Cognizant Java Developer(AWS)"))
        page.root.add(DomNode("div", "Not the target header").add(first, second))
        page.root.add(DomNode("div", "", "JobDetailsSimilarJobsSlot_4469471138"))

        self.assertEqual(external_app.find_external_apply_link(page, COGNIZANT_JOB), "")

    def test_target_job_identity_must_match_open_page_before_link_scan(self):
        page = FakePage(
            [FakeControl("https://careers.example.test/apply")],
            url="https://www.linkedin.com/jobs/view/9999999999/",
        )

        self.assertEqual(external_app.find_external_apply_link(page, TARGET_JOB), "")
        self.assertEqual(page.locator_calls, [])

    def test_unsafe_target_control_scheme_is_rejected(self):
        control = FakeControl("javascript:alert(1)")
        page = FakePage([control], url=COGNIZANT_JOB["Link"])
        page.root.add(
            DomNode("header", "Cognizant Java Developer(AWS)").add(control),
            DomNode("div", "", "JobDetailsSimilarJobsSlot_4469471138"),
        )

        self.assertEqual(external_app.find_external_apply_link(page, TARGET_JOB), "")

    def test_known_supported_ats_destination_remains_supported(self):
        control = FakeControl(
            "https://jobs.myworkdayjobs.com/example/job/123",
            label="",
        )
        page = FakePage([control])
        page.root.add(
            DomNode("header", "Example Corp Backend Developer").add(control),
            DomNode("div", "", "JobDetailsSimilarJobsSlot_1234567890"),
        )

        self.assertEqual(
            external_app.find_external_apply_link(page, TARGET_JOB),
            control.href,
        )

    def test_url_validator_rejects_non_http_s_schemes_and_credentials(self):
        for url in (
            "javascript:alert(1)",
            "data:text/html,application",
            "mailto:jobs@example.test",
            "//careers.example.test/apply",
            "https://user:password@careers.example.test/apply",
        ):
            with self.subTest(url=url):
                self.assertFalse(external_app.is_safe_external_application_url(url))

    def test_http_s_destination_is_accepted(self):
        self.assertTrue(
            external_app.is_safe_external_application_url(
                "https://careers.example.test/apply"
            )
        )
        self.assertTrue(
            external_app.is_safe_external_application_url(
                "http://careers.example.test/apply"
            )
        )

    def test_same_host_redirect_is_accepted(self):
        self.assertTrue(external_app.is_safe_external_application_redirect(
            "https://careers.example.test/apply",
            "https://careers.example.test/application/123",
        ))

    def test_existing_supported_ats_cross_host_redirect_is_accepted(self):
        supported_destinations = (
            "https://boards.greenhouse.io/example/jobs/1",
            "https://jobs.lever.co/example/1",
            "https://jobs.myworkdayjobs.com/example/job/123",
            "https://jobs.workday.com/example/job/123",
            "https://jobs.ashbyhq.com/example/1",
            "https://jobs.smartrecruiters.com/example/1",
            "https://jobs.jobvite.com/example/job/1",
            "https://cutshort.io/job/example/1",
            "https://career5.successfactors.eu/example/job/1",
            "https://acme.successfactors.com/example/job/1",
            "https://docs.google.com/forms/d/example/viewform",
            "https://forms.gle/example",
        )
        for destination in supported_destinations:
            with self.subTest(destination=destination):
                self.assertTrue(external_app.is_safe_external_application_redirect(
                    "https://careers.example.test/apply",
                    destination,
                ))

    def test_unrelated_cross_host_or_unsafe_redirect_is_rejected(self):
        requested = "https://careers.example.test/apply"
        self.assertFalse(external_app.is_safe_external_application_redirect(
            requested,
            "https://unrelated.example.net/login",
        ))
        self.assertFalse(external_app.is_safe_external_application_redirect(
            requested,
            "javascript:alert(1)",
        ))
        self.assertFalse(external_app.is_safe_external_application_redirect(
            requested,
            "http://careers.example.test/insecure-downgrade",
        ))

    def test_ats_hostname_matching_does_not_accept_lookalike_hosts(self):
        self.assertFalse(external_app.is_safe_external_application_redirect(
            "https://careers.example.test/apply",
            "https://myworkdayjobs.com.attacker.example/apply",
        ))

    def _open_external_with_redirect(self, final_url):
        page = FakeNavigationPage(
            [],
            url="https://www.linkedin.com/jobs/view/1234567890/",
        )
        context = MagicMock()
        context.pages = [page]
        browser = MagicMock()
        browser.contexts = [context]
        playwright = MagicMock()
        playwright.chromium.connect_over_cdp.return_value = browser
        manager = MagicMock()
        manager.__enter__.return_value = playwright
        manager.__exit__.return_value = False
        navigation_calls = []
        job = dict(TARGET_JOB)

        def navigate(_page, url, **_kwargs):
            navigation_calls.append(url)
            if len(navigation_calls) > 1:
                page.url = final_url
            return True

        with (
            patch.object(easy_apply, "sync_playwright", return_value=manager),
            patch.object(easy_apply, "get_application_status", return_value="NOT APPLIED"),
            patch.object(easy_apply, "convert_to_job_url", side_effect=lambda value: value),
            patch.object(easy_apply, "navigate_page", side_effect=navigate),
            patch.object(easy_apply, "is_job_closed", return_value=False),
            patch.object(easy_apply, "is_current_job_already_applied", return_value=False),
            patch.object(easy_apply, "check_external_eligibility", return_value="UNKNOWN"),
            patch.object(easy_apply, "find_easy_apply_button", return_value=None),
            patch.object(easy_apply, "find_external_apply_link", return_value="https://careers.example.test/apply"),
            patch.object(easy_apply, "record_application_status") as record_status,
            patch.object(easy_apply, "prepare_external_application_page") as prepare,
            redirect_stdout(StringIO()),
        ):
            result = easy_apply.open_easy_apply(job)

        return result, navigation_calls, record_status, prepare

    def test_easy_apply_rejects_invalid_redirect_before_external_preparation(self):
        result, navigation_calls, record_status, prepare = self._open_external_with_redirect(
            "https://unrelated.example.net/login"
        )

        self.assertFalse(result)
        self.assertEqual(len(navigation_calls), 2)
        record_status.assert_called_once_with(TARGET_JOB, "READY_FOR_REVIEW")
        prepare.assert_not_called()

    def test_easy_apply_rejects_unsafe_scheme_before_navigation(self):
        page = FakeNavigationPage(
            [],
            url="https://www.linkedin.com/jobs/view/1234567890/",
        )
        context = MagicMock()
        context.pages = [page]
        browser = MagicMock()
        browser.contexts = [context]
        playwright = MagicMock()
        playwright.chromium.connect_over_cdp.return_value = browser
        manager = MagicMock()
        manager.__enter__.return_value = playwright
        manager.__exit__.return_value = False
        job = dict(TARGET_JOB)

        with (
            patch.object(easy_apply, "sync_playwright", return_value=manager),
            patch.object(easy_apply, "get_application_status", return_value="NOT APPLIED"),
            patch.object(easy_apply, "convert_to_job_url", side_effect=lambda value: value),
            patch.object(easy_apply, "navigate_page", return_value=True) as navigate,
            patch.object(easy_apply, "is_job_closed", return_value=False),
            patch.object(easy_apply, "is_current_job_already_applied", return_value=False),
            patch.object(easy_apply, "check_external_eligibility", return_value="UNKNOWN"),
            patch.object(easy_apply, "find_easy_apply_button", return_value=None),
            patch.object(easy_apply, "find_external_apply_link", return_value="javascript:alert(1)"),
            patch.object(easy_apply, "record_application_status") as record_status,
            patch.object(easy_apply, "prepare_external_application_page") as prepare,
            redirect_stdout(StringIO()),
        ):
            result = easy_apply.open_easy_apply(job)

        self.assertFalse(result)
        navigate.assert_called_once()  # LinkedIn job-page navigation only.
        record_status.assert_called_once_with(TARGET_JOB, "READY_FOR_REVIEW")
        prepare.assert_not_called()


if __name__ == "__main__":
    unittest.main()
