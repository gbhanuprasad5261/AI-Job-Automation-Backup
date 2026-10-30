import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import application_tracker
import easy_apply


class AtomicStatusWriteTests(unittest.TestCase):
    TRACKER_FIELDS = [
        "Title", "Company", "Location", "Match Score", "Priority",
        "Easy Apply", "Application Status", "Applied Date", "Link", "Status",
    ]
    HISTORY_FIELDS = [
        "Title", "Company", "Location", "URL", "Status", "Applied Date",
    ]
    JOB = {
        "Title": "Backend Engineer",
        "Company": "Example Corp",
        "Location": "Bengaluru",
        "Match Score": "90%",
        "Priority": "HIGH",
        "Easy Apply": "No",
        "Link": "https://www.linkedin.com/jobs/view/1234567890/",
    }

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        root = Path(self.temp_dir.name)
        self.tracker_path = root / "tracker.csv"
        self.history_path = root / "history.csv"
        self._write_csv(self.tracker_path, self.TRACKER_FIELDS, [{
            **self.JOB,
            "Application Status": "NOT APPLIED",
            "Applied Date": "",
            "Status": "NOT APPLIED",
        }])
        self._write_csv(self.history_path, self.HISTORY_FIELDS, [])

    @staticmethod
    def _write_csv(path, fields, rows):
        with path.open("w", encoding="utf-8", newline="") as output:
            writer = csv.DictWriter(output, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

    @staticmethod
    def _read_csv(path):
        with path.open(encoding="utf-8", newline="") as source:
            reader = csv.DictReader(source)
            return reader.fieldnames, list(reader)

    def _temporary_files(self, path):
        return list(path.parent.glob(f".{path.name}.*.tmp"))

    def test_tracker_update_preserves_schema_and_updates_matching_row(self):
        with patch.object(easy_apply, "TRACKER_FILE", str(self.tracker_path)):
            self.assertTrue(
                easy_apply._write_tracker_application_status(self.JOB, "READY_FOR_REVIEW")
            )

        headers, rows = self._read_csv(self.tracker_path)
        self.assertEqual(headers, self.TRACKER_FIELDS)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["Title"], self.JOB["Title"])
        self.assertEqual(rows[0]["Status"], "READY_FOR_REVIEW")
        self.assertEqual(rows[0]["Application Status"], "READY_FOR_REVIEW")
        self.assertEqual(rows[0]["Applied Date"], "")
        self.assertEqual(self._temporary_files(self.tracker_path), [])

    def test_history_update_preserves_schema_and_row_data(self):
        row = {
            "Title": self.JOB["Title"],
            "Company": self.JOB["Company"],
            "Location": self.JOB["Location"],
            "URL": self.JOB["Link"],
            "Status": "APPLIED",
            "Applied Date": "2026-10-13",
        }
        with patch.object(easy_apply, "APPLICATION_HISTORY_FILE", str(self.history_path)):
            self.assertTrue(
                easy_apply._write_application_history([row], self.HISTORY_FIELDS)
            )

        headers, rows = self._read_csv(self.history_path)
        self.assertEqual(headers, self.HISTORY_FIELDS)
        self.assertEqual(rows, [row])
        self.assertEqual(self._temporary_files(self.history_path), [])

    def test_tracker_write_failure_preserves_existing_file_and_cleans_temp(self):
        original = self.tracker_path.read_bytes()

        class FailingWriter:
            def __init__(self, output, **_kwargs):
                self.output = output

            def writeheader(self):
                self.output.write("partial header\n")

            def writerows(self, _rows):
                raise OSError("simulated CSV write failure")

        with (
            patch.object(easy_apply, "TRACKER_FILE", str(self.tracker_path)),
            patch.object(easy_apply.csv, "DictWriter", FailingWriter),
        ):
            with self.assertRaisesRegex(OSError, "simulated CSV write failure"):
                easy_apply._write_tracker_application_status(self.JOB, "APPLIED")

        self.assertEqual(self.tracker_path.read_bytes(), original)
        self.assertEqual(self._temporary_files(self.tracker_path), [])

    def test_history_write_failure_preserves_existing_file_and_cleans_temp(self):
        original = self.history_path.read_bytes()

        class FailingWriter:
            def __init__(self, output, **_kwargs):
                self.output = output

            def writeheader(self):
                self.output.write("partial header\n")

            def writerows(self, _rows):
                raise OSError("simulated CSV write failure")

        with (
            patch.object(easy_apply, "APPLICATION_HISTORY_FILE", str(self.history_path)),
            patch.object(easy_apply.csv, "DictWriter", FailingWriter),
        ):
            self.assertFalse(
                easy_apply._write_application_history(
                    [{"Title": self.JOB["Title"]}], self.HISTORY_FIELDS
                )
            )

        self.assertEqual(self.history_path.read_bytes(), original)
        self.assertEqual(self._temporary_files(self.history_path), [])

    def test_replace_failure_preserves_tracker_destination_and_cleans_temp(self):
        original = self.tracker_path.read_bytes()
        with (
            patch.object(easy_apply, "TRACKER_FILE", str(self.tracker_path)),
            patch.object(easy_apply.os, "replace", side_effect=OSError("replace denied")),
        ):
            with self.assertRaisesRegex(OSError, "replace denied"):
                easy_apply._write_tracker_application_status(self.JOB, "APPLIED")

        self.assertEqual(self.tracker_path.read_bytes(), original)
        self.assertEqual(self._temporary_files(self.tracker_path), [])

    def test_replace_failure_preserves_history_destination_and_cleans_temp(self):
        original = self.history_path.read_bytes()
        with (
            patch.object(easy_apply, "APPLICATION_HISTORY_FILE", str(self.history_path)),
            patch.object(easy_apply.os, "replace", side_effect=OSError("replace denied")),
        ):
            self.assertFalse(
                easy_apply._write_application_history([], self.HISTORY_FIELDS)
            )

        self.assertEqual(self.history_path.read_bytes(), original)
        self.assertEqual(self._temporary_files(self.history_path), [])

    def test_application_tracker_replace_failure_preserves_file_and_cleans_temp(self):
        original = self.tracker_path.read_bytes()
        temp_path = Path(str(self.tracker_path) + ".tmp")
        with (
            patch.object(application_tracker, "OUTPUT_FILE", str(self.tracker_path)),
            patch.object(
                application_tracker.os,
                "replace",
                side_effect=OSError("synthetic tracker replacement failure"),
            ),
        ):
            with self.assertRaisesRegex(OSError, "synthetic tracker replacement failure"):
                application_tracker.save_tracker([dict(self.JOB)])

        self.assertEqual(self.tracker_path.read_bytes(), original)
        self.assertFalse(temp_path.exists())

    def test_application_tracker_temp_creation_failure_preserves_file(self):
        original = self.tracker_path.read_bytes()
        temp_path = Path(str(self.tracker_path) + ".tmp")
        with (
            patch.object(application_tracker, "OUTPUT_FILE", str(self.tracker_path)),
            patch(
                "builtins.open",
                side_effect=OSError("synthetic temp creation failure"),
            ) as open_file,
        ):
            with self.assertRaisesRegex(OSError, "synthetic temp creation failure"):
                application_tracker.save_tracker([dict(self.JOB)])

        open_file.assert_called_once_with(
            str(temp_path), "w", newline="", encoding="utf-8"
        )
        self.assertEqual(self.tracker_path.read_bytes(), original)
        self.assertFalse(temp_path.exists())

    def test_application_tracker_write_failure_preserves_file_and_cleans_temp(self):
        original = self.tracker_path.read_bytes()
        temp_path = Path(str(self.tracker_path) + ".tmp")

        class FailingWriter:
            def __init__(self, output, **_kwargs):
                self.output = output

            def writeheader(self):
                self.output.write("partial header\n")

            def writerow(self, _row):
                raise OSError("synthetic tracker serialization failure")

        with (
            patch.object(application_tracker, "OUTPUT_FILE", str(self.tracker_path)),
            patch.object(application_tracker.csv, "DictWriter", FailingWriter),
        ):
            with self.assertRaisesRegex(OSError, "synthetic tracker serialization failure"):
                application_tracker.save_tracker([dict(self.JOB)])

        self.assertEqual(self.tracker_path.read_bytes(), original)
        self.assertFalse(temp_path.exists())


if __name__ == "__main__":
    unittest.main()
