"""Synthetic, bounded tests for the offline unittest runner."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock

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

    def test_nonzero_process_exit_overrides_an_ok_unittest_summary(self):
        summary = runner.parse_unittest_summary("", "Ran 2 tests in 0.010s\n\nOK\n")
        status, reasons = runner.classify_module_result(
            exit_code=7, timed_out=False, summary=summary
        )
        self.assertEqual(status, "FAIL")
        self.assertIn("process exited with code 7", reasons)

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


if __name__ == "__main__":
    unittest.main()
