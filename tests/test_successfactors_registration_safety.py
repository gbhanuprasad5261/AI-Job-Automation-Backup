import unittest
from unittest.mock import MagicMock, patch

import config
import external_app


class FakeLocator:
    def __init__(self, elements=()):
        self.elements = list(elements)

    def count(self):
        return len(self.elements)

    def nth(self, index):
        return self.elements[index]


class FakeControl:
    def __init__(self, label=""):
        self.label = label
        self.fill = MagicMock()
        self.click = MagicMock()
        self.select_option = MagicMock()

    def is_visible(self):
        return True

    def get_attribute(self, name):
        return {"id": "candidate-password", "type": "password"}.get(name)

    def inner_text(self):
        return self.label

    def scroll_into_view_if_needed(self):
        return None


class FakePage:
    def __init__(self, password_fields=(), selects=(), controls=()):
        self.url = "https://careers.successfactors.com/account/register"
        self.password_fields = FakeLocator(password_fields)
        self.selects = FakeLocator(selects)
        self.controls = FakeLocator(controls)
        self.locator_calls = []
        self.wait_for_timeout = MagicMock()

    def locator(self, selector):
        self.locator_calls.append(selector)
        if selector.startswith("input[type='password']"):
            return self.password_fields
        if selector == "select":
            return self.selects
        if selector.startswith("button,"):
            return self.controls
        raise AssertionError(f"Unexpected locator search: {selector}")


class SuccessFactorsRegistrationSafetyTests(unittest.TestCase):
    def test_auto_submit_false_stops_before_any_account_page_interaction(self):
        password = FakeControl()
        country = FakeControl()
        register = FakeControl("Create Account")
        page = FakePage([password], [country], [register])

        with (
            patch.object(config, "AUTO_SUBMIT", False),
            patch.object(external_app, "SUCCESSFACTORS_PASSWORD", "configured-secret"),
        ):
            result = external_app._prepare_successfactors_account(page)

        self.assertEqual(result, "READY_FOR_REVIEW")
        self.assertEqual(page.locator_calls, [])
        password.fill.assert_not_called()
        country.select_option.assert_not_called()
        register.click.assert_not_called()

    def test_auto_submit_true_without_password_preserves_login_required(self):
        page = FakePage()

        with (
            patch.object(config, "AUTO_SUBMIT", True),
            patch.object(external_app, "SUCCESSFACTORS_PASSWORD", ""),
        ):
            result = external_app._prepare_successfactors_account(page)

        self.assertEqual(result, "LOGIN_REQUIRED")
        self.assertEqual(page.locator_calls, [])

    def test_auto_submit_true_keeps_account_registration_path_available(self):
        password = FakeControl()
        register = FakeControl("Create Account")
        page = FakePage([password], controls=[register])
        register.click.side_effect = lambda: setattr(
            page, "url", "https://careers.successfactors.com/application"
        )

        with (
            patch.object(config, "AUTO_SUBMIT", True),
            patch.object(external_app, "SUCCESSFACTORS_PASSWORD", "configured-secret"),
            patch.object(external_app, "_required_empty_count", return_value=0),
        ):
            result = external_app._prepare_successfactors_account(page)

        self.assertEqual(result, "CONTINUE")
        password.fill.assert_called_once_with("configured-secret")
        register.click.assert_called_once_with()
        self.assertTrue(
            any(selector.startswith("button,") for selector in page.locator_calls)
        )

    def test_auto_submit_true_still_stops_on_missing_required_fields(self):
        password = FakeControl()
        register = FakeControl("Register")
        page = FakePage([password], controls=[register])

        with (
            patch.object(config, "AUTO_SUBMIT", True),
            patch.object(external_app, "SUCCESSFACTORS_PASSWORD", "configured-secret"),
            patch.object(external_app, "_required_empty_count", return_value=1),
        ):
            result = external_app._prepare_successfactors_account(page)

        self.assertEqual(result, "READY_FOR_REVIEW")
        password.fill.assert_called_once_with("configured-secret")
        self.assertFalse(
            any(selector.startswith("button,") for selector in page.locator_calls)
        )
        register.click.assert_not_called()


if __name__ == "__main__":
    unittest.main()
