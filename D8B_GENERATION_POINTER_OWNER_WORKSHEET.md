# D8b Generation-Pointer Owner Worksheet

**Status:** **OWNER APPROVED — OPTION C: EXPLICIT ROLLBACK AUTHORIZATION — POLICY DECISION ONLY.** This decision does not authorize implementation.

## Exact D8b question

“Which jobs may be evaluated or returned for retry review after restart, and separately, does a failed/interrupted generation retain prior selection, set `NONE`, or require explicit rollback?”

The application-selection portion has separate owner-approved policy directions only: never-attempted jobs remain eligible for normal evaluation; confirmed `APPLIED` jobs are excluded; confirmed non-submissions may enter retry review only; uncertain outcomes, confirmed-submission persistence failures, unavailable/corrupt/missing tracking state, and conflicting tracker/history are blocked. Non-submission alone does not authorize submission. The high-level retry policy requires affirmative evidence of non-submission. Those decisions and this pointer decision do not authorize implementation.

## Generation-pointer options

| Option | Behavior after a failed or interrupted attempt |
|---|---|
| **A. Retain the previous complete generation** | Keep the prior `COMPLETE` generation selected automatically while recording the new attempt as failed, partial, or interrupted. |
| **B. Set the active pointer to `NONE`** | Clear selection after a failed or interrupted attempt. A later validated successful generation may become selected; the prior generation can remain stored but is not selected. |
| **C. Require explicit rollback authorization** | Leave selection at `NONE` after failure. Reselect a retained prior `COMPLETE` generation only through a separately authorized and validated rollback event. |

## Trade-offs

| Concern | A. Retain previous complete | B. Set pointer to `NONE` | C. Explicit rollback authorization |
|---|---|---|---|
| **Data safety** | The failed attempt stays unselected, but older data remains implicitly current and may be stale for the present source. | Fails closed: no generation is selected after failure. The prior data can remain on disk without being exposed as current. | Fails closed by default and allows a prior complete generation to be selected only after an authorized, validated recovery. Requires trustworthy authorization and source checks. |
| **Failure recovery** | Fastest continuity; consumers can continue from the prior selection. It can mask a failed refresh unless the failure is visible to every consumer. | Recovery requires a new valid generation. This favors safety over continuity and may temporarily provide no candidates. | Can restore service from the prior generation after review, with an auditable recovery action. Recovery is unavailable until the authority and validation path are defined. |
| **Restart behavior** | A restart continues to see the old selection unless another process changes it. | A restart sees no selection until a valid new generation is published. | A restart sees no selection until a valid new generation or explicit rollback is published. |
| **Compatibility** | Most compatible with consumers that expect a current generation to remain available, though they must still detect the failed latest attempt and stale source. | Consumers must handle `NONE` without silently falling back to fixed-path CSVs. | Consumers must handle `NONE` and the explicit rollback state/event; this is the largest interface change. |
| **Duplicate-selection risk** | Highest relative risk: stale candidates can be evaluated again if downstream state is unavailable, inconsistent, or not bound to the generation. D8’s approved application policy still requires its own fail-closed checks. | Lowest by default because no candidates come from a selected generation. Risk returns if consumers bypass the pointer or fall back to old fixed-path files. | Low while selection is `NONE`; after rollback, risk depends on source matching, generation validation, and the approved application/tracker evidence rules. |
| **Implementation complexity** | Lowest pointer-state change, but reliable stale-state signaling and source freshness checks are still needed. | Relatively low; consumers and restart recovery must consistently treat `NONE` as zero selected candidates. | Highest; requires verifiable authority, audit data, rollback validation, source-identity rules, and restart-safe publication. |

## Owner-approved pointer policy

**OWNER APPROVED — OPTION C: EXPLICIT ROLLBACK AUTHORIZATION — POLICY DECISION ONLY.** The approved conditions are:

1. Failed or interrupted generations must not become active automatically.
2. Active generation selection remains `NONE` after a failed or interrupted attempt.
3. Previous `COMPLETE` generations remain preserved.
4. Reselecting a previous generation requires explicit rollback authorization.
5. Rollback requires validation of selected-generation completeness, source-fingerprint compatibility, generation identity, rollback authority, rollback reason, and required audit evidence.
6. Missing, malformed, or conflicting evidence must fail closed.
7. Rollback must not silently overwrite historical generation records.

This is a policy decision only. D8a must still define failure/interruption classification; D10 authority and audit rules, D12 compatibility, and D13 independent storage/security review remain dependencies. No implementation, pointer publication, rollback, recovery, or history mutation is authorized. The helper’s string-valued rollback fields are not proof of authorization.

The isolated helper currently permits `EXPLICIT_ROLLBACK` only when the latest attempt is `FAILED` or `PARTIAL`; `IN_PROGRESS` can use `NONE` but cannot yet be rolled back through that validator. The helper also requires the selected prior generation to be `COMPLETE` and match the current source fingerprint. These are helper validation constraints, not production behavior or proof that the approved authorization/evidence conditions are implemented.

## Owner decision record

Selected option: **C — Explicit Rollback Authorization**

Decision: **OWNER APPROVED — POLICY DECISION ONLY.**

Conditions: the seven approved conditions listed above.

Decision source: project owner instruction in the current task. No individual name, approval date, or reviewer identity was supplied; none is inferred.

**Implementation authorization:** NOT GRANTED. **Response status:** POLICY APPROVED; implementation remains blocked.
