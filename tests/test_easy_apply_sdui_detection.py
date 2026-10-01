import unittest

import easy_apply


LEGACY_SELECTOR = ".jobs-easy-apply-modal"


class FakeElement:
    def __init__(self, *, visible=True, attributes=None, text=""):
        self.visible = visible
        self.attributes = attributes or {}
        self.text = text

    def is_visible(self):
        return self.visible

    def get_attribute(self, name):
        return self.attributes.get(name)

    def inner_text(self):
        return self.text


class FakeLocator:
    def __init__(self, elements=()):
        self.elements = list(elements)

    def count(self):
        return len(self.elements)

    def nth(self, index):
        return self.elements[index]


class FakePage:
    def __init__(self, selector_map=None, url="https://www.linkedin.com/jobs/view/123/"):
        self.selector_map = selector_map or {}
        self.url = url

    def locator(self, selector):
        return FakeLocator(self.selector_map.get(selector, ()))


class EasyApplySduiDetectionTests(unittest.TestCase):
    def test_legacy_modal_selector_keeps_existing_detection(self):
        page = FakePage({
            LEGACY_SELECTOR: [FakeElement(
                attributes={"class": "jobs-easy-apply-modal"},
                text="Contact info",
            )]
        })

        result = easy_apply._detect_easy_apply_container(page)

        self.assertTrue(result["detected"])
        self.assertEqual(result["source"], "legacy")

    def test_visible_sdui_easy_apply_screen_is_detected(self):
        page = FakePage({
            easy_apply.EASY_APPLY_SDUI_SELECTOR: [FakeElement(
                attributes={"class": "auygt0 auymt3"},
                text="Contact info Next",
            )]
        })

        result = easy_apply._detect_easy_apply_container(page)

        self.assertTrue(result["detected"])
        self.assertEqual(result["source"], "sdui")
        self.assertEqual(
            result["sdui_diagnostics"]["selector"],
            'div[data-sdui-screen="com.linkedin.sdui.flagshipnav.jobs.easyapply.EasyApply"]',
        )
        self.assertEqual(result["sdui_diagnostics"]["match_count"], 1)
        self.assertEqual(result["sdui_diagnostics"]["visible_match_count"], 1)
        self.assertEqual(
            result["sdui_diagnostics"]["candidates"][0]["class"],
            "auygt0 auymt3",
        )
        self.assertIn(
            "Contact info",
            result["sdui_diagnostics"]["candidates"][0]["text_preview"],
        )

    def test_invisible_sdui_screen_is_not_detected(self):
        page = FakePage({
            easy_apply.EASY_APPLY_SDUI_SELECTOR: [FakeElement(
                visible=False,
                attributes={"class": "auygt0 auymt3"},
                text="Contact info",
            )]
        })

        result = easy_apply._detect_easy_apply_container(page)

        self.assertFalse(result["detected"])
        self.assertEqual(result["sdui_diagnostics"]["match_count"], 1)
        self.assertEqual(result["sdui_diagnostics"]["visible_match_count"], 0)

    def test_easy_apply_button_alone_is_not_an_application_container(self):
        page = FakePage({
            'button[aria-label="Easy Apply to this job"]': [FakeElement(
                attributes={"aria-label": "Easy Apply to this job"},
                text="Easy Apply",
            )]
        })

        result = easy_apply._detect_easy_apply_container(page)

        self.assertFalse(result["detected"])

    def test_url_change_alone_is_not_an_application_container(self):
        page = FakePage(
            url=("https://www.linkedin.com/jobs/view/123/"
                 "?companyName=Example&trackingId=abc")
        )

        result = easy_apply._detect_easy_apply_container(page)

        self.assertFalse(result["detected"])


if __name__ == "__main__":
    unittest.main()
