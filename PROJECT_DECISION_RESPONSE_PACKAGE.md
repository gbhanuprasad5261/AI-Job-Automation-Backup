# Project Decision and Release-Unblocking Package

**Prepared:** 2026-10-30
**Repository:** `C:\Users\gbhan\Downloads\AI-Job-Automation-updated v1`
**Reference:** `RELEASE_READINESS_HANDOFF.md`

This is a fillable response package, not an approval record. It does not change any existing decision, authorize implementation, or establish a protected-file baseline. The choices below are copied or summarized from project records; no choice is selected. Where the records do not define options, provide a custom answer.

## Current recorded gate status

- **D1–D13:** OPEN / UNAPPROVED. `PIPELINE_GENERATION_POLICY.md` requires an owner response per ID and says an owner policy answer alone does not authorize implementation, testing, publication, or filesystem-security changes.
- **Phase 66:** REJECTED for the current evidence-reader design. A different design may be proposed for a new review; that is not approval to test or integrate it.
- **Protected baseline:** six documented files matched in the recorded 2026-10-30 check; 15 entries remain unavailable. No replacement baseline was created.
- **Authentication incident:** OPEN / UNCONFIRMED pending owner/provider confirmation of revocation.
- **Runner redaction:** helper remains standalone; actual runner output is not verified as redacted. `run_offline_tests.py` remains protected.
- **Git:** status/diff failure has reproduced in restricted context. They succeeded in a prior write-enabled context. Cause is unconfirmed; the current restricted-context inventory is unknown.
- **AUTO_SUBMIT:** `false` was last verified. Do not change it.

## 1. Owner decision response template

For each row, fill in every response field. Use `approve`, `reject`, or `replace` for D1–D13 as required by the policy register, then state the concrete selected policy and any conditions. Do not treat a recommendation column in an existing report as a selected choice. Use a separate signed/dated response for each ID; do not close unanswered IDs by implication.

| ID | Question | Available choices documented in project records (none selected) | Selected choice | Rationale | Approver role/name | Decision date | Supporting evidence/reference |
|---|---|---|---|---|---|---|---|
| D1 | Which producer is authoritative for `jobs.csv`? Are manual/imported files allowed, and who may designate them current? | Authorize a future collection producer; designate a separately controlled import/manual source; or leave source unauthoritative. | [Owner fill in] | [Owner fill in] | [Owner fill in] | [YYYY-MM-DD] | [Reference] |
| D2 | What source identity is required: exact raw bytes or canonical records, and which producer/query/scope/time metadata must be retained? | Choose raw-byte or canonical-record identity; specify required metadata fields and how unknown fields are recorded. | [Owner fill in] | [Owner fill in] | [Owner fill in] | [YYYY-MM-DD] | [Reference] |
| D3 | Which source fields are required? Can a missing link be an intentional skip, and which skip rules are allowed? | Missing link is failure; an explicitly approved skip; or source-level rejection. Specify each allowed skip code. | [Owner fill in] | [Owner fill in] | [Owner fill in] | [YYYY-MM-DD] | [Reference] |
| D4 | Are duplicate source occurrences processed independently or deduplicated? What identity and survivor rule apply? | Preserve/process every occurrence; or deduplicate by an approved identity with each removed occurrence accounted for. Specify identity/survivor rules. | [Owner fill in] | [Owner fill in] | [Owner fill in] | [YYYY-MM-DD] | [Reference] |
| D5 | When is a blank description a successful low-quality result versus extraction failure? How are per-record and stage exceptions classified? | Define blank/placeholder/partial-description outcomes; distinguish navigation/extraction failures from transform/output failures. | [Owner fill in] | [Owner fill in] | [Owner fill in] | [YYYY-MM-DD] | [Reference] |
| D6 | What are the status rules for all-skipped, all-failed, valid-empty, and partial runs? | Specify status for each case; the policy register discusses `EMPTY`, `FAILED`, `PARTIAL`, and `COMPLETE`, but selects none. | [Owner fill in] | [Owner fill in] | [Owner fill in] | [YYYY-MM-DD] | [Reference] |
| D7 | Which artifacts are mandatory for each stage/status, especially `EMPTY`, all-skipped, `FAILED`, and `PARTIAL`? | Data artifacts absent for empty/failed; header-only CSVs; or diagnostics-only artifacts are alternatives in the register. Specify exact artifact sets and retention. | [Owner fill in] | [Owner fill in] | [Owner fill in] | [YYYY-MM-DD] | [Reference] |
| D8 | After a failed/interrupted attempt, does the prior complete generation remain selected, become `NONE`, or require explicit rollback? | Keep prior selection; clear to `NONE`; or require explicit rollback. Specify stale-selection and recovery policy. | [Owner fill in] | [Owner fill in] | [Owner fill in] | [YYYY-MM-DD] | [Reference] |
| D9 | What stable job identity governs tracker continuity, and how are URL changes, duplicates, merges, and history conflicts handled? | Platform ID, normalized URL, or a defined composite key are discussed. Specify migration, ambiguity, and conflict rules. | [Owner fill in] | [Owner fill in] | [Owner fill in] | [YYYY-MM-DD] | [Reference] |
| D10 | Who may authorize rollback, what constitutes verifiable authorization, and may rollback use a different source fingerprint? | Designated/verifiable authorization; same-source-only rollback; or explicitly authorized cross-source rollback are discussed. Specify approver and evidence mechanism. | [Owner fill in] | [Owner fill in] | [Owner fill in] | [YYYY-MM-DD] | [Reference] |
| D11 | What generations are retained, who may clean them, and how is cleanup coordinated with readers/writers? | Retention by time/count; selected plus rollback generations; or manual cleanup are discussed. Specify period/count, authority, and coordination. | [Owner fill in] | [Owner fill in] | [Owner fill in] | [YYYY-MM-DD] | [Reference] |
| D12 | Which external tools consume fixed-path CSVs, and what compatibility window is required? | Keep fixed-path exports; migrate consumers; or use a bounded compatibility window. Supply the external consumer inventory and dates. | [Owner fill in] | [Owner fill in] | [Owner fill in] | [YYYY-MM-DD] | [Reference] |
| D13 | Which Windows/Python/filesystem/provider cells and concurrency/durability guarantees are supported? | Restrict support to verified cells; add cells only with evidence; or keep generation-backed production work blocked. Specify each exact cell and guarantees. | [Owner fill in] | [Owner fill in] | [Owner fill in] | [YYYY-MM-DD] | [Reference] |
| PH66-ALT | May a different evidence-reader design be proposed for a new security review? | Yes—proposal only; no; defer. This does not reverse Phase 66 or authorize tests/integration. | [Owner fill in] | [Owner fill in] | [Owner fill in] | [YYYY-MM-DD] | [Reference] |
| BASELINE | Who may supply the existing 15 missing protected-file paths/hashes, or may the documented re-establishment process be used? | Supply the authoritative existing manifest; or explicitly authorize the documented re-establishment process. Do not invent values. | [Owner fill in] | [Owner fill in] | [Owner fill in] | [YYYY-MM-DD] | [Reference] |
| CDP-EMPTY | What should empty `CHROME_CDP_URL` mean? | Treat as explicitly unset; use localhost fallback; reject as invalid. | [Owner fill in] | [Owner fill in] | [Owner fill in] | [YYYY-MM-DD] | [Reference] |
| JS-FALLBACK | Should `job_search.py`'s `ImportError` compatibility fallback remain supported? | Keep supported; retire; replace with specified behavior; defer. State affected compatibility requirements. | [Owner fill in] | [Owner fill in] | [Owner fill in] | [YYYY-MM-DD] | [Reference] |
| BACKUPS | Are the six named backup snapshots supported for manual use, and should their local settings remain? | Supported; unsupported/retired; conditionally supported (state conditions). Applies to `application_form_backup.py`, `application_form_backup_before_radio_fix.py`, `easy_apply_backup.py`, `easy_apply_backup_before_apply_fix.py`, `easy_apply_backup_before_tracker_fix.py`, and `external_apply_backup.py`. | [Owner fill in] | [Owner fill in] | [Owner fill in] | [YYYY-MM-DD] | [Reference] |
| TRK-1 | Does a missing tracker file mean empty data or missing/uninitialized data? | Treat as valid empty; report missing/uninitialized; custom answer. | [Owner fill in] | [Owner fill in] | [Owner fill in] | [YYYY-MM-DD] | [Reference] |
| TRK-2 | Must tracker read errors be distinguishable from empty data? | Distinguish and signal error; treat as empty; custom answer. | [Owner fill in] | [Owner fill in] | [Owner fill in] | [YYYY-MM-DD] | [Reference] |
| TRK-3 | Should malformed CSV be rejected or accepted? | Reject with distinct error; accept under specified rules; custom answer. | [Owner fill in] | [Owner fill in] | [Owner fill in] | [YYYY-MM-DD] | [Reference] |
| TRK-4 | Which headers and row shapes are permitted? | Specify required/optional headers, extra columns, and short/long row handling in free text; existing records establish no full schema policy. | [Owner fill in] | [Owner fill in] | [Owner fill in] | [YYYY-MM-DD] | [Reference] |
| TRK-5 | How should `main()` report missing, unreadable, malformed, or valid-empty data? | Specify separate user-visible outcomes in free text; existing behavior reports “No application tracker records found” for falsey load results. | [Owner fill in] | [Owner fill in] | [Owner fill in] | [YYYY-MM-DD] | [Reference] |
| TRK-6 | Should `count_confirmed_today()` return zero or signal unavailable data after a failed read? | Zero for all cases; distinguish unavailable/error; custom answer. | [Owner fill in] | [Owner fill in] | [Owner fill in] | [YYYY-MM-DD] | [Reference] |

## 2. Administrator escalation template

**Request:** diagnose Git worktree/status behavior read-only. Do not repair or modify the repository as part of diagnosis.

- Repository path: `C:\Users\gbhan\Downloads\AI-Job-Automation-updated v1`
- Branch: `master`
- Last known HEAD: `f362dffb47fb26d015e9b9056e0676df6cac2c64`
- Git executable/version: `C:\Program Files\Git\cmd\git.exe`, `2.50.1.windows.1`
- Restricted-context failing commands: `git status --short --untracked-files=all`; `git diff --check`; both returned exit 128 with `fatal: this operation must be run in a work tree`.
- `git rev-parse --show-toplevel`, `--is-inside-work-tree`, `--git-dir`, `--git-path index`, branch, and HEAD succeeded in that context. It reported the expected root, `true`, `.git`, and `.git/index`. Checked Git discovery/index override variables were unset; local config showed `core.bare=false` and no `core.worktree`.
- Explicit `--git-dir <project>\.git --work-tree <project> status` reproduced the same error. From a temp working directory, Git failed to enter the project with `Permission denied`.
- Prior write-enabled context: status and `git diff --check` both exited 0. Status then listed `M tests/test_atomic_status_writes.py`, `M tests/test_phase7g_diagnostics.py`, and `?? RELEASE_READINESS_HANDOFF.md`.
- Known existing modified test files: `tests/test_phase7g_diagnostics.py` and `tests/test_atomic_status_writes.py`. The complete inventory in the current restricted context is **UNKNOWN**; the prior successful list is context-specific.
- Please investigate process identity/context, Windows access boundaries, and why Git worktree discovery succeeds while status/diff fail. Provide the safe explanation and any remediation proposal for owner approval.
- **Underlying cause: UNCONFIRMED.** No ACL, permission, `.git`, Git configuration, or history changes are authorized by this request.

Administrator response:

- Finding and evidence: [fill in]
- Process/access context tested: [fill in]
- Root cause: [confirmed / not established, explain]
- Recommended remediation (no action until separately authorized): [fill in]
- Administrator role/name: [fill in]
- Date: [YYYY-MM-DD]
- Evidence/reference: [fill in]

## 3. Security review request

This request does not authorize runner changes or live authentication. Keep authentication status OPEN / UNCONFIRMED until owner confirmation is documented. The owner must revoke the affected session through the issuing provider and record confirmation using a secret-safe reference; do not include tokens, cookies, account secrets, or session values here.

### Decisions and review fields

For every SEC-ID response, record the selected choice/status, rationale, approver or reviewer role/name, decision date, and supporting evidence/reference. Use `DEFER` or `OPEN` rather than implying approval when evidence is pending.

| ID | Required question/evidence | Response (leave blank pending decision) |
|---|---|---|
| SEC-AUTH | Has the owner revoked the affected session through the issuing provider and received confirmation? Record only completion/date and a safe evidence reference; never include secrets. | Selected status: [OPEN / CONFIRMED]; rationale: [ ]; owner role/name: [ ]; date: [ ]; evidence reference: [ ] |
| SEC-RUNNER | Does the owner explicitly authorize modification of protected `run_offline_tests.py` to integrate redaction? | Selected choice: [YES / NO / DEFER]; rationale/conditions: [ ]; approver role/name: [ ]; date: [ ]; evidence: [ ] |
| SEC-REVIEWER | Who is the named, qualified specialist/security reviewer, and what scope/criteria are they authorized to approve? | Selected reviewer/scope: [ ]; rationale/qualifications: [ ]; appointing approver role/name: [ ]; date: [ ]; evidence/reference: [ ] |
| SEC-FAIL-CLOSED | What must happen if redaction fails or receives malformed diagnostics? | Available proposals (none selected): fixed omission marker with no raw fallback; reject/abort capture; or specified alternative. Selected behavior: [ ]; rationale: [ ]; approver role/name: [ ]; date: [ ]; evidence: [ ] |
| SEC-SINKS | Confirm every sink that must be protected before data is persisted or displayed. | Selected sink scope: child `stdout.bin`/`stderr.bin`; report/summary fields; stdout/stderr excerpts; startup exceptions; termination/timeout/interruption details; failure reasons; logs; console output; returned report. Rationale: [ ]; approver role/name: [ ]; date: [ ]; evidence: [ ] |
| SEC-TESTS | Approve synthetic tests and their boundaries. | Selected test scope: fabricated secrets only; success, failure, timeout, interruption, startup failure, malformed/multiline output, exception text, helper failure, and fail-closed paths; assert no synthetic value in each sink while useful diagnostics/counts remain. Rationale/conditions: [ ]; approver role/name: [ ]; date: [ ]; evidence: [ ] |
| SEC-EVIDENCE | What evidence is required before security approval? | Selected evidence criteria: reviewer’s written decision; approved threat model/scope; exact integration diff; sink-by-sink end-to-end results/artifact inspection; failure-path/fail-closed evidence; supported environment/limitations. Rationale: [ ]; approver role/name: [ ]; date: [ ]; reference: [ ] |

Known sink inventory from the handoff: raw subprocess `stdout.bin` and `stderr.bin`; summary/report fields and excerpts; startup `OSError` text; termination details; failure reasons; and `print_report` console output. Raw captures may persist on failure/interruption. The standalone helper and simulated sink tests do **not** prove actual runner protection. Redaction must occur before persistence/display, and a redaction failure must never fall back to raw output. Any test of actual runner output remains blocked until explicit authorization and reviewer approval.

Reviewer decision:

- Decision: [APPROVE / CONDITIONAL / REJECT / DEFER]
- Scope, supported environment, exclusions, and required follow-up: [fill in]
- Reviewer role/name and qualification: [fill in]
- Date: [YYYY-MM-DD]
- Evidence/reference: [fill in]

## 4. Dependency-ordered roadmap

### Mandatory blockers before affected integration/release claims

| Order | Work | Dependency / decision owner | Expected outcome | Focused validation after approval | Risk if skipped |
|---|---|---|---|---|---|
| A | Administrator diagnoses Git access and supplies a reliable complete working-tree inventory. | Repository administrator; current restricted-context Git failure. | Reproducible status/diff behavior and complete list of existing modifications. | `git rev-parse`, `git status --short --untracked-files=all`, and `git diff --check` from documented restricted and authorized contexts; compare results without modifying metadata. | User changes may be missed; clean-tree claims would be unsupported. |
| B | Owners answer D1–D13 and the CDP, `job_search.py` fallback, six backup, and six tracker questions. | Project owner for D1–D13; tracker/compatibility owner role is not individually named in current records. | Written, per-ID choices, conditions, rationale, approver, date, and evidence. | Prepare tests from selected policies only; run focused synthetic tests after separate authorization where the policy register requires it. | Guessing can change data meaning, selection, status, or compatibility behavior. |
| C | Authorized custodian supplies the existing 15 missing baseline paths/hashes, or owner explicitly authorizes the documented re-establishment process. | Project owner identifies custodian/authority; no individual is named. | Verifiable 21-entry baseline with provenance or documented authorized re-establishment decision. | Verify each supplied path against its exact authorized hash; report missing/mismatch individually. | Full protected-state claims remain impossible; invented hashes undermine integrity. |
| D | Owner confirms provider-side revocation; owner separately authorizes any runner integration and appoints a qualified reviewer. | Project owner for revocation and runner edit authorization; named specialist/security reviewer must be supplied. | Secret-safe revocation confirmation and written review scope/criteria/authorization. | No auth access; synthetic redaction tests only after authorization; sink-by-sink review and written decision. | Incident remains open; actual runner artifacts may disclose sensitive data. |
| E | Plan, implement, and test only specifically approved work. | Relevant owner decisions, specialist approval, and explicit implementation/test authorization must be complete for the work item. Phase 66 rejection remains active for its current design. | Bounded implementation plan that preserves restrictions and approved contracts. | Focused tests, regression suite, syntax/diff checks, protected-state checks, and retained evidence appropriate to the change. | Policy drift, security claims without support, or unintended production behavior. |
| F | Perform final release validation and packaging. | A–E gates applicable to the release scope; baseline and Git inventory must be adequate for the claims made. | Release record separating fresh results, historical evidence, exclusions, and unresolved limits. | Full approved offline allowlist, artifact/package inventory, configuration checks, hash verification against authoritative baseline, and clean/reconciled worktree evidence. | Release status or claims may be incomplete or misleading. |

### Optional improvements

- New offline synthetic tests for a specific, demonstrated gap in an unprotected helper, provided they do not encode pending D1–D13, tracker, CDP, or security policy.
- Documentation maintenance when authoritative owner/admin/reviewer evidence arrives.
- No particular optional implementation is currently approved by this package; do not create work solely to increase test counts or show progress.

## 5. Documentation validation checklist

Before submitting filled responses, verify:

- [ ] D1–D13 each has an individual decision; no blank ID is inferred from another answer.
- [ ] Every selected choice is explicitly written and is not copied from a recommendation as if already approved.
- [ ] Decision-maker roles/names, dates, conditions, rationale, and evidence references are present.
- [ ] Phase 66 remains rejected for the current design unless a new authoritative security decision explicitly addresses it; a new proposal is not implementation approval.
- [ ] No missing baseline hash/path is guessed or generated without authorization.
- [ ] Tracker decisions cover all six questions and do not silently change existing behavior before approval.
- [ ] Authentication confirmation contains no credentials, cookies, tokens, or session values.
- [ ] Runner authorization, reviewer qualifications, fail-closed rules, complete sink list, and evidence criteria are explicit.
- [ ] Administrator report distinguishes reproducible observations from confirmed root cause; root cause is not claimed until proven.
- [ ] Historical and fresh tests, simulated and actual runner checks, and verified/unverified baseline entries are clearly separated.

**Current validation:** this package is a documentation template only. No application tests are required or run. Do not interpret blanks, suggested choices, or this package’s creation as approval. Existing release statuses remain unchanged until authoritative responses are recorded.
