import unittest

import job_details


JOB_ID = "1234567890"
JOB_URL = f"https://www.linkedin.com/jobs/view/{JOB_ID}/"
JOB_ROOT_SELECTOR = f'div[id="JobDetails_AboutTheJob_{JOB_ID}"]'
EXPANDABLE_BOX_SELECTOR = '[data-testid="expandable-text-box"]'


class _FakeLocator:
    def __init__(self, page, kind):
        self.page = page
        self.kind = kind

    @property
    def first(self):
        return self

    def count(self):
        state = self.page.state
        if self.kind == "root":
            return int(state["root_exists"])
        if self.kind == "paragraphs":
            return state["paragraph_count"]
        if self.kind == "expandable_box":
            return state["expandable_box_count"]
        if self.kind == "article":
            return int(bool(state["article_text"]))
        return 0

    def locator(self, selector):
        if self.kind == "root" and selector == "p":
            return _FakeLocator(self.page, "paragraphs")
        if self.kind == "paragraphs" and selector == EXPANDABLE_BOX_SELECTOR:
            return _FakeLocator(self.page, "expandable_box")
        raise AssertionError(f"Unexpected nested selector: {self.kind} -> {selector}")

    def inner_text(self):
        if self.kind == "paragraphs":
            return self.page.state["paragraph_text"]
        if self.kind == "article":
            return self.page.state["article_text"]
        if self.kind == "body":
            return self.page.state["body_text"]
        return ""

    def evaluate(self, script):
        self.page.evaluate_scripts.append(script)
        return {
            "text": self.page.state["extracted_text"],
            "ui_tail_excluded": self.page.state["ui_tail_excluded"],
        }

    def click(self):
        self.page.click_count += 1
        raise AssertionError("Description extraction must never click controls")


class _FakePage:
    def __init__(self, *, root_exists=True, **state_overrides):
        self.url = JOB_URL
        self.state = {
            "root_exists": root_exists,
            "paragraph_count": 0,
            "expandable_box_count": 0,
            "paragraph_text": "",
            "extracted_text": "",
            "ui_tail_excluded": False,
            "body_text": "",
            "article_text": "",
            **state_overrides,
        }
        self.wait_calls = []
        self.wait_callback = None
        self.evaluate_scripts = []
        self.click_count = 0

    def locator(self, selector):
        if selector == JOB_ROOT_SELECTOR:
            return _FakeLocator(self, "root")
        if selector == "div[data-sdui-component=\"com.linkedin.sdui.generated.jobseeker.dsl.impl.aboutTheJob\"]":
            return _FakeLocator(self, "generic_sdui")
        if selector == "article":
            return _FakeLocator(self, "article")
        if selector == "body":
            return _FakeLocator(self, "body")
        return _FakeLocator(self, "other")

    def wait_for_function(self, expression, *, arg, timeout):
        self.wait_calls.append({"expression": expression, "arg": arg, "timeout": timeout})
        if self.wait_callback is None:
            raise TimeoutError("bounded SDUI wait expired")
        self.wait_callback(self.state)


class JobDetailsExtractionTests(unittest.TestCase):
    def test_populated_description_extracts_immediately_without_wait(self):
        description = "A meaningful description with responsibilities and qualifications."
        page = _FakePage(
            paragraph_count=1,
            expandable_box_count=1,
            extracted_text=description,
        )
        diagnostics = {}

        result = job_details.extract_description(page, diagnostics)

        self.assertEqual(result, description)
        self.assertEqual(page.wait_calls, [])
        self.assertEqual(diagnostics["sdui_wait_status"], "available_immediately")
        self.assertEqual(diagnostics["winner"],
                         JOB_ROOT_SELECTOR + " > p > " + EXPANDABLE_BOX_SELECTOR)

    def test_empty_root_populated_within_bound_is_retried(self):
        description = "Responsibilities and qualifications become available after render."
        page = _FakePage()

        def populate(state):
            state.update({
                "paragraph_count": 1,
                "expandable_box_count": 1,
                "extracted_text": description,
                "ui_tail_excluded": True,
            })

        page.wait_callback = populate
        diagnostics = {}

        result = job_details.extract_description(page, diagnostics)

        self.assertEqual(result, description)
        self.assertEqual(len(page.wait_calls), 1)
        self.assertEqual(page.wait_calls[0]["arg"], JOB_ROOT_SELECTOR)
        self.assertEqual(
            page.wait_calls[0]["timeout"],
            job_details.SDUI_DESCRIPTION_WAIT_MS,
        )
        self.assertEqual(diagnostics["sdui_wait_status"], "appeared_after_wait")
        candidate = diagnostics["candidates"][0]
        self.assertTrue(candidate["first_match_has_nonempty_text"])
        self.assertEqual(candidate["text_length"], len(description))

    def test_empty_root_after_bounded_wait_stays_blank(self):
        page = _FakePage(body_text="Unrelated page footer")
        diagnostics = {}

        result = job_details.extract_description(page, diagnostics)

        self.assertEqual(result, "")
        self.assertEqual(len(page.wait_calls), 1)
        self.assertEqual(diagnostics["sdui_wait_status"], "wait_expired_empty")
        self.assertFalse(diagnostics["body_fallback_reached"])

    def test_missing_job_specific_root_keeps_existing_body_fallback(self):
        body_text = "About the job\nExisting legacy description content."
        page = _FakePage(root_exists=False, body_text=body_text)
        diagnostics = {}

        result = job_details.extract_description(page, diagnostics)

        self.assertEqual(result, body_text)
        self.assertEqual(page.wait_calls, [])
        self.assertTrue(diagnostics["body_fallback_reached"])
        self.assertIsNone(diagnostics.get("sdui_wait_status"))

    def test_extraction_never_clicks_expandable_button(self):
        page = _FakePage(
            paragraph_count=1,
            expandable_box_count=1,
            extracted_text="Description without clicking the expandable control.",
            ui_tail_excluded=True,
        )

        job_details.extract_description(page)

        self.assertEqual(page.click_count, 0)
        self.assertEqual(len(page.evaluate_scripts), 1)
        self.assertIn("button.remove()", page.evaluate_scripts[0])
        self.assertNotIn(".click(", page.evaluate_scripts[0])

    def test_ui_tail_exclusion_is_preserved(self):
        description = "The extracted role description."
        page = _FakePage(
            paragraph_count=1,
            expandable_box_count=1,
            extracted_text=description,
            ui_tail_excluded=True,
        )
        diagnostics = {}

        result = job_details.extract_description(page, diagnostics)

        self.assertEqual(result, description)
        self.assertTrue(diagnostics["candidates"][0]["ui_tail_excluded"])
        self.assertIn("before expandable-text-button tail", diagnostics["winner"])

    def test_existing_legacy_text_avoids_unnecessary_sdui_wait(self):
        legacy_text = "Legacy article description already available."
        page = _FakePage(article_text=legacy_text)
        diagnostics = {}

        result = job_details.extract_description(page, diagnostics)

        self.assertEqual(result, legacy_text)
        self.assertEqual(page.wait_calls, [])
        self.assertEqual(diagnostics["sdui_wait_status"],
                         "fallback_available_without_wait")


if __name__ == "__main__":
    unittest.main()
