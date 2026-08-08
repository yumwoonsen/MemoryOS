# MemoryOS architecture: AI-first v2 and v1.1 compatibility

## Objective

MemoryOS v2 is an AI-first interpretation pipeline. Its external input is raw, realistic synthetic
game telemetry plus limited squad context—not a pre-authored memory. Deterministic code establishes
the trusted evidence boundary, prepares eligible event windows, and validates the model's proposal
before anything reaches a player.

The correct product claim is:

> MemoryOS uses AI to turn trusted gameplay evidence into a grounded, personalized memory and
> reunion mission. Deterministic validation checks that the AI stayed within the supplied evidence.

AI is not the final authority on whether telemetry is authentic. That trust must come from an
authenticated telemetry adapter and source-quality controls. The player decides whether a validated
memory is relevant; the player is not asked to audit raw telemetry.

> **Implementation status:** the additive v2 public contract, orchestration, validators, frontend
> adapter, and acceptance tests exist. The updated automated suites and one telemetry-only live
> smoke run passed on 8 August 2026 with Groq `openai/gpt-oss-120b`, prompt
> `memory-interpreter-v2.4-grounded-controls`, no correction, and a validated pending delivery.
> Existing v1.0 and v1.1 routes remain runnable compatibility paths while production authentication,
> persistence, telemetry integrations, and broader comparative live evaluation are deferred.

```mermaid
flowchart LR
    A["Raw telemetry + squad context + consent"] --> B["Normalize canonical events"]
    B --> C["Filter consent and source quality"]
    C --> D["Build eligible event windows"]
    D --> E["AI returns one compact typed draft"]
    E --> F["Deterministic expansion: resolve references and enrich controls"]
    F --> G["Deterministic evidence, privacy, and mission validation"]
    G -->|"pass"| H["Pending player decision"]
    G -->|"fail"| I["Rejected with no draft prose"]
    H --> J{"Player decision"}
    J -->|"accept"| K["Mission started"]
    J -->|"decline"| L["Suppress exact delivery"]
```

The engine is Python-first. FastAPI and its OpenAPI document remain the canonical backend/frontend
contract; a browser or Worker must not implement an independent normalization, scoring, consent, or
validation pipeline.

## V2 responsibility boundary

| Layer | Responsibility |
|---|---|
| Telemetry adapter | Map external game event names and shapes into a strict canonical vocabulary; reject unknown or unsafe data |
| Deterministic backend | Source trust, consent, filtering, deduplication, eligibility, event windows, authoritative enrichment, mission controls, validation, trace construction, and fail-closed delivery |
| AI Memory Interpreter | Select one offered connected episode and author a compact typed draft containing player-facing language and bounded fact/capability references |
| Player frontend | Render validated delivery content only and collect one accept/decline decision |
| Player | Judge relevance and choose whether to start the reunion mission |

The additive v2 raw contract contains match metadata, squad membership and current consent, canonical
telemetry events, structured current context, optional social signals, and optional media references.
It does not accept a title, memory type, summary, perspective, mission, selected evidence set, or
prewritten “why this surfaced” narrative. Optional captions and tags remain player-authored context,
not telemetry facts.

External event names and detail shapes must pass through a deterministic adapter before eligibility.
The adapter outputs a canonical event vocabulary with typed numeric details and rejects unknown or
unsafe fields. Categorical detail keys and values are accepted only from deterministic allowlists.
Each normalized event explicitly carries `event_scope`: `player` preserves actor/target roles,
`squad` represents a collective squad action, and `match` represents a match-level fact. It is not a
model stage. The legacy `MemoryPack` models remain unchanged for v1.0 and v1.1 compatibility; v2 uses
separate composed request models rather than inheriting their review and scaffold semantics.

## V2 eligible windows, compact AI draft, and deterministic enrichment

The deterministic backend builds bounded chronological windows from consent-safe canonical events.
Each offered window carries consent-safe roles, facts, context, media capabilities, and mission
capabilities behind bounded references. The AI may choose one offered window; it may not choose an
arbitrary event subset from the complete match or author authoritative control values.

One live provider call returns an internal compact draft containing:

- one offered window reference and a supported narrative framing;
- title, notification teaser, summary, and why the memory matters now;
- one distinct perspective, including the supplied player ID, for every eligible player role;
- one offered mission candidate, reunion mission title/text, and one objective description; and
- compact references identifying which supplied facts and mission capabilities support each
  authored section.

The compact draft intentionally omits authoritative match/event ID lists, complete
`GroundedClaim` objects, media objects, mission recipe, objective IDs, assignments, required flags,
source event IDs, verification rules, roster records, delivery state, and Studio trace. The
deterministic backend resolves the selected window and compact references, supplements only literal
player/action/location/match-value terms with conservative candidate evidence from the selected
window, then derives those fields from normalized telemetry, consent state, media mappings, and the
mission capability catalogue. This lexical enrichment is not a unique semantic mapping: expanded
claims and prose still pass the complete deterministic validators. Categorical and ordinary numeric
detail claims require lexical detection of the typed value plus an associated field/action cue;
survival wording may use positive squad-alive telemetry without restating its numeric count.
Expansion keeps lexically selected candidate event evidence for each section, or one
explicitly cited fallback event when no event evidence is inferred, so a model cannot inflate the
final claim set by citing every event. The backend orders the
provider-supplied perspectives by the trusted roster and validates that their IDs equal the exact
eligible set; it does not restore or synthesize missing perspectives. The full proposal is validated
before the backend creates a delivery record, safe trace, and unchanged public
`InterpretDeliveryResultV2`.

The provider payload makes perspective permissions explicit. Each eligible player receives their
direct actor/target event IDs. A collective event is also offered for that perspective only when its
`event_scope` is `squad` and an allowlisted membership count proves that the entire submitted roster
participated. The model may describe such an event as "we" or "the squad", never as the narrator's
personal action. Match-scoped facts support match language, not individual action claims.
Privacy-safe aliases remain first-class grounding labels; hiding an original identity does not let
the model attach unsupported actions or observations to its replacement label.

Each mission candidate is paired with a deterministic `authoring_scope`: permitted intent,
permitted player IDs, and permitted count. The provider can select one candidate and phrase one
objective within that scope; recipe, assignment, source events, and verification rule remain
backend-owned. Conservative lexical validation compares mission action language,
metric-associated target counts, operator language, named players, and known unoffered gameplay
condition terms with that selected capability. It is a bounded guardrail rather than a universal
semantic proof for unrestricted prose.
Both mission text and objective text must express the selected deterministic requirement. The
delivered memory type is also checked against the selected episode and squad history, including the
rule that a `first` memory cannot coexist with prior session history.
Numbers attached to other nouns, such as a squadmate count, are not treated as the mission metric's
target. Optional media is selected only when `media.event_ids` is a subset of the chosen
episode's event IDs; a media reference need not cover the whole episode. Collective- or
match-scoped media requires media consent from the full submitted roster because its actor/target
fields do not enumerate everyone potentially visible.

The consent-safe provider context includes previous session timestamps, days since the full squad,
recent rematch count, active players, available modes, and reunion eligibility. Secret-like input is
rejected and unsafe/instruction-like social context is filtered before the provider boundary.

Compact references are not a shortcut around grounding. A reference that is unknown, incompatible
with the selected window, attached to the wrong section or player, or insufficient for an authored
fact fails enrichment or validation. Full claims and all player-facing prose still pass the same
role, chronology, value, context, privacy, media, and mission checks. Validation also checks direct
player-action-target wording against one supported telemetry tuple, preventing literal enrichment or
separate cited events from being used to recombine a false role assignment. A single bounded correction
call may use stable issue codes plus allowlisted section IDs; rejected generated prose and validator
messages are never returned to the model. If correction still fails, v2 rejects it and exposes no
generated prose.

Reducing duplicated IDs and backend-owned controls in the provider schema should make structured
output easier for a live model to produce consistently. It does not weaken validation because the
removed fields are derived from deterministic sources rather than trusted from the model. Automated
compact-draft/enrichment checks and one configured 120B live smoke run now pass. The expected
reliability improvement relative to the former schema still requires a larger controlled sample.

## V1.1 compatibility: historical discovery

Historical discovery is deterministic. It is cheap enough to run across every submitted pack,
repeatable in tests, and explainable to a player reviewing a candidate. It does not call OpenAI.

Each eligible candidate receives four normalized score components:

| Component | Weight | What it measures |
|---|---:|---|
| Evidence strength | 35% | Specific events and connected gameplay patterns |
| Human signals | 30% | Captions, tags, saves, reactions, and review signals |
| Squad specificity | 20% | How strongly the episode depends on this squad and its roles |
| Reactivation relevance | 15% | Whether resurfacing the memory is timely in the current context |

The four stored components are already weighted. Their sum is both `score_breakdown.total` and
`score`, and the `0.45` eligibility threshold is applied to that unpenalized base score. Duplicate
match IDs then collapse to their strongest candidate. During iterative top-candidate selection, a
repeated memory type receives a `0.08` penalty, reported separately as `diversity_penalty`, and
`ranking_score` becomes `max(score - diversity_penalty, 0)`. Diversity can change selection order,
but cannot make a candidate eligible or ineligible. Remaining ties resolve by newest `played_at`,
then stable `pack_id` order. Offset-aware timestamps are preferred; a legacy timestamp without an
offset is interpreted as UTC so ordering does not depend on the backend host's timezone.

Hard filters run before ranking. A pack cannot surface when it has no grounded events, fewer than
two opted-in squad members, its target player opted out, its source is disputed, or its meaning was
dismissed. Requiring two consenting participants preserves the product's shared-memory premise and
prevents generation of a nominally social quest for one person.

A history request is one consent and identity boundary. Its 1-50 packs must share one squad ID,
target player, roster ID set, and current per-member consent snapshot, and every pack ID must be
unique. New endpoints require explicit consent even for a legacy v1.0 inner pack. This avoids
combining historical snapshots that disagree about who currently permits resurfacing.

## Evidence and privacy boundary

In v2, only a consent-safe ledger and eligible windows may reach the provider. When an event is
needed for factual continuity, an opted-out actor or target may remain only as a request-scoped
anonymous role; their raw ID and display name never cross the privacy boundary. Social content
authored by an opted-out player is excluded. Anonymous roles do not receive a perspective, media
identity, invitation, or mission assignment, and they do not count toward the minimum eligible
participants required for a shared memory.

The current v1.1 evidence compiler remains a compatibility boundary with its own stable aliasing
rules. V2 uses request-scoped aliases and recursively checks the complete outbound model payload
for private identity terms before interpretation.

Before a prompt is assembled:

- Opted-out identities become stable anonymous labels within the request.
- Opted-out players receive no perspective and cannot own a quest objective.
- An important shared event may remain only in anonymized form.
- Opaque pack, squad, match, and event IDs are rejected if they contain an opted-out identity.
- Unknown IDs in typed owners, assignees, and evidence references are rejected.

The validator checks generated facts against this ledger. A valid event ID alone is not enough: its
type, ownership, assignment, and quest verification shape must agree with the source event.
Conservative lexical rules also reject selected unsupported names, locations, numbers, actions,
relationships, emotions, and motives. These rules catch known failure patterns; they are not a
general proof that arbitrary natural language entails only ledger facts. Interpretive language
therefore remains reviewable and must not be presented as measured telemetry.

## V1.1 compatibility: split human trust

One confirmation flag cannot express two different questions. Schema v1.1 separates:

| State | Values | Question answered |
|---|---|---|
| `source_status` | `unreviewed`, `verified`, `disputed` | Did these events actually happen as described? |
| `meaning_status` | `unreviewed`, `confirmed`, `dismissed` | Does this moment matter to the player? |

On the new `/v1/memories/generate` route, AI generation starts only for `verified` + `confirmed`
inputs. Unreviewed candidates remain useful for discovery but cannot become re-engagement content.
Disputed or dismissed candidates are filtered. Legacy v1.0 `confirmed: true` maps to both positive
states; `false` maps to both unreviewed states, with the conversion recorded in response metadata.
The deprecated v1.0 `/discover` route intentionally preserves its older behavior and may create
reviewable drafts before confirmation; new clients must not use it as the Phase 2 trust boundary.

V2 removes the pre-generation player meaning gate. Authenticated ingestion and deterministic source
quality establish whether telemetry may be interpreted. The player then accepts or declines the
validated delivery. `not_relevant` is a relevance signal; `details_wrong` is a source-quality signal
for operations. Neither decision edits trusted telemetry or triggers automatic prompt changes.

## Stage ownership

| V2 stage | Model-capable? | Owned behavior |
|---|---:|---|
| Raw ingestion and normalization | No | Types, external-to-canonical mappings, provenance, and rejection |
| Consent and eligibility | No | Current consent, source quality, deduplication, and event-window construction |
| Compact memory draft | Yes | Choose one offered window; author player-facing interpretation, perspectives, mission wording, and bounded fact/capability references |
| Authoritative enrichment | No | Resolve the window and references; derive proposal match/event IDs, full claims, media, roster, recipe, objectives, assignments, and rules |
| Proposal validation | No | Chronology, derived claim references, roles, privacy, context, media, prose support, and mission controls |
| Delivery construction | No | After validation, create the delivery record, safe Studio trace, and public result |
| Delivery and feedback | No | Final status, exact-delivery suppression, and structured decision semantics |

“Agent” means a bounded typed stage, not an autonomous multi-agent runtime. Stages have no authority
to bypass an earlier gate or weaken a later validation rule.

## V1.1 compatibility: narrative generation on deterministic scaffolds

Schema-constrained output is not, by itself, proof that free prose is grounded. MemoryOS therefore
separates player-facing language from factual and consent controls:

- The model authors the memory title, type, and summary, while the server fixes the evidence set,
  confidence, and confirmation state.
- The model authors one message per opted-in player, while the server fixes identity, ordering, and
  player-specific evidence references.
- The model authors quest title, mission, recipe, and objective descriptions, while the server fixes
  objective IDs, assignments, requirements, source events, and verification rules.

Live prompts receive control-only scaffolds. The pipeline copies model-authored narrative fields
onto the authoritative scaffold and ignores model attempts to change control fields. Narrative then
passes deterministic privacy, evidence, action, objective-alignment, and conservative lexical
checks before it can be returned. These checks deliberately fail closed but remain prototype
guardrails rather than a proof of every implication in natural language.

V2 replaces the three narrative scaffolds with one compact draft schema, deterministic enrichment,
and structural controls. The
legacy scaffold path stays available for regression tests and explicitly labelled offline Studio
demonstrations, but it is not presented as a live v2 AI delivery.

## Provider boundary

The provider-neutral structured-generation interface remains reusable. The preferred v2 live
provider is the existing Groq GPT-OSS integration; the provider returns one compact internal draft
under a strict schema. The backend, not the provider, expands it into an authoritative proposal;
only a proposal that passes deterministic validation becomes a public delivery and safe trace.
Provider refusal, timeout, malformed output, unresolved compact references, failed enrichment, or
failed deterministic validation fails closed. V2 never substitutes deterministic narrative text
into a response labelled as live AI.

Deterministic mode remains the credential-free regression baseline and may power explicitly labelled
offline Studio demonstrations. The current v1.1 compatibility path still uses three semantic stages
with the same sanitized ledger plus the previous typed output.

```text
sanitized evidence
    |-- deterministic stage implementation --|
    `-- structured live-provider stage call --|--> compact typed draft
                                                --> deterministic proposal expansion
                                                --> deterministic validator
                                                --> public delivery + safe trace
```

The OpenAI adapter uses the Responses API with Pydantic Structured Outputs and `store=False`. The
Groq adapter uses Chat Completions with an explicit strict JSON Schema and validates the returned
JSON through the same Pydantic response model. Both use low reasoning effort, a 30-second timeout,
at most two SDK transport retries, and explicit output ceilings. Compact v2 interpretation is
capped at 2,000 output tokens on Groq and 4,000 on OpenAI. On a
direct JSON route, a provider failure is reported as a structured HTTP `503`; the
service never silently changes a live request to deterministic prose. Once an NDJSON response has
begun, the equivalent failure is a typed `error` event under HTTP `200`.

## Status and failure behavior

`POST /v2/memories/interpret-delivery` returns either a fully validated
`pending_player_decision` delivery or a rejected/provider-error result with no generated artifacts.
Rejected proposal prose is never included in a player response or Developer Studio trace; Studio may
show stable issue codes and a structural, redacted validation trace only.

`POST /v2/deliveries/{delivery_id}/decision` records `accepted` or `declined`. A decline
requires exactly `not_relevant` or `details_wrong` and suppresses that exact process-local delivery.
Authentication, durable storage, retention, deletion, and operational review are deferred
until their consent and privacy policies are approved.

The following statuses describe the current v1.1 compatibility routes:

- Invalid schemas, mixed squads, and mixed target players fail with HTTP `422`.
- Ineligible, disputed, dismissed, or validation-failing packs return `rejected`.
- A strong unreviewed candidate returns `needs_source_verification`.
- A verified but unconfirmed candidate returns `needs_meaning_confirmation`.
- Only verified, confirmed, grounded output returns `ready`.
- On direct JSON routes, provider timeouts, refusals, quota failures, and malformed structured
  output return a retryability-aware HTTP `503` response. The NDJSON adapter reports the same fields
  in an HTTP `200` error event because its headers have already been sent.

Response bodies omit `memory` and `next_chapter` when their value is `null`; an empty perspectives
list remains present. A validation failure fails closed by withholding all generated artifacts.
The NDJSON route is a snapshot adapter: after an initial event it runs the same canonical call, then
emits completed previews. It is not token streaming or a live per-stage execution trace. Its
OpenAPI response describes the discriminated schema for one NDJSON line. Client disconnects do not
reliably cancel the synchronous worker thread or an in-flight provider call, so the prototype may
continue work until completion or timeout after its response consumer has gone away.

The top-level result `status` is authoritative for readiness. `validation.passed` can also be true
when deterministic abstention succeeded or when no validation error precedes a human-review gate;
only `status == "ready"` authorizes presentation of generated artifacts as ready.

## Frontend handoff: v1.1 compatibility and canonical v2

Legacy v1.1 review tools should use `/openapi.json` or `/docs`, derive client types from that
contract, display backend scores and reasons, preserve the selected compatibility pack, apply the
review decision, and resubmit that pack for generation. They must not recompute status, consent,
ranking, or validation, and a candidate rank or ID is not a generation token. Any prototype review
persistence must use the v1.1 state semantics above. This pack-resubmission workflow is retained for
compatibility only; it is not the canonical player delivery path.

The player frontend now has one canonical consumer flow split by responsibility:

- `/` prepares and reveals the current source-verified memory, its grounded explanation, the
  current player's perspective, and one reunion proposal. It alone owns **Accept mission** and the
  two structured decline reasons.
- `/mission` receives an accepted delivery through session-only React state and owns invitation,
  synthetic rematch, deterministic mission verification, and the resulting continuation chapter.
- `/history` is a compact, read-only timeline. It shows the current session milestones plus only
  sanitized metadata from eligible past packs; it does not prepare deliveries or record decisions.

The current-memory route uses the v2 interpretation contract through same-origin server proxies.
The server normalizes synthetic raw telemetry, asks one live model for a compact draft, enriches it
with authoritative claims and mission controls, validates the complete result, and returns
`pending_player_decision`. A player can accept or decline;
`details_wrong` is a data-quality signal and `not_relevant` is a relevance signal. Neither lets the
browser rewrite telemetry. Generated types, runtime guards, and a backend snapshot test keep
FastAPI as the contract source of truth. The older discovery and split-review contracts remain only
for internal compatibility and quality workflows, not as a second player interface.

`/` proxies `/v2/memories/interpret-delivery` and
`/v2/deliveries/{delivery_id}/decision` without exposing backend credentials. `/history` remains
read-only and does not prepare a delivery or record a decision.

Developer Studio may display raw **synthetic** telemetry, deterministic normalization and window
metadata, provider/model/prompt version, evidence links from a validated proposal, validator issue
codes, final delivery status, and recorded prototype feedback. It must never display raw prompts,
the raw compact provider draft, chain-of-thought, credentials, opted-out identities, or
rejected/unvalidated proposal prose.

## Phase 3 reunion prototype

The consumer continuation lives at `/mission`. A shared client provider carries the accepted
delivery between player routes for the current browser session, so the delivery is not placed in a
URL, browser storage, or treated as durable authorization. Refreshing or directly opening the route
therefore shows an honest no-active-mission state. An accepted decision unlocks a squad invitation
simulation built only from the delivery's privacy-filtered player perspectives. Opted-out roster
members never enter the invitation model.

The prototype then evaluates a labelled synthetic rematch against the quest's existing
machine-readable `equals`, `at_least`, and `contains_all` rules. Every required objective must pass
before the UI can construct the deterministic “Story Continues” chapter. `/history` then reflects
that milestone in its session timeline. This proves the continuation state machine and verification
semantics without claiming access to live Garena telemetry. Optional post-chapter relevance
feedback is session-only and deliberately excludes the `details_wrong` source-quality reason used
during the original delivery decision.

## Deferred production boundaries

This phase does not add authentication, durable backend storage, queues, notifications, production
telemetry, regional retention enforcement, cross-request pseudonym management, or real match-result
verification. Optional v2 media references are limited to curated synthetic clip, thumbnail, or
keyframe IDs mapped deterministically to allowed event IDs. The prototype makes no automated video
understanding claim. Unknown or mismatched media mappings fail closed. Production media access,
storage, deletion, and retention require Garena data contracts and privacy review.
