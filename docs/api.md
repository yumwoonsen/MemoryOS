# API reference

FastAPI publishes the authoritative schemas at `/openapi.json` and interactive documentation at
`/docs`. The examples below are intentionally shortened to show the Phase 1/2 flow; use OpenAPI for
complete field definitions and generated frontend types.

## Start the service

```powershell
$env:MEMORYOS_PROVIDER = "deterministic"
uvicorn backend.main:app --reload
```

Default base URL: `http://127.0.0.1:8000`

## `GET /health`

Confirms the service is running and reports the active provider and model.

```json
{
  "status": "ok",
  "phase": "1",
  "provider": "deterministic",
  "model": "rules-v1"
}
```

The health payload intentionally remains compatible with the Phase 1 client while the FastAPI
application version advances to `0.2.0`.

## `POST /v1/memories/discover-history`

Ranks historical packs without an OpenAI call. The request accepts 1-50 v1.0 or v1.1 packs and
`limit` defaults to 3 with a maximum of 10. Every pack in one request must use:

- the same `squad_id` and target `player_profile.player_id`;
- exactly the same set of squad-member IDs;
- one consistent, current `opted_in` value for each member; and
- a unique `pack_id`.

Consent must be explicit for every member, including when a legacy v1.0 pack is sent through a new
v1.1 endpoint. A history request is rejected instead of inferring permission from a missing value.

Request shape (nested objects are abbreviated and this snippet is not a complete runnable pack):

```json
{
  "schema_version": "1.1",
  "memory_packs": [
    {
      "schema_version": "1.1",
      "pack_id": "pack-chaos-001",
      "player_profile": {"player_id": "lee"},
      "squad": {},
      "match": {},
      "match_events": [],
      "human_review": {
        "source_status": "verified",
        "meaning_status": "confirmed"
      }
    }
  ],
  "limit": 3
}
```

For a runnable local request, wrap an existing complete fixture:

```powershell
$pack = Get-Content -Raw backend/data/funny_memory.json | ConvertFrom-Json
$body = @{schema_version = "1.1"; memory_packs = @($pack); limit = 3} | ConvertTo-Json -Depth 20
Invoke-RestMethod `
  -Uri http://127.0.0.1:8000/v1/memories/discover-history `
  -Method Post `
  -ContentType application/json `
  -Body $body
```

Response shape (trimmed):

```json
{
  "schema_version": "1.1",
  "candidates": [
    {
      "rank": 1,
      "pack_id": "pack-chaos-001",
      "match_id": "match-001",
      "memory_type": "chaos",
      "title": "Clock Tower escape",
      "summary": "A verified preview grounded in the submitted events.",
      "score": 0.82,
      "ranking_score": 0.82,
      "score_breakdown": {
        "evidence_strength": 0.315,
        "human_signals": 0.24,
        "squad_specificity": 0.16,
        "resurfacing_relevance": 0.105,
        "diversity_penalty": 0.0,
        "total": 0.82
      },
      "reasons": ["connected rescue-and-escape evidence"],
      "source_status": "verified",
      "meaning_status": "confirmed",
      "redactions": []
    }
  ],
  "filters": {
    "received": 1,
    "duplicates_removed": 0,
    "no_grounded_events": 0,
    "below_threshold": 0,
    "disputed": 0,
    "dismissed": 0,
    "target_opted_out": 0,
    "insufficient_opted_in": 0,
    "eligible_not_selected": 0
  },
  "metadata": {
    "provider": "deterministic"
  }
}
```

`score`, `score_breakdown.total`, and the sum of the four weighted components are the same base
eligibility score. The `0.45` eligibility threshold is applied to that value. A repeated memory
type may receive `diversity_penalty: 0.08` during iterative top-candidate selection; only
`ranking_score = max(score - diversity_penalty, 0)` includes that adjustment. The penalty never
changes eligibility. Frontends should display the provided values and reasons rather than
recreating this stateful selection logic. Send an offset with `played_at` when possible; a legacy
timestamp without one is interpreted as UTC for deterministic tie-breaking.

## `POST /v1/memories/generate`

Runs the selected pack through normalization, evidence compilation, the eligibility gate, review
gates, semantic generation, and deterministic validation. It recomputes all trusted state and does
not accept a browser-provided discovery score.

The request wraps one complete v1.0 or v1.1 Memory Pack so the endpoint contract itself stays at
v1.1. Legacy inner packs are normalized before evaluation:

```json
{
  "schema_version": "1.1",
  "memory_pack": {
    "schema_version": "1.1",
    "pack_id": "pack-chaos-001"
  }
}
```

The inner object above is shortened and is not a runnable pack; all required Memory Pack fields
still apply. A generated response has one of four statuses:

| Status | Meaning | AI called? |
|---|---|---:|
| `needs_source_verification` | The candidate is promising but its events are unreviewed | No |
| `needs_meaning_confirmation` | Events are verified, but the player has not confirmed meaning | No |
| `ready` | Verified, confirmed, generated, and deterministically valid | Yes, in OpenAI mode |
| `rejected` | Filtered, ineligible, or generated output failed validation | No before a gate; in OpenAI mode, possibly yes if generated output was later rejected |

The `ready` body contains the memory, opted-in player perspectives, next-chapter quest, validation
report, and provider/prompt/pipeline version metadata. Because the route excludes `null` response
fields, `memory` and `next_chapter` are absent when a gate stops generation or validation rejects
the artifacts; `player_perspectives` remains an empty array. `discovery`, review states,
`validation`, and metadata remain available to explain the result.

The top-level `status` is the readiness contract. Only `status: "ready"` permits a client to present
generated artifacts as ready. `validation.passed` has a narrower meaning: it reports whether the
deterministic checks that were applicable at that stopping point completed without an error. It is
therefore also `true` for a safe eligibility abstention and for a candidate waiting at either human
review gate. Frontends must not use `validation.passed` as a replacement for `status`.

This phase stores no review state. To continue an unreviewed candidate, the client keeps the
complete selected Memory Pack, records the player's decision in `human_review`, and resubmits that
pack to `/v1/memories/generate`. The backend recomputes eligibility and review state; a candidate
ID, rank, or client-provided score is not sufficient. A later frontend data layer may persist the
decision, but it must preserve these v1.1 meanings.

PowerShell example using a complete fixture:

```powershell
$pack = Get-Content -Raw backend/data/funny_memory.json | ConvertFrom-Json
$body = @{schema_version = "1.1"; memory_pack = $pack} | ConvertTo-Json -Depth 20
Invoke-RestMethod `
  -Uri http://127.0.0.1:8000/v1/memories/generate `
  -Method Post `
  -ContentType application/json `
  -Body $body
```

## `POST /v1/memories/generate-stream`

Returns newline-delimited JSON (`application/x-ndjson`) snapshots from the same canonical
generation pipeline. It emits an initial `working` event, completes the canonical call, and then
emits completed-stage previews followed by the typed result. It is not token streaming or a
real-time trace of model-stage completion. Review-gated or rejected requests instead emit a
`stopped` snapshot and the final result.

Events use `type: "stage"`, `type: "result"`, or `type: "error"`. A provider error contains the same
stable stage, code, and retryability fields as a direct failure. Clients must inspect NDJSON error
events: once streaming has begun the HTTP status remains `200` and cannot be changed to `503`.
OpenAPI describes one NDJSON line as a discriminated union of `GenerateStreamStageEvent`,
`GenerateStreamResultEvent`, and `GenerateStreamErrorEvent` under the
`application/x-ndjson` media type.

Stream cancellation is best-effort in this prototype. Generation currently runs in a synchronous
worker thread; if a browser disconnects after the first event, cancellation of the response does
not reliably stop the in-flight provider request or deterministic pipeline. That work may continue
until the current call completes or reaches its timeout. Production needs disconnect propagation,
idempotency, and request-level cancellation before treating this route as resource-cancellable.

## Deprecated `POST /v1/memories/discover`

The original v1.0 route accepts one legacy Memory Pack and remains available during the migration
window. It is deprecated; new clients should use historical discovery followed by generation. The
compatibility route preserves legacy behavior: an eligible `confirmed: false` pack can produce
draft artifacts with `needs_human_confirmation`. It therefore does not provide the stricter
pre-generation source/meaning gate of `/v1/memories/generate`.

Legacy review normalization:

| v1.0 value | v1.1 `source_status` | v1.1 `meaning_status` |
|---|---|---|
| `confirmed: true` | `verified` | `confirmed` |
| `confirmed: false` | `unreviewed` | `unreviewed` |

For `/generate`, `metadata.compatibility_conversion` reports when its selected inner pack was
normalized from v1.0, while `pipeline_version` still identifies the Phase 2 generation path. A
history response reports only the aggregate `metadata.normalized_legacy_packs` count; individual
candidate provenance is not added to the response. A client that needs per-pack migration UI must
preserve the submitted pack's `schema_version` itself. Native v1.1 packs must include
`human_review`; all packs sent to the new endpoints must include an explicit `opted_in` value for
every squad member. Omitted consent is not treated as permission. Packs are also rejected if an
opaque pack, squad, match, or event identifier embeds an opted-out player's ID or display name,
because those identifiers are preserved for traceability.

## Errors

- `422` - invalid fields, out-of-range history size or limit, cross-reference failures, duplicate
  pack IDs, or mixed squad IDs, targets, rosters, or consent snapshots.
- `503` - a live AI stage failed. The direct JSON body identifies the stage, a stable error code,
  whether retrying may help, and a safe message:

```json
{
  "stage": "memory_discovery",
  "code": "provider_timeout",
  "retryable": true,
  "message": "The live AI provider could not complete this generation stage."
}
```

The service does not silently switch a failed OpenAI request to deterministic content.

Final validation checks exact schemas, IDs, evidence types, perspective ownership, and quest-rule
shapes, plus conservative lexical checks for selected unsupported names, locations, numbers,
actions, relationships, emotions, and motives. These heuristics reduce obvious hallucinations but
do not prove every implication in arbitrary prose. A production service still needs broader
semantic evaluation, moderation, adversarial testing, and human review.

Core factual clauses use a stricter closed renderer. A live model must return the server-rendered
memory summary and evidence exactly, return each player-specific perspective message and its
evidence references exactly, and use the exact objective description associated with each validated
quest rule. The pipeline also overwrites model-authored confidence and confirmation values with the
deterministic score and normalized review state. Memory title and type, plus quest title, mission,
and recipe, remain bounded model framing and still pass the privacy, evidence, action, and lexical
checks above.

## Provider configuration

The default needs no credentials:

```dotenv
MEMORYOS_PROVIDER=deterministic
```

To opt into live generation, copy `.env.example` to `.env` and set:

```dotenv
MEMORYOS_PROVIDER=openai
OPENAI_API_KEY=your_server_side_key
OPENAI_MODEL=gpt-5.6-luna
```

Start each mode explicitly in PowerShell:

```powershell
# Free, repeatable local mode
$env:MEMORYOS_PROVIDER = "deterministic"
uvicorn backend.main:app --reload

# Opt-in live mode; reads OPENAI_API_KEY from .env
$env:MEMORYOS_PROVIDER = "openai"
uvicorn backend.main:app --reload
```

Keep the key server-side. The live provider uses structured typed responses, but deterministic code
still owns evidence, consent, eligibility, review state, and final validation.

Each model request uses low reasoning effort, a 30-second timeout, at most two SDK retries, and a
2,000-token output ceiling. Responses use `store=False`. See the official
[gpt-5.6-luna model reference](https://developers.openai.com/api/docs/models/gpt-5.6-luna) for the
configured model's current capabilities and pricing.

Local browser origins on ports 3000 and 5173 are allowed by default. Override them with a
comma-separated value when a frontend runs elsewhere:

```dotenv
MEMORYOS_CORS_ORIGINS=http://127.0.0.1:3000,http://localhost:3000,http://127.0.0.1:5173,http://localhost:5173
```

A production deployment still requires an explicit origin, authentication, ownership, and
rate-limit policy.

## Frontend integration

Use `/openapi.json` to derive frontend request and response types. During integration, contract tests
should compare the generated client against the running backend. Do not copy Pydantic definitions by
hand or retain a separate Worker implementation of ranking and generation; that creates conflicting
meaning for schema version, consent, and `ready`.

The current player prototype intentionally remains on deprecated `/v1/memories/discover` while the
Phase 2 review screens are built. Its `/api/discover` route is a server-side compatibility proxy,
not a second ranking engine. New historical UI work should call `/discover-history`, retain the
selected complete Memory Pack, collect both review decisions, and then call `/generate`.

The implemented Phase 2B client exposes that handoff as same-origin `/api/history` and
`/api/generate` server routes. It sends the entire selected v1.1 pack, never a candidate ID or
score, and treats only `status: "ready"` as permission to render generated artifacts.

`POST /v1/memories/prepare-delivery` is the consumer delivery route. It ranks a submitted trusted
history, selects the highest source-verified candidate, and returns `pending_player_decision` with
validated artifacts while `meaning_status` remains `unreviewed`. `POST
/v1/memories/record-delivery-decision` accepts `accepted` or `declined`; a decline must be either
`not_relevant` or `details_wrong`. Decisions are process-local prototype data only.

## Data boundary

Included JSON is synthetic evaluation data. Do not deploy this prototype with real player data
without authentication, ownership checks, rate limiting, regional privacy rules, retention policy,
and a security review.
