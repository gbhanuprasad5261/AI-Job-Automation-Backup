import unittest

import external_app


class FakeElement:
    def is_visible(self):
        return True


class FakeLocator:
    def __init__(self, *, text="", elements=()):
        self.text = text
        self.elements = list(elements)

    def inner_text(self, *args, **kwargs):
        return self.text

    def count(self):
        return len(self.elements)

    def nth(self, index):
        return self.elements[index]


class FakePage:
    def __init__(self, url, body, visible_input_count=0, child_frames=()):
        self.url = url
        self.body = body
        self.main_frame = object()
        self.frames = [self.main_frame, *child_frames]
        self.visible_inputs = [FakeElement() for _ in range(visible_input_count)]

    def locator(self, selector):
        if selector == "body":
            return FakeLocator(text=self.body)
        return FakeLocator(elements=self.visible_inputs)


class ExternalFormDetectionTests(unittest.TestCase):
    def test_generic_personal_information_alone_is_not_a_form(self):
        page = FakePage(
            "https://careers.example.test/jobs/123",
            "Personal information",
        )

        self.assertFalse(external_app._looks_like_application_form(page))

    def test_ford_landing_personal_information_and_apply_now_is_not_a_form(self):
        page = FakePage(
            "https://www.careers.ford.com/en/job/48560/101313842768",
            "Senior AI Software Engineer. Personal information. Apply Now. Apply Now.",
        )

        # This landing-page fixture has no visible form controls or child iframe.
        self.assertFalse(external_app._looks_like_application_form(page))

    def test_two_visible_structural_inputs_still_identify_a_form(self):
        page = FakePage(
            "https://careers.example.test/jobs/123",
            "Senior Engineer role",
            visible_input_count=2,
        )

        self.assertTrue(external_app._looks_like_application_form(page))

    def test_known_ats_personal_information_signal_remains_supported(self):
        page = FakePage(
            "https://boards.greenhouse.io/example/jobs/123",
            "Personal information",
        )

        self.assertTrue(external_app._looks_like_application_form(page))

    def test_strong_application_phrase_remains_supported(self):
        page = FakePage(
            "https://careers.example.test/jobs/123",
            "Complete your application",
        )

        self.assertTrue(external_app._looks_like_application_form(page))

    def test_application_phrase_in_child_iframe_remains_supported(self):
        class FakeFrame:
            def locator(self, selector):
                return FakeLocator(text="Personal information")

        page = FakePage(
            "https://careers.example.test/jobs/123",
            "Senior Engineer role",
            child_frames=(FakeFrame(),),
        )

        self.assertTrue(external_app._looks_like_application_form(page))


if __name__ == "__main__":
    unittest.main()
