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

## Engineering backlog (updated 2026-10-27)

### Completed and verified

- Extended `tests/test_csv_contracts.py` with isolated header and Link cases covering empty, duplicate, missing, extra, and reordered headers; HTTP/HTTPS values; missing, whitespace, non-string, malformed, relative, invalid-port, and hostname-edge inputs; deterministic reason codes; and an assertion that importing the contract helpers does not load configuration or browser modules. No network requests are made.
- Reviewed `job_details.py` and `job_analyzer.py`. Their module imports include Playwright and configuration/profile dependencies; the pure CSV contract stays in `csv_contracts.py`. The Link validator remains a standalone helper and has no production call-site integration.
- Expanded manifest compatibility cases for malformed byte envelopes, duplicate JSON keys, invalid UTF-8/JSON, object/byte disagreement, empty and incorrectly typed fields, missing verifier bytes, incompatible versions, fail-closed results, and deterministic errors.
- Expanded lifecycle coverage for duplicate input rows as distinct ordinal occurrences, duplicate occurrence identifiers, repeated interruption, failure followed by recovery, and non-inheriting state. No persistent transition engine or uniqueness rule for logical identity is defined by this synthetic lifecycle.
- Added runner-report tests for timeout category, failed termination detail, partial logs, subprocess startup failures, nonzero exits despite an `OK` unittest summary, and zero-test runs. The runner source and allowlist remain unchanged.
- Added strict malformed-header parsing, non-bytes fingerprint rejection, temp-cleanup-error preservation, repeated atomic output replacement, deterministic manifest serialization, and direct dry-run policy edge cases.
- Added synthetic failure-path checks for `fsync` errors during output replacement and malformed explicit-rollback recovery metadata. Existing output preservation and deterministic contract rejection are verified.
- Added interruption and post-replace-failure recovery checks for atomic outputs, malformed dry-run field coverage that remains non-authorizing, boolean schema-version rejection, and lifecycle input-type rejection before validator dispatch.
- Added generated-ID uniqueness checks across repeated generation creation, rejected non-text run IDs, and nested duplicate-key manifest parsing coverage. Runner timeout, startup failure, process exit, and summary-accuracy cases remain covered by the bounded runner tests; its allowlist was not changed.
- Added UTF-8 encoding-failure preservation and generation-stage path-conflict checks; both use synthetic data in temporary directories outside the checkout.
- Added a failed-serialization check for a destination that does not yet exist. Review of pure helper coverage found the parser, serializer, fingerprint, pointer, CSV contract, and policy behavior already exercised through public contracts; no private-helper-only tests were added to duplicate those checks.
- Added direct synthetic tests for `job_analyzer.extract_experience_years`, `get_experience_label`, `location_matches`, and `calculate_priority`, plus `job_details.clean_lines` and `looks_like_location`. The latter has a comment/behavior mismatch for bare `Remote`: current code returns false despite a later comment saying it is acceptable. `job_details.py` remains protected and was not changed; reconcile that behavior only with the required authorization.
- Lifecycle tests cover unsupported dispositions with consistent accounting, duplicate occurrence identifiers, repeated interruption, and failure/recovery. The lifecycle has no persistent transition engine; no transition policy was inferred.
- Latest focused regression run: **9 modules, 171 passed, 0 failed/errors/skipped/timeouts/incomplete**, report `C:\Users\gbhan\Documents\Codex\offline-run-reports\20261027T130617896036Z-e3b555e79a3641cabc4f4f1cc5cce63c\summary.json`. Latest helper-only run: **3 modules, 44 passed**, report `C:\Users\gbhan\Documents\Codex\offline-run-reports\20261027T125910632518Z-b2b7054198c646d788b5ff1f62df3801\summary.json`. Full bounded allowlist: **32 modules, 581 passed, 0 failed/errors/skipped/timeouts/incomplete**, report `C:\Users\gbhan\Documents\Codex\offline-run-reports\20261027T130629792341Z-a0b201547b724456929f3e368d1696d2\summary.json`. Temporary files were directed to `C:\Users\gbhan\Documents\Codex\offline-run-temp`, outside the checkout. Search-evidence and browser-smoke modules remained excluded.

### Open blockers and boundaries

- D1–D13 remain unresolved; production generation integration remains **NO-GO**. The Phase 66 security rejection remains in force.
- Future integration prerequisites: owner answers for all D1–D13 (including source authority, occurrence/skip/status semantics, selection/rollback, tracker continuity, retention, and fixed-path consumers); one reconciled manifest/interface contract; owner-defined storage root and environment/threat matrix; independent specialist approval and authorized real-Windows acceptance evidence; then a new explicit implementation authorization. Publication and application submission require their own approvals.
- `looks_like_location("Remote")` returns false because the early invalid-value list includes `remote`; the later regex/comment saying bare Remote is acceptable is unreachable for that input, and the current test asserts false. The precise owner decision is: should the standalone value `Remote` be accepted as a location fragment (yes or no)? Until that is answered, keep behavior unchanged. Implementing a change would additionally require explicit authorization to edit protected `job_details.py` and an approved exception or replacement for its established hash baseline.
- This work verifies pure helper and synthetic offline behavior only. It does not validate live URLs, Windows filesystem security, trusted-root containment, crash durability, or production workflow behavior.
- Link validator production integration, publication changes, workflow-runner configuration changes, and application submission remain outside the approved scope.

### Next recommended task

Obtain the required owner decisions for D1–D13 and the independent specialist resolution for the storage/security boundary. Only after those gates are documented should a separately authorized integration proposal be prepared; do not treat these helper tests as approval to integrate or publish.
