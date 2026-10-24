# Phase 110 — Offline Generation Lifecycle Integration Report

**Project:** AI-Job-Automation-updated v1  
**Scope:** Synthetic, offline integration probe for canonical manifest schema v2, the provenance verifier, and generation-store validation. No production integration.

## Result

Added `tools/offline_generation_lifecycle.py` and a focused synthetic test module. The lifecycle passes canonical schema-v2 manifests directly to the verifier and generation store, preserves each component's result, and reports their contract incompatibilities. It does not translate or normalize manifests between interfaces.

The Phase 109 report described schema v2 as non-authorizing and documented a four-module regression. The current source files confirm that schema v2 validates in-memory structure only and leaves D1–D13 unresolved. Inspection also found that the verifier and generation store still use distinct v1 manifest contracts, preventing the proposed components from cooperating end-to-end without an unresolved contract decision.

**Production integration remains NO-GO.**

## Current interface findings

| Component | Current contract observed |
|---|---|
| `tools/provenance_manifest_schema.py` | Canonical schema version 2; 17 exact top-level keys; stages `source`, `job_details`, and `job_analyzer`; `input_generation` uses `size_bytes`; accounting uses occurrence counts and `output_rows`; successful validation returns `NOT_AUTHORIZED`. |
| `tools/offline_provenance_verifier.py` | Schema version 1; 12 exact top-level keys; input references use `artifact_size_bytes`; validates supplied manifest and artifact bytes; `eligible` is always false; PARTIAL is rejected for policy resolution with D6/D7 dependencies. |
| `pipeline_generation_store.py` | Manifest schema version 1; 11 exact top-level keys; only `job_details` and `job_analyzer` stages; input references use `artifact_size_bytes`; accounting uses `source_records`, `processed_records`, `intentionally_skipped_records`, and `failed_records`. It does not support source-stage manifests. |

Passing canonical schema-v2 details manifests directly to the verifier fails at its exact-key envelope (`MALFORMED_MANIFEST`). The generation store rejects the v2 envelope at its own exact-key validation before applying its v1 contract. The mismatches include schema version, top-level fields, reference size-field naming, accounting names, and source-stage support. These are preserved as independent outcomes in the structured lifecycle result.

The schema validator checks a generation reference's shape and artifact fingerprint fields but does not receive parent manifest bytes. A structurally valid but contradictory upstream run ID can therefore pass schema validation. The lifecycle separately compares the declared ID to the synthetic upstream manifest and reports `CONTRADICTORY_SOURCE_GENERATION_ID`; it does not alter the manifest or claim that the schema validator established the binding.

## Lifecycle coverage

The prototype constructs deterministic synthetic source and details manifests and records stage outcomes for `COMPLETE`, `EMPTY`, `PARTIAL`, `FAILED`, and `IN_PROGRESS`. It includes explicit source-generation binding diagnostics, schema validation, direct verifier invocation, direct generation-store validation, and fixed `false` results for production selection and publication authorization.

The tests cover malformed manifests, missing source binding, contradictory source IDs, missing or inconsistent artifact declarations, inconsistent occurrence accounting, zero-item EMPTY accounting, PARTIAL refusal by the existing verifier, FAILED non-authorization, interrupted runs, unexpected schema exceptions, deterministic repetition, and refusal to authorize production selection/publication.

The PARTIAL policy test supplies a separate verifier-v1 native synthetic fixture directly to the existing verifier to observe its current D6/D7 behavior. This is an isolated policy probe, not an adapter between the schema-v2 and verifier-v1 contracts.

## Bounded test evidence

The selected modules were run through `run_offline_tests.py` with Python 3.12.14. The first combined attempt encountered `PermissionError` while Windows `tempfile` cleanup removed sandbox temp directories in three existing modules. Those modules reported cleanup errors rather than assertion failures. The same selection was rerun with process-local `TEMP` and `TMP` pointing to the existing writable `C:\Users\gbhan\Documents\Codex\Phase105Scratch` directory; the prior values were restored in `finally`.

Final bounded run: **139 passed, 0 skipped, 0 failures, 0 errors, 0 timeouts; runner exit code 0**.

| Module | Run | Passed | Skipped | Failures | Errors | Exit |
|---|---:|---:|---:|---:|---:|---:|
| `test_offline_generation_lifecycle.py` | 13 | 13 | 0 | 0 | 0 | 0 |
| `test_provenance_manifest_schema.py` | 33 | 33 | 0 | 0 | 0 | 0 |
| `test_provenance_schema_differential.py` | 11 | 11 | 0 | 0 | 0 | 0 |
| `test_offline_provenance_verifier.py` | 53 | 53 | 0 | 0 | 0 | 0 |
| `test_pipeline_generation_store.py` | 29 | 29 | 0 | 0 | 0 | 0 |
| **Total** | **139** | **139** | **0** | **0** | **0** | **0** |

The runner summary is `C:\Users\gbhan\Documents\Codex\phase110-test-reports\20261024T065446103043Z-38fdb16df80a4d80a5b513cc6392c581\summary.json`. The runner's explicit exclusions remained `test_offline_search_evidence`, `test_route_audit_browser_smoke`, and `test_search_page_evidence`.

## Safety boundaries and limits

- Only the lifecycle prototype, its synthetic tests, this report, and the single test-runner allowlist entry were changed.
- `pipeline_generation_store.py`, `tools/offline_provenance_verifier.py`, production modules, environment controls, and publication controls were not modified.
- No browser, CDP, live job website, evidence reader, production pipeline, application submission, or protected CSV fixture was used.
- No Git staging, commit, push, or recovery operation was performed.
- D1–D13 remain unresolved and unapproved. The Phase 66 Windows filesystem security rejection remains in force.
- These tests do not establish cross-component artifact-byte integrity, Windows filesystem security, rollback authority, crash durability, or resistance to concurrent file modification.

**Production integration remains NO-GO.**
