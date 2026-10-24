"""Run an explicit allowlist of offline unittest modules with hard bounds.

Each module runs in a separate Python process. Exact stdout/stderr bytes and a
JSON run report are written to a unique directory outside the project by
default. No test discovery across the full suite or application entry point is
performed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_TIMEOUT_SECONDS = 120.0
TERMINATION_OBSERVE_SECONDS = 2.0
WINDOWS_TASKKILL_TIMEOUT_SECONDS = 10.0

EXCLUDED_MODULES = frozenset({
    "test_search_page_evidence",
    "test_offline_search_evidence",
    "test_route_audit_browser_smoke",
})

# Explicitly reviewed offline tests. Browser workflows, application workflows,
# and filesystem evidence readers are not in this set. Review behavior before
# adding any module.
ALLOWED_MODULES = frozenset({
    "test_analysis_freshness",
    "test_application_form_navigation",
    "test_application_form_policy",
    "test_application_form_sdui_and_review_diagnostics",
    "test_application_route_classification",
    "test_application_step_progress",
    "test_atomic_status_writes",
    "test_bounded_offline_runner",
    "test_collection_diagnostics_adapter",
    "test_collection_evidence_policy_spec",
    "test_collection_run_evidence",
    "test_csv_output_durability",
    "test_csv_contracts",
    "test_daily_application_limit",
    "test_description_quality",
    "test_dom_evidence_package",
    "test_easy_apply_identity",
    "test_easy_apply_sdui_detection",
    "test_external_form_detection",
    "test_final_page_safety_cases",
    "test_job_collection_completeness",
    "test_job_details_extraction",
    "test_job_scraper_publication",
    "test_offline_pipeline_demo",
    "test_offline_provenance_verifier",
    "test_offline_generation_lifecycle",
    "test_manifest_contract_compat",
    "test_offline_generation_contract_integration",
    "test_provenance_manifest_schema",
    "test_provenance_schema_differential",
    "test_pipeline_generation_store",
    "test_skill_matcher",
})

_RUN_RE = re.compile(r"^Ran\s+(\d+)\s+tests?\s+in\s+.+$", re.MULTILINE)
_OUTCOME_RE = re.compile(r"^(OK(?:\s*\((.*?)\))?|FAILED(?:\s*\((.*?)\))?)$", re.MULTILINE)
_COUNT_RE = re.compile(r"(failures|errors|skipped)=(\d+)")


class RunnerArgumentError(ValueError):
    """An invalid allowlist selection or runner option."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def positive_seconds(value: Any, label: str = "timeout") -> float:
    try:
        seconds = float(value)
    except (TypeError, ValueError) as exc:
        raise RunnerArgumentError(f"{label} must be a positive finite number") from exc
    if not math.isfinite(seconds) or seconds <= 0:
        raise RunnerArgumentError(f"{label} must be a positive finite number")
    return seconds


def normalize_module_name(value: str) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise RunnerArgumentError("module name must be a non-empty exact allowlist name")
    name = value[:-3] if value.endswith(".py") else value
    if not name or any(char in name for char in ("/", "\\", ".")):
        raise RunnerArgumentError("use a test module name, not a path or dotted import")
    if name in EXCLUDED_MODULES:
        raise RunnerArgumentError(f"module is explicitly excluded: {name}.py")
    if name not in ALLOWED_MODULES:
        raise RunnerArgumentError(f"module is not allowlisted: {name}.py")
    return name


def validate_modules(modules: list[str] | tuple[str, ...]) -> list[str]:
    if isinstance(modules, (str, bytes)) or not modules:
        raise RunnerArgumentError("select at least one explicitly allowlisted module")
    selected = [normalize_module_name(module) for module in modules]
    if len(set(selected)) != len(selected):
        raise RunnerArgumentError("duplicate module selection is not allowed")
    return selected


def resolve_python_executable(value: str | os.PathLike[str] | None) -> str:
    requested = os.fspath(value) if value is not None else sys.executable
    candidate = Path(requested).expanduser()
    if candidate.is_absolute() or candidate.parent != Path("."):
        resolved = candidate.resolve()
        if not resolved.is_file():
            raise RunnerArgumentError(f"Python executable does not exist: {requested}")
        return str(resolved)
    found = shutil.which(requested)
    if not found:
        raise RunnerArgumentError(f"Python executable was not found: {requested}")
    return str(Path(found).resolve())


def ensure_report_root(report_root: str | os.PathLike[str] | None, project_root: Path) -> Path:
    root = (
        Path(report_root).expanduser().resolve()
        if report_root is not None
        else (Path(tempfile.gettempdir()) / "ai-job-automation-test-runs").resolve()
    )
    project = project_root.resolve()
    try:
        root.relative_to(project)
    except ValueError:
        pass
    else:
        raise RunnerArgumentError("report root must be outside the project tree")
    root.mkdir(parents=True, exist_ok=True)
    if not root.is_dir():
        raise RunnerArgumentError(f"report root is not a directory: {root}")
    return root


def create_run_directory(report_root: Path) -> tuple[str, Path]:
    for _ in range(10):
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid.uuid4().hex
        run_dir = report_root / run_id
        try:
            run_dir.mkdir(exist_ok=False)
        except FileExistsError:
            continue
        return run_id, run_dir
    raise OSError("could not create a unique test report directory")


def build_unittest_command(python_executable: str, module: str) -> list[str]:
    module = normalize_module_name(module)
    return [python_executable, "-B", "-m", "unittest", "discover", "-s", "tests", "-p", f"{module}.py", "-v"]


def parse_unittest_summary(stdout: str, stderr: str) -> dict[str, Any]:
    combined = f"{stdout}\n{stderr}".replace("\r\n", "\n").replace("\r", "\n")
    run_matches = list(_RUN_RE.finditer(combined))
    outcomes = list(_OUTCOME_RE.finditer(combined))
    empty = {
        "complete": False,
        "tests_run": None,
        "passed": None,
        "failures": None,
        "errors": None,
        "skipped": None,
        "outcome": None,
    }
    if not run_matches or not outcomes:
        return empty
    run_match, outcome_match = run_matches[-1], outcomes[-1]
    if outcome_match.start() < run_match.end():
        return empty
    tests_run = int(run_match.group(1))
    outcome = "FAILED" if outcome_match.group(1).startswith("FAILED") else "OK"
    count_text = outcome_match.group(2) or outcome_match.group(3) or ""
    counts = {name: 0 for name in ("failures", "errors", "skipped")}
    counts.update({name: int(value) for name, value in _COUNT_RE.findall(count_text)})
    passed = max(0, tests_run - counts["failures"] - counts["errors"] - counts["skipped"])
    return {
        "complete": True,
        "tests_run": tests_run,
        "passed": passed,
        "failures": counts["failures"],
        "errors": counts["errors"],
        "skipped": counts["skipped"],
        "outcome": outcome,
    }


def classify_module_result(*, exit_code: int | None, timed_out: bool, summary: dict[str, Any], start_error: str | None = None) -> tuple[str, list[str]]:
    if timed_out:
        return "TIMED_OUT", ["process exceeded its configured time bound"]
    reasons = []
    if start_error:
        reasons.append(f"process could not start: {start_error}")
    if exit_code not in (0, None):
        reasons.append(f"process exited with code {exit_code}")
    if summary.get("outcome") == "FAILED" or (summary.get("failures") or 0) or (summary.get("errors") or 0):
        reasons.append("unittest reported failures or errors")
    if reasons:
        return "FAIL", reasons
    if not summary.get("complete"):
        return "INCOMPLETE", ["final unittest summary is absent or incomplete"]
    if summary.get("tests_run", 0) == 0:
        return "FAIL", ["no tests were discovered"]
    return "PASS", []


def _process_options() -> dict[str, Any]:
    return ({"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)}
            if os.name == "nt" else {"start_new_session": True})


def terminate_process_tree(process: subprocess.Popen[Any]) -> dict[str, Any]:
    """Terminate only the process tree created for this module invocation."""
    if process.poll() is not None:
        return {"succeeded": True, "method": "already_exited", "detail": "process already exited"}
    if os.name == "nt":
        # CREATE_NEW_PROCESS_GROUP gives this runner-owned process tree a
        # dedicated Ctrl-Break target. Prefer it because it needs no elevated
        # taskkill access and does not address unrelated developer processes.
        try:
            process.send_signal(signal.CTRL_BREAK_EVENT)
            try:
                process.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                pass
            if process.poll() is not None:
                return {
                    "succeeded": True,
                    "method": "CTRL_BREAK_EVENT to runner-created process group",
                    "detail": "launched process group exited",
                }
        except (OSError, AttributeError, ValueError) as exc:
            ctrl_break_error = str(exc)
        else:
            ctrl_break_error = "process group did not exit after CTRL_BREAK_EVENT"
        taskkill = shutil.which("taskkill")
        if not taskkill:
            return {"succeeded": False, "method": "CTRL_BREAK_EVENT / taskkill", "detail": f"{ctrl_break_error}; taskkill was not found"}
        command = [taskkill, "/PID", str(process.pid), "/T", "/F"]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=WINDOWS_TASKKILL_TIMEOUT_SECONDS, check=False, shell=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {"succeeded": False, "method": "CTRL_BREAK_EVENT / taskkill /T /F", "detail": f"{ctrl_break_error}; {exc}"}
        try:
            process.wait(timeout=TERMINATION_OBSERVE_SECONDS)
        except subprocess.TimeoutExpired:
            pass
        success = process.poll() is not None and result.returncode == 0
        detail = (result.stderr or result.stdout or "").strip()
        return {
            "succeeded": success,
            "method": "CTRL_BREAK_EVENT / taskkill /PID <launched-pid> /T /F",
            "detail": detail or ("process tree exited" if success else f"{ctrl_break_error}; taskkill exit code {result.returncode}"),
        }

    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return {"succeeded": True, "method": "process-group SIGTERM", "detail": "process group already exited"}
    except OSError as exc:
        return {"succeeded": False, "method": "process-group SIGTERM", "detail": str(exc)}
    try:
        process.wait(timeout=0.5)
    except subprocess.TimeoutExpired:
        pass
    try:
        # Only the process group created with start_new_session=True is targeted.
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except OSError as exc:
        return {"succeeded": False, "method": "process-group SIGTERM/SIGKILL", "detail": str(exc)}
    try:
        process.wait(timeout=TERMINATION_OBSERVE_SECONDS)
    except subprocess.TimeoutExpired:
        return {"succeeded": False, "method": "process-group SIGTERM/SIGKILL", "detail": "launched process did not exit"}
    return {"succeeded": True, "method": "process-group SIGTERM/SIGKILL", "detail": "launched process group terminated"}


def execute_command(command: list[str], *, cwd: Path, timeout_seconds: float, stdout_path: Path, stderr_path: Path, overall_deadline: float | None = None, popen_factory: Any = subprocess.Popen, terminator: Any = terminate_process_tree) -> dict[str, Any]:
    timeout_seconds = positive_seconds(timeout_seconds, "per-module timeout")
    remaining = None if overall_deadline is None else overall_deadline - time.monotonic()
    if remaining is not None and remaining <= 0:
        return {"started": False, "exit_code": None, "timed_out": False, "timeout_status": None, "termination": None, "start_error": None, "elapsed_seconds": 0.0, "not_started_reason": "overall deadline elapsed before module start"}
    effective_timeout = timeout_seconds if remaining is None else min(timeout_seconds, remaining)
    deadline_kind = "overall_deadline" if remaining is not None and remaining <= timeout_seconds else "per_module_timeout"
    start = time.monotonic()
    process = None
    exit_code = None
    timed_out = False
    termination = None
    start_error = None
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path.parent.mkdir(parents=True, exist_ok=True)
    with stdout_path.open("wb") as stdout_file, stderr_path.open("wb") as stderr_file:
        try:
            process = popen_factory(command, cwd=str(cwd), stdin=subprocess.DEVNULL, stdout=stdout_file, stderr=stderr_file, shell=False, **_process_options())
        except OSError as exc:
            start_error = str(exc)
        else:
            try:
                exit_code = process.wait(timeout=effective_timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                termination = terminator(process)
                if process.poll() is None:
                    try:
                        exit_code = process.wait(timeout=TERMINATION_OBSERVE_SECONDS)
                    except subprocess.TimeoutExpired:
                        exit_code = None
                else:
                    exit_code = process.returncode
            except KeyboardInterrupt:
                timed_out = True
                deadline_kind = "runner_interrupted"
                termination = terminator(process)
                try:
                    exit_code = process.wait(timeout=TERMINATION_OBSERVE_SECONDS)
                except subprocess.TimeoutExpired:
                    exit_code = None
    return {
        "started": process is not None,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "timeout_status": deadline_kind if timed_out else None,
        "termination": termination,
        "start_error": start_error,
        "elapsed_seconds": max(0.0, time.monotonic() - start),
        "not_started_reason": None,
    }


def _read_log(path: Path) -> tuple[str, str]:
    raw = path.read_bytes() if path.exists() else b""
    text = raw.decode("utf-8", errors="replace")
    return text, "\n".join(text.splitlines()[-30:])


def _write_report(path: Path, report: dict[str, Any]) -> None:
    # The run directory itself is exclusive and unique. Rewriting this run's
    # own summary avoids relying on replace semantics in restricted temp dirs.
    mode = "r+b" if path.exists() else "x+b"
    with path.open(mode) as output:
        output.seek(0)
        output.truncate()
        output.write(json.dumps(report, indent=2, ensure_ascii=False).encode("utf-8"))
        output.flush()
        os.fsync(output.fileno())


def _aggregate(report: dict[str, Any]) -> None:
    modules = report["modules"]
    totals = {
        "requested": len(report["requested_modules"]),
        "executed": sum(bool(module.get("started")) for module in modules),
        "passed": sum(module["status"] == "PASS" for module in modules),
        "failed": sum(module["status"] == "FAIL" for module in modules),
        "errored": sum(((module.get("counts") or {}).get("errors") or 0) > 0 for module in modules),
        "skipped": sum(((module.get("counts") or {}).get("skipped") or 0) > 0 for module in modules),
        "incomplete": sum(module["status"] == "INCOMPLETE" for module in modules),
        "timed_out": sum(module["status"] == "TIMED_OUT" for module in modules),
        "not_completed": len(report["not_completed"]),
    }
    report["module_totals"] = totals
    report["test_totals"] = {
        key: sum((module.get("counts") or {}).get(key) or 0 for module in modules)
        for key in ("tests_run", "passed", "failures", "errors", "skipped")
    }
    if totals["failed"]:
        report["overall_status"] = "FAIL"
    elif totals["incomplete"] or totals["timed_out"] or totals["not_completed"]:
        report["overall_status"] = "INCOMPLETE"
    else:
        report["overall_status"] = "PASS"


def run_modules(modules: list[str] | tuple[str, ...], *, python_executable: str | os.PathLike[str] | None = None, timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS, overall_timeout_seconds: float | None = None, report_root: str | os.PathLike[str] | None = None, project_root: Path = PROJECT_ROOT, executor: Any = None) -> dict[str, Any]:
    selected = validate_modules(modules)
    timeout_seconds = positive_seconds(timeout_seconds, "per-module timeout")
    if overall_timeout_seconds is not None:
        overall_timeout_seconds = positive_seconds(overall_timeout_seconds, "overall timeout")
    python_executable = resolve_python_executable(python_executable)
    project_root = Path(project_root).resolve()
    tests_dir = project_root / "tests"
    report_base = ensure_report_root(report_root, project_root)
    run_id, run_dir = create_run_directory(report_base)
    report_path = run_dir / "summary.json"
    started_utc = utc_now()
    started_mono = time.monotonic()
    overall_deadline = None if overall_timeout_seconds is None else started_mono + overall_timeout_seconds
    report: dict[str, Any] = {
        "schema_version": 1,
        "run_id": run_id,
        "overall_status": "INCOMPLETE",
        "started_at": started_utc,
        "ended_at": None,
        "elapsed_seconds": None,
        "project_root": str(project_root),
        "python_executable": python_executable,
        "runner_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "per_module_timeout_seconds": timeout_seconds,
        "overall_timeout_seconds": overall_timeout_seconds,
        "allowlist": sorted(ALLOWED_MODULES),
        "excluded_modules": sorted(EXCLUDED_MODULES),
        "requested_modules": [f"{name}.py" for name in selected],
        "modules": [],
        "not_completed": [],
        "report_directory": str(run_dir),
    }
    _write_report(report_path, report)
    execute = executor or execute_command
    interrupted = False

    for index, module in enumerate(selected, start=1):
        if overall_deadline is not None and time.monotonic() >= overall_deadline:
            report["not_completed"].extend(
                {"module": f"{name}.py", "reason": "overall deadline elapsed before module start"}
                for name in selected[index - 1 :]
            )
            break
        module_path = tests_dir / f"{module}.py"
        module_dir = run_dir / f"{index:02d}-{module}"
        module_dir.mkdir()
        stdout_path, stderr_path = module_dir / "stdout.bin", module_dir / "stderr.bin"
        command = build_unittest_command(python_executable, module)
        module_started_at = utc_now()
        module_started_mono = time.monotonic()
        if not module_path.is_file():
            execution = {"started": False, "exit_code": None, "timed_out": False, "timeout_status": None, "termination": None, "start_error": f"allowlisted test file does not exist: {module_path}", "elapsed_seconds": 0.0, "not_started_reason": None}
            stdout_path.write_bytes(b"")
            stderr_path.write_bytes(b"")
        else:
            try:
                execution = execute(command, cwd=project_root, timeout_seconds=timeout_seconds, stdout_path=stdout_path, stderr_path=stderr_path, overall_deadline=overall_deadline)
            except KeyboardInterrupt:
                execution = {"started": False, "exit_code": None, "timed_out": False, "timeout_status": None, "termination": None, "start_error": None, "elapsed_seconds": 0.0, "not_started_reason": "runner interrupted before module execution completed"}
                interrupted = True
        stdout, stdout_excerpt = _read_log(stdout_path)
        stderr, stderr_excerpt = _read_log(stderr_path)
        summary = parse_unittest_summary(stdout, stderr)
        if execution.get("not_started_reason"):
            status, reasons = "INCOMPLETE", [execution["not_started_reason"]]
        else:
            status, reasons = classify_module_result(exit_code=execution.get("exit_code"), timed_out=bool(execution.get("timed_out")), summary=summary, start_error=execution.get("start_error"))
        report["modules"].append({
            "module": f"{module}.py",
            "command_argv": command,
            "command_display": subprocess.list2cmdline(command) if os.name == "nt" else " ".join(map(repr, command)),
            "python_executable": python_executable,
            "started_at": module_started_at if execution.get("started") else None,
            "ended_at": utc_now(),
            "elapsed_seconds": round(float(execution.get("elapsed_seconds", time.monotonic() - module_started_mono)), 3),
            "started": bool(execution.get("started")),
            "exit_code": execution.get("exit_code"),
            "timeout_status": execution.get("timeout_status"),
            "termination": execution.get("termination"),
            "start_error": execution.get("start_error"),
            "status": status,
            "reasons": reasons,
            "unittest_summary": summary,
            "summary_status": "complete" if summary["complete"] else "absent_or_incomplete",
            "counts": summary,
            "stdout_file": str(stdout_path.relative_to(run_dir)),
            "stderr_file": str(stderr_path.relative_to(run_dir)),
            "stdout_bytes": stdout_path.stat().st_size,
            "stderr_bytes": stderr_path.stat().st_size,
            "stdout_excerpt": stdout_excerpt,
            "stderr_excerpt": stderr_excerpt,
        })
        if interrupted:
            report["not_completed"].extend({"module": f"{name}.py", "reason": "runner interrupted"} for name in selected[index:])
            break
        _aggregate(report)
        _write_report(report_path, report)

    report["ended_at"] = utc_now()
    report["elapsed_seconds"] = round(time.monotonic() - started_mono, 3)
    _aggregate(report)
    report["report_file"] = str(report_path)
    _write_report(report_path, report)
    return report


def print_report(report: dict[str, Any]) -> None:
    modules, tests = report["module_totals"], report["test_totals"]
    print(f"Overall status: {report['overall_status']}")
    print("Modules: requested={requested}, executed={executed}, passed={passed}, failed={failed}, errored={errored}, skipped={skipped}, incomplete={incomplete}, timed_out={timed_out}, not_completed={not_completed}".format(**modules))
    print("Tests: run={tests_run}, passed={passed}, failures={failures}, errors={errors}, skipped={skipped}".format(**tests))
    print(f"Python: {report['python_executable']}")
    print(f"Per-module timeout: {report['per_module_timeout_seconds']} seconds")
    print(f"Overall timeout: {report['overall_timeout_seconds'] if report['overall_timeout_seconds'] is not None else 'not set'}")
    print("Explicitly excluded: " + ", ".join(report["excluded_modules"]))
    for module in report["modules"]:
        print(f"  {module['module']}: {module['status']}; elapsed={module['elapsed_seconds']}s; exit={module['exit_code']}; tests={module['counts'].get('tests_run')}")
        if module["reasons"]:
            print("    reason: " + "; ".join(module["reasons"]))
        if module.get("termination") and not module["termination"].get("succeeded"):
            print("    TERMINATION FAILURE: " + module["termination"].get("detail", "unknown"))
        if module["status"] in {"FAIL", "INCOMPLETE", "TIMED_OUT"}:
            print(f"    stdout: {module['stdout_file']}")
            print(f"    stderr: {module['stderr_file']}")
            if module["stdout_excerpt"]:
                print("    stdout tail:\n" + module["stdout_excerpt"])
            if module["stderr_excerpt"]:
                print("    stderr tail:\n" + module["stderr_excerpt"])
    for item in report["not_completed"]:
        print(f"  NOT COMPLETED {item['module']}: {item['reason']}")
    print(f"Report: {report['report_file']}")


def _positive_float_argument(value: str) -> float:
    try:
        return positive_seconds(value)
    except RunnerArgumentError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run only explicitly selected allowlisted offline unittest modules.")
    parser.add_argument("modules", nargs="+", help="allowlisted module names, optionally ending in .py")
    parser.add_argument("--python", dest="python_executable", help="Python executable; defaults to this runner's interpreter")
    parser.add_argument("--timeout", type=_positive_float_argument, default=DEFAULT_TIMEOUT_SECONDS, help="positive per-module timeout seconds (default: 120)")
    parser.add_argument("--overall-timeout", type=_positive_float_argument, help="optional positive overall deadline seconds")
    parser.add_argument("--report-root", help="report directory outside the project; defaults to system temp")
    args = parser.parse_args(argv)
    try:
        report = run_modules(args.modules, python_executable=args.python_executable, timeout_seconds=args.timeout, overall_timeout_seconds=args.overall_timeout, report_root=args.report_root)
    except (RunnerArgumentError, OSError) as exc:
        parser.error(str(exc))
    print_report(report)
    return {"PASS": 0, "FAIL": 1, "INCOMPLETE": 2}[report["overall_status"]]


if __name__ == "__main__":
    raise SystemExit(main())



