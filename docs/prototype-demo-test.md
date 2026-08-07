# Phase 2B prototype demo and test guide

## What the prototype proves

MemoryOS selects a trusted, evidence-backed squad moment, uses AI to prepare a personal memory and
mission, then lets the player accept or decline it. Match facts are verified upstream from trusted
telemetry; a player decline records relevance feedback, not an edit to match history.

Notifications, clips, invitations, and decline-feedback collection are Phase 3 work. They are not
required to prove the Phase 2B trust loop.

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
3. Accept the mission and show the mission-ready confirmation.
4. Restart, decline, and demonstrate both **Not relevant to me** and **Details are wrong** feedback.

## Acceptance checks

- Delivery comes only from `/v1/memories/prepare-delivery`; it returns
  `pending_player_decision`, never falsely marks a player as confirmed, and only trusted source
  packs may produce content.
- A response that is malformed, rejected, or unavailable never displays a memory, perspective, or
  mission.
- Opted-out people are not shown as perspectives or quest assignees; a supplied redaction notice is
  displayed safely.
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
