import contextlib
import csv
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import job_search


class FakeAnchor:
    def __init__(self, href):
        self.href = href

    def get_attribute(self, name):
        return self.href if name == "href" else None


class FakeLocator:
    def __init__(self, values=(), error=None):
        self.values = list(values)
        self.error = error

    def count(self):
        if self.error:
            raise self.error
        return len(self.values)

    def nth(self, index):
        if self.error:
            raise self.error
        return self.values[index]

    def inner_text(self):
        if self.error:
            raise self.error
        return "Bengaluru · India"


class FakeMouse:
    def __init__(self, fail=False):
        self.fail = fail

    def wheel(self, *_args):
        if self.fail:
            raise RuntimeError("scroll failed")


class FakePage:
    def __init__(self, links=(), fail_search=(), fail_jobs=(), scroll_fails=False,
                 parser_error=False):
        self.links = tuple(links)
        self.fail_search = set(fail_search)
        self.fail_jobs = set(fail_jobs)
        self.parser_error = parser_error
        self.mouse = FakeMouse(scroll_fails)
        self.url = "about:blank"

    def goto(self, url, **_kwargs):
        if "/jobs/search/" in url:
            for keyword in self.fail_search:
                if f"keywords={keyword}" in url:
                    raise RuntimeError("search navigation failed")
        if "/jobs/view/" in url:
            for job_id in self.fail_jobs:
                if f"/jobs/view/{job_id}/" in url:
                    raise RuntimeError("candidate navigation failed")
        self.url = url

    def wait_for_timeout(self, *_args):
        return None

    def title(self):
        return "LinkedIn"

    def screenshot(self, **_kwargs):
        return None

    def is_closed(self):
        return False

    def locator(self, selector):
        if selector == "body":
            return FakeLocator(["Bengaluru · India"])
        if self.parser_error:
            return FakeLocator(error=RuntimeError("selector parsing failed"))
        if "/jobs/search/" in self.url:
            return FakeLocator(
                [FakeAnchor(f"/jobs/view/{job_id}/") for job_id in self.links]
            )
        return FakeLocator()


class FakeContext:
    def __init__(self, page):
        self.pages = [page]

    def new_page(self):
        page = FakePage()
        self.pages.append(page)
        return page


class FakeBrowser:
    def __init__(self, page):
        self.contexts = [FakeContext(page)]

    def is_connected(self):
        return True


def playwright_mock(page=None, connect_error=None, no_context=False):
    page = page or FakePage()
    browser = FakeBrowser(page)
    playwright = mock.Mock()
    if no_context:
        browser.contexts = []
    playwright.chromium.connect_over_cdp.return_value = browser
    if connect_error:
        playwright.chromium.connect_over_cdp.side_effect = connect_error
    manager = mock.MagicMock()
    manager.__enter__.return_value = playwright
    return manager


class CollectionRunTests(unittest.TestCase):
    def run_collector(self, page, keywords=("backend",), max_jobs=10,
                      connect_error=None, no_context=False,
                      easy_apply_filter=False, extracted_location="Bengaluru"):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "jobs.csv"
            original = b"preserve this dataset\r\n"
            output.write_bytes(original)

            with (
                mock.patch.object(job_search, "OUTPUT_FILE", str(output)),
                mock.patch.object(job_search, "SEARCH_KEYWORDS", keywords),
                mock.patch.object(job_search, "TARGET_LOCATIONS", ("bengaluru",)),
                mock.patch.object(job_search, "MAX_JOBS", max_jobs),
                mock.patch.object(job_search, "EASY_APPLY_FILTER", easy_apply_filter),
                mock.patch.object(
                    job_search,
                    "sync_playwright",
                    return_value=playwright_mock(
                        page,
                        connect_error=connect_error,
                        no_context=no_context,
                    ),
                ),
                mock.patch.object(job_search, "extract_job_title", return_value="Backend Engineer"),
                mock.patch.object(job_search, "extract_company", return_value="Example"),
                mock.patch.object(job_search, "extract_location", return_value=extracted_location),
                mock.patch.object(job_search, "detect_easy_apply", return_value=False),
                mock.patch.object(job_search, "detect_actively_reviewing", return_value=False),
                mock.patch("builtins.input", return_value=""),
            ):
                with contextlib.redirect_stdout(io.StringIO()):
                    outcome = job_search._collect_search_jobs()

            self.assertEqual(output.read_bytes(), original)
            self.assertEqual(list(Path(directory).iterdir()), [output])
            return outcome

    def test_clean_navigation_and_parsing_remain_unknown(self):
        outcome = self.run_collector(FakePage(links=("101",)))
        self.assertEqual(outcome.status, job_search.CollectionStatus.UNKNOWN)
        self.assertEqual(len(outcome.jobs), 1)
        self.assertFalse(outcome.issues)

    def test_browser_connection_failure_is_failed(self):
        outcome = self.run_collector(
            FakePage(),
            connect_error=RuntimeError("not connected"),
        )
        self.assertEqual(outcome.status, job_search.CollectionStatus.FAILED)

    def test_missing_browser_context_is_failed(self):
        outcome = self.run_collector(FakePage(), no_context=True)
        self.assertEqual(outcome.status, job_search.CollectionStatus.FAILED)

    def test_zero_links_from_unrecognized_page_structure_remain_unknown(self):
        outcome = self.run_collector(FakePage())
        self.assertEqual(outcome.status, job_search.CollectionStatus.UNKNOWN)
        self.assertEqual(outcome.jobs, ())

    def test_search_navigation_failure_is_incomplete(self):
        outcome = self.run_collector(FakePage(fail_search=("backend",)))
        self.assertEqual(outcome.status, job_search.CollectionStatus.INCOMPLETE)
        self.assertTrue(any("Search navigation failed" in item for item in outcome.issues))

    def test_mixed_success_and_failed_search_does_not_publish_subset(self):
        outcome = self.run_collector(
            FakePage(links=("101",), fail_search=("failed",)),
            keywords=("failed", "working"),
        )
        self.assertEqual(outcome.status, job_search.CollectionStatus.INCOMPLETE)
        self.assertEqual(len(outcome.jobs), 1)

    def test_candidate_page_failure_is_incomplete(self):
        outcome = self.run_collector(FakePage(links=("101",), fail_jobs=("101",)))
        self.assertEqual(outcome.status, job_search.CollectionStatus.INCOMPLETE)
        self.assertTrue(any("Candidate-page processing failed" in item for item in outcome.issues))

    def test_scroll_failure_is_recorded(self):
        outcome = self.run_collector(FakePage(links=("101",), scroll_fails=True))
        self.assertEqual(outcome.status, job_search.CollectionStatus.INCOMPLETE)
        self.assertTrue(any("Scrolling failed" in item for item in outcome.issues))

    def test_result_parser_failure_is_recorded(self):
        outcome = self.run_collector(FakePage(parser_error=True))
        self.assertEqual(outcome.status, job_search.CollectionStatus.INCOMPLETE)
        self.assertTrue(any("selector" in item for item in outcome.issues))

    def test_configured_global_cap_is_reported_as_bounded_unknown(self):
        outcome = self.run_collector(FakePage(links=("101", "102")), max_jobs=1)
        self.assertEqual(outcome.status, job_search.CollectionStatus.UNKNOWN)
        self.assertTrue(outcome.bounded_by_limit)

    def test_duplicate_ids_are_deduplicated(self):
        page = FakePage(links=("101", "101"))
        page.url = "https://www.linkedin.com/jobs/search/"
        result = job_search.get_job_links(page, max_links=5)
        self.assertEqual(result.links, ("https://www.linkedin.com/jobs/view/101/",))

    def test_link_parser_reports_element_errors(self):
        page = FakePage()
        page.url = "https://www.linkedin.com/jobs/search/"
        page.parser_error = True
        result = job_search.get_job_links(page, max_links=5)
        self.assertEqual(result.links, ())
        self.assertTrue(result.errors)

    def test_per_search_cap_is_reported_as_bounded_sampling(self):
        page = FakePage(links=("1", "2", "3"))
        page.url = "https://www.linkedin.com/jobs/search/"
        result = job_search.get_job_links(page, max_links=3)
        self.assertEqual(len(result.links), 3)
        self.assertTrue(result.bounded_by_limit)

    def test_intended_closed_job_filter_is_not_a_processing_failure(self):
        page = FakePage(links=("101",))
        with mock.patch.object(job_search, "detect_closed", return_value=True):
            outcome = self.run_collector(page)
        self.assertEqual(outcome.status, job_search.CollectionStatus.UNKNOWN)
        self.assertFalse(outcome.issues)

    def test_intended_location_filter_is_not_a_processing_failure(self):
        outcome = self.run_collector(
            FakePage(links=("101",)),
            extracted_location="London",
        )
        self.assertEqual(outcome.status, job_search.CollectionStatus.UNKNOWN)
        self.assertFalse(outcome.jobs)
        self.assertFalse(outcome.issues)

    def test_intended_easy_apply_filter_is_not_a_processing_failure(self):
        outcome = self.run_collector(
            FakePage(links=("101",)),
            easy_apply_filter=True,
        )
        self.assertEqual(outcome.status, job_search.CollectionStatus.UNKNOWN)
        self.assertFalse(outcome.jobs)
        self.assertFalse(outcome.issues)


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.output = Path(self.temp_dir.name) / "jobs.csv"
        self.original = b"existing bytes\r\n"
        self.output.write_bytes(self.original)
        self.sample_row = {
            "Title": "Engineer",
            "Company": "Example",
            "Location": "Bengaluru",
            "Easy Apply": "No",
            "Actively Reviewing": "No",
            "Link": "https://www.linkedin.com/jobs/view/101/",
        }

    def test_atomic_writer_preserves_six_column_schema(self):
        job_search._write_jobs_csv_atomically((self.sample_row,), self.output)
        with self.output.open(newline="", encoding="utf-8") as file:
            rows = list(csv.DictReader(file))
        self.assertEqual(tuple(rows[0]), job_search.JOB_CSV_FIELDS)
        self.assertEqual(rows[0]["Title"], "Engineer")

    def test_nonpublishable_statuses_preserve_existing_bytes(self):
        for status in (
            job_search.CollectionStatus.UNKNOWN,
            job_search.CollectionStatus.INCOMPLETE,
            job_search.CollectionStatus.FAILED,
        ):
            with self.subTest(status=status):
                outcome = job_search.CollectionOutcome(status, ())
                self.assertFalse(job_search.publish_collection(outcome, self.output))
                self.assertEqual(self.output.read_bytes(), self.original)

    def test_serialization_failure_preserves_destination_and_cleans_temp(self):
        writer = mock.Mock()
        writer.writeheader.return_value = None
        writer.writerows.side_effect = OSError("serialization failed")
        with mock.patch.object(job_search.csv, "DictWriter", return_value=writer):
            with self.assertRaises(OSError):
                job_search._write_jobs_csv_atomically((self.sample_row,), self.output)
        self.assertEqual(self.output.read_bytes(), self.original)
        self.assertEqual(list(Path(self.temp_dir.name).iterdir()), [self.output])

    def test_flush_failure_preserves_destination_and_cleans_temp(self):
        original_factory = job_search.tempfile.NamedTemporaryFile

        class FlushFailingFile:
            def __init__(self, *args, **kwargs):
                self.file = original_factory(*args, **kwargs)

            def __enter__(self):
                self.file.__enter__()
                return self

            def __exit__(self, *args):
                return self.file.__exit__(*args)

            def __getattr__(self, name):
                return getattr(self.file, name)

            def flush(self):
                raise OSError("flush failed")

        with mock.patch.object(
            job_search.tempfile,
            "NamedTemporaryFile",
            side_effect=lambda *args, **kwargs: FlushFailingFile(*args, **kwargs),
        ):
            with self.assertRaises(OSError):
                job_search._write_jobs_csv_atomically((self.sample_row,), self.output)
        self.assertEqual(self.output.read_bytes(), self.original)
        self.assertEqual(list(Path(self.temp_dir.name).iterdir()), [self.output])

    def test_replace_failure_preserves_destination_and_cleans_temp(self):
        with mock.patch.object(job_search.os, "replace", side_effect=OSError("replace failed")):
            with self.assertRaises(OSError):
                job_search._write_jobs_csv_atomically((self.sample_row,), self.output)
        self.assertEqual(self.output.read_bytes(), self.original)
        self.assertEqual(list(Path(self.temp_dir.name).iterdir()), [self.output])


if __name__ == "__main__":
    unittest.main()
