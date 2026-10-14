"""Offline regression tests for the standalone scraper's output boundary."""

import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import job_scraper


class FakeAnchor:
    def __init__(self, href="https://www.linkedin.com/jobs/view/101/", text=None,
                 failure=None):
        self.href = href
        self.text = text or "Backend Engineer\nExample\nBengaluru"
        self.failure = failure

    def is_visible(self):
        if self.failure:
            raise self.failure
        return True

    def get_attribute(self, name):
        return self.href if name == "href" else None

    def inner_text(self):
        return self.text


class FakeLocator:
    def __init__(self, anchors):
        self.anchors = anchors

    def count(self):
        return len(self.anchors)

    def nth(self, index):
        return self.anchors[index]


class FakePage:
    url = "https://www.linkedin.com/jobs/search/"

    def __init__(self, anchors=(), locator_error=None):
        self.anchors = anchors
        self.locator_error = locator_error

    def title(self):
        return "Synthetic Jobs Page"

    def locator(self, selector):
        if self.locator_error:
            raise self.locator_error
        return FakeLocator(self.anchors)


class FakeBrowser:
    def __init__(self, page):
        self.contexts = [mock.Mock(pages=[page])]

    def close(self):
        pass


class FakePlaywright:
    def __init__(self, page, connect_error=None):
        self.chromium = mock.Mock()
        if connect_error:
            self.chromium.connect_over_cdp.side_effect = connect_error
        else:
            self.chromium.connect_over_cdp.return_value = FakeBrowser(page)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False


class StandaloneScraperPublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(
            dir=Path(__file__).resolve().parents[1]
        )
        self.addCleanup(self.temp_dir.cleanup)
        self.output = Path(self.temp_dir.name) / "jobs.csv"
        self.original = b"existing jobs must remain unchanged\r\n"
        self.output.write_bytes(self.original)

    def run_scraper(self, page, connect_error=None):
        playwright = FakePlaywright(page, connect_error=connect_error)
        with (
            mock.patch.object(job_scraper, "sync_playwright", return_value=playwright),
            mock.patch.object(job_scraper, "extract_company", return_value="Example"),
            mock.patch.object(job_scraper, "extract_location", return_value="Bengaluru"),
            mock.patch.object(job_scraper, "is_target_location", return_value=True),
            mock.patch.object(job_scraper, "make_direct_job_url", return_value="https://example.invalid/101"),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            return job_scraper.scrape_jobs(output_file=str(self.output))

    def assert_output_preserved_without_temp_files(self):
        self.assertEqual(self.output.read_bytes(), self.original)
        self.assertEqual(list(Path(self.temp_dir.name).iterdir()), [self.output])

    def test_empty_unverified_result_remains_unknown_and_preserves_output(self):
        self.assertEqual(self.run_scraper(FakePage()), [])
        self.assert_output_preserved_without_temp_files()

    def test_populated_unverified_result_remains_unknown_and_preserves_output(self):
        rows = self.run_scraper(FakePage(anchors=(FakeAnchor(),)))
        self.assertEqual(len(rows), 1)
        self.assert_output_preserved_without_temp_files()

    def test_candidate_processing_failure_is_incomplete_and_preserves_output(self):
        rows = self.run_scraper(
            FakePage(anchors=(
                FakeAnchor(),
                FakeAnchor(href="https://www.linkedin.com/jobs/view/102/",
                           failure=RuntimeError("synthetic candidate failure")),
            ))
        )
        self.assertEqual(len(rows), 1)
        self.assert_output_preserved_without_temp_files()

    def test_exception_before_publication_preserves_existing_output(self):
        with self.assertRaisesRegex(RuntimeError, "synthetic page failure"):
            self.run_scraper(
                FakePage(locator_error=RuntimeError("synthetic page failure"))
            )
        self.assert_output_preserved_without_temp_files()

    def test_connection_failure_is_failed_and_preserves_output(self):
        self.assertEqual(
            self.run_scraper(FakePage(), connect_error=RuntimeError("synthetic connection failure")),
            [],
        )
        self.assert_output_preserved_without_temp_files()

    def test_output_write_is_never_attempted(self):
        with mock.patch("builtins.open", side_effect=AssertionError("unexpected file open")) as open_mock:
            rows = self.run_scraper(FakePage(anchors=(FakeAnchor(),)))
        self.assertEqual(len(rows), 1)
        open_mock.assert_not_called()
        self.assert_output_preserved_without_temp_files()

    def test_summary_says_no_csv_was_written_and_path_was_unchanged(self):
        for destination_exists in (True, False):
            with self.subTest(destination_exists=destination_exists):
                if not destination_exists:
                    self.output.unlink()

                playwright = FakePlaywright(FakePage())
                output = io.StringIO()
                with (
                    mock.patch.object(job_scraper, "sync_playwright", return_value=playwright),
                    contextlib.redirect_stdout(output),
                ):
                    rows = job_scraper.scrape_jobs(output_file=str(self.output))

                self.assertEqual(rows, [])
                self.assertIn(
                    "No CSV was written; output path was left unchanged:",
                    output.getvalue(),
                )
                self.assertNotIn("existing output was preserved", output.getvalue())
                if destination_exists:
                    self.assertEqual(self.output.read_bytes(), self.original)
                else:
                    self.assertFalse(self.output.exists())

        self.assertEqual(list(Path(self.temp_dir.name).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
