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

An observed cap is not automatically incomplete if exhaustion was
independently verified before the cap prevented any required work. If the cap
may have truncated an unexhausted scope, classify INCOMPLETE. If cap timing or
exhaustion is unknown, classify UNKNOWN.

## Current model boundary

`job_search.CollectionEvidence` represents one aggregate evidence record. It
has aggregate counts and booleans, but no per-query/location scope records or
per-candidate disposition ledger. Its classifier is a pure policy helper and
is not called by the production collector. The production collector continues
to produce UNKNOWN for clean runs and does not have evidence to prove search
exhaustion. The offline screenshot/metadata validator always returns UNKNOWN.

Consequently, this policy can be tested as a single-scope decision table using
the current helper, but multi-scope aggregation and per-candidate completeness
cannot safely be implemented against the current model. The smallest future
model change is a separate offline `CollectionRunEvidence` containing required
`ScopeEvidence` records, each with explicit verification fields, cap/exhaustion
evidence, and candidate dispositions. Missing values must remain missing; a
fixture label, displayed total, screenshot, nonzero link count, fixed wait, or
absence of exceptions must never manufacture verification.

No production collector, classifier, publisher, browser, CDP, network, or
application workflow is connected by this specification.
