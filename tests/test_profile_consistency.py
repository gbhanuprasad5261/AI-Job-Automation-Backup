import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import external_app
import external_apply
import profile as shared_profile


class SharedProfileSourceTests(unittest.TestCase):
    PROFILE_DATA = {
        "first_name": "Synthetic Ada",
        "last_name": "Example",
        "email": "ada@example.invalid",
        "phone": "5550100",
        "city": "Sample City",
        "state": "Sample State",
        "country": "Exampleland",
        "degree": "Synthetic Degree",
        "field_of_study": "Testing",
        "specialization": "Reliability",
        "graduation_year": "2020",
        "experience_years": "5",
        "skills": ["Python"],
        "resume_path": "synthetic-resume.pdf",
    }

    def test_profile_resolves_existing_fields_and_keeps_missing_company_blank(self):
        with patch.object(shared_profile, "PROFILE", self.PROFILE_DATA), patch.dict(
            os.environ, {}, clear=True
        ):
            values = shared_profile.get_application_profile()

        self.assertEqual(values["name"], "Synthetic Ada Example")
        self.assertEqual(values["email"], "ada@example.invalid")
        self.assertEqual(values["phone"], "5550100")
        self.assertEqual(
            values["current_location"],
            "Sample City, Sample State, Exampleland",
        )
        self.assertEqual(values["current_company"], "")
        self.assertEqual(values["resume_path"], "synthetic-resume.pdf")

    def test_existing_environment_overrides_keep_precedence(self):
        env = {
            "CURRENT_LOCATION": "Synthetic Override Location",
            "CURRENT_COMPANY": "Synthetic Override Company",
            "RESUME_PATH": "override-resume.pdf",
        }
        with patch.object(shared_profile, "PROFILE", self.PROFILE_DATA), patch.dict(
            os.environ, env, clear=True
        ):
            values = shared_profile.get_application_profile()

        self.assertEqual(values["current_location"], env["CURRENT_LOCATION"])
        self.assertEqual(values["current_company"], env["CURRENT_COMPANY"])
        self.assertEqual(values["resume_path"], env["RESUME_PATH"])
        self.assertEqual(values["email"], self.PROFILE_DATA["email"])

    def test_external_preparation_paths_receive_the_same_shared_profile(self):
        page = SimpleNamespace(url="https://synthetic.invalid/forms")
        with patch.object(shared_profile, "PROFILE", self.PROFILE_DATA), patch.dict(
            os.environ, {}, clear=True
        ):
            expected = shared_profile.get_application_profile()
        for module in (external_app, external_apply):
            with self.subTest(module=module.__name__):
                with (
                    patch.object(shared_profile, "PROFILE", self.PROFILE_DATA),
                    patch.dict(os.environ, {}, clear=True),
                    patch.object(
                        module.EXECUTION_POLICY,
                        "allows_browser_actions",
                        return_value=True,
                    ),
                    patch.object(module, "_text", return_value="synthetic form"),
                    patch.object(module, "detect_ats", return_value="GOOGLE_FORMS"),
                    patch.object(module, "_external_page_has_error", return_value=False),
                    patch.object(module, "_wait_for_manual_consent", return_value=True),
                    patch.object(module, "_prepare_google_form", return_value="PREPARED") as prepare,
                    patch.object(module, "_auto_submit_google_form") as submit,
                ):
                    result = module.prepare_external_application_page(
                        page,
                        application_identity="synthetic-job:1",
                        title="Synthetic role",
                        company="Synthetic employer",
                    )

                self.assertEqual(result, "PREPARED")
                self.assertEqual(prepare.call_args.args[1:7], (
                    expected["name"],
                    expected["email"],
                    expected["phone"],
                    expected["current_location"],
                    expected["current_company"],
                    expected["resume_path"],
                ))
                submit.assert_not_called()

    def test_missing_required_profile_values_stop_synthetic_ats_before_submit(self):
        page = SimpleNamespace(url="https://synthetic.invalid/application")
        incomplete_profile = dict(self.PROFILE_DATA, email="", phone="")
        with (
            patch.object(shared_profile, "PROFILE", incomplete_profile),
            patch.dict(os.environ, {}, clear=True),
            patch.object(
                external_apply.EXECUTION_POLICY,
                "allows_browser_actions",
                return_value=True,
            ),
            patch.object(external_apply, "_text", return_value="synthetic form"),
            patch.object(external_apply, "detect_ats", return_value="SYNTHETIC_ATS"),
            patch.object(external_apply, "_external_page_has_error", return_value=False),
            patch.object(external_apply, "_wait_for_manual_consent", return_value=True),
            patch.object(external_apply, "_click_external_application_start", return_value=page),
            patch.object(external_apply, "_looks_like_application_form", return_value=True),
            patch.object(external_apply, "_fill_known_application_fields", return_value=0),
            patch.object(external_apply, "_fill_known_fields", return_value=0) as fill_fields,
            patch.object(external_apply, "_upload_resume", return_value=False),
            patch.object(external_apply, "_fill_known_profile_links", return_value=0),
            patch.object(external_apply, "_select_known_dropdowns", return_value=0),
            patch.object(external_apply, "_check_known_terms_consent", return_value=False),
            patch.object(external_apply, "_required_empty_count", return_value=1),
            patch.object(external_apply, "_auto_submit_external_application") as submit,
        ):
            result = external_apply.prepare_external_application_page(
                page,
                application_identity="synthetic-job:1",
                title="Synthetic role",
                company="Synthetic employer",
            )

        self.assertEqual(result, "READY_FOR_REVIEW")
        self.assertEqual(fill_fields.call_args.args[1:6], (
            "Synthetic Ada Example",
            "",
            "",
            "Sample City, Sample State, Exampleland",
            "",
        ))
        submit.assert_not_called()

    def test_explicit_legacy_field_arguments_remain_supported(self):
        page = SimpleNamespace(url="https://synthetic.invalid/forms")
        overrides = {
            "resume_path": "explicit-synthetic-resume.pdf",
            "name": "Synthetic Override Name",
            "email": "override@example.invalid",
            "phone": "5550199",
            "current_location": "Synthetic Override Location",
            "current_company": "Synthetic Override Company",
        }
        for module in (external_app, external_apply):
            with self.subTest(module=module.__name__):
                with (
                    patch.object(shared_profile, "PROFILE", self.PROFILE_DATA),
                    patch.dict(os.environ, {}, clear=True),
                    patch.object(
                        module.EXECUTION_POLICY,
                        "allows_browser_actions",
                        return_value=True,
                    ),
                    patch.object(module, "_text", return_value="synthetic form"),
                    patch.object(module, "detect_ats", return_value="GOOGLE_FORMS"),
                    patch.object(module, "_external_page_has_error", return_value=False),
                    patch.object(module, "_wait_for_manual_consent", return_value=True),
                    patch.object(module, "_prepare_google_form", return_value="PREPARED") as prepare,
                    patch.object(module, "_auto_submit_google_form") as submit,
                ):
                    result = module.prepare_external_application_page(
                        page,
                        **overrides,
                        application_identity="synthetic-job:1",
                        title="Synthetic role",
                        company="Synthetic employer",
                    )

                self.assertEqual(result, "PREPARED")
                self.assertEqual(prepare.call_args.args[1:7], (
                    overrides["name"],
                    overrides["email"],
                    overrides["phone"],
                    overrides["current_location"],
                    overrides["current_company"],
                    overrides["resume_path"],
                ))
                submit.assert_not_called()

    def test_active_generic_ats_path_receives_profile_before_mocked_submit_gate(self):
        page = SimpleNamespace(url="https://synthetic.invalid/generic-form")
        with (
            patch.object(shared_profile, "PROFILE", self.PROFILE_DATA),
            patch.dict(os.environ, {}, clear=True),
            patch.object(external_app.config, "AUTO_SUBMIT", True),
            patch.object(external_app, "UNKNOWN_QUESTIONS_POLICY", "SKIP"),
            patch.object(
                external_app.EXECUTION_POLICY,
                "allows_browser_actions",
                return_value=True,
            ),
            patch.object(external_app, "_text", return_value="synthetic form"),
            patch.object(external_app, "detect_ats", return_value="SYNTHETIC_ATS"),
            patch.object(external_app, "_external_page_has_error", return_value=False),
            patch.object(external_app, "_wait_for_manual_consent", return_value=True),
            patch.object(external_app, "_click_external_application_start", return_value=page),
            patch.object(external_app, "_looks_like_application_form", return_value=True),
            patch.object(external_app, "_fill_known_application_fields", return_value=0),
            patch.object(external_app, "_fill_known_fields", return_value=0) as fill_fields,
            patch.object(external_app, "_upload_resume", return_value=False),
            patch.object(external_app, "_fill_known_profile_links", return_value=0),
            patch.object(external_app, "_select_known_dropdowns", return_value=0),
            patch.object(external_app, "_check_known_terms_consent", return_value=False),
            patch.object(external_app, "_required_empty_count", return_value=0),
            patch.object(
                external_app,
                "_auto_submit_external_application",
                return_value="SYNTHETIC_SUBMIT_GATE",
            ) as submit_gate,
        ):
            result = external_app.prepare_external_application_page(
                page,
                application_identity="synthetic-job:1",
                title="Synthetic role",
                company="Synthetic employer",
            )

        self.assertEqual(result, "SYNTHETIC_SUBMIT_GATE")
        self.assertEqual(fill_fields.call_args.args[1:6], (
            "Synthetic Ada Example",
            "ada@example.invalid",
            "5550100",
            "Sample City, Sample State, Exampleland",
            "",
        ))
        submit_gate.assert_called_once()


if __name__ == "__main__":
    unittest.main()
