import csv
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import job_analyzer
import job_details
import output_files


class CsvOutputDurabilityTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.root = Path(self.temp_dir.name)

    def _temporary_files(self, destination):
        return list(destination.parent.glob(f".{destination.name}.*.tmp"))

    def test_successful_replacement_writes_complete_new_content(self):
        destination = self.root / "output.csv"
        destination.write_text("old\n", encoding="utf-8")

        output_files.write_replaced_output(
            destination,
            lambda file: file.write("header\nnew row\n"),
            newline="",
        )

        self.assertEqual(destination.read_text(encoding="utf-8"), "header\nnew row\n")
        self.assertEqual(self._temporary_files(destination), [])

    def test_repeated_replacements_leave_only_the_latest_complete_output(self):
        destination = self.root / "output.csv"
        destination.write_text("original\n", encoding="utf-8")

        for contents in ("first replacement\n", "second replacement\n"):
            output_files.write_replaced_output(
                destination, lambda file, value=contents: file.write(value)
            )

        self.assertEqual(destination.read_text(encoding="utf-8"), "second replacement\n")
        self.assertEqual(self._temporary_files(destination), [])

    def test_serialization_failure_preserves_existing_destination_and_cleans_temp(self):
        destination = self.root / "output.csv"
        destination.write_text("previous valid contents\n", encoding="utf-8")

        def fail_after_partial_write(file):
            file.write("partial contents\n")
            raise OSError("simulated serialization failure")

        with self.assertRaisesRegex(OSError, "simulated serialization failure"):
            output_files.write_replaced_output(destination, fail_after_partial_write)

        self.assertEqual(destination.read_text(encoding="utf-8"), "previous valid contents\n")
        self.assertEqual(self._temporary_files(destination), [])

    def test_replace_failure_preserves_existing_destination_and_cleans_temp(self):
        destination = self.root / "output.csv"
        destination.write_text("previous valid contents\n", encoding="utf-8")

        with patch.object(output_files.os, "replace", side_effect=OSError("replace denied")):
            with self.assertRaisesRegex(OSError, "replace denied"):
                output_files.write_replaced_output(destination, lambda file: file.write("new\n"))

        self.assertEqual(destination.read_text(encoding="utf-8"), "previous valid contents\n")
        self.assertEqual(self._temporary_files(destination), [])

    def test_temporary_cleanup_failure_does_not_mask_serialization_error(self):
        destination = self.root / "output.csv"
        destination.write_text("previous valid contents\n", encoding="utf-8")

        def fail_after_partial_write(file):
            file.write("partial contents\n")
            raise ValueError("original serialization failure")

        with patch.object(output_files.os, "remove", side_effect=OSError("cleanup denied")):
            with self.assertRaisesRegex(ValueError, "original serialization failure"):
                output_files.write_replaced_output(destination, fail_after_partial_write)

        self.assertEqual(destination.read_text(encoding="utf-8"), "previous valid contents\n")
        leftovers = self._temporary_files(destination)
        self.assertEqual(len(leftovers), 1)
        leftovers[0].unlink()

    def test_temporary_file_creation_failure_preserves_existing_destination(self):
        destination = self.root / "output.csv"
        destination.write_text("previous valid contents\n", encoding="utf-8")

        with patch.object(
            output_files.tempfile,
            "NamedTemporaryFile",
            side_effect=OSError("temporary directory unavailable"),
        ):
            with self.assertRaisesRegex(OSError, "temporary directory unavailable"):
                output_files.write_replaced_output(destination, lambda file: file.write("new\n"))

        self.assertEqual(destination.read_text(encoding="utf-8"), "previous valid contents\n")

    def test_analyzer_write_failure_does_not_truncate_previous_analysis(self):
        input_path = self.root / "job_details.csv"
        output_path = self.root / "job_analysis.csv"
        with input_path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=[
                "Title", "Company", "Location", "Easy Apply", "Link", "Description",
            ])
            writer.writeheader()
            writer.writerow({
                "Title": "Backend Engineer",
                "Company": "Example Corp",
                "Location": "Bengaluru",
                "Easy Apply": "Yes",
                "Link": "https://www.linkedin.com/jobs/view/1234567890/",
                "Description": "Java backend engineer. " * 20,
            })
        original = b"previous valid analysis\n"
        output_path.write_bytes(original)

        class FailingWriter:
            def __init__(self, file, **_kwargs):
                self.file = file

            def writeheader(self):
                self.file.write("partial header\n")

            def writerow(self, _row):
                raise OSError("simulated analysis serialization failure")

        with (
            patch.object(job_analyzer, "INPUT_FILE", str(input_path)),
            patch.object(job_analyzer, "OUTPUT_FILE", str(output_path)),
            patch.object(job_analyzer.csv, "DictWriter", FailingWriter),
        ):
            with self.assertRaisesRegex(OSError, "simulated analysis serialization failure"):
                job_analyzer.analyze_jobs()

        self.assertEqual(output_path.read_bytes(), original)
        self.assertEqual(self._temporary_files(output_path), [])

    def test_analyzer_parse_failure_preserves_previous_analysis(self):
        input_path = self.root / "job_details.csv"
        output_path = self.root / "job_analysis.csv"
        input_path.write_bytes(b"Title,Description\n\xff,invalid utf-8\n")
        original = b"previous valid analysis\n"
        output_path.write_bytes(original)

        with (
            patch.object(job_analyzer, "INPUT_FILE", str(input_path)),
            patch.object(job_analyzer, "OUTPUT_FILE", str(output_path)),
        ):
            with self.assertRaises(UnicodeDecodeError):
                job_analyzer.analyze_jobs()

        self.assertEqual(output_path.read_bytes(), original)

    def test_analyzer_missing_input_preserves_previous_analysis(self):
        input_path = self.root / "missing_details.csv"
        output_path = self.root / "job_analysis.csv"
        original = b"previous valid analysis\n"
        output_path.write_bytes(original)

        with (
            patch.object(job_analyzer, "INPUT_FILE", str(input_path)),
            patch.object(job_analyzer, "OUTPUT_FILE", str(output_path)),
        ):
            with self.assertRaisesRegex(FileNotFoundError, "missing_details.csv not found"):
                job_analyzer.analyze_jobs()

        self.assertEqual(output_path.read_bytes(), original)

    def test_analyzer_malformed_schema_or_row_preserves_previous_analysis(self):
        input_path = self.root / "job_details.csv"
        output_path = self.root / "job_analysis.csv"
        original = b"previous valid analysis\n"
        output_path.write_bytes(original)
        malformed_inputs = (
            "Title,Link\nBackend Engineer,https://example.test/job\n",
            "Title,Company,Location,Easy Apply,Link,Description\nBackend,Example,Bengaluru\n",
            'Title,Company,Location,Easy Apply,Link,Description\nBackend,Example,Bengaluru,Yes,"unfinished\n',
        )

        with (
            patch.object(job_analyzer, "INPUT_FILE", str(input_path)),
            patch.object(job_analyzer, "OUTPUT_FILE", str(output_path)),
        ):
            for malformed in malformed_inputs:
                with self.subTest(malformed=malformed):
                    input_path.write_text(malformed, encoding="utf-8")
                    with self.assertRaises((ValueError, csv.Error)):
                        job_analyzer.analyze_jobs()
                    self.assertEqual(output_path.read_bytes(), original)

    def test_details_missing_input_and_valid_empty_input_preserve_prior_outputs(self):
        input_path = self.root / "jobs.csv"
        csv_path = self.root / "details.csv"
        diagnostics_path = self.root / "diagnostics.json"
        old_csv = b"previous details\n"
        old_diagnostics = "previous diagnostics"
        csv_path.write_bytes(old_csv)
        diagnostics_path.write_text(old_diagnostics, encoding="utf-8")
        previous_cwd = Path.cwd()
        try:
            import os
            os.chdir(self.root)
            with (
                patch.object(job_details, "INPUT_FILE", str(input_path)),
                patch.object(job_details, "OUTPUT_FILE", str(csv_path)),
                patch.object(job_details, "DIAGNOSTICS_FILE", str(diagnostics_path)),
                patch.object(job_details, "sync_playwright") as playwright,
            ):
                with self.assertRaisesRegex(FileNotFoundError, "jobs.csv not found"):
                    job_details.extract_job_details()
                self.assertFalse(playwright.called)

                input_path.write_text(
                    "Title,Company,Location,Easy Apply,Link\n",
                    encoding="utf-8",
                )
                job_details.extract_job_details()
                self.assertFalse(playwright.called)
        finally:
            os.chdir(previous_cwd)

        self.assertEqual(csv_path.read_bytes(), old_csv)
        self.assertEqual(diagnostics_path.read_text(encoding="utf-8"), old_diagnostics)

    def test_details_malformed_schema_or_row_fails_before_cdp_and_preserves_outputs(self):
        input_path = self.root / "jobs.csv"
        csv_path = self.root / "details.csv"
        diagnostics_path = self.root / "diagnostics.json"
        old_csv = b"previous details\n"
        old_diagnostics = "previous diagnostics"
        csv_path.write_bytes(old_csv)
        diagnostics_path.write_text(old_diagnostics, encoding="utf-8")
        malformed_inputs = (
            "Title,Link\nBackend,https://example.test/job\n",
            "Title,Company,Location,Easy Apply,Link\nBackend,Example,Bengaluru\n",
        )

        previous_cwd = Path.cwd()
        try:
            import os
            os.chdir(self.root)
            with (
                patch.object(job_details, "INPUT_FILE", str(input_path)),
                patch.object(job_details, "OUTPUT_FILE", str(csv_path)),
                patch.object(job_details, "DIAGNOSTICS_FILE", str(diagnostics_path)),
                patch.object(job_details, "sync_playwright") as playwright,
            ):
                for malformed in malformed_inputs:
                    with self.subTest(malformed=malformed):
                        input_path.write_text(malformed, encoding="utf-8")
                        with self.assertRaises(ValueError):
                            job_details.extract_job_details()
                        self.assertFalse(playwright.called)
                        self.assertEqual(csv_path.read_bytes(), old_csv)
                        self.assertEqual(
                            diagnostics_path.read_text(encoding="utf-8"),
                            old_diagnostics,
                        )
        finally:
            os.chdir(previous_cwd)

    def test_partial_extraction_writes_partial_rows_without_run_status(self):
        input_path = self.root / "jobs.csv"
        csv_path = self.root / "details.csv"
        diagnostics_path = self.root / "diagnostics.json"
        input_path.write_text(
            "Title,Company,Location,Easy Apply,Link\n"
            "No Link,Example,Bengaluru,Yes,\n"
            "Fails During Navigation,Example,Bengaluru,Yes,https://example.test/job\n",
            encoding="utf-8",
        )

        page = MagicMock()
        page.goto.side_effect = RuntimeError("simulated navigation failure")
        context = SimpleNamespace(pages=[page], new_page=lambda: page)
        browser = SimpleNamespace(contexts=[context])
        chromium = SimpleNamespace(connect_over_cdp=lambda _url: browser)
        playwright_context = SimpleNamespace(chromium=chromium)
        playwright_manager = MagicMock()
        playwright_manager.__enter__.return_value = playwright_context

        previous_cwd = Path.cwd()
        try:
            os.chdir(self.root)
            with (
                patch.object(job_details, "INPUT_FILE", str(input_path)),
                patch.object(job_details, "OUTPUT_FILE", str(csv_path)),
                patch.object(job_details, "DIAGNOSTICS_FILE", str(diagnostics_path)),
                patch.object(job_details, "sync_playwright", return_value=playwright_manager),
            ):
                job_details.extract_job_details()
        finally:
            os.chdir(previous_cwd)

        with csv_path.open(encoding="utf-8", newline="") as file:
            rows = list(csv.DictReader(file))
        diagnostics = json.loads(diagnostics_path.read_text(encoding="utf-8"))

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["Title"], "Fails During Navigation")
        self.assertEqual(rows[0]["Description"], "")
        self.assertEqual(len(diagnostics), 1)
        self.assertIn("simulated navigation failure", diagnostics[0]["error"])
        self.assertNotIsInstance(diagnostics, dict)

    def test_extraction_failure_before_output_writes_preserves_previous_pair(self):
        input_path = self.root / "jobs.csv"
        csv_path = self.root / "details.csv"
        diagnostics_path = self.root / "diagnostics.json"
        input_path.write_text(
            "Title,Company,Location,Easy Apply,Link\n"
            "Backend Engineer,Example,Bengaluru,Yes,https://example.test/job\n",
            encoding="utf-8",
        )
        previous_csv = b"previous details\n"
        previous_diagnostics = "previous diagnostics"
        csv_path.write_bytes(previous_csv)
        diagnostics_path.write_text(previous_diagnostics, encoding="utf-8")
        previous_cwd = Path.cwd()
        try:
            os.chdir(self.root)
            with (
                patch.object(job_details, "INPUT_FILE", str(input_path)),
                patch.object(job_details, "OUTPUT_FILE", str(csv_path)),
                patch.object(job_details, "DIAGNOSTICS_FILE", str(diagnostics_path)),
                patch.object(
                    job_details,
                    "sync_playwright",
                    side_effect=RuntimeError("simulated extraction startup failure"),
                ),
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "simulated extraction startup failure",
                ):
                    job_details.extract_job_details()
        finally:
            os.chdir(previous_cwd)

        self.assertEqual(csv_path.read_bytes(), previous_csv)
        self.assertEqual(
            diagnostics_path.read_text(encoding="utf-8"),
            previous_diagnostics,
        )

    def test_analyzer_transformation_failure_preserves_previous_analysis(self):
        input_path = self.root / "job_details.csv"
        output_path = self.root / "job_analysis.csv"
        with input_path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=[
                "Title", "Company", "Location", "Easy Apply", "Link", "Description",
            ])
            writer.writeheader()
            writer.writerow({
                "Title": "Backend Engineer",
                "Company": "Example Corp",
                "Location": "Bengaluru",
                "Easy Apply": "Yes",
                "Link": "https://www.linkedin.com/jobs/view/1234567890/",
                "Description": "Java backend engineer. " * 20,
            })
        original = b"previous valid analysis\n"
        output_path.write_bytes(original)

        with (
            patch.object(job_analyzer, "INPUT_FILE", str(input_path)),
            patch.object(job_analyzer, "OUTPUT_FILE", str(output_path)),
            patch.object(job_analyzer, "match_resume", side_effect=RuntimeError("transform failed")),
        ):
            with self.assertRaisesRegex(RuntimeError, "transform failed"):
                job_analyzer.analyze_jobs()

        self.assertEqual(output_path.read_bytes(), original)

    def test_empty_analyzer_input_keeps_existing_output_under_current_no_op_semantics(self):
        input_path = self.root / "job_details.csv"
        output_path = self.root / "job_analysis.csv"
        input_path.write_text(
            "Title,Company,Location,Easy Apply,Link,Description\n",
            encoding="utf-8",
        )
        original = b"previous analysis remains\n"
        output_path.write_bytes(original)

        with (
            patch.object(job_analyzer, "INPUT_FILE", str(input_path)),
            patch.object(job_analyzer, "OUTPUT_FILE", str(output_path)),
        ):
            job_analyzer.analyze_jobs()

        self.assertEqual(output_path.read_bytes(), original)

    def test_extraction_output_csv_and_json_replace_from_isolated_paths(self):
        csv_path = self.root / "details.csv"
        diagnostics_path = self.root / "diagnostics.json"
        with (
            patch.object(job_details, "OUTPUT_FILE", str(csv_path)),
            patch.object(job_details, "DIAGNOSTICS_FILE", str(diagnostics_path)),
        ):
            job_details._write_extraction_outputs(
                [{
                    "Title": "Backend Engineer",
                    "Company": "Example Corp",
                    "Location": "Bengaluru",
                    "Experience": "",
                    "Easy Apply": "Yes",
                    "Skills": "",
                    "Link": "https://www.linkedin.com/jobs/view/1234567890/",
                    "Description": "First line\nsecond line",
                }],
                [{"job_url": "https://www.linkedin.com/jobs/view/1234567890/"}],
            )

        with csv_path.open(encoding="utf-8", newline="") as file:
            rows = list(csv.DictReader(file))
        self.assertEqual(rows[0]["Description"], "First line second line")
        self.assertEqual(
            json.loads(diagnostics_path.read_text(encoding="utf-8")),
            [{"job_url": "https://www.linkedin.com/jobs/view/1234567890/"}],
        )

    def test_extraction_input_parse_failure_preserves_prior_outputs_before_cdp(self):
        input_path = self.root / "jobs.csv"
        csv_path = self.root / "details.csv"
        diagnostics_path = self.root / "diagnostics.json"
        input_path.write_bytes(b"Title,Link\n\xff,invalid utf-8\n")
        old_csv = b"previous valid details\n"
        old_diagnostics = "previous diagnostics"
        csv_path.write_bytes(old_csv)
        diagnostics_path.write_text(old_diagnostics, encoding="utf-8")

        previous_cwd = Path.cwd()
        try:
            import os
            os.chdir(self.root)
            with (
                patch.object(job_details, "INPUT_FILE", str(input_path)),
                patch.object(job_details, "OUTPUT_FILE", str(csv_path)),
                patch.object(job_details, "DIAGNOSTICS_FILE", str(diagnostics_path)),
                patch.object(job_details, "sync_playwright") as playwright,
            ):
                with self.assertRaises(UnicodeDecodeError):
                    job_details.extract_job_details()

            playwright.assert_not_called()
        finally:
            os.chdir(previous_cwd)

        self.assertEqual(csv_path.read_bytes(), old_csv)
        self.assertEqual(diagnostics_path.read_text(encoding="utf-8"), old_diagnostics)

    def test_extraction_csv_serialization_failure_preserves_previous_csv(self):
        csv_path = self.root / "details.csv"
        diagnostics_path = self.root / "diagnostics.json"
        original_csv = b"old details\n"
        csv_path.write_bytes(original_csv)
        diagnostics_path.write_text("old diagnostics", encoding="utf-8")

        class FailingWriter:
            def __init__(self, file, **_kwargs):
                self.file = file

            def writeheader(self):
                self.file.write("partial header\n")

            def writerows(self, _rows):
                raise OSError("simulated details serialization failure")

        with (
            patch.object(job_details, "OUTPUT_FILE", str(csv_path)),
            patch.object(job_details, "DIAGNOSTICS_FILE", str(diagnostics_path)),
            patch.object(job_details.csv, "DictWriter", FailingWriter),
        ):
            with self.assertRaisesRegex(OSError, "simulated details serialization failure"):
                job_details._write_extraction_outputs([{"Description": "value"}], [])

        self.assertEqual(csv_path.read_bytes(), original_csv)
        self.assertEqual(diagnostics_path.read_text(encoding="utf-8"), "old diagnostics")
        self.assertEqual(self._temporary_files(csv_path), [])

    def test_diagnostics_failure_preserves_its_prior_file_but_outputs_are_not_a_pair_transaction(self):
        csv_path = self.root / "details.csv"
        diagnostics_path = self.root / "diagnostics.json"
        diagnostics_path.write_text("previous diagnostics", encoding="utf-8")

        def fail_after_partial_json(_data, file, *_args, **_kwargs):
            file.write("partial json")
            raise OSError("simulated diagnostics serialization failure")

        with (
            patch.object(job_details, "OUTPUT_FILE", str(csv_path)),
            patch.object(job_details, "DIAGNOSTICS_FILE", str(diagnostics_path)),
            patch.object(job_details.json, "dump", side_effect=fail_after_partial_json),
        ):
            with self.assertRaisesRegex(OSError, "simulated diagnostics serialization failure"):
                job_details._write_extraction_outputs([{
                    "Title": "Backend Engineer",
                    "Company": "Example Corp",
                    "Location": "Bengaluru",
                    "Experience": "",
                    "Easy Apply": "Yes",
                    "Skills": "",
                    "Link": "https://www.linkedin.com/jobs/view/1234567890/",
                    "Description": "Example description",
                }], [{"diagnostic": "new"}])

        self.assertTrue(csv_path.exists())
        self.assertEqual(diagnostics_path.read_text(encoding="utf-8"), "previous diagnostics")
        self.assertEqual(self._temporary_files(diagnostics_path), [])

    def test_diagnostics_replace_failure_after_csv_replace_preserves_old_diagnostics(self):
        csv_path = self.root / "details.csv"
        diagnostics_path = self.root / "diagnostics.json"
        diagnostics_path.write_text("previous diagnostics", encoding="utf-8")
        original_replace = output_files.os.replace

        def fail_diagnostics_replace(source, destination):
            if os.path.abspath(destination) == os.path.abspath(diagnostics_path):
                raise OSError("diagnostics replace denied")
            return original_replace(source, destination)

        with (
            patch.object(job_details, "OUTPUT_FILE", str(csv_path)),
            patch.object(job_details, "DIAGNOSTICS_FILE", str(diagnostics_path)),
            patch.object(output_files.os, "replace", side_effect=fail_diagnostics_replace),
        ):
            with self.assertRaisesRegex(OSError, "diagnostics replace denied"):
                job_details._write_extraction_outputs([{
                    "Title": "Backend Engineer",
                    "Company": "Example Corp",
                    "Location": "Bengaluru",
                    "Experience": "",
                    "Easy Apply": "Yes",
                    "Skills": "",
                    "Link": "https://www.linkedin.com/jobs/view/1234567890/",
                    "Description": "Example description",
                }], [{"diagnostic": "new"}])

        self.assertTrue(csv_path.exists())
        self.assertEqual(diagnostics_path.read_text(encoding="utf-8"), "previous diagnostics")
        self.assertEqual(self._temporary_files(diagnostics_path), [])


if __name__ == "__main__":
    unittest.main()
