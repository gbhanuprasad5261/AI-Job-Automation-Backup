import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import offline_provenance_verifier as verifier


SOURCE_HEADER = "Title,Company,Location,Easy Apply,Actively Reviewing,Link\n"
DETAILS_HEADER = '"Title","Company","Location","Experience","Easy Apply","Skills","Link","Description"\n'
ANALYSIS_HEADER = '"Title","Company","Location","Easy Apply","Match Score","Priority","Matched Skills","Missing Skills","Experience Required","Experience Years","Experience Skip","Data Status","Application Eligible","Link"\n'
RUN_SOURCE = "7c9d5c21-66eb-4ee7-84b8-2523d3bbf1d2"
RUN_DETAILS = "2eb56da5-e63b-4e6b-9d3c-b5abff7aa63b"
RUN_ANALYSIS = "3c7c5d21-66eb-4ee7-84b8-3523d3bbf1d2"
STARTED = "2026-10-18T12:00:00Z"
COMPLETED = "2026-10-18T12:01:00Z"


def _fp(data):
    return {"sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data)}


def _encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _artifact(path, fmt, data, rows):
    return {
        "relative_path": path,
        **_fp(data),
        "record_count": rows,
        "format": fmt,
    }


class OfflineProvenanceVerifierTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.serial = 0

    def _bytes(self, name, data):
        path = self.root / name
        path.write_bytes(data)
        return path.read_bytes()

    def _source(self, rows=None):
        if rows is None:
            rows = ["Backend,Example,Bengaluru,Yes,No,https://example.test/1\n"]
        data = self._bytes("source.csv", (SOURCE_HEADER + "".join(rows)).encode("utf-8"))
        count = len(rows)
        run_id = RUN_SOURCE
        status = "COMPLETE" if count else "EMPTY"
        manifest = {
            "schema_version": 1,
            "run_id": run_id,
            "stage": "source",
            "status": status,
            "producer": {"id": "synthetic-source", "version": "test-1"},
            "started_at": STARTED,
            "completed_at": COMPLETED,
            "source": {
                "role": "jobs_csv",
                **_fp(data),
                "record_count": count,
                "encoding": "utf-8",
                "format": "csv/jobs-v1",
            },
            "input_generation": None,
            "accounting": None,
            "occurrences": None,
            "outputs": {"jobs_csv": _artifact("jobs.csv", "csv/jobs-v1", data, count)},
            "failure": None,
        }
        return _encode(manifest), {"jobs_csv": data}, manifest

    def _occurrence(self, source_hash, ordinal, *, disposition="PROCESSED",
                    logical_identity="job-1", reason=None, policy_rule=None,
                    retained=None, error=None, quality=None, output_row=1):
        return {
            "ordinal": ordinal,
            "occurrence_key": f"{source_hash}:{ordinal}",
            "logical_identity": logical_identity,
            "disposition": disposition,
            "reason_code": reason,
            "policy_rule_id": policy_rule,
            "retained_occurrence_key": retained,
            "error_code": error,
            "quality_code": quality,
            "output_row": output_row,
        }

    def _details(self, source_bundle=None, *, source_rows=None, descs=None,
                 dispositions=None, status=None, run_id=RUN_DETAILS):
        if source_bundle is None:
            source_bundle = self._source(source_rows)
        source_bytes, source_artifacts, source_manifest = source_bundle
        source_data = source_artifacts["jobs_csv"]
        rows = source_manifest["source"]["record_count"]
        if descs is None:
            descs = ["Java backend development experience"]
        if dispositions is None:
            dispositions = ["PROCESSED"] * rows
        output_rows = sum(1 for d in dispositions if d == "PROCESSED")
        csv_data = DETAILS_HEADER.encode() + "".join(
            f'"Backend","Example","Bengaluru","5 years","Yes","Java","https://example.test/{i}","{description}"\n'
            for i, description in enumerate(descs[:output_rows], 1)
        ).encode()
        csv_data = self._bytes("details.csv", csv_data)
        diagnostics = self._bytes("diagnostics.json", b"[]")
        occurrences = []
        output_row = 0
        for ordinal, disposition in enumerate(dispositions, 1):
            if disposition == "PROCESSED":
                output_row += 1
                occurrences.append(self._occurrence(
                    source_manifest["source"]["sha256"], ordinal,
                    logical_identity="job-" + str(ordinal), output_row=output_row,
                    quality="DESCRIPTION_MISSING" if descs and output_row <= len(descs) and not descs[output_row - 1].strip() else None,
                ))
            elif disposition == "FAILED":
                occurrences.append(self._occurrence(
                    source_manifest["source"]["sha256"], ordinal,
                    logical_identity="job-" + str(ordinal), disposition="FAILED",
                    error="EXTRACTION_ERROR", output_row=None,
                ))
            else:
                occurrences.append(self._occurrence(
                    source_manifest["source"]["sha256"], ordinal,
                    logical_identity="job-" + str(ordinal), disposition="INTENTIONAL_SKIP",
                    reason="FILTERED", policy_rule="approved-rule-v1",
                    retained=(f"{source_manifest['source']['sha256']}:{ordinal - 1}" if ordinal > 1 else None),
                    output_row=None,
                ))
        failed = dispositions.count("FAILED")
        skipped = dispositions.count("INTENTIONAL_SKIP")
        if status is None:
            status = "EMPTY" if rows == 0 else ("PARTIAL" if failed and output_rows else "COMPLETE")
        outputs = {}
        artifacts = {}
        if status in {"COMPLETE", "PARTIAL"}:
            outputs = {
                "details_csv": _artifact("job_details.csv", "csv/details-v1", csv_data, output_rows),
                "diagnostics_json": _artifact("job_details_diagnostics.json", "json/diagnostics-v1", diagnostics, 0),
            }
            artifacts = {"details_csv": csv_data, "diagnostics_json": diagnostics}
        accounting = {
            "source_occurrences": rows,
            "processed_occurrences": output_rows,
            "intentional_skip_occurrences": skipped,
            "failed_occurrences": failed,
            "output_rows": output_rows,
        }
        source_descriptor = {
            "role": "jobs_csv",
            **_fp(source_data),
            "record_count": rows,
            "encoding": "utf-8",
            "format": "csv/jobs-v1",
        }
        input_ref = {
            "stage": "source",
            "run_id": source_manifest["run_id"],
            "status": source_manifest["status"],
            "manifest_sha256": hashlib.sha256(source_bytes).hexdigest(),
            "artifact_role": "jobs_csv",
            "artifact_sha256": source_manifest["outputs"]["jobs_csv"]["sha256"],
            "artifact_size_bytes": source_manifest["outputs"]["jobs_csv"]["size_bytes"],
            "record_count": rows,
        }
        manifest = {
            "schema_version": 1,
            "run_id": run_id,
            "stage": "job_details",
            "status": status,
            "producer": {"id": "synthetic-details", "version": "test-1"},
            "started_at": STARTED,
            "completed_at": COMPLETED,
            "source": source_descriptor,
            "input_generation": input_ref,
            "accounting": accounting,
            "occurrences": occurrences,
            "outputs": outputs,
            "failure": None,
        }
        return _encode(manifest), artifacts, manifest, source_bytes, source_artifacts

    def _verify_details(self, bundle):
        manifest_bytes, artifacts, manifest, source_bytes, source_artifacts = bundle
        return verifier.verify_generation(
            manifest_bytes, artifacts, expected_stage="job_details",
            upstream_manifest_bytes=source_bytes,
            upstream_artifacts_by_role=source_artifacts,
        )

    def _analysis(self, details_bundle):
        details_bytes, details_artifacts, details_manifest, source_bytes, source_artifacts = details_bundle
        data = self._bytes(
            "analysis.csv",
            ANALYSIS_HEADER.encode() + b'"Backend","Example","Bengaluru","Yes","80%","High","Java","","5 years","5","No","OK","No","https://example.test/1"\n',
        )
        count = details_manifest["outputs"].get("details_csv", {}).get("record_count", 0)
        status = "EMPTY" if details_manifest["status"] == "EMPTY" else "COMPLETE"
        output = {} if status == "EMPTY" else {
            "analysis_csv": _artifact("job_analysis.csv", "csv/analysis-v1", data, 1)
        }
        artifacts = {} if status == "EMPTY" else {"analysis_csv": data}
        source_hash = details_manifest["outputs"].get("details_csv", {}).get("sha256", hashlib.sha256(b"").hexdigest())
        source_size = details_manifest["outputs"].get("details_csv", {}).get("size_bytes", 0)
        ref = {
            "stage": "job_details",
            "run_id": details_manifest["run_id"],
            "status": details_manifest["status"],
            "manifest_sha256": hashlib.sha256(details_bytes).hexdigest(),
            "artifact_role": "details_csv" if details_manifest["status"] == "COMPLETE" else None,
            "artifact_sha256": source_hash if details_manifest["status"] == "COMPLETE" else None,
            "artifact_size_bytes": source_size if details_manifest["status"] == "COMPLETE" else None,
            "record_count": count,
        }
        manifest = {
            "schema_version": 1,
            "run_id": RUN_ANALYSIS,
            "stage": "job_analyzer",
            "status": status,
            "producer": {"id": "synthetic-analyzer", "version": "test-1"},
            "started_at": STARTED,
            "completed_at": COMPLETED,
            "source": {
                "role": "details_csv",
                "sha256": source_hash,
                "size_bytes": source_size,
                "record_count": count,
                "encoding": "utf-8",
                "format": "csv/details-v1",
            },
            "input_generation": ref,
            "accounting": {
                "source_occurrences": count,
                "processed_occurrences": count,
                "intentional_skip_occurrences": 0,
                "failed_occurrences": 0,
                "output_rows": 0 if status == "EMPTY" else 1,
            },
            "occurrences": [] if status == "EMPTY" else [
                self._occurrence(source_hash, 1, output_row=1)
            ],
            "outputs": output,
            "failure": None,
        }
        return _encode(manifest), artifacts, manifest, details_bytes, details_artifacts

    def test_01_valid_complete_generation(self):
        bundle = self._details()
        result = self._verify_details(bundle)
        self.assertTrue(result.accepted)
        self.assertFalse(result.eligible)
        self.assertEqual(result.classification, "VERIFIED_DATA_ONLY")

    def test_02_valid_empty_generation(self):
        source = self._source([])
        result = verifier.verify_generation(source[0], source[1], expected_stage="source")
        self.assertTrue(result.accepted)
        self.assertFalse(result.eligible)
        self.assertEqual(result.classification, "EMPTY_DATA_ONLY")

    def test_03_missing_manifest(self):
        result = verifier.verify_generation(None, {})
        self.assertEqual(result.failure_code, "MISSING_MANIFEST")

    def test_04_unknown_schema_version(self):
        bundle = self._details()
        data = json.loads(bundle[0])
        data["schema_version"] = 7
        result = verifier.verify_generation(_encode(data), bundle[1])
        self.assertEqual(result.failure_code, "UNKNOWN_SCHEMA_VERSION")

    def test_05_malformed_manifest(self):
        result = verifier.verify_generation(b'{"schema_version":1,', {})
        self.assertEqual(result.failure_code, "MALFORMED_MANIFEST")

    def test_06_duplicate_artifact_declaration(self):
        raw = b'{"outputs":{"x":1,"x":2}}'
        result = verifier.verify_generation(raw, {})
        self.assertEqual(result.failure_code, "DUPLICATE_JSON_KEY")

    def test_07_missing_artifact(self):
        bundle = self._details()
        result = self._verify_details((bundle[0], {}, *bundle[2:]))
        self.assertEqual(result.failure_code, "MISSING_ARTIFACT")

    def test_08_incorrect_artifact_size(self):
        bundle = self._details()
        manifest = json.loads(bundle[0])
        manifest["outputs"]["details_csv"]["size_bytes"] += 1
        result = self._verify_details((_encode(manifest), bundle[1], *bundle[2:]))
        self.assertEqual(result.failure_code, "ARTIFACT_SIZE_MISMATCH")

    def test_09_incorrect_fingerprint(self):
        bundle = self._details()
        manifest = json.loads(bundle[0])
        manifest["outputs"]["details_csv"]["sha256"] = "0" * 64
        result = self._verify_details((_encode(manifest), bundle[1], *bundle[2:]))
        self.assertEqual(result.failure_code, "ARTIFACT_HASH_MISMATCH")

    def test_10_source_fingerprint_mismatch(self):
        bundle = self._details()
        manifest = json.loads(bundle[0])
        manifest["source"]["sha256"] = "0" * 64
        result = self._verify_details((_encode(manifest), bundle[1], *bundle[2:]))
        self.assertEqual(result.failure_code, "SOURCE_FINGERPRINT_MISMATCH")

    def test_11_details_bound_to_wrong_source_generation(self):
        bundle = self._details()
        manifest = json.loads(bundle[0])
        manifest["input_generation"]["run_id"] = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        result = self._verify_details((_encode(manifest), bundle[1], *bundle[2:]))
        self.assertEqual(result.failure_code, "INPUT_GENERATION_MISMATCH")

    def test_12_analysis_bound_to_wrong_details_generation(self):
        details = self._details()
        analysis = self._analysis(details)
        manifest = json.loads(analysis[0])
        manifest["input_generation"]["run_id"] = RUN_SOURCE
        result = verifier.verify_generation(
            _encode(manifest), analysis[1], expected_stage="job_analyzer",
            upstream_manifest_bytes=analysis[3], upstream_artifacts_by_role=analysis[4],
            upstream_chain=((details[3], details[4]),),
        )
        self.assertEqual(result.failure_code, "INPUT_GENERATION_MISMATCH")

    def test_13_contradictory_record_counts(self):
        bundle = self._details()
        manifest = json.loads(bundle[0])
        manifest["accounting"]["processed_occurrences"] += 1
        result = self._verify_details((_encode(manifest), bundle[1], *bundle[2:]))
        self.assertEqual(result.failure_code, "COUNT_MISMATCH")

    def test_14_unaccounted_source_occurrence(self):
        bundle = self._details()
        manifest = json.loads(bundle[0])
        manifest["occurrences"] = []
        result = self._verify_details((_encode(manifest), bundle[1], *bundle[2:]))
        self.assertEqual(result.failure_code, "UNACCOUNTED_OCCURRENCE")

    def test_15_duplicate_source_occurrences_remain_distinct(self):
        source = self._source([
            "Backend,Example,Bengaluru,Yes,No,https://example.test/1\n",
            "Backend,Example,Bengaluru,Yes,No,https://example.test/1\n",
        ])
        bundle = self._details(
            source, descs=["Java experience", "Java experience"],
            dispositions=["PROCESSED", "PROCESSED"],
        )
        result = self._verify_details(bundle)
        self.assertTrue(result.accepted)
        self.assertEqual(len({o["occurrence_key"] for o in bundle[2]["occurrences"]}), 2)

    def test_16_skip_without_approved_policy_is_not_accepted(self):
        source = self._source([
            "Backend,Example,Bengaluru,Yes,No,https://example.test/1\n",
            "Backend,Example,Bengaluru,Yes,No,https://example.test/2\n",
        ])
        bundle = self._details(source, dispositions=["PROCESSED", "INTENTIONAL_SKIP"])
        manifest = json.loads(bundle[0])
        manifest["occurrences"][1]["reason_code"] = None
        result = self._verify_details((_encode(manifest), bundle[1], *bundle[2:]))
        self.assertEqual(result.failure_code, "UNAPPROVED_SKIP_RULE")

    def test_17_extraction_failure_cannot_be_claimed_complete(self):
        source = self._source([
            "Backend,Example,Bengaluru,Yes,No,https://example.test/1\n",
        ])
        bundle = self._details(source, dispositions=["FAILED"], status="COMPLETE")
        result = self._verify_details(bundle)
        self.assertEqual(result.failure_code, "STATUS_CONTRADICTION")

    def test_18_blank_description_is_policy_unresolved(self):
        bundle = self._details(descs=[""])
        result = self._verify_details(bundle)
        self.assertEqual(result.classification, "UNSUPPORTED_POLICY")
        self.assertIn("D5", result.policy_dependencies)
        manifest = json.loads(bundle[0])
        manifest["occurrences"][0]["quality_code"] = None
        result = self._verify_details((_encode(manifest), bundle[1], *bundle[2:]))
        self.assertEqual(result.failure_code, "BLANK_QUALITY_UNCLASSIFIED")

    def test_19_partial_mislabeled_complete_is_rejected(self):
        source = self._source([
            "Backend,Example,Bengaluru,Yes,No,https://example.test/1\n",
            "Backend,Example,Bengaluru,Yes,No,https://example.test/2\n",
        ])
        bundle = self._details(source, dispositions=["PROCESSED", "FAILED"], status="COMPLETE")
        result = self._verify_details(bundle)
        self.assertEqual(result.failure_code, "STATUS_CONTRADICTION")

    def test_20_failed_attempt_never_implicitly_falls_back(self):
        successful = self._verify_details(self._details())
        failed_manifest = {
            "schema_version": 1, "run_id": RUN_DETAILS, "stage": "job_details",
            "status": "FAILED", "producer": {"id": "synthetic", "version": "1"},
            "started_at": STARTED, "completed_at": COMPLETED, "source": None,
            "input_generation": None, "accounting": None, "occurrences": None,
            "outputs": {}, "failure": {"code": "STAGE_FAILURE"},
        }
        latest = verifier.verify_generation(_encode(failed_manifest), {})
        result = verifier.verify_selection(latest, successful)
        self.assertEqual(result.failure_code, "IMPLICIT_OLD_GENERATION_FALLBACK")

    def test_21_conflicting_generation_identifier(self):
        bundle = self._details()
        manifest = json.loads(bundle[0])
        manifest["input_generation"]["run_id"] = RUN_DETAILS
        result = self._verify_details((_encode(manifest), bundle[1], *bundle[2:]))
        self.assertEqual(result.failure_code, "INPUT_GENERATION_MISMATCH")

    def test_22_malformed_csv_schema_is_rejected_even_with_matching_hash(self):
        bundle = self._details()
        manifest = json.loads(bundle[0])
        data = b"wrong,header\nvalue,here\n"
        data = self._bytes("malformed.csv", data)
        manifest["outputs"]["details_csv"].update(_fp(data))
        manifest["outputs"]["details_csv"]["record_count"] = 1
        result = self._verify_details((_encode(manifest), {
            **bundle[1], "details_csv": data,
        }, *bundle[2:]))
        self.assertEqual(result.failure_code, "ARTIFACT_SCHEMA_INVALID")

    def test_23_artifact_change_after_fingerprint_is_detected(self):
        bundle = self._details()
        mutated = bundle[1]["details_csv"] + b" "
        mutated = self._bytes("mutated.csv", mutated)
        result = self._verify_details((bundle[0], {
            **bundle[1], "details_csv": mutated,
        }, *bundle[2:]))
        self.assertEqual(result.failure_code, "ARTIFACT_SIZE_MISMATCH")

    def test_24_unexpected_artifact_role_is_rejected(self):
        bundle = self._details()
        manifest = json.loads(bundle[0])
        manifest["outputs"]["unexpected"] = copy.deepcopy(manifest["outputs"]["details_csv"])
        artifacts = {**bundle[1], "unexpected": bundle[1]["details_csv"]}
        result = self._verify_details((_encode(manifest), artifacts, *bundle[2:]))
        self.assertEqual(result.failure_code, "UNEXPECTED_ARTIFACT_ROLE")

    def test_25_rollback_without_verifiable_authority_is_rejected(self):
        result = verifier.verify_rollback_request({
            "authorized_by": "owner", "authorization_ref": "ticket-1",
            "at": COMPLETED, "reason": "rollback", "source_sha256": "a" * 64,
        })
        self.assertEqual(result.classification, "UNSUPPORTED_POLICY")
        self.assertEqual(result.failure_code, "ROLLBACK_AUTHORITY_UNVERIFIABLE")

    def test_in_progress_is_incomplete_and_never_eligible(self):
        bundle = self._details()
        manifest = json.loads(bundle[0])
        manifest.update({
            "status": "IN_PROGRESS", "completed_at": None, "source": None,
            "accounting": None, "occurrences": None, "outputs": {},
        })
        result = verifier.verify_generation(_encode(manifest), {})
        self.assertEqual(result.classification, "INCOMPLETE")
        self.assertFalse(result.eligible)

    def test_partial_generation_is_diagnostic_only(self):
        source = self._source([
            "Backend,Example,Bengaluru,Yes,No,https://example.test/1\n",
            "Backend,Example,Bengaluru,Yes,No,https://example.test/2\n",
        ])
        bundle = self._details(source, dispositions=["PROCESSED", "FAILED"])
        result = self._verify_details(bundle)
        self.assertEqual(result.classification, "UNSUPPORTED_POLICY")
        self.assertFalse(result.eligible)

    def test_duplicate_skip_policy_is_exposed_as_unresolved(self):
        source = self._source([
            "Backend,Example,Bengaluru,Yes,No,https://example.test/1\n",
            "Backend,Example,Bengaluru,Yes,No,https://example.test/1\n",
        ])
        bundle = self._details(source, dispositions=["PROCESSED", "INTENTIONAL_SKIP"])
        result = self._verify_details(bundle)
        self.assertEqual(result.classification, "UNSUPPORTED_POLICY")
        self.assertIn("D4", result.policy_dependencies)

    def test_valid_analysis_is_bound_to_exact_details_and_source_chain(self):
        details = self._details()
        analysis = self._analysis(details)
        result = verifier.verify_generation(
            analysis[0], analysis[1], expected_stage="job_analyzer",
            upstream_manifest_bytes=analysis[3],
            upstream_artifacts_by_role=analysis[4],
            upstream_chain=((details[3], details[4]),),
        )
        self.assertTrue(result.accepted)
        self.assertFalse(result.eligible)

    def test_empty_details_and_analysis_are_explicit_empty_results(self):
        source = self._source([])
        details = self._details(source, descs=[])
        details_result = self._verify_details(details)
        self.assertEqual(details_result.classification, "EMPTY_DATA_ONLY")
        analysis = self._analysis(details)
        result = verifier.verify_generation(
            analysis[0], analysis[1], expected_stage="job_analyzer",
            upstream_manifest_bytes=analysis[3],
            upstream_artifacts_by_role=analysis[4],
            upstream_chain=((details[3], details[4]),),
        )
        self.assertTrue(result.accepted)
        self.assertFalse(result.eligible)
        self.assertEqual(result.classification, "EMPTY_DATA_ONLY")

    def test_missing_manifest_fields_reject(self):
        bundle = self._details()
        manifest = json.loads(bundle[0])
        del manifest["producer"]
        self.assertEqual(verifier.verify_generation(_encode(manifest), bundle[1]).failure_code,
                         "MALFORMED_MANIFEST")

    def test_unexpected_manifest_field_rejects(self):
        bundle = self._details()
        manifest = json.loads(bundle[0])
        manifest["unapproved_field"] = True
        self.assertEqual(verifier.verify_generation(_encode(manifest), bundle[1]).failure_code,
                         "MALFORMED_MANIFEST")

    def test_invalid_manifest_input_type_rejects(self):
        self.assertEqual(verifier.verify_generation("not-bytes", {}).failure_code,
                         "MALFORMED_MANIFEST")

    def test_invalid_artifact_mapping_type_rejects(self):
        bundle = self._details()
        result = self._verify_details((bundle[0], None, *bundle[2:]))
        self.assertEqual(result.failure_code, "MALFORMED_ARTIFACT_INPUT")

    def test_bool_and_negative_counts_reject(self):
        bundle = self._details()
        for value in (True, -1):
            manifest = json.loads(bundle[0])
            manifest["accounting"]["source_occurrences"] = value
            result = self._verify_details((_encode(manifest), bundle[1], *bundle[2:]))
            self.assertEqual(result.failure_code, "ACCOUNTING_INVALID")

    def test_wrong_stage_status_and_identifier_types_reject(self):
        bundle = self._details()
        for field, value, expected in (
            ("stage", [], "UNSUPPORTED_STAGE"),
            ("status", {}, "UNSUPPORTED_STATUS"),
            ("run_id", 12, "INVALID_RUN_ID"),
        ):
            manifest = json.loads(bundle[0])
            manifest[field] = value
            result = self._verify_details((_encode(manifest), bundle[1], *bundle[2:]))
            self.assertEqual(result.failure_code, expected)

    def test_invalid_encoding_rejects(self):
        bundle = self._source([])
        data = self._bytes("invalid-encoding.csv", b"\xff\xfe")
        manifest = copy.deepcopy(bundle[2])
        manifest["source"].update(_fp(data))
        manifest["outputs"]["jobs_csv"].update(_fp(data))
        result = verifier.verify_generation(_encode(manifest), {"jobs_csv": data})
        self.assertEqual(result.failure_code, "ARTIFACT_SCHEMA_INVALID")

    def test_truncated_csv_rejects_even_when_fingerprint_is_updated(self):
        bundle = self._details()
        manifest = json.loads(bundle[0])
        data = self._bytes("truncated.csv", DETAILS_HEADER.encode() + b'"Backend","Company')
        manifest["outputs"]["details_csv"].update(_fp(data))
        result = self._verify_details((_encode(manifest), {
            **bundle[1], "details_csv": data,
        }, *bundle[2:]))
        self.assertEqual(result.failure_code, "ARTIFACT_SCHEMA_INVALID")

    def test_csv_row_width_mismatch_rejects(self):
        bundle = self._details()
        manifest = json.loads(bundle[0])
        data = self._bytes("wrong-width.csv", DETAILS_HEADER.encode() + b'"only","two"\n')
        manifest["outputs"]["details_csv"].update(_fp(data))
        result = self._verify_details((_encode(manifest), {
            **bundle[1], "details_csv": data,
        }, *bundle[2:]))
        self.assertEqual(result.failure_code, "ARTIFACT_SCHEMA_INVALID")

    def test_diagnostics_json_must_be_a_list(self):
        bundle = self._details()
        manifest = json.loads(bundle[0])
        data = self._bytes("diagnostics-object.json", b"{}")
        manifest["outputs"]["diagnostics_json"].update(_fp(data))
        manifest["outputs"]["diagnostics_json"]["record_count"] = 0
        result = self._verify_details((_encode(manifest), {
            **bundle[1], "diagnostics_json": data,
        }, *bundle[2:]))
        self.assertEqual(result.failure_code, "ARTIFACT_SCHEMA_INVALID")

    def test_wrong_empty_claim_is_rejected(self):
        source = self._source([])
        manifest = copy.deepcopy(source[2])
        manifest["status"] = "COMPLETE"
        result = verifier.verify_generation(_encode(manifest), source[1])
        self.assertEqual(result.failure_code, "STATUS_CONTRADICTION")

    def test_missing_upstream_is_incomplete_not_verified(self):
        bundle = self._details()
        result = verifier.verify_generation(bundle[0], bundle[1], expected_stage="job_details")
        self.assertEqual(result.classification, "INCOMPLETE")
        self.assertFalse(result.accepted)

    def test_missing_diagnostic_reference_remains_policy_blocked(self):
        source = self._source([
            "Backend,Example,Bengaluru,Yes,No,https://example.test/1\n",
            "Backend,Example,Bengaluru,Yes,No,https://example.test/2\n",
        ])
        bundle = self._details(source, dispositions=["PROCESSED", "FAILED"])
        # Phase 102 does not define a diagnostic-reference schema. Failure
        # evidence therefore remains policy-blocked instead of being inferred.
        result = self._verify_details(bundle)
        self.assertEqual(result.classification, "UNSUPPORTED_POLICY")
        self.assertIn("D7", result.policy_dependencies)
        self.assertFalse(result.eligible)

    def test_validation_failure_precedence_is_deterministic(self):
        bundle = self._details()
        manifest = json.loads(bundle[0])
        manifest["schema_version"] = 99
        manifest["outputs"] = {}
        results = [verifier.verify_generation(_encode(manifest), {}) for _ in range(3)]
        self.assertEqual([r.failure_code for r in results], ["UNKNOWN_SCHEMA_VERSION"] * 3)
        self.assertTrue(all(not r.accepted and not r.eligible for r in results))

    def test_size_error_precedes_hash_error_deterministically(self):
        bundle = self._details()
        manifest = json.loads(bundle[0])
        manifest["outputs"]["details_csv"]["size_bytes"] += 2
        manifest["outputs"]["details_csv"]["sha256"] = "0" * 64
        result = self._verify_details((_encode(manifest), bundle[1], *bundle[2:]))
        self.assertEqual(result.failure_code, "ARTIFACT_SIZE_MISMATCH")

    def test_unexpected_internal_exception_becomes_stable_failure(self):
        with patch.object(verifier, "_manifest_result", side_effect=RuntimeError("boom")):
            result = verifier.verify_generation(b"{}", {})
        self.assertEqual(result.failure_code, "INTERNAL_VALIDATION_ERROR")
        self.assertFalse(result.accepted)
        self.assertFalse(result.eligible)

    def test_invalid_source_parent_manifest_is_not_trusted_by_hash_alone(self):
        bundle = self._details()
        source_manifest = json.loads(bundle[3])
        source_manifest["schema_version"] = 99
        source_bytes = _encode(source_manifest)
        details_manifest = json.loads(bundle[0])
        details_manifest["input_generation"]["manifest_sha256"] = hashlib.sha256(source_bytes).hexdigest()
        result = self._verify_details((
            _encode(details_manifest), bundle[1], bundle[2], source_bytes, bundle[4]
        ))
        self.assertEqual(result.failure_code, "UNKNOWN_SCHEMA_VERSION")

    def test_invalid_details_parent_manifest_is_not_trusted_by_hash_alone(self):
        details = self._details()
        analysis = self._analysis(details)
        bad_details = json.loads(analysis[3])
        bad_details["schema_version"] = 99
        bad_details_bytes = _encode(bad_details)
        analysis_manifest = json.loads(analysis[0])
        analysis_manifest["input_generation"]["manifest_sha256"] = hashlib.sha256(bad_details_bytes).hexdigest()
        result = verifier.verify_generation(
            _encode(analysis_manifest), analysis[1], expected_stage="job_analyzer",
            upstream_manifest_bytes=bad_details_bytes,
            upstream_artifacts_by_role=analysis[4],
            upstream_chain=((details[3], details[4]),),
        )
        self.assertEqual(result.failure_code, "UNKNOWN_SCHEMA_VERSION")

    def test_failure_code_is_stable_for_repeated_malformed_input(self):
        raw = b'{"schema_version":1,'
        results = [verifier.verify_generation(raw, {}) for _ in range(5)]
        self.assertEqual({result.failure_code for result in results}, {"MALFORMED_MANIFEST"})
        self.assertTrue(all(not result.accepted and not result.eligible for result in results))

    def test_in_progress_rejects_malformed_artifact_mapping(self):
        bundle = self._details()
        manifest = json.loads(bundle[0])
        manifest.update({
            "status": "IN_PROGRESS", "completed_at": None, "source": None,
            "accounting": None, "occurrences": None, "outputs": {},
        })
        result = verifier.verify_generation(_encode(manifest), {"details_csv": object()})
        self.assertEqual(result.failure_code, "MALFORMED_ARTIFACT_INPUT")
        self.assertFalse(result.accepted)

    def test_optional_occurrence_fields_must_have_valid_types(self):
        for field in ("quality_code", "retained_occurrence_key"):
            bundle = self._details()
            manifest = json.loads(bundle[0])
            manifest["occurrences"][0][field] = ["not", "text"]
            result = self._verify_details((_encode(manifest), bundle[1], *bundle[2:]))
            self.assertEqual(result.failure_code, "OCCURRENCE_INVALID")
            self.assertFalse(result.accepted)

    def test_occurrence_failure_code_must_be_machine_readable(self):
        source = self._source([
            "Backend,Example,Bengaluru,Yes,No,https://example.test/1\n",
            "Backend,Example,Bengaluru,Yes,No,https://example.test/2\n",
        ])
        bundle = self._details(source, dispositions=["PROCESSED", "FAILED"])
        manifest = json.loads(bundle[0])
        manifest["occurrences"][1]["error_code"] = "extraction failed"
        result = self._verify_details((_encode(manifest), bundle[1], *bundle[2:]))
        self.assertEqual(result.failure_code, "OCCURRENCE_INVALID")
        self.assertFalse(result.accepted)

    def test_invalid_selection_argument_returns_structured_rejection(self):
        result = verifier.verify_selection(None)
        self.assertEqual(result.failure_code, "SELECTION_INPUT_INVALID")
        self.assertFalse(result.accepted)
        self.assertFalse(result.eligible)


if __name__ == "__main__":
    unittest.main()

