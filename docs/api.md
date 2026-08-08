# API reference and v2 contract

FastAPI publishes the implemented schemas at `/openapi.json` and interactive documentation at
`/docs`. The v2 schemas are included in the checked-in generated OpenAPI document. The v1.0 and
v1.1 sections describe the runnable compatibility API.

## V2 implementation status

The implemented consumer API is additive:

- `POST /v2/memories/interpret-delivery` ingests raw telemetry and returns either one fully
  validated V2.1 delivery, a typed V2.1 abstention, or a fail-closed result with no generated artifacts.
- `POST /v2/deliveries/{delivery_id}/decision` records one prototype accept/decline decision and
  suppresses the exact delivery when declined.
- `GET /v2/deliveries/{delivery_id}/trace` returns the sanitized Studio trace for a process-local
  delivery.

Their Pydantic models, normalizer, validators, OpenAPI snapshot, and integration tests are
implemented. They remain prototype routes without player authentication or durable storage.
Existing `/v1/memories/discover-history`, `/generate`, `/prepare-delivery`, and
`/record-delivery-decision` remain compatibility/internal behavior during migration.

## `POST /v2/memories/interpret-delivery`

The request contains raw telemetry and limited context, never a pre-authored memory. This shortened
example illustrates the boundary; use OpenAPI for the complete generated schema:

`RawTelemetryBatchV2.schema_version` accepts both `"2.0"` and `"2.1"`. Successful typed responses,
including abstention and rejection, always use `InterpretDeliveryResultV2.schema_version: "2.1"`.
The request below intentionally uses `2.0` to show that compatibility boundary.

```json
{
  "schema_version": "2.0",
  "request_id": "request-17",
  "target_player_id": "player-lee",
  "squad": {
    "squad_id": "squad-17",
    "players": [
      {
        "player_id": "player-lee",
        "display_name": "Lee",
        "consent": {
          "memory_appearance": true,
          "identity_display": true,
          "media_use": true,
          "mission_invitation": true
        }
      },
      {
        "player_id": "player-mei",
        "display_name": "Mei",
        "consent": {
          "memory_appearance": true,
          "identity_display": true,
          "media_use": true,
          "mission_invitation": true
        }
      }
    ]
  },
  "matches": [
    {
      "match_id": "match-001",
      "game": "free_fire",
      "mode": "battle_royale_squad",
      "map_name": "Bermuda",
      "started_at": "2026-05-10T12:00:00Z",
      "ended_at": "2026-05-10T12:20:00Z",
      "placement": 5,
      "result": "eliminated",
      "events": [
        {
          "event_id": "event-16",
          "provider_event_type": "PLAYER_KNOCKED",
          "actor_id": "player-lee",
          "timestamp_seconds": 888,
          "location": "Clock Tower",
          "details": {"zone_phase": 4}
        },
        {
          "event_id": "event-17",
          "provider_event_type": "TEAMMATE_REVIVED",
          "actor_id": "player-mei",
          "target_id": "player-lee",
          "timestamp_seconds": 900,
          "location": "Clock Tower",
          "details": {"zone_phase": 4}
        }
      ]
    }
  ],
  "squad_history": {
    "previous_session_at": ["2026-05-10T12:00:00Z"],
    "days_since_full_squad": 42,
    "recent_rematch_count": 0
  },
  "current_context": {
    "active_player_ids": ["player-lee", "player-mei"],
    "available_modes": ["battle_royale_squad"],
    "reunion_eligible": true
  },
  "media_references": [
    {
      "media_id": "clip-synthetic-17",
      "kind": "clip",
      "event_ids": ["event-17"],
      "consented_player_ids": ["player-lee", "player-mei"]
    }
  ]
}
```

The telemetry adapter deterministically maps `provider_event_type` and allowlisted details into
canonical events. Unknown JSON fields and broken schema cross-references return `422`. Unsupported
provider events, unsafe detail combinations, failed eligibility, or invalid media consent return a
typed `rejected` result before a provider call. Opted-out identities are replaced with request-scoped
aliases before window construction or prompting; opted-out-authored social prose is excluded.

For the current v2 contract, the batch-level `squad.players` list is the provider-asserted roster
for every submitted match. A production adapter must split batches when the roster changes (or add
an authenticated per-match roster field in a later contract) rather than infer participation from
an unrelated event.

### Internal compact decision and enrichment boundary

The public request and response do not expose the provider's internal schema. Deterministic
preparation builds a consent-safe `StoryBriefV2` with no more than four narratively neutral
`eligible_event_windows`, plus runtime `mission_affordances`. The current affordance catalogue has
exactly three families: `reunion`, `role_reversal`, and `redemption`; only families supported by
the submitted evidence and current feasibility are offered.

Each `MissionAffordanceV2` carries backend-owned `affordance_id`, `family`, `window_id`,
`source_event_ids`, `source_match_ids`, `source_context_ids`, `parameters`,
`objective_candidate_ids`, and `allowed_reason_codes`. The corresponding
`MissionCapabilityCandidate` records own `recipe`, `assigned_player_id`, `source_event_ids`, and
`verification` (`metric`, `operator`, and `target`).

For one eligible request, AI returns `CompactInterpretationDecisionV2` as exactly one of:

- `decision: "abstain"`, `abstention_reason_code: "no_meaningful_episode"`, and `proposal: null`; or
- `decision: "generate"`, a null abstention reason, and one compact proposal that:
  - selects exactly one offered window;
  - puts every offered ID exactly once in `ranked_affordance_ids` and places
    `selected_affordance_id` first;
  - supplies only the selected affordance's allowlisted `selection_reason_codes`;
  - authors the title, teaser, summary, current-relevance explanation, player perspectives, mission
    title/text, and an `objective_descriptions` entry for every objective candidate of the selected
    affordance; and
  - attaches bounded evidence and capability references to those authored sections.

The generated compact proposal does not author authoritative match or event ID lists, complete `GroundedClaim` objects,
media mappings, mission recipe, objective IDs, assignments, required flags, verification metrics,
operators, targets, source event/match/context references, the consent-safe roster, a delivery
ID/status, or Studio trace records. The backend resolves the selected window, selected affordance,
and compact references against the prepared evidence ledger and affordance catalogue. A literal
player name, canonical action, location, or selected-match value may
add conservative candidate evidence from the selected window when a reference was omitted. This is
not a unique semantic mapping and does not infer emotion, meaning, or causality; the expanded claims
and prose still have to pass the full role-tuple, value, privacy, and grounding validators. Event
categorical and ordinary numeric detail claims require lexical detection of a typed value plus an
associated field/action cue. Survival wording may use positive squad-alive telemetry without
restating its numeric count. Lexically selected candidate events replace redundant broad
citations; when no event evidence is inferred, at most one explicitly cited event is retained as a
default citation for that section. The backend derives
the authoritative proposal fields and controls, validates the complete
proposal, and only then creates the delivery ID/status, safe Studio trace, and public result.

This is an internal structured-output simplification only. The public
`InterpretDeliveryResultV2` remains the fully enriched delivery shown below, so clients do not
consume the compact decision or proposal. Removing duplicated IDs and backend-owned controls from model output is
expected to reduce malformed and contradictory structured responses; it does not reduce grounding,
privacy, or mission checks because deterministic code reconstructs and validates the complete
control plane. Player, action, and target terms are checked as one supported role tuple; merely
citing separate events that contain each word is insufficient. That expected reliability benefit
is not inferred from schema size alone. Automated suites cover the current contract. A historical
telemetry-only Groq 120B request passed on 8 August 2026 with the older V2.4 prompt, but it is not
evidence for the active `memory-interpreter-v2.6-mission-affordances` prompt. Current live
reliability remains an evaluation task.

A successful response has `status: "pending_player_decision"` and only validated delivery fields.
This abridged example omits additional required section claims and trace details:

```json
{
  "schema_version": "2.1",
  "request_id": "request-17",
  "delivery_id": "delivery-opaque-id",
  "status": "pending_player_decision",
  "reason_codes": [],
  "memory": {
    "title": "Back for One More",
    "memory_type": "comeback",
    "summary": "Mei revived Lee at Clock Tower.",
    "notification_teaser": "A squad moment is ready.",
    "why_this_matters_now": "It has been 42 days since the full squad played.",
    "selected_match_id": "match-001",
    "selected_event_ids": ["event-16", "event-17"]
  },
  "player_perspectives": [
    {
      "player_id": "player-lee",
      "display_name": "Lee",
      "message": "You were revived at Clock Tower.",
      "evidence_event_ids": ["event-17"]
    },
    {
      "player_id": "player-mei",
      "display_name": "Mei",
      "message": "You brought Lee back into the match.",
      "evidence_event_ids": ["event-17"]
    }
  ],
  "next_chapter": {
    "title": "Return the Favour",
    "mission": "Bring the squad back, complete one match, and let Lee make the first squad revive.",
    "recipe": "remix",
    "family": "role_reversal",
    "invitation_player_ids": ["player-lee", "player-mei"],
    "objectives": [
      {
        "objective_id": "objective:role_reversal:participants:window_match-001_1:1",
        "description": "Bring both invitation-ready squadmates into one lobby.",
        "required": true,
        "source_event_ids": ["event-16", "event-17"],
        "verification": {
          "metric": "squad.participant_ids",
          "operator": "contains_all",
          "target": ["player-lee", "player-mei"]
        }
      },
      {
        "objective_id": "objective:role_reversal:match:window_match-001_1:1",
        "description": "Complete one match together.",
        "required": true,
        "source_event_ids": ["event-16", "event-17"],
        "verification": {
          "metric": "squad.matches_completed",
          "operator": "at_least",
          "target": 1
        }
      },
      {
        "objective_id": "objective:role_reversal:first_revive:window_match-001_1:1",
        "description": "Lee makes the squad's first revive.",
        "assigned_player_id": "player-lee",
        "required": true,
        "source_event_ids": ["event-17"],
        "verification": {
          "metric": "match.first_squad_revive_actor_id",
          "operator": "equals",
          "target": "player-lee"
        }
      }
    ]
  },
  "grounded_claims": [
    {
      "claim_id": "claim-summary-revive",
      "output_section": "summary",
      "subject_id": "player-mei",
      "predicate": "revived",
      "target_id": "player-lee",
      "location": "Clock Tower",
      "supporting_event_ids": ["event-17"]
    }
  ],
  "validation": {"passed": true, "correction_attempted": false, "issues": []},
  "studio_trace": {"trace_id": "trace-redacted", "stages": []},
  "metadata": {
    "provider": "groq",
    "model": "configured-live-model",
    "mode": "live_ai",
    "prompt_version": "memory-interpreter-v2.6-mission-affordances",
    "content_origin": "live_ai_validated",
    "grounded_render": false,
    "narrative_fallback": false
  }
}
```

An abridged accepted AI abstention returns no delivery artifacts:

```json
{
  "schema_version": "2.1",
  "request_id": "request-17",
  "status": "not_generated",
  "reason_codes": ["ai_no_meaningful_episode"],
  "player_perspectives": [],
  "grounded_claims": [],
  "validation": {"passed": true, "correction_attempted": false, "issues": []},
  "studio_trace": {"trace_id": "trace-redacted", "stages": []},
  "metadata": {"content_origin": "no_player_content"}
}
```

Every factual clause or constrained factual field must have a complete backend-derived claim in the
public schema. The provider must return every consent-safe eligible perspective ID exactly once;
the backend orders those supplied perspectives by the trusted roster and validates the exact set. It
does not restore or synthesize a missing perspective.
The selected **Next Chapter** may contain AI-authored descriptions, but its `family`, recipe,
objective IDs, player assignments, required flags, verification metrics/operators/targets, and
source event/match/context references are backend controls. The compact proposal ranks only the
runtime affordances, selects exactly one, uses only that affordance's allowed reason codes, and
authors a description for every compiled objective. Conservative lexical validation rejects tested
conflicting metric actions, operators, metric-associated counts, player names, and known unoffered
gameplay condition terms. Counts attached to participants or other nouns are evaluated in context
rather than compared with the wrong target. Mission and objective wording must express the selected
backend requirements. This is not a universal semantic proof for arbitrary mission prose.

Every normalized event fact declares `event_scope` as `player`, `squad`, or `match`. A player-scoped
event keeps its actor/target semantics; squad- and match-scoped facts are collective rather than an
individual player's action. The provider receives direct-role event IDs for each required
perspective. It receives a squad event as a full-squad perspective permission only when an
allowlisted membership detail proves participation by the complete submitted roster. Categorical
event details are restricted to deterministic key/value allowlists before prompting.

The provider may select only one deterministically offered chronological event window and cite only
supplied compact fact or capability references. It may not invent players, events, roles, locations,
timestamps, numbers, outcomes, media mappings, consent state, assignments, or verification rules.
`why_this_matters_now` may use only supplied structured current-context signals. Unknown,
cross-window, wrong-player, or otherwise unsupported references fail enrichment or validation.
Those consent-safe signals include previous-session timestamps, days since full-squad activity,
recent rematch count, active players, available modes, and reunion eligibility. Secret-like input is
rejected before provider use. Delivered memory types are checked against episode/history evidence,
and unsupported observation language is withheld.

`active_player_ids` never gates invitation eligibility. A consented player with
`memory_appearance: true` and `mission_invitation: true` remains invitation-ready while inactive;
the player UI may label that recipient `away`. `online` and `away` are presentation states only.

Media mapped to a collective or match-scoped event requires media consent from the complete
submitted roster; sparse actor/target fields are not treated as proof that nobody else appears.

Provider transport failure, timeout, or refusal returns a safe HTTP `503`. A repairable malformed
schema, expansion error, or validation failure may receive exactly one correction call containing
stable issue codes and allowlisted section IDs, never rejected generated prose or free-form
validator messages. A terminal correction failure fails closed. Eligibility or terminal proposal
validation failure returns `rejected` with no memory, perspectives, mission, claims, or media
selection. Rejected proposal prose must not be returned to the player or Developer Studio.

Groq GPT-OSS is the preferred live v2 provider. Deterministic mode remains available for tests and
explicitly labelled offline Studio demonstrations; deterministic narrative must never be labelled as
a live AI delivery.

## `POST /v2/deliveries/{delivery_id}/decision`

Accepted request:

```json
{"schema_version": "2.0", "decision": "accepted"}
```

Declined request:

```json
{"schema_version": "2.0", "decision": "declined", "decline_reason": "not_relevant"}
```

`decline_reason` is required only for a decline and is exactly `not_relevant` or `details_wrong`.
Acceptance marks the validated mission as started and hands off to the invitation/continuation
experience. Either decline suppresses that exact process-local prototype delivery.
`details_wrong` additionally creates a source-quality signal for operations; it does not edit raw
telemetry, perform a client-side correction, or trigger automatic prompt/model changes.

The current prototype decision store is process-local and unauthenticated. Durable decisions,
idempotency, player binding, retention, deletion, and operations access remain deferred until
consent and privacy decisions are approved.

After acceptance, the current browser demo follows a scripted sequence: invitations are shown,
the invitation-ready squad joins, the game starts, the game ends, and the selected mission is
marked complete. That sequence does not call a new-match ingestion endpoint and does not verify
objective metrics against real telemetry. Real notifications/invitations, post-match ingestion,
and objective verification are deferred with authentication and durable persistence.

## V2 media and Studio boundary

Media is reference-only. The backend may attach a `media_id` only when every event represented by
that media reference belongs to the selected episode: `media.event_ids` must be a subset of the
enriched delivery's selected event IDs. The media reference does not have to cover every selected
event. The AI draft does not choose authoritative media.
Unknown or mismatched IDs fail closed. The first prototype
uses curated synthetic clips, thumbnails, or keyframes and makes no automated video-understanding
claim.

Developer Studio may show synthetic raw telemetry, normalization results, eligibility and consent
outcomes, neutral offered windows, sanitized dynamic `mission_affordances`, ranked and selected
affordance/family IDs under `mission_selection` (`ranked_affordance_ids`,
`selected_affordance_id`, `selected_family`, and `reason_codes`), backend-owned objective controls,
`active_player_count` versus `invitation_eligible_count`, correction/validation state, typed
abstention, provider/model/prompt version, safe usage metrics, and structured feedback. It never
shows raw prompts, the raw compact provider draft, chain-of-thought, API keys, opted-out identities,
provider exception text, or rejected and unvalidated proposal prose. A deterministic result is a
clearly labelled `deterministic_studio_sample` for Studio/tests, never a player-facing live fallback.

## Current v1.0/v1.1 compatibility API

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
  "phase": "v1-compatibility+v2",
  "provider": "deterministic",
  "model": "rules-v1",
  "mode": "deterministic"
}
```

The FastAPI application version is `0.3.0`; v1 compatibility routes remain available.

## `POST /v1/memories/discover-history`

Ranks historical packs without a model call. The request accepts 1-50 v1.0 or v1.1 packs and
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
| `ready` | Verified, confirmed, generated, and deterministically valid | Yes, in a live-provider mode |
| `rejected` | Filtered, ineligible, or generated output failed validation | No before a gate; in a live-provider mode, possibly yes if generated output was later rejected |

The `ready` body contains the memory, opted-in player perspectives, next-chapter quest, validation
report, and provider/prompt/pipeline version metadata. Because the route excludes `null` response
fields, `memory` and `next_chapter` are absent when a gate stops generation or validation rejects
the artifacts; `player_perspectives` remains an empty array. `discovery`, review states,
`validation`, and metadata remain available to explain the result.

`metadata.prompt_version: "narrative-scaffold-v1"` identifies the prompt contract used by the
model-capable stages. `metadata.narrative_boundary: "model-prose-deterministic-controls-v1"`
records that player-facing prose may be model-authored while evidence, consent, identity,
assignment, and verification controls remain deterministic.

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

The service does not silently switch a failed live-provider request to deterministic content.

Final validation checks exact schemas, IDs, evidence types, perspective ownership, and quest-rule
shapes, plus conservative lexical checks for selected unsupported names, locations, numbers,
actions, relationships, emotions, and motives. These heuristics reduce obvious hallucinations but
do not prove every implication in arbitrary prose. A production service still needs broader
semantic evaluation, moderation, adversarial testing, and human review.

In live mode, the model authors memory title/type/summary, each personalized perspective message,
and quest title/mission/recipe/objective descriptions. The server preserves the deterministic
evidence set, per-player references, safe identities, quest assignments, required flags, source
events, and verification rules. It also overwrites model-authored confidence and confirmation with
the deterministic score and normalized review state. The merged result must pass the privacy,
evidence, action, objective-alignment, and lexical checks above.

## Provider configuration

The deterministic provider is appropriate for repeatable tests and offline Studio demos. The v2
player route requires an explicitly configured Groq or OpenAI provider and fails closed; it never
silently uses deterministic narrative when a live provider is unavailable.

The active v2 prompt contract is `memory-interpreter-v2.6-mission-affordances`. Any V2.4/120B smoke
record is historical only and cannot be cited as validation of this prompt.

The default needs no credentials:

```dotenv
MEMORYOS_PROVIDER=deterministic
```

To opt into the recommended Groq live generation path, copy `.env.example` to `.env` and set:

```dotenv
MEMORYOS_PROVIDER=groq
GROQ_API_KEY=your_server_side_key
GROQ_MODEL=openai/gpt-oss-20b
GROQ_V2_MAX_OUTPUT_TOKENS=2500
```

The existing OpenAI path remains available:

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

# Recommended free-tier live mode; reads GROQ_API_KEY from .env
$env:MEMORYOS_PROVIDER = "groq"
uvicorn backend.main:app --reload
```

Keep the key server-side. The live provider uses structured typed responses, but deterministic code
still owns evidence, consent, eligibility, review state, and final validation.

For a deployed server-to-server frontend proxy, optionally set `MEMORYOS_PROXY_TOKEN`. When it is
non-empty, protected data-bearing routes require the same value in the
`X-MemoryOS-Proxy-Token` header, including the v2 Studio trace lookup; `/health` remains public.
Keep this value in server environment variables only—never bundle it into browser JavaScript.
Local development remains unchanged while the variable is unset.

Each current v1.1 model request uses low reasoning effort, a 30-second timeout, at most two SDK
retries, and a 2,000-token output ceiling. V2 compact interpretation uses a 2,500-token Groq
ceiling so the synthetic Story Brief, strict schema, and completion budget fit the prototype
account's 8K envelope. The OpenAI adapter retains its 4,000-token ceiling. Either provider fails
closed rather than returning a partial delivery. OpenAI responses use `store=False`; Groq requests
omit the unsupported `store` field. See the official
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

The canonical `/` player route uses same-origin `/api/delivery/prepare` and
`/api/delivery/decision` proxies for `POST /v2/memories/interpret-delivery` and
`POST /v2/deliveries/{delivery_id}/decision`. The prepare route supplies the server-held synthetic
raw telemetry fixture and accepts only fully validated live-AI delivery output or the minimal typed
`not_generated` projection. The decision route
accepts `accepted` or `declined`; a decline must be either `not_relevant` or `details_wrong`.
Decisions are process-local prototype data only.

The authoritative `InterpretDeliveryResultV2` remains server-side. The browser receives
`PlayerPendingDeliveryProjectionV2`, which contains display-safe memory text, source display data,
verified-moment labels, only the current player's perspective, one selected `next_chapter`, and an
invitation roster. Raw player IDs and objective IDs are replaced with request-scoped
`recipient_ref` and `objective_ref` values. The projection deliberately omits raw event IDs,
`grounded_claims`, backend verification rules, metric/operator/target controls, source references,
and `studio_trace`. A browser abstention is the smaller `PlayerNotGeneratedV2` shape with singular
`reason_code: "ai_no_meaningful_episode"`.

`/history` is a separate read-only view. It does not prepare a delivery, collect review decisions,
or record accept/decline feedback. The older `/api/discover`, `/api/history`, and `/api/generate`
routes remain compatibility infrastructure and are not the canonical consumer decision path.

Types are generated from the v2 OpenAPI schema, opaque delivery IDs remain behind the same-origin
server boundary, and malformed, rejected, or deterministic-demo results fail closed in the player
route. Delivery preparation and decision controls do not belong in `/history`.

## Data boundary

Included JSON is synthetic evaluation data. Do not deploy this prototype with real player data
without authentication, ownership checks, rate limiting, regional privacy rules, retention policy,
and a security review.
