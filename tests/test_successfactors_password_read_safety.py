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


class SuccessFactorsPasswordReadSafetyTests(unittest.TestCase):
    def test_auto_submit_false_does_not_read_password_or_interact_with_page(self):
        password = FakeControl()
        country = FakeControl()
        register = FakeControl("Create Account")
        page = FakePage([password], [country], [register])

        with (
            patch.object(config, "AUTO_SUBMIT", False),
            patch.object(external_app.os, "getenv") as getenv,
        ):
            result = external_app._prepare_successfactors_account(page)

        self.assertEqual(result, "READY_FOR_REVIEW")
        getenv.assert_not_called()
        self.assertEqual(page.locator_calls, [])
        password.fill.assert_not_called()
        country.select_option.assert_not_called()
        register.click.assert_not_called()

    def test_auto_submit_true_with_missing_password_keeps_login_required(self):
        page = FakePage()

        with (
            patch.object(config, "AUTO_SUBMIT", True),
            patch.object(external_app.os, "getenv", return_value="") as getenv,
        ):
            result = external_app._prepare_successfactors_account(page)

        self.assertEqual(result, "LOGIN_REQUIRED")
        getenv.assert_called_once_with("SUCCESSFACTORS_PASSWORD", "")
        self.assertEqual(page.locator_calls, [])

    def test_auto_submit_true_reads_configured_password_and_continues_existing_logic(self):
        password = FakeControl()
        register = FakeControl("Create Account")
        page = FakePage([password], controls=[register])
        register.click.side_effect = lambda: setattr(
            page,
            "url",
            "https://careers.successfactors.com/application",
        )

        with (
            patch.object(config, "AUTO_SUBMIT", True),
            patch.object(
                external_app.os,
                "getenv",
                return_value="configured-secret",
            ) as getenv,
            patch.object(external_app, "_required_empty_count", return_value=0),
        ):
            result = external_app._prepare_successfactors_account(page)

        self.assertEqual(result, "CONTINUE")
        getenv.assert_called_once_with("SUCCESSFACTORS_PASSWORD", "")
        password.fill.assert_called_once_with("configured-secret")
        register.click.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
