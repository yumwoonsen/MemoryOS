# Phase 1/2 evaluation

Fluent prose alone is not a success criterion. MemoryOS must find the right episodes, know when to
abstain, protect consent, keep structured evidence references traceable, and reject the unsupported
factual patterns covered by its closed renderers and conservative lexical rules.

## Deterministic acceptance criteria

The automated suite covers:

- Stable top-three ranking and documented score composition
- Empty, weak, disputed, and dismissed candidate abstention
- Duplicate collapse, diversity selection, and deterministic tie-breaking
- Mixed-squad and mixed-target request rejection
- V1.0 review-state normalization into v1.1
- Prompt and output redaction for opted-out identities
- One perspective per opted-in participant, with no duplicates
- Known, opted-in quest assignees and at least two grounded objectives
- Exact enforcement of server-rendered memory facts, player-perspective facts, and quest-objective
  descriptions
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

The closed renderers make the tested memory, perspective, and objective clauses exact contractual
checks, but they do not turn the remaining model-authored title, type, quest title, mission, or
recipe into semantic proofs. Those framing fields still rely on bounded schemas, evidence/privacy
checks, conservative lexical rules, and human review.

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
python -m backend.evaluate --provider openai
```

The cost field uses configurable `OPENAI_INPUT_COST_PER_MILLION` and
`OPENAI_OUTPUT_COST_PER_MILLION` assumptions, so the report records the rates alongside the result.

## Prompt and model evaluation workflow

For any prompt or model change:

1. Run deterministic CI gates to protect schemas and guardrails.
2. Run the complete eligible fixture set in explicit OpenAI mode.
3. Save results outside source fixtures and remove any secret-bearing logs.
4. Compare ranking labels and generation metrics against the previous run.
5. Add a regression fixture for every newly observed failure mode.
6. Promote the change only when it improves usefulness without weakening grounding or consent.

Never use the live provider to calculate historical rank. Model comparisons begin only after the
same deterministic candidates have been selected and reviewed.

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
