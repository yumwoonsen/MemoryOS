# Shank branch integration review

## Decision

`Shank-Branch` is compatible with the Phase 2 backend when integrated as a Phase 1 compatibility
client, not as a replacement backend. The merge keeps its player experience and selectively ports
its strongest backend hardening ideas. Where both branches defined the same pipeline, the Phase 2
Python/OpenAPI implementation remains authoritative.

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
| `/v1/memories/discover` | Retained as deprecated adapter | The current UI remains runnable during migration |
| Historical ranking and review gates | Kept from Phase 2 backend | These are the canonical v1.1 trust semantics |
| Python agents and prompts | Phase 2 base plus selected hardening | Avoids raw-pack prompting and duplicated behavior |
| Frontend runtime guards | Retained | Useful defense in depth, while backend stays authoritative |
| Frontend TypeScript contracts | Temporary | They describe v1.0 and must be generated from OpenAPI next |
| Worker fallback | Exact demo only | It does not rank or generate arbitrary player content |

The teammate backend implementation was not merged wholesale because it overlapped the canonical
pipeline and relaxed important boundaries in places, including sending broader pack data toward
prompts and deriving facts that were not always present in a source event. Those conflicts were
resolved in favor of the sanitized evidence ledger and closed factual renderer.

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

Phase 1 is complete. The Phase 2A historical-discovery backend is complete for prototype use. Phase
2B is in progress: a high-quality single-memory player screen exists, but historical selection and
the two human review decisions are not yet represented in the UI. Phase 3 reunion execution and
new-match verification have not started.

## Next implementation order

1. Generate TypeScript client types from `/openapi.json` and add contract drift checks.
2. Build the historical top-three candidate screen with ranking reasons and redaction notices.
3. Add separate source verification and meaning confirmation/dismissal actions.
4. Submit the complete selected pack to `/v1/memories/generate`; never trust a client score or ID as
   authorization.
5. Add prototype persistence for review decisions, with the backend state vocabulary unchanged.
6. Run qualitative human evaluation on candidate precision, perspective usefulness, quest appeal,
   and consent comprehension before tuning ranking weights or prompts.
7. Begin Phase 3 only after the review loop is usable: invitation simulation, new-match objective
   verification, and a truthful continuation chapter.

Production work still requires authentication, player ownership checks, rate limits, retention and
regional privacy rules, real Garena telemetry contracts, provider observability, and adversarial
evaluation.

## Phase 2B frontend implementation

The Phase 2B player journey lives at `/history`; the retained `/` screen remains the Phase 1
compatibility demo. It uses FastAPI-derived types and server-side proxy routes, holds the complete
selected pack locally, and makes source verification and meaning confirmation distinct screens.
Only a structurally valid v1.1 result whose top-level status is `ready` may render a memory,
perspective, or Next Chapter. Historical hosted fallbacks were deliberately not added, so the
walkthrough truthfully requires the deterministic backend.
