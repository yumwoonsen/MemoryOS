# Phase 2B–3.4 prototype demo and test guide

## What the prototype proves

The runnable Phase 3 prototype selects a source-bounded, evidence-backed squad moment, prepares a
personal memory and mission, then lets the player accept or decline it. Match facts stay inside the
source/evidence boundary and are grounding-checked; production source authentication is deferred.
A player decline records relevance feedback, not an edit to match history. A result is described as
AI-prepared only when its provenance identifies an actual live provider. The credential-free
deterministic run is an explicitly labelled offline demonstration.

The Phase 3 continuation extends that trust loop with an explicitly synthetic moment preview,
consent-safe invitation simulation, a scripted successful game, a **Story Continues** chapter, and
session-only feedback. Its exact sequence is: mission accepted, invitations sent, invitation-ready
squad joins, game starts, game ends, mission complete. It does not send a real notification or
invitation, ingest new-match telemetry, or verify backend objective rules against a real match.

The AI-first V2.1 raw-telemetry route and public delivery flow exist. Input schema `2.0` and `2.1`
are accepted; typed interpretation results are always `2.1`. The current prompt is
`memory-interpreter-v2.6-mission-affordances`. A historical 8 August 2026 Groq 120B smoke used V2.4,
so it is not evidence for the current prompt and should not be presented as a V2.6 benchmark. The
V1.1 routes remain available as compatibility APIs.

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

1. Open `/` and explain that source-bounded synthetic telemetry and deterministic checks prepared
   the eligible evidence before the player saw it.
2. Show the prepared memory, its provenance label, personal perspective, and one selected **Next
   Chapter** from the `reunion`, `role_reversal`, or `redemption` family.
3. Accept the mission, follow the handoff to `/mission`, and show that only opted-in players are
   present in the squad-safe invitation. Point out that consented inactive invitees remain present
   as **Away**; Online/Away is display state, not invitation authority.
4. Follow the explicit script: send invitations, simulate the squad joining, start the game, wait
   for the game to end, then show mission complete and **Story Continues**. State that the successful
   outcome is scripted and no new telemetry or actual objective verification occurs.
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
   outcome, consent filtering, no more than four neutral chronological windows, sanitized dynamic
   affordances, active versus invitation-ready counts, and allowed evidence/context/media references.
3. Use the provider/model/prompt metadata and validated result to explain
   `CompactInterpretationDecisionV2`: AI either generates or abstains with
   `no_meaningful_episode`. A generated proposal selects one window, ranks offered affordances,
   selects one family/affordance with allowlisted reason codes, and authors descriptions for all
   selected objectives. Studio intentionally does not display the raw compact provider response.
4. Show deterministic expansion deriving selected match/event IDs, complete `GroundedClaim`
   records, eligible media, mission recipe, objective IDs, assignments, metrics, operators, targets,
   and source references, plus ordered/exact-set consent-safe perspectives. Then show validation,
   followed by construction of the delivery record, safe Studio trace, and resulting
   `pending_player_decision` delivery.
   If generation fails, show stable issue codes and a closed status—never the rejected proposal
   prose.
5. Accept through `POST /v2/deliveries/{delivery_id}/decision` and continue through the existing
   scripted invitation, squad-join, game-start, game-end, mission-complete, and **Story Continues**
   flow. Explicitly state that this is not post-match telemetry ingestion or real rule verification.
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
- A continuation chapter appears only after the scripted invitation/join/start/end/complete state
  sequence; this test does not claim telemetry-backed rule verification.
- Post-chapter **Hide this chapter** feedback never becomes a factual source dispute.
- `/history` never prepares a delivery or records an accept/decline decision.
- Directly opening or refreshing `/mission` does not invent durable authorization; without the
  current in-memory handoff it shows a safe no-active-mission state.
- Any saved deterministic result is a clearly labelled Studio/test sample and cannot enter or stand
  in for the canonical live `/` delivery flow.

## V2 acceptance checks

- Raw telemetry is normalized and rejected for unknown types, detail combinations, or broken
  references before the provider is called.
- `RawTelemetryBatchV2` accepts `2.0` and `2.1`; `InterpretDeliveryResultV2` is always `2.1`.
- Opted-out raw identities and opted-out-authored social content are absent from provider input,
  player output, and Studio. An event needed for factual continuity may remain only under a
  request-scoped anonymous role, which cannot receive a perspective, media identity, invitation,
  or mission assignment.
- `StoryBriefV2` contains no more than four structurally ranked, narratively neutral windows.
- The backend dynamically offers only evidence-supported members of the exact family set
  `reunion`, `role_reversal`, and `redemption`. AI returns
  `CompactInterpretationDecisionV2`: `generate`, or typed `abstain` with
  `no_meaningful_episode` and no proposal.
- For generation, AI selects exactly one offered window, ranks offered affordances, selects one as
  first, uses only its allowed reason codes, and uses only supplied evidence/capability references.
- The backend derives authoritative match/event IDs and complete claims, orders provider-supplied
  perspective IDs and validates that they exactly equal the consent-safe eligible roster, and
  derives media, mission family/recipe, the complete objective set, assignments, required flags,
  metrics, operators, targets, and source references. It never restores a missing perspective.
- Normalized facts declare `player`, `squad`, or `match` event scope. Provider perspective
  permissions contain direct-role events and only full-squad collective events whose allowlisted
  membership count proves participation by the complete submitted roster.
- Deterministic categorical allowlists constrain telemetry details. Categorical and ordinary
  numeric detail claims require lexical detection of the typed value plus an associated field/action
  cue; survival wording may use positive squad-alive telemetry without restating its numeric count.
  Conservative literal enrichment adds only candidate evidence and remains subject to all final
  tuple and prose checks.
- The provider authors one description for every backend-owned objective in the selected
  affordance; it never supplies assignments or verification controls.
- Unknown, cross-window, wrong-player, or unsupported compact references fail closed. Non-unique
  literal matches use a conservative scored candidate and remain subject to the full deterministic
  validation pass; simplifying model output does not remove that pass.
- A provider refusal, timeout, or terminal malformed/validation failure returns no partial
  player-facing artifacts. A repairable error gets at most one correction guided by stable issue
  codes and allowlisted section IDs; rejected prose and free-form validator messages are never sent
  back to the provider.
- Groq live output and deterministic offline output have unambiguous provenance. A live failure
  never silently becomes deterministic narrative; deterministic prose is only a clearly labelled
  Studio/test sample.
- Unknown or mismatched media mappings fail closed; selected media must represent only events in the
  selected episode (`media.event_ids` is a subset of selected event IDs), and only curated synthetic
  media is claimed.
- Developer Studio exposes safe structural observability and issue codes, but no raw prompt,
  raw compact provider draft, chain-of-thought, key, opted-out identity, provider exception text,
  or rejected proposal prose. It shows sanitized affordances, ranked/selected family and reason
  codes, validation/correction, active versus invitation-ready counts, and abstention.
- Inactive but consented players remain invitation-ready; `online` and `away` are player-facing
  presentation only.
- The player browser receives request-scoped `recipient_ref` and `objective_ref` values, one
  current-player perspective, and one selected **Next Chapter**, but no raw player/event/backend
  objective IDs, claims, verification rules, source references, or Studio trace.
- The post-accept demo is explicitly scripted through invitations, squad joins, game start, game
  end, and mission complete. It performs no new-match ingestion and no real objective verification.
- The decision route accepts only `accepted` or a decline with exactly `not_relevant` or
  `details_wrong`; exact-delivery suppression and the operations signal are verified.
- Authentication, durable persistence, real notifications/invitations, new-match ingestion, and
  post-match verification remain deferred until ownership, consent, retention, deletion, and
  operations-access policies are approved.

## Verification

The commands below verify the deterministic and rendered boundaries but do not by themselves prove
live-provider behavior. For each release, also start the backend with an explicitly configured Groq
or OpenAI provider and submit `backend/data/raw_telemetry_v2.json` to
`POST /v2/memories/interpret-delivery`. Record whether the compact decision parsed, whether it
generated or abstained, whether correction was
used, whether every reference resolved, and whether the enriched public delivery passed final
validation. The 8 August 2026 Groq 120B smoke used the older V2.4 prompt. It is historical only and
is not evidence for `memory-interpreter-v2.6-mission-affordances`; rerun a labelled V2.6 matrix
before making current provider or prompt claims.

```powershell
$env:MEMORYOS_PROVIDER = "deterministic"
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m backend.evaluate --provider deterministic
.\.venv\Scripts\python.exe -m backend.evaluate_v2

cd frontend
npm ci
npm audit --audit-level=high
npm run generate:api-types
npm run typecheck
npm run lint
npm test
```
