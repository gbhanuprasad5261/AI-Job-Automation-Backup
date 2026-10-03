import contextlib
import io
import unittest
from unittest.mock import patch

import application_form


class _Container:
    def __init__(self, text):
        self.text = text

    def inner_text(self):
        return self.text


class ApplicationStepProgressTests(unittest.TestCase):
    def get_step(self, text):
        with patch(
            "application_form.get_application_container",
            return_value=_Container(text),
        ):
            return application_form.get_application_step(object())

    def test_resume_date_is_not_application_progress(self):
        for text in (
            "Resume: Bhanu_Prasad_Resume.pdf 9/28/2026",
            "Resume: added 9/28/2026 pages available",
        ):
            with self.subTest(text=text):
                self.assertIsNone(self.get_step(text))

    def test_labeled_page_counts_are_parsed(self):
        for current in range(1, 5):
            with self.subTest(current=current):
                self.assertEqual(
                    self.get_step(f"Application questions {current}/4 pages"),
                    (current, 4),
                )

    def test_existing_explicit_page_labels_remain_supported(self):
        cases = (
            ("Application page: 2/4", (2, 4)),
            ("Page 3 of 4", (3, 4)),
            ("Step 4 of 4", (4, 4)),
        )
        for text, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(self.get_step(text), expected)

    def test_unrelated_numeric_fractions_are_not_progress(self):
        unrelated_text = (
            "Salary range 9/28, employee ID 3/8, phone extension 1/4, "
            "and resume date 9/28/2026"
        )
        self.assertIsNone(self.get_step(unrelated_text))

    def test_progress_percentages_are_not_inferred_as_page_counts(self):
        # get_application_step has never mapped generic percentage values to
        # page counts; the Review verifier handles progressbar evidence.
        for percent in (25, 50, 75, 100):
            with self.subTest(percent=percent):
                self.assertIsNone(self.get_step(f"{percent} percent complete"))

    def test_status_printer_uses_the_same_progress_specific_parser(self):
        with patch(
            "application_form.get_application_container",
            return_value=_Container("Resume file 9/28/2026"),
        ), contextlib.redirect_stdout(io.StringIO()) as output:
            application_form.print_application_status(object())
        self.assertEqual(output.getvalue().strip(), "Application page: unknown")

    def test_status_printer_keeps_existing_caller_output_for_page_label(self):
        with patch(
            "application_form.get_application_container",
            return_value=_Container("4/4 pages"),
        ), contextlib.redirect_stdout(io.StringIO()) as output:
            application_form.print_application_status(object())
        self.assertEqual(output.getvalue().strip(), "Application page: 4/4")


if __name__ == "__main__":
    unittest.main()
