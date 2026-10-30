import os
import unittest
from unittest.mock import Mock, patch

import application_form
import external_app
import external_apply
import profile as shared_profile


class ProfileCompletenessTests(unittest.TestCase):
    PROFILE_DATA = {
        "first_name": "Synthetic",
        "last_name": "Candidate",
        "email": "",
        "phone": "   ",
        "city": "Synthetic City",
        "state": "Synthetic State",
        "country": "Synthetic Country",
        "degree": "Synthetic Degree",
        "field_of_study": "Synthetic Study",
        "specialization": "Synthetic Specialization",
        "graduation_year": "2030",
        "experience_years": "0",
        "skills": ["Synthetic Skill"],
        "resume_path": "synthetic-resume.pdf",
    }

    def test_completeness_distinguishes_configured_missing_optional_and_unsupported(self):
        with patch.object(shared_profile, "PROFILE", self.PROFILE_DATA), patch.dict(
            os.environ, {}, clear=True
        ):
            result = shared_profile.validate_profile_completeness(
                required_fields=(
                    "name", "email", "city", "country", "street_address",
                    "employment_history", "internship_history",
                    "project_experience", "availability", "resume_path",
                ),
                optional_fields=("phone", "current_company", "unmapped_question"),
            )

        self.assertEqual(
            result,
            {
                "configured": ["city", "country", "name", "resume_path"],
                "missing": [
                    "availability", "email", "employment_history",
                    "internship_history", "project_experience", "street_address",
                ],
                "optional": ["current_company", "phone"],
                "unsupported": ["unmapped_question"],
            },
        )
        self.assertNotIn("Synthetic", repr(result))
        self.assertNotIn("synthetic-resume.pdf", repr(result))

    def test_empty_environment_override_remains_missing_and_precedence_is_preserved(self):
        overrides = {
            "APPLICANT_NAME": "  Synthetic Override  ",
            "APPLICANT_EMAIL": "override@example.invalid",
            "APPLICANT_PHONE": "5550101",
            "APPLICANT_CITY": "Override City",
            "APPLICANT_STATE": "Override State",
            "APPLICANT_COUNTRY": "Override Country",
            "CURRENT_LOCATION": "",
            "CURRENT_COMPANY": "",
            "RESUME_PATH": "override-resume.pdf",
        }
        with patch.object(shared_profile, "PROFILE", self.PROFILE_DATA), patch.dict(
            os.environ, overrides, clear=True
        ):
            values = shared_profile.get_application_profile()
            completeness = shared_profile.validate_profile_completeness(
                required_fields=("name", "email", "phone", "current_location"),
                optional_fields=("current_company", "resume_path"),
            )

        self.assertEqual(values["name"], "Synthetic Override")
        self.assertEqual(values["email"], overrides["APPLICANT_EMAIL"])
        self.assertEqual(values["phone"], overrides["APPLICANT_PHONE"])
        self.assertEqual(values["city"], overrides["APPLICANT_CITY"])
        self.assertEqual(values["country"], overrides["APPLICANT_COUNTRY"])
        self.assertEqual(values["current_location"], "")
        self.assertEqual(values["current_company"], "")
        self.assertEqual(values["resume_path"], overrides["RESUME_PATH"])
        self.assertIn("current_location", completeness["missing"])
        self.assertIn("current_company", completeness["optional"])

    def test_linkedin_known_location_mapping_uses_shared_profile_values(self):
        with (
            patch.object(application_form, "CITY", "Synthetic City"),
            patch.object(application_form, "STATE", "Synthetic State"),
            patch.object(application_form, "COUNTRY", "Synthetic Country"),
        ):
            self.assertEqual(
                application_form._value_for_text_question("preferred city"),
                "Synthetic City",
            )
            self.assertEqual(
                application_form._value_for_text_question("current state"),
                "Synthetic State",
            )
            self.assertEqual(
                application_form._value_for_text_question("country of residence"),
                "Synthetic Country",
            )

    def test_unconfigured_internship_project_and_availability_answers_are_not_guessed(self):
        with (
            patch.object(application_form, "INTERNSHIP_EXPERIENCE", ""),
            patch.object(application_form, "NOTICE_PERIOD", ""),
            patch.object(application_form, "WILLING_TO_RELOCATE", ""),
            patch.object(application_form, "WILLING_ONSITE", ""),
            patch.object(application_form, "SHIFT_COMFORT", ""),
            patch.object(application_form, "WEEKEND_COMFORT", ""),
        ):
            self.assertIsNone(
                application_form._choose_safe_radio_answer(
                    "Do you have internship experience?", ["Yes", "No"]
                )
            )
            self.assertIsNone(
                application_form._choose_safe_radio_answer(
                    "Do you have project experience?", ["Yes", "No"]
                )
            )
            self.assertIsNone(
                application_form._choose_safe_radio_answer(
                    "Are you available to start immediately?", ["Yes", "No"]
                )
            )
            self.assertIsNone(
                application_form._value_for_text_question("notice period")
            )

    def test_linkedin_name_email_and_phone_helpers_use_shared_profile_fields(self):
        class Field:
            def __init__(self, placeholder):
                self.placeholder = placeholder

            def is_visible(self):
                return True

        first = Field("First name")
        last = Field("Last name")
        full = Field("Full name")

        class NameContainer:
            def locator(self, selector):
                if "firstName" in selector or "given-name" in selector:
                    fields = [first]
                elif "name" in selector:
                    fields = [first, last, full]
                else:
                    fields = []
                locator = Mock()
                locator.count.return_value = len(fields)
                locator.nth.side_effect = fields.__getitem__
                return locator

        filled_names = []
        synthetic_profile = {
            "first_name": "Synthetic",
            "last_name": "Candidate",
            "name": "Synthetic Candidate",
            "email": "synthetic@example.invalid",
            "phone": "5550103",
        }
        with (
            patch.object(application_form, "_APPLICATION_PROFILE", synthetic_profile),
            patch.object(
                application_form,
                "safe_attribute",
                side_effect=lambda field, name: (
                    field.placeholder if name == "placeholder" else ""
                ),
            ),
            patch.object(
                application_form,
                "fill_if_empty",
                side_effect=lambda _field, value: filled_names.append(value) or True,
            ),
        ):
            self.assertTrue(application_form.fill_name(NameContainer()))

        self.assertIn("Synthetic", filled_names)
        self.assertIn("Candidate", filled_names)
        self.assertIn("Synthetic Candidate", filled_names)

        email_locator = Mock()
        email_locator.count.return_value = 1
        email_container = Mock()
        email_container.locator.return_value = email_locator
        phone_locator = Mock()
        phone_locator.count.return_value = 1
        phone_container = Mock()
        phone_container.locator.return_value = phone_locator
        contact_values = []
        with (
            patch.object(application_form, "EMAIL", synthetic_profile["email"]),
            patch.object(application_form, "PHONE", synthetic_profile["phone"]),
            patch.object(
                application_form,
                "fill_if_empty",
                side_effect=lambda _field, value: contact_values.append(value) or True,
            ),
            patch.object(application_form, "select_india_country_code"),
        ):
            self.assertTrue(application_form.fill_email(email_container))
            self.assertTrue(application_form.fill_phone(phone_container))

        self.assertEqual(
            contact_values,
            [synthetic_profile["email"], synthetic_profile["phone"]],
        )

    def test_external_handlers_support_alternative_contact_labels_and_ignore_blank_values(self):
        labels = (
            "work email address",
            "mobile telephone number",
            "given name",
            "family name",
            "legal full name",
            "current company",
            "street address",
        )
        for module in (external_app, external_apply):
            with self.subTest(module=module.__name__):
                fields = [Mock() for _ in labels]
                for field in fields:
                    field.input_value.return_value = ""
                collection = Mock()
                collection.count.return_value = len(fields)
                collection.nth.side_effect = fields.__getitem__
                page = Mock()
                page.locator.return_value = collection
                filled = []

                with (
                    patch.object(module, "_visible", return_value=True),
                    patch.object(module, "_attr", return_value="text"),
                    patch.object(module, "_field_text", side_effect=labels),
                    patch.object(module, "_fill", side_effect=lambda element, value: filled.append((element, value)) or True),
                ):
                    count = module._fill_known_fields(
                        page,
                        "Synthetic Ada Example",
                        "ada@example.invalid",
                        "5550102",
                        current_location="Synthetic City, Synthetic State, Synthetic Country",
                        current_company="",
                    )

                self.assertEqual(count, 5)
                self.assertEqual(
                    [value for _, value in filled],
                    [
                        "ada@example.invalid", "5550102", "Synthetic", "Ada Example",
                        "Synthetic Ada Example",
                    ],
                )
                self.assertNotIn("", [value for _, value in filled])


if __name__ == "__main__":
    unittest.main()
