# Phase 111 — Manifest Contract Reconciliation and Conformance

**Project:** AI-Job-Automation-updated v1  
**Scope:** Evidence-backed comparison and isolated, fail-closed version gate. No conversion between manifest contracts and no production integration.

## Outcome

The current code confirms that schema v2 and the two v1 components are distinct contracts. The generation store and offline verifier both call their manifests version 1, but their exact envelopes and validation meanings differ. The schema-v2 proposal is explicitly version 2 and remains non-authorizing.

The minimum safe reconciliation is an isolated compatibility fence in `tools/manifest_contract_compat.py`. It requires the caller to name a target and source version, checks the actual envelope version, rejects mismatches, and delegates only version-matched native inputs to existing public validation APIs. It does not rename fields, add defaults, translate statuses, drop findings, or treat validation as authorization. A v2 manifest submitted to either v1 component returns `SCHEMA_VERSION_MISMATCH` before dispatch.

This choice follows Phase 106's recommendation to keep the components separate until policy decisions are resolved. The fence is useful to prevent accidental cross-version dispatch, while conversion would require unresolved decisions about source provenance, occurrence accounting, partial runs, diagnostics, and rollback.

**Production integration remains NO-GO.**

## Field-level contract comparison

The following reflects the inspected current source. Exact-field groups refer to each validator's required-key set; optional means a field may be null where the validator explicitly permits it, not that the key may be omitted.

| Concern | Canonical schema v2 | Offline verifier v1 | Generation store v1 | Classification and evidence |
|---|---|---|---|---|
| Version identity | `SCHEMA_VERSION = 2`; proposed schema contract. `validate_manifest` checks exact integer version. | `SCHEMA_VERSION = 1`; `verify_generation` parses supplied manifest bytes and checks exact integer version. | `MANIFEST_SCHEMA_VERSION = 1`; `validate_manifest` checks exact integer version. | V2 versus v1 is an `INTENTIONAL_VERSION_BOUNDARY`; no automatic upgrade is justified. Store v1 and verifier v1 sharing the integer 1 does not make them compatible: their envelopes differ (`TECHNICAL_INCOMPATIBILITY`). See constants and validation entry points in all three modules. |
| Exact top-level fields | `TOP_LEVEL_KEYS` requires 17: schema/run/stage/status, producer, start/completion, source, input generation, accounting, occurrences, outputs, diagnostics, failure, previous generation, policy dependencies, extensions. Exact keys only. | `TOP_KEYS` requires 13: schema/run/stage/status, producer, start/completion, source, input generation, accounting, occurrences, outputs, failure. Exact keys only. | `_MANIFEST_KEYS` requires 11: schema/run/stage/status, start/completion, source, input generation, accounting, outputs, failure. Exact keys only. | Exact-envelope rejection is `TECHNICAL_INCOMPATIBILITY`. No field is silently added or removed. The Phase 110 report's count of 12 verifier keys was inaccurate; the current `TOP_KEYS` contains 13. |
| Identifiers | `run_id` and reference IDs must be canonical lowercase UUIDv4. | `run_id` and reference IDs must be canonical lowercase UUIDv4. | `run_id` and reference IDs must be canonical lowercase UUIDv4. | Syntax is aligned. Cross-manifest identity proof differs and is classified under lineage as `MISSING_INTERFACE`; no authority follows from UUID syntax. |
| Stages and source | Supports `source`, `job_details`, `job_analyzer`; source roles are `jobs_csv` or `details_csv`, with encoding and format. | Supports the same three stages and source roles, including `jobs_csv`, encoding, and format. | Supports only `job_details` and `job_analyzer`; `_validate_source` uses role `jobs.csv` for details input and `details_csv` for analyzer input. | Role/key vocabulary mismatch is `TECHNICAL_INCOMPATIBILITY`. Store source-stage absence is a `MISSING_INTERFACE`; whether source is a first-class generation remains an `UNRESOLVED_POLICY_DECISION` under D1–D2. |
| Source-generation references | `INPUT_KEYS` requires stage, run ID, status, manifest hash, artifact role/hash, `size_bytes`, record count, format. `_check_source_reference` compares source descriptor fields. | `INPUT_KEYS` requires stage, run ID, status, manifest hash, artifact role/hash, `artifact_size_bytes`, record count. `_verify_input_binding` requires upstream manifest/artifact bytes and checks IDs and descriptors. | `_validate_input_generation` requires stage, run ID, status, manifest hash, artifact role/hash, `artifact_size_bytes`; analyzer binding is a separate public API. Details stage has no input edge. | Field names and edge coverage are `TECHNICAL_INCOMPATIBILITY`. V2 `validate_manifest` receives no parent bytes and therefore cannot establish that a shaped reference's run ID exists or matches the supplied parent; that is a `MISSING_INTERFACE`, observed by `test_analyzer_generation_binding_requires_parent_evidence_in_existing_validators`. |
| Status vocabulary and meaning | `IN_PROGRESS`, `COMPLETE`, `EMPTY`, `PARTIAL`, `FAILED`; schema validates state-specific shape and always returns `NOT_AUTHORIZED`. | Same tokens; `IN_PROGRESS` returns `INCOMPLETE`; `FAILED` returns a nonaccepted `FAILED`; `PARTIAL` remains policy unresolved with D6/D7. | Same tokens; `validate_manifest` validates shape; `read_verified_artifacts` only accepts COMPLETE/PARTIAL, while pointers separately constrain selection. | Tokens match, but status consequences are not interchangeable (`TECHNICAL_INCOMPATIBILITY`). PARTIAL thresholds/handling and selection remain `UNRESOLVED_POLICY_DECISION` (D6–D8); verifier D6/D7 behavior is preserved. |
| Artifacts | `ROLE_PATH_FORMAT`, `STAGE_ROLES`, and `OUTPUT_KEYS`: canonical relative path, SHA-256, byte size, record count, format. Schema does not open bytes. | `EXPECTED_ARTIFACTS` and `ARTIFACT_KEYS`: role/path/hash/size/count/format; requires supplied bytes, parses CSV/JSON, and checks hash, size, format, and counts. | `_EXPECTED_OUTPUTS` and `_EXPECTED_OUTPUT_PATHS`; output descriptor has path/hash/size, without record count or format. Optional `read_verified_artifacts` checks hash/size from a path. | Metadata and verification-depth differences are `TECHNICAL_INCOMPATIBILITY`. V2 does not prove artifact bytes. Filesystem safety, path containment, and concurrent replacement are not established by the store's path reads and require separate specialist approval. |
| Occurrence accounting | `ACCOUNTING_KEYS` has source/processed/intentional-skip/failed occurrence counts plus `output_rows`; `OCCURRENCE_KEYS` specifies ordinal, key, disposition, identity, reason/rule, retained key, error/quality codes, and output row. | Same occurrence and five-counter field family; `_validate_occurrences` checks ledger/count/output-row agreement. | `_ACCOUNTING_KEYS` has four aggregate `*_records` counters; no occurrence ledger. | `TECHNICAL_INCOMPATIBILITY`; aggregate counts cannot express per-occurrence identity. Whether skips, duplicate links, and occurrence dispositions are allowed remains `UNRESOLVED_POLICY_DECISION` under D3–D7. |
| Diagnostics and failure | Required top-level `diagnostics` list and `failure` null/object; diagnostic references are checked against declared outputs and occurrences. | No diagnostics list field. Details diagnostics are supplied as a declared `diagnostics_json` artifact and its bytes are parsed. Failure is null or `{code}`; failed results reject artifacts. | No diagnostics list field; diagnostics JSON is an output artifact descriptor. Failure is null or `{code}`; FAILED manifests have no outputs. | Representation differs (`TECHNICAL_INCOMPATIBILITY`). Failure code shapes overlap but do not authorize use. D6/D7 failed-diagnostic rules remain unresolved. |
| Analyzer input binding | Schema validates reference shape and local fingerprint consistency. It has no parameter for parent bytes. | `_verify_input_binding` verifies details manifest bytes/artifact and, for analyzer, a source ancestor via `upstream_chain`. | `validate_analyzer_input_binding` compares analyzer reference with supplied details manifest and bytes/artifact. | Evidence depth and call signatures differ (`MISSING_INTERFACE` for a shared public binding interface). No adapter can safely fill parent evidence that its caller did not provide. |
| Current/EMPTY selection and rollback | `previous_generation` is metadata only; no pointer or selection API. | `verify_selection` prevents implicit fallback; `verify_rollback_request` returns `ROLLBACK_AUTHORITY_UNVERIFIABLE` absent an approved verifier. | `validate_pointer` defines `NONE`, `CURRENT`, `EMPTY`, and `EXPLICIT_ROLLBACK`, with structural checks; it does not publish pointers or authenticate rollback authority. | Interface difference is `MISSING_INTERFACE`; authorization, fallback, rollback, and retention remain `UNRESOLVED_POLICY_DECISION` under D8/D10/D11/D13. Structural pointer validity is not authorization. |
| Validation result | `SchemaValidationResult`: schema validity, policy resolution, `NOT_AUTHORIZED`, unresolved decisions, dependencies, findings. | `VerificationResult`: classification, accepted, eligible (always false), failure code, identity/status, policy dependencies, supplied artifact bytes. | `validate_manifest` returns `{}` on success or raises `GenerationValidationError`; pointer validation returns the validated pointer object. | Result contracts are `TECHNICAL_INCOMPATIBILITY`. A success from any of the three is never treated as production authorization. |

### Classification summary

- `INTENTIONAL_VERSION_BOUNDARY`: canonical proposal v2 versus both existing v1 consumers.
- `TECHNICAL_INCOMPATIBILITY`: exact envelopes, reference field names, source-role spelling, artifact descriptors, accounting, diagnostics, status outcomes, and result types differ.
- `UNRESOLVED_POLICY_DECISION`: source authority and lineage (D1–D2), occurrence/skip/partial semantics (D3–D7), selection/fallback (D8), rollback/retention (D10–D11), and platform/durability controls (D13).
- `MISSING_INTERFACE`: store v1 has no source-stage validator; schema v2 has no supplied-parent binding input; schema v2 has no selection/pointer or rollback-authorization interface; there is no common artifact-byte boundary.
- `UNCONFIRMED`: no broad semantic equivalence is inferred for fields whose contracts merely share names or tokens. The selected tests provide case evidence, not universal equivalence.

## Compatibility behavior implemented

`tools/manifest_contract_compat.py` exposes `validate_for_component` with an explicit target (`schema_v2`, `offline_verifier_v1`, or `generation_store_v1`) and explicit declared source version. It:

1. Parses exact supplied verifier bytes without translating them and rejects malformed/duplicate-key envelopes.
2. Rejects a declared/actual version mismatch and any actual/target version mismatch.
3. Rejects statuses outside the known lifecycle vocabulary.
4. Dispatches only the native schema-v2 object, verifier-v1 bytes plus supplied evidence, or generation-store-v1 object to its existing public validator.
5. Preserves schema findings, verifier classification/failure/policy dependencies, and store validation failures.
6. Returns `eligible=false` and `authorization=NOT_AUTHORIZED` for every outcome, including successful structural validation.
7. Converts unexpected validator exceptions into explicit nonaccepted `UNEXPECTED_VALIDATION_EXCEPTION` results.

No v2-to-v1 conversion was implemented. In particular, the module does not infer source lineage, map occurrence counts to aggregate records, reinterpret PARTIAL, construct diagnostics/failure evidence, or translate rollback metadata. Schema v2 results explicitly note that external lineage was not verified.

## Synthetic conformance coverage

Added 12 compatibility-fence tests. They cover valid schema-v2 input; valid native v1 verifier and store inputs; both directions of version mismatch; caller-declared version mismatch; missing and unknown fields; unsupported status; missing artifact metadata; IN_PROGRESS remaining incomplete; FAILED remaining non-authorizing; rollback metadata remaining unauthorized; unexpected validator exceptions; and determinism.

The selected existing synthetic suites also exercise source-generation and analyzer-parent mismatches, artifact and occurrence accounting, EMPTY/PARTIAL/FAILED/IN_PROGRESS outcomes, and D6/D7 verifier policy. The relevant existing differential case `ANALYZER_PARENT_RUN_ID_MISMATCH` confirms that the v2 shape validator does not receive the parent manifest bytes needed to establish the parent identity; verifier and store native interfaces reject mismatched parent evidence.

## Bounded offline test evidence

Before testing, each protected file matched its recorded Phase 109 baseline. Tests ran through `run_offline_tests.py` with Python 3.12.14, per-module timeout 60 seconds, and overall timeout 300 seconds. `TEMP` and `TMP` were set only in the launching PowerShell process to `C:\Users\gbhan\Documents\Codex\Phase105Scratch` and restored in `finally`.

Final result: **151 passed, 0 skipped, 0 failures, 0 errors, 0 timeouts; runner exit code 0**.

| Module | Run | Passed | Skipped | Failures | Errors | Timeout | Exit |
|---|---:|---:|---:|---:|---:|---|---:|
| `test_provenance_manifest_schema.py` | 33 | 33 | 0 | 0 | 0 | No | 0 |
| `test_provenance_schema_differential.py` | 11 | 11 | 0 | 0 | 0 | No | 0 |
| `test_offline_provenance_verifier.py` | 53 | 53 | 0 | 0 | 0 | No | 0 |
| `test_pipeline_generation_store.py` | 29 | 29 | 0 | 0 | 0 | No | 0 |
| `test_offline_generation_lifecycle.py` | 13 | 13 | 0 | 0 | 0 | No | 0 |
| `test_manifest_contract_compat.py` | 12 | 12 | 0 | 0 | 0 | No | 0 |
| **Total** | **151** | **151** | **0** | **0** | **0** | **No** | **0** |

Runner summary: `C:\Users\gbhan\Documents\Codex\phase111-test-reports\20261024T070256409893Z-d43e06965dbe46269f749693b6f93c04\summary.json`. The runner explicitly excluded `test_offline_search_evidence`, `test_route_audit_browser_smoke`, and `test_search_page_evidence`.

## Protected files: before and after

Before-run and after-run byte sizes and SHA-256 values both match the established Phase 109 baselines. The files were hashed only; they were not used as fixtures.

| Protected file | Bytes before = after | SHA-256 before = after | Baseline |
|---|---:|---|---|
| `jobs.csv` | 3,198 | `C91092D6F1E24DB1BF34F132D6AF1245AC5E23FEB10DA4ECEBFEFE17DFD96C58` | Match |
| `data/job_details.csv` | 113,172 | `E08903ED9D88CDB15479170CA6B464F127F747EA9DA937B2D28C2755185F270E` | Match |
| `data/job_analysis.csv` | 6,546 | `872A38B4ACDAAD32273184DAE656AC91F58FD543FCF03C61CA1674FCD3C4C250` | Match |
| `data/application_tracker.csv` | 6,186 | `02A25CF281E05818B8B1D2C3F9A00C651DE9B45B0F771BE142BC666A9ABF014E` | Match |
| `data/application_history.csv` | 179 | `9A8F23A900457A26FDDCA22B629539EEDE312E5CA1EC54515A5E1618EC6E2F72` | Match |
| `user_provided_screenshots/java_backend_developer_bengaluru_original.png` | 341,072 | `8CC472E59074E5300816DA1FE619B8B05EE2D2B6248CDEA11FAD562A8E89A70B` | Match |

## Files changed

- Added `tools/manifest_contract_compat.py` — explicit version fence; no contract conversion.
- Added `tests/test_manifest_contract_compat.py` — 12 synthetic conformance tests.
- Added `test_manifest_contract_compat` to the explicit allowlist in `run_offline_tests.py`.
- Added this report.

The schema v2 validator, verifier v1, generation store v1, lifecycle prototype, production modules, environment controls, and protected files were not changed.

## Remaining blockers and safety boundary

D1–D13 remain unresolved and unapproved. The component interfaces still cannot be composed into one generation lifecycle without policy decisions and a separately approved common contract. Schema v2 does not authenticate parent identity; neither manifest validation nor the compatibility fence establishes filesystem containment, safe path opening, crash durability, concurrent-writer safety, artifact publication, or rollback authority. Those remain outside this work and the Phase 66 Windows filesystem-security rejection remains in force.

No production entry point, browser, CDP connection, live job site, collection, evidence reader, or application workflow was used. No protected file was a fixture. No Git staging, commit, push, or recovery was performed. Collection publication remains closed.

**Production integration remains NO-GO.**
