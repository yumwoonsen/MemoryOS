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

**Prototype status: integrated, with broader model comparison still open.** Groq GPT-OSS is
available behind the provider boundary for structured live interpretation. The offline evaluator
captures grounding, abstention, consent, mission, latency, token, correction, and feedback metrics
by prompt/model version. Malformed, unavailable, or ungrounded output fails closed. A wider
comparison of hosting cost, hardware needs, latency, and model quality remains production research;
it does not change deterministic consent, evidence, or validation ownership.

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

**Prototype status: complete for the local simulation.** The `/mission` slice includes invitations
derived only from privacy-filtered perspectives, deterministic evaluation of the existing mission
rules against a synthetic rematch, a grounded “Story Continues” chapter, a mission continuation
timeline, and session-only relevance feedback. `/history` reflects the resulting milestones in a
compact read-only timeline. Real notifications, clips, Garena match-result ingestion,
authentication, and durable feedback remain deferred production work.

- In-app Memory Inbox or notification delivery with a curated moment clip
- Squad invitation and acceptance simulation
- Deterministic mission verification from a new match result
- “Story Continues” chapter generation
- Memory timeline and feedback capture
- Optional dismissal feedback, kept separate from factual source disputes

## Phase 4 — AI-first v2 prototype (implemented)

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

### 4.2 — One complete AI Memory Proposal with deterministic validation — complete

- Requests one typed `MemoryProposal` from the preferred live Groq GPT-OSS provider, selected from exactly
  one offered event window: memory framing, notification teaser, player perspectives, current
  relevance, and reunion-mission prose.
- Requires evidence references for every factual clause and exactly one perspective for each
  opted-in squad member.
- Keeps assignments, required flags, source event IDs, media eligibility, and machine-verification
  rules deterministic; the model never creates or changes those controls.
- Permits at most one correction call using stable validator issue codes. Provider failure,
  refusal, malformed output, or a second validation failure returns no generated artifacts.
- Keeps deterministic narrative generation only for tests and explicitly labelled offline Studio
  demonstrations; never present it as a live-AI fallback.

### 4.3 — V2 API, player adapter, and safe Studio trace — complete

- Implements `POST /v2/memories/interpret-delivery` and
  `POST /v2/deliveries/{delivery_id}/decision`, with generated OpenAPI client types and contract
  tests.
- Moves the canonical `/` player route to same-origin v2 proxies while keeping `/history` read-only
  and preserving the completed Phase 3.3/3.4 interaction sequence.
- Shows synthetic normalization, offered window IDs, validated evidence links, safe provider
  metadata, issue codes, final status, and structured feedback in Studio.
- Excludes raw prompts, chain-of-thought, secrets, opted-out identities, provider exception
  text, or rejected and unvalidated proposal prose in Studio or the player client.
- Treats curated synthetic media as reference-only, requires deterministic event mappings, and makes
  no automated video-understanding claim.

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
