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
- A discovered-candidate count larger than the disposition ledger is
  INCOMPLETE. A smaller count contradicts the supplied ledger and is UNKNOWN.
- Every candidate must be explicitly QUALIFYING or FILTERED, and the scope
  must affirm that intended filters were applied. UNPROCESSED is INCOMPLETE;
  missing or unknown disposition evidence is UNKNOWN.

An observed cap is not automatically incomplete if exhaustion was
independently verified before the cap prevented any required work. If the cap
may have truncated an unexhausted scope, classify INCOMPLETE. If cap timing or
exhaustion is unknown, classify UNKNOWN.

## Current model boundary

`job_search.CollectionEvidence` remains an aggregate single-record helper; it
does not model per-query/location records or a candidate disposition ledger,
and its classifier is not called by the production collector. The separate
`collection_run_evidence.py` module models multi-scope evidence and candidate
dispositions as an offline policy only. It does not establish that supplied
assertions are true, inspect pages, or connect to production collection or
publication. The production collector continues to produce UNKNOWN for clean
runs because it has no evidence to prove search exhaustion. The offline
screenshot/metadata validator always returns UNKNOWN.

Missing values must remain missing; a fixture label, displayed total,
screenshot, nonzero link count, fixed wait, or absence of exceptions must never
manufacture verification.

No production collector, classifier, publisher, browser, CDP, network, or
application workflow is connected by this specification.
