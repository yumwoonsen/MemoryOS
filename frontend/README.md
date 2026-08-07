# MemoryOS player prototype

This frontend is the compact, mobile-first player view for the latest MemoryOS prototype. It keeps
one focused Free Fire Battle Royale example so the end-to-end idea is easy to understand without
turning the player screen into an internal dashboard.

The experience moves through four clear states:

1. an unrevealed squad memory;
2. a short loading transition;
3. the shared gist, chronological evidence, and the current player's perspective; and
4. a grounded “Next Chapter” challenge with a safe preview dialog.

The player story never exposes internal validation scores, rule IDs, prompts, or credentials. It
does show a compact provenance label so a live AI result, deterministic fallback, and saved sample
replay cannot be confused. A navigation
link opens the separate Developer Studio without mixing its controls into the story itself. The
checks still run behind the interface: results are bound to the submitted Memory Pack,
evidence must reference real match events, and every opted-in player must receive exactly one
grounded perspective. Review, rejected, malformed, or unavailable results do not reveal a story.

The custom Bermuda map and clock-tower town artwork live in `public/art` as optimized WebPs. The
dedicated MemoryOS Studio remains intentionally separate from this player prototype.

## Developer Studio

Open `/studio` for the developer-facing observability workspace. It accepts an editable synthetic
Memory Pack and shows how the pipeline moves from verified match evidence into a shared memory,
personal perspectives, a continuation quest, and deterministic validation.

The Studio deliberately separates three generation states:

- **Live AI** — Groq GPT-OSS generated the semantic stages through the configured backend.
- **Deterministic run** — the rules provider completed the pipeline without model calls.
- **Sample replay** — the hosted frontend replayed the bundled canonical result because no backend
  is configured or reachable.

Pipeline events are labelled as completed snapshots rather than a live token trace. When the
backend supplies them, the Studio displays safe aggregate and per-stage request counts, token
counts, latency, and configured retry limits. It never displays prompts, model inputs, API keys,
server environment values, unrestricted player data, or raw provider exceptions.

## Run locally

From this directory:

```powershell
npm install
npm run dev
```

Open the local URL printed by the development server. The frontend calls `/api/discover`, which
uses the local MemoryOS backend when it is available. If the backend is offline, the exact included
Battle Royale pack can use its canonical sample result; altered or unknown packs fail closed.

The Studio uses `/api/studio/health` and `/api/studio/generate-stream`. During local development,
those routes connect to `http://127.0.0.1:8000`. In a hosted environment, set `MEMORYOS_API_URL` on
the server to enable live runs; otherwise the Studio remains usable as an explicitly labelled
sample replay. If the public backend is protected with the optional proxy boundary, set
`MEMORYOS_PROXY_TOKEN` only in the frontend server environment. It is attached to server-to-server
requests and is never serialized into the browser bundle.

This screen currently targets the deprecated v1.0 `/v1/memories/discover` compatibility route. It
is safe to keep during the migration window, but it is not the Phase 2 historical review flow.
That flow is available at `/history`; FastAPI OpenAPI is authoritative.

## Phase 2B historical review

`/history` is the local AI Memory Inbox. It submits the synthetic collection through the server-side
`/api/delivery/prepare` proxy, receives one source-verified AI-prepared memory, then records only
an accept decision or one of two decline reasons through `/api/delivery/decision`. Player feedback
does not rewrite telemetry.

`lib/api.generated.ts` is generated from the FastAPI OpenAPI snapshot. Run
`npm run generate:api-types` after a backend schema change; pytest verifies that the snapshot has
not drifted. The legacy exact-fixture fallback remains limited to `/api/discover` and is not used
by `/history`.

To run the optional backend, start it from the repository root:

```powershell
$env:MEMORYOS_PROVIDER = "deterministic"
python -m uvicorn backend.main:app --reload
```

## Quality checks

```powershell
npm run typecheck
npm run lint
npm test
npm audit --audit-level=high
```

The challenge dialog is a simulation only. It does not send a real invitation or persist player
actions.
