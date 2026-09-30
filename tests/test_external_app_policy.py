import unittest
from unittest.mock import Mock, patch

import external_app


class FakePage:
    url = "https://careers.example.test/application"


class ExternalApplicationPolicyTests(unittest.TestCase):
    def _prepare(self, policy, required=0):
        page = FakePage()
        submit_gate = Mock(return_value="READY_FOR_REVIEW")
        with (
            patch.object(external_app, "UNKNOWN_QUESTIONS_POLICY", policy),
            patch.object(external_app, "_text", return_value="Application form"),
            patch.object(external_app, "_external_page_has_error", return_value=False),
            patch.object(external_app, "_wait_for_manual_consent", return_value=True),
            patch.object(external_app, "_click_external_application_start", return_value=page),
            patch.object(external_app, "_looks_like_application_form", return_value=True),
            patch.object(external_app, "_fill_known_application_fields", return_value=0),
            patch.object(external_app, "_fill_known_fields", return_value=0),
            patch.object(external_app, "_upload_resume", return_value=False),
            patch.object(external_app, "_fill_known_profile_links", return_value=0),
            patch.object(external_app, "_select_known_dropdowns", return_value=0),
            patch.object(external_app, "_check_known_terms_consent", return_value=0),
            patch.object(external_app, "_required_empty_count", return_value=required),
            patch.object(external_app, "_auto_submit_external_application", submit_gate),
        ):
            result = external_app.prepare_external_application_page(page)
        return result, submit_gate

    def test_review_policy_stops_before_external_submit_routine(self):
        result, submit_gate = self._prepare("REVIEW")
        self.assertEqual(result, "READY_FOR_REVIEW")
        submit_gate.assert_not_called()

    def test_skip_policy_keeps_existing_external_submit_gate_path(self):
        result, submit_gate = self._prepare("SKIP")
        self.assertEqual(result, "READY_FOR_REVIEW")
        submit_gate.assert_called_once()

    def test_required_unknown_stops_before_external_submit_routine(self):
        result, submit_gate = self._prepare("SKIP", required=1)
        self.assertEqual(result, "READY_FOR_REVIEW")
        submit_gate.assert_not_called()


if __name__ == "__main__":
    unittest.main()
