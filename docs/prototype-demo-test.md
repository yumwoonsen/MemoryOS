# Phase 2B–3.4 prototype demo and test guide

## What the prototype proves

MemoryOS selects a trusted, evidence-backed squad moment, uses AI to prepare a personal memory and
mission, then lets the player accept or decline it. Match facts are verified upstream from trusted
telemetry; a player decline records relevance feedback, not an edit to match history.

The Phase 3 continuation extends that trust loop with an explicitly synthetic moment preview,
opted-in invitation simulation, deterministic rematch verification, a “Story Continues” chapter,
and session-only feedback. It does not claim to send a real notification or consume live telemetry.

## Run the local demo

From the repository root, start the credential-free backend:

```powershell
$env:MEMORYOS_PROVIDER = "deterministic"
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload
```

In a second terminal:

```powershell
cd frontend
npm run dev
```

Open the printed local URL and select **Review your squad history**. The legacy `/` screen remains
available as the Phase 1 compatibility demo; `/history` is the AI Memory Inbox and requires the
local backend. Its browser calls are relative delivery API routes, never localhost.

## Presenter walkthrough

1. Open the AI Memory Inbox and explain that trusted telemetry and deterministic checks selected the
   moment before the player saw it.
2. Show the AI-prepared memory, personal perspective, and new mission proposal.
3. Accept the mission, continue to the squad-safe invitation, and show that only opted-in players
   are present.
4. Simulate squad acceptance and the new match, then show all required objectives being verified
   before **Story Continues** appears.
5. Show the memory timeline and record optional chapter relevance feedback.
6. Restart, decline, and demonstrate both **Not relevant to me** and **Details are wrong** feedback,
   including their different completion copy.
7. Use **Back to player memory** to leave the inbox without relying on the MemoryOS logo.

## Acceptance checks

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
- Post-chapter “Not for me” feedback never becomes a factual source dispute.
- The hosted legacy fallback is limited to the original exact fixture and is not evidence that the
  Phase 2B history flow is running.

## Verification

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
