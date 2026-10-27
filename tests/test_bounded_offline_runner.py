"""Synthetic, bounded tests for the offline unittest runner."""

import os
import json
import io
import contextlib
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

import run_offline_tests as runner


class BoundedOfflineRunnerTests(unittest.TestCase):
    def test_success_summary_and_skipped_count_are_parsed(self):
        summary = runner.parse_unittest_summary(
            "",
            "Ran 3 tests in 0.010s\r\n\r\nOK (skipped=1)\r\n",
        )
        self.assertEqual(
            summary,
            {
                "complete": True,
                "tests_run": 3,
                "passed": 2,
                "failures": 0,
                "errors": 0,
                "skipped": 1,
                "outcome": "OK",
            },
        )
        self.assertEqual(
            runner.classify_module_result(exit_code=0, timed_out=False, summary=summary),
            ("PASS", []),
        )

    def test_failure_summary_and_nonzero_exit_are_failures(self):
        summary = runner.parse_unittest_summary(
            "Ran 4 tests in 0.010s\nFAILED (failures=1, errors=1, skipped=1)\n",
            "",
        )
        self.assertEqual((summary["tests_run"], summary["passed"]), (4, 1))
        self.assertEqual((summary["failures"], summary["errors"], summary["skipped"]), (1, 1, 1))
        status, _ = runner.classify_module_result(exit_code=1, timed_out=False, summary=summary)
        self.assertEqual(status, "FAIL")

    def test_complete_zero_test_summary_is_a_failure(self):
        summary = runner.parse_unittest_summary("", "Ran 0 tests in 0.000s\n\nOK\n")
        self.assertTrue(summary["complete"])
        self.assertEqual(summary["tests_run"], 0)
        status, reasons = runner.classify_module_result(
            exit_code=0, timed_out=False, summary=summary
        )
        self.assertEqual(status, "FAIL")
        self.assertEqual(reasons, ["no tests were discovered"])

    def test_exit_without_final_summary_is_incomplete(self):
        summary = runner.parse_unittest_summary("test_one ... ok\n", "")
        self.assertFalse(summary["complete"])
        self.assertEqual(
            runner.classify_module_result(exit_code=0, timed_out=False, summary=summary)[0],
            "INCOMPLETE",
        )

    def test_subprocess_start_failure_is_a_reported_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = runner.execute_command(
                ["missing-python-executable"],
                cwd=root,
                timeout_seconds=1,
                stdout_path=root / "stdout.bin",
                stderr_path=root / "stderr.bin",
                popen_factory=Mock(side_effect=FileNotFoundError("synthetic executable missing")),
            )

        self.assertFalse(result["started"])
        self.assertIn("synthetic executable missing", result["start_error"])
        summary = runner.parse_unittest_summary("", "")
        status, reasons = runner.classify_module_result(
            exit_code=result["exit_code"],
            timed_out=result["timed_out"],
            summary=summary,
            start_error=result["start_error"],
        )
        self.assertEqual(status, "FAIL")
        self.assertTrue(any("could not start" in reason for reason in reasons))

    def test_subprocess_start_failure_is_aggregated_in_module_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            project = base / "project"
            tests = project / "tests"
            tests.mkdir(parents=True)
            (tests / "test_bounded_offline_runner.py").write_text("", encoding="utf-8")

            def failed_executor(command, *, stdout_path, stderr_path, **_kwargs):
                stdout_path.write_bytes(b"")
                stderr_path.write_bytes(b"synthetic permission denied")
                return {
                    "started": False,
                    "exit_code": None,
                    "timed_out": False,
                    "timeout_status": None,
                    "termination": None,
                    "start_error": "synthetic permission denied",
                    "elapsed_seconds": 0.0,
                    "not_started_reason": None,
                }

            report = runner.run_modules(
                ["test_bounded_offline_runner"],
                python_executable=sys.executable,
                timeout_seconds=1,
                report_root=base / "reports",
                project_root=project,
                executor=failed_executor,
            )

        module = report["modules"][0]
        self.assertEqual(module["status"], "FAIL")
        self.assertTrue(any("could not start" in reason for reason in module["reasons"]))
        self.assertEqual(module["stderr_excerpt"], "synthetic permission denied")
        self.assertEqual(report["module_totals"]["executed"], 0)
        self.assertEqual(report["module_totals"]["failed"], 1)
        self.assertEqual(report["overall_status"], "FAIL")

    def test_nonzero_process_exit_overrides_an_ok_unittest_summary(self):
        summary = runner.parse_unittest_summary("", "Ran 2 tests in 0.010s\n\nOK\n")
        status, reasons = runner.classify_module_result(
            exit_code=7, timed_out=False, summary=summary
        )
        self.assertEqual(status, "FAIL")
        self.assertIn("process exited with code 7", reasons)

    def test_keyboard_interrupt_terminates_process_and_reports_runner_interruption(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            process = Mock()
            process.wait.side_effect = [KeyboardInterrupt(), -2]
            process.returncode = -2
            terminator = Mock(return_value={"succeeded": True, "method": "synthetic", "detail": "terminated"})

            result = runner.execute_command(
                [sys.executable, "-c", "pass"],
                cwd=root,
                timeout_seconds=1,
                stdout_path=root / "stdout.bin",
                stderr_path=root / "stderr.bin",
                popen_factory=Mock(return_value=process),
                terminator=terminator,
            )

        self.assertTrue(result["started"])
        self.assertTrue(result["timed_out"])
        self.assertEqual(result["timeout_status"], "runner_interrupted")
        self.assertEqual(result["termination"]["method"], "synthetic")
        self.assertEqual(result["exit_code"], -2)
        terminator.assert_called_once_with(process)

    def test_timeout_values_must_be_positive_and_finite(self):
        for value in (0, -1, "nan", "inf", "invalid"):
            with self.subTest(value=value), self.assertRaises(runner.RunnerArgumentError):
                runner.positive_seconds(value)
        self.assertEqual(runner.positive_seconds("0.25"), 0.25)

    def test_unknown_excluded_path_and_duplicate_modules_are_rejected(self):
        for module in (
            "test_not_allowlisted",
            "test_search_page_evidence",
            "tests/test_pipeline_generation_store.py",
            "tests.test_pipeline_generation_store",
        ):
            with self.subTest(module=module), self.assertRaises(runner.RunnerArgumentError):
                runner.validate_modules([module])
        with self.assertRaises(runner.RunnerArgumentError):
            runner.validate_modules(["test_pipeline_generation_store", "test_pipeline_generation_store.py"])

    def test_command_uses_exact_module_pattern_without_a_shell(self):
        command = runner.build_unittest_command("python312", "test_pipeline_generation_store.py")
        self.assertEqual(
            command,
            ["python312", "-B", "-m", "unittest", "discover", "-s", "tests", "-p", "test_pipeline_generation_store.py", "-v"],
        )

    def test_per_module_timeout_terminates_launched_process_and_keeps_partial_logs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = runner.execute_command(
                [sys.executable, "-c", "import sys,time; print('partial-out',flush=True); print('partial-err',file=sys.stderr,flush=True); time.sleep(20)"],
                cwd=root,
                timeout_seconds=0.25,
                stdout_path=root / "stdout.bin",
                stderr_path=root / "stderr.bin",
            )
            self.assertTrue(result["timed_out"])
            self.assertEqual(result["timeout_status"], "per_module_timeout")
            self.assertTrue(result["termination"]["succeeded"], result["termination"])
            self.assertIn(b"partial-out", (root / "stdout.bin").read_bytes())
            self.assertIn(b"partial-err", (root / "stderr.bin").read_bytes())

    def test_termination_targets_runner_tree_and_leaves_unrelated_process_alive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            child_marker = root / "runner-child-survived.txt"
            unrelated_marker = root / "unrelated-process-finished.txt"
            child_code = (
                "import pathlib,sys,time; time.sleep(0.8); "
                "pathlib.Path(sys.argv[1]).write_text('survived')"
            )
            parent_code = (
                "import subprocess,sys,time; "
                "subprocess.Popen([sys.executable,'-c',sys.argv[2],sys.argv[1]]); "
                "time.sleep(20)"
            )
            unrelated_code = (
                "import pathlib,sys,time; time.sleep(0.8); "
                "pathlib.Path(sys.argv[1]).write_text('alive')"
            )
            unrelated = subprocess.Popen(
                [sys.executable, "-c", unrelated_code, str(unrelated_marker)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            try:
                result = runner.execute_command(
                    [sys.executable, "-c", parent_code, str(child_marker), child_code],
                    cwd=root,
                    timeout_seconds=0.25,
                    stdout_path=root / "stdout.bin",
                    stderr_path=root / "stderr.bin",
                )
                self.assertTrue(result["timed_out"])
                self.assertTrue(result["termination"]["succeeded"], result["termination"])
                unrelated.wait(timeout=3)
                self.assertEqual(unrelated.returncode, 0)
                self.assertTrue(unrelated_marker.exists(), "unrelated process was killed or did not finish")
                time.sleep(0.9)
                self.assertFalse(child_marker.exists(), "runner-launched child survived tree termination")
            finally:
                if unrelated.poll() is None:
                    unrelated.terminate()
                    unrelated.wait(timeout=2)

    def test_termination_failure_is_explicit_and_process_exit_is_observed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            failure = {"succeeded": False, "method": "injected", "detail": "synthetic termination failure"}
            result = runner.execute_command(
                [sys.executable, "-c", "import time; time.sleep(0.35)"],
                cwd=root,
                timeout_seconds=0.05,
                stdout_path=root / "stdout.bin",
                stderr_path=root / "stderr.bin",
                terminator=Mock(return_value=failure),
            )
            self.assertTrue(result["timed_out"])
            self.assertEqual(result["termination"], failure)
            self.assertIsNotNone(result["exit_code"], "runner should observe the synthetic child exit")

    def test_report_creation_is_unique_and_overall_deadline_marks_unrun_modules(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            project = base / "project"
            (project / "tests").mkdir(parents=True)
            (project / "tests" / "test_bounded_offline_runner.py").write_text("", encoding="utf-8")
            report_root = base / "reports"
            executor = Mock()
            first = runner.run_modules(
                ["test_bounded_offline_runner"],
                python_executable=sys.executable,
                timeout_seconds=1,
                overall_timeout_seconds=0.000000000001,
                report_root=report_root,
                project_root=project,
                executor=executor,
            )
            second = runner.run_modules(
                ["test_bounded_offline_runner"],
                python_executable=sys.executable,
                timeout_seconds=1,
                overall_timeout_seconds=0.000000000001,
                report_root=report_root,
                project_root=project,
                executor=executor,
            )
            self.assertNotEqual(first["run_id"], second["run_id"])
            self.assertTrue(Path(first["report_file"]).is_file())
            self.assertTrue(Path(second["report_file"]).is_file())
            self.assertEqual(first["overall_status"], "INCOMPLETE")
            self.assertEqual(first["module_totals"]["not_completed"], 1)
            self.assertEqual(len(list(report_root.iterdir())), 2)
            executor.assert_not_called()

    def test_completed_report_captures_counts_command_and_log_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            project = base / "project"
            tests = project / "tests"
            tests.mkdir(parents=True)
            (tests / "test_bounded_offline_runner.py").write_text("", encoding="utf-8")

            def synthetic_executor(command, *, stdout_path, stderr_path, **_kwargs):
                stdout_path.write_bytes(b"synthetic stdout\n")
                stderr_path.write_bytes(b"Ran 2 tests in 0.010s\n\nOK (skipped=1)\n")
                return {
                    "started": True,
                    "exit_code": 0,
                    "timed_out": False,
                    "timeout_status": None,
                    "termination": None,
                    "start_error": None,
                    "elapsed_seconds": 0.01,
                    "not_started_reason": None,
                }

            report = runner.run_modules(
                ["test_bounded_offline_runner"],
                python_executable=sys.executable,
                timeout_seconds=1,
                report_root=base / "reports",
                project_root=project,
                executor=synthetic_executor,
            )
            module = report["modules"][0]
            self.assertEqual(report["overall_status"], "PASS")
            self.assertEqual(report["test_totals"]["skipped"], 1)
            self.assertEqual(report["module_totals"]["skipped"], 1)
            self.assertEqual(report["module_totals"]["errored"], 0)
            self.assertEqual(module["stdout_bytes"], len(b"synthetic stdout\n"))
            self.assertEqual(module["stderr_bytes"], len(b"Ran 2 tests in 0.010s\n\nOK (skipped=1)\n"))
            self.assertEqual(module["command_argv"][1:3], ["-B", "-m"])
            self.assertEqual((Path(report["report_directory"]) / module["stdout_file"]).read_bytes(), b"synthetic stdout\n")
            self.assertEqual(
                report["runner_source_sha256"],
                __import__("hashlib").sha256(Path(runner.__file__).read_bytes()).hexdigest(),
            )
            self.assertTrue(Path(report["report_file"]).is_file())

    def test_timeout_and_termination_details_are_preserved_in_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            project = base / "project"
            tests = project / "tests"
            tests.mkdir(parents=True)
            (tests / "test_bounded_offline_runner.py").write_text("", encoding="utf-8")
            termination = {
                "succeeded": False,
                "method": "synthetic terminator",
                "detail": "synthetic child remained alive",
            }

            def timed_out_executor(command, *, stdout_path, stderr_path, **_kwargs):
                stdout_path.write_bytes(b"partial output\n")
                stderr_path.write_bytes(b"partial error\n")
                return {
                    "started": True,
                    "exit_code": None,
                    "timed_out": True,
                    "timeout_status": "per_module_timeout",
                    "termination": termination,
                    "start_error": None,
                    "elapsed_seconds": 1.0,
                    "not_started_reason": None,
                }

            report = runner.run_modules(
                ["test_bounded_offline_runner"],
                python_executable=sys.executable,
                timeout_seconds=1,
                report_root=base / "reports",
                project_root=project,
                executor=timed_out_executor,
            )
            module = report["modules"][0]
            self.assertEqual(module["status"], "TIMED_OUT")
            self.assertEqual(module["timeout_status"], "per_module_timeout")
            self.assertEqual(module["termination"], termination)
            self.assertEqual(module["stdout_excerpt"], "partial output")
            self.assertEqual(module["stderr_excerpt"], "partial error")
            self.assertEqual(report["overall_status"], "INCOMPLETE")
            self.assertTrue(Path(report["report_file"]).is_file())

    def test_incomplete_unittest_summary_is_incomplete_in_module_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            project = base / "project"
            tests = project / "tests"
            tests.mkdir(parents=True)
            (tests / "test_bounded_offline_runner.py").write_text("", encoding="utf-8")

            def incomplete_executor(command, *, stdout_path, stderr_path, **_kwargs):
                stdout_path.write_bytes(b"test_one ... ok\n")
                stderr_path.write_bytes(b"")
                return {
                    "started": True,
                    "exit_code": 0,
                    "timed_out": False,
                    "timeout_status": None,
                    "termination": None,
                    "start_error": None,
                    "elapsed_seconds": 0.01,
                    "not_started_reason": None,
                }

            report = runner.run_modules(
                ["test_bounded_offline_runner"],
                python_executable=sys.executable,
                timeout_seconds=1,
                report_root=base / "reports",
                project_root=project,
                executor=incomplete_executor,
            )

        module = report["modules"][0]
        self.assertEqual(module["status"], "INCOMPLETE")
        self.assertEqual(module["summary_status"], "absent_or_incomplete")
        self.assertFalse(module["counts"]["complete"])
        self.assertEqual(report["module_totals"]["incomplete"], 1)
        self.assertEqual(report["overall_status"], "INCOMPLETE")

    def test_aggregate_counts_failed_and_errored_modules(self):
        report = {
            "requested_modules": ["test_one.py", "test_two.py"],
            "modules": [
                {"started": True, "status": "FAIL", "counts": {"tests_run": 2, "passed": 1, "failures": 0, "errors": 1, "skipped": 0}},
                {"started": True, "status": "FAIL", "counts": {"tests_run": 3, "passed": 2, "failures": 1, "errors": 0, "skipped": 1}},
            ],
            "not_completed": [],
        }
        runner._aggregate(report)
        self.assertEqual(report["module_totals"]["failed"], 2)
        self.assertEqual(report["module_totals"]["errored"], 1)
        self.assertEqual(report["module_totals"]["skipped"], 1)
        self.assertEqual(report["test_totals"], {"tests_run": 5, "passed": 3, "failures": 1, "errors": 1, "skipped": 1})
        self.assertEqual(report["overall_status"], "FAIL")

    def test_report_root_inside_project_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            project.mkdir()
            with self.assertRaises(runner.RunnerArgumentError):
                runner.ensure_report_root(project / "reports", project)


class DiagnosticRedactionTests(unittest.TestCase):
    """Synthetic coverage for the standalone redaction helper only."""

    def test_bearer_credentials_are_redacted_and_context_is_preserved(self):
        from tools.diagnostic_redaction import redact_diagnostic_text

        source = "request failed: Bearer synthetic-bearer-01; retry later"
        result = redact_diagnostic_text(source)
        self.assertNotIn("synthetic-bearer-01", result)
        self.assertIn("Bearer [REDACTED]", result)
        self.assertIn("request failed:", result)
        self.assertIn("retry later", result)

    def test_authorization_and_multiline_cookie_headers_are_redacted(self):
        from tools.diagnostic_redaction import redact_diagnostic_text

        source = (
            "Authorization: Basic synthetic-auth-01\n"
            "Authorization: Token synthetic-token-scheme-01\n"
            "Proxy-Authorization: Digest synthetic-proxy-auth-01\n"
            "Cookie: sessionid=synthetic-session-01;\n"
            "  csrf=synthetic-csrf-01\n"
            "ValueError: response rejected"
        )
        result = redact_diagnostic_text(source)
        for value in ("synthetic-auth-01", "synthetic-token-scheme-01", "synthetic-proxy-auth-01", "synthetic-session-01", "synthetic-csrf-01"):
            self.assertNotIn(value, result)
        self.assertIn("Authorization: [REDACTED]", result)
        self.assertIn("Cookie: [REDACTED]", result)
        self.assertIn("ValueError: response rejected", result)

    def test_session_password_and_api_key_assignments_are_redacted(self):
        from tools.diagnostic_redaction import redact_diagnostic_text

        source = (
            'session_id="synthetic-session-02" password=synthetic-password-01 '
            'api_key=synthetic-api-key-01 X-API-Key: synthetic-header-key-01'
        )
        result = redact_diagnostic_text(source)
        for value in (
            "synthetic-session-02", "synthetic-password-01",
            "synthetic-api-key-01", "synthetic-header-key-01",
        ):
            self.assertNotIn(value, result)
        self.assertGreaterEqual(result.count("[REDACTED]"), 4)

    def test_credentials_embedded_in_exception_text_are_redacted(self):
        from tools.diagnostic_redaction import redact_diagnostic_text

        source = "RuntimeError: API request failed (access_token=synthetic-exception-token-01)"
        result = redact_diagnostic_text(source)
        self.assertNotIn("synthetic-exception-token-01", result)
        self.assertIn("RuntimeError: API request failed", result)

    def test_multiline_malformed_and_invalid_utf8_diagnostics_are_deterministic(self):
        from tools.diagnostic_redaction import redact_diagnostic_text

        source = b"Traceback (most recent call last):\n  password=synthetic-multiline-01\n\xff\napi_key="
        expected = "Traceback (most recent call last):\n  password=[REDACTED]\n\ufffd\napi_key="
        self.assertEqual(redact_diagnostic_text(source), expected)
        self.assertEqual(redact_diagnostic_text(source), expected)

    def test_json_and_environment_credential_formats_are_redacted(self):
        from tools.diagnostic_redaction import redact_diagnostic_text

        source = (
            '{"password": "synthetic-json-password-01", '
            '"client_secret": "synthetic-json-secret-01"}\n'
            'export API_KEY=synthetic-env-key-01\n'
            '$env:SESSION_TOKEN=synthetic-env-session-01'
        )
        result = redact_diagnostic_text(source)
        for value in (
            "synthetic-json-password-01", "synthetic-json-secret-01",
            "synthetic-env-key-01", "synthetic-env-session-01",
        ):
            self.assertNotIn(value, result)
        self.assertIn('"password": "[REDACTED]"', result)
        self.assertIn("export API_KEY=[REDACTED]", result)
        self.assertIn("$env:SESSION_TOKEN=[REDACTED]", result)

    def test_url_query_credentials_are_redacted_without_erasing_other_parameters(self):
        from tools.diagnostic_redaction import redact_diagnostic_text

        source = "GET https://example.invalid/?access_token=synthetic-query-token-01&api_key=synthetic%2Fquery%3Dkey-02&state=keep-me#section"
        result = redact_diagnostic_text(source)
        self.assertNotIn("synthetic-query-token-01", result)
        self.assertNotIn("synthetic%2Fquery%3Dkey-02", result)
        self.assertIn("access_token=[REDACTED]", result)
        self.assertIn("&state=keep-me#section", result)

    def test_indented_multiline_secret_fragments_are_redacted_and_context_is_kept(self):
        from tools.diagnostic_redaction import redact_diagnostic_text

        source = (
            "ValueError: request rejected\n"
            "  API_KEY=synthetic-key-fragment-01\n"
            "    synthetic-key-fragment-02\n"
            "Bearer synthetic-bearer-fragment-01\n"
            "  synthetic-bearer-fragment-02\n"
            "Retry-After: 2 seconds"
        )
        result = redact_diagnostic_text(source)
        for value in (
            "synthetic-key-fragment-01", "synthetic-key-fragment-02",
            "synthetic-bearer-fragment-01", "synthetic-bearer-fragment-02",
        ):
            self.assertNotIn(value, result)
        self.assertIn("ValueError: request rejected", result)
        self.assertIn("Retry-After: 2 seconds", result)
        self.assertEqual(redact_diagnostic_text(source), result)

    def test_nested_json_and_overlapping_secret_names_are_redacted_once(self):
        from tools.diagnostic_redaction import redact_diagnostic_text

        source = (
            '{"outer":{"auth":{"password":"synthetic-nested-password-01",'
            '"session_token":"synthetic-nested-session-01"}},'
            '"items":[{"api_key":"synthetic-nested-key-01"}]}'
        )
        result = redact_diagnostic_text(source)
        for value in (
            "synthetic-nested-password-01", "synthetic-nested-session-01",
            "synthetic-nested-key-01",
        ):
            self.assertNotIn(value, result)
        self.assertIn('"outer":{"auth":{"password":"[REDACTED]"', result)

        overlap = redact_diagnostic_text("https://example.invalid/?access_token=synthetic-overlap-01&state=keep")
        self.assertNotIn("synthetic-overlap-01", overlap)
        self.assertEqual(overlap.count("[REDACTED]"), 1)
        self.assertIn("&state=keep", overlap)

    def test_multiline_exception_trace_redacts_secret_and_preserves_trace_context(self):
        from tools.diagnostic_redaction import redact_diagnostic_text

        source = (
            'Traceback (most recent call last):\n'
            '  File "worker.py", line 8, in request\n'
            '    raise RuntimeError("access_token=synthetic-trace-token-01")\n'
            'RuntimeError: request failed\n'
            '  diagnostic context: retry is safe'
        )
        result = redact_diagnostic_text(source)
        self.assertNotIn("synthetic-trace-token-01", result)
        self.assertIn('File "worker.py", line 8, in request', result)
        self.assertIn("RuntimeError: request failed", result)
        self.assertIn("diagnostic context: retry is safe", result)
    def test_redaction_failure_omits_original_sensitive_diagnostic(self):
        from tools import diagnostic_redaction

        source = "RuntimeError: api_key=synthetic-fail-closed-01"
        broken_redactor = Mock(sub=Mock(side_effect=RuntimeError("synthetic internal error")))
        with patch.object(diagnostic_redaction, "_HEADER", broken_redactor):
            result = diagnostic_redaction.redact_diagnostic_text(source)
        self.assertEqual(result, "<diagnostic omitted: redaction failed>")
        self.assertNotIn("synthetic-fail-closed-01", result)
    def test_unclosed_quoted_credentials_are_redacted_without_losing_later_context(self):
        from tools.diagnostic_redaction import redact_diagnostic_text

        source = (
            'RuntimeError: password="synthetic-unclosed-password-01\n'
            "Bearer 'synthetic-unclosed-bearer-01\n"
            "Retry-After: 2 seconds"
        )
        result = redact_diagnostic_text(source)
        self.assertNotIn("synthetic-unclosed-password-01", result)
        self.assertNotIn("synthetic-unclosed-bearer-01", result)
        self.assertIn('password="[REDACTED]', result)
        self.assertIn("Bearer '[REDACTED]", result)
        self.assertIn("Retry-After: 2 seconds", result)
    def test_non_sensitive_error_details_and_non_text_handling_are_preserved_safely(self):
        from tools.diagnostic_redaction import redact_diagnostic_text

        message = "FileNotFoundError: config.toml not found at /tmp/example"
        self.assertEqual(redact_diagnostic_text(message), message)
        self.assertEqual(redact_diagnostic_text(object()), "<non-text diagnostic>")


class SimulatedDiagnosticSinkTests(unittest.TestCase):
    """Simulated output sinks; these do not invoke or verify the protected runner."""

    def test_simulated_runner_sinks_are_redacted_for_all_terminal_scenarios(self):
        import contextlib
        import io
        import json

        from tools.diagnostic_redaction import redact_diagnostic_text

        scenarios = {
            "success": {
                "stdout": "Ran 2 tests in 0.01s\nOK\nBearer synthetic-success-token-01",
                "stderr": "",
                "start_error": "",
                "termination": "",
            },
            "failure": {
                "stdout": "Ran 2 tests in 0.01s\nFAILED (failures=1)",
                "stderr": '{"password":"synthetic-failure-password-01"}',
                "start_error": "",
                "termination": "",
            },
            "timeout": {
                "stdout": "partial output ?api_key=synthetic-timeout-key-01&keep=yes",
                "stderr": "TimeoutError: operation timed out",
                "start_error": "",
                "termination": "termination failed: session_id=synthetic-timeout-session-01",
            },
            "interruption": {
                "stdout": "partial output",
                "stderr": "KeyboardInterrupt: Cookie: session=synthetic-interrupt-cookie-01",
                "start_error": "",
                "termination": "interrupted while access_token=synthetic-interrupt-token-01",
            },
            "startup_failure": {
                "stdout": "",
                "stderr": "",
                "start_error": "OSError: launch denied api_key=synthetic-start-key-01",
                "termination": "",
            },
        }
        synthetic_values = (
            "synthetic-success-token-01", "synthetic-failure-password-01",
            "synthetic-timeout-key-01", "synthetic-timeout-session-01",
            "synthetic-interrupt-cookie-01", "synthetic-interrupt-token-01",
            "synthetic-start-key-01",
        )

        for scenario, raw in scenarios.items():
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                safe_stdout = redact_diagnostic_text(raw["stdout"])
                safe_stderr = redact_diagnostic_text(raw["stderr"])
                report = {
                    "scenario": scenario,
                    "reasons": ["synthetic failure detail"] if scenario == "failure" else [],
                    "stdout_excerpt": "\n".join(safe_stdout.splitlines()[-30:]),
                    "stderr_excerpt": "\n".join(safe_stderr.splitlines()[-30:]),
                    "start_error": redact_diagnostic_text(raw["start_error"]),
                    "termination_detail": redact_diagnostic_text(raw["termination"]),
                    "test_summary": {"tests_run": 2, "passed": 1, "failures": int(scenario == "failure")},
                }
                (root / "stdout.bin").write_bytes(safe_stdout.encode("utf-8"))
                (root / "stderr.bin").write_bytes(safe_stderr.encode("utf-8"))
                report_path = root / "summary.json"
                report_path.write_text(json.dumps(report), encoding="utf-8")
                captured = io.StringIO()
                with contextlib.redirect_stdout(captured):
                    print(report["scenario"], report["start_error"], report["termination_detail"], report["reasons"])
                    print(report["stdout_excerpt"], report["stderr_excerpt"])

                sinks = (
                    (root / "stdout.bin").read_text(encoding="utf-8"),
                    (root / "stderr.bin").read_text(encoding="utf-8"),
                    report_path.read_text(encoding="utf-8"),
                    captured.getvalue(),
                )
                for sink in sinks:
                    for value in synthetic_values:
                        self.assertNotIn(value, sink, scenario)
                self.assertIn(scenario, report_path.read_text(encoding="utf-8"))
                self.assertEqual(report["test_summary"]["tests_run"], 2)
                if scenario == "failure":
                    self.assertIn("synthetic failure detail", report["reasons"])
                if scenario == "timeout":
                    self.assertIn("keep=yes", report["stdout_excerpt"])
                if scenario == "startup_failure":
                    self.assertIn("launch denied", report["start_error"])


    def test_simulated_helper_failure_never_falls_back_to_raw_sink_values(self):
        import contextlib
        import io
        import json

        from tools import diagnostic_redaction

        raw = {
            "stdout": "Bearer synthetic-fallback-out-01",
            "stderr": "password=synthetic-fallback-err-01",
            "start_error": "OSError: api_key=synthetic-fallback-start-01",
            "termination": "TimeoutError: session_id=synthetic-fallback-term-01",
        }
        expected_marker = "<diagnostic omitted: redaction failed>"
        synthetic_values = tuple(value.split("=", 1)[-1] for value in raw.values())
        broken_redactor = Mock(sub=Mock(side_effect=RuntimeError("simulated redactor failure")))

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.object(diagnostic_redaction, "_HEADER", broken_redactor):
                safe = {
                    key: diagnostic_redaction.redact_diagnostic_text(value)
                    for key, value in raw.items()
                }
            report = {
                "status": "TIMED_OUT",
                "stdout_excerpt": safe["stdout"],
                "stderr_excerpt": safe["stderr"],
                "start_error": safe["start_error"],
                "termination_detail": safe["termination"],
                "reasons": [expected_marker],
                "test_summary": {"tests_run": 1, "errors": 1},
            }
            (root / "stdout.bin").write_text(safe["stdout"], encoding="utf-8")
            (root / "stderr.bin").write_text(safe["stderr"], encoding="utf-8")
            report_path = root / "summary.json"
            report_path.write_text(json.dumps(report), encoding="utf-8")
            captured = io.StringIO()
            with contextlib.redirect_stdout(captured):
                print(report["status"], report["reasons"], report["start_error"], report["termination_detail"])
                print(report["stdout_excerpt"], report["stderr_excerpt"])

            sinks = (
                (root / "stdout.bin").read_text(encoding="utf-8"),
                (root / "stderr.bin").read_text(encoding="utf-8"),
                report_path.read_text(encoding="utf-8"),
                captured.getvalue(),
            )
            for sink in sinks:
                self.assertIn(expected_marker, sink)
                for value in synthetic_values:
                    self.assertNotIn(value, sink)
            self.assertIn("test_summary", report_path.read_text(encoding="utf-8"))
if __name__ == "__main__":
    unittest.main()
