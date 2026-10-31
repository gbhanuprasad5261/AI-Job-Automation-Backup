# D8a Failure and Interruption Classification Owner Worksheet

**Status:** **OWNER APPROVED — OPTION A: EXISTING FIVE-STATE VOCABULARY — POLICY DECISION ONLY**, subject to D6 approval of detailed status, accounting, and artifact semantics. This decision does not authorize implementation.

## Scope and decision boundary

D8a covers how generation attempts are classified when work succeeds, produces no records, fails at different boundaries, is interrupted, or cannot be reliably inspected after restart. The owner has now approved the existing five-state vocabulary under D8a Option A, policy only; D6 must still resolve detailed status and evidence rules. D8b Option C — Explicit Rollback Authorization is separately **OWNER APPROVED — POLICY DECISION ONLY**: failed or interrupted generations do not become active automatically; selection remains `NONE`; a prior `COMPLETE` generation can be reselected only through explicit authorized rollback. This worksheet does not authorize a state transition, pointer update, recovery journal, or production implementation.

D6 status and artifact decisions remain a dependency. The owner has approved the five-state vocabulary and the explicit rules recorded below. The detailed helper constraints described in this worksheet remain proposed pending D6 approval; they are not production behavior.

## Verified state inventory

| Area | Existing states or behavior | Boundary |
|---|---|---|
| `pipeline_generation_store.py` manifest | `IN_PROGRESS`, `COMPLETE`, `EMPTY`, `PARTIAL`, `FAILED` | Isolated validator contract; no production writer, publisher, or restart recovery integration. |
| Isolated pointer validator | `NONE`, `CURRENT`, `EMPTY`, `EXPLICIT_ROLLBACK` | Validates pointer shape and referenced data. It does not publish pointers or prove filesystem atomicity, durability, or authorization. `NONE` accepts latest `IN_PROGRESS`, `PARTIAL`, or `FAILED`; explicit rollback accepts latest `PARTIAL` or `FAILED`. |
| Helper tests | Synthetic validation fixtures for all five manifest statuses; output/accounting rules; missing/mismatched artifacts; pointer validation and rollback constraints. | Tests verify helper contracts only; they do not establish production transitions. |
| `job_search.py` collection evidence | Collection-specific `COMPLETE`, `COMPLETE_EMPTY`, `INCOMPLETE`, `FAILED`, `UNKNOWN` classifications exist. | These are collection/evidence statuses, not generation manifest states. Production `publish_collection()` currently returns `False` for all outcomes. |
| Production `job_details.py` stage | Reads fixed-path `jobs.csv`; missing/malformed input raises. A valid zero-row input returns before output replacement. Per-record exceptions are logged, diagnostic entries are recorded, and a row with blank description is appended; missing-link records are skipped. | It writes fixed-path details CSV and diagnostics JSON sequentially, with no generation status or occurrence accounting contract. These outcomes do not currently map to `PARTIAL` or `FAILED`. |
| Production `job_analyzer.py` stage | Reads fixed-path details CSV; missing or malformed input raises. Valid zero-row input returns before writing analysis. | Writes the analysis CSV at a fixed path; no manifest status, input-generation binding, or restart classification is produced in this stage. |
| Output replacement helper | `output_files.py` writes each output to a sibling temporary file and replaces that destination after serialization. | It protects a single destination from some serialization/write failures, but does not provide a multi-output transaction, generation manifest, or restart state. |

The generation helper allows `COMPLETE` only for nonempty source with zero failed records, `EMPTY` only with zero source/accounting and no data outputs, and `PARTIAL` only with at least one failed and at least one processed record plus the required valid artifact set. `FAILED` requires a failure code and no outputs. `IN_PROGRESS` has no completion timestamp, accounting, or outputs. These are helper validation constraints. D6 has not approved them as production semantics.

## Classification cases for owner review

The table separates observed behavior from candidate classification. A physical file or exception alone does not prove a generation status.

| Case | Verified or proposed evidence | Approved policy direction; detailed semantics remain subject to D6 |
|---|---|---|
| **1. Successful generation** | Validated source, accounting, required artifacts, and stage bindings. Production does not currently record this as a generation. | `COMPLETE` for nonempty, fully accounted work with no failed occurrences and validated required outputs. All-skipped nonempty input remains dependent on D6’s skip rule and ledger requirement. |
| **2. Empty generation** | Valid source with zero records, distinguished from a missing or malformed source. Production stages return early and can leave old outputs in place. | `EMPTY` under the helper contract requires zero source/accounting records and no data outputs. D8b pointer mode `EMPTY` represents zero selected candidates; no fallback to old fixed-path files. Owner must decide whether the production empty-input case qualifies as a completed `EMPTY` generation. |
| **3. Failure before output creation** | A known source/transform/stage failure with no outputs. | Candidate `FAILED` if a valid terminal failure manifest and stable failure code can be recorded. If no terminal record can be written, the persisted result may remain `IN_PROGRESS` or be unavailable; do not claim `FAILED` without evidence. |
| **4. Failure after partial output creation** | One output may exist while another is absent, or output bytes may be incomplete. Details and diagnostics are currently replaced one file at a time. | Do not classify based only on a file’s existence. `PARTIAL` under the helper contract means useful processed occurrences plus failed occurrences and a complete, valid required artifact set. Incomplete/corrupt output does not satisfy that contract. A known publication failure could be recorded as `FAILED` only if a valid terminal record is written; otherwise the outcome remains nonterminal or unknown. |
| **5. Process interruption** | The process stops before a validated terminal record; an `IN_PROGRESS` record may or may not remain. | Existing helper has `IN_PROGRESS`, which is nonterminal and not selectable. D8b requires selection `NONE` after interruption. No approved rule currently converts `IN_PROGRESS` to `FAILED` on restart. |
| **6. Unexpected process termination** | Termination may occur between artifact, manifest, or pointer writes; production has no generation publication protocol. | If valid persisted metadata proves `IN_PROGRESS`, treat it as nonterminal and keep selection `NONE`. If the record is absent, contradictory, or unreadable, report unavailable/blocked and select no candidates. Do not invent an `INTERRUPTED` status or infer a terminal failure. |
| **7. Missing output** | A required artifact is absent or cannot be opened. The helper rejects missing artifacts when artifact reading is requested. | Reject the generation as invalid/unavailable for selection. A failure label is not established unless a valid failure record records it. Do not fall back to a fixed-path or older output. |
| **8. Corrupt manifest or output** | Strict parsing, schema/accounting checks, artifact hash/size checks, and bindings may reject malformed or inconsistent data. | Validation failure means blocked/unselectable. Corruption is not itself a persisted `FAILED` status. Preserve the evidence; do not rewrite history to make it appear terminal. |
| **9. Unknown generation outcome** | Evidence is missing, malformed, contradictory, or insufficient to determine which boundary completed. | Treat as unavailable/blocked with no selected candidates and no fallback. `UNKNOWN` is used by collection evidence, not by the generation manifest contract. Whether to add a generation `UNKNOWN` status is an owner decision below. |

## Restart behavior under approved D8b Option C

“Effective selection is none” below describes the fail-closed selection result. When pointer data is missing or corrupt, this does not mean a new persisted `NONE` pointer may be fabricated or written.

| State/evidence found at restart | Existing helper behavior | D8b policy interaction and unresolved D8a point |
|---|---|---|
| **`COMPLETE`** | A valid `CURRENT` pointer must select the latest `COMPLETE` run; manifest and artifacts can be validated. | Selection may use the validated generation. Missing/corrupt/conflicting state blocks and does not fall back. D8a must define what counts as enough terminal success evidence. |
| **`EMPTY`** | A valid `EMPTY` pointer selects the latest `EMPTY` run, representing zero candidates. | A validated empty generation yields no candidates. It must not expose a prior fixed-path CSV. D8a/D6 must distinguish a valid empty source from a missing or malformed source. |
| **`FAILED`** | Pointer mode `NONE` is valid; helper rollback may reference a retained matching `COMPLETE` generation, but only for latest `FAILED` and with required metadata. | Keep selection `NONE`. Previous data remains preserved but unselected unless explicit authorized rollback passes D8b and D10 conditions. D8a must define failure evidence and terminal-record requirements. |
| **`PARTIAL`** | Pointer mode `NONE` is valid; required partial artifact/accounting constraints apply; helper rollback may reference a prior complete generation. | Keep selection `NONE`; partial output is not automatically selectable. Any rollback remains gated by explicit authorization and validation. D8a must distinguish occurrence-level partial work from incomplete/corrupt publication. |
| **`IN_PROGRESS`** | Nonterminal and nonselectable; pointer mode `NONE` is valid. | Keep selection `NONE`. Restart does not prove completion or failure. D8a must decide whether and how an authorized process can later classify the attempt; no recovery protocol is approved. |
| **Unexpected termination** | No dedicated manifest state or production restart recovery exists. A prior `IN_PROGRESS` record can validate, but the helper does not discover or repair it. | Keep effective selection at none. Do not synthesize a terminal state or rewrite historical records. If no trustworthy pointer/manifest exists, block as unavailable. |
| **Generation metadata missing, corrupt, or conflicting** | Validators reject malformed data; production has no generation metadata reader to recover from. | Fail closed: unavailable/blocked, no candidates, no stale-file fallback, and no retry/rollback based on absence. Do not claim that a persisted `NONE` pointer exists unless one is actually validated. |

## Owner-approved D8a policy

**D8a — Option A: Existing Five-State Vocabulary. OWNER APPROVED — POLICY DECISION ONLY.** Use these status names, subject to D6 approval of exact semantics:

- `IN_PROGRESS`
- `COMPLETE`
- `EMPTY`
- `PARTIAL`
- `FAILED`

The owner-approved classification rules are:

1. `PARTIAL` remains nonselectable.
2. Failed or interrupted generations leave effective selection at `NONE`.
3. Missing, corrupt, or conflicting evidence blocks selection.
4. Never fall back silently to stale fixed-path CSV files.
5. `EMPTY` represents a valid completed generation with no eligible records.
6. `EMPTY` must not be confused with missing or malformed input.
7. Preserve evidence distinguishing incomplete occurrence-level work from incomplete output artifacts.
8. Do not invent terminal states when evidence is unavailable.

This policy approval does not authorize code, pointer publication, recovery, tracker/history changes, or implementation of a new state transition. No individual name, approval date, or reviewer identity was supplied.

### Detailed semantics still requiring D6

The helper’s present validation constraints are evidence for the proposed model, not semantics approved by this D8a decision. D6 must still resolve exact completion and failure boundaries, occurrence accounting, all-skipped treatment, required artifacts/diagnostics, handling of valid zero-row input per stage, and terminal-record requirements after known failures. Missing/corrupt/conflicting metadata continues to block selection under the approved rules; that does not itself create a persisted `FAILED` or other terminal status.

For reference, the isolated helper currently validates these conditions:

| State | Existing helper constraint (still subject to D6; not production behavior) |
|---|---|
| `IN_PROGRESS` | Attempt has started but has no completion timestamp, accounting, or outputs; it is nonterminal. |
| `COMPLETE` | Nonempty source, zero failed occurrences, and the stage’s required output set validates. All-skipped input can satisfy the helper’s counter rule, but D6 must decide whether it is allowed and what evidence is required. |
| `EMPTY` | Valid zero-record source, all accounting counts are zero, and no data outputs. It is not a substitute for missing or malformed source input. |
| `PARTIAL` | Nonempty source, at least one failed occurrence and at least one processed occurrence, with all required stage outputs validating. It is not selectable by the approved D8a rule. |
| `FAILED` | Failure code is present and there are no outputs; optional source/accounting evidence, if present, must validate and reconcile. |

## Options considered; Option A selected by owner

| Option | Classification rule | Advantages | Costs and risks |
|---|---|---|---|
| **A. Adopt the existing five-state contract, with unknown evidence blocked — OWNER APPROVED, POLICY ONLY** | Use `COMPLETE`, `EMPTY`, `PARTIAL`, `FAILED`, and `IN_PROGRESS` only under their current helper constraints, subject to D6 approval of exact semantics. Keep interruption nonterminal when only `IN_PROGRESS` is evidenced. Missing/corrupt/conflicting metadata is unavailable/blocked, not a new persisted status. Invalid or incomplete output is never selectable. | Reuses the isolated schema and test vocabulary; distinguishes useful partial work, valid empty input, and confirmed failure; aligns naturally with D8b’s `NONE` pointer rule. | D6 still must approve exact accounting, skip, and artifact rules. An interrupted run can remain unresolved indefinitely without an authorized classification procedure. `PARTIAL` must not be confused with physically truncated output. |
| **B. Collapse every known unsuccessful/incomplete attempt into `FAILED`** | Valid success and valid empty input remain distinct; any recognized attempt that does not meet a full success/empty contract is `FAILED` and unselectable. A crash with no writable terminal record remains `IN_PROGRESS` or unavailable; it cannot be changed merely by restart. | Simpler terminal reporting and no `PARTIAL` policy branch for consumers. | Discards distinctions between useful partial processing and stage/publication failure; conflicts with current helper `PARTIAL` support and tests; does not solve missing or corrupt metadata and may require schema/compatibility changes. |
| **C. Add an explicit `INTERRUPTED` or `UNKNOWN` generation state** | Record abnormal termination or indeterminate outcome as a distinct state, separate from `FAILED` and `IN_PROGRESS`. | Makes interruption/uncertainty explicit for operators and audit review. | New schema and pointer behavior; consumers and external CSV/dashboard compatibility need review; helper rollback currently accepts only latest `FAILED` or `PARTIAL`; may blur actual interruption with a state that cannot be durably written after abrupt termination. D12 and D13 review would be needed before implementation. |

### Option A rationale (recorded recommendation)

Option A was recommended and is now owner-approved as policy only. The described helper constraints for `COMPLETE`, `EMPTY`, `PARTIAL`, `FAILED`, and `IN_PROGRESS` remain subject to D6. Under the approved rules, `PARTIAL` is nonselectable, failed/interrupted attempts have effective selection `NONE`, and missing/corrupt/conflicting evidence blocks without a fabricated terminal state or stale fixed-path fallback. D8b Option C remains separately approved policy only.

This approval does not decide whether every event can be durably classified. D6, D10, D12, and D13 remain decision/review dependencies.

## Evidence needed before any later implementation proposal

- Synthetic status/accounting matrix for nonempty complete, valid empty, all-skipped, all-failed, mixed processed/failed, and analyzer propagation.
- Fault injection before and after each artifact serialization, temporary-file flush/replace, between the two details outputs, manifest creation, and pointer publication.
- Restart snapshots after each boundary, including `IN_PROGRESS`, absent state, malformed state, mismatched hashes/sizes, missing required artifact, and conflicting manifest/pointer.
- Assertions that `COMPLETE`/`EMPTY` require validated evidence; `PARTIAL` never becomes automatically selectable; `FAILED`/interrupted leave selection `NONE`; prior generations remain intact; no stale fixed-path fallback occurs.
- Explicit evidence and audit contract for any terminal classification or rollback event, including authority under D10.
- D12 inventory and compatibility checks for consumers of fixed-path CSVs and their behavior when there is no selected generation.
- D13 independent Windows filesystem/security review of supported environments, output replacement, interruption/durability, reparse/path behavior, and concurrency before storage or publication claims are relied on.
- Synthetic/offline tests only; no browser, live search, application, or real submission workflow.

## Dependencies and decision status

- **D3/D5:** The owner approved strict input validation and evidence-based processing-failure classification as policy only, at the scope recorded in `PIPELINE_GENERATION_POLICY.md`. These decisions provide input/occurrence classifications; they do not assign generation terminal states or replace D6 accounting decisions.
- **D6:** Exact status, accounting, all-skipped, failed, empty, partial, and artifact rules are not established as owner-approved production policy.
- **D8b:** Option C — Explicit Rollback Authorization is **OWNER APPROVED — POLICY DECISION ONLY**. Its `NONE` selection rule applies after failed/interrupted attempts; it does not define how to detect interruption or establish a terminal status.
- **D10:** Rollback authority, authorization evidence, reason, and audit requirements must be defined before rollback implementation.
- **D12:** External CSV/dashboard consumers and handling of `NONE`, empty output, and no fallback remain unresolved.
- **D13:** Independent filesystem/security specialist review and environment-specific evidence remain required before persistent storage, publication, recovery, or durability implementation.

**Other approved policy context:** D4 Option 3 — Hybrid duplicate handling; D8 Option C — Evidence-Based Retry; D8 application selection Option B — Evidence-Based Selection. Each is policy-only and does not authorize implementation.

## Owner decision record

Selected option: **A — Existing Five-State Vocabulary**

Decision: **OWNER APPROVED — POLICY DECISION ONLY.**

Conditions: the five-state vocabulary and eight classification rules recorded above; detailed status semantics remain subject to D6 approval.

Decision source: project owner instruction in the current task. No individual name, approval date, or reviewer identity was supplied; none is inferred.

**Implementation authorization:** NOT GRANTED. **Response status:** POLICY APPROVED; D6-dependent details remain pending.
