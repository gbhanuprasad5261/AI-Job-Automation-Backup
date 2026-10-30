import os
import unittest
from unittest.mock import Mock, patch

import external_app
import external_apply
import profile as shared_profile


class ExternalProfileFormCompatibilityTests(unittest.TestCase):
    def _country_dropdown(self, module, country, *, select_error=None):
        field = Mock()
        field.input_value.return_value = ""
        if select_error is not None:
            field.select_option.side_effect = select_error

        selects = Mock()
        selects.count.return_value = 1
        selects.nth.return_value = field
        page = Mock()
        page.locator.return_value = selects

        with (
            patch.object(shared_profile, "PROFILE", {"country": country}),
            patch.dict(os.environ, {}, clear=True),
            patch.object(module, "_visible", return_value=True),
            patch.object(module, "_field_text", return_value="what is your location"),
        ):
            result = module._select_known_dropdowns(page)

        return result, field

    def test_country_dropdown_uses_exact_shared_profile_value(self):
        for module in (external_app, external_apply):
            with self.subTest(module=module.__name__):
                result, field = self._country_dropdown(module, "Synthetic Republic")

                self.assertEqual(result, 1)
                field.select_option.assert_called_once_with(label="Synthetic Republic")

    def test_missing_country_leaves_required_dropdown_unanswered(self):
        for module in (external_app, external_apply):
            with self.subTest(module=module.__name__):
                result, field = self._country_dropdown(module, "")

                self.assertEqual(result, 0)
                field.select_option.assert_not_called()

    def test_unavailable_profile_option_is_not_replaced_with_a_guess(self):
        for module in (external_app, external_apply):
            with self.subTest(module=module.__name__):
                result, field = self._country_dropdown(
                    module,
                    "Synthetic Republic",
                    select_error=ValueError("synthetic option unavailable"),
                )

                self.assertEqual(result, 0)
                field.select_option.assert_called_once_with(label="Synthetic Republic")

    def test_google_form_radio_answers_remain_unset_without_profile_facts(self):
        for module in (external_app, external_apply):
            with self.subTest(module=module.__name__):
                page = Mock()

                result = module._google_forms_confirmed_radio_answers(page)

                self.assertEqual(result, 0)
                page.locator.assert_not_called()


if __name__ == "__main__":
    unittest.main()
