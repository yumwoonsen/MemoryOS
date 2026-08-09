# Roadmap

## Phase 1 — Memory Engine foundation (complete)

- Versioned Memory Pack and result contracts
- Discovery, perspective, quest, and validation stages
- Deterministic and structured-model providers
- Golden fixtures and quality tests

## Phase 2A — Historical discovery backend (complete for prototype)

- Deterministic ranking across up to 50 packs
- Split source-verification and meaning-confirmation states
- Consent-aware evidence compilation and redaction
- Selected-memory generation and strengthened validation
- OpenAPI contract and regression evaluation

## Phase 2B — Consumer memory delivery (complete for prototype)

Completed in the integrated teammate slice and Phase 2B delivery flow:

- Mobile-first reveal flow for one grounded current memory
- Evidence-first story, current-player perspective, and quest preview
- Server-side backend proxy with an exact-fixture hosted fallback
- Runtime result guards and rendered HTML regression tests
- Consumer-facing AI Memory Inbox that prepares one source-verified moment
- Accept-mission and structured-decline decisions, without asking players to audit telemetry
- Ready-only player reveal and consent-safe redaction presentation
- OpenAPI-derived client types and API contract tests

The `/` player flow is now the AI Memory Inbox: it prepares one source-verified memory and mission,
then records accept, not-relevant, or details-wrong feedback in process-local prototype storage.
`/mission` owns the accepted reunion continuation, while `/history` is a compact, privacy-safe
timeline rather than a second decision interface. Source verification remains an upstream
telemetry/data-quality responsibility; player feedback expresses relevance and is never used to
rewrite match facts.

## Phase 3 — Backend validation, Studio, and reunion loop (complete for prototype)

### 3.1 — Test and select a no-cost/open-source model

**Prototype status: integrated, with broader model comparison still open.** Gemini
`gemini-3.6-flash` is the preferred hosted prototype provider; Groq GPT-OSS and OpenAI remain
available for comparison. Gemini uses the official OpenAI-compatible endpoint with a strict
sanitized schema, low reasoning, no explicit temperature, a 60-second per-attempt timeout, no hidden
SDK retries, and a 4,000-token v2 ceiling. MemoryOS may make one explicit semantic correction. The
original Pydantic and deterministic validators remain authoritative, and failures close
without partial delivery. Free-tier trials are limited to synthetic, non-sensitive telemetry. The
offline evaluator captures grounding, abstention, consent, mission, latency, token, correction, and
feedback metrics by prompt/model version. A wider comparison of hosting cost, hardware needs,
latency, and model quality remains production research; it does not change deterministic consent,
evidence, or validation ownership.

### 3.2 — Collaborator dashboard and backend visibility

**Prototype status: complete in Developer Studio.** The Studio uses same-origin server routes and
the versioned OpenAPI contract to show sanitized telemetry preparation, eligible event windows, AI
provider metadata, validated claim mappings, backend-owned mission rules, correction status,
delivery status, and source-quality feedback. Player responses remain minimal, and neither Studio
nor the player UI exposes raw prompts, secrets, opted-out identities, or rejected prose. Integration
checks cover loading, provider failures, malformed responses, offline demonstration labels, and
empty states.

### 3.3 — Complete the consumer decision path

**Prototype status: complete on the consumer continuation branch.** The canonical `/` view
validates the recorded decision response, shows reason-specific decline completion, and hands an
accepted delivery to the dedicated `/mission` route through an ephemeral in-memory session.

- Adjust the player frontend around the final delivery contract: one AI-prepared memory, its
  grounded explanation, and a clear reunion mission.
- On **Accept mission**, show the squad-safe mission-start state and hand off to the invitation /
  continuation experience.
- On **Decline**, capture exactly one structured reason: **Not relevant to me** or **Details are
  wrong**; suppress the mission and show a respectful completion state. “Details are wrong” is a
  source-quality signal for operations, not a client-side correction to trusted telemetry.
- Replace the prototype in-memory decision store with authenticated, durable, privacy-reviewed
  storage only after data-retention and consent decisions are approved.

### 3.4 — Reunion and continuation experience

**Prototype status: complete as a labelled static simulation.** The `/mission` slice includes a
privacy-safe invitation roster, inactive-but-consented squad reactivation, a scripted lobby/game
success sequence, a family-specific “Story Continues” chapter, and session-only relevance
feedback. `/history` reflects the resulting milestones in a compact read-only timeline. Real
notifications, clips, Garena match-result ingestion and verification, authentication, and durable
feedback remain deferred production work.

- In-app Memory Inbox or notification delivery with a curated moment clip
- Squad invitation and acceptance simulation
- Static, clearly labelled family-specific mission completion for the prototype
- Deterministic mission verification from authenticated new-match results in a future integration
- “Story Continues” chapter generation
- Memory timeline and feedback capture
- Optional dismissal feedback, kept separate from factual source disputes

## Phase 4 — AI-first v2.1 prototype (implemented)

The Phase 1–3 implementation remains the v1.1 compatibility baseline. New ingestion now uses a
separate v2 contract rather than extending or inheriting the composed `MemoryPackV11` shape.
Compatibility endpoints stay available during migration and are deprecated only after production
authentication, persistence, and rollout telemetry are ready.

### 4.1 — Raw telemetry contract and deterministic preparation — complete

- Defines a telemetry-only v2 DTO with squad, match, event, structured current-context, optional
  social, and optional curated-media mapping inputs.
- Normalizes source formats before provider use and rejects unknown event/detail combinations and
  malformed cross-references at the API boundary.
- Replaces opted-out identities with request-scoped aliases when their events are needed for factual
  continuity and excludes their social prose, perspectives, media identity, invitations, and missions.
- Builds deterministic eligible chronological event windows with stable IDs and allowed evidence,
  identity, context, and media sets.

### 4.2 — One compact AI decision, deterministic expansion, and validation — complete

- Requests one typed internal interpretation decision from the preferred hosted Gemini provider:
  either a grounded abstention or one offered event window, memory framing, notification teaser,
  player perspectives, current relevance, and one selected mission affordance. Groq GPT-OSS and
  OpenAI remain alternative implementations behind the same boundary.
- Requires evidence references for every factual clause and provider-supplied perspective IDs for
  every opted-in squad member. The backend orders those perspectives and validates the exact roster;
  it does not restore a missing perspective.
- Deterministically expands the compact draft into authoritative match/event IDs, complete claims,
  eligible media, mission recipe, and objective ID/assignment/rule; after the full validation pass,
  it creates delivery state and a safe trace.
- Carries explicit `player`, `squad`, and `match` event scopes. Collective perspective permission is
  granted only when allowlisted membership telemetry proves full-squad participation; categorical
  detail values are allowlisted. Categorical and ordinary numeric detail claims require the typed
  value plus an associated field/action cue; survival wording may use positive squad-alive telemetry
  without restating its numeric count.
- Uses conservative lexical candidate evidence without treating it as a unique semantic mapping;
  tuple, prose, privacy, value, and grounding validators still decide delivery.
- Supplies deterministic reunion, role-reversal, and redemption affordances, each composed from
  backend-owned objective capabilities and an `authoring_scope` of allowed intent, players, and targets;
  AI selects one and writes its mission title and short story bridge, while the backend compiles the
  exact objective descriptions. Conservative checks reject contradictory targets/operators,
  unoffered mechanics, unsupported facts, privacy violations, and unsafe content without requiring
  the bridge to repeat every rule. Assignments, required flags, source event IDs, media eligibility,
  and machine-verification rules remain deterministic.
- Permits at most one correction call using stable validator issue codes and allowlisted section
  IDs, never rejected provider prose or validator messages. Provider failure,
  refusal, malformed output, or a second validation failure returns no generated artifacts.
- Keeps deterministic narrative generation only for tests and explicitly labelled offline Studio
  demonstrations; never present it as a live-AI fallback.

### 4.3 — Dynamic mission affordances and reactivation — complete

- Builds a typed, consent-safe Story Brief containing neutral windows and feasible mission
  affordances rather than one hard-coded objective space.
- Lets AI rank and select one offered affordance while deterministic validation owns its family,
  assignments, objective copy, and rules. The public mission field carries the AI story bridge; the
  public objectives carry backend-compiled steps.
- Treats current activity as context rather than invitation authority, allowing inactive original
  squadmates with valid consent to join the scripted reunion lobby.
- Returns `not_generated` with no player artifacts when AI makes a valid abstention.
- Uses `live_ai_validated` provenance for player delivery and reserves
  `deterministic_studio_sample` for explicitly labelled Studio demonstrations.

### 4.4 — V2 API, player adapter, and safe Studio trace — complete

- Implements `POST /v2/memories/interpret-delivery` and
  `POST /v2/deliveries/{delivery_id}/decision`, with generated OpenAPI client types and contract
  tests.
- Moves the canonical `/` player route to same-origin v2 proxies while keeping `/history` read-only
  and preserving the completed Phase 3.3/3.4 interaction sequence.
- Shows synthetic normalization, offered window IDs, validated evidence links, safe provider
  metadata, issue codes, final status, and structured feedback in Studio.
- Excludes raw prompts, chain-of-thought, secrets, opted-out identities, provider exception text,
  the raw compact provider draft, or rejected and unvalidated proposal prose in Studio or the
  player client.
- Treats curated synthetic media as reference-only, requires deterministic event mappings, and makes
  a media reference eligible only when `media.event_ids` is a subset of the selected episode; it
  makes no automated video-understanding claim.

### 4.4 — Authenticated durable decisions and operations feedback

- Bind decisions and exact-delivery suppression to an authenticated player with idempotency and
  ownership checks.
- Route `details_wrong` to an operations source-quality queue without editing trusted telemetry or
  automatically changing prompts/models; keep optional dismissal feedback separate.
- Approve consent, retention, access, deletion, regional privacy, and audit policies before
  replacing the prototype's process- and session-local stores.

## Production questions to resolve later

- Which Free Fire event and social signals are genuinely available internally?
- What consent, retention, and regional privacy rules apply to squad memories?
- Which open-source model and hosting path meets the required quality, latency, licence, and
  operational-cost envelope at Garena scale?
- Which constrained-generation, semantic-grounding, moderation, and human-audit layers should
  replace the prototype's lexical validation heuristics?
- How should relevance feedback and upstream source-quality outcomes affect future eligibility
  without treating players as telemetry editors?
- What experiment design can isolate dormant-squad reactivation impact?
- How should pseudonyms, deletions, and consent changes propagate across stored squad memories?
- What authenticated retention, deletion, suppression, and operations-access policy is acceptable
  for delivery decisions and source-quality signals?
