# Shank branch integration review

## Decision

The Shank player experience and the teammate's end-to-end Studio are now integrated around the
AI-first v2 backend. FastAPI/OpenAPI remains authoritative. The compact player route consumes only
a validated live delivery, while Studio exposes a separate sanitized responsibility trace. The
older Phase 1/2 Memory Pack path remains runnable only as deprecated compatibility infrastructure.

## What the teammate branch added

- A polished, compact mobile player journey from hidden memory to evidence, personal perspective,
  and a Next Chapter preview
- A Vite/Vinext React frontend with a server-side `/api/discover` proxy
- An exact-fixture hosted fallback that fails closed for altered or unknown packs
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
- Quest validation requires exactly one mandatory squad-reunion objective and screens unsafe
  instructions without rejecting safe prevention language.
- Invalid provider configuration returns a structured safe error.
- The frontend fallback now matches canonical backend metadata and deterministic fixture output.
- Frontend dependencies were upgraded and the remaining transitive `undici` version was pinned;
  `npm audit --audit-level=high` is a merge gate.

## Current phase

The AI-first v2 prototype is implemented. It accepts raw synthetic Free Fire telemetry, constructs
consent-safe event windows and feasible mission candidates, asks one live model for a complete
proposal, validates the proposal, and exposes the accept/decline and reunion-continuation flow.
History is a privacy-safe read-only timeline. Production authentication, durable suppression,
retention, real notification delivery, and Garena telemetry integration remain deferred.

## Next implementation order

1. Connect an authenticated Garena telemetry adapter while preserving the v2 raw-input boundary.
2. Approve consent, retention, deletion, regional privacy, and source-dispute operations policy.
3. Replace process-local delivery decisions with authenticated, idempotent, durable storage.
4. Run labelled offline and human evaluation for episode quality, grounding, perspective utility,
   mission appeal, abstention, latency, and consent comprehension before changing prompts/models.
5. Integrate real notification, invitation, and deterministic new-match result verification.

Production work still requires authentication, player ownership checks, rate limits, retention and
regional privacy rules, real Garena telemetry contracts, provider observability, and adversarial
evaluation.

## Current frontend implementation

The canonical player journey lives at `/`. It uses same-origin server routes to submit raw v2
telemetry and returns only a live, fully validated player projection; Studio claims and validation
internals are stripped before browser delivery. `/mission` owns the accepted invitation and
continuation simulation, `/history` is read-only, and `/studio` owns the sanitized judge trace.
Unavailable or invalid live output is withheld. Deterministic output is clearly labelled and
limited to Studio/tests.
