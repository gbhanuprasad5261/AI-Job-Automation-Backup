# Collection Evidence Policy (Offline Specification)

This document specifies conservative collection classification. It does not
provide page selectors, live-capture logic, or production integration. Fixture
labels and synthetic evidence are assertions; they are not independent proof
of live search behavior.

## Precedence

Apply the first applicable rule:

1. **FAILED** — a fatal setup or execution failure makes the required
   collection attempt impossible or invalid.
2. **INCOMPLETE** — reliable evidence establishes unfinished required work:
   an unresolved error, an unprocessed required scope or candidate, known
   additional results/batches, or a cap that stopped work before verified
   exhaustion.
3. **UNKNOWN** — evidence is absent, ambiguous, malformed, contradictory, or
   insufficient. Examples include an unverified search identity, unsettled
   results, missing exhaustion evidence, missing candidate dispositions, and
   zero links without a verified empty-state observation.
4. **COMPLETE** — every required scope has independently verified identity,
   settled results, terminal exhaustion, a disposition for every discovered
   candidate, and accounting for every intended filter; there are no
   unresolved errors or caps that stopped work before exhaustion; at least one
   qualifying job remains.
5. **COMPLETE_EMPTY** — every COMPLETE requirement holds, and the verified,
   settled, exhausted results contain no qualifying job after all intended
   filters.

For multi-scope runs, any known incomplete scope makes the overall result
INCOMPLETE. If none is known incomplete but any scope is unclassifiable, the
overall result is UNKNOWN. Only all-verified scopes can yield COMPLETE or
COMPLETE_EMPTY.

The offline multi-scope model applies these structural rules:

- An empty requested-scope set is UNKNOWN; it is not vacuously complete.
- A requested scope with no evidence record is INCOMPLETE because required
  work is unaccounted for.
- Duplicate requested scopes, duplicate or unexpected scope records, duplicate
  candidate IDs without an explicit occurrence link, malformed dispositions,
  and contradictory candidate counts are UNKNOWN unless a higher-precedence
  known failure or incomplete condition is present.
- A candidate occurrence is one ordered discovery record under one scope;
  candidate identity is the ID used to recognize repeated jobs. A repeated
  selector observation within a scope remains a separate ledger occurrence and
  may be recorded as `DUPLICATE` with `DUPLICATE_WITHIN_SCOPE`, an earlier
  sequence reference, and processing status `DUPLICATE`. This is explicit
  duplicate accounting, not a claim that the repeated occurrence was processed
  as a qualifying or filtered candidate.
- The same candidate ID may appear in multiple scopes. Each record remains a
  distinct scope occurrence. A cross-scope output-deduplication record must
  retain its source scope, discovery sequence, and reference to the prior scope
  occurrence in separate output-deduplication fields. Its scope disposition
  remains UNPROCESSED. The offline run classifier treats that currently-skipped
  cross-scope occurrence as INCOMPLETE; it does not inherit the earlier scope's
  disposition. The same ID can be independently qualified or filtered in each
  scope when each scope has its own explicit disposition. This classifier does
  not compute a globally unique-job count or deduplicate combined output.
- A discovered-candidate count larger than the disposition ledger is
  INCOMPLETE. A smaller count contradicts the supplied ledger and is UNKNOWN.
- Every candidate occurrence must be explicitly accounted for. A first unique
  occurrence must be QUALIFYING or FILTERED, and the scope must affirm that
  intended filters were applied. An explicitly linked within-scope repeat is
  accounted as DUPLICATE but is not counted as processed/qualifying. A skipped
  cross-scope repeat is preserved as an output-deduplication observation and makes the run INCOMPLETE
  until that scope has its own disposition. UNPROCESSED is INCOMPLETE; missing
  or unknown disposition evidence is UNKNOWN.
- FILTERED occurrences require one reason code from the shared vocabulary:
  CLOSED_JOB, OUTSIDE_TARGET_LOCATION, NOT_EASY_APPLY, or OTHER_FILTER.
  UNPROCESSED may record PROCESSING_ERROR. These codes describe supplied
  evidence; they do not prove that the filter or processing failure occurred.

`filters_applied` remains a scope-level assertion: `True` asserts that the
producer accounted for all intended filters for that scope; `False` establishes
that filter work remains and is INCOMPLETE; missing or malformed evidence is
UNKNOWN. A FILTERED occurrence now carries a reason code, but neither that code
nor `filters_applied` independently verifies execution or represents separate
observations for each filter.

An observed cap is not automatically incomplete if exhaustion was
independently verified before the cap prevented any required work. If the cap
may have truncated an unexhausted scope, classify INCOMPLETE. If cap timing or
exhaustion is unknown, classify UNKNOWN.

## Current model boundary

`job_search.CollectionEvidence` remains an aggregate single-record helper; it
does not model per-query/location records or a candidate disposition ledger,
does not contain an explicit legitimate-empty page observation, and its
classifier is not called by the production collector. It therefore leaves a
zero-candidate result UNKNOWN; fully processed candidates that are all filtered
may still be COMPLETE_EMPTY under the supplied filter assertions. The separate
`collection_run_evidence.py` module models multi-scope evidence and candidate
dispositions as an offline policy only. It does not establish that supplied
assertions are true, inspect pages, or connect to production collection or
publication. The production collector continues to produce UNKNOWN for clean
runs because it has no evidence to prove search exhaustion. The offline
screenshot/metadata validator always returns UNKNOWN.

Production search diagnostics retain selector-level candidate link
occurrences before per-scope and cross-scope deduplication. Each occurrence
records its scope-local order, selector, processing state, final disposition,
and a reason code for filtering or deduplication when observed. These are
collector diagnostics, not verified completion evidence: overlapping selectors
can observe the same rendered link more than once, and configured scan caps
can stop discovery before later links are examined. Candidate-page processing
continues to leave the collection outcome UNKNOWN or INCOMPLETE as appropriate.

Production publication remains closed because the production diagnostics
adapter cannot verify the required page identity, settled state, exhaustion,
and complete filter evidence.
`publish_collection()` rejects all outcomes, including manually constructed
COMPLETE/COMPLETE_EMPTY statuses and structurally valid offline classifier
results. No token or status-only bypass authorizes replacement. The atomic
writer remains isolated behind this fail-closed boundary; no current workflow
reaches it through `publish_collection()`.

Missing values must remain missing; a fixture label, displayed total,
screenshot, nonzero link count, fixed wait, or absence of exceptions must never
manufacture verification.

## Page-state and pagination evidence vocabulary

The shared offline state vocabulary distinguishes
`POPULATED_RESULTS_SETTLED`, `LEGITIMATE_EMPTY`, `LOADING_OR_UNSETTLED`,
`AUTHENTICATION_REQUIRED`, `CHALLENGE_OR_INTERSTITIAL`, `NAVIGATION_ERROR`,
`PARSING_ERROR`, `PAGINATION_BATCH_FAILED`, `POPULATED_MORE_PAGINATION`,
`EXHAUSTION_REVIEW_RECORDED`, and `UNKNOWN`. A non-unknown state requires its
state-specific observations and evidence references in the DOM package
validator. A label remains a supplied interpretation; structural validation
does not verify the referenced bytes or prove the page actually had that
state. Settled search states require directly referenced query/location
observations, a matching assertion, settled loading history, and a sanitized
DOM-artifact reference. Empty additionally requires zero visible cards and a
directly referenced empty-state observation. Authentication and challenge
states require a distinct interstitial kind and cannot be interpreted as empty
search results. Navigation and parsing errors require matching direct error
observations. Missing or conflicting evidence is rejected or left UNKNOWN.
An exhausted scope with zero discovered candidates must be explicitly classified
as `LEGITIMATE_EMPTY`; an exhaustion-review record alone cannot establish an
empty result.

The offline pagination contract requires unique, contiguous one-based batch
sequences. Every earlier observed batch must say that another batch is
indicated; the final batch must either indicate more (INCOMPLETE) or carry an
explicit terminal evidence reference. A terminal claim also requires a
recorded independent-review assertion and explicit cap-impact fields. A failed
batch is INCOMPLETE, an unknown cap effect is UNKNOWN, and a cap that may have
stopped work before terminal evidence is INCOMPLETE. These are consistency
rules for supplied observations, not validation of any live site's controls.

## Production evidence availability

| Requirement | Evidence currently recorded | Availability classification | Boundary |
| --- | --- | --- | --- |
| Requested versus observed query/location identity | Requested keyword/location and scope ID are recorded; only final URL origin is recorded from the page | REQUIRES INDEPENDENT SITE-SPECIFIC VALIDATION | The page's observed query/location is not captured or compared. |
| Settled result state | `DOMContentLoaded` navigation and fixed waits | NOT ESTABLISHED | Neither is a result-settled signal. |
| Legitimate empty results | Extracted-link count can be zero | REQUIRES INDEPENDENT SITE-SPECIFIC VALIDATION | Zero links cannot distinguish empty results from loading, parser failure, interstitial, or unsupported structure. |
| Authentication/interstitial/challenge state | A URL substring check for `login` exists; navigation failures are counted | REQUIRES INDEPENDENT SITE-SPECIFIC VALIDATION | The diagnostic record does not identify page state, and no challenge/interstitial evidence is captured. |
| Pagination continuation and terminal state | Scroll attempts/failures and per-search extracted links | NOT ESTABLISHED | No batch sequence, continuation observation, or terminal observation is recorded. |
| Cap impact | Per-search/global cap flags, skipped scopes, and scope attempt flags | AVAILABLE FROM CURRENT PRODUCTION DIAGNOSTICS | Cap activation and skipped requested scopes are observable; whether a cap interrupted verified exhaustion is not. |
| Candidate occurrence accounting | Ordered recognized candidate occurrences, duplicate links, and processing dispositions | AVAILABLE FROM CURRENT PRODUCTION DIAGNOSTICS | The ledger is limited to links recognized by existing selectors; parse errors and caps remain explicit unresolved evidence. |
| Filter and processing dispositions | Candidate processing status, disposition, and reason code; unresolved errors | NOT ESTABLISHED | Per-candidate outcomes are recorded, but there is no scope-level proof that every intended filter ran successfully. |
| Unresolved errors | Navigation, selector/parser, scroll, candidate-page counters, and run issue list | AVAILABLE FROM CURRENT PRODUCTION DIAGNOSTICS | Any positive recorded error prevents a successful classification; counts remain diagnostic and can overlap. |
| Scope/run provenance | Ordered requested scopes and matching diagnostic scope IDs | AVAILABLE FROM CURRENT PRODUCTION DIAGNOSTICS | No durable run identifier, capture timestamp, or code revision is recorded; request identity is not observed page identity. |

The adapter/classifier integration below exposes these recorded facts and
leaves missing observations absent. No item in this matrix supplies
independent site-specific completion evidence.

## Production diagnostics adapter boundary

`collection_diagnostics_adapter.py` is a one-way offline transformation into
the canonical model. It requires the caller to provide the requested scope set;
it does not reconstruct that set from observed diagnostics. It preserves the
producer's candidate occurrence order, per-scope candidate IDs, reason codes,
processing statuses, scope sequence, duplicate links, cap observations, and
error counts. `job_search.py` now passes the requested scopes created directly
from its configured keyword/location pairs and attaches both the canonical
evidence and its diagnostic classification to `CollectionOutcome`. The
requested set is created before browser setup, so setup failures and cap-skipped
scopes remain visible to the model. A missing requested-scope record remains
missing and classifies as INCOMPLETE.

The collector does not record observed query/location identity, settled
loading, a verified legitimate-empty state, pagination batches or exhaustion,
or a scope-level assertion that all intended filters were applied. The adapter
leaves these fields absent. It may not derive them from navigation success,
fixed waits, visible counts, screenshots, no exceptions, or the `valid` field
of `dom_evidence_package.PackageValidation`. Candidate accounting alone
therefore remains UNKNOWN for clean non-duplicate runs; explicit skipped work,
recorded errors, or a validated cross-scope duplicate remains INCOMPLETE. A
clean navigation, visible links, and processed candidate details do not fill
those missing fields. The production outcome uses the canonical diagnostic
classification, which can conservatively refine a run to INCOMPLETE when its
recorded diagnostics establish unprocessed scope or candidate work. It cannot
produce COMPLETE or COMPLETE_EMPTY from the current diagnostics.

`publish_collection()` remains closed and rejects every outcome. The attached
evidence and classification are diagnostic data only; neither is an
authorization capability, and no manually constructed status or evidence
object reaches the atomic writer through the publisher.

`candidate_occurrences` counts every ordered occurrence, including repeated
selector observations. `candidate_identity_ids` separately preserves the
producer's unique per-scope ID sequence, and its reported count must agree with
the unique IDs derived from the occurrence ledger. The model permits the same
candidate ID in separate scopes but validates a cross-scope duplicate link
against an earlier occurrence in the requested run order. Output-level
deduplication remains distinct from scope-level disposition and must not erase
the occurrence ledger.

This is limited in-memory diagnostics integration, not page-state evidence
acquisition or publication integration. Production collection continues to
emit UNKNOWN for otherwise clean runs and publication remains fail-closed.

The artifact readers' Windows path-containment and replacement-race concerns
remain a separate unresolved security blocker. The future adapter must not
read evidence artifacts through those readers until a supported Windows
security contract and platform tests have been reviewed.

Required specialist acceptance must define a trusted root, document the
supported Windows versions and filesystems, and demonstrate root-relative
handle opening that rejects intermediate and final reparse traversal. The
specialist must address symbolic links, junctions, mount points and other
reparse tags; same-handle identity/type/size checks; bounded reads and hashing;
replacement and growth races; access denial; and fail-closed behavior. Tests
must include real Windows filesystem coverage for reparse and race semantics;
mocked tests alone cannot establish kernel or filesystem guarantees.

No production collector, classifier, publisher, browser, CDP, network, or
application workflow is connected by this specification.
