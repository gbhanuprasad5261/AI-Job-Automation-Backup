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
  candidate IDs within a scope, malformed dispositions, and contradictory
  candidate counts are UNKNOWN unless a higher-precedence known failure or
  incomplete condition is present.
- Candidate IDs are unique within each scope's occurrence ledger. The same ID
  may appear once in each of multiple scopes; each such record is a distinct
  scope occurrence and must be accounted for in that scope. This classifier
  does not compute a globally unique-job count or deduplicate combined output.
  Any output-level deduplication must be an explicit downstream policy and
  must not erase the per-scope evidence.
- A discovered-candidate count larger than the disposition ledger is
  INCOMPLETE. A smaller count contradicts the supplied ledger and is UNKNOWN.
- Every candidate must be explicitly QUALIFYING or FILTERED, and the scope
  must affirm that intended filters were applied. UNPROCESSED is INCOMPLETE;
  missing or unknown disposition evidence is UNKNOWN.
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

Production publication remains closed because no production adapter verifies
the required page identity, settled state, exhaustion, and candidate evidence.
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

## Future production adapter contract (not implemented)

A future adapter must consume collector-native observations per requested
scope and preserve the run sequence, requested keyword/location, observed
keyword/location with evidence references, identity-match state, loading
state, page interpretation, pagination/batch observations, cap impact,
candidate occurrences, dispositions/reason codes, and unresolved errors.
Every requested scope must have a record, including scopes not attempted after
a cap or fatal setup failure. Candidate IDs are scoped occurrences; output
deduplication must not erase occurrences in other scopes.

The adapter must map absent or unsupported observations to UNKNOWN and may not
derive identity, settled state, empty results, exhaustion, or candidate
accounting from navigation success, fixed waits, visible counts, screenshots,
no exceptions, or the `valid` field of `dom_evidence_package.PackageValidation`.
That validator checks package structure only and remains disconnected from
publication. No production adapter currently supplies the required verified
site observations, so production collection continues to emit UNKNOWN for
otherwise clean runs and publication remains fail-closed.

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
