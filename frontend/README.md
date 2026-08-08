# MemoryOS player prototype

This frontend is the compact, mobile-first player view for the latest MemoryOS prototype. It keeps
one focused Free Fire Battle Royale example so the end-to-end idea is easy to understand without
turning the player screen into an internal dashboard.

The experience is split into four focused routes:

- `/` — the current memory, grounded explanation, player perspective, and Accept/Decline choice;
- `/mission` — the accepted squad invitation, synthetic rematch, verification, and continuation;
- `/history` — a read-only, privacy-safe timeline of the current session and eligible past matches;
- `/studio` — developer-facing pipeline observability.

The player story never exposes internal validation scores, rule IDs, prompts, or credentials. It
does show a compact provenance label so a live AI result, explicitly offline deterministic run,
and saved sample replay cannot be confused. A navigation link opens the separate Developer Studio
without mixing its controls into the story itself. The
checks still run behind the interface: results are bound to the consent-safe telemetry view,
evidence must reference real match events, and every opted-in player must receive exactly one
grounded perspective. Review, rejected, malformed, or unavailable results do not reveal a story.

The custom Bermuda map and clock-tower town artwork live in `public/art` as optimized WebPs. The
dedicated MemoryOS Studio remains intentionally separate from this player prototype.

## V2 implementation status

The canonical `/` route uses the AI-first v2 adapter and proxies:

- `POST /v2/memories/interpret-delivery` for raw telemetry to one validated Memory Proposal; and
- `POST /v2/deliveries/{delivery_id}/decision` for acceptance or one structured decline reason.

This preserves the compact player sequence: one memory, its grounded explanation,
the current player's perspective, a clear reunion mission, and one decision. `/history` remains a
read-only timeline rather than a second delivery or feedback surface.

## Developer Studio

Open `/studio` for the developer-facing observability workspace. It accepts synthetic raw telemetry
and shows how the pipeline moves from normalized match evidence into a shared memory,
personal perspectives, a continuation quest, and deterministic validation.

The Studio deliberately separates three runtime states:

- **Live AI** — the configured Groq or OpenAI provider generated one complete typed proposal.
- **Deterministic run** — the rules provider completed the pipeline without model calls.
- **Sample replay** — the hosted frontend replayed the bundled canonical result because no backend
  is configured or reachable.

Pipeline events are labelled as completed snapshots rather than a live token trace. When the
backend supplies them, the Studio displays safe aggregate and per-stage request counts, token
counts, latency, and configured retry limits. For v2, the safe trace may additionally show
synthetic raw telemetry, normalization and eligibility outcomes, offered window IDs, validated
evidence links, provider/model/prompt version, validator issue codes, final status, and structured
feedback. It never displays raw prompts, chain-of-thought, API keys, server environment values,
opted-out identities, raw provider exceptions, or rejected and unvalidated proposal prose.

## Run locally

From this directory:

```powershell
npm install
npm run dev
```

Open the local URL printed by the development server. The canonical `/` player route calls the
same-origin `/api/delivery/prepare` and `/api/delivery/decision` proxies and requires the local
MemoryOS backend. It fails closed when the backend is unavailable or returns an invalid delivery.
`/api/discover` and its exact-fixture sample fallback remain compatibility infrastructure and are
not used by the canonical player flow.

The Studio uses `/api/studio/health`, `/api/studio/interpret`, and
`/api/studio/delivery-trace`. During local development, those routes connect to
`http://127.0.0.1:8000`. In a hosted environment, set `MEMORYOS_API_URL` on
the server to enable live runs; otherwise the Studio remains usable as an explicitly labelled
sample replay. If the public backend is protected with the optional proxy boundary, set
`MEMORYOS_PROXY_TOKEN` only in the frontend server environment. It is attached to server-to-server
requests and is never serialized into the browser bundle.

## Current memory and squad history

`/` is the local AI Memory Inbox. It submits the server-held synthetic raw telemetry fixture through
the `/api/delivery/prepare` proxy, receives one evidence-validated live-AI delivery with explicit
provenance, then records only an accept decision or one of two decline reasons through
`/api/delivery/decision`.
The v2 proxy preserves those semantics while binding the decision to the opaque delivery ID.
`/history` is a separate read-only view built from verified, confirmed, deduplicated safe-list data.
It performs no delivery preparation and records no player decision. Player feedback does not
rewrite telemetry.

An accepted v2 delivery starts the validated mission and hands off to the invitation flow. A
decline requires exactly `not_relevant` or `details_wrong` and suppresses that exact prototype
delivery. `details_wrong` is also an operations source-quality signal; it is not a
client-side correction or an automatic prompt/model update. The current process- and session-local
stores remain prototype-only until authentication, retention, deletion, consent, and privacy
decisions approve durable storage.

`lib/api.generated.ts` is generated from the FastAPI OpenAPI snapshot. Run
`npm run generate:api-types` after a backend schema change; pytest verifies that the snapshot has
not drifted. The legacy exact-fixture fallback remains limited to `/api/discover` and is not used
by the canonical player routes.

## Phase 3 reunion continuation

After an accepted `/` delivery, layout-scoped in-memory state hands the validated delivery to
`/mission`. The player sees a consent-safe mission start, invites only the privacy-filtered squad
perspectives, and can run a clearly labelled reunion simulation. A pure
deterministic evaluator checks the synthetic new-match metrics against the quest's existing
verification rules. “Story Continues,” the three-step timeline, and optional chapter feedback stay
locked until every required objective passes.

This Phase 3 slice remains intentionally ephemeral. The accepted handoff is not placed in a URL,
browser storage, or durable store, so a refresh or direct `/mission` visit correctly shows no active
mission. It sends no real invitation, reads no live Garena match result, and does not persist
chapter feedback while authentication, retention, consent, and privacy policy are unresolved.

Any moment clip, thumbnail, or keyframe shown by this prototype is a curated synthetic asset with a
deterministic event mapping. MemoryOS does not currently inspect or understand gameplay video.

To run the backend for the offline Studio demonstration, start it from the repository root in
deterministic mode:

```powershell
$env:MEMORYOS_PROVIDER = "deterministic"
python -m uvicorn backend.main:app --reload
```

The canonical player route intentionally refuses deterministic narrative. To test the player flow,
start the backend with `MEMORYOS_PROVIDER=groq` and a server-side `GROQ_API_KEY`, or use the OpenAI
provider configuration described in the root README.

## Quality checks

```powershell
npm run typecheck
npm run lint
npm test
npm audit --audit-level=high
```

The challenge, invitation, rematch, and continuation are simulations only. They do not send a real
invitation or persist player actions.
