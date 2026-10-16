# Phase 25 — External Validation Readiness

This is a preparation document for separate Windows filesystem-security review and, if separately approved, read-only search-page validation. It does not authorize live navigation, artifact-reader use, production integration, or publication.

## Repository baseline

- Branch: `master`
- HEAD and `origin/master`: `fe640a8118318d4fa168becce30ab9078304534b`
- Initial status: only `user_provided_screenshots/` was untracked; no tracked, staged, or other untracked changes were reported.
- Protected CSV and screenshot hashes are recorded in the Phase 25 report.

## Windows filesystem specialist handoff

### Source-verified behavior

| Reader | Existing sequence and safeguards |
| --- | --- |
| `search_page_evidence.py` | `_check_screenshot()` validates a relative reference, resolves root and target, checks lexical containment, stats for regular-file type and the 10 MiB limit, then separately opens and bounded-reads/hashes the target. It rejects a byte count that differs from the earlier size. See lines 175–247. |
| `offline_search_evidence.py` | `_resolve_under_root()` strictly resolves and checks containment before returning a path. Metadata is separately statted and opened with a 256 KiB bounded read. PNGs are separately resolved, statted, signature-checked, bounded-read, and hashed with a final size comparison. See lines 51–83, 86–132, and 150–226. |
| Failure behavior | The standalone validator adds validation issues; the offline wrapper returns a failed candidate-preparation result with no candidate. Both are fail-closed at the validation boundary. |

### Not established by source

- The path validated is the same filesystem object later opened.
- Resolution and containment checks prevent intermediate or final reparse-point traversal, including a concurrent replacement after checking.
- A pre-open size/type check describes the opened handle. A matching length/hash does not prove origin, authenticity, or a stable snapshot against same-size concurrent content changes.
- The wrapper's bounded read limits allocation, but does not establish containment or eliminate replacement races.

### Specialist decisions required

The specialist must define the trusted-root contract, supported Windows releases and filesystems, and an application-supported open strategy that binds containment, identity, regular-file type, size, and bounded read/hash to the same opened object. The review must address intermediate and final symbolic links, junctions, mount points and other reparse tags; replacement between resolution/open; replacement during open; growth and same-size mutation during reads; permissions; unsupported filesystems/APIs; and fail-closed behavior. Do not accept path-prefix checks, final-component-only checks, or a speculative native API workaround as a substitute for a documented contract.

### Required acceptance tests

Use a dedicated Windows filesystem environment for real kernel/filesystem behavior:

- Normal in-root metadata and PNG files; absolute and `..` traversal.
- File and directory symlink escapes; junction and mount-point escapes; intermediate-component reparse traversal.
- Replace a file or intermediate directory between validation and open, including same-size replacement; verify the opened identity remains the validated one or the operation fails closed.
- File growth beyond 256 KiB / 10 MiB during reads; same-size concurrent content mutation; bounded memory, digest, size, and identity consistency.
- Directory/device/non-regular input, access denied, missing file, unsupported filesystem/API, and each fail-closed result.

Mocks can test call order, limits, hash calculation, and error mapping. They cannot establish Windows reparse handling, file identity, or race guarantees. Do not let `dom_evidence_package.py` read artifacts until specialist acceptance and real-platform tests are complete.

## Search-page validation specification

Current diagnostic fields are in `job_search.py` lines 96–133. Requested scopes are created before browser setup at lines 1041–1106. Navigation records response status and only a sanitized final origin at lines 1262–1280; the login check is a URL substring at lines 1297–1338. Collection uses fixed waits and three scroll attempts at lines 1274–1276 and 1366–1386, then records extracted links, selector/parser errors, and cap state at lines 1388–1419. Per-candidate failures are recorded at lines 1920–1937. These diagnostics do not currently prove page identity, settled results, or exhaustion.

| Requirement | Evidence needed in a separately approved read-only session | Scope/mismatch handling and acceptance test |
| --- | --- | --- |
| A. Requested/observed identity | Record configured keyword, location, scope ID/sequence and directly observed page query/location from the actual page. Do not infer observed identity from the requested URL or origin. | Bind each observation to one scope ID. A mismatch or absent observation remains unverified. Test exact match, mismatch, absent and contradictory identity. |
| B. Loading/settled | Capture actual loading-state observations over transitions and the result state they relate to. Validate a site-specific settled signal against the page; fixed delay or stable screenshot alone is insufficient. | Associate observations with scope and sequence/time. Test loading, settled, conflicting transitions and missing evidence. Do not choose selectors before inspecting real DOM. |
| C. Legitimate empty | Require a positively observed, site-specific empty-result state, expected identity, settled state, zero visible candidate cards, and no navigation/parser/interstitial error. Zero extracted links alone is insufficient. | Test legitimate empty separately from loading, parser failure, unsupported structure, and auth/challenge states. |
| D. Authentication/interstitial | Record an observed login, challenge, verification or other interstitial state as its own state. Stop without login, MFA, CAPTCHA, consent, or form interaction. Existing `"login" in page.url` is not a complete detector. | Bind state to the scope; any unexpected redirect or ambiguous page remains unknown and stops the session. Test each state and unexpected redirects using sanitized snapshots. |
| E. Pagination/exhaustion | For every observed batch, record ordered batch identity, evidence that more results are indicated or not, loading transition, and a directly referenced terminal observation. Validate the actual controls/structure before selecting any marker. | Sequence batches per scope; gaps, repeats, contradictory continuation/terminal evidence, failed batches, or missing terminal evidence cannot establish exhaustion. Test multi-batch continuation and final-batch conflict. A screenshot or displayed total alone is insufficient. |
| F. Per-scope/global caps | Record configured limits, observed per-search/global cap activation, processed scopes, skipped scopes, and whether a cap stopped work before a validated terminal state. Current diagnostics already record per-search/global cap flags and skipped scopes, but not cap-versus-exhaustion timing. | Test each cap independently, cap after verified terminal evidence, cap before terminal evidence, and unknown impact. Unknown impact stays unknown; known truncation is incomplete. |
| G. Candidate occurrences | Preserve every candidate occurrence recognized by the collector, its scope-local discovery order, selector, ID, duplicate relation, and eventual disposition. Compare observed occurrence ledger counts with parser output. | Keep cross-scope occurrences distinct. Test repeated selector observations, within/across-scope duplicates, missing/extra dispositions, and sequence/count mismatches. Existing selectors cannot prove undiscovered or unrecognized cards were absent. |
| H. Filter/processing completeness | Record the intended filter set and whether each filter was evaluated for every candidate, with outcome/reason; record candidate-page processing outcome separately. Current per-candidate reason/status is diagnostic, while adapter `filters_applied` remains unset. | Any missing filter or candidate disposition is unknown/incomplete per policy. Test each filter outcome, processing failure, and filter-ledger mismatch. A scope-level assertion alone is not independent verification. |
| I. Errors/conflicts | Retain navigation status where available, navigation/selector/parser/scroll/candidate-page failures, and run issues. Preserve contradictory observations rather than choosing one silently. | Map each error/conflict to its scope. Positive unresolved errors or known unprocessed work is incomplete; malformed, missing, or ambiguous evidence is unknown unless a higher-precedence failure/incomplete condition is established. |
| J. Provenance/scope association | Add a run identifier, capture time when known, code revision when known, requested scope ID/sequence, and sanitized evidence references. Keep provider assertions distinct from direct observations and independent review. | Verify all evidence references point to the same run and scope. Missing provenance remains unknown. A matching artifact hash verifies bytes only, not authenticity or capture origin. |

No CSS selector, success marker, empty-state text, pagination control, or terminal signal is approved by this specification. Site-specific markers must be selected only after inspecting actual sanitized page evidence and then tested against representative states.

## Minimum controlled validation plan

1. **Offline (already available):** use synthetic packages and mocks to test schema consistency, status precedence, scope/candidate ledgers, cap conflicts, fail-closed publication, and the completion-status `UNKNOWN` invariant. These tests verify code behavior, not real-site behavior.
2. **Windows specialist review:** resolve the reader contract above before relying on either artifact reader for externally supplied files. Include real filesystem tests; do not use artifact reading through an unreviewed fallback.
3. **Separately approved site-specific session:** authorize one user-selected query/location scope only. Use a fresh, nonpersistent browser context opened for this purpose; do not use CDP, saved profiles, or stored authentication. Capture sanitized, scope-associated observations for loading/settled state, a continuation state, and a terminal state by following that single search through its actual batches. Stop on login, verification, CAPTCHA, unexpected interstitial, or ambiguous identity. Do not click Apply, consent, or application controls. Redact personal UI before retaining evidence. If a terminal observation cannot be safely established, keep exhaustion unknown.
4. **Offline replay/review:** convert the sanitized observations into synthetic/frozen fixtures, review provenance and contradictions, and test expected state classification. Do not treat fixture validity as truth or production completion.
5. **Wait on integration:** only after the specialist and site-specific observations are independently reviewed should a narrowly scoped production acquisition change be proposed. Keep `publish_collection()` closed until all required scope identity, settled state, exhaustion, candidate disposition, filter, error, and cap evidence can be established in production.

This plan does not authorize browser launch or external navigation. It requests only one explicitly approved scope for future site-specific validation, not broad account access or application interaction.

## Publication boundary

`publish_collection()` in `job_search.py` lines 376–395 currently returns `False` for every outcome. The atomic writer is therefore unreachable through this publisher. The independent DOM package validator remains structural and fixed to `UNKNOWN`; neither a status string, synthetic package, screenshot, fixed wait, visible link count, nor provider assertion may authorize CSV replacement. Do not enable publication in Phase 25.

## Next milestone and blockers

1. Obtain a documented Windows specialist decision and pass real reparse/race tests.
2. Obtain separate explicit approval for the one-scope read-only page validation.
3. Review observed site-specific signals and resulting offline fixtures independently.
4. Only then scope production evidence-acquisition work; publication remains a later, separate gate.

Until then, the Windows artifact-reader security contract and site-specific completion evidence remain unresolved. No production readiness claim is made.
