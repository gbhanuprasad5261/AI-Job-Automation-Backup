# AI Job Automation

## Bounded offline test runner

`run_offline_tests.py` runs only explicitly selected modules from a fixed offline allowlist. It never auto-discovers the full suite or launches application entry points. The allowlist contains reviewed data, policy, in-memory classification, synthetic UI, and temporary-file regression tests; review the exact names in `ALLOWED_MODULES` before extending it. Application-workflow tests requiring further review are not allowlisted, including tests that temporarily patch `AUTO_SUBMIT=True`. `test_search_page_evidence.py`, `test_offline_search_evidence.py`, and `test_route_audit_browser_smoke.py` are explicitly excluded.

Run one module:

```powershell
.\venv312\Scripts\python.exe .\run_offline_tests.py test_pipeline_generation_store.py --timeout 120
```

Run an explicit group, optionally with an overall deadline:

```powershell
.\venv312\Scripts\python.exe .\run_offline_tests.py `
  test_pipeline_generation_store `
  test_analysis_freshness `
  test_csv_output_durability `
  test_offline_pipeline_demo `
  test_job_details_extraction `
  test_job_scraper_publication `
  --timeout 120 --overall-timeout 900
```

Names may include or omit `.py`. The default per-module timeout is 120 seconds. `--timeout` and `--overall-timeout` must be positive finite values. Modules run sequentially in separate Python processes with `-B`; the runner records the exact argv and executable. An overall deadline prevents later modules from starting and lists them as `NOT COMPLETED`.

Reports go to a unique run directory under the system temporary directory at `ai-job-automation-test-runs` by default. `--report-root` can select another directory outside the project. Existing reports are not reused. Each run has `summary.json` and exact byte captures `stdout.bin` / `stderr.bin` per module; the summary includes their byte sizes and the runner source SHA-256. It records no environment-variable snapshot. Keep reports when investigating failures or timeouts.

Module status is `PASS` only when the process exits zero, unittest emits a complete final summary, and at least one test was discovered. A nonzero exit, reported failure/error, or zero discovered tests is `FAIL`. A timeout, missing/incomplete summary, or module not reached by the overall deadline is `INCOMPLETE` (timed-out modules are identified separately). Skipped tests are counted; they do not count as passed. Overall status cannot be `PASS` if any module failed, timed out, lacked a complete summary, or was not completed.

On timeout, inspect that module's preserved output and termination result before deciding whether to rerun it. Windows first sends Ctrl-Break to the dedicated process group and falls back to `taskkill` scoped to the launched PID and its tree; POSIX uses a dedicated process group. A termination failure is explicitly reported and must be investigated before another run. This runner is a test-isolation aid, not a security boundary; it does not authorize live workflows or Windows filesystem adversarial tests.
