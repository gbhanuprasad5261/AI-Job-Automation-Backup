import hashlib
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from search_page_evidence import (
    EvidenceCompletionStatus,
    EvidenceState,
    MAX_SCREENSHOT_BYTES,
    sanitize_url,
    validate_evidence_fixture,
)


def synthetic_fixture(state):
    loading_state = "settled_observed"
    card_count = 3
    empty_state_observed = False
    identity_state = "unverified"
    interstitial_observed = False
    interstitial_kind = "none"
    interstitial_evidence = "No interstitial observation in this synthetic fixture."

    if state == "LEGITIMATE_EMPTY":
        card_count = 0
        empty_state_observed = True
        identity_state = "matched"
    elif state == "LOADING_OR_INCOMPLETE":
        loading_state = "loading_observed"
        card_count = 0
    elif state == "AUTHENTICATION_OR_INTERSTITIAL":
        loading_state = "unknown"
        card_count = None
        interstitial_observed = True
        interstitial_kind = "synthetic authentication interstitial"
        interstitial_evidence = "Synthetic fixture records an interstitial observation."
    elif state == "UNKNOWN":
        loading_state = "unknown"
        card_count = None

    return {
        "schema_version": 1,
        "provenance": {
            "source": "synthetic_fixture",
            "source_reference": f"synthetic/{state.casefold()}.json",
        },
        "requested_scope": {
            "query": "backend engineer",
            "location": "Bengaluru",
        },
        "observations": {
            "sanitized_url": "https://example.invalid",
            "observed_state": state,
            "page_identity": {
                "state": identity_state,
                "evidence": "Synthetic page identity annotation.",
            },
            "dom_evidence": {
                "excerpt": f"Synthetic DOM evidence for {state}.",
                "sanitized": True,
            },
            "loading": {
                "state": loading_state,
                "evidence": f"Synthetic loading observation: {loading_state}.",
            },
            "visible_results": {
                "card_count": card_count,
                "displayed_count_text": "2,000+ results" if card_count else None,
                "empty_state_observed": empty_state_observed,
            },
            "pagination": {
                "batch_observations": [],
                "exhaustion_observation": "unknown",
                "cap_observation": "unknown",
            },
            "interstitial": {
                "observed": interstitial_observed,
                "kind": interstitial_kind,
                "evidence": interstitial_evidence,
            },
            "errors_observed": [],
        },
        "interpretation": {
            "notes": "Synthetic fixture label only; not a production completion claim.",
            "search_completion_claim": False,
        },
        "limitations": ["Synthetic evidence does not establish live page behavior."],
    }


class SearchPageEvidenceFixtureTests(unittest.TestCase):
    def validate(self, state, **kwargs):
        return validate_evidence_fixture(synthetic_fixture(state), **kwargs)

    def test_valid_synthetic_populated_results(self):
        result = self.validate("POPULATED_RESULTS")
        self.assertTrue(result.valid, result.issues)
        self.assertEqual(result.observed_state, EvidenceState.POPULATED_RESULTS)
        self.assertEqual(result.completion_status, EvidenceCompletionStatus.UNKNOWN)

    def test_valid_synthetic_legitimate_empty_label(self):
        result = self.validate("LEGITIMATE_EMPTY")
        self.assertTrue(result.valid, result.issues)
        self.assertEqual(result.observed_state, EvidenceState.LEGITIMATE_EMPTY)
        self.assertEqual(result.completion_status, EvidenceCompletionStatus.UNKNOWN)

    def test_valid_synthetic_loading_or_incomplete(self):
        result = self.validate("LOADING_OR_INCOMPLETE")
        self.assertTrue(result.valid, result.issues)
        self.assertEqual(result.observed_state, EvidenceState.LOADING_OR_INCOMPLETE)

    def test_valid_synthetic_authentication_interstitial(self):
        result = self.validate("AUTHENTICATION_OR_INTERSTITIAL")
        self.assertTrue(result.valid, result.issues)
        self.assertEqual(
            result.observed_state,
            EvidenceState.AUTHENTICATION_OR_INTERSTITIAL,
        )

    def test_unknown_fixture_remains_unknown(self):
        result = self.validate("UNKNOWN")
        self.assertTrue(result.valid, result.issues)
        self.assertEqual(result.observed_state, EvidenceState.UNKNOWN)
        self.assertEqual(result.completion_status, EvidenceCompletionStatus.UNKNOWN)

    def test_missing_required_fields_are_rejected_as_unknown(self):
        fixture = synthetic_fixture("POPULATED_RESULTS")
        del fixture["requested_scope"]["location"]
        result = validate_evidence_fixture(fixture)
        self.assertFalse(result.valid)
        self.assertEqual(result.observed_state, EvidenceState.UNKNOWN)
        self.assertTrue(any("location" in issue for issue in result.issues))

    def test_contradictory_state_evidence_is_rejected(self):
        fixture = synthetic_fixture("POPULATED_RESULTS")
        fixture["observations"]["visible_results"]["card_count"] = 0
        result = validate_evidence_fixture(fixture)
        self.assertFalse(result.valid)
        self.assertEqual(result.observed_state, EvidenceState.UNKNOWN)
        self.assertTrue(any("positive observed visible-card count" in issue for issue in result.issues))

    def test_populated_results_requires_positive_card_evidence(self):
        for card_count in (None, 0, "three", True):
            with self.subTest(card_count=card_count):
                fixture = synthetic_fixture("POPULATED_RESULTS")
                fixture["observations"]["visible_results"]["card_count"] = card_count
                # A displayed total is not evidence of a visible card.
                fixture["observations"]["visible_results"]["displayed_count_text"] = "2,000+ results"
                result = validate_evidence_fixture(fixture)
                self.assertFalse(result.valid)
                self.assertEqual(result.observed_state, EvidenceState.UNKNOWN)
                self.assertTrue(any("positive observed visible-card count" in issue for issue in result.issues))

    def test_populated_results_rejects_missing_card_count_field(self):
        fixture = synthetic_fixture("POPULATED_RESULTS")
        del fixture["observations"]["visible_results"]["card_count"]
        result = validate_evidence_fixture(fixture)
        self.assertFalse(result.valid)
        self.assertEqual(result.observed_state, EvidenceState.UNKNOWN)
        self.assertTrue(any("card_count" in issue for issue in result.issues))

    def test_legitimate_empty_requires_matching_identity_and_settled_observation(self):
        fixture = synthetic_fixture("LEGITIMATE_EMPTY")
        fixture["observations"]["page_identity"]["state"] = "unverified"
        fixture["observations"]["loading"]["state"] = "unknown"
        result = validate_evidence_fixture(fixture)
        self.assertFalse(result.valid)
        self.assertEqual(result.observed_state, EvidenceState.UNKNOWN)

    def test_legitimate_empty_requires_nonblank_state_scoped_evidence(self):
        for field_path, value in (
            (("page_identity", "evidence"), ""),
            (("loading", "evidence"), "not observed"),
            (("dom_evidence", "excerpt"), "   "),
        ):
            with self.subTest(field_path=field_path):
                fixture = synthetic_fixture("LEGITIMATE_EMPTY")
                fixture["observations"][field_path[0]][field_path[1]] = value
                result = validate_evidence_fixture(fixture)
                self.assertFalse(result.valid)
                self.assertEqual(result.observed_state, EvidenceState.UNKNOWN)

    def test_legitimate_empty_rejects_missing_identity_evidence(self):
        fixture = synthetic_fixture("LEGITIMATE_EMPTY")
        del fixture["observations"]["page_identity"]["evidence"]
        result = validate_evidence_fixture(fixture)
        self.assertFalse(result.valid)
        self.assertEqual(result.observed_state, EvidenceState.UNKNOWN)

    def test_interstitial_requires_specific_nonblank_observation(self):
        cases = (("kind", ""), ("kind", "none"), ("evidence", "no evidence"), ("evidence", ""))
        for field, value in cases:
            with self.subTest(field=field, value=value):
                fixture = synthetic_fixture("AUTHENTICATION_OR_INTERSTITIAL")
                fixture["observations"]["interstitial"][field] = value
                result = validate_evidence_fixture(fixture)
                self.assertFalse(result.valid)
                self.assertEqual(result.observed_state, EvidenceState.UNKNOWN)

    def test_interstitial_rejects_missing_evidence(self):
        fixture = synthetic_fixture("AUTHENTICATION_OR_INTERSTITIAL")
        del fixture["observations"]["interstitial"]["evidence"]
        result = validate_evidence_fixture(fixture)
        self.assertFalse(result.valid)
        self.assertEqual(result.observed_state, EvidenceState.UNKNOWN)

    def test_provenance_source_and_optional_metadata_are_validated(self):
        fixture = synthetic_fixture("UNKNOWN")
        fixture["provenance"]["source"] = "unverified_source"
        fixture["provenance"]["captured_at_utc"] = "2026-10-14T12:00:00"
        fixture["provenance"]["code_revision"] = "not a revision"
        result = validate_evidence_fixture(fixture)
        self.assertFalse(result.valid)
        self.assertGreaterEqual(len(result.issues), 3)

    def test_sensitive_looking_code_revision_is_rejected(self):
        fixture = synthetic_fixture("UNKNOWN")
        fixture["provenance"]["code_revision"] = "token=private"
        result = validate_evidence_fixture(fixture)
        self.assertFalse(result.valid)
        self.assertTrue(any("code_revision" in issue and "sensitive" in issue for issue in result.issues))

    def test_url_sanitizer_drops_credentials_path_query_and_fragment(self):
        self.assertEqual(
            sanitize_url("https://user:secret@example.invalid/search?token=secret#frag"),
            "https://example.invalid",
        )
        fixture = synthetic_fixture("UNKNOWN")
        fixture["observations"]["sanitized_url"] = (
            "https://example.invalid/search?token=secret"
        )
        result = validate_evidence_fixture(fixture)
        self.assertFalse(result.valid)
        self.assertTrue(any("sanitized HTTP(S) origin" in issue for issue in result.issues))

    def test_full_and_originless_urls_are_rejected_in_free_text_fields(self):
        cases = (
            (
                ("observations", "dom_evidence", "excerpt"),
                "Observed https://user:fixture@example.invalid/jobs/view/7?session=fixture#details",
            ),
            (
                ("provenance", "source_reference"),
                "www.example.invalid/jobs?token=fixture#panel",
            ),
            (
                ("interpretation", "notes"),
                "Related page: example.invalid/jobs?query=fixture#results",
            ),
        )
        for path, value in cases:
            with self.subTest(field=path):
                fixture = synthetic_fixture("UNKNOWN")
                target = fixture
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = value
                result = validate_evidence_fixture(fixture)
                self.assertFalse(result.valid)
                self.assertEqual(result.observed_state, EvidenceState.UNKNOWN)
                self.assertTrue(any("URL" in issue for issue in result.issues))

    def test_url_screenshot_reference_is_rejected(self):
        fixture = synthetic_fixture("UNKNOWN")
        fixture["screenshot"] = {
            "reference": "https://user:fixture@example.invalid/image.png?token=fixture#view",
            "sha256": "0" * 64,
        }
        result = validate_evidence_fixture(fixture, artifact_root=".")
        self.assertFalse(result.valid)
        self.assertTrue(any("screenshot.reference" in issue and "URL" in issue for issue in result.issues))

    def test_obvious_contact_and_secret_text_is_rejected(self):
        fixture = synthetic_fixture("UNKNOWN")
        fixture["observations"]["dom_evidence"]["excerpt"] = (
            "Email candidate@example.invalid; token=private"
        )
        result = validate_evidence_fixture(fixture)
        self.assertFalse(result.valid)
        self.assertTrue(any("sensitive" in issue for issue in result.issues))

    def test_screenshot_hash_is_verified_when_reference_is_supplied(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image_path = root / "synthetic.png"
            image_bytes = b"offline synthetic screenshot fixture"
            image_path.write_bytes(image_bytes)
            fixture = synthetic_fixture("POPULATED_RESULTS")
            fixture["screenshot"] = {
                "reference": "synthetic.png",
                "sha256": hashlib.sha256(image_bytes).hexdigest(),
            }
            result = validate_evidence_fixture(fixture, artifact_root=root)
            self.assertTrue(result.valid, result.issues)

            fixture["screenshot"]["sha256"] = "0" * 64
            mismatch = validate_evidence_fixture(fixture, artifact_root=root)
            self.assertFalse(mismatch.valid)
            self.assertTrue(any("does not match" in issue for issue in mismatch.issues))

    def test_screenshot_paths_cannot_escape_artifact_root(self):
        fixture = synthetic_fixture("UNKNOWN")
        fixture["screenshot"] = {"reference": "../outside.png", "sha256": "0" * 64}
        result = validate_evidence_fixture(fixture, artifact_root=".")
        self.assertFalse(result.valid)
        self.assertTrue(any("inside the supplied artifact root" in issue for issue in result.issues))

    def test_oversized_screenshot_is_rejected_before_open(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image_path = root / "oversized.png"
            image_path.write_bytes(b"x" * (MAX_SCREENSHOT_BYTES + 1))
            fixture = synthetic_fixture("UNKNOWN")
            fixture["screenshot"] = {
                "reference": image_path.name,
                "sha256": "0" * 64,
            }
            with patch.object(Path, "open", side_effect=AssertionError("oversized file opened")):
                result = validate_evidence_fixture(fixture, artifact_root=root)
            self.assertFalse(result.valid)
            self.assertEqual(result.observed_state, EvidenceState.UNKNOWN)
            self.assertTrue(any("maximum permitted size" in issue for issue in result.issues))

    def test_screenshot_growth_is_read_only_up_to_the_bound(self):
        class GrowingStream:
            def __init__(self):
                self.read_sizes = []
                self.total_read = 0

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

            def read(self, size=-1):
                self.read_sizes.append(size)
                self.total_read += size
                return b"x" * size

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image_path = root / "growing.png"
            image_path.write_bytes(b"x")
            resolved_image = image_path.resolve()
            fixture = synthetic_fixture("UNKNOWN")
            fixture["screenshot"] = {
                "reference": image_path.name,
                "sha256": "0" * 64,
            }
            stream = GrowingStream()
            original_stat = Path.stat
            original_open = Path.open

            def stale_small_stat(path, *args, **kwargs):
                if path == resolved_image:
                    result = original_stat(path, *args, **kwargs)
                    return SimpleNamespace(st_mode=result.st_mode, st_size=1)
                return original_stat(path, *args, **kwargs)

            def growing_open(path, *args, **kwargs):
                if path == resolved_image:
                    return stream
                return original_open(path, *args, **kwargs)

            with patch.object(Path, "stat", new=stale_small_stat), patch.object(
                Path, "open", new=growing_open
            ):
                result = validate_evidence_fixture(fixture, artifact_root=root)

            self.assertFalse(result.valid)
            self.assertEqual(result.observed_state, EvidenceState.UNKNOWN)
            self.assertTrue(any("maximum permitted size" in issue for issue in result.issues))
            self.assertEqual(stream.total_read, MAX_SCREENSHOT_BYTES + 1)
            self.assertLessEqual(max(stream.read_sizes), 64 * 1024)

    def test_invalid_artifact_root_type_is_a_validation_failure(self):
        fixture = synthetic_fixture("UNKNOWN")
        fixture["screenshot"] = {"reference": "synthetic.png", "sha256": "0" * 64}
        result = validate_evidence_fixture(fixture, artifact_root=[])
        self.assertFalse(result.valid)
        self.assertEqual(result.observed_state, EvidenceState.UNKNOWN)
        self.assertTrue(any("could not be read" in issue for issue in result.issues))

    def test_displayed_count_and_terminal_label_do_not_claim_completion(self):
        fixture = synthetic_fixture("POPULATED_RESULTS")
        fixture["observations"]["pagination"]["exhaustion_observation"] = (
            "terminal_condition_observed"
        )
        result = validate_evidence_fixture(fixture)
        self.assertTrue(result.valid, result.issues)
        self.assertEqual(result.completion_status, EvidenceCompletionStatus.UNKNOWN)

    def test_reached_cap_is_recorded_without_claiming_incompleteness_or_completion(self):
        fixture = synthetic_fixture("POPULATED_RESULTS")
        fixture["observations"]["pagination"]["cap_observation"] = "reached"
        result = validate_evidence_fixture(fixture)
        self.assertTrue(result.valid, result.issues)
        self.assertEqual(result.completion_status, EvidenceCompletionStatus.UNKNOWN)

    def test_populated_or_empty_fixture_never_becomes_production_complete(self):
        for state in (
            "POPULATED_RESULTS",
            "LEGITIMATE_EMPTY",
            "LOADING_OR_INCOMPLETE",
            "AUTHENTICATION_OR_INTERSTITIAL",
            "UNKNOWN",
        ):
            with self.subTest(state=state):
                result = self.validate(state)
                self.assertEqual(result.completion_status, EvidenceCompletionStatus.UNKNOWN)


if __name__ == "__main__":
    unittest.main()
