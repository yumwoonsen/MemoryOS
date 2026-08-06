# Phase 2B prototype demo and test guide

## What the prototype proves

MemoryOS deterministically surfaces a few evidence-backed squad moments, then asks the player two
separate questions: whether the match events are true and whether the moment matters. Only a
verified and kept moment becomes a grounded memory and Next Chapter.

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
available as the Phase 1 compatibility demo; `/history` is the Phase 2B flow and requires the local
backend. Its browser calls are relative `/api/history` and `/api/generate` routes, never localhost.

## Presenter walkthrough

1. Start **Review squad memories** and explain that the backend ranks evidence and squad context,
   not a player's feelings.
2. Choose a candidate, point out its rank reasons and any consent redaction notice.
3. Confirm the chronological source events only if they happened. Demonstrate that **Dispute** stops
   the journey without generating a memory.
4. Confirm whether the verified moment is worth keeping. Demonstrate that **Dismiss** also stops the
   journey without generating content.
5. Keep one moment to reveal the evidence-backed memory, personal perspective, and Next Chapter.

## Acceptance checks

- Candidate previews come only from `/v1/memories/discover-history`; the client retains the full
  fixture pack only to submit the chosen pack to `/v1/memories/generate`.
- Meaning review cannot appear before source verification, and generation cannot start before both
  positive decisions.
- A response that is malformed, rejected, review-gated, or unavailable never displays a memory,
  perspective, or quest.
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
