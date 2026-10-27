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
- Added failed-serialization and failed-replacement checks for destinations that do not yet exist, plus combined replacement/cleanup failure preservation; the tests verify temporary sibling cleanup where possible and preserve existing output. Added generation-stage permission-error coverage and deterministic rejection of non-object JSON manifest roots; synthetic runner coverage for subprocess startup failure aggregation, interrupted execution termination, and incomplete-summary reporting. Review of pure helper coverage found the parser, serializer, fingerprint, pointer, CSV contract, and policy behavior already exercised through public contracts; no private-helper-only tests were added to duplicate those checks.
- Added direct synthetic tests for `job_analyzer.extract_experience_years`, `get_experience_label`, `location_matches`, and `calculate_priority`, plus `job_details.clean_lines` and `looks_like_location`. The latter has a comment/behavior mismatch for bare `Remote`: current code returns false despite a later comment saying it is acceptable. `job_details.py` remains protected and was not changed; reconcile that behavior only with the required authorization.
- Lifecycle tests cover unsupported dispositions with consistent accounting, duplicate occurrence identifiers, repeated interruption, and failure/recovery. The lifecycle has no persistent transition engine; no transition policy was inferred.
- Latest focused regression run: **9 modules, 178 passed, 0 failed/errors/skipped/timeouts/incomplete**, report `C:\Users\gbhan\Documents\Codex\offline-run-reports\20261027T155234155212Z-93a3bd1786d644c2bcd03768782edf28\summary.json`. Latest helper-only run: **3 modules, 44 passed**, report `C:\Users\gbhan\Documents\Codex\offline-run-reports\20261027T125910632518Z-b2b7054198c646d788b5ff1f62df3801\summary.json`. Full bounded allowlist: **32 modules, 588 passed, 0 failed/errors/skipped/timeouts/incomplete**, report `C:\Users\gbhan\Documents\Codex\offline-run-reports\20261027T155246605355Z-a00d9fefdd12449abd1599755a4df60d\summary.json`. Temporary files were directed to `C:\Users\gbhan\Documents\Codex\offline-run-temp`, outside the checkout. Search-evidence and browser-smoke modules remained excluded.

### Authorized offline development

Synthetic offline tests, isolated helper validation, runner diagnostics, and engineering documentation can continue under the current scope. This work does not authorize production integration, publication, browser workflows, live URL checks, or application submission.

### Decision checklist — open and unapproved

The `PIPELINE_GENERATION_POLICY.md` register marks D1–D13 **OPEN / UNAPPROVED**. It requires the project owner to answer each ID with **approve**, **reject**, or **replace**, plus conditions and evidence. The records identify the decision role as the project owner but do not name an individual. The independent Windows filesystem specialist decides security supportability; no specialist approval is recorded. Owner policy approval alone does not authorize tests or implementation.

| ID | Owner decision required | Evidence to close the decision; specialist gate |
|---|---|---|
| D1 | Authoritative `jobs.csv` producer; whether manual/imported sources are allowed and who designates current. | Producer schema, provenance/run identity, unauthorized-source rejection tests. Specialist review before file-backed integration; publication needs separate approval. |
| D2 | Source identity: raw bytes or canonical records; producer/query/scope/time metadata to retain. | Encoding/BOM, CSV dialect, line endings, duplicates, invalid CSV, header, fingerprint and parse-same-snapshot tests. Specialist review for secure acquisition and byte binding. |
| D3 | Required source fields; whether missing links can be intentional skips; allowed skip rules. | Missing/blank link, approved skip codes, malformed fields and per-occurrence accounting tests. Owner policy; specialist gate applies to secured file access. |
| D4 | Process duplicate source occurrences independently or deduplicate; identity and survivor rule. | Identical URLs, same ID/different metadata, URL variants and multiplicity-through-pipeline tests. Specialist only if identity is used as a security trust decision. |
| D5 | Blank description as successful low-quality result or extraction failure; classify per-record and stage exceptions. | Empty/placeholder/partial descriptions, navigation/parser/transformation exceptions and diagnostic reconciliation tests. Specialist gate if secure evidence-file reads support claims. |
| D6 | Status rules for all-skipped, all-failed, valid-empty and partial runs. | Table-driven status/accounting boundaries and analyzer propagation. Specialist review applies to platform/storage claims. |
| D7 | Required artifacts by stage/status, especially `EMPTY`, all-skipped, `FAILED` and `PARTIAL`. | Per-stage/status artifact-set tests, missing diagnostics, ledger, empty and failed cases. Specialist review if artifact storage/opening/retention is security-sensitive. |
| D8 | After failed/interrupted attempt, keep prior complete selected or set selection to `NONE` pending explicit rollback. | Faults at write/manifest/pointer boundaries, recovery, and candidate-consumer fail-closed tests. Specialist approval for pointer publication, crash, concurrency and supported providers. |
| D9 | Stable job identity for tracker continuity; URL changes, duplicate identities, merges and history conflicts. | ID/URL changes, collisions, conflicting history and tracker persistence tests. Specialist gate if persistence/root security or concurrency is claimed. |
| D10 | Who may authorize rollback, verifiable authorization form, and whether source-fingerprint changes are allowed. | Missing/invalid authority, actor/reference, changed-source, prior-manifest and audit-integrity tests. Specialist review for filesystem durability and rollback-record integrity; authority policy is owner-owned. |
| D11 | Retention period/count, cleanup authority, and coordination with readers/writers. | Retention selection, active-reader/writer coordination, interrupted cleanup and selected-generation protection tests. Specialist review for race/durability claims on each provider. |
| D12 | Inventory of external fixed-path CSV consumers and required compatibility window. | Consumer inventory plus no-mixed-generation/no-legacy-fallback tests. Specialist gate for each consumer’s secure filesystem boundary. |
| D13 | Supported Windows/Python/filesystem/provider matrix and concurrency/durability guarantees. | Owner-authorized real-Windows acceptance evidence per exact environment cell. Independent specialist decision and evidence are **mandatory** before implementation authorization. |

#### Standalone `Remote` question

The exact owner decision is: **Should `looks_like_location("Remote")` accept standalone `Remote` as a location fragment (yes or no)?** Current behavior is false: the earlier invalid-value list returns before a later comment’s regex branch that says bare Remote is acceptable. The existing test asserts false. Keep behavior unchanged until the owner answers. Changing it also requires separate explicit authorization to edit protected `job_details.py` and an approved hash-baseline exception or replacement.

#### Phase 66 security gate

Phase 66 rejected the current evidence-reader design as a trusted-root security boundary. Evidence reading remains blocked; collection publication is closed; `AUTO_SUBMIT` must remain false; browser auditing remains disabled. The assessment authorizes no security-sensitive reader implementation, and the rejection does not imply that a secure alternative is impossible.

Before reconsidering integration, the records require: an owner-defined trusted root/ACL/threat model; supported environment matrix; settled root-relative API/reparse policy; exact opened-object-to-byte binding; mutation/consistency guarantees; fail-closed unsupported-cell behavior; owner-authorized real-Windows acceptance tests with retained per-cell results; and a new written independent specialist decision based on that evidence. Specialist preapproval is separately required for C-class adversarial methods. Explicit implementation authorization is still a separate final gate. See `WINDOWS_FILESYSTEM_SECURITY_REVIEW_PACKAGE.md` and `WINDOWS_GENERATION_STORAGE_SPECIALIST_SUBMISSION.md` for the full criteria.

#### Independent offline work while decisions are pending

The existing backlog and regression modules were reviewed. This pass identified additional standalone redaction gaps for URL queries, JSON/environment formats, wrapped multiline credentials, and failure fallback; these were covered synthetically. No other nonredundant offline gap independent of D1–D13 and Phase 66 was identified. Do not connect helpers to production workflows or treat passing tests as security approval.

#### Authentication-state exposure follow-up

The prior task record identifies `auth/storage_state.json` as the source of one matching line returned by a broad JSON text search. This turn did not reopen the file or inspect its contents. Project documentation contains no owner confirmation of revocation; status remains **OPEN / UNCONFIRMED**. The available record says the line appeared in task tool output, but does not establish whether it was retained or shared elsewhere. The provider/account cannot be identified from the record without reading the saved state, so no revocation was attempted. The owner must identify the provider through their own account records, revoke active sessions/tokens for the account that produced the saved state, and remove the local saved state through the approved secret-handling process. Treat revocation as incomplete until the provider confirms it.

#### Diagnostic redaction status

The standalone helper, `tools/diagnostic_redaction.py`, redacts common bearer, authorization/cookie headers, session identifiers, passwords, API keys, and labelled assignments. Thirteen helper-focused synthetic tests cover bearer and authorization schemes, cookies, sessions, passwords, API keys, percent-encoded URL queries, nested JSON, environment assignments, exception traces, wrapped/malformed multiline output, invalid UTF-8, overlapping patterns, fail-closed fallback, determinism, and preservation of useful context. It can be exercised independently against representative strings/bytes without invoking the protected runner. It is not integrated into any runner or production/report path, is not exhaustive, and does **not** protect diagnostics.

Protected runner integration map (`run_offline_tests.py`, unchanged):

- `execute_command` directs child stdout/stderr straight to `stdout.bin` and `stderr.bin`; these files are raw and may persist even when the run fails or is interrupted. Redacting only excerpts does not protect these files. An authorized design must prevent raw output from becoming a report artifact, including interruption/crash behavior.
- `_read_log` decodes the captures and returns full text plus a 30-line tail. `parse_unittest_summary` only derives test counts/outcome from this text, but `run_modules` also stores the tails as `stdout_excerpt` / `stderr_excerpt` in `summary.json`.
- Startup `OSError` text (`start_error`) and termination details are stored in the module report; failure reasons, termination details, and stdout/stderr tails are printed by `print_report`. These exception-derived strings need redaction before persistence and console output.
- Minimum end-to-end verification after authorization: inject fabricated credentials in child stdout/stderr, startup exception text, timeout/termination details, and malformed/multiline output; assert no value appears in `.bin` artifacts, JSON, returned report, or captured console output while useful errors and accurate test counts remain. Exercise success, failure, timeout, interruption, and startup-failure paths. The standalone helper tests do not substitute for these sink-level tests.
- `tests/test_bounded_offline_runner.py` now has `SimulatedDiagnosticSinkTests`: it writes helper-redacted synthetic stdout/stderr to temporary `stdout.bin`/`stderr.bin`, constructs simulated report excerpts, failure reasons, summaries and startup/termination fields, and captures simulated console text for success, failure, timeout, interruption, and startup-failure cases. A second fixture forces helper failure and verifies the fixed omission marker reaches every modeled sink without falling back to fabricated raw values. These fixtures verify helper behavior at representative sinks only; they do not invoke `run_offline_tests.py` or prove actual runner output is protected.
`run_offline_tests.py` is protected and remains unchanged. Integration requires explicit authorization to modify it, choose a capture design that does not leave raw secrets in report artifacts, and add the end-to-end tests above. Until then, treat runner reports as potentially sensitive and keep test output free of credentials.

Verified results: focused runner/redaction and simulated-sink tests **35/35 passed**; full offline allowlist **32 modules, 603/603 passed**, with `TEMP` and `TMP` outside the checkout. Report: `20261027T165711016602Z-54536608470c4595aa4892661c6afa1d`.

### Next recommended task

Owner action: revoke the affected account session as described above and document provider confirmation. For engineering, obtain the required owner decisions for D1–D13 and the independent specialist resolution for the storage/security boundary. Separately authorize the protected runner's diagnostic-redaction change if desired. Only after those gates are documented should a separately authorized integration proposal be prepared; do not treat these helper tests as approval to integrate or publish.
