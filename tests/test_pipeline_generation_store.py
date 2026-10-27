import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pipeline_generation_store as store


def _fingerprint(data):
    return {"sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data)}


class PipelineGenerationStoreTests(unittest.TestCase):
    RUN_ID = "7c9d5c21-66eb-4ee7-84b8-2523d3bbf1d2"
    PRIOR_ID = "2eb56da5-e63b-4e6b-9d3c-b5abff7aa63b"
    STARTED = "2026-10-18T12:00:00Z"
    COMPLETED = "2026-10-18T12:01:00Z"
    SHA_EMPTY = hashlib.sha256(b"").hexdigest()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def _details_manifest(self, *, status="COMPLETE", run_id=None):
        run_id = run_id or self.RUN_ID
        artifacts = {
            "details_csv": b"Title,Link,Description\nBackend,https://example.test/1,Java\n",
            "diagnostics_json": b"[]",
        }
        outputs = {
            role: {
                "relative_path": {
                    "details_csv": "job_details.csv",
                    "diagnostics_json": "job_details_diagnostics.json",
                }[role],
                **_fingerprint(data),
            }
            for role, data in artifacts.items()
        }
        if status == "EMPTY":
            source_data = b"Title,Link\n"
            source_count = 0
            accounting = {
                "source_records": 0,
                "processed_records": 0,
                "intentionally_skipped_records": 0,
                "failed_records": 0,
            }
            outputs = {}
        else:
            source_data = b"input bytes"
            source_count = 1
            accounting = {
                "source_records": 1,
                "processed_records": 1,
                "intentionally_skipped_records": 0,
                "failed_records": 0,
            }
        if status == "PARTIAL":
            accounting = {
                "source_records": 2,
                "processed_records": 1,
                "intentionally_skipped_records": 0,
                "failed_records": 1,
            }
            source_count = 2
        manifest = {
            "schema_version": 1,
            "run_id": run_id,
            "stage": "job_details",
            "status": status,
            "started_at": self.STARTED,
            "completed_at": None if status == "IN_PROGRESS" else self.COMPLETED,
            "source": None if status == "IN_PROGRESS" else {
                "role": "jobs.csv",
                **_fingerprint(source_data),
                "record_count": source_count,
            },
            "input_generation": None,
            "accounting": None if status == "IN_PROGRESS" else accounting,
            "outputs": {} if status in {"IN_PROGRESS", "EMPTY", "FAILED"} else outputs,
            "failure": {"code": "SOURCE_INVALID"} if status == "FAILED" else None,
        }
        if status == "FAILED":
            manifest["source"] = None
            manifest["accounting"] = None
        return manifest, artifacts

    def _analyzer_manifest(self, *, status="COMPLETE", run_id=None, input_run_id=None):
        run_id = run_id or self.PRIOR_ID
        input_run_id = input_run_id or self.RUN_ID
        data = b'Title,Link,Match Score\nBackend,https://example.test/1,80%\n'
        empty = status == "EMPTY"
        input_status = "EMPTY" if empty else "COMPLETE"
        input_manifest_sha = "a" * 64
        source_data = b"" if empty else b"details csv bytes"
        input_artifact_sha = None if empty else hashlib.sha256(source_data).hexdigest()
        return {
            "schema_version": 1,
            "run_id": run_id,
            "stage": "job_analyzer",
            "status": status,
            "started_at": self.STARTED,
            "completed_at": None if status == "IN_PROGRESS" else self.COMPLETED,
            "source": None if status == "IN_PROGRESS" else {
                "role": "details_csv",
                **_fingerprint(source_data),
                "record_count": 0 if empty else 1,
            },
            "input_generation": None if status == "IN_PROGRESS" else {
                "stage": "job_details",
                "run_id": input_run_id,
                "status": input_status,
                "manifest_sha256": input_manifest_sha,
                "artifact_role": None if empty else "details_csv",
                "artifact_sha256": input_artifact_sha,
                "artifact_size_bytes": None if empty else len(source_data),
            },
            "accounting": None if status == "IN_PROGRESS" else {
                "source_records": 0 if empty else 1,
                "processed_records": 0 if empty else 1,
                "intentionally_skipped_records": 0,
                "failed_records": 0,
            },
            "outputs": {} if status in {"IN_PROGRESS", "EMPTY", "FAILED"} else {
                "analysis_csv": {"relative_path": "job_analysis.csv", **_fingerprint(data)},
            },
            "failure": {"code": "TRANSFORM_FAILED"} if status == "FAILED" else None,
        }

    def _write_artifacts(self, generation_dir, artifacts):
        for role, data in artifacts.items():
            name = {
                "details_csv": "job_details.csv",
                "diagnostics_json": "job_details_diagnostics.json",
            }[role]
            (generation_dir / name).write_bytes(data)

    def test_new_run_id_is_canonical_uuid4(self):
        run_id = store.new_run_id()
        self.assertEqual(store.validate_run_id(run_id), run_id)
        self.assertEqual(len(run_id), 36)

    def test_invalid_run_ids_rejected(self):
        invalid = (
            "not-a-uuid",
            "7c9d5c21-66eb-1ee7-84b8-2523d3bbf1d2",
            self.RUN_ID.upper(),
            "00000000-0000-0000-0000-000000000000",
            None,
            123,
            b"7c9d5c21-66eb-4ee7-84b8-2523d3bbf1d2",
        )
        for run_id in invalid:
            with self.subTest(run_id=run_id), self.assertRaises(store.GenerationValidationError):
                store.validate_run_id(run_id)

    def test_generation_creation_requires_explicit_existing_root_and_does_not_overwrite(self):
        generation = store.create_generation(self.root, "job_details", self.RUN_ID)
        self.assertEqual(generation.name, self.RUN_ID)
        with self.assertRaises(FileExistsError):
            store.create_generation(self.root, "job_details", self.RUN_ID)
        with self.assertRaises(store.GenerationValidationError):
            store.create_generation(None, "job_details", self.PRIOR_ID)
        with self.assertRaises(store.GenerationValidationError):
            store.create_generation(self.root / "missing", "job_details", self.PRIOR_ID)
        with self.assertRaises(store.GenerationValidationError):
            store.create_generation(self.root, "job_details", "")

    def test_stage_path_file_conflict_fails_without_overwriting_it(self):
        stage_path = self.root / "job_details"
        stage_path.write_text("existing non-directory content", encoding="utf-8")

        with self.assertRaises(FileExistsError):
            store.create_generation(self.root, "job_details", self.RUN_ID)

        self.assertEqual(stage_path.read_text(encoding="utf-8"), "existing non-directory content")

    def test_stage_creation_filesystem_error_propagates_without_generation(self):
        with patch.object(Path, "mkdir", side_effect=PermissionError("synthetic stage denied")):
            with self.assertRaisesRegex(PermissionError, "synthetic stage denied"):
                store.create_generation(self.root, "job_details", self.RUN_ID)

        self.assertEqual(list(self.root.iterdir()), [])

    def test_generated_generation_ids_are_unique_across_repeated_calls(self):
        first = store.create_generation(self.root, "job_details")
        second = store.create_generation(self.root, "job_details")

        self.assertNotEqual(first, second)
        self.assertEqual(first.parent, second.parent)
        self.assertEqual(store.validate_run_id(first.name), first.name)
        self.assertEqual(store.validate_run_id(second.name), second.name)
        self.assertTrue(first.is_dir())
        self.assertTrue(second.is_dir())

    def test_invalid_stage_is_rejected_for_generation_creation(self):
        with self.assertRaises(store.GenerationValidationError):
            store.create_generation(self.root, "unknown", self.RUN_ID)
        with self.assertRaises(store.GenerationValidationError):
            store.create_generation(self.root, [], self.RUN_ID)

    def test_valid_details_manifest_round_trip_and_artifact_verification(self):
        manifest, artifacts = self._details_manifest()
        generation = self.root / "job_details" / self.RUN_ID
        generation.mkdir(parents=True)
        self._write_artifacts(generation, artifacts)
        encoded = store.serialize_manifest(manifest)
        parsed = store.parse_manifest(encoded, generation_dir=generation, read_artifacts=True)
        self.assertEqual(parsed, manifest)
        self.assertEqual(store.validate_manifest(parsed, generation_dir=generation, read_artifacts=True), artifacts)

    def test_valid_empty_manifest_has_no_current_artifacts(self):
        manifest, _ = self._details_manifest(status="EMPTY")
        self.assertEqual(store.validate_manifest(manifest), {})

    def test_valid_in_progress_manifest_is_nonterminal(self):
        manifest, _ = self._details_manifest(status="IN_PROGRESS")
        self.assertEqual(store.validate_manifest(manifest), {})

    def test_valid_partial_manifest_is_diagnostic_only_artifact_set(self):
        manifest, artifacts = self._details_manifest(status="PARTIAL")
        generation = self.root / "job_details" / self.RUN_ID
        generation.mkdir(parents=True)
        self._write_artifacts(generation, artifacts)
        self.assertEqual(store.validate_manifest(manifest, generation_dir=generation, read_artifacts=True), artifacts)

    def test_failed_manifest_requires_failure_code_and_no_outputs(self):
        manifest, _ = self._details_manifest(status="FAILED")
        self.assertEqual(store.validate_manifest(manifest), {})
        manifest["failure"] = None
        with self.assertRaisesRegex(store.GenerationValidationError, "FAILED requires a failure code"):
            store.validate_manifest(manifest)

    def test_failed_source_and_accounting_counts_must_reconcile(self):
        manifest, _ = self._details_manifest(status="FAILED")
        manifest["source"] = {
            "role": "jobs.csv",
            **_fingerprint(b"input"),
            "record_count": 2,
        }
        manifest["accounting"] = {
            "source_records": 1,
            "processed_records": 0,
            "intentionally_skipped_records": 0,
            "failed_records": 1,
        }
        with self.assertRaisesRegex(store.GenerationValidationError, "failed source and accounting"):
            store.validate_manifest(manifest)

    def test_unknown_manifest_version_status_and_stage_are_rejected(self):
        for key, value in (("schema_version", 99), ("status", "UNKNOWN"), ("stage", "other")):
            manifest, _ = self._details_manifest()
            manifest[key] = value
            with self.subTest(key=key), self.assertRaises(store.GenerationValidationError):
                store.validate_manifest(manifest)
        for key in ("stage", "status"):
            manifest, _ = self._details_manifest()
            manifest[key] = []
            with self.subTest(key=key, malformed=manifest[key]), self.assertRaises(store.GenerationValidationError):
                store.validate_manifest(manifest)

    def test_invalid_timestamps_and_noncanonical_order_are_rejected(self):
        manifest, _ = self._details_manifest()
        manifest["started_at"] = "2026-10-18T12:00:00+00:00"
        with self.assertRaises(store.GenerationValidationError):
            store.validate_manifest(manifest)
        manifest, _ = self._details_manifest()
        manifest["started_at"] = "2026-10-18T12:02:00Z"
        with self.assertRaisesRegex(store.GenerationValidationError, "precedes"):
            store.validate_manifest(manifest)

    def test_invalid_hashes_sizes_and_accounting_are_rejected(self):
        cases = []
        manifest, _ = self._details_manifest()
        manifest["source"]["sha256"] = "A" * 64
        cases.append(manifest)
        manifest, _ = self._details_manifest()
        manifest["outputs"]["details_csv"]["size_bytes"] = True
        cases.append(manifest)
        manifest, _ = self._details_manifest()
        manifest["accounting"]["processed_records"] = 0
        cases.append(manifest)
        for candidate in cases:
            with self.subTest(candidate=candidate), self.assertRaises(store.GenerationValidationError):
                store.validate_manifest(candidate)

    def test_invalid_relative_paths_and_traversal_are_rejected(self):
        for path in ("../outside.csv", "a/../../outside.csv", "/absolute.csv", "C:/outside.csv", "a\\b.csv", "a//b.csv", "./file.csv", "nested/job_details.csv"):
            manifest, _ = self._details_manifest()
            manifest["outputs"]["details_csv"]["relative_path"] = path
            with self.subTest(path=path), self.assertRaises(store.GenerationValidationError):
                store.validate_manifest(manifest)

    def test_required_output_set_and_duplicate_output_paths_are_enforced(self):
        manifest, _ = self._details_manifest()
        manifest["outputs"].pop("diagnostics_json")
        with self.assertRaisesRegex(store.GenerationValidationError, "artifact set"):
            store.validate_manifest(manifest)
        manifest, _ = self._details_manifest()
        manifest["outputs"]["diagnostics_json"]["relative_path"] = "job_details.csv"
        with self.assertRaisesRegex(store.GenerationValidationError, "same path"):
            store.validate_manifest(manifest)
        manifest, _ = self._details_manifest()
        manifest["outputs"]["unexpected"] = manifest["outputs"].pop("diagnostics_json")
        with self.assertRaisesRegex(store.GenerationValidationError, "artifact set"):
            store.validate_manifest(manifest)

    def test_missing_artifact_and_hash_or_size_mismatch_are_rejected(self):
        manifest, artifacts = self._details_manifest()
        generation = self.root / "job_details" / self.RUN_ID
        generation.mkdir(parents=True)
        with self.assertRaises(FileNotFoundError):
            store.validate_manifest(manifest, generation_dir=generation, read_artifacts=True)
        self._write_artifacts(generation, artifacts)
        (generation / "job_details.csv").write_bytes(b"different bytes")
        with self.assertRaisesRegex(store.GenerationValidationError, "size mismatch|hash mismatch"):
            store.validate_manifest(manifest, generation_dir=generation, read_artifacts=True)
        (generation / "job_details.csv").write_bytes(artifacts["details_csv"])
        manifest["outputs"]["details_csv"]["size_bytes"] += 1
        with self.assertRaisesRegex(store.GenerationValidationError, "size mismatch"):
            store.validate_manifest(manifest, generation_dir=generation, read_artifacts=True)

    def test_mutation_between_artifact_reads_is_detected(self):
        manifest, artifacts = self._details_manifest()
        generation = self.root / "job_details" / self.RUN_ID
        generation.mkdir(parents=True)
        self._write_artifacts(generation, artifacts)
        original_read_bytes = Path.read_bytes

        def mutate_diagnostics_before_read(path):
            if path.name == "job_details_diagnostics.json":
                path.write_bytes(b"mutated diagnostics")
            return original_read_bytes(path)

        with patch.object(Path, "read_bytes", mutate_diagnostics_before_read):
            with self.assertRaisesRegex(store.GenerationValidationError, "size mismatch|hash mismatch"):
                store.read_verified_artifacts(manifest, generation)

    def test_generation_directory_name_must_match_manifest_id(self):
        manifest, artifacts = self._details_manifest()
        wrong_generation = self.root / "job_details" / self.PRIOR_ID
        wrong_generation.mkdir(parents=True)
        self._write_artifacts(wrong_generation, artifacts)
        with self.assertRaisesRegex(store.GenerationValidationError, "directory path"):
            store.validate_manifest(manifest, generation_dir=wrong_generation, read_artifacts=True)
        wrong_stage = self.root / "job_analyzer" / self.RUN_ID
        wrong_stage.mkdir(parents=True)
        self._write_artifacts(wrong_stage, artifacts)
        with self.assertRaisesRegex(store.GenerationValidationError, "directory path"):
            store.validate_manifest(manifest, generation_dir=wrong_stage, read_artifacts=True)

    def test_analyzer_requires_valid_details_generation_binding(self):
        manifest = self._analyzer_manifest()
        self.assertEqual(store.validate_manifest(manifest), {})
        manifest["input_generation"]["stage"] = "job_analyzer"
        with self.assertRaises(store.GenerationValidationError):
            store.validate_manifest(manifest)
        manifest = self._analyzer_manifest()
        manifest["input_generation"]["status"] = "PARTIAL"
        with self.assertRaises(store.GenerationValidationError):
            store.validate_manifest(manifest)
        manifest = self._analyzer_manifest(status="EMPTY")
        self.assertEqual(store.validate_manifest(manifest), {})

    def test_analyzer_source_fingerprint_must_match_referenced_details_bytes(self):
        manifest = self._analyzer_manifest()
        manifest["source"]["sha256"] = "c" * 64
        with self.assertRaisesRegex(store.GenerationValidationError, "does not match its input-generation"):
            store.validate_manifest(manifest)
        manifest = self._analyzer_manifest()
        manifest["input_generation"]["artifact_size_bytes"] += 1
        with self.assertRaisesRegex(store.GenerationValidationError, "does not match its input-generation"):
            store.validate_manifest(manifest)

    def test_analyzer_binding_rejects_wrong_generation_manifest_or_artifact(self):
        details_manifest, details_artifacts = self._details_manifest()
        details_manifest_bytes = store.serialize_manifest(details_manifest)
        details_bytes = details_artifacts["details_csv"]
        analyzer = self._analyzer_manifest()
        analyzer["input_generation"].update({
            "run_id": details_manifest["run_id"],
            "status": "COMPLETE",
            "manifest_sha256": hashlib.sha256(details_manifest_bytes).hexdigest(),
            "artifact_role": "details_csv",
            "artifact_sha256": hashlib.sha256(details_bytes).hexdigest(),
            "artifact_size_bytes": len(details_bytes),
        })
        analyzer["source"].update(_fingerprint(details_bytes))
        self.assertTrue(store.validate_analyzer_input_binding(
            analyzer,
            details_manifest,
            details_manifest_bytes=details_manifest_bytes,
            details_artifact_bytes=details_bytes,
        ))

        wrong_manifest = copy.deepcopy(details_manifest)
        wrong_manifest["run_id"] = self.PRIOR_ID
        with self.assertRaisesRegex(store.GenerationValidationError, "different details generation"):
            store.validate_analyzer_input_binding(
                analyzer,
                wrong_manifest,
                details_manifest_bytes=store.serialize_manifest(wrong_manifest),
                details_artifact_bytes=details_bytes,
            )
        mutated = bytearray(details_bytes)
        mutated[-1] ^= 1
        with self.assertRaisesRegex(store.GenerationValidationError, "artifact bytes"):
            store.validate_analyzer_input_binding(
                analyzer,
                details_manifest,
                details_manifest_bytes=details_manifest_bytes,
                details_artifact_bytes=bytes(mutated),
            )

    def test_empty_analyzer_binding_requires_matching_empty_generation(self):
        details_manifest, _ = self._details_manifest(status="EMPTY")
        details_manifest_bytes = store.serialize_manifest(details_manifest)
        analyzer = self._analyzer_manifest(status="EMPTY")
        analyzer["input_generation"].update({
            "run_id": details_manifest["run_id"],
            "status": "EMPTY",
            "manifest_sha256": hashlib.sha256(details_manifest_bytes).hexdigest(),
            "artifact_role": None,
            "artifact_sha256": None,
            "artifact_size_bytes": None,
        })
        self.assertTrue(store.validate_analyzer_input_binding(
            analyzer,
            details_manifest,
            details_manifest_bytes=details_manifest_bytes,
        ))

    def test_source_accounting_must_match_and_status_requirements_are_enforced(self):
        manifest, _ = self._details_manifest()
        manifest["accounting"]["failed_records"] = 1
        with self.assertRaises(store.GenerationValidationError):
            store.validate_manifest(manifest)
        manifest, _ = self._details_manifest(status="PARTIAL")
        manifest["accounting"]["processed_records"] = 0
        manifest["accounting"]["failed_records"] = 2
        with self.assertRaises(store.GenerationValidationError):
            store.validate_manifest(manifest)
        manifest, _ = self._details_manifest(status="EMPTY")
        manifest["source"]["record_count"] = 1
        with self.assertRaises(store.GenerationValidationError):
            store.validate_manifest(manifest)
        manifest = self._analyzer_manifest(status="EMPTY")
        manifest["input_generation"]["status"] = "COMPLETE"
        manifest["input_generation"]["artifact_role"] = "details_csv"
        manifest["input_generation"]["artifact_sha256"] = "b" * 64
        manifest["input_generation"]["artifact_size_bytes"] = 10
        manifest["source"].update({"sha256": "b" * 64, "size_bytes": 10})
        with self.assertRaisesRegex(store.GenerationValidationError, "requires an EMPTY details generation"):
            store.validate_manifest(manifest)

    def test_strict_json_rejects_duplicate_keys_and_invalid_utf8(self):
        with self.assertRaises(store.GenerationValidationError):
            store.parse_manifest(b'{"schema_version":1,"schema_version":1}')
        with self.assertRaises(store.GenerationValidationError):
            store.parse_manifest(b"\xff")

    def test_strict_json_rejects_non_object_manifest_roots_deterministically(self):
        for payload in (b"null", b"[]", b"\"manifest\"", b"7"):
            with self.subTest(payload=payload):
                messages = []
                for _ in range(2):
                    with self.assertRaises(store.GenerationValidationError) as caught:
                        store.parse_manifest(payload)
                    messages.append(str(caught.exception))
                self.assertEqual(messages, ["manifest must be an object"] * 2)

    def test_manifest_serialization_is_deterministic_and_does_not_mutate_input(self):
        manifest, _ = self._details_manifest()
        original = copy.deepcopy(manifest)

        first = store.serialize_manifest(manifest)
        second = store.serialize_manifest(copy.deepcopy(manifest))

        self.assertEqual(first, second)
        self.assertEqual(manifest, original)
        self.assertEqual(store.parse_manifest(first), original)

    def test_fingerprint_rejects_non_bytes_without_coercion(self):
        for value in ("payload", bytearray(b"payload"), memoryview(b"payload"), None):
            with self.subTest(value_type=type(value).__name__), self.assertRaisesRegex(
                TypeError, "data must be bytes"
            ):
                store.fingerprint_bytes(value)

    def test_exact_byte_fingerprint_and_parse_input_contract(self):
        payload = b'{"value":"original"}'
        fingerprint = store.fingerprint_bytes(payload)
        manifest, artifacts = self._details_manifest()
        artifacts["diagnostics_json"] = payload
        manifest["outputs"]["diagnostics_json"].update(_fingerprint(payload))
        generation = self.root / "job_details" / self.RUN_ID
        generation.mkdir(parents=True)
        self._write_artifacts(generation, artifacts)
        bytes_to_parse = store.read_verified_artifacts(manifest, generation)["diagnostics_json"]
        (generation / "job_details_diagnostics.json").write_bytes(b'{"value":"changed"}')
        self.assertEqual(json.loads(bytes_to_parse), {"value": "original"})
        self.assertEqual(fingerprint, _fingerprint(payload))

    def test_pointer_validates_complete_empty_and_failed_states(self):
        manifest, _ = self._details_manifest()
        pointer = {
            "schema_version": 1,
            "stage": "job_details",
            "latest_attempt": {"run_id": self.RUN_ID, "status": "COMPLETE"},
            "selected_generation_id": self.RUN_ID,
            "previous_complete_generation_id": self.PRIOR_ID,
            "selection_mode": "CURRENT",
            "recovery_event": None,
        }
        self.assertEqual(store.validate_pointer(pointer, manifest=manifest), pointer)
        pointer["latest_attempt"]["status"] = "FAILED"
        pointer["selected_generation_id"] = None
        pointer["selection_mode"] = "NONE"
        failed, _ = self._details_manifest(status="FAILED")
        self.assertEqual(store.validate_pointer(pointer, manifest=failed), pointer)
        empty, _ = self._details_manifest(status="EMPTY")
        pointer["latest_attempt"] = {"run_id": self.RUN_ID, "status": "EMPTY"}
        pointer["selected_generation_id"] = self.RUN_ID
        pointer["selection_mode"] = "EMPTY"
        self.assertEqual(store.validate_pointer(pointer, manifest=empty), pointer)

    def test_pointer_manifest_disagreement_and_invalid_pointer_are_rejected(self):
        pointer = {
            "schema_version": 1,
            "stage": "job_details",
            "latest_attempt": {"run_id": self.RUN_ID, "status": "COMPLETE"},
            "selected_generation_id": self.RUN_ID,
            "previous_complete_generation_id": None,
            "selection_mode": "CURRENT",
            "recovery_event": None,
        }
        manifest, _ = self._details_manifest()
        manifest["run_id"] = self.PRIOR_ID
        with self.assertRaisesRegex(store.GenerationValidationError, "disagree"):
            store.validate_pointer(pointer, manifest=manifest)
        bad = copy.deepcopy(pointer)
        bad["selection_mode"] = "NONE"
        with self.assertRaises(store.GenerationValidationError):
            store.validate_pointer(bad)
        bad = copy.deepcopy(pointer)
        bad["schema_version"] = 2
        with self.assertRaises(store.GenerationValidationError):
            store.validate_pointer(bad)
        bad = copy.deepcopy(pointer)
        bad["selection_mode"] = []
        with self.assertRaises(store.GenerationValidationError):
            store.validate_pointer(bad)
        bad = copy.deepcopy(pointer)
        bad["previous_complete_generation_id"] = self.RUN_ID
        with self.assertRaisesRegex(store.GenerationValidationError, "previous complete generation"):
            store.validate_pointer(bad)

    def test_pointer_rejects_selectable_partial_or_in_progress_status(self):
        for status in ("IN_PROGRESS", "PARTIAL", "FAILED"):
            pointer = {
                "schema_version": 1,
                "stage": "job_details",
                "latest_attempt": {"run_id": self.RUN_ID, "status": status},
                "selected_generation_id": self.RUN_ID,
                "previous_complete_generation_id": None,
                "selection_mode": "CURRENT",
                "recovery_event": None,
            }
            with self.subTest(status=status), self.assertRaises(store.GenerationValidationError):
                store.validate_pointer(pointer)

    def test_explicit_rollback_requires_authorization_and_matching_manifest_source(self):
        manifest, _ = self._details_manifest(run_id=self.PRIOR_ID)
        pointer = {
            "schema_version": 1,
            "stage": "job_details",
            "latest_attempt": {"run_id": self.RUN_ID, "status": "FAILED"},
            "selected_generation_id": self.PRIOR_ID,
            "previous_complete_generation_id": self.PRIOR_ID,
            "selection_mode": "EXPLICIT_ROLLBACK",
            "recovery_event": {
                "authorized_by": "owner",
                "authorization_ref": "approval-123",
                "at": self.COMPLETED,
                "reason": "restore prior generation",
                "source_sha256": manifest["source"]["sha256"],
            },
        }
        self.assertEqual(
            store.validate_pointer(
                pointer,
                manifest=manifest,
                current_source_sha256=manifest["source"]["sha256"],
                latest_attempt_manifest=self._details_manifest(status="FAILED")[0],
            ),
            pointer,
        )
        with self.assertRaisesRegex(store.GenerationValidationError, "does not match"):
            store.validate_pointer(pointer, manifest=manifest, current_source_sha256="c" * 64)

    def test_explicit_rollback_rejects_incomplete_or_invalid_recovery_metadata(self):
        manifest, _ = self._details_manifest(run_id=self.PRIOR_ID)
        failed_manifest, _ = self._details_manifest(status="FAILED")
        valid_pointer = {
            "schema_version": 1,
            "stage": "job_details",
            "latest_attempt": {"run_id": self.RUN_ID, "status": "FAILED"},
            "selected_generation_id": self.PRIOR_ID,
            "previous_complete_generation_id": self.PRIOR_ID,
            "selection_mode": "EXPLICIT_ROLLBACK",
            "recovery_event": {
                "authorized_by": "owner",
                "authorization_ref": "approval-123",
                "at": self.COMPLETED,
                "reason": "restore prior generation",
                "source_sha256": manifest["source"]["sha256"],
            },
        }
        invalid_events = []
        missing_field = copy.deepcopy(valid_pointer)
        del missing_field["recovery_event"]["authorization_ref"]
        invalid_events.append(("missing_field", missing_field))
        blank_reason = copy.deepcopy(valid_pointer)
        blank_reason["recovery_event"]["reason"] = "  "
        invalid_events.append(("blank_reason", blank_reason))
        malformed_time = copy.deepcopy(valid_pointer)
        malformed_time["recovery_event"]["at"] = "2026-10-18T12:01:00+00:00"
        invalid_events.append(("malformed_time", malformed_time))
        malformed_fingerprint = copy.deepcopy(valid_pointer)
        malformed_fingerprint["recovery_event"]["source_sha256"] = "g" * 64
        invalid_events.append(("malformed_fingerprint", malformed_fingerprint))

        for label, pointer in invalid_events:
            with self.subTest(case=label), self.assertRaises(store.GenerationValidationError):
                store.validate_pointer(
                    pointer,
                    manifest=manifest,
                    current_source_sha256=manifest["source"]["sha256"],
                    latest_attempt_manifest=failed_manifest,
                )


if __name__ == "__main__":
    unittest.main()
