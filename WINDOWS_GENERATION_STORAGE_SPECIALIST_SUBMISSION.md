# Windows Generation Storage Specialist Submission

**Purpose:** preliminary independent design review of the proposed pipeline-generation storage boundary.

**Decision status:** the Phase 66 rejection of the current evidence-reader design remains in force. This submission is a request for review only. It is not approval of a design, authorization to execute adversarial tests, or authorization to implement. Evidence reading remains blocked, collection publication remains closed, `AUTO_SUBMIT` remains false, and browser auditing remains disabled. Production integration is **NO-GO**.

This concise submission accompanies the detailed history and acceptance criteria in [WINDOWS_FILESYSTEM_SECURITY_REVIEW_PACKAGE.md](WINDOWS_FILESYSTEM_SECURITY_REVIEW_PACKAGE.md) and the proposed, unapproved pipeline contract in [PIPELINE_GENERATION_POLICY.md](PIPELINE_GENERATION_POLICY.md). It does not supersede either document.

## 1. Project and proposed workflow

The project processes job records through a details-extraction stage, an analysis stage, and a downstream candidate-selection/application path. The proposed generation design would write each stage's outputs into an isolated per-run generation, record a versioned manifest with source and output fingerprints, validate that the outputs belong to one generation, and publish a pointer only after a generation is complete. Analysis would record the exact details generation it consumed. Consumers would accept only a fully validated eligible generation; `EMPTY`, `PARTIAL`, `FAILED`, and `IN_PROGRESS` would not select old or mixed data.

This workflow is a proposal. The generation-store helper is currently a standalone foundation; production writers, pointer publication, locking, recovery, and manifest-aware consumers have not been integrated. The authoritative `jobs.csv` producer and production artifact root have not been established.

## 2. Verified facts and limitations

- `pipeline_generation_store.py` provides schema and byte fingerprint validation for synthetic generation data. Its ordinary path operations and hashing do not establish trusted-root containment, reparse-point resistance, exact-handle binding, or crash durability.
- Current production stages use fixed paths. `job_details.py` writes the details CSV and diagnostics JSON separately; `job_analyzer.py` consumes the fixed details CSV. A valid empty input may leave prior outputs in place. These writes do not form a multi-file transaction.
- `output_files.py` replaces one file at a time using a temporary file and `os.replace`; this is not evidence of power-loss durability or cross-file atomicity.
- `easy_apply.py` has freshness and identity checks, but does not bind parsed data to a generation ID and content hash. External consumers of fixed-path CSVs are unknown.
- Existing helper and durability tests use isolated fixtures and injected failures. They do not establish Windows filesystem security or power-loss behavior. Phase 93's 12 acceptance areas are proposals and remain **NOT RUN**.
- The current evidence readers validate paths and then open separately. Phase 66 rejected that design as a trusted-root boundary. That rejection remains unchanged; it does not establish that a secure alternative is impossible.

These are repository/documentation findings, not claims about a production deployment or runtime environment.

## 3. Proposed trust boundary and threat model

The boundary requiring review includes the actual trusted root and every ancestor; generation directories; manifests and publication pointer; all referenced artifacts; the filesystem objects opened; the exact bytes parsed; concurrent readers, writers, and cleanup; and downstream consumers. The design must establish that an accepted selection refers to one fully validated generation and that the bytes consumed are those validated under the approved contract.

The following remain unknown and must not be inferred from the project directory or prior environment notes: actual artifact-root path and lifecycle; root and ancestor owners, ACLs, inheritance, and modifying principals; whether same-account hostile processes are in scope; concurrent-writer threat; accepted Windows/Python/filesystem/storage-provider cells; effective privileges; reparse-point policy; and required consistency/durability level. Earlier Windows product observations contain a discrepancy and do not define a support matrix.

The specialist is asked to define requirements and supported/rejected conditions. This submission prescribes no Windows API and claims no API provides containment merely because it exists or succeeds.

## 4. Environment and contract decisions requested

Please identify each supported configuration as a precise Windows build/product, Python version and architecture, filesystem and storage provider, privilege model, and relevant ACL/root assumptions. State any configurations that must be rejected.

For each supported cell, please resolve:

1. How the owner establishes the trusted root and protects it and all ancestors, including required ownership, ACL, inheritance, and allowed writers.
2. How every path component is traversed and how symlinks, junctions, mount points, and other relevant reparse tags are handled, including replacement races.
3. Which documented API contracts support root-relative opening and what guarantees they do and do not provide on the named configurations.
4. How validation is bound to the exact opened object and exact bytes parsed, including file type, identity, size bounds, short reads, and stable-read or mutation detection requirements.
5. Required behavior for replacement, truncation, growth, and same-size mutation; concurrent readers/writers; multiple writers; pointer conflicts; interruption; crash recovery; flush/durability; and cleanup during active use.
6. Mandatory fail-closed behavior when the root, ACLs, provider, reparse state, object identity, bytes, coordination, or durability cannot be verified. Confirm prohibited fallbacks, including path-only retry, mixed generations, directory scanning, and automatic legacy CSV fallback.

## 5. Acceptance areas and authorization classes

Categories: **A** = isolated ordinary unit tests with synthetic fixtures; **B** = controlled real-Windows acceptance tests for each approved configuration; **C** = specialist approval of the test method and safety boundary before execution. B/C execution also requires separate owner authorization. The detailed setups, observable evidence, and pass/fail rules are in Phase 93 of the review package. Every test below is **NOT RUN**.

| # | Acceptance area | Class | Required acceptance result and retained evidence |
|---|---|---|---|
| 1 | Trusted-root identity, ownership, and ACL enforcement | B, C | Root and ancestors match the approved identity/ACL contract; unauthorized changes are rejected. Retain root/ancestor identities, ACLs, effective principals, commands, results, and logs. |
| 2 | Reparse traversal and component replacement | B, C | Across approved tags and race points, the operation reads only an approved in-root object or rejects; no outside sentinel is accepted. Retain tag inventory, race schedule, handle-derived observations, sentinel hashes, and traces. |
| 3 | Opened-object identity and exact-byte binding | B, C; A for pure byte comparison | Parsed bytes equal the bytes fingerprinted from the object that passed the approved identity/type checks; path reopen or uncertain binding rejects. Retain open/read trace, object observations, byte hash, and parser-input hash. |
| 4 | Truncation, growth, and same-size mutation | B, C; A for deterministic hash mismatch | Each case yields a coherent result permitted by the approved consistency contract or rejects; mixed, short, over-limit, or contradictory bytes never pass. Retain synchronized mutation schedule and before/after/returned hashes and sizes. |
| 5 | Concurrent readers and writers | B, C | A reader observes a fully validated eligible old generation, fully validated new generation, or no selection; never a mixed generation. Retain process timelines, selected IDs, hashes, and results. |
| 6 | Multiple writers and pointer conflicts | B, C | Approved serialization/conflict rule is followed; stale or losing writers cannot silently replace a newer selection. Retain process/lock events, pointer versions, manifests, and outcomes. |
| 7 | Interrupted publication and recovery | B, C; A for injected state-machine cases | At every write boundary recovery selects only the approved complete state or none. Retain fault point, restart inventory, pointer/manifests/artifact hashes, logs, and consumer result. |
| 8 | Crash and durability behavior | B, C | Each named cell meets the written durability contract after approved interruption scenarios, or is rejected. Retain provider details, interruption method, restart state, hashes, and system logs. |
| 9 | Cleanup during active reads/writes | B, C; A for retention-policy logic | Active, selected, and protected generations are not removed or altered; uncertainty prevents deletion. Retain active-use traces, protected IDs, cleanup logs, and hashes. |
| 10 | Legacy-only and mixed-mode rejection | A; B for integrated consumer behavior | In enforcement mode, legacy-only, mixed, missing, or corrupt generation inputs produce zero candidates without fallback; a valid generation chain reads only its selected bytes. Retain fixture inventory, path/read trace, validation result, and candidate count. |
| 11 | Rollback authorization and source mismatch | A for decision validation; B, C for real authorization/persistence | Missing, invalid, unauthorized, or source-mismatched rollback rejects; only a verifiable approved authorization can select a validated prior generation. Retain authorization proof, source/generation hashes, pointer history, and consumer result. |
| 12 | Storage-boundary query/verification failure | A for injected error mapping; B, C for real platform failures | Any required query failure or unsupported condition yields no selection and a diagnostic; no weaker fallback occurs. Retain exact error codes, query sequence, environment cell, logs, and result. |

No support cell passes based on API availability, unit tests, or results from a different Windows build, filesystem, provider, or privilege configuration. All required tests must have explicit per-cell PASS/FAIL/BLOCKED/NOT RUN results and retained evidence.

## 6. Owner decisions still outstanding

The owner must answer the open decisions in `PIPELINE_GENERATION_POLICY.md` (D1–D13). In particular:

- Identify the authoritative `jobs.csv` producer, permitted manual/import sources, source identity, and required provenance metadata.
- Approve required source fields, missing-link and intentional-skip rules, duplicate-occurrence policy, blank-description classification, and all-skipped/all-failed/empty status semantics.
- Approve required artifacts by status and whether a prior complete generation stays selected after a failed attempt.
- Define tracker identity/merge/history rules, rollback authority and changed-source restrictions, retention/cleanup policy, and external fixed-path consumer compatibility.
- Supply the actual trusted artifact root, its lifecycle, root/ancestor ownership and ACL evidence, modifying principals, same-account threat scope, actual deployment environment/provider, privileges, concurrent-writer assumptions, and required consistency/durability level.
- Confirm whether existing metadata JSON (256 KiB) and PNG (10 MiB) evidence limits satisfy real input requirements; no limit suitability is established here.

Owner intent and policy approval do not constitute specialist security approval.

## 7. Written specialist response requested

Please return a written response that:

1. Names supported and rejected environment cells, and the assumptions/limitations for each.
2. Resolves root/ancestor trust, ACL, every-component reparse handling, and the documented root-relative API contract for those cells.
3. Defines exact opened-object and byte validation, read bounds, mutation consistency, and reader/writer/multiple-writer coordination.
4. Defines pointer publication, interruption/recovery, durability, retention/cleanup, rollback validation, and mandatory fail-closed behavior, including prohibited fallback behavior.
5. Specifies any additional acceptance cases, identifies A/B/C authorization needs, and states evidence and explicit pass criteria per supported cell.
6. Explicitly records an outcome—approved for a separate implementation proposal, conditionally approved with prerequisites, or rejected—and its exact scope. Partial answers, silence, API availability, and unexecuted tests are not approval.

Even an approval for a separate proposal would not itself authorize production implementation. The owner must separately authorize Windows acceptance testing; C-class methods require specialist pre-approval. Actual results for each proposed supported cell and a new written specialist decision based on those results are required before a later implementation decision. Explicit implementation authorization must then be obtained separately.

## 8. Decision traceability register

**Ownership:** The project owner supplies deployment facts and decides product/pipeline policy. The independent specialist decides technical supportability and security requirements. Neither role or approval is inferred here. Test IDs refer to the 12 areas in §5 and the detailed Phase 93 matrix. All test areas remain **NOT RUN**.

| Owner decision | Owner facts/decision still needed | Specialist question linked to this decision | Test area(s) and class | Evidence and closure criterion | Dependency |
|---|---|---|---|---|---|
| **D1 Source producer** | Name authoritative `jobs.csv` producer; state whether manual/import inputs are allowed and who designates current input. | How is approved source acquisition bound to the supported storage contract? | 3 (B,C); 10 (A; B consumer); 12 (A; B,C platform). | Approved producer/provenance rule; captured source identity and consumer trace; unauthorized source rejected. | Owner source decision → specialist source/opening contract → authorized tests. |
| **D2 Source identity/metadata** | Choose raw-byte snapshot or fully specified canonical identity; list required producer/query/scope/time metadata. | How are the exact source bytes opened, bounded, fingerprinted, and parsed under each supported cell? | 3,4 (B,C; A byte comparison); 10 (A; B consumer); 12 (A; B,C). | Defined encoding/parser/fingerprint contract; retained source and parser-input hashes/sizes; mismatch rejects. | Owner identity policy → specialist byte-binding contract → per-cell tests. |
| **D3 Required fields/skips** | Approve required fields, missing-link treatment, and permitted reason-coded skips. | Does the approved file/input boundary require additional rejection on unverifiable source data? | 10 (A; B consumer); no dedicated Windows security case for business skip policy. | Every occurrence has one disposition; missing/unknown rules do not silently become skips; tests match approved rule IDs. | Owner policy; specialist review only for secure file-access reliance. |
| **D4 Duplicates** | Choose occurrence preservation or explicit dedup identity/survivor rule. | If identity contributes to a trust decision, what evidence is security-relevant? | 10 (A; B consumer); otherwise policy-level offline tests. | Duplicate occurrences remain independently accounted or are removed only by approved rule with traceable references. | Owner identity decision before implementation/tests. |
| **D5 Blank descriptions/errors** | Define blank-description quality policy and which per-record outcomes are extraction failures. | No security API question unless evidence-file content is used to assert extraction correctness; if so, how is that content bound? | 3,4 (B,C for byte/object claims; A deterministic content checks); 10 (A; B consumer). | Separate successful low-quality records from exceptions; diagnostics and counts reconcile exactly to approved outcomes. | Owner extraction policy; specialist approval for any security-sensitive evidence dependency. |
| **D6 Status semantics** | Approve valid-empty, all-skipped, all-failed, and partial outcomes and candidate eligibility. | Can supported storage/recovery behavior preserve these states without exposing stale or partial data? | 7 (A injected; B,C Windows); 10 (A; B consumer); 5 (B,C reader view). | State table approved; actual downstream selection matches it; noneligible states yield no candidates. | Owner semantics → specialist publication/recovery requirements → tests. |
| **D7 Artifacts by status** | Name required outputs/diagnostics/ledger for every stage and state. | How are each artifact and its manifest reference validated as the same opened object/bytes? | 3,7 (B,C; A byte/state checks); 10 (A; B consumer); 12 (A; B,C). | Approved exact role sets; absent/mismatched required artifact rejects; retained hashes/sizes and consumer result. | Owner schema decision + specialist object/byte contract. |
| **D8 Prior selection after failure** | Choose prior selection retained, selection `NONE`, or explicit rollback after failed/interrupted attempt. | What pointer publication, concurrent observation, and recovery guarantees hold on supported cells? | 5,6,7 (B,C; 7 also A injected). | Approved transition table; fault-boundary evidence shows only permitted complete generation or none, never mixed/stale-by-implicit-fallback. | Owner stale-data policy → specialist pointer/recovery contract → authorized tests. |
| **D9 Tracker continuity** | Approve stable job key, URL/duplicate/merge rules, and conflict/history preservation. | How do concurrent tracker readers/writers and cleanup preserve validated tracker state, if included in the boundary? | 5,9 (B,C if tracker shares the protected store); 10 (A; B consumer). | Approved identity/migration rules; conflict cases preserve history or reject; active-use tests if tracker is in storage boundary. | Owner identity policy; specialist scope decision determines Windows tests. |
| **D10 Rollback** | Name authorization authority/mechanism and decide whether changed-source rollback is prohibited or specially allowed. | How is authorization verifiable and durable, and what source/generation checks are mandatory? | 11 (A decision validation; B,C real authorization/persistence). | Missing, invalid, unauthorized, or disallowed source-mismatch rollback rejects; valid case retains verifiable approval and pointer audit. | Owner authority/source rule → specialist integrity/durability decision → C approval and authorized tests. |
| **D11 Retention/cleanup** | Set retention period/count, cleanup authority, and protected-generation rules. | How are active readers/writers detected or coordinated so cleanup cannot invalidate a selected generation? | 9 (A policy logic; B,C Windows). | Approved retention rule; evidence shows selected/protected/active generations are untouched and uncertainty prevents deletion. | Owner retention policy → specialist coordination contract → authorized tests. |
| **D12 External consumers/migration** | Inventory external fixed-path consumers and set compatibility/migration window; repository inspection cannot answer this. | What single-mode/fail-closed behavior is required during any supported migration? | 10 (A; B integrated consumer). | Owner inventory and compatibility plan; fixtures show legacy-only/mixed inputs produce zero candidates under enforcement, without fallback. | Owner external inventory → consumer contract → tests; no assumption of external compatibility. |
| **D13 Environment/concurrency/durability** | Identify actual root, OS/product/build, Python/architecture, filesystem/provider, privileges, ACLs, writers, threat scope, consistency and durability requirements. | Name supported/rejected cells; resolve documented API contracts, reparse traversal, object/byte binding, coordination, publication, crash/durability, fail-closed behavior. | 1–9 and 12 (B,C; A portions only for pure logic); 10–11 where integrated consumer/rollback applies. | Per-cell inventory and specialist-approved contract; every required test has retained evidence and PASS; unsupported/query-failure cases reject. | Owner facts → written specialist decision → separate owner test authorization and C preapproval → per-cell acceptance evidence. |

No D item is closed by this table. Each requires an explicit owner response against its ID; specialist-dependent items also require written specialist answers. Recommendations remain proposals, not approved policy.

## 9. Controlled Windows testing entry criteria

Do not begin controlled Windows acceptance testing until all of the following are recorded:

1. A written specialist decision names the exact supported configuration(s), security contract, testable pass criteria, and rejected conditions.
2. The owner explicitly authorizes the enumerated tests and scope; this authorization is separate from policy decisions or an approval to submit this package for review.
3. The specialist has approved the method and safety boundary for every C-class test before that test is run.
4. The owner and specialist approve a disposable test environment matching each support cell, plus an evidence-retention procedure that records configuration, commands, harness/version, identities/ACLs, fault schedules, logs/traces, hashes, and outcomes without using protected project data or a production root.
5. Each test has a named ID, preconditions, expected result, and PASS/FAIL/BLOCKED/NOT RUN recording rule. A test not authorized or not run remains **NOT RUN**; no result is generalized to an untested cell.

These are proposed process gates requested for this review, not proof that testing is authorized now. No tests were run for this submission.

## 10. Criteria to reconsider implementation

Reconsideration requires all of the following, in order:

1. Applicable owner policy decisions D1–D13 are explicitly resolved, with deployment facts evidenced and no inferred answers.
2. A written specialist contract defines supported/rejected cells, APIs and limits, threat scope, fail-closed rules, and acceptance criteria.
3. Separately authorized acceptance tests pass for every proposed supported cell; all failures are documented and addressed, and no required case remains failed, blocked, or unrun for a cell proposed for support.
4. Retained evidence is reviewed against the specialist's written requirements, including documented deviations and cell-specific results.
5. The specialist issues a new written decision based on the proposed design and actual evidence, explicitly stating its outcome and scope.
6. The owner provides separate explicit implementation authorization. Passing earlier gates does not grant this authorization.

No test or implementation gate is satisfied by the current submission. The detailed criteria remain in Phase 93 of the review package.

## 11. Current hold

Until all applicable owner, specialist, test, and authorization gates are completed, keep evidence reading blocked, collection publication closed, `AUTO_SUBMIT` false, and browser auditing disabled. Do not integrate the generation helper or treat this submission as security approval. Production integration remains **NO-GO**.
