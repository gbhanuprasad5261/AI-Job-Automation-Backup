"""Deterministic route-policy tests; fixtures do not execute browser JavaScript."""

import unittest
from unittest.mock import patch

import easy_apply


JOB = {
    "Title": "Backend Developer",
    "Company": "Example Corp",
    "Link": "https://www.linkedin.com/jobs/view/1234567890/",
    "Easy Apply": "Yes",
    "Match Score": "88%",
    "Application Eligible": "Yes",
}


class FakeBody:
    def __init__(self, text):
        self.text = text

    def inner_text(self):
        return self.text


class FakeTextNode:
    def __init__(self, text):
        self.text = text

    def is_visible(self):
        return True

    def inner_text(self):
        return self.text


class FakeLocator:
    def __init__(self, nodes):
        self.nodes = nodes

    def count(self):
        return len(self.nodes)

    def nth(self, index):
        return self.nodes[index]


class FakeTargetJobCard(FakeTextNode):
    def __init__(self, text, *, title=JOB["Title"], company=JOB["Company"]):
        super().__init__(text)
        self.title = title
        self.company = company

    def locator(self, selector):
        if selector == "h1.job-details-jobs-unified-top-card__job-title":
            return FakeLocator([FakeTextNode(self.title)])
        if selector == ".job-details-jobs-unified-top-card__company-name":
            return FakeLocator([FakeTextNode(self.company)])
        raise AssertionError(f"Unexpected target-card query: {selector}")


class FakePage:
    def __init__(self, *, url=None, title="Backend Developer | Example Corp | LinkedIn",
                 body="Job details", target_card=None):
        self.url = url or JOB["Link"]
        self._title = title
        self.body = body
        self.target_card = target_card

    def title(self):
        return self._title

    def locator(self, selector):
        if selector == "body":
            return FakeBody(self.body)
        if selector == 'input[type="password"]':
            return FakeLocator([])
        if selector == ".jobs-details__main-content .job-details-jobs-unified-top-card":
            return FakeLocator([self.target_card] if self.target_card else [])
        raise AssertionError(f"Unexpected page query: {selector}")


def easy(status="NONE", reason="none", *, evidence=None):
    return {
        "status": status,
        "reason": reason,
        "candidate_count": 1 if status != "NONE" else 0,
        "target_candidate_count": 1 if status == "VALIDATED" else 0,
        "similar_job_candidate_count": 0,
        "ambiguous_candidate_count": 1 if status in {"AMBIGUOUS", "DUPLICATE"} else 0,
        "control_evidence": evidence or [],
        "control": object() if status == "VALIDATED" else None,
    }


def external(status="NO_CANDIDATE", reason="none", href=""):
    return {
        "status": status,
        "reason": reason,
        "candidate_count": 1 if status != "NO_CANDIDATE" else 0,
        "target_candidate_count": 1 if status == "VALIDATED" else 0,
        "similar_job_candidate_count": 0,
        "ambiguous_candidate_count": 1 if status in {"AMBIGUOUS", "DUPLICATE"} else 0,
        "invalid_candidate_count": 1 if status == "INVALID_URL" else 0,
        "validated_href": href,
        "candidates": [{"label": "Apply on company website", "association": "TARGET_ASSOCIATED"}] if status != "NO_CANDIDATE" else [],
    }


class ApplicationRouteClassificationTests(unittest.TestCase):
    def classify(self, page=None, *, easy_result=None, external_result=None, **kwargs):
        with (
            patch.object(easy_apply, "inspect_easy_apply_control", return_value=easy_result or easy()),
            patch.object(easy_apply, "inspect_external_apply_link", return_value=external_result or external()),
        ):
            return easy_apply.inspect_application_route(page or FakePage(), JOB, **kwargs)

    def test_unique_easy_apply_control_is_detected_but_not_claimed_available(self):
        result = self.classify(easy_result=easy("VALIDATED", "unique target control"))
        self.assertEqual(result["classification"], "LINKEDIN_EASY_APPLY_CONTROL_DETECTED")
        self.assertEqual(result["saved_easy_apply_hint"], "Yes")
        self.assertNotIn("available", result["classification"].casefold())

    def test_valid_external_control_is_classified_without_opening_destination(self):
        href = "https://careers.example.test/apply/123"
        result = self.classify(external_result=external("VALIDATED", "url is syntactically valid", href))
        self.assertEqual(result["classification"], "EXTERNAL_APPLY_CONTROL_DETECTED_VALIDATED")
        self.assertEqual(result["validated_external_href"], href)

    def test_saved_hint_no_does_not_override_live_external_evidence(self):
        job = {**JOB, "Easy Apply": "No"}
        href = "https://careers.example.test/apply/123"
        with (
            patch.object(easy_apply, "inspect_easy_apply_control", return_value=easy()),
            patch.object(easy_apply, "inspect_external_apply_link", return_value=external("VALIDATED", "validated", href)),
        ):
            result = easy_apply.inspect_application_route(FakePage(), job)
        self.assertEqual(result["classification"], "EXTERNAL_APPLY_CONTROL_DETECTED_VALIDATED")
        self.assertEqual(result["saved_easy_apply_hint"], "No")

    def test_unavailable_message_in_verified_target_card_is_explicitly_unavailable(self):
        page = FakePage(target_card=FakeTargetJobCard(
            "Backend Developer | Example Corp | No longer accepting applications"
        ))
        result = self.classify(page)
        self.assertEqual(result["classification"], "EXPLICITLY_UNAVAILABLE")

    def test_similar_job_card_unavailable_message_does_not_classify_target(self):
        page = FakePage(
            body="Selected job details. Similar job: No longer accepting applications",
            target_card=FakeTargetJobCard("Backend Developer | Example Corp | Job details"),
        )
        result = self.classify(page)
        self.assertEqual(result["classification"], "NO_TARGET_APPLICATION_CONTROL")

    def test_unrelated_body_unavailable_message_does_not_classify_target(self):
        page = FakePage(
            body="Navigation and recommendation content: No longer accepting applications",
            target_card=FakeTargetJobCard("Backend Developer | Example Corp | Job details"),
        )
        result = self.classify(page)
        self.assertEqual(result["classification"], "NO_TARGET_APPLICATION_CONTROL")

    def test_no_control_is_not_reported_as_closed(self):
        result = self.classify()
        self.assertEqual(result["classification"], "NO_TARGET_APPLICATION_CONTROL")

    def test_unavailable_message_conflicting_with_route_is_ambiguous(self):
        page = FakePage(target_card=FakeTargetJobCard(
            "Backend Developer | Example Corp | No longer accepting applications"
        ))
        result = self.classify(
            page,
            easy_result=easy("VALIDATED", "target control"),
        )
        self.assertEqual(result["classification"], "AMBIGUOUS")

    def test_missing_or_unreliable_target_card_fails_closed_for_unavailable_text(self):
        pages = (
            FakePage(body="No longer accepting applications"),
            FakePage(
                body="No longer accepting applications",
                target_card=FakeTargetJobCard(
                    "No longer accepting applications",
                    title="Different job title",
                ),
            ),
        )
        for page in pages:
            with self.subTest(target_card=page.target_card):
                result = self.classify(page)
                self.assertNotEqual(result["classification"], "EXPLICITLY_UNAVAILABLE")

    def test_both_route_types_are_ambiguous(self):
        result = self.classify(
            easy_result=easy("VALIDATED", "easy"),
            external_result=external("VALIDATED", "external", "https://ats.example.test/apply"),
        )
        self.assertEqual(result["classification"], "AMBIGUOUS")

    def test_duplicate_or_invalid_candidates_are_ambiguous(self):
        for inspected in (easy("DUPLICATE", "duplicate"), external("INVALID_URL", "bad URL")):
            with self.subTest(status=inspected["status"]):
                if "validated_href" in inspected:
                    result = self.classify(external_result=inspected)
                else:
                    result = self.classify(easy_result=inspected)
                self.assertEqual(result["classification"], "AMBIGUOUS")

    def test_identity_mismatch_is_ambiguous_before_detector_calls(self):
        page = FakePage(url="https://www.linkedin.com/jobs/view/9999999999/")
        with (
            patch.object(easy_apply, "inspect_easy_apply_control") as easy_inspector,
            patch.object(easy_apply, "inspect_external_apply_link") as external_inspector,
        ):
            result = easy_apply.inspect_application_route(page, JOB)
        self.assertEqual(result["classification"], "AMBIGUOUS")
        easy_inspector.assert_not_called()
        external_inspector.assert_not_called()

    def test_navigation_failure_auth_and_interstitial_are_inaccessible(self):
        failed = self.classify(navigation_succeeded=False)
        login = self.classify(FakePage(
            url="https://www.linkedin.com/jobs/view/1234567890/login",
            title="Sign in | LinkedIn",
        ))
        for result in (failed, login):
            self.assertEqual(result["classification"], "INACCESSIBLE")
        self.assertEqual(login["inspection_outcome"], "AUTHENTICATION_OR_INTERSTITIAL")

    def test_http_failure_and_unverified_page_title_are_inaccessible(self):
        failed = self.classify(http_status=503)
        wrong_title = self.classify(FakePage(title="LinkedIn Help Center"))
        self.assertEqual(failed["classification"], "INACCESSIBLE")
        self.assertEqual(wrong_title["inspection_outcome"], "TARGET_PAGE_UNVERIFIED")
        self.assertEqual(wrong_title["classification"], "INACCESSIBLE")

    def test_external_inspection_error_is_inaccessible(self):
        result = self.classify(external_result=external("INSPECTION_ERROR", "read failed"))
        self.assertEqual(result["classification"], "INACCESSIBLE")


class EasyApplyStructuredDetectorTests(unittest.TestCase):
    class Control:
        def __init__(self, relation="TARGET_ASSOCIATED"):
            self.relation = relation

        def is_visible(self):
            return True

        def inner_text(self):
            return "Easy Apply"

        def get_attribute(self, name):
            return {"aria-label": "Easy Apply to this job", "href": "", "title": ""}.get(name, "")

        def evaluate(self, _script):
            return "button"

    class Locator:
        def __init__(self, controls):
            self.controls = controls

        def count(self):
            return len(self.controls)

        def nth(self, index):
            return self.controls[index]

    class CandidatePage(FakePage):
        def __init__(self, controls, **kwargs):
            super().__init__(**kwargs)
            self.controls = controls

        def locator(self, selector):
            if selector == "body":
                return FakeBody(self.body)
            return EasyApplyStructuredDetectorTests.Locator(self.controls)

    def test_actual_easy_candidate_scan_reports_one_target_candidate(self):
        control = self.Control()
        page = self.CandidatePage([control])
        with patch.object(easy_apply, "_control_job_association_status", return_value="TARGET_ASSOCIATED"):
            result = easy_apply.inspect_easy_apply_control(page, JOB)
        self.assertEqual(result["status"], "VALIDATED")
        self.assertEqual(result["target_candidate_count"], 1)

    def test_easy_candidate_scan_rejects_similar_job_and_reports_duplicate(self):
        similar = self.Control()
        with patch.object(easy_apply, "_control_job_association_status", return_value="SIMILAR_JOB"):
            result = easy_apply.inspect_easy_apply_control(self.CandidatePage([similar]), JOB)
        self.assertEqual(result["status"], "NONE")
        self.assertEqual(result["similar_job_candidate_count"], 1)

        controls = [self.Control(), self.Control()]
        with patch.object(easy_apply, "_control_job_association_status", return_value="TARGET_ASSOCIATED"):
            result = easy_apply.inspect_easy_apply_control(self.CandidatePage(controls), JOB)
        self.assertEqual(result["status"], "DUPLICATE")


if __name__ == "__main__":
    unittest.main()
