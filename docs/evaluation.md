# Evaluation: v1.1 compatibility baseline and AI-first v2

Fluent prose alone is not a success criterion. MemoryOS must find the right episodes, know when to
abstain, protect consent, keep structured evidence references traceable, and reject the unsupported
factual patterns covered by its deterministic control plane and conservative lexical rules.

## Current v1.1 deterministic acceptance criteria

The automated suite covers:

- Stable top-three ranking and documented score composition
- Empty, weak, disputed, and dismissed candidate abstention
- Duplicate collapse, diversity selection, and deterministic tie-breaking
- Mixed-squad and mixed-target request rejection
- V1.0 review-state normalization into v1.1
- Prompt and output redaction for opted-out identities
- Rejection when fewer than two squad members are currently opted in
- One second-person perspective per opted-in participant, with no duplicates and at least one
  concrete anchor from that player's deterministic evidence set
- Known, opted-in quest assignees and at least two grounded objectives
- Enforcement of deterministic memory evidence, player ownership/citations, and quest verification
  controls while preserving model-authored narrative
- Rejection of invented IDs, mismatched event types, and tested unsupported patterns involving
  names, places, numbers, actions, and relationship claims
- No model call before source verification and meaning confirmation
- Safe behavior for refusal, timeout, quota, and malformed structured output
- FastAPI OpenAPI exposure of the v1.1 endpoints and response schemas

The original golden cases remain compatibility regressions:

1. Confirmed chaos becomes `ready` with distinct perspectives.
2. An unreviewed comeback stops at the appropriate human-review state.
3. Insufficient evidence becomes `rejected` without generated content.
4. Unknown players and invalid cross-references fail at input validation.
5. Invented evidence and unsupported relationships fail final validation.

## Current v2 acceptance criteria

The v2 route is implemented in this branch. Its release and regression gates must prove the
complete raw-input-to-decision contract, not only the quality of generated prose:

- A telemetry-only fixture with no authored caption or precomposed memory produces one valid live
  `MemoryProposal` from `POST /v2/memories/interpret-delivery`.
- Unknown event types, unsupported event/detail combinations, invalid cross-references, and
  unstructured current-context claims are rejected before any provider call.
- Raw opted-out identities and opted-out-authored social prose are absent from provider payloads,
  player output, logs, and Studio views. Important shared events may remain only with a
  request-scoped anonymous role for factual continuity; that role receives no perspective, media
  identity, invitation, or mission ownership.
- The provider selects exactly one deterministically offered chronological window and references
  only that window's allowed events, identities, context signals, and curated media mappings.
- Every factual clause has valid evidence references; perspectives cover exactly the opted-in
  roster; roles and current relevance are supported by structured inputs.
- Mission assignments, required flags, source event IDs, objective constraints, and verification
  rules exactly match deterministic controls.
- Refusal, timeout, malformed output, unsupported claims, and failed correction produce no
  proposal, teaser, perspective, mission, media selection, or rejected proposal prose in the
  player response or Studio.
- Live results are unambiguously labelled with provider, model, mode, and prompt version.
  Deterministic output is available only as an explicitly offline test or Studio demonstration and
  is never presented as a live-AI fallback.
- `POST /v2/deliveries/{delivery_id}/decision` accepts only `accepted` or `declined`; a decline
  requires exactly `not_relevant` or `details_wrong`. Both suppress that exact delivery, while
  `details_wrong` also creates an operations source-quality signal without editing telemetry.
- All v1.0/v1.1 compatibility tests remain green throughout migration.

The typed v2 offline evaluator reports:

| Metric | Definition | Release expectation |
|---|---|---:|
| Proposal validity | Live responses that pass schema and all deterministic validators | Report baseline; no invalid delivery |
| Episode-selection accuracy | Selected window matches an optional expected-window label | Report baseline |
| Factual-claim grounding | Offline-labeled factual claims that are grounded; unsupported claims are reported separately | 100% grounded; 0 unsupported |
| Offered-window compliance | Proposals select exactly one offered window and no outside events | 100% |
| Perspective roster precision/coverage | Returned player IDs exactly equal the opted-in roster | 100% |
| Perspective distinctness | Delivered player perspectives are pairwise distinct after normalization | Report baseline |
| Consent leak count | Supplied forbidden raw identity terms found in the serialized safe result | 0 |
| Mission feasibility and story connection | Mission validation passes and every objective source ID belongs to the selected episode | 100% |
| Fail-closed artifact count | Generated artifact fields returned after provider or validation failure | 0 |
| Media mapping validity | Selected media IDs whose deterministic mapping covers all required selected events | 100% |
| Deliverability and abstention correctness | Delivered/rejected outcome matches an optional expected-deliverability label | 100% |
| Correction outcome | Attempted correction and successful corrected delivery are counted separately | Report baseline |
| Provider usage | Safe observability totals for request count, latency, and input/output tokens | Report baseline |
| Feedback outcome | Accepted and declined decisions, reasons, and source-quality flags grouped by prompt/model version | Report baseline |

`summarize_v2_evaluation` consumes typed `V2OfflineEvaluationCase` values. Expected labels and
delivery decisions are optional, and evaluation never changes telemetry, prompts, provider
configuration, or model selection. `summarize_v2_results` remains available as the compatibility
smoke summary for callers that only provide interpretation results.

The complete proposal schema is tested against the v2 4,000-token output ceiling. Worst-case
opted-in rosters, references, and mission controls must still fail closed rather than return a
partial delivery.

## Historical ranking evaluation

Historical fixtures include strong, weak, stale, duplicate, dismissed, disputed, diverse, and
partially opted-out packs. The companion label file records synthetic expected-relevant and
expected-to-abstain candidates so ranking regressions can be measured rather than judged from one
attractive result.

| Metric | What the current evaluator calculates | Phase 1/2 expectation |
|---|---|---:|
| Candidate precision at 3 | Relevant labeled pack IDs among up to the first three selected IDs | Report baseline |
| Abstention correctness | Labeled abstain pack IDs whose deterministic assessment is ineligible because of a hard filter or a below-threshold score | 100% safety cases |
| Evidence-reference precision | Output event-ID references that exist in the source pack | 100% |
| Perspective coverage | Returned perspective count divided by opted-in member count across generated candidates | 100% |
| Perspective distinctness | Generated candidates whose normalized perspective strings are all exactly different | Report baseline |
| Consent leak count | Opted-out display names or quoted player IDs found in serialized result JSON | 0 |
| Quest verifiability | Generated candidates with a quest whose complete validation report passes | 100% |

The report also records provider, model, prompt version, wall-clock latency, token usage, and an
estimated cost based on configured rates. Live runs are opt-in and excluded from CI because they
require credentials and may incur cost.

These are deliberately narrow regression proxies. In particular, event-ID precision does not prove
the associated sentence is semantically entailed; exact-string distinctness does not measure
useful role diversity; and the serialized-output leak scan does not inspect provider-side storage or
logs. Prompt redaction is covered by separate tests. Human-labeled datasets and qualitative review
are still required before treating these values as product-quality measurements.

The deterministic control checks make evidence, identity, ownership, assignment, and verification controls exact,
but they do not turn model-authored memory, perspective, or quest prose into semantic proofs. Those
narrative fields still rely on bounded schemas, evidence/privacy checks, conservative lexical rules,
and human review.

There are a few mechanical edge cases to remember: no selected candidates yields precision `0`;
no labeled abstention cases yields abstention correctness `0`; no output references yields evidence
precision `0`; and an empty perspective set is vacuously "distinct" in the raw equality check, so
distinctness must be read beside coverage and generated candidate count. `quest_verifiability`
reuses the complete final validator result rather than independently grading only quest rules.

Run the committed synthetic fixtures in deterministic mode:

```powershell
python -m backend.evaluate --provider deterministic
```

The provider flag defaults to `deterministic`, so `python -m backend.evaluate` is equivalent. The
default files are `backend/data/historical_memory_packs.json` and
`backend/data/historical_eval_labels.json`; the command prints one JSON metric report to stdout.
Use `--fixture` and `--labels` to evaluate another compatible pair. The labels define relevant and
expected-to-abstain pack IDs; they are synthetic expectations, not collected player judgments. A
live run is explicit:

```powershell
python -m backend.evaluate --provider groq
python -m backend.evaluate --provider openai
```

The cost field uses configurable `OPENAI_INPUT_COST_PER_MILLION` and
`OPENAI_OUTPUT_COST_PER_MILLION` assumptions, so the report records the rates alongside the result.

## Prompt and model evaluation workflow

For any prompt or model change:

1. Run deterministic CI gates to protect schemas, normalization, consent filtering, window
   construction, mission controls, and validators.
2. Run the complete eligible fixture set in explicit Groq mode; use other providers only as a
   documented comparison.
3. Save responses and aggregate metrics only in an approved offline evaluation location; remove
   secrets, opted-out content, raw prompts, chain-of-thought, and provider exception text.
4. Compare proposal validity, factual-clause grounding, window compliance, roster coverage,
   mission-control integrity, latency, token use, and failure rate against the previous run.
5. Review narrative usefulness with human raters separately from deterministic safety checks.
6. Add a regression fixture for every newly observed failure mode.
7. Promote the change only when it improves usefulness without weakening grounding, consent, or
   fail-closed behavior.

For the v1.1 compatibility flow, never use the live provider to calculate historical rank. For v2,
deterministic code builds the eligible windows and the model may choose only one of those offered
windows; it does not expand eligibility or create a new episode boundary.

## Quality gates

Local and CI verification:

```powershell
$env:MEMORYOS_PROVIDER = "deterministic"
ruff check .
ruff format --check .
pytest
```

CI runs these checks on Python 3.11 and 3.13 without credentials or external model calls. The
OpenAPI contract smoke test is part of the normal pytest suite.

The integrated frontend has its own deterministic gates:

```powershell
cd frontend
npm ci
npm audit --audit-level=high
npm run typecheck
npm run lint
npm test
```

The rendered-flow tests cover the unrevealed state, evidence-first reveal, hosted fallback,
fail-closed errors, asset selection, and the absence of direct browser-to-localhost calls.
