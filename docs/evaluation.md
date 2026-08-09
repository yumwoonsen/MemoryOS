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

The V2.1 route is implemented in this branch. Its release and regression gates must prove the
complete raw-input-to-decision-to-projection contract, not only generated-prose quality:

- `RawTelemetryBatchV2` accepts `schema_version` `2.0` and `2.1`; every typed
  `InterpretDeliveryResultV2` is `2.1`.
- Unknown event types, unsupported event/detail combinations, invalid cross-references, and unsafe
  context are rejected before any provider call.
- Preparation produces a consent-safe `StoryBriefV2` with no more than four narratively neutral
  `eligible_event_windows`; words such as “meaningful”, “heroic”, “funny”, or “clutch” are absent
  from the structural window projection.
- Raw opted-out identities and opted-out-authored social prose are absent from provider payloads,
  player output, logs, and Studio. A request-scoped anonymous role may preserve factual continuity,
  but receives no perspective, media identity, invitation, or mission assignment.
- Mission affordances are derived dynamically from evidence and deterministic feasibility and
  verifiability checks, and belong to exactly
  three families: `reunion`, `role_reversal`, and `redemption`. Removing the supporting revive
  removes role reversal; repeated places four through six enable redemption; reunion remains only
  when its consent, target, mode, and context conditions hold.
- Invitation eligibility is independent of `active_player_ids`. Inactive but memory- and
  invitation-consented players remain invitation-ready; `online`/`away` is presentation only.
- AI returns `ProviderInterpretationDecisionV2`: either `generate` with a complete ranking of
  request-scoped `A#` affordances whose first choice determines the linked `W#` episode, or
  `abstain` with exactly `no_meaningful_episode` and no proposal. A validated abstention becomes
  `not_generated` with
  `ai_no_meaningful_episode` and no player artifacts.
- AI compares the offered episode-and-mission combinations and should normally choose the strongest
  direct evidence-linked continuation. `reunion` is the general fallback when no more coherent
  specific continuation is supported. Serialized order, `A#` reference number, and nested `O#`
  count are not preference signals. Deterministic validation has no family-priority rule; it checks
  only that the chosen option is offered, grounded, consent-safe, feasible, and correctly expressed.
- For generation, the backend resolves the selected window and affordance into authoritative
  match/event IDs and complete `GroundedClaim` records. It owns the selected objective set, recipe,
  assignments, required flags, verification metrics/operators/targets, and all source references.
  The AI authors only bounded player-facing descriptions and supported fact/capability references.
- Perspectives are ordered and exact-set validated against the eligible consent-safe roster; a
  missing perspective is never restored. Normalized facts retain `player`, `squad`, and `match`
  scope, and collective perspective language requires allowlisted complete-roster evidence.
- Categorical details pass deterministic key/value allowlists. Cue-bound categorical/numeric
  checks, role-tuple checks, memory-type/history checks, privacy checks, and final validation still
  apply after compact expansion.
- One correction is allowed for repairable live schema, expansion, or validation failures. Rejected
  prose and free-form validator messages are not recycled. A second failure, fatal issue, provider
  refusal/timeout, or unsupported claim fails closed with no generated player artifacts.
- Live results are labelled with provider, model, mode, prompt version, and
  `content_origin: "live_ai_validated"`. Deterministic prose is limited to clearly labelled
  Studio/test samples and is never a live player fallback.
- The browser receives a minimal projection with request-scoped `recipient_ref` and `objective_ref`
  values, one current-player perspective, and one selected **Next Chapter**. Raw player/event/objective
  IDs, complete claims, verification rules, source references, and Studio trace do not cross that
  boundary.
- Studio exposes sanitized dynamic affordances, ranked/selected family and reason codes,
  backend-owned controls, validation/correction, active versus invitation-ready counts, and typed
  abstention, without rejected prose or opted-out identities.
- The post-accept flow is explicitly scripted: invitations, squad joins, game start, game end, then
  mission complete. Tests must not describe this as new-match telemetry ingestion or real objective
  verification.
- `POST /v2/deliveries/{delivery_id}/decision` accepts only `accepted` or `declined`; a decline
  requires exactly `not_relevant` or `details_wrong`. Both suppress that exact delivery, while
  `details_wrong` records a source-quality signal without editing telemetry.
- All V1.0/V1.1 compatibility tests remain green throughout migration.

The typed v2 offline evaluator reports:

| Metric | Definition | Release expectation |
|---|---|---:|
| Compact-decision schema reliability | Live responses that parse `ProviderInterpretationDecisionV2` without repair | Report generate/abstain/invalid rates by model and prompt |
| Reference-resolution success | Compact references resolve inside the selected window and selected affordance; any conservative evidence addition survives complete validation | 100% for delivered results |
| Deterministic enrichment completeness | Required public IDs, claims, roster, media, objective set, assignments, metrics/operators/targets, source references, delivery fields, and trace fields come from trusted state | 100% for delivered results |
| Public-contract stability | Enriched public delivery and generated OpenAPI remain compatible with existing player/Studio consumers | 100%; no unreviewed breaking diff |
| Proposal validity | Live responses that pass schema and all deterministic validators | Report baseline; no invalid delivery |
| Episode-selection accuracy | Selected window matches an optional expected-window label | Report baseline |
| Factual-claim grounding | Offline-labeled factual claims that are grounded; unsupported claims are reported separately | 100% grounded; 0 unsupported |
| Offered-window compliance | Proposals select exactly one offered window and no outside events | 100% |
| Perspective roster precision/coverage | Returned player IDs exactly equal the opted-in roster | 100% |
| Perspective distinctness | Delivered player perspectives are pairwise distinct after normalization | Report baseline |
| Consent leak count | Supplied forbidden raw identity terms found in the serialized safe result | 0 |
| Mission affordance compliance | Provider ranking contains offered `A#` references only; the first reference resolves to the selected canonical affordance, whose family, reason codes, objective set, and backend controls all match | 100% |
| Story-continuation selection | Across labelled and counterfactual fixtures, the first-ranked option is the strongest supported direct transformation; reunion is used when no coherent specific continuation exists | Report by prompt/model; compare with labels, not serialized position |
| Candidate-order invariance | Permuting `A#` serialization/reference assignment or changing non-semantic objective count does not systematically change the selected family | No position- or count-driven preference in the labelled matrix |
| Backend mission-copy compliance | Every selected `O#` resolves to the exact backend-compiled public objective description; the AI story bridge may omit rule restatement but cannot contradict targets/operators, add unoffered mechanics, assert unsupported facts, or violate privacy/safety | 100% |
| Fail-closed artifact count | Generated artifact fields returned after provider or validation failure | 0 |
| Media mapping validity | Selected media IDs whose represented `media.event_ids` are all contained in the selected episode | 100% |
| Deliverability and abstention correctness | Delivered/rejected/not-generated outcome matches optional labels; abstention has only `no_meaningful_episode` and no artifacts | 100% for labelled cases |
| Correction outcome | Attempted correction and successful corrected delivery are counted separately | Report baseline |
| Provider usage | Safe observability totals for request count, latency, and input/output tokens | Report baseline |
| Player-projection minimization | Player projection contains request-scoped refs and no raw player/event/backend-objective IDs, claims, verification controls, source references, or Studio trace; overlapping roster-participation and match-completion mechanics appear as one clear player step | 100% |
| Feedback outcome | Accepted and declined decisions, reasons, and source-quality flags grouped by prompt/model version | Report baseline |

`summarize_v2_evaluation` consumes typed `V2OfflineEvaluationCase` values. Expected labels and
delivery decisions are optional, and evaluation never changes telemetry, prompts, provider
configuration, or model selection. `summarize_v2_results` remains available as the compatibility
smoke summary for callers that only provide interpretation results.

The runnable V2.1 manifest evaluator defaults to deterministic mode and emits no prompts,
telemetry, credentials, or generated prose:

```powershell
python -m backend.evaluate_v2
```

Its labelled cases cover rescue → `role_reversal`, the same rescue with the revive removed → no
`role_reversal` plus `reunion`, repeated near misses → `redemption`, and ordinary sparse telemetry
→ `not_generated`. The report separates delivered, abstained, and rejected results and audits that
the affordance ranking is unique, contains exactly the offered IDs, puts the selected ID first, and
matches the selected family, reason codes, and backend objective set.

The deterministic Studio/test interpreter does not decide semantic abstention and currently
generates for the ordinary case, so the default baseline intentionally reports typed-abstention
accuracy `0`. That failed label is useful: only a labelled V2.11 live run can supply current evidence
that the model uses `no_meaningful_episode` appropriately.

Live evaluation is deliberately double opt-in. Repeat `--model` for a controlled model matrix and
use `--repeats` from 1 to 10:

```powershell
python -m backend.evaluate_v2 --provider gemini --allow-live-api --repeats 3 `
  --model gemini-3.6-flash

# Groq comparison
python -m backend.evaluate_v2 --provider groq --allow-live-api --repeats 3 `
  --model openai/gpt-oss-20b --model openai/gpt-oss-120b
```

Without `--allow-live-api`, Gemini, Groq, and OpenAI evaluation stops with a configuration error
before an API call. Deterministic evaluation rejects `--model` because it has no live model choice.
Gemini free-tier evaluation is restricted to the committed synthetic, non-sensitive fixtures; it
does not approve production player telemetry for hosted processing.

The compact decision schema must be tested against an evidence-based output ceiling. Worst-case
eligible rosters, authored sections, and compact references must still fail closed rather than
return a partial delivery. Backend-derived IDs, complete claims, media, mission controls, delivery,
and trace do not consume provider output tokens, but they remain part of final validation. The
prototype defaults to 4,000 output tokens on Gemini, 2,500 on Groq, and 4,000 on OpenAI. Gemini's
ceiling is configured with `GEMINI_V2_MAX_OUTPUT_TOKENS`; Groq's ceiling can be raised with
`GROQ_V2_MAX_OUTPUT_TOKENS` after provider capacity increases. The backend must be restarted after a
configuration change. Gemini requests use low reasoning, no explicit temperature, and a 60-second
per-attempt timeout with no hidden SDK transport retries. MemoryOS may make one explicit semantic
correction, and the same-origin proxy permits 130 seconds for that bounded path; a malformed or
terminally invalid result still fails closed after final Pydantic and deterministic validation.
The provider Story Brief omits null placeholders only—concrete false consent/capability values and
all actual evidence remain present.

## V2.11 backend-mission-copy verification gate

The automated checks below cover the current contract. A configured historical smoke used the
telemetry-only fixture, Groq `openai/gpt-oss-120b`, and
`memory-interpreter-v2.4-grounded-controls`; it ended as a validated pending delivery without a
correction. That result is retained only as V2.4 history. It is not evidence for the active
`memory-interpreter-v2.11-backend-mission-copy` prompt, its generate/abstain behavior, mission
selection behavior, or current model reliability. V2.11 requires a new labelled provider/model
sample.

Two controlled V2.10 smokes were recorded historically on 9 August 2026 with Gemini
`gemini-3.6-flash`. The
synthetic rescue selected `role_reversal` and completed in 4.74 seconds; the repeated-near-miss case
selected `redemption` and completed in 4.81 seconds. Both passed deterministic validation without
correction. These successful paths do not replace the labelled no-revive and ordinary-telemetry
cases or repeated runs required for a provider reliability claim, and they are not evidence for the
active V2.11 prompt.

Automated verification must cover:

- strict `ProviderInterpretationDecisionV2` parsing, generate/abstain payload invariants, and
  rejection of extra authoritative control fields;
- exact request-scoped `W#`/`A#`/`O#` projection, complete ranking of offered affordance references,
  first-ranked selection, deterministic canonical resolution, recognition of supplied
  fact/capability references, and fail-closed validation of unknown, ambiguous, or cross-affordance
  references and conservatively added literal candidate evidence;
- deterministic objective-description compilation for participant, completed-match, first-revive,
  and placement capabilities; public mission/objective shape stability; and rejection of story
  bridges that contradict targets/operators, add unoffered mechanics, assert unsupported facts, or
  violate privacy or safety, without requiring the bridge to restate every rule;
- dynamic coverage of the `reunion`, `role_reversal`, and `redemption` families, including exact
  reason-code and objective-set compilation;
- labelled rescue, repeated-near-miss, reunion-only, ordinary, and counterfactual cases that assess
  whether AI selects the strongest direct evidence-linked continuation without treating serialized
  `A#` order/reference number or `O#` count as preference; validator tests must separately prove
  that there is no deterministic family-priority rule;
- deterministic derivation of selected match/event IDs, complete claims, media, recipe, objective
  IDs, assignments, metrics/operators/targets, source references, ordered/exact-set perspectives,
  public delivery, and Studio trace;
- `event_scope` semantics, full-squad collective membership proof, provider perspective
  permissions, evidence-bound authoring constraints, categorical detail allowlists, cue-bound
  detail claims, and selected-affordance
  objective/reason-code enforcement;
- rejection of unknown, cross-window, wrong-player, and unsupported references, with scored
  candidate selection for non-unique literal matches still subject to complete validation;
- parity of the always-V2.1 `InterpretDeliveryResultV2`, generated OpenAPI types, minimal player
  projection, and Studio rendering;
- preservation of inactive-but-consented invitation eligibility and separation of
  `online`/`away` presentation from invitation state;
- proof that the player projection replaces raw player and backend-objective IDs with request-scoped
  refs, omits raw event IDs, claims, rules, source references, and Studio trace, and collapses
  overlapping participant-plus-match-completion mechanics into one player-facing step;
- Studio coverage for sanitized affordances, ranking/selection reasons, active versus
  invitation-ready counts, the separate backend participant/completion rules,
  validation/correction, and abstention;
- privacy and secret-leak checks, provider-visible correction sections and request-scoped references
  with no canonical candidate ID or rejected prose, one bounded correction, and zero generated artifacts
  after any terminal failure, including absence of the raw compact provider response from Studio;
- explicit frontend tests for the scripted post-accept sequence, without claiming new-match
  ingestion or actual objective verification; and
- continued green v1.0/v1.1 compatibility, backend, frontend, evaluator, and production-build tests.

For subsequent releases, repeat the telemetry-only fixture across the configured provider/model
matrix and record provider/model/prompt version, compact-decision parse/outcome, correction use,
reference-resolution result, final validator result, latency, and token usage. A release sample must
enrich into valid deliveries with no deterministic narrative fallback before comparative reliability
or performance claims are made.

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
python -m backend.evaluate --provider gemini
python -m backend.evaluate --provider groq
python -m backend.evaluate --provider openai
```

The cost field uses configurable `OPENAI_INPUT_COST_PER_MILLION` and
`OPENAI_OUTPUT_COST_PER_MILLION` assumptions for every provider, so Gemini and Groq cost figures are
comparison assumptions rather than provider pricing unless those values are set deliberately.

## Prompt and model evaluation workflow

For any prompt or model change:

1. Run deterministic CI gates to protect schemas, normalization, consent filtering, window
   construction, mission controls, and validators.
2. Run the complete labelled V2.1 manifest in explicit Gemini mode with `--allow-live-api`; use Groq
   and OpenAI as documented comparisons.
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
python -m backend.evaluate_v2
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

The rendered-flow tests cover the unrevealed state, evidence-first reveal, clearly labelled
Studio-only saved samples, fail-closed live-player errors, asset selection, the minimal player
projection, inactive invitees, and the absence of direct browser-to-localhost calls. Real
persistence, authentication, notifications/invitations, new-match ingestion, and post-match
objective verification remain outside these gates because they are deferred production work.
