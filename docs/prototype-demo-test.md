# Phase 2B–3.4 prototype demo and test guide

## What the prototype proves

The runnable Phase 3 prototype selects a trusted, evidence-backed squad moment, prepares a personal
memory and mission, then lets the player accept or decline it. Match facts are verified upstream;
a player decline records relevance feedback, not an edit to match history. A result is described as
AI-prepared only when its provenance identifies an actual live provider. The credential-free
deterministic run is an explicitly labelled offline demonstration.

The Phase 3 continuation extends that trust loop with an explicitly synthetic moment preview,
opted-in invitation simulation, deterministic rematch verification, a “Story Continues” chapter,
and session-only feedback. It does not claim to send a real notification or consume live telemetry.

The AI-first v2 raw-telemetry route and public delivery flow exist. The compact internal AI-draft
refinement passed the updated automated suites and one telemetry-only live request on 8 August 2026
with Groq `openai/gpt-oss-120b`, no correction, and a fully validated pending delivery. Treat that
as an end-to-end smoke result, not a benchmark for every model. The v1.1 routes remain available as
compatibility APIs.

## Run the local demo

For Studio-only deterministic inspection, start the credential-free backend:

```powershell
$env:MEMORYOS_PROVIDER = "deterministic"
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload
```

In a second terminal:

```powershell
cd frontend
npm run dev
```

Open the printed local URL at `/studio`. Deterministic output is clearly labelled and cannot enter
the player route. To demonstrate `/`, configure `MEMORYOS_PROVIDER=groq` with `GROQ_API_KEY`, or
`MEMORYOS_PROVIDER=openai` with `OPENAI_API_KEY`, before starting the backend. Browser calls use
relative delivery API routes, never hard-coded browser-to-localhost calls. `/mission`
becomes available only after the player accepts in the same client-navigation session; direct
visits and refreshes intentionally show the unavailable-session state. `/history` is the separate,
compact privacy-safe squad timeline.

## Presenter walkthrough

1. Open `/` and explain that trusted telemetry and deterministic checks selected the moment before
   the player saw it.
2. Show the prepared memory, its provenance label, personal perspective, and new mission proposal.
3. Accept the mission, follow the handoff to `/mission`, and show that only opted-in players are
   present in the squad-safe invitation.
4. Simulate squad acceptance and the new match, then show all required objectives being verified
   before **Story Continues** appears.
5. Show the mission continuation timeline and record optional chapter relevance feedback.
6. Return to `/`, start a new session, and demonstrate both **Not relevant to me** and **Details are
   wrong** feedback, including their different completion copy.
7. Open `/history`, verify the compact list omits decision controls and private captions, then use
   the shared **Memory**, **Mission**, and **History** navigation.

Any clip, thumbnail, or keyframe in this walkthrough is a curated synthetic asset selected through
a deterministic event mapping. It demonstrates presentation only; the prototype does not inspect
or understand gameplay video.

## V2 judge walkthrough

1. Submit the telemetry-only fixture to `POST /v2/memories/interpret-delivery`; point out that it
   contains no authored caption, memory summary, mission, importance label, or player review gate.
2. In Developer Studio, show only the safe structural trace: normalization and source-quality
   outcome, consent filtering, offered chronological window IDs, and allowed evidence/context/media
   references.
3. Use the provider/model/prompt metadata and validated result to explain the internal compact-draft
   boundary: one selected window, authored memory sections, ordered perspective IDs, one mission
   candidate, one objective description, and bounded fact/capability references. Studio intentionally
   does not display the raw compact provider draft.
4. Show deterministic expansion deriving selected match/event IDs, complete `GroundedClaim`
   records, eligible media, mission recipe, objective ID/assignment/rule, the ordered and
   exact-set-validated consent-safe perspectives. Then show validation, followed by construction of
   the delivery record, safe Studio trace, and resulting `pending_player_decision` delivery.
   If generation fails, show stable issue codes and a closed status—never the rejected proposal
   prose.
5. Accept through `POST /v2/deliveries/{delivery_id}/decision` and continue through the existing
   invitation, deterministic rematch verification, and **Story Continues** flow.
6. Repeat with a decline. Demonstrate that **Not relevant to me** and **Details are wrong** both
   suppress the exact delivery, while only **Details are wrong** creates an operations
   source-quality signal. Neither path edits telemetry or automatically changes the model.

## Current v1.1 acceptance checks

- Delivery comes only from `/v1/memories/prepare-delivery`; it returns
  `pending_player_decision`, never falsely marks a player as confirmed, and only trusted source
  packs may produce content.
- A response that is malformed, rejected, or unavailable never displays a memory, perspective, or
  mission.
- Opted-out people are not shown as perspectives or quest assignees; a supplied redaction notice is
  displayed safely.
- Invitation recipients come only from privacy-filtered delivery perspectives.
- A continuation chapter cannot appear until every required rule passes against the synthetic
  rematch result.
- Post-chapter **Hide this chapter** feedback never becomes a factual source dispute.
- `/history` never prepares a delivery or records an accept/decline decision.
- Directly opening or refreshing `/mission` does not invent durable authorization; without the
  current in-memory handoff it shows a safe no-active-mission state.
- The hosted legacy fallback is limited to the original compatibility API and is not evidence that
  the canonical `/` delivery flow is running.

## V2 acceptance checks

- Raw telemetry is normalized and rejected for unknown types, detail combinations, or broken
  references before the provider is called.
- Opted-out raw identities and opted-out-authored social content are absent from provider input,
  player output, and Studio. An event needed for factual continuity may remain only under a
  request-scoped anonymous role, which cannot receive a perspective, media identity, invitation,
  or mission assignment.
- AI selects exactly one offered chronological window and uses only supplied compact fact or
  mission-capability references for authored memory, perspective, and mission sections.
- The backend derives authoritative match/event IDs and complete claims, orders provider-supplied
  perspective IDs and validates that they exactly equal the consent-safe eligible roster, and
  derives media, mission recipe, one objective ID, assignment, required flag, source event IDs, and
  machine-verification rule. It never restores a missing perspective.
- Normalized facts declare `player`, `squad`, or `match` event scope. Provider perspective
  permissions contain direct-role events and only full-squad collective events whose allowlisted
  membership count proves participation by the complete submitted roster.
- Deterministic categorical allowlists constrain telemetry details. Categorical and ordinary
  numeric detail claims require lexical detection of the typed value plus an associated field/action
  cue; survival wording may use positive squad-alive telemetry without restating its numeric count.
  Conservative literal enrichment adds only candidate evidence and remains subject to all final
  tuple and prose checks.
- The provider selects one mission candidate and writes one objective description within its
  deterministic `authoring_scope` of allowed intent, player IDs, and count.
- Unknown, cross-window, wrong-player, or unsupported compact references fail closed. Non-unique
  literal matches use a conservative scored candidate and remain subject to the full deterministic
  validation pass; simplifying model output does not remove that pass.
- A provider refusal, timeout, malformed response, or validation failure returns no proposal or
  partial player-facing artifacts. At most one correction is guided by stable issue codes and
  allowlisted section IDs; rejected prose and validator messages are never sent back to the provider.
- Groq live output and deterministic offline output have unambiguous provenance. A live failure
  never silently becomes deterministic narrative.
- Unknown or mismatched media mappings fail closed; selected media must represent only events in the
  selected episode (`media.event_ids` is a subset of selected event IDs), and only curated synthetic
  media is claimed.
- Developer Studio exposes safe structural observability and issue codes, but no raw prompt,
  raw compact provider draft, chain-of-thought, key, opted-out identity, provider exception text, or
  rejected proposal prose.
- The decision route accepts only `accepted` or a decline with exactly `not_relevant` or
  `details_wrong`; exact-delivery suppression and the operations signal are verified.
- Authenticated durable storage is not enabled until ownership, consent, retention, deletion, and
  operations-access policies are approved.

## Verification

The commands below verify the deterministic and rendered boundaries but do not by themselves prove
live-provider behavior. For each release, also start the backend with an explicitly configured Groq
or OpenAI provider and submit `backend/data/raw_telemetry_v2.json` to
`POST /v2/memories/interpret-delivery`. Record whether the draft parsed, whether correction was
used, whether every reference resolved, and whether the enriched public delivery passed final
validation. The 8 August 2026 smoke run passed with Groq `openai/gpt-oss-120b`, no correction, and
no deterministic narrative fallback; repeat it when provider, model, prompt, or contract changes.

```powershell
$env:MEMORYOS_PROVIDER = "deterministic"
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m backend.evaluate --provider deterministic

cd frontend
npm ci
npm audit --audit-level=high
npm run generate:api-types
npm run typecheck
npm run lint
npm test
```
