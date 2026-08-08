# Shank branch integration review

## Decision

The Shank player experience and the teammate's end-to-end Studio are now integrated around the
AI-first v2 backend. FastAPI/OpenAPI remains authoritative. The compact player route consumes only
a validated live delivery, while Studio exposes a separate sanitized responsibility trace. The
older Phase 1/2 Memory Pack path remains runnable only as deprecated compatibility infrastructure.

## What the teammate branch added

- A polished, compact mobile player journey from hidden memory to evidence, personal perspective,
  and a Next Chapter preview
- A React frontend with same-origin server proxies
- A fixed-fixture saved result used only as a clearly labelled Studio/test sample; submitted
  telemetry is validated but never supplies identities or narrative to the sample, and the sample
  never substitutes for live player output
- Runtime response guards before player-facing content is revealed
- Optimized custom WebP artwork and rendered HTML regression tests
- Useful prototype hardening ideas around connected events, perspective distinctness, quest safety,
  output truncation, and provider configuration

## Compatibility choices

| Area | Resolution | Why |
|---|---|---|
| Player frontend | Retained | It gives the project a coherent, testable demo now |
| `/v1/memories/*` | Retained as deprecated compatibility adapters | Existing tests and internal workflows remain runnable during migration |
| Historical ranking and review gates | Kept from Phase 2 backend | These are the canonical v1.1 trust semantics |
| Python agents and prompts | Phase 2 base plus selected hardening | Avoids raw-pack prompting and duplicated behavior |
| Frontend runtime guards | Retained | Useful defense in depth, while backend stays authoritative |
| Frontend TypeScript contracts | Generated from OpenAPI | Contract drift is checked in tests |
| Deterministic narrative | Tests and labelled Studio sample only | It never substitutes for a failed live player delivery |
| `/v2/memories/interpret-delivery` | Canonical player generation route | It starts from telemetry rather than a prepared memory |
| V2 versioning | `RawTelemetryBatchV2` accepts 2.0/2.1; `InterpretDeliveryResultV2` is always 2.1 | Existing raw callers migrate without weakening the output contract |

The teammate backend implementation was not merged wholesale because it overlapped the canonical
pipeline and relaxed important boundaries in places, including sending broader pack data toward
prompts and deriving facts that were not always present in a source event. Those conflicts were
resolved in favor of the sanitized evidence ledger and deterministic factual control plane.

## Hardening included during integration

- Connected-event bonuses now require compatible participants, location, ordering, and a bounded
  time window instead of rewarding merely coexisting event types.
- At least two opted-in squad members are required for a shared memory.
- Player captions remain attributed context rather than verified telemetry.
- Generic actor perspectives are distinct and player-specific.
- The backend dynamically compiles exactly three mission affordance families—`reunion`,
  `role_reversal`, and `redemption`—and owns their objective sets, assignments,
  metrics/operators/targets, and source references.
- `StoryBriefV2` exposes no more than four neutral windows. AI returns a typed generate-or-abstain
  decision, ranks/selects one offered affordance, and may abstain with `no_meaningful_episode`.
- Invalid provider configuration returns a structured safe error.
- The Studio/test sample matches canonical metadata and is unmistakably separate from live player
  output.
- Frontend dependencies were upgraded and the remaining transitive `undici` version was pinned;
  `npm audit --audit-level=high` is a merge gate.

## Current phase

The AI-first V2.1 prototype is implemented. It accepts V2.0/V2.1 raw synthetic Free Fire telemetry,
constructs at most four consent-safe neutral windows and dynamic mission affordances, and asks one
live model for `CompactInterpretationDecisionV2`. AI may generate by ranking/selecting one offered
affordance or abstain with `no_meaningful_episode`. The backend validates and enriches a generated
proposal into one player-facing **Next Chapter**. History is a privacy-safe read-only timeline.
Production authentication, durable persistence/suppression, real notifications and invitations,
Garena telemetry integration, and post-match objective verification remain deferred.
The active prompt is `memory-interpreter-v2.6-mission-affordances`; the historical V2.4/120B smoke
does not validate this prompt.

## Next implementation order

1. Connect an authenticated Garena telemetry adapter while preserving the v2 raw-input boundary.
2. Approve consent, retention, deletion, regional privacy, and source-dispute operations policy.
3. Replace process-local delivery decisions with authenticated, idempotent, durable storage.
4. Run labelled offline and human evaluation for episode quality, grounding, perspective utility,
   mission appeal, abstention, latency, and consent comprehension before changing prompts/models.
5. Integrate real notifications and invitations, authenticated new-match telemetry ingestion, and
   post-match objective verification.

Production work still requires authentication, player ownership checks, rate limits, retention and
regional privacy rules, real Garena telemetry contracts, provider observability, and adversarial
evaluation.

## Current frontend implementation

The canonical player journey lives at `/`. It uses same-origin server routes to submit raw v2
telemetry and returns only a live, fully validated minimal projection with request-scoped
`recipient_ref` and `objective_ref` values, the current player's perspective, and one selected
**Next Chapter**. Raw player/event/backend objective IDs, claims, verification rules, source
references, and Studio trace are stripped before browser delivery. Inactive but consented invitees
remain eligible; `online` and `away` are presentation only.

`/studio` owns the sanitized judge trace: dynamic affordances, ranked/selected family and reason
codes, backend controls, validation/correction, active versus invitation-ready counts, and
abstention. `/mission` owns the scripted post-accept sequence—invitations, squad joins, game start,
game end, then mission complete—and does not ingest a new match or verify real objectives.
`/history` is read-only. Unavailable or invalid live output is withheld. Deterministic output is
clearly labelled and limited to Studio/tests.
