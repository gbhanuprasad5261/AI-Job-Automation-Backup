# D6 Generation Accounting and Artifact Owner Worksheet

**Status:** The twelve expressly supported D6 principles and D6.Q1, D6.Q3 terminal accounting equation, D6.Q5, D6.Q6, and D6.Q8 are **OWNER APPROVED — POLICY DECISION ONLY** at the recorded scope. D6.Q2, D6.Q4, D6.Q7, D6.Q9, and D6.Q10 remain pending, as do unapproved technical details. This worksheet authorizes no implementation.

## Scope and approved context

D6 must decide how source occurrences are accounted for, what makes stage artifacts valid, how valid empty and all-skipped results are classified, and what evidence supports terminal statuses. D1 Option 3 (no authoritative source yet), D2 exact-byte identity/fingerprinting, D3 strict input validation, and D5 evidence-based classification are now **OWNER APPROVED — POLICY DECISION ONLY** at the exact scope in `PIPELINE_GENERATION_POLICY.md`; they do not authorize implementation. D1/D2 do not establish a current authoritative source or a completeness proof threshold. D8a Option A — Existing Five-State Vocabulary is **OWNER APPROVED — POLICY DECISION ONLY**, subject to D6 approval of detailed semantics. D8b Option C — Explicit Rollback Authorization is also policy-approved only: failed/interrupted attempts leave effective selection `NONE`; previous complete generations remain preserved and require authorized rollback to reselect.

Other relevant approved policy-only decisions: D4 Option 3 — Hybrid duplicate handling; D8 application selection Option B; D8 retry Option C. None authorizes implementation.

## Existing D6 records and unresolved questions

The main register’s D6 recommendation is: a valid zero-row input = `EMPTY`; all required extraction failed = `FAILED`; useful processed results plus failed occurrences = `PARTIAL`; and nonempty all-skipped input may be `COMPLETE` only with approved skip rules and a required ledger. That is a recommendation, not an owner decision. D6 remains open.

The isolated contracts do not agree on every edge case:

- `pipeline_generation_store.py` v1 uses aggregate `source_records`, `processed_records`, `intentionally_skipped_records`, and `failed_records`. It validates conservation, but does not require a per-row ledger. Its `PARTIAL` rule requires at least one failed and at least one processed record. `EMPTY` requires zero source/accounting counts. `COMPLETE` requires nonempty source and zero failures, and permits all-skipped counts.
- `tools/provenance_manifest_schema.py` v2 and the offline verifier use `source_occurrences`, `processed_occurrences`, `intentional_skip_occurrences`, `failed_occurrences`, and `output_rows`, plus a per-occurrence ledger. Source occurrences reconcile to processed + skipped + failed. A terminal ledger has no `UNPROCESSED` disposition. In this proposal `EMPTY` can describe zero source rows or nonempty all-skipped input; both all-skipped `EMPTY` and all-skipped `COMPLETE` produce unresolved D6 findings. `PARTIAL` with failures but zero processed occurrences also remains unresolved in parts of the proposal/tests.
- Neither contract is wired into production. Production stages use fixed-path CSVs and do not persist generation manifests, occurrence ledgers, or these accounting statuses.

## Accounting findings and proposed accounting unit

### What the current contracts count

The v1 helper’s source `record_count` and accounting totals are row counts. The v2 proposal explicitly names source **occurrences** and assigns each source row a 1-based ordinal and source-hash-bound occurrence key. Duplicate rows remain separate occurrences even when their logical identity is the same. The synthetic lifecycle tests confirm two identical input rows count as two source/processed occurrences. The occurrence ledger also stores `logical_identity`, but does not aggregate counts by unique identity.

The v2 proposal currently has no `expected_occurrences`, `discovered_occurrences`, or `remaining_occurrences` field. `source_occurrences` is the row count in the captured source snapshot. It must not be treated as a search result expectation or proof that acquisition was complete. Collection evidence has separate status/counter concepts and is not integrated as generation accounting.

| Quantity | Current evidence | Owner decision needed |
|---|---|---|
| **Expected source occurrences** | Not a generation manifest field. A search limit or query is not itself a proven expected row count. | Track only when an upstream producer can establish an exact expected set/count; otherwise record as unknown/not applicable, not zero. Decide whether this belongs in D1/source acquisition or D6 stage accounting. |
| **Discovered occurrences** | Source snapshot `record_count` describes parsed rows in the exact snapshot. It does not say whether collection discovery was complete. | Define discovery at a named pipeline boundary and retain completeness evidence from the upstream source process. Do not claim discovered = expected unless supported. |
| **Source occurrences** | v2 uses one occurrence per parsed source row, with ordinal and occurrence key. Duplicate source rows are distinct. | Recommend this as the conservation/accounting unit for each stage. Preserve a separate logical identity for duplicate policy decisions. |
| **Processed occurrences** | v1 aggregate count; v2 count plus one ledger disposition/output-row reference per processed occurrence. | Define whether “processed” means required stage work completed, regardless of eligibility or quality, and bind each processed occurrence to exactly one output row or an explicitly approved output rule. |
| **Skipped occurrences** | v1 aggregate intentional skip count; v2 `INTENTIONAL_SKIP` requires a reason and policy rule ID. A retained-occurrence reference is optional in the schema. | Count each skipped input occurrence once. Require a specific approved skip rule/reason. For D4-authorized deduplication, require references to the retained occurrence(s); ambiguous identity is not an intentional skip. |
| **Failed occurrences** | v1 aggregate count; v2 `FAILED` disposition requires an error code and no output row. | Count each occurrence whose required work failed. Decide separately how stage-level failures that prevent per-occurrence processing are recorded. |
| **Remaining/unprocessed occurrences** | No field/disposition in current terminal accounting. `IN_PROGRESS` has no accounting in helper v1/v2. | Recommend terminal `COMPLETE`/`EMPTY`/`PARTIAL` ledgers leave zero unaccounted occurrences. Decide whether `IN_PROGRESS` checkpoints may record pending/remaining occurrences; do not relabel unobserved remainder as failed. |
| **Output rows** | v2 records this separately and requires it to match the primary output descriptor; processed occurrence row references must cover output rows exactly once. | Preserve as a distinct count. It need not equal source occurrences when skips/failures occur. Define whether rows can be emitted for non-processed dispositions (recommend no absent an explicit rule). |
| **Unique identities** | Not an aggregate accounting unit. The v2 schema includes `logical_identity` per occurrence but does not deduplicate counts by it. | Recommend no unique-identity denominator for D6 conservation. Use D4 identity evidence only to classify verified duplicate dispositions while preserving every source occurrence reference. |

### Candidate conservation rule

For a fully classified source snapshot:

`source_occurrences = processed_occurrences + intentional_skip_occurrences + failed_occurrences`

For a terminal result, `remaining_occurrences = 0` by derivation if every source occurrence has exactly one disposition. For nonterminal `IN_PROGRESS`, the current contracts do not define a checkpoint/remaining ledger. The owner must decide whether to add one later or leave the attempt explicitly incomplete; no journal or checkpoint implementation is authorized here.

**Synthetic examples (illustrative only):**

| Scenario | Source occurrences | Processed | Skipped | Failed | Output rows | Observation |
|---|---:|---:|---:|---:|---:|---|
| Two identical source rows, both processed | 2 | 2 | 0 | 0 | 2 | Two occurrence keys; one logical identity may repeat. |
| Verified duplicate skip, first retained | 2 | 1 | 1 | 0 | 1 | Skip needs approved D4 rule/reason and retained-occurrence reference. |
| Two intentional skips | 2 | 0 | 2 | 0 | 0 | All-skipped status remains a D6 decision; preserve both reasons. |
| One processed and one failed | 2 | 1 | 0 | 1 | 1 | Candidate `PARTIAL` only if the configured threshold and all required artifacts validate. |
| Four source rows, process stopped after one | 4 | 1 | 0 | 0 | 1 | Not a reconciled terminal ledger; do not call it `PARTIAL` without an approved checkpoint/disposition rule. |

## Artifact-validity findings

### Required output roles in isolated contracts

| Stage | Required roles in v2 proposal | Current fixed-path production outputs |
|---|---|---|
| Source | `jobs_csv` (`jobs.csv`) | `job_search.py` names `jobs.csv`; production collection publication is closed and returns `False`. `job_scraper.py` returns rows but does not establish authoritative publication. |
| `job_details` | `details_csv` (`job_details.csv`) and `diagnostics_json` (`job_details_diagnostics.json`) | `data/job_details.csv` and `data/job_details_diagnostics.json`, written sequentially. |
| `job_analyzer` | `analysis_csv` (`job_analysis.csv`) | `data/job_analysis.csv`. |

For the v1 generation-store helper, manifest output roles/paths are fixed per stage; descriptors contain SHA-256 and byte size but not output row count/format. The v2 manifest proposal also records output row count and format. Both use source fingerprints; v2 records encoding/format, source row count, run ID, and downstream input-generation references that bind manifest hash, artifact role/hash, byte size, row count, and format. The source snapshot/output must agree. Downstream source must match its upstream artifact reference.

The v1 helper validates descriptor shape and, when asked to read artifacts, checks actual bytes against size/hash. It does not parse CSV structure. The separate offline verifier receives artifact bytes, checks required roles/paths/formats, verifies SHA-256 and size, parses strict UTF-8 CSV, requires the exact expected header and consistent row width, and checks parsed row count against the descriptor. It also checks cross-stage source-generation identity/fingerprint/format/row-count bindings and occurrence-to-output-row accounting. These validators are isolated; none is production-integrated or a Windows filesystem/security approval.

### Artifact edge cases

- **Missing role/file:** v2 verifier rejects missing required roles or bytes. A missing artifact is not a valid empty artifact.
- **Zero-byte CSV:** descriptor schemas allow a nonnegative size of zero, but the offline CSV parser rejects empty bytes because the required header is absent. Exact hash/size alone is insufficient.
- **Zero-byte diagnostics JSON:** JSON parser requires valid JSON of the expected shape; an empty byte string is not valid diagnostics. The synthetic valid empty diagnostics payload is `[]`.
- **Header-only CSV:** strict parsing accepts the exact header with zero data rows and row count 0. That proves structural validity only; it does not decide whether the generation is `EMPTY`, all-skipped `COMPLETE`, or another policy state.
- **Malformed CSV:** strict CSV parsing, exact header comparison, and row-width checks reject malformed/incorrect headers and inconsistent rows, even if hashes match the bytes supplied to the verifier. Duplicate or missing header fields fail exact-header comparison.
- **Partial multi-file replacement:** `write_replaced_output()` uses a temporary sibling and `os.replace()` for one destination at a time. Details CSV is replaced before diagnostics JSON. A later failure can leave outputs from different attempts. This is not a transaction and there is no production manifest binding the pair.

## Empty and all-skipped scenarios — keep separate

| Scenario | Evidence distinction | D6 question; do not infer a shared status |
|---|---|---|
| **Valid empty source** | Captured source is valid (for CSV, expected header is present) and has zero data rows. A v2 source `EMPTY` still has a source snapshot/output descriptor; source byte size need not be zero. | Recommend `EMPTY` for a validated zero-row source. Decide downstream propagation and ensure old outputs are not exposed. |
| **Nonempty source with zero eligible records** | Source has rows; output eligibility may be zero even if rows were processed and represented as ineligible. | Does `EMPTY` mean zero eligible output rows, zero output rows, or zero source rows? Keep source/disposition counts so this differs from a genuinely empty source. |
| **All records intentionally skipped** | Nonempty source; every occurrence has an approved skip reason/rule; zero processed/output rows. | The v2 proposal flags both `EMPTY` and `COMPLETE` all-skipped variants as unresolved. Decide one state and whether any skipped source can be `COMPLETE`. Do not infer from zero output alone. |
| **All records filtered as duplicates** | Every repeated row remains a distinct source occurrence. Verified deduplication needs approved identity/rule and retained-occurrence references; ambiguous identities block. | Decide whether verified duplicate elimination is an `INTENTIONAL_SKIP` disposition or a distinct disposition and which status applies when all occurrences are so classified. D4 requires occurrence references; the v2 retained reference field is currently optional. |
| **Missing source** | No valid captured input exists; there is no trustworthy source row count/fingerprint. | Never call this `EMPTY`. Decide whether a known invocation records `FAILED` with a stable source-missing code or remains unavailable when no terminal manifest can be written. |
| **Malformed source** | Bytes exist but fail encoding, CSV syntax, header/schema, or row-width checks. | Never call this `EMPTY`. Decide terminal `FAILED` evidence and whether original bytes/diagnostics are retained outside selectable outputs. |
| **Output containing headers only** | Valid CSV structure with exact header and zero data rows. | Treat as structurally valid only. Status depends on input rows and dispositions; it could accompany a valid empty source or an all-skipped result. Decide whether each role permits header-only output or requires no data artifact for `EMPTY`. |
| **Output generation interrupted** | Some temporary/replaced files may exist; there may be no valid terminal manifest or outputs may span attempts. | Keep selection `NONE`. Do not infer `PARTIAL` from file presence. Use `IN_PROGRESS` only if that record is validly present; otherwise block as unavailable/unknown without inventing terminal state. |

## Terminal-state semantics and transition proposal

The names are approved under D8a, but the detailed D6 semantics below remain undecided. These candidate criteria preserve evidence boundaries and do not assert that current production transitions exist.

| State | Candidate evidence/entry condition for owner decision | Candidate restart/selection behavior under approved D8 policy |
|---|---|---|
| **`IN_PROGRESS`** | Attempt has a valid start record and no validated terminal outcome. Current helper constraints leave source/accounting/outputs unset. | Nonterminal; effective selection `NONE`. Restart is not proof of success or failure. Decide whether a durable checkpoint can account pending occurrences; no recovery journal is authorized. |
| **`COMPLETE`** | Valid nonempty generation; every source occurrence has a reconciled disposition; no failed occurrences; required artifacts and cross-stage references validate. Decide whether all-skipped input qualifies and whether “complete” requires any processed/eligible output. | Eligible for validation/selection only under approved pointer/candidate rules. Never select based on status label alone. |
| **`EMPTY`** | Valid completed input/result with no eligible records under D8a. D6 must decide whether this includes zero source rows, nonempty all-skipped input, filtered rows, or some distinct subset. Required source snapshot and accounting distinguish these cases. | Represents zero eligible candidates; never means missing/malformed input. Do not fall back to older fixed-path output. |
| **`PARTIAL`** | Some required occurrence work succeeded and some failed, with reconciled occurrence accounting and all artifacts required for a diagnostic partial generation valid. Decide minimum useful-work threshold and whether all-failed is ever `PARTIAL`. | Nonselectable per D8a. Effective selection `NONE`; preserve diagnostics/evidence. Partial physical files without a complete valid declared artifact set do not meet this criterion. |
| **`FAILED`** | A known stage/source/publication failure is evidenced with a stable failure code; no selectable output set is declared. Decide whether/how partial occurrence accounting and diagnostics survive. | Nonselectable; effective selection `NONE`. Prior `COMPLETE` remains preserved and unselected until separately authorized D8b rollback. |

**Candidate transitions:** `IN_PROGRESS` may reach `COMPLETE`, `EMPTY`, `PARTIAL`, or `FAILED` only when the selected D6 evidence threshold is satisfied and a valid terminal record is persisted. If the terminal outcome cannot be written or validated, retain a validated `IN_PROGRESS` record if one exists; otherwise report unavailable/blocked. Do not infer a transition from process restart, missing files, output presence, or absence of an error record. This is a proposed rule for owner review, not an implementation.

## Exact owner decision questions and options

For each question, select/revise an option and give any conditions/evidence. A choice in one row does not close the others.

| # | Owner question | Options | Recommendation for owner consideration |
|---|---|---|---|
| **1. Accounting boundary/unit** | What is one source occurrence, and where does accounting begin: upstream expected search scope, discovered candidates, or rows in one immutable captured source snapshot? | **A.** Count rows in the captured snapshot as source occurrences; record expected/discovered collection evidence separately when authoritative. **B.** Count only unique logical identities. **C.** Track expected, discovered, and captured rows as separate quantities with producer provenance. | **A with C’s separate provenance when known.** Keep per-row occurrences as the conserved unit; do not treat an unknown search expectation as zero or as complete. |
| **2. Duplicate accounting** | How are duplicate source rows counted and dispositioned? | **A.** Preserve/count every occurrence; verified dedup may disposition an occurrence as a skip under D4 with reason, rule, and retained-row reference. **B.** Collapse verified duplicates before D6 accounting but retain a side map. **C.** Fail any source with duplicates. | **A**, aligned with D4 hybrid policy. Ambiguous duplicate identities block; do not aggregate by unique identity. |
| **3. Required ledger and counts** | Which counts and per-occurrence evidence must each terminal manifest contain? | **A.** Source, processed, skipped, failed counts plus one ledger disposition/output-row reference per source occurrence; remaining is zero for terminal runs and derived. **B.** Aggregate counts only. **C.** Add explicit pending/remaining dispositions and checkpoint fields for `IN_PROGRESS`. | **A for terminal states.** Decide separately whether to design checkpoints in a later authorized phase; do not invent a recovery journal. |
| **4. Artifact roles/validity** | Which artifacts are required per stage/status, and is a header-only file valid? | **A.** Require exact stage role set and validated fingerprints/format/header/row count; status-specific empty/failed output rules. **B.** Allow any available subset with diagnostics marking gaps. **C.** Make all outputs optional and trust aggregate status. | **A**, with D7 review. Require exact bytes to match manifest; missing/corrupt/malformed output blocks. Decide header-only behavior per role/status. |
| **5. Manifest/source identity** | Which source identity is required for a terminal generation and for cross-stage inputs? | **A.** Bind one exact captured byte snapshot using role, format/encoding, row count, SHA-256 and size; downstream manifests reference exact upstream run/manifest/artifact fingerprints. **B.** Use path and modification time. **C.** Hash canonicalized records only. | **A**, subject to D1/D2 and D13: it is auditable and avoids parsing one byte set while fingerprinting another. SHA-256 alone does not prove safe filesystem containment. |
| **6. Valid empty / zero eligible output** | When is `EMPTY` correct: zero source rows, no eligible output rows after filtering, or both? How do header-only outputs and retained ineligible rows affect it? | **A.** `EMPTY` only for a valid zero-row source. **B.** `EMPTY` for any valid completed stage with zero eligible output, including nonempty all-skipped input. **C.** Distinguish source-empty from result-empty in accounting/manifest fields while retaining the five-state vocabulary. | **C** if representable without adding an unapproved terminal state; otherwise prefer **B** to honor D8a’s “no eligible records” meaning while retaining source/disposition evidence. Do not confuse either with missing/malformed input. |
| **7. All-skipped and all-duplicate** | Can a nonempty run with every occurrence intentionally skipped be `EMPTY`, `COMPLETE`, or `FAILED`? Does verified all-duplicate elimination have the same rule? | **A.** `EMPTY` when zero eligible rows and every occurrence has an approved skip disposition. **B.** `COMPLETE` because accounting completed, even with no processed rows. **C.** `FAILED` because no work was processed. Define duplicate skip references under D4 separately. | **A** only with approved rule IDs and full retained-occurrence evidence; ambiguous duplicates block. Keep zero-source `EMPTY` distinguishable in the ledger/source descriptor. |
| **8. Partial threshold** | When is a terminal result `PARTIAL` versus `FAILED`, particularly for one useful result plus failures, all failures, stage-level failure, or invalid output? | **A.** `PARTIAL` requires at least one processed and one failed occurrence, reconciled counts, and a fully valid required artifact set; all-failed or invalid publication is `FAILED`. **B.** Any failure with any diagnostic output is `PARTIAL`. **C.** Every failure makes the stage `FAILED`; no `PARTIAL`. | **A**, consistent with the stricter v1 helper threshold and current v2 verifier; separately decide terminal all-failed and stage-level failure evidence. |
| **9. Terminal evidence/restart** | What proof permits a terminal label, and how should restart treat missing/corrupt manifests, missing outputs, or interrupted publication? | **A.** Persist `COMPLETE`/`EMPTY`/`PARTIAL`/`FAILED` only with validated evidence; otherwise keep valid `IN_PROGRESS` or report unavailable/blocked. **B.** Infer `FAILED` from any nonterminal state at restart. **C.** Add an `UNKNOWN`/`INTERRUPTED` persisted state. | **A**, aligned with D8a and D8b. Do not promote status or write a new state from absence alone. |

## Owner decision record — partial policy approval

The project owner authorized the supported D6 recommendations below as **OWNER APPROVED — POLICY DECISION ONLY**. This is not implementation authorization. The owner did not supply a name, date, or reviewer identity; none is inferred.

| Worksheet question | Approved portion | Still pending |
|---|---|---|
| **1. Accounting boundary/unit** | Count each row in the captured source snapshot as an individual occurrence; use Option A for expected/discovered quantities: record expected only when supplied by an authoritative source, otherwise `UNKNOWN`, never zero; a fingerprint alone does not prove completeness. | Current source has no authoritative expected count; no source completeness claim is supported. This evidence limitation does not reopen the approved accounting rule. |
| **2. Duplicate accounting** | Preserve duplicate occurrences and their source references; do not count only unique identities. | Exact duplicate disposition/schema fields and how verified deduplication is recorded under D4 identity rules. |
| **3. Required ledger and counts** | Require exactly one mutually exclusive disposition per captured occurrence; reconcile `captured = processed + skipped + failed + unprocessed`; preserve the four dispositions; an occurrence not reached is `UNPROCESSED`, not `FAILED`; an evidenced terminal `FAILED` generation may contain explicitly accounted `UNPROCESSED` occurrences. | Manifest field names, output-row linkage, checkpoint durability, and terminal mapping beyond this approved equation remain open. Do not invent dispositions when evidence is unavailable. |
| **4. Artifact roles/validity** | A generation is not selectable until its required artifacts validate. A header-only CSV alone is not sufficient proof of `EMPTY`; required accounting evidence is also necessary. | Exact required roles by stage/status, byte/format/header/row-count checks, and whether header-only artifacts are valid for each role. D7 remains a dependency. |
| **5. Manifest/source identity** | Preserve source fingerprints and cross-stage consistency evidence. | Exact fingerprint fields/algorithm/encoding, manifest format, and snapshot/acquisition contract. |
| **6. Valid empty / zero eligible output** | Distinguish a valid zero-row source from a valid completed result with zero eligible output; preserve the evidence for each; zero output alone does not prove completeness. | Other state semantics and role-specific artifact rules remain subject to D6/D7/D12. |
| **7. All-skipped and all-duplicate** | For fully accounted all-skipped runs, `EMPTY` is permitted only when every occurrence has an approved skip reason, accounting is reconciled, and required artifacts validate; preserve occurrences and skip evidence; zero output alone is insufficient. D4/D6 occurrence preservation remains approved. | All-duplicate status and exact duplicate disposition/identity remain pending under Q7/D9; no automatic `EMPTY` inference. |
| **8. Partial threshold** | `PARTIAL` requires processed and failed occurrences, reconciled occurrence accounting, and valid required artifacts; `PARTIAL` remains nonselectable. | All-failed and stage-level failure mapping, artifact roles, and technical publication validation remain open. |
| **9. Terminal evidence/restart** | Missing, corrupt, or conflicting evidence blocks selection; no silent stale fixed-path fallback. Do not invent a terminal state when outcome evidence is unavailable. Q3 additionally permits an evidenced terminal `FAILED` ledger to retain explicitly accounted `UNPROCESSED` occurrences. | Whether an interrupted attempt with valid `IN_PROGRESS` metadata remains there, when a known failure becomes `FAILED`, and the exact restart classification when metadata is absent. |

### Approved D6 rules

1. Count each row in the captured source snapshot as an individual occurrence.
2. Preserve duplicate occurrences and their source references.
3. Require explicit terminal accounting for every occurrence.
4. Distinguish processed, skipped, failed, and unprocessed occurrences.
5. Require validated required artifacts before a generation becomes selectable.
6. Distinguish valid `EMPTY` results from missing, malformed, or unavailable input.
7. Do not automatically classify all-skipped or all-duplicate outcomes as `EMPTY` without valid accounting.
8. Keep `PARTIAL` generations nonselectable.
9. Missing, corrupt, or conflicting evidence blocks selection.
10. Never invent a terminal state when outcome evidence is unavailable.
11. Preserve source fingerprints and cross-stage consistency evidence.
12. Do not treat a header-only CSV as sufficient proof of a valid `EMPTY` generation without the required accounting evidence.

All twelve are **OWNER APPROVED — POLICY DECISION ONLY** at the scope stated. Unresolved details in the table above remain pending; this approval does not authorize code, schema, data, or production changes.

## D6 detailed owner decision package — approved and pending items

The choices and recommendations below are decision support, with owner responses recorded per question. The five approved responses are policy-only; they do not authorize implementation or establish unapproved state transitions. Q2, Q4, Q7, Q9, and Q10 remain **PENDING OWNER DECISION**. Existing helper/schema/verifier behavior is descriptive evidence, not binding policy.

### 1. Expected versus discovered occurrence counts

**Decision question:** Should a generation account only for rows in its captured source snapshot, or must it also account for upstream expected and discovered quantities? If upstream quantities are unavailable or not authoritative, what must the manifest say?

- **A. Captured snapshot is the accounting boundary.** Conserve one occurrence per row in the immutable captured snapshot; record expected/discovered quantities only as separately sourced metadata when the producer provides reliable evidence.
- **B. Require all three quantities.** Require expected, discovered, and captured counts and block terminal classification if any cannot be established.
- **C. Captured count only.** Do not record upstream expected/discovered quantities.

**Approved decision — Option A, POLICY ONLY:** Count captured snapshot rows as individual occurrences. Record an expected count only when an authoritative source supplies it; otherwise record `UNKNOWN`, never zero. A fingerprint alone does not prove completeness.

**Evidence to require:** Source snapshot fingerprint and parsed row count; producer/acquisition evidence and its scope for any expected/discovered figures; explicit unavailable/unknown representation rather than zero; reconciliation of captured rows against the occurrence ledger.

**Dependencies:** D1/D2 define acquisition scope and producer evidence; D6 sets accounting policy; D13 validates storage/fingerprint assumptions.

**Owner response:** **OWNER APPROVED — OPTION A — POLICY DECISION ONLY.** Count captured snapshot rows as individual occurrences; record expected count only with an authoritative source; unavailable expected count is `UNKNOWN`, never zero; a fingerprint alone does not prove completeness.

### 2. Exact dispositions for duplicate occurrences

**Decision question:** When D4 hybrid handling identifies duplicate rows, how is each occurrence represented and what terminal disposition may it receive?

- **A. Preserve every occurrence.** Each row keeps its own ordinal/source reference and receives its own disposition. A verified redundant occurrence may be recorded as an intentional skip with a reason/rule and reference to the retained occurrence; unresolved identity stays unresolved and cannot be silently collapsed.
- **B. Deduplicate before the D6 ledger.** Retain a separate source-to-retained mapping, but count only retained rows in the main ledger.
- **C. Treat any duplicate as a generation failure.**

**Recommendation:** A, consistent with already approved D4 hybrid handling and D6’s approved occurrence unit. The exact identity, alias, and reason-code rules remain governed by D4 and must not be invented in D6.

**Evidence to require:** Stable source-row ordinal/reference for each occurrence; D4 identity decision and rule version; retained-occurrence reference for each dedup skip; reason code; reconciliation proving no occurrence disappeared. Conflicting/ambiguous identities block disposition pending review.

**Dependencies:** D1/D2 source snapshot, ordering, and occurrence references; approved D4 Hybrid policy; D9 verified identity, URL alias, collision, and retained-occurrence rules; D3/D5 dispositions; D6 occurrence ledger; D13 validation of safe source references. D4’s high-level approval does not settle D9 identity details.

**Owner response:** Option: ____  Conditions or edits: ____  Rationale: ____

### 3. Manifest fields and accounting equation

**Decision question:** What minimum occurrence-level evidence and conservation equation must a terminal manifest carry, and how are unresolved occurrences represented for nonterminal attempts?

- **A. Per-occurrence terminal ledger.** Record captured-source occurrence count and exactly one mutually exclusive disposition per occurrence: `PROCESSED`, `SKIPPED`, `FAILED`, or `UNPROCESSED`. Reconcile terminal occurrence counts using `captured = processed + skipped + failed + unprocessed`. An occurrence not reached remains `UNPROCESSED`, not `FAILED`; a terminal `FAILED` generation may contain explicitly accounted `UNPROCESSED` occurrences when supported by evidence. Do not invent a disposition when evidence is unavailable. Separately bind processed occurrences to output rows where the stage emits rows.
- **B. Aggregate counts plus source/output fingerprints.** No row-level ledger; require counts to reconcile and trust the manifest producer.
- **C. Per-occurrence ledger for terminal attempts and explicit unprocessed/pending dispositions for `IN_PROGRESS`.** Define checkpoint semantics as part of this decision.

**Approved decision — Option A for the terminal equation, POLICY ONLY:** Require exactly one mutually exclusive disposition per captured occurrence and reconcile terminal counts with the equation above. Preserve all four dispositions. An occurrence not reached is `UNPROCESSED`, not `FAILED`; a terminal `FAILED` generation may include explicitly accounted `UNPROCESSED` occurrences only when evidence supports them. Do not invent dispositions when evidence is unavailable. This approval does not define checkpoint durability, manifest fields, or restart transitions.

**Evidence to require:** Source row ordinal/reference, disposition, reason/rule for skips and failures, output-row mapping where applicable, source fingerprint, consistent aggregate totals, and immutable manifest identity. For checkpoints, specify durability and restart evidence before allowing them to support transitions.

**Dependencies:** D1/D2 exact-byte identity policy is approved, but no authoritative source or completeness proof exists; D3/D5 meanings are approved only at their recorded scope. D4 duplicate direction is approved; D9 exact identity references, D8 retry/restart rules, D10 audit authority, and D13 integrity/durability review remain dependencies. The terminal equation remains this D6 owner decision; checkpoint semantics remain a separate technical gate. No recovery journal or schema is authorized here.

**Owner response:** **OWNER APPROVED — OPTION A (TERMINAL ACCOUNTING EQUATION ONLY) — POLICY DECISION ONLY.** Checkpoint semantics, manifest fields, output linkage, and other terminal-state mappings remain open.

### 4. Required artifact roles and per-role validation

**Decision question:** Which artifact roles are mandatory for each stage and status, and which validations are required before the manifest can support terminal classification or selection?

- **A. Exact status-specific role set.** Require each declared role and validate safe path containment, existence, nonzero/allowed size, hash, byte format/encoding, headers, row widths/counts, and upstream/downstream binding as applicable. Define explicit exceptions for intentionally empty roles.
- **B. Data artifacts required; diagnostics optional.** Validate data roles strictly; missing diagnostics do not block, but their absence is recorded.
- **C. Any available subset.** Record missing roles and permit status if aggregate accounting reconciles.

**Recommendation:** A for roles required by the stage/status, with D7 deciding the role matrix and diagnostics policy. Existing isolated contracts show role-specific outputs and fingerprint/count checks; they do not prove that the current production stages emit a durable atomic artifact set. Do not select based on status alone.

**Evidence to require:** D7-approved role matrix; manifest role/path and artifact hash/size/format/count; strict parse and schema validation; exact headers and row widths; cross-stage manifest/artifact fingerprint match; synthetic cases for missing, zero-byte, malformed and mismatched artifacts. Header-only CSV validity must be decided by role and status and never alone establish `EMPTY`.

**Dependencies:** D7 artifact contracts; D12 external reader/header compatibility; D13 filesystem containment, atomicity, durability, and concurrency review; D6 status/accounting semantics.

**Owner response:** Option: ____  Conditions or edits: ____  Rationale: ____

### 5. `EMPTY` semantics

**Decision question:** Which validated outcomes may receive the existing `EMPTY` state, while preserving the distinction between no source rows and nonempty input yielding zero eligible records?

- **A. Source-empty only.** `EMPTY` requires a valid captured source with zero rows and valid required empty-result evidence; nonempty zero-eligible outcomes use another approved state.
- **B. Zero eligible result.** `EMPTY` means valid completed processing produced zero eligible records, including zero-row input and potentially fully accounted skipped/duplicate input, with accounting retaining the source distinction.
- **C. Preserve source-empty and completed-result-empty as distinct evidence under the existing five-state vocabulary; retain required separate rules for all-skipped and all-duplicate outcomes.**

**Approved decision — Option C, POLICY ONLY:** Distinguish a valid zero-row source from a valid completed result containing zero eligible output; preserve evidence for each and do not infer completeness from zero output. The separate Q6 all-skipped rule is approved below; Q7 all-duplicate classification and D12 consumer semantics remain open. This preserves D8a’s five-state vocabulary and does not treat absent/malformed input as empty.

**Evidence to require:** Valid source snapshot/fingerprint and row count; complete occurrence accounting; status-specific output role validation; evidence of eligibility/filter decisions; proof that input was available and parsed; downstream reader behavior. A header-only CSV is insufficient by itself.

**Dependencies:** D1/D2 source capture and parse validity; D3/D5 filtering and quality definitions; D7 artifact roles; D12 reader semantics; D13 integrity review.

**Owner response:** **OWNER APPROVED — OPTION C — POLICY DECISION ONLY.** Preserve distinct evidence for valid zero-row source and valid completed zero-eligible result; zero output alone does not establish completeness.

### 6. Fully accounted all-skipped runs

**Decision question:** If a nonempty source is valid and every occurrence has a valid intentional-skip disposition, which five-state classification is permitted?

- **A. `EMPTY`.** Only if all skip rules are approved, all occurrences reconcile, and the result has zero eligible records; retain explicit evidence that source was nonempty and why each row was skipped.
- **B. `COMPLETE`.** Accounting completed successfully even though no occurrence was processed into eligible output; record zero eligible rows and all skips.
- **C. Keep classification unresolved/blocked until a dedicated state-specific rule is approved.** Do not label it `EMPTY` or `COMPLETE` by inference.

**Approved decision — Option A conditionally, POLICY ONLY:** `EMPTY` is permitted only when every occurrence has an approved skip reason, accounting is reconciled, and required artifacts are valid. Preserve source occurrences and skip evidence. Zero output alone does not establish `EMPTY`.

**Evidence to require:** One valid skip disposition per captured occurrence, approved reason/rule, valid source and output evidence, zero unresolved/failed occurrences, and a demonstrated zero-eligible result. Missing or invalid evidence blocks classification.

**Dependencies:** D1/D2 valid source evidence; D3/D5 skip and eligibility rules; D4 approved duplicate direction; D7 output/diagnostic roles; D12 consumer meaning of empty outputs; D13 integrity review where publication claims are involved.

**Owner response:** **OWNER APPROVED — OPTION A, CONDITIONAL — POLICY DECISION ONLY.** Conditions: every occurrence has an approved skip reason; accounting is reconciled; required artifacts validate; source occurrences and skip evidence are preserved. Zero output alone is insufficient.

### 7. Fully accounted all-duplicate runs

**Decision question:** If every row is accounted for as a verified duplicate of a retained occurrence, but no eligible retained output remains for this stage, may the attempt be `EMPTY`, `COMPLETE`, `FAILED`, or must it remain unclassified pending additional evidence?

- **A. `EMPTY` only when D4-approved deduplication leaves zero eligible output and the retained/removed occurrence mapping is complete.**
- **B. `COMPLETE` whenever deduplication and accounting complete successfully, including zero eligible output.**
- **C. Block classification until the dedup rule and retained-output semantics establish whether this is a valid zero-eligible result.**

**Recommendation:** C as the present decision; it is the only choice that does not assume duplicate policy implies a result state. D4 approves hybrid duplicate handling, but exact identity, alias, and retained-row rules remain technical/policy prerequisites. Do not count duplicate identities instead of source occurrences.

**Evidence to require:** Per-occurrence mapping to retained occurrence, D4 rule/version, identity confidence/evidence, accounting reconciliation, stage output and cross-stage consistency checks, and proof whether any retained occurrence is eligible for this stage.

**Dependencies:** D1/D2 source occurrence references; D4 approved Hybrid policy; D9 identity/alias/collision and retained-occurrence rules; D3/D5 eligibility and extraction criteria; D7 artifact contract; D12 behavior for zero outputs; D13 validation of persisted references if used.

**Owner response:** Option: ____  Conditions or edits: ____  Rationale: ____

### 8. `PARTIAL` thresholds

**Decision question:** What minimum successful work and valid evidence distinguish `PARTIAL` from `FAILED`, including all-failed, stage-level failure, unresolved occurrences, and artifact publication failure?

- **A. Useful-work threshold.** `PARTIAL` requires at least one processed occurrence, at least one failed occurrence, complete occurrence reconciliation (including any permitted unprocessed count), and a fully valid required diagnostic/output role set. All-failed is `FAILED` only if a valid failure outcome is evidenced; invalid/incomplete artifact publication blocks terminal classification.
- **B. Any mixed outcome.** Any run with at least one success and any failure may be `PARTIAL`; diagnostics/artifact gaps are allowed but recorded.
- **C. No `PARTIAL`.** Any occurrence or stage failure makes the generation `FAILED`.

**Approved decision — Option A, POLICY ONLY:** Require at least one `PROCESSED` and one `FAILED` occurrence, reconciled occurrence accounting, and valid required artifacts. `PARTIAL` remains nonselectable under the existing approved D8a policy.

**Evidence to require:** Reconciled occurrence ledger; at least one processed and one failed occurrence if A is chosen; explicit stage failure code where applicable; valid declared artifacts; distinction between incomplete occurrence work and incomplete output publication; restart/synthetic boundary cases.

**Dependencies:** D3/D5 input and failure taxonomy; D7 partial diagnostics and artifact contract; D8 selection/retry rules; D10 audit evidence; D13 publication-integrity validation.

**Owner response:** **OWNER APPROVED — OPTION A — POLICY DECISION ONLY.** Require processed and failed occurrences, reconciled occurrence accounting, and valid required artifacts; `PARTIAL` remains nonselectable under D8a.

### 9. Interrupted-run accounting

**Decision question:** After interruption, what may be recorded about occurrences whose work may have happened but whose durable outcome evidence is absent or incomplete?

- **A. Evidence-only accounting.** Preserve only dispositions supported by durable validated evidence. Mark all remaining occurrences unprocessed only when a durable checkpoint proves that they were not processed; otherwise their outcome remains unavailable and blocks a terminal classification.
- **B. Infer unprocessed from missing result rows.** Treat occurrences without output rows as unprocessed and retry them.
- **C. Infer failure from interruption.** Mark all unconfirmed occurrences failed and terminalize as `FAILED`.
- **D. Add an `INTERRUPTED` state.**

**Recommendation:** A. It follows the approved five-state vocabulary and the approved rule not to invent terminal states. B and C assume absence of output proves what happened; D would add an unapproved state. Whether durable checkpoints may be introduced is a technical design and is not authorized by this worksheet.

**Evidence to require:** Valid `IN_PROGRESS` record if available; immutable source fingerprint; durable per-occurrence checkpoints/results; artifact hashes and publication state; process exit/interruption evidence when available. If outcome is unknown, retain unknown/unavailable evidence outside any invented terminal claim and keep effective selection `NONE` under D8b.

**Dependencies:** D3/D5 occurrence and failure meanings; D6 terminal evidence requirements; D7 required artifact/checkpoint evidence; D8 evidence-based retry and `NONE` selection rules; D10 audit/reconciliation authority; D13 durability and crash consistency. Recovery journal/checkpoint implementation remains unauthorized.

**Owner response:** Option: ____  Conditions or edits: ____  Rationale: ____

### 10. Terminal-state and restart mapping

**Decision question:** For each validated persisted state and restart observation, which existing five-state classification may be retained or written, and what evidence is required? What must happen when metadata is absent, corrupt, or conflicting?

- **A. Evidence-gated mapping.** Retain validated terminal states only after revalidating their evidence; retain `IN_PROGRESS` only when its metadata validates; write `COMPLETE`, `EMPTY`, `PARTIAL`, or `FAILED` only when the selected D6 evidence threshold is met. Missing/corrupt/conflicting metadata or unknown outcomes are unavailable/blocked, not inferred terminal states. Effective selection remains `NONE` after failed/interrupted attempts under D8b.
- **B. Restart converts every `IN_PROGRESS` attempt to `FAILED`.**
- **C. Restart infers status from output files and fills gaps from stale fixed-path files.**
- **D. Add a persisted `UNKNOWN` or `INTERRUPTED` terminal state.**

**Recommendation:** A. It aligns with D8a’s fixed five-state vocabulary, approved fail-closed evidence rules, and D8b’s `NONE` pointer after failed/interrupted attempts. It does not specify new transitions where the evidence cannot support them. Prior `COMPLETE` records remain preserved; rollback remains separately authorized and validated under D8b.

**Evidence to require:** Run/generation identity; schema/version and manifest integrity; source fingerprint; accounting reconciliation; stage/status-required artifacts; cross-stage bindings; validated terminal timestamp/failure evidence; previous terminal record integrity; explicit latest-attempt identity. No silent fixed-path fallback.

**Dependencies:** D3/D5 occurrence and failure meanings; D6 terminal accounting; D7 required artifact roles; D8a/D8b approved vocabulary/selection policy and unresolved D8c–D8f details; D10 rollback/reconciliation authority and audit evidence; D12 external fixed-path reader behavior; D13 storage, atomicity, and crash-recovery validation.

**Owner response:** Option: ____  Conditions or edits: ____  Rationale: ____

### Unsupported assumptions and technical validation boundary

- The recommendation to keep `EMPTY` source-empty-only pending decisions is conservative decision support; broader zero-eligible semantics are not established by the isolated v1 helper, which requires a zero-row source for `EMPTY`.
- Calling fully accounted all-skipped/all-duplicate data `EMPTY` or `COMPLETE` is not settled by D4 or the prior D6 approval. Any recommendation requiring eligibility, dedup identity, or retention semantics depends on D3/D4/D5 decisions.
- Requiring expected and discovered counts is unsupported absent authoritative producer/acquisition evidence from D1/D2. Unknown must not be represented as zero.
- Checkpoint durability, crash consistency, atomic multi-file publication, filesystem containment, and concurrency properties cannot be established by worksheet policy or source-level contracts alone; they require D13 technical validation. No checkpoint or recovery mechanism is authorized here.
- The isolated generation helper and schema/verifier proposals are not integrated production behavior. Their accepted manifest shapes and thresholds are evidence of existing isolated contracts only.
- A terminal `FAILED` record with partial occurrence data is not uniformly defined across the isolated contracts. The owner must not infer its accounting equation or artifact-retention requirements from one helper.

### Dependency map — policy decisions versus technical validation

| Dependency | Owner/policy input needed | Technical validation needed |
|---|---|---|
| **D1–D2** | Approved: no authoritative source yet; exact captured bytes used for parsing define the byte identity; specified provenance is recorded separately; no authority/completeness claim without evidence and no completeness claim from a fingerprint alone. No producer is authorized. | Verify byte capture/parse consistency and provenance handling if separately authorized. Full evidence threshold for completeness, expected counts, and source acquisition remain unresolved; no claim that current `jobs.csv` is complete. |
| **D3–D5** | Approved at scoped policy level: strict input validation, preserve occurrences, title/company enrichment then ineligible, missing/unusable ID/URL blocks processing, malformed source structure fails stage; evidence-based description/failure classification as recorded in D5. | D6 still decides accounting and terminal mapping; D7 decides required diagnostic/artifact roles. Technical validation of any implementation requires separate authorization and D13 where storage/security claims apply. |
| **D7** | Approve per-stage/status required artifact roles, diagnostics retention, and empty/partial role expectations. | Validate strict byte/format/header/row-width/count checks and multi-artifact consistency. |
| **D8** | Evidence-based retry and selection rules already approved policy-only; clarify retryable evidence boundaries as needed. | Validate idempotency, duplicate/retry interaction, latest-attempt binding and crash scenarios. |
| **D10** | Define authority and audit requirements for rollback/reconciliation. | Verify evidence can be authenticated, preserved and reviewed; no reconciliation behavior is implemented by this worksheet. |
| **D12** | Decide external fixed-path reader/dashboard behavior for empty, unselected, or unavailable generations. | Validate actual consumer compatibility, headers and zero-row handling before any integration. |
| **D13** | Independent validation criteria and signoff authority remain outside these D6 choices. | Validate path containment, atomicity, durability, crash consistency, concurrency and recovery claims before implementation relies on them. |

## Consolidated D6 decision-readiness matrix

This matrix consolidates the detailed questions above; it does not repeat their options or record owner responses. “Existing technical evidence” refers to isolated helper/schema/verifier contracts and synthetic tests only. It is not production behavior and does not by itself authorize design implementation. **READY FOR DESIGN** means the stated policy boundary is sufficiently defined for design documentation only; implementation remains separately unauthorized.

| Decision area | Existing evidence | Owner approval | Specialist validation | Readiness |
|---|---|---|---|---|
| **Captured-source occurrence denominator** | Isolated contracts count rows; D6 expressly approved each captured-source row as one occurrence and preserving duplicate occurrences/references. Production generation accounting is absent. | **Yes, policy-only** for captured-row occurrence unit and duplicate preservation. | Validate exact snapshot capture/fingerprint behavior before implementation; D13 storage claims remain separate. | **READY FOR DESIGN** — policy boundary only. |
| **Expected versus discovered counts** | Production collection diagnostics record requested scopes and recognized discovered-candidate occurrences, but no authoritative expected count or completeness signal; no source establishes that these counts equal rows published to `jobs.csv`. | **OWNER APPROVED — OPTION A — POLICY ONLY.** Expected is recorded only from an authoritative source; otherwise `UNKNOWN`, never zero. Fingerprint alone is not completeness evidence. | No current authoritative expected count or source-completeness evidence exists; this is an evidence limitation, not a pending Q1 policy choice. | **POLICY APPROVED — IMPLEMENTATION NOT AUTHORIZED** |
| **Duplicate occurrence dispositions** | Production stages process source rows; isolated v2 proposal models separate ordinals/dispositions. D4 approves hybrid duplicate handling; D6 approves preserving occurrences/references. Exact disposition codes and retained-row links are not settled. | **Partial only.** D4/D6 principles approved; exact disposition and all-duplicate status pending. | Validate D4 identity evidence, source references, multiplicity, and occurrence-to-output mapping after the rule is selected. | **OWNER DECISION REQUIRED** |
| **Manifest fields and accounting equation** | Isolated v1 helper has aggregate source/processed/skipped/failed counts with a conservation check; v2 proposal has occurrence ledger/output-row fields. Contracts differ, and `IN_PROGRESS`/`FAILED` accounting is not uniform. Production has no generation manifest. | **OWNER APPROVED — OPTION A FOR THE TERMINAL EQUATION — POLICY ONLY.** Exactly one mutually exclusive disposition; `captured = processed + skipped + failed + unprocessed`; not reached is `UNPROCESSED`, not `FAILED`; evidenced terminal `FAILED` may include accounted `UNPROCESSED`. | Manifest fields, output-row mapping, checkpoint durability, and other terminal mappings remain technical/policy details; D13 before durability claims. | **PARTIAL POLICY APPROVAL — IMPLEMENTATION NOT AUTHORIZED** |
| **Required artifact roles** | Isolated helper defines role sets for data-bearing statuses; its `EMPTY`/`FAILED` roles differ from other proposals. Production stages have no generation role contract and may return early without writing output. | **No.** D7 is expressly open; D6 only approves validating whichever required artifacts D7 defines. | D13 review for secure paths, publication, atomicity/durability; D12 consumer validation. | **BOTH REQUIRED** |
| **Per-artifact validation** | Isolated verifier checks role/path, hash/size, strict CSV/JSON parsing, headers, widths/counts and cross-stage references. Synthetic tests cover malformed/missing/mismatched cases. This is not wired into production. | **Partial only.** D6 approves artifact validation before selectability and missing/corrupt/conflicting-evidence fail-closed; exact role-specific rules pending D7. | D7 role matrix plus D13 filesystem/security review; D12 compatibility checks for real consumers. | **BOTH REQUIRED** |
| **`EMPTY` classification** | v1 helper permits `EMPTY` only for zero source rows with zero counts/no data outputs. D8a defines valid completed zero-eligible generation, subject to D6. Header-only CSV parses structurally but does not prove accounting. | **OWNER APPROVED — OPTION C — POLICY ONLY.** Preserve separate evidence for valid zero-row source and valid completed zero-eligible output; zero output alone does not prove completeness. | D7 roles and D12 consumer behavior remain for role/state validation; D13 for storage/integrity claims. No implementation is authorized. | **POLICY APPROVED — IMPLEMENTATION NOT AUTHORIZED** |
| **Fully accounted all-skipped runs** | v1 helper can accept all-skipped `COMPLETE`; v2 proposal flags all-skipped `EMPTY`/`COMPLETE` as unresolved. Production does not produce a generation status. | **OWNER APPROVED — OPTION A, CONDITIONAL — POLICY ONLY.** `EMPTY` only with an approved skip reason per occurrence, reconciled accounting, and valid required artifacts; preserve occurrences and skip evidence. | D7 artifact/diagnostic roles and D12 zero-row behavior remain validation dependencies; no status may be inferred from zero output alone. | **POLICY APPROVED — IMPLEMENTATION NOT AUTHORIZED** |
| **Fully accounted all-duplicate runs** | D4-approved hybrid rule preserves occurrences and blocks ambiguous identities. Isolated v2 can represent duplicate occurrences, but exact retained mapping/disposition is not fixed; no production generation state exists. | **Partial only.** Preserve occurrences/references approved; exact duplicate disposition and resulting state pending. | Validate D4/D9 identity and retained-occurrence evidence, stage eligibility and output reconciliation. | **BOTH REQUIRED** |
| **`PARTIAL` thresholds** | v1 helper requires nonempty source, at least one processed and one failed; current verifier proposal has a similar useful-work threshold. Both remain isolated contracts. | **OWNER APPROVED — OPTION A — POLICY ONLY.** Require processed and failed occurrences, reconciled accounting, and valid required artifacts; `PARTIAL` remains nonselectable. | D7 role definitions and D13 publication-integrity validation remain gates. All-failed/stage-level mappings remain outside this approval. | **POLICY APPROVED — IMPLEMENTATION NOT AUTHORIZED** |
| **Interrupted-run accounting** | Isolated `IN_PROGRESS` requires no completion/accounting/outputs; tests classify it incomplete. Neither source absence nor missing output proves what occurred; no production checkpoint or recovery journal exists. | **Partial only.** Do not invent terminal state; failed/interrupted selection `NONE`; missing/corrupt/conflicting evidence blocks. Exact occurrence outcomes/checkpoint rules pending. | D13 crash consistency/durability; D8 retry evidence and D10 audit/reconciliation rules. | **BOTH REQUIRED** |
| **Terminal-state and restart mapping** | Isolated pointer/helper contracts constrain some `IN_PROGRESS`, `COMPLETE`, `EMPTY`, `PARTIAL`, and `FAILED` shapes, but no production publisher/restart protocol exists and failure/accounting contracts differ. | **Partial only.** Five-state vocabulary, nonselectable `PARTIAL`, no silent fallback, and D8b `NONE`/rollback rules approved; exact state transitions and restart mappings pending. | D10 rollback authority/audit, D12 CSV/dashboard behavior, and D13 storage/recovery validation. | **BOTH REQUIRED** |

**Classification against the five review categories:** (1) **Explicitly supported by approved decision:** captured-row denominator; Q1 expected-count handling; Q3 terminal equation; Q5 source-empty/result-empty distinction; conditional Q6 all-skipped rule; Q8 `PARTIAL` threshold; existing D6 principles. (2) **Technical evidence exists, owner approval remains:** exact ledger/manifest schema, output linkage, and checkpoint/restart details. (3) **Specialist validation required:** D13 remains a gate for filesystem, durability, crash-consistency, concurrency, or publication claims. (4) **Owner approval and/or validation still required:** Q2 exact duplicate disposition, Q4 artifact roles/checks, Q7 all-duplicate status, Q9 interruption accounting, and Q10 restart mapping. (5) **Blocked by missing evidence:** no authoritative expected count or current complete-source evidence exists even though the Q1 recording rule is approved. The worksheet’s artifact question remains split into two matrix rows.

### Record consistency note

The original blanket “D1–D13 OPEN / UNAPPROVED” status in `PROJECT_DECISION_RESPONSE_PACKAGE.md` and `RELEASE_READINESS_HANDOFF.md` is retained as a broad snapshot, not current per-ID authority. Those documents now point to the current register and specific D4, partial D6, D8, and D9 records. `PIPELINE_GENERATION_POLICY.md` remains the current per-ID register. The snapshot wording is not evidence that pending decisions are approved; no individual approval dates or identities are inferred.

## D1/D2 source-completeness evidence and D6 dependency closure

The classifications below are based on static source/document inspection and existing synthetic tests only. No live collection, browser, or publication workflow was run. “Production behavior” means behavior implemented by the repository code, not a claim about a live search result or an external source.

| Finding | Classification | What existing evidence establishes | What remains open |
|---|---|---|---|
| **Authority of `jobs.csv` producer** | **Owner decision recorded; production evidence remains insufficient** | Owner selected D1 Option 3 — no authoritative source yet. `job_search.py` names `jobs.csv`, but `publish_collection()` rejects every outcome. `job_scraper.scrape_jobs()` returns candidate rows and does not publish the file. `job_details` consumes the fixed path. | Existing `jobs.csv` remains unverified; no new producer is authorized. Filename/existence does not prove authority or freshness. This approval does not make the source authoritative. |
| **Source capture boundary and identity** | **Owner decision recorded; verified isolated-helper behavior; production implementation absent** | Owner approved exact-byte identity: hash exact captured bytes used for parsing and record specified provenance separately. The isolated helper can hash supplied bytes but does not acquire/parse the production source. | Production still lacks a shared immutable snapshot and provenance capture. Exact-byte policy approval is not evidence that current `jobs.csv` was captured or parsed as an immutable snapshot. |
| **Completeness of captured source** | **Owner-approved fail-closed limit; unknown / insufficient production evidence** | Production diagnostics preserve requested scopes, observed candidate occurrences, certain errors/caps, and scope attempts. They do not record observed query/location identity, settled results, pagination batches/exhaustion, or complete filter execution. Current clean collection evidence remains `UNKNOWN`; publication remains closed. | Owner approved no authority/completeness claim without evidence and no completeness claim from a fingerprint alone. The full evidence threshold is not defined. No evidence establishes that fixed `jobs.csv` contains every intended result or represents a completed search. |
| **Expected versus discovered quantities** | **Verified production diagnostic behavior; unknown / insufficient evidence** | A per-scope discovered-candidate occurrence count is present for selector-recognized candidates. The offline classifier checks that supplied discovered counts agree with supplied disposition ledgers. | D6.Q1 Option A is policy-approved: no authoritative source or expected-results quantity is currently evidenced, so expected count remains `UNKNOWN`, never zero. Selector observations do not prove all results or rows published to `jobs.csv`; this is a current evidence limitation, not a pending Q1 decision. |
| **Duplicate occurrences** | **Verified production behavior; approved policy only** | The collection diagnostics record ordered selector observations, including repeats, before output deduplication. `job_details` iterates each source row. D4 Option 3 and the D6 row-occurrence/preservation rules are policy-approved only. | Selector overlap/caps can mean observed occurrences are not a complete source snapshot. Exact generation disposition and retained-occurrence evidence remain pending D3/D4/D6/D9; no production generation ledger exists. |
| **Missing, malformed, or interrupted capture** | **Verified production diagnostic behavior; verified isolated-helper behavior; unknown / insufficient evidence** | Collection diagnostics record some setup/navigation/parser/cap issues; the offline classifier distinguishes supplied `INCOMPLETE` from `UNKNOWN` evidence. The production publisher remains fail-closed. The isolated helper validates supplied manifests/artifacts but provides no production recovery journal or capture protocol. | There is no durable source-capture record or restart evidence that proves where an interrupted capture stopped, whether a missing file means no results, or whether existing rows form a complete capture. |
| **Zero source rows versus incomplete capture** | **Verified isolated-helper behavior; recommendation; unknown / insufficient production evidence** | The generation helper accepts `EMPTY` only when a valid supplied source has zero rows and accounting/output constraints validate. The offline collection specification accepts `COMPLETE_EMPTY` only with direct legitimate-empty, settled-result, terminal-exhaustion, and filter evidence. | Production zero discovered links is not proof of legitimate empty; the production adapter lacks the required page/pagination evidence and classifies clean runs `UNKNOWN`. Thus current production evidence cannot distinguish a truly empty search from incomplete/unsupported capture. |

### D6 dependency closure (using the readiness matrix above)

- **Already supported by explicit policy approval:** captured-source-row occurrence unit; preserving duplicate occurrences/references; explicit accounting categories; artifact validation as a selectability gate; fail-closed missing/corrupt/conflicting evidence; `PARTIAL` nonselectability; no invented terminal status. These are policy-only and do not define all schema or transition details.
- **Technical facts established but not policy-resolving:** v1 helper zero-source `EMPTY`, its aggregate conservation fields, all-skipped `COMPLETE` acceptance, and useful-work `PARTIAL` threshold are isolated constraints. The v2 contract and offline collection classifier add other supplied-evidence checks. None closes an owner question or proves production capture completeness.
- **Owner decisions still required:** D6 expected/discovered accounting, exact duplicate disposition, terminal equation/checkpoint details, `EMPTY`, all-skipped/all-duplicate, `PARTIAL`, interruption and restart semantics; D7 role/status contract; D9 exact identity rules; D10–D12 policy details. D1/D2 and D3/D5 approvals are scoped policy inputs, not implementation authorization; full completeness evidence thresholds remain unresolved.
- **Additional validation gates:** D7 must define roles before per-role validation can be fixed; D12 must establish CSV/dashboard consumer behavior; D13 must independently validate any file-containment, replacement, atomicity, durability, crash-consistency, concurrency, or recovery claim. These are separate from owner policy decisions and remain open.
- **Blocked by upstream evidence/decisions:** expected/discovered completeness remains blocked by absence of an authoritative source and completeness evidence, notwithstanding the approved D1/D2 limits. D3/D5 now supply the stated input/failure policy meanings, but D6 must still decide accounting, all-skipped and terminal classification. All-duplicate classification additionally depends on D4/D9 identity and retained-occurrence rules. No D6 question is closed merely by its recommendation or an isolated helper test.

## Owner response status — approved and remaining questions

Q1, Q3 terminal equation, Q5, Q6, and Q8 are **OWNER APPROVED — POLICY DECISION ONLY** as recorded above. Q2, Q4, Q7, Q9, and Q10 remain **PENDING OWNER DECISION**; their blank response fields are intentional. The prior twelve-item D6 approval and D4/D8a/D8b approvals remain policy-only and unchanged. No D6 question is implementation-ready; no implementation, schema, manifest, recovery, pointer, tracker, migration, rollback, or production authorization is granted by this worksheet.

## Recommendation summary (recorded where approved; other details pending)

Approved rules: use one occurrence per captured source row; record expected count only from an authoritative source and otherwise `UNKNOWN`; reconcile the terminal equation `captured = processed + skipped + failed + unprocessed` with exactly one mutually exclusive disposition per occurrence. Keep `UNPROCESSED` distinct from `FAILED`; an evidenced terminal `FAILED` generation may contain explicitly accounted unprocessed work. Q5 preserves separate evidence for a valid zero-row source and a valid completed zero-eligible result; Q6 permits `EMPTY` for all-skipped input only with approved skip reasons, reconciled accounting, and valid required artifacts; Q8 requires processed and failed occurrences, reconciled accounting, and valid required artifacts, with `PARTIAL` nonselectable. Q2, Q4, Q7, Q9, and Q10 remain open, as do exact schemas, output linkage, artifact-role contracts, checkpoints, and technical validation. Missing evidence still fails closed; do not invent dispositions or terminal outcomes.

## Dependencies

- **D1/D2:** Owner approved no authoritative source yet and exact-byte identity/fingerprinting with specified separate provenance. No producer is authorized; full completeness evidence threshold and any source-acquisition contract remain unresolved. Expected/discovered evidence remains limited.
- **D3/D5:** Owner approved strict input validation and evidence-based failure classification at the scope recorded in the policy register. This does not decide D6 occurrence accounting/terminal mapping or D7 diagnostic/artifact requirements.
- **D4:** Hybrid duplicate policy is approved, but verified identity/alias rules remain; duplicate skips need retained source-occurrence references.
- **D7:** Exact artifact roles and status-specific output/diagnostic retention are separate dependencies.
- **D8a/D8b:** Five-state vocabulary and explicit rollback authorization are policy-approved only; `PARTIAL` is nonselectable and failed/interrupted selection is `NONE`.
- **D10:** Authority and audit evidence for any later rollback or reconciliation.
- **D12:** External fixed-path CSV/dashboard readers, header/schema contract, and behavior when a generation is empty or unselected.
- **D13:** Independent filesystem/security specialist validation before storage, publication, atomicity, durability, or concurrency claims are relied on.

## Owner response status

Supported recommendations are **OWNER APPROVED — POLICY DECISION ONLY** as recorded above. Remaining subquestions are pending. Decision source: project owner instruction in the current task. No individual name, approval date, or reviewer identity was supplied.
