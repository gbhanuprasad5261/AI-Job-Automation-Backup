"""Synthetic in-memory tests for pure CSV contracts and Link validation."""

import csv
from io import StringIO
from pathlib import Path
import subprocess
import sys
import unittest

from csv_contracts import missing_required_columns, validate_link_value


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
    def test_contract_helpers_do_not_load_configuration_or_browser_modules(self):
        probe = (
            "import sys; import csv_contracts; "
            "assert 'config' not in sys.modules; "
            "assert not any(name == 'playwright' or name.startswith('playwright.') "
            "for name in sys.modules)"
        )
        result = subprocess.run(
            [sys.executable, "-B", "-c", probe],
            cwd=Path(__file__).resolve().parents[1],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

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

    def test_unterminated_quoted_header_is_rejected_by_strict_csv_parser(self):
        with self.assertRaises(csv.Error):
            parsed_headers('"Title,Company,Location,Easy Apply,Link\n')

    def test_empty_input_reports_all_required_headers(self):
        self.assertEqual(
            missing_required_columns(parsed_headers(""), DETAILS_REQUIRED),
            tuple(sorted(DETAILS_REQUIRED)),
        )

    def test_empty_header_sequence_reports_all_required_headers(self):
        for headers in (None, []):
            with self.subTest(headers=headers):
                self.assertEqual(
                    missing_required_columns(headers, DETAILS_REQUIRED),
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

    def test_header_order_does_not_affect_required_column_membership(self):
        text = "Link,Easy Apply,Location,Company,Title\n"
        self.assertEqual(
            missing_required_columns(parsed_headers(text), DETAILS_REQUIRED),
            (),
        )

    def test_duplicate_header_is_not_reported_as_missing(self):
        # This helper checks required-name membership; duplicate detection is
        # explicitly outside its contract and remains a parser/caller concern.
        text = "Title,Company,Location,Easy Apply,Link,Link\n"
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


class LinkValueValidationTests(unittest.TestCase):
    def test_accepts_absolute_http_and_https_urls(self):
        for value in (
            "http://example.com/jobs/1",
            "https://example.com/jobs/1?source=synthetic",
            "HTTPS://example.com:443/jobs/1",
            "http://[2001:db8::1]:8080/jobs/1",
        ):
            with self.subTest(value=value):
                self.assertEqual(validate_link_value(value), (True, None))

    def test_accepts_nonempty_hostname_edge_forms_without_network_access(self):
        for value in (
            "http://localhost/jobs/1",
            "https://127.0.0.1:8443/jobs/1",
            "https://[2001:db8::1]/jobs/1",
            "https://example.com./jobs/1",
            "https://bücher.example/jobs/1",
        ):
            with self.subTest(value=value):
                self.assertEqual(validate_link_value(value), (True, None))

    def test_classifies_missing_and_whitespace_only_values(self):
        for value in (None, "", "   ", "\t\r\n"):
            with self.subTest(value=value):
                self.assertEqual(validate_link_value(value), (False, "LINK_MISSING"))

    def test_rejects_non_string_values_without_coercion(self):
        for value in (123, b"https://example.com", object()):
            with self.subTest(value_type=type(value).__name__):
                self.assertEqual(validate_link_value(value), (False, "LINK_TYPE_INVALID"))

    def test_rejects_unsupported_schemes(self):
        for value in (
            "ftp://example.com/jobs/1",
            "javascript:alert(1)",
            "file:///jobs/1",
        ):
            with self.subTest(value=value):
                self.assertEqual(
                    validate_link_value(value), (False, "LINK_UNSUPPORTED_SCHEME")
                )

    def test_invalid_reason_codes_are_deterministic(self):
        for value, expected in (
            (None, "LINK_MISSING"),
            (42, "LINK_TYPE_INVALID"),
            ("ftp://example.com/", "LINK_UNSUPPORTED_SCHEME"),
            ("http://example.com:invalid/", "LINK_INVALID"),
        ):
            with self.subTest(value=value):
                results = [validate_link_value(value) for _ in range(3)]
                self.assertEqual(results, [(False, expected)] * 3)

    def test_rejects_relative_or_scheme_less_values(self):
        for value in ("/jobs/1", "//example.com/jobs/1", "example.com/jobs/1"):
            with self.subTest(value=value):
                self.assertEqual(validate_link_value(value), (False, "LINK_INVALID"))

    def test_rejects_malformed_urls_and_authorities(self):
        for value in (
            "http://",
            "http:///jobs/1",
            "http://?query=1",
            "http://#fragment",
            "http://[]/jobs/1",
            "http://[::1]extra/jobs/1",
            "http://2001:db8::1/jobs/1",
            "http://[::1/jobs/1",
            "http://example.com:",
            "http://example.com:abc/jobs/1",
            "http://example.com:65536/jobs/1",
            "http://user:secret@example.com/jobs/1",
            "https://example.com/a b",
            " https://example.com/jobs/1",
            "https://example.com/jobs/1 ",
            "https://example.com/line\nbreak",
            "https://example.com\\@attacker.invalid/jobs/1",
            "https://example.com/%ZZ",
        ):
            with self.subTest(value=value):
                self.assertEqual(validate_link_value(value), (False, "LINK_INVALID"))


if __name__ == "__main__":
    unittest.main()
