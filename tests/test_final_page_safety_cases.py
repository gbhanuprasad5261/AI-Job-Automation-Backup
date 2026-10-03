import contextlib
import io
import unittest
from unittest.mock import patch

import application_form
import config


class FakeBody:
    def __init__(self, text):
        self.text = text

    def inner_text(self, **kwargs):
        return self.text


class FakePage:
    def __init__(self, text):
        self.body = FakeBody(text)
        self.buttons = []

    def locator(self, selector):
        if selector == "body":
            return self.body
        if selector == "button":
            return FakeLocator(self.buttons)
        return FakeLocator([])


class FakeLocator:
    def __init__(self, items):
        self.items = list(items)

    def count(self):
        return len(self.items)

    def nth(self, index):
        return self.items[index]


class FakeContainer:
    def __init__(self, text):
        self.text = text

    def inner_text(self, *args, **kwargs):
        return self.text


class FakeControl:
    def __init__(self, text, visible=True, enabled=True):
        self.text = text
        self.visible = visible
        self.enabled = enabled
        self.click_count = 0

    def is_visible(self):
        return self.visible

    def is_enabled(self):
        return self.enabled

    def inner_text(self):
        return self.text

    def get_attribute(self, name):
        return None

    def scroll_into_view_if_needed(self):
        return None

    def click(self, **kwargs):
        self.click_count += 1

    def evaluate(self, *args, **kwargs):
        self.click_count += 1


class FakeDomElement:
    def __init__(self, tag, text="", attributes=None, visible=True, enabled=True):
        self.tag = tag
        self.text = text
        self.attributes = attributes or {}
        self.visible = visible
        self.enabled = enabled

    def inner_text(self, *args, **kwargs):
        return self.text

    def get_attribute(self, name):
        return self.attributes.get(name)

    def is_visible(self):
        return self.visible

    def is_enabled(self):
        return self.enabled


class FakeReviewRoot:
    def __init__(self, *, headings=(), page_labels=(), progressbars=(), buttons=()):
        self.headings = list(headings)
        self.page_labels = list(page_labels)
        self.progressbars = list(progressbars)
        self.buttons = list(buttons)

    def locator(self, selector):
        if selector == "h1, h2, h3, h4, h5, h6, [role='heading']":
            return FakeLocator(self.headings)
        if selector == "p, span, div":
            return FakeLocator(self.page_labels)
        if selector == '[role="progressbar"]':
            return FakeLocator(self.progressbars)
        if selector == "button, [role='button']":
            return FakeLocator(self.buttons)
        return FakeLocator([])


class FinalPageSafetyCases(unittest.TestCase):
    def _run_inspector(self, page, container, submit_button, *, next_button=None):
        with (
            patch.object(application_form, "job_is_closed", return_value=False),
            patch.object(application_form, "prepare_current_page", return_value=0),
            patch.object(application_form, "get_application_container", return_value=container),
            patch.object(application_form, "find_submit_button", return_value=submit_button) as find_submit,
            patch.object(application_form, "find_next_button", return_value=next_button) as find_next,
        ):
            result = application_form.inspect_and_prepare_form(page)
        return result, find_submit, find_next

    def test_submit_only_without_review_evidence_fails_closed(self):
        """A Submit-only Contact info screen without a step marker is not certified."""
        text = "Contact info. Phone. Resume. Submit application."
        page = FakePage(text)
        container = FakeContainer(text)
        submit = FakeControl("Submit application")
        page.buttons = [submit]

        with patch.object(application_form, "get_application_container", return_value=container):
            self.assertIsNone(application_form.get_application_step(page))

        output = io.StringIO()
        with (
            patch.object(config, "AUTO_SUBMIT", False),
            contextlib.redirect_stdout(output),
        ):
            verifier_result = application_form.verify_final_review_page(page)
            result, find_submit, find_next = self._run_inspector(page, container, submit)

        self.assertFalse(verifier_result)
        self.assertEqual(result, "FAILED")
        self.assertFalse(config.AUTO_SUBMIT)
        self.assertTrue(submit.is_visible())
        self.assertTrue(submit.is_enabled())
        self.assertEqual(submit.click_count, 0)
        find_submit.assert_called_once_with(container)
        find_next.assert_not_called()

    def test_submit_plus_next_exposes_submit_first_ambiguity_without_click(self):
        """Current inspection chooses Submit before consulting a present Next."""
        text = "Contact info. Resume. Next. Submit application."
        page = FakePage(text)
        container = FakeContainer(text)
        submit = FakeControl("Submit application")
        next_button = FakeControl("Next")
        page.buttons = [submit, next_button]

        output = io.StringIO()
        with (
            patch.object(config, "AUTO_SUBMIT", False),
            contextlib.redirect_stdout(output),
        ):
            verifier_result = application_form.verify_final_review_page(page)
            result, find_submit, find_next = self._run_inspector(
                page, container, submit, next_button=next_button
            )

        self.assertFalse(verifier_result)
        self.assertEqual(result, "FAILED")
        self.assertFalse(config.AUTO_SUBMIT)
        self.assertTrue(submit.is_visible())
        self.assertTrue(submit.is_enabled())
        self.assertTrue(next_button.is_visible())
        self.assertTrue(next_button.is_enabled())
        find_submit.assert_called_once_with(container)
        find_next.assert_not_called()
        self.assertEqual(submit.click_count, 0)
        self.assertIn("Final application page detected.", output.getvalue())
        self.assertIn("Final review verification failed.", output.getvalue())

    def test_engineering_square_style_review_with_zero_answer_pairs_passes_structurally(self):
        text = (
            "4/4 pages. Review your application. Contact info. Resume. "
            "Work authorization. Submit application."
        )
        page = FakePage(text)
        submit = FakeControl("Submit application")
        page.buttons = [submit]
        root = FakeReviewRoot(
            headings=[FakeDomElement("h3", "Review your application")],
            page_labels=[FakeDomElement("p", "4/4 pages")],
            progressbars=[
                FakeDomElement(
                    "svg",
                    attributes={
                        "role": "progressbar",
                        "aria-valuemin": "0",
                        "aria-valuemax": "100",
                        "aria-valuenow": "100",
                    },
                )
            ],
            buttons=[submit],
        )

        with (
            patch.object(config, "AUTO_SUBMIT", False),
            patch.object(application_form, "get_application_container", return_value=root),
            patch.object(application_form, "find_submit_button", return_value=submit) as find_submit,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            verifier_result = application_form.verify_final_review_page(page)
            result = application_form.handle_final_submission(page)

        self.assertTrue(verifier_result)
        self.assertEqual(result, "READY_FOR_REVIEW")
        self.assertEqual(submit.click_count, 0)
        find_submit.assert_not_called()

    def test_terminal_page_counter_and_review_heading_are_sufficient(self):
        text = "4/4 pages. Review your application. Resume. Submit application."
        submit = FakeControl("Submit application")
        page = FakePage(text)
        root = FakeReviewRoot(
            headings=[FakeDomElement("h3", "Review your application")],
            page_labels=[FakeDomElement("p", "4/4 pages")],
            buttons=[submit],
        )
        with (
            patch.object(application_form, "get_application_container", return_value=root),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            result = application_form.verify_final_review_page(page)
        self.assertTrue(result)
        self.assertEqual(submit.click_count, 0)

    def test_terminal_aria_progressbar_and_review_heading_are_sufficient(self):
        text = "Review your application. Resume. Submit application."
        submit = FakeControl("Submit application")
        page = FakePage(text)
        root = FakeReviewRoot(
            headings=[FakeDomElement("h3", "Review your application")],
            progressbars=[
                FakeDomElement(
                    "svg",
                    attributes={
                        "role": "progressbar",
                        "aria-valuemin": "0",
                        "aria-valuemax": "100",
                        "aria-valuenow": "100",
                    },
                )
            ],
            buttons=[submit],
        )
        with (
            patch.object(application_form, "get_application_container", return_value=root),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            result = application_form.verify_final_review_page(page)
        self.assertTrue(result)
        self.assertEqual(submit.click_count, 0)

    def test_tcs_submit_only_screen_still_fails_with_zero_answer_pairs(self):
        text = "Contact info. Resume. Submit application."
        submit = FakeControl("Submit application")
        page = FakePage(text)
        root = FakeReviewRoot(buttons=[submit])
        with (
            patch.object(application_form, "get_application_container", return_value=root),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            result = application_form.verify_final_review_page(page)
        self.assertFalse(result)
        self.assertEqual(submit.click_count, 0)

    def test_generic_resume_application_and_matching_answer_without_review_fails(self):
        text = (
            "Contact info. Resume. Submit application. "
            "How many years of work experience do you have with .NET Core? 0."
        )
        submit = FakeControl("Submit application")
        page = FakePage(text)
        root = FakeReviewRoot(buttons=[submit])
        with (
            patch.object(application_form, "get_application_container", return_value=root),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            result = application_form.verify_final_review_page(page)
        self.assertFalse(result)
        self.assertEqual(submit.click_count, 0)

    def test_submit_without_review_or_progress_fails(self):
        text = "Application. Resume. Submit application."
        submit = FakeControl("Submit application")
        page = FakePage(text)
        root = FakeReviewRoot(buttons=[submit])
        with (
            patch.object(application_form, "get_application_container", return_value=root),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            result = application_form.verify_final_review_page(page)
        self.assertFalse(result)

    def test_review_terminal_progress_without_enabled_submit_fails(self):
        answer_text = (
            "How many years of work experience do you have with .NET Core? 0. "
        )
        for submit in (None, FakeControl("Submit application", enabled=False)):
            with self.subTest(submit=submit):
                text = (
                    "Review your application. 4/4 pages. Resume. "
                    + answer_text
                    + "Submit application."
                )
                page = FakePage(text)
                root = FakeReviewRoot(
                    headings=[FakeDomElement("h3", "Review your application")],
                    page_labels=[FakeDomElement("p", "4/4 pages")],
                    buttons=[submit] if submit is not None else [],
                )
                with (
                    patch.object(application_form, "get_application_container", return_value=root),
                    contextlib.redirect_stdout(io.StringIO()),
                ):
                    result = application_form.verify_final_review_page(page)
                self.assertFalse(result)
                if submit is not None:
                    self.assertEqual(submit.click_count, 0)

    def test_blocking_phrase_overrides_structural_review_evidence(self):
        text = (
            "Review your application. 4/4 pages. Submit application. "
            "Please correct the errors."
        )
        submit = FakeControl("Submit application")
        page = FakePage(text)
        root = FakeReviewRoot(
            headings=[FakeDomElement("h3", "Review your application")],
            page_labels=[FakeDomElement("p", "4/4 pages")],
            buttons=[submit],
        )
        with (
            patch.object(application_form, "get_application_container", return_value=root),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            result = application_form.verify_final_review_page(page)
        self.assertFalse(result)
        self.assertEqual(submit.click_count, 0)

    def test_review_with_nonterminal_quarter_progress_fails(self):
        text = (
            "Review your application. 1/4 pages. 25 percent complete. "
            "Submit application. "
            "How many years of work experience do you have with .NET Core? 0."
        )
        submit = FakeControl("Submit application")
        page = FakePage(text)
        root = FakeReviewRoot(
            headings=[FakeDomElement("h3", "Review your application")],
            page_labels=[FakeDomElement("p", "1/4 pages")],
            progressbars=[
                FakeDomElement(
                    "svg",
                    attributes={
                        "role": "progressbar",
                        "aria-valuemin": "0",
                        "aria-valuemax": "100",
                        "aria-valuenow": "25",
                    },
                )
            ],
            buttons=[submit],
        )
        with (
            patch.object(application_form, "get_application_container", return_value=root),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            result = application_form.verify_final_review_page(page)
        self.assertFalse(result)
        self.assertEqual(submit.click_count, 0)

    def test_ambiguous_non_review_screen_with_zero_answer_pairs_remains_false(self):
        text = "Contact info. Resume. Submit application."
        page = FakePage(text)
        root = FakeReviewRoot(buttons=[FakeControl("Submit application")])
        with (
            patch.object(application_form, "get_application_container", return_value=root),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            result = application_form.verify_final_review_page(page)
        self.assertFalse(result)

    def test_review_evidence_and_one_answer_pass_but_auto_submit_stays_off(self):
        text = (
            "Review your application. Resume. "
            "How many years of work experience do you have with .NET Core? 0. "
            "Submit application."
        )
        page = FakePage(text)
        submit = FakeControl("Submit application")
        page.buttons = [submit]

        with (
            patch.object(config, "AUTO_SUBMIT", False),
            patch.object(application_form, "find_submit_button") as find_submit,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            verifier_result = application_form.verify_final_review_page(page)
            result = application_form.handle_final_submission(page)

        self.assertTrue(verifier_result)
        self.assertEqual(page.locator("button").count(), 1)
        self.assertTrue(submit.is_visible())
        self.assertTrue(submit.is_enabled())
        self.assertEqual(result, "READY_FOR_REVIEW")
        self.assertFalse(config.AUTO_SUBMIT)
        self.assertEqual(submit.click_count, 0)
        find_submit.assert_not_called()

    def test_inspector_final_submit_path_stops_at_auto_submit_gate(self):
        text = (
            "Review your application. Resume. "
            "How many years of work experience do you have with .NET Core? 0. "
            "Submit application."
        )
        page = FakePage(text)
        container = FakeContainer(text)
        submit = FakeControl("Submit application")
        page.buttons = [submit]
        with contextlib.redirect_stdout(io.StringIO()):
            verifier_result = application_form.verify_final_review_page(page)

        with (
            patch.object(config, "AUTO_SUBMIT", False),
            patch.object(
                application_form,
                "verify_final_review_page",
                wraps=application_form.verify_final_review_page,
            ) as verifier,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            result, find_submit, find_next = self._run_inspector(page, container, submit)

        self.assertTrue(verifier_result)
        self.assertEqual(result, "READY_FOR_REVIEW")
        self.assertTrue(submit.is_visible())
        self.assertTrue(submit.is_enabled())
        verifier.assert_called_once_with(page)
        find_submit.assert_called_once_with(container)
        find_next.assert_not_called()
        self.assertFalse(config.AUTO_SUBMIT)
        self.assertEqual(submit.click_count, 0)


if __name__ == "__main__":
    unittest.main()
