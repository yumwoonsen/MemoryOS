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
Deterministic narrative is reserved for tests and explicitly labelled offline Studio demonstrations;
it must never be presented as a live AI result.

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

**Status:** implemented; automated suites and one configured live-provider smoke run passed

The internal v2 provider schema is simplified so AI selects one offered event window and returns only
the player-facing language, perspectives, mission wording, and compact fact/capability references it
must reason about. The model does not repeat authoritative selected match/event ID lists, complete
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

The provider selects one offered mission candidate and authors one objective description. Its
candidate-specific `authoring_scope` limits prose to the permitted intent, player IDs, and count;
recipe, assignment, source events, and verification rule remain deterministic.

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
selects one, and authors its language; it cannot introduce a fourth family, new assignments, or new
verification rules.

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
