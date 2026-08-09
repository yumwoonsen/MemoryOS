# Architecture decision log

## ADR-001 — Backend before frontend

**Status:** accepted

The backend proves ranking, grounding, personalization, and quest connection before frontend
integration. The concurrent UI consumes the resulting versioned API instead of defining product
truth independently.

## ADR-002 — Python, FastAPI, and Pydantic

**Status:** accepted

Python supports fast AI iteration; FastAPI exposes the prototype with minimal ceremony; Pydantic is
the shared contract for request validation, model Structured Outputs, and response validation.

## ADR-003 — Lightweight Memory Packs, not full telemetry

**Status:** accepted for v1.0/v1.1 compatibility; superseded for new ingestion by ADR-013

The prototype uses key events, squad context, and human signals that a live-service game could
reasonably assemble. It does not require every movement or bullet event and does not pretend that an
undocumented Garena API exists.

## ADR-004 — Human confirmation is part of the product

**Status:** accepted for v1.0/v1.1 review workflows; refined for v2 by ADR-015

AI cannot reliably infer that a match felt funny or meaningful. In v1.1, humans independently review
source and meaning. In v2, authenticated telemetry ingestion and operations own source quality; the
player decides whether a validated memory is relevant and whether to start its mission.

## ADR-005 — Hybrid intelligence

**Status:** accepted; v2 ownership is refined by ADR-014

Player-facing memory framing, personalized perspectives, and quest wording may use a model.
Eligibility, selected evidence, identity references, consent, review state, quest verification
controls, validation, and final status remain deterministic.

## ADR-006 — One bounded model call per semantic stage

**Status:** accepted for Phase 1/2 compatibility; superseded for v2 by ADR-014

Discovery, perspectives, and quest generation have separate prompts and schemas. This improves
traceability and evaluation. Calls may be consolidated later only if latency and cost data justify
it without reducing quality or grounding.

## ADR-007 — Deterministic provider as the default

**Status:** accepted for tests and compatibility; refined for live v2 delivery by ADR-016

The repository must run without credentials and produce stable test results. Live AI is explicit,
shares the same contracts, and still ends in deterministic validation.

## ADR-008 — No backend persistence in Phase 1/2

**Status:** accepted for the prototype; production replacement deferred by ADR-017

JSON fixtures are sufficient for historical discovery. The frontend may persist prototype review
feedback, but backend database and feedback-learning design should wait until schemas have been
tested with users.

Until that persistence exists, the client keeps the complete selected pack, applies the review
decision, and resubmits it. A discovery rank, candidate ID, or score does not represent stored
review state.

## ADR-009 — Deterministic historical ranking

**Status:** accepted

Ranking up to 50 packs must be explainable, repeatable, and inexpensive. Evidence, human signals,
squad specificity, and reactivation context use fixed weights and an explicit threshold. Historical
ranking itself never calls AI, and a model cannot alter either eligibility or candidate order.

`/v1/memories/generate` accepts one complete pack and recomputes deterministic eligibility and
review state before any model call. It does not require proof that the pack previously appeared in a
top-candidate response. A caller could therefore submit every eligible pack separately; production
admission control, authentication, and rate limiting remain separate responsibilities.

The weighted component sum is the eligibility `score`. The repeated-type diversity penalty affects
only the iterative `ranking_score`; it never changes the threshold decision. A request also uses one
squad, target, roster, and current consent snapshot so ranking cannot combine conflicting identity
or consent state.

## ADR-010 — Source truth and personal meaning are separate

**Status:** accepted for v1.1 compatibility; refined for v2 by ADR-015

Schema v1.1 replaces the overloaded confirmation meaning with `source_status` and
`meaning_status`. A player may verify that an event happened without wanting it resurfaced. Only a
verified and confirmed memory may enter the new v1.1 `/generate` path; disputed and dismissed
memories are filtered. The deprecated v1.0 `/discover` adapter intentionally remains an exception
during migration and can produce reviewable drafts for `confirmed: false` packs.

## ADR-011 — Python owns the canonical contract

**Status:** accepted

FastAPI, Pydantic, and generated OpenAPI define request, response, consent, ranking, and status
semantics. The frontend consumes that interface instead of maintaining a separate Worker pipeline.
This prevents two runtimes from disagreeing about whether a memory is safe or ready.

## ADR-012 — Privacy is enforced before prompting

**Status:** accepted for v1.1 compatibility; strengthened for v2 by ADR-013 and ADR-014

The evidence compiler anonymizes opted-out participants before data reaches a generative stage.
Opted-out players receive no perspective and cannot be assigned quest objectives. Post-generation
validation remains a second defense, not the primary privacy mechanism. Model stages receive the
sanitized ledger and the preceding typed output rather than the original Memory Pack.

Validation combines exact type, evidence, identity, and quest-rule checks with conservative lexical
heuristics for known hallucination patterns. It fails closed, but it is not a proof system for every
possible implication in natural language; source and meaning review remain human decisions.

The model authors all player-facing prose, but not its factual control plane. Memory evidence,
player-specific references, safe identities, quest assignments, required flags, source IDs, and
verification rules come from deterministic scaffolds. Model-authored confidence and confirmation
are overwritten from trusted pipeline state. The merged narrative must still pass the deterministic
checks above.

V2 strengthens the pre-provider boundary: opted-out identities are replaced with request-scoped
aliases when their events are needed for factual continuity. Their social prose, perspectives,
media identity, invitations, and mission assignments are excluded.

## ADR-013 — Add a separate raw-telemetry v2 contract

**Status:** accepted and implemented for v2

V2 introduces composed raw request models and `POST /v2/memories/interpret-delivery`. It does not
inherit from or remove fields from `MemoryPackV11`. The v1.0 and v1.1 endpoints remain compatibility
routes during the production migration.

The v2 request contains match metadata, squad IDs and current consent, raw external telemetry,
structured current context, optional social context, and optional media references. A deterministic
adapter maps external event names and shapes into a strict canonical event vocabulary. Unknown event
types, unsafe detail fields, invalid cross-references, and invalid media mappings are rejected rather
than silently interpreted by a model.

Submitted event importance, review confirmation, and free-form “why this surfaced” text are not v2
input controls. Optional captions, tags, reactions, and saves remain player-authored context, never
trusted telemetry facts.

## ADR-014 — One AI MemoryProposal, deterministic control plane

**Status:** accepted for the initial v2 design; refined by ADR-018

The initial v2 contract asked the live provider for one complete typed `MemoryProposal` after
deterministic eligibility, consent filtering, and connected-window construction. That proposal
repeated selected event IDs and other controls beside memory type, narrative angle, title, teaser,
summary, current relevance explanation, one perspective per opted-in player, and reunion mission
prose. ADR-018 keeps the single-call interpretation boundary but replaces this provider schema with
a compact draft and deterministic enrichment.

The model may choose only one offered event window. It cannot invent event IDs, people, roles,
locations, timestamps, numbers, consent state, media mappings, assignments, or machine-verification
rules. Those controls are prepared and validated deterministically. Evidence references accompany
each factual clause or constrained factual field. One bounded correction call may receive stable
issue codes and allowlisted section IDs, but never rejected generated prose or validator messages;
a second failure rejects the proposal.

The three-stage scaffold pipeline remains available for v1.1 compatibility and deterministic
offline demonstrations. It is not the normal v2 live-delivery path.

## ADR-015 — Source quality is upstream; the player decides relevance

**Status:** accepted and implemented for v2

AI proposes an interpretation and deterministic code checks consistency with the trusted evidence
ledger. Neither AI nor the player proves that raw telemetry is authentic. Production source truth
requires an authenticated telemetry adapter and provenance outside model output.

The player receives only a validated delivery. **Accept mission** starts the reunion path.
**Decline** requires exactly `not_relevant` or `details_wrong` and suppresses that exact delivery for
the current prototype delivery. `details_wrong` additionally creates an operations source-quality signal;
it does not edit telemetry or trigger live prompt rewriting.

## ADR-016 — Live v2 delivery fails closed

**Status:** accepted and implemented for v2

Groq GPT-OSS is the preferred live v2 provider behind the existing provider-neutral structured
generation boundary. Refusal, timeout, malformed output, unavailable credentials, or failed
deterministic validation returns rejected/provider-error information with no generated artifacts.
Deterministic narrative is reserved for tests. The registered Studio preparation checkpoint is
deterministic but generates no prose; neither boundary may be presented as a live AI result. ADR-022
defines the separate exact-provenance saved-live-replay path.

Provider, model, prompt version, latency, and token counts may appear in a safe trace. Raw prompts,
chain-of-thought, credentials, request payloads containing private data, and rejected proposal prose
must not appear.

## ADR-017 — Feedback, media, and persistence stay bounded

**Status:** accepted for the prototype; production design deferred

The decision endpoint is `POST /v2/deliveries/{delivery_id}/decision`. The prototype keeps
session/process-local state, but authenticated durable storage is not introduced until consent,
retention, deletion, regional privacy, and operations-access decisions are approved.

Optional media is reference-only. A proposal may select a curated synthetic clip, thumbnail, or
keyframe ID only when every event represented by that media belongs to the selected episode
(`media.event_ids` is a subset of the selected event IDs). The media need not represent every event
in the episode. Unknown or mismatched mappings fail closed. MemoryOS does not claim automated video
understanding.

Developer Studio is an auditable structural trace, not a prompt inspector. It may show synthetic raw
input, normalization, eligibility, consent decisions, offered windows, validated evidence links,
provider metadata, validator issue codes, final delivery status, and structured feedback. Rejected
proposal prose and the raw compact provider draft are withheld.

## ADR-018 — Compact AI draft, deterministic enrichment, stable public delivery

**Status:** implemented; mission-copy responsibility refined by ADR-021

The initial compact v2 provider schema was simplified so AI selected one offered event window and
returned player-facing language, perspectives, mission wording, and compact fact/capability
references. The model did not repeat authoritative selected match/event ID lists, complete
`GroundedClaim` objects, media mappings, mission recipe, objective IDs, assignments, required flags,
source event IDs, verification rules, the eligible roster, delivery state, or Studio trace.

After the provider returns, deterministic code resolves the window and compact references against
the consent-safe evidence ledger and mission capability catalogue. It derives the omitted fields,
orders the provider-supplied perspective IDs by the trusted roster, validates that the IDs equal the
exact eligible set, constructs the full proposal claims and controls, and then runs the existing
privacy, chronology, role, value, context, media, prose-grounding, and mission validators. A delivery
record and safe trace are created only after that complete proposal passes.
It does not restore or synthesize a perspective omitted by the provider. Literal terms may add
conservative candidate evidence from the selected window, but this is not a unique semantic mapping
and never bypasses the complete validators. Categorical and ordinary numeric detail claims require
lexical detection of the typed value plus an associated field/action cue; survival wording may use
positive squad-alive telemetry without restating its numeric count. Unknown, wrong-player,
cross-window, or unsupported references fail closed; when several events share a literal term,
enrichment makes a conservative scored candidate selection that still passes complete validation.
One correction attempt remains bounded by safe validator codes and allowlisted section IDs.

Normalized facts distinguish `player`, `squad`, and `match` event scopes. Direct actor/target events
define a player's ordinary perspective permissions. A squad event becomes available as collective
perspective evidence only when an allowlisted membership count proves full-roster participation;
match-scoped facts cannot be reframed as an individual's action. Deterministic categorical
allowlists constrain accepted telemetry detail values.

The provider selected one offered mission candidate and, before ADR-021, authored objective copy.
Its candidate-specific `authoring_scope` limited prose to the permitted intent, player IDs, and
count; recipe, assignment, source events, and verification rule remained deterministic. ADR-021
moves the exact objective description into the deterministic backend while preserving the compact
selection boundary and stable public response.

This decision changes an internal model-output contract, not the public API. The public
`InterpretDeliveryResultV2`, player projection, decision endpoints, and Studio trace retain their
existing responsibilities. The smaller schema is expected to improve structured-output reliability
by removing duplicated identifiers and values that deterministic code already knows. It does not
weaken validation because those values are derived and checked rather than trusted from AI.

The reliability claim is not accepted as demonstrated merely because the schema is smaller.
Automated tests cover draft parsing, reference
resolution, deterministic enrichment, public-contract stability, adversarial unsupported facts,
privacy, fail-closed behavior, and correction. On 8 August 2026, a telemetry-only request through
Groq `openai/gpt-oss-120b` and prompt `memory-interpreter-v2.4-grounded-controls` produced a valid
`pending_player_decision` delivery without correction or deterministic narrative fallback. This
single smoke result proves operability, not a statistical reliability advantage over the former
schema or equivalent behavior from the default 20B model.

## ADR-019 — One delivered mission selected from dynamic affordances

**Status:** accepted for v2.1

The player receives one Next Chapter. Internally, deterministic preparation may offer three
mission families: reunion, role reversal, and redemption. An affordance groups the backend-owned
objective capabilities that together form one complete mission. AI ranks the offered affordances,
selects one, and authors its title and story bridge; it cannot introduce a fourth family, new
assignments, or new verification rules. ADR-021 assigns exact objective copy to the backend.

Invitation eligibility depends on memory-appearance and mission-invitation consent, not current
activity. Active status is a current-context signal and optional Online/Away presentation detail.
An inactive but consented original squad member can receive the prototype invitation and become
Joined without altering the source activity snapshot.

The v2.1 model may return an allowlisted `not_generated` abstention when eligible telemetry does
not contain a moment worth delivering. A repairable invalid generation receives one correction
attempt; a second failure is withheld. A deterministic evidence render is not substituted into
the live player path.

The prototype player journey after acceptance is intentionally static and clearly labelled:
invitation, lobby assembly, game start, and a successful family-specific outcome are simulated.
The dynamic product claim ends at validated mission selection. Authenticated post-match telemetry
and authoritative mission-result verification remain deferred.

## ADR-020 — Gemini is the preferred hosted prototype provider

**Status:** accepted and implemented; supersedes only the provider preference in ADR-016

Gemini `gemini-3.6-flash` is the preferred hosted provider for current prototype trials. The adapter
uses Google's official OpenAI-compatible endpoint, so the existing OpenAI SDK and provider-neutral
structured-generation boundary remain in place. Configuration is server-side through
`GEMINI_API_KEY`, `GEMINI_MODEL=gemini-3.6-flash`, and
`GEMINI_V2_MAX_OUTPUT_TOKENS=4000`. Groq GPT-OSS and OpenAI remain explicit alternatives.

Gemini requests use low reasoning, no explicit temperature, a 60-second per-attempt timeout, no
hidden SDK transport retries, and bounded output. MemoryOS owns one explicit semantic correction,
and the same-origin proxy permits 130 seconds for that bounded path. The adapter removes
provider-unsupported hints from the
strict wire JSON Schema, but never weakens the authoritative contract: returned JSON must pass the
original Pydantic response model, deterministic enrichment, and final validation. Refusal,
transport failure, malformed output, or terminal validation failure returns no partial player
artifacts and never falls back to deterministic prose labelled as live AI.

Free-tier Gemini use is limited to synthetic, non-sensitive prototype telemetry. It is not approval
to send production player data to a hosted provider; production use still requires the unresolved
privacy, retention, regional processing, security, contractual, and operations reviews.

ADR-016's fail-closed boundary remains in force. Its Groq preference and the dated Groq smoke record
remain historical context rather than evidence about Gemini or the current prompt/model combination.

## ADR-021 — Backend-compiled objective copy, AI-authored story bridge

**Status:** accepted and implemented for the V2.11 prompt boundary

The active prompt is `memory-interpreter-v2.11-backend-mission-copy`, loaded from
`memory_interpreter_v2_11.txt`. AI still performs the meaningful interpretation: it ranks the
offered episode-and-affordance combinations, selects one, and authors the memory language,
perspectives, mission title, and a short narrative bridge connecting the source episode to the next
chapter.

The deterministic backend now compiles each selected objective candidate into its exact public
description. It continues to own objective IDs, assignments, required flags, metrics, operators,
targets, source references, and verification rules. The public response remains compatible:
`next_chapter.mission` carries the AI-authored story bridge and `next_chapter.objectives` carries the
backend-compiled steps.

The validator no longer requires the story bridge to repeat every selected mechanical rule. It still
rejects contradictory targets or operators, unoffered mechanics, unsupported factual claims,
privacy violations, and unsafe content. This reduces brittle failures caused by harmless paraphrases
without allowing AI to redefine what the game can measure or what the mission requires.

This decision changes only the authoring boundary before delivery. The post-accept prototype remains
the clearly labelled scripted sequence: invitations, lobby assembly, game start, game end, and
mission completion. It does not ingest an authenticated result or claim real objective verification.

Historical V2.4 and V2.10 provider results remain labelled historical and are not evidence for the
active V2.11 prompt.

## ADR-022 — Backend-owned Studio scenarios and separated provenance

**Status:** accepted and implemented for the prototype

Developer Studio uses three backend-owned, versioned synthetic scenarios:
`rescue-role-reversal`, `repeated-near-miss`, and `ordinary-sparse-telemetry`. The backend catalog
loads their expected status/family labels from the offline evaluation manifest and publishes a safe
descriptor containing the scenario ID, purpose, fixture SHA-256, and fixture revision. Those labels
are evaluation metadata only. They never enter `RawTelemetryBatchV2`, `StoryBriefV2`, or the
provider payload and therefore cannot force the advertised result.

`GET /v2/studio/scenarios` lists the registry.
`POST /v2/studio/scenarios/{scenario_id}/prepare` accepts no body and performs deterministic
normalization, privacy filtering, neutral-window construction, and mission-affordance compilation
with zero provider calls. `POST /v2/studio/scenarios/{scenario_id}/interpret` also accepts no body
and runs only the exact registered fixture through the existing live V2 pipeline. This prevents a
named demonstration from silently accepting different client telemetry.

The Studio may display a reviewed live capture under the separate top-level origin
`saved_live_replay` only when the scenario ID, fixture hash/revision, provider, model, prompt
version, result schema, and capture timestamp match exactly. The committed replay registry is
currently empty. Saved replay is Studio inspection content, not player authorization, a generic
rescue fallback, deterministic prose, or a completed-result cache. The player projection accepts
only `live_ai_validated` pending deliveries and labels them
**AI-prepared · evidence-checked**.

The prototype intentionally has no backend result cache, request idempotency, completed-request
deduplication, or singleflight coordination. The browser disables scenario switching and duplicate
clicks only while one run is active. Each later **Run new live interpretation** click starts a fresh
pipeline and can use one initial provider call plus the one permitted correction call, for at most
two MemoryOS-owned semantic calls.

The post-accept sequence remains local and scripted. Its completed chapter title is selected
deterministically from the mission family: **Together Again**, **The Favour Returned**, or
**The Comeback Complete**, with a fixed collision-safe alternative when necessary. This is not a
second AI generation or telemetry-backed completion claim.
