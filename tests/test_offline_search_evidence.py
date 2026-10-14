import ast
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import offline_search_evidence
from offline_search_evidence import (
    MAX_METADATA_BYTES,
    MAX_PNG_BYTES,
    prepare_evidence_candidate,
)
from search_page_evidence import EvidenceCompletionStatus, EvidenceState


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def fixture_metadata(state="UNKNOWN"):
    card_count = 3 if state == "POPULATED_RESULTS" else None
    loading_state = "unknown" if state == "UNKNOWN" else "settled_observed"
    return {
        "schema_version": 1,
        "provenance": {
            "source": "synthetic_fixture",
            "source_reference": "synthetic/evidence.json",
        },
        "requested_scope": {"query": "backend engineer", "location": "Bengaluru"},
        "observations": {
            "sanitized_url": "https://example.invalid",
            "observed_state": state,
            "page_identity": {
                "state": "unverified",
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
                "displayed_count_text": None,
                "empty_state_observed": False,
            },
            "pagination": {
                "batch_observations": [],
                "exhaustion_observation": "unknown",
                "cap_observation": "unknown",
            },
            "interstitial": {
                "observed": False,
                "kind": "none",
                "evidence": "No interstitial observation in this synthetic fixture.",
            },
            "errors_observed": [],
        },
        "interpretation": {
            "notes": "Synthetic fixture only.",
            "search_completion_claim": False,
        },
        "limitations": ["Synthetic evidence does not establish live page behavior."],
    }


class OfflineSearchEvidenceTests(unittest.TestCase):
    def setUp(self):
        # Keep test artifacts under the project workspace, where the isolated
        # test runtime can resolve temporary paths reliably.
        project_root = Path(__file__).resolve().parents[1]
        self.temp_context = tempfile.TemporaryDirectory(dir=project_root)
        self.root = Path(self.temp_context.name).resolve()

    def tearDown(self):
        self.temp_context.cleanup()

    def write_metadata(self, metadata=None, name="metadata.json"):
        path = self.root / name
        path.write_text(
            json.dumps(metadata if metadata is not None else fixture_metadata()),
            encoding="utf-8",
        )
        return path

    def prepare(self, metadata_path, screenshot_path=None):
        return prepare_evidence_candidate(
            metadata_path,
            artifact_root=self.root,
            screenshot_path=screenshot_path,
        )

    def assert_unknown(self, result):
        self.assertEqual(
            result.validation.completion_status,
            EvidenceCompletionStatus.UNKNOWN,
        )

    def test_valid_synthetic_json_without_screenshot(self):
        metadata_path = self.write_metadata()
        result = self.prepare(metadata_path)
        self.assertTrue(result.validation.valid, result.validation.issues)
        self.assertIsNotNone(result.candidate_fixture)
        self.assertNotIn("screenshot", result.candidate_fixture)
        self.assert_unknown(result)

    def test_valid_synthetic_json_with_explicit_png(self):
        metadata_path = self.write_metadata()
        png = self.root / "capture.png"
        png.write_bytes(PNG_SIGNATURE + b"synthetic PNG payload")
        result = self.prepare(metadata_path, png)
        self.assertTrue(result.validation.valid, result.validation.issues)
        self.assertEqual(
            result.candidate_fixture["screenshot"]["sha256"],
            hashlib.sha256(png.read_bytes()).hexdigest(),
        )
        self.assertEqual(result.candidate_fixture["screenshot"]["reference"], "capture.png")
        self.assert_unknown(result)

    def test_missing_metadata_and_screenshot_files_are_rejected(self):
        missing_metadata = self.prepare(self.root / "missing.json")
        self.assertFalse(missing_metadata.validation.valid)
        self.assertIsNone(missing_metadata.candidate_fixture)
        self.assert_unknown(missing_metadata)

        metadata = self.write_metadata()
        missing_png = self.prepare(metadata, self.root / "missing.png")
        self.assertFalse(missing_png.validation.valid)
        self.assertIsNone(missing_png.candidate_fixture)
        self.assert_unknown(missing_png)

    def test_malformed_utf8_json_and_non_object_json_are_rejected(self):
        invalid_utf8 = self.root / "invalid_utf8.json"
        invalid_utf8.write_bytes(b"\xff")
        malformed = self.prepare(invalid_utf8)
        self.assertFalse(malformed.validation.valid)
        self.assert_unknown(malformed)

        non_object = self.root / "array.json"
        non_object.write_text("[]", encoding="utf-8")
        result = self.prepare(non_object)
        self.assertFalse(result.validation.valid)
        self.assert_unknown(result)

    def test_oversized_metadata_is_rejected(self):
        oversized = self.root / "oversized.json"
        oversized.write_bytes(b" " * (MAX_METADATA_BYTES + 1))
        result = self.prepare(oversized)
        self.assertFalse(result.validation.valid)
        self.assertIsNone(result.candidate_fixture)
        self.assert_unknown(result)

    def test_oversized_png_is_rejected(self):
        metadata = self.write_metadata()
        png = self.root / "oversized.png"
        with png.open("wb") as target:
            target.write(PNG_SIGNATURE)
            target.seek(MAX_PNG_BYTES)
            target.write(b"x")
        result = self.prepare(metadata, png)
        self.assertFalse(result.validation.valid)
        self.assertIsNone(result.candidate_fixture)
        self.assert_unknown(result)

    def test_invalid_png_signature_is_rejected(self):
        metadata = self.write_metadata()
        png = self.root / "not_png.png"
        png.write_bytes(b"not a PNG file")
        result = self.prepare(metadata, png)
        self.assertFalse(result.validation.valid)
        self.assert_unknown(result)

    def test_declared_screenshot_hash_mismatch_is_rejected(self):
        png = self.root / "capture.png"
        png.write_bytes(PNG_SIGNATURE + b"synthetic PNG payload")
        metadata = fixture_metadata()
        metadata["screenshot"] = {"reference": "capture.png", "sha256": "0" * 64}
        metadata_path = self.write_metadata(metadata)
        result = self.prepare(metadata_path, png)
        self.assertFalse(result.validation.valid)
        self.assertIsNone(result.candidate_fixture)
        self.assert_unknown(result)

    def test_screenshot_metadata_requires_explicit_screenshot_path(self):
        metadata = fixture_metadata()
        metadata["screenshot"] = {"reference": "capture.png", "sha256": "0" * 64}
        result = self.prepare(self.write_metadata(metadata))
        self.assertFalse(result.validation.valid)
        self.assert_unknown(result)

    def test_screenshot_reference_traversal_is_rejected(self):
        png = self.root / "capture.png"
        png.write_bytes(PNG_SIGNATURE + b"synthetic")
        metadata = fixture_metadata()
        metadata["screenshot"] = {"reference": "../capture.png", "sha256": "0" * 64}
        result = self.prepare(self.write_metadata(metadata), png)
        self.assertFalse(result.validation.valid)
        self.assert_unknown(result)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks are unsupported")
    def test_screenshot_symlink_escape_is_rejected_when_supported(self):
        with tempfile.TemporaryDirectory(dir=self.root.parent) as outside_directory:
            outside = Path(outside_directory) / "outside.png"
            outside.write_bytes(PNG_SIGNATURE + b"synthetic")
            link = self.root / "linked.png"
            try:
                link.symlink_to(outside)
            except (OSError, NotImplementedError):
                self.skipTest("symlink creation is not permitted")
            result = self.prepare(self.write_metadata(), link)
            self.assertFalse(result.validation.valid)
            self.assert_unknown(result)

    def test_raw_urls_and_unsafe_text_are_rejected_by_validator(self):
        for text in (
            "Visible text at https://user:fixture@example.invalid/jobs?q=fixture#page",
            "Observed at www.example.invalid/jobs?session=fixture",
            "Authorization: fixture-value",
        ):
            with self.subTest(kind="unsafe evidence"):
                metadata = fixture_metadata()
                metadata["observations"]["dom_evidence"]["excerpt"] = text
                result = self.prepare(self.write_metadata(metadata))
                self.assertFalse(result.validation.valid)
                self.assertIsNone(result.candidate_fixture)
                self.assert_unknown(result)

    def test_missing_and_contradictory_metadata_are_rejected(self):
        missing = fixture_metadata()
        del missing["requested_scope"]["location"]
        missing_result = self.prepare(self.write_metadata(missing))
        self.assertFalse(missing_result.validation.valid)
        self.assert_unknown(missing_result)

        contradictory = fixture_metadata("POPULATED_RESULTS")
        contradictory["observations"]["visible_results"]["card_count"] = 0
        contradictory_result = self.prepare(self.write_metadata(contradictory))
        self.assertFalse(contradictory_result.validation.valid)
        self.assert_unknown(contradictory_result)

    def test_validator_rejection_does_not_return_candidate(self):
        metadata = fixture_metadata()
        metadata["interpretation"]["search_completion_claim"] = True
        result = self.prepare(self.write_metadata(metadata))
        self.assertFalse(result.validation.valid)
        self.assertIsNone(result.candidate_fixture)
        self.assert_unknown(result)

    def test_paths_must_resolve_inside_artifact_root(self):
        metadata = self.write_metadata()
        with tempfile.TemporaryDirectory(dir=self.root.parent) as outside_directory:
            outside = Path(outside_directory) / "metadata.json"
            outside.write_text(json.dumps(fixture_metadata()), encoding="utf-8")
            result = self.prepare(outside)
            self.assertFalse(result.validation.valid)
            self.assert_unknown(result)

    def test_explicit_input_paths_are_used_without_directory_crawling(self):
        metadata = self.write_metadata()
        (self.root / "unrelated.json").write_text("not metadata", encoding="utf-8")
        with patch.object(Path, "glob", side_effect=AssertionError("glob called")), patch.object(
            Path, "rglob", side_effect=AssertionError("rglob called")
        ):
            result = self.prepare(metadata)
        self.assertTrue(result.validation.valid, result.validation.issues)
        self.assertEqual(result.candidate_fixture["provenance"]["source_reference"], "synthetic/evidence.json")
        self.assert_unknown(result)

    def test_prototype_creates_no_files(self):
        metadata = self.write_metadata()
        before = {item.relative_to(self.root) for item in self.root.rglob("*")}
        original_open = Path.open
        opened_modes = []

        def read_only_open(path, mode="r", *args, **kwargs):
            opened_modes.append(mode)
            if any(flag in mode for flag in ("w", "a", "x", "+")):
                raise AssertionError("write mode requested")
            return original_open(path, mode, *args, **kwargs)

        with patch.object(Path, "open", new=read_only_open):
            result = self.prepare(metadata)
        after = {item.relative_to(self.root) for item in self.root.rglob("*")}
        self.assertTrue(result.validation.valid, result.validation.issues)
        self.assertEqual(before, after)
        self.assertEqual(opened_modes, ["rb"])
        self.assert_unknown(result)

    def test_module_imports_no_production_browser_or_network_modules(self):
        source = Path(offline_search_evidence.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.add(node.module.split(".")[0])

        forbidden = {
            "job_search",
            "route_audit",
            "easy_apply",
            "external_app",
            "execution_policy",
            "playwright",
            "requests",
            "httpx",
            "urllib",
            "socket",
            "subprocess",
        }
        self.assertTrue(forbidden.isdisjoint(imports), imports & forbidden)
        self.assertIn("search_page_evidence", imports)

    def test_all_results_keep_completion_status_unknown(self):
        valid = self.prepare(self.write_metadata())
        invalid = self.prepare(self.root / "missing.json")
        self.assert_unknown(valid)
        self.assert_unknown(invalid)
        self.assertEqual(valid.validation.completion_status, EvidenceCompletionStatus.UNKNOWN)
        self.assertEqual(invalid.validation.completion_status, EvidenceCompletionStatus.UNKNOWN)


if __name__ == "__main__":
    unittest.main()
