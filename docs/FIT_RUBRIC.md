# Core fit rubric and evaluation baseline

Status: **draft for Thomas review**, 2026-11-25. Implements the evaluation foundation for
[Core 01, #36](https://github.com/tjfalcon/rolesignal/issues/36), first in the
[active delivery order, #41](https://github.com/tjfalcon/rolesignal/issues/41).
This increment defines a proposed output contract and measures the existing analyzer. It does
not implement fit synthesis or change public scoring, API responses, or the UI.

## What the signal means

The signal describes fit to the work using reviewed candidate evidence and explicitly supplied
constraints. It is neither interview probability nor a hiring prediction. Missing evidence means
the selected profile does not establish a claim; it does not prove the candidate lacks the skill.

Evaluate these dimensions separately before synthesizing a signal:

1. **Core work:** the activities central to this role. A matching secondary keyword cannot make
   up for missing evidence of the daily work.
2. **Mandatory qualifications:** consequential prerequisites, including depth, scope, duration,
   and whether a compound requirement is fully evidenced. Prototype experience does not establish
   production ownership. A technology mention does not establish proficiency or years.
3. **Preferences:** useful additions whose absence alone should not decide the signal.
4. **Career direction:** compare only against explicitly reviewed goals when available. Do not
   invent a desired title or interpret a missing preference as a mismatch.
5. **Material constraints:** salary, location, schedule, authorization, and similar conditions
   require current confirmation. Employer assertions are job facts, not candidate facts.

## Proposed labels

| Signal | Proposed interpretation |
| --- | --- |
| Strong fit | Direct evidence covers the central work and consequential qualifications; no established decisive gap or confirmed blocker. |
| Plausible fit | Credible direct or transferable core experience, with a bounded gap or uncertainty about the core work that merits discussion. |
| Stretch | Meaningful transferable evidence exists, but a central responsibility or substantial mandatory qualification remains unproved. |
| Poor fit | The central work has little relevant support, or a confirmed material constraint blocks the role. Matching secondary skills cannot override that reason. |
| Insufficient information | Too little reliable job or candidate information to judge the central work; ask for the missing information. |

Apply insufficient-information handling when the central work cannot be identified. With enough
information, consider confirmed blockers and decisive core gaps before preferences. Distinguish
unconfirmed conditions from established conflicts. Contradictory employer statements remain an
explicit question, rather than a guessed requirement or a guessed candidate incompatibility.

**Confirmed by Thomas, 2026-11-25:** unknown salary, location, or work authorization must not cap
an otherwise Strong fit at Plausible fit. Keep the fit signal and attention state separate.
Unresolved terms, including contradictory attendance statements, require manual review; they are
not a confirmed candidate incompatibility. Confirmed material blockers still affect the signal.
Individual case judgments and the rest of the rubric remain draft.

For the result UI in #37, show an amber attention icon with the text **Needs review** beside the
fit label when unknowns remain. The text and icon must communicate the state without relying on
color alone. Expanding the indicator should list the unresolved items, such as salary, location,
and authorization, with a focused confirmation question. For example, **Strong fit · Needs review**
means the work matches while those conditions await confirmation. Clearing the last unresolved
item clears the indicator; confirming a blocker can also change the fit result.

The mixed web/CUDA example is proposed Poor fit because the role's central work is kernel research;
commerce experience supports only a secondary qualification. The Python/GPU example is proposed
Stretch because Python is part of the stated central work, with the infrastructure portion missing.
These boundaries are deliberate review targets, not calibrated rules.

## Proposed output contract

[`FitDecision`](../evals/fit.py) is an evaluation-only Pydantic contract:

- `signal`: one of the five labels; no numeric fit score or hiring probability.
- `decisive_reason`: concise explanation with exact requirement quotes, evidence IDs, and any
  explicit scenario-context references used to reach the decision.
- `top_gap`: the most consequential gap or unresolved condition, with source references, or
  `null` if none is identified.
- `unknowns`: explicit unresolved information keys, such as `salary`, `location`,
  `work_authorization`, `core_work`, or unverified duration. Omission is not confirmation.
- `needs_review`: an independent attention flag, true when `unknowns` is nonempty. Validation
  prevents unresolved items from being hidden behind a false flag. This flag does not cap fit.
- `what_would_change`: a focused question or new evidence that could alter the conclusion.

Requirement annotations distinguish core, mandatory, preference, and constraint roles; label
importance and acceptable assessment states; and list permissible supporting evidence IDs.
The proposed synthesis contract will need analysis/profile-version identifiers at the runtime
boundary when local sessions and fit synthesis are implemented in #42 and #37.

Exact reference matching makes reason and gap selection measurable without requiring identical
prose. It cannot establish that a fluent explanation logically follows from those sources.
Explanation correctness, completeness of compound claims, and the usefulness of the follow-up
question require human review. The evaluator does not use keyword similarity as a semantic judge.

## Cases and provenance

[`fit_cases.json`](../evals/fit_cases.json) contains 12 agent-authored synthetic jobs, all explicitly
marked `draft`. No live employer posting, private résumé, tracker record, email, or proprietary
source text was imported. Candidate evidence comes only from the existing sanitized `demo-thomas`
and fictional `synthetic` fixtures. SHA-256 snapshots pin their validated contents; an evidence
change requires deliberate label review and snapshot update.

The confirmed-location-blocker example includes a **fictional scenario-only** candidate condition.
It is not Thomas's location preference and is never written to a profile. The current analyzer
cannot consume this extra context; the baseline states that limitation.

Each case supplies the full posting, expected signal, decisive reason, top gap, unknowns,
what would change the decision, requirement checks, and a review record. The review validator
requires a reviewer and date before a case can be marked reviewed. No agent-authored proposal is
presented as Thomas's judgment.

## Running and interpreting the baseline

```bash
.venv/bin/python -m scripts.evaluate_fit
.venv/bin/python -m scripts.evaluate_fit --format json
.venv/bin/python -m scripts.evaluate_fit --reviewed-only
```

The runner uses the real request validator, parser, local retrieval, and assessment service, with
no database access or external model call. API tests verify the same observations through
`POST /v1/analyze`, including the current rejection of the short blurb. Rejection is recorded as
an input failure, not silently repaired, padded, or counted as an insufficient-information verdict.
No fit label is inferred from `evidence_coverage`.

The [recorded baseline](../evals/CORE_FIT_BASELINE.md) reports overall decisions as **unavailable**
because the current app does not return them. Until synthesis exists, this is an end-to-end
evaluation harness with observed component failures, not evidence of end-to-end fit accuracy.

The JSON report includes:

- Requirement extraction, provenance, importance, assessment, and relevant-citation checks.
- Citation integrity against returned evidence **and** pinned fixture claims. This catches
  dangling IDs, invented sources, altered claims, and candidate citations on missing/unknown rows.
  Reference validity alone still does not establish semantic support.
- Separate counts of proposed labels versus returned labels, including `unavailable`.
- Expected and actual attention flags, scored separately from fit. When no decision exists,
  actual attention is `null`, rather than falsely indicating that everything is confirmed.
- False-positive Strong fit case IDs: predicted Strong fit with a different expected label.
- False-negative Poor fit case IDs: predicted Poor fit with a different expected label.
  These lists include only returned decisions. Zero entries with zero decisions conveys no quality.

Draft requirement disagreements are observations, not CI failures. CI checks the fixture contracts,
objective citation integrity across the real baseline, and the evaluator's ability to catch injected
regressions. It does not freeze the analyzer's known defects as expected behavior. Newly reviewed
judgments can later become acceptance gates; `--reviewed-only` exits with an error while there are
no reviewed cases.

## Review and next delivery

Thomas should read the cases in the report and adjust each signal, decisive reason, top gap,
unknowns, and acceptable evidence references. Record his actual judgments with reviewer/date/notes;
add consent-safe representative jobs if these synthetic examples miss important boundaries.
Do not bulk-mark these cases reviewed from agreement with the label names alone.

Before treating a fit threshold as final, review every Strong/Poor disagreement separately, verify
that every positive claim is supported in full, and confirm that unknown constraints remain visible.
No calibrated percentage or numerical acceptance threshold is claimed by this draft.

Next in the ordered track is local job context and profile drafts (#42), followed by fit synthesis
and result UI (#37). The measured extraction/assessment defects belong in that later reliability
work. Conversation, correction, uploads, pipeline workflows, and hosted authentication remain in
their respective later issues. This foundation does not close #36 until the human review is done.
