import unittest
from unittest.mock import patch

import application_form


class ApplicationStepTests(unittest.TestCase):
    def test_application_step_bounds_remain_validated(self):
        self.assertTrue(application_form._valid_application_step(1, 4))
        self.assertTrue(application_form._valid_application_step(4, 4))
        self.assertFalse(application_form._valid_application_step(0, 4))
        self.assertFalse(application_form._valid_application_step(5, 4))

    def test_page_indicator_is_parsed(self):
        class Container:
            @staticmethod
            def inner_text():
                return "2/4 pages"

        with patch(
            "application_form.get_application_container",
            return_value=Container(),
        ):
            self.assertEqual(application_form.get_application_step(object()), (2, 4))

    def test_out_of_range_page_indicator_is_rejected(self):
        class Container:
            @staticmethod
            def inner_text():
                return "5/4 pages"

        with patch(
            "application_form.get_application_container",
            return_value=Container(),
        ):
            self.assertIsNone(application_form.get_application_step(object()))


if __name__ == "__main__":
    unittest.main()
