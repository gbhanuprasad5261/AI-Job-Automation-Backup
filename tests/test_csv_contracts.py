"""Synthetic in-memory tests for pure CSV required-header validation."""

import csv
from io import StringIO
import unittest

from csv_contracts import missing_required_columns


DETAILS_REQUIRED = {
    "Title",
    "Company",
    "Location",
    "Easy Apply",
    "Link",
}
ANALYSIS_REQUIRED = DETAILS_REQUIRED | {"Description"}


def parsed_headers(text):
    reader = csv.DictReader(StringIO(text), strict=True)
    return reader.fieldnames


class CsvRequiredHeaderTests(unittest.TestCase):
    def test_valid_details_headers(self):
        text = "Title,Company,Location,Easy Apply,Link\n"
        self.assertEqual(
            missing_required_columns(parsed_headers(text), DETAILS_REQUIRED),
            (),
        )

    def test_valid_analyzer_headers(self):
        text = "Title,Company,Location,Easy Apply,Link,Description\n"
        self.assertEqual(
            missing_required_columns(parsed_headers(text), ANALYSIS_REQUIRED),
            (),
        )

    def test_missing_required_header_returns_sorted_names(self):
        text = "Title,Location\n"
        self.assertEqual(
            missing_required_columns(parsed_headers(text), DETAILS_REQUIRED),
            ("Company", "Easy Apply", "Link"),
        )

    def test_empty_input_reports_all_required_headers(self):
        self.assertEqual(
            missing_required_columns(parsed_headers(""), DETAILS_REQUIRED),
            tuple(sorted(DETAILS_REQUIRED)),
        )

    def test_header_only_input_passes_header_validation(self):
        text = "Title,Company,Location,Easy Apply,Link\n"
        reader = csv.DictReader(StringIO(text), strict=True)
        self.assertEqual(
            missing_required_columns(reader.fieldnames, DETAILS_REQUIRED),
            (),
        )
        self.assertEqual(list(reader), [])

    def test_unexpected_extra_column_is_accepted(self):
        text = "Title,Company,Location,Easy Apply,Link,Source Note\n"
        self.assertEqual(
            missing_required_columns(parsed_headers(text), DETAILS_REQUIRED),
            (),
        )

    def test_header_matching_preserves_exact_case(self):
        text = "Title,Company,Location,Easy Apply,link\n"
        self.assertEqual(
            missing_required_columns(parsed_headers(text), DETAILS_REQUIRED),
            ("Link",),
        )


if __name__ == "__main__":
    unittest.main()
