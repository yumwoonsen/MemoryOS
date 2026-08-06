# MemoryOS player prototype

This frontend is the compact, mobile-first player view for the latest MemoryOS prototype. It keeps
one focused Free Fire Battle Royale example so the end-to-end idea is easy to understand without
turning the player screen into an internal dashboard.

The experience moves through four clear states:

1. an unrevealed squad memory;
2. a short loading transition;
3. the shared gist, chronological evidence, and the current player's perspective; and
4. a grounded “Next Chapter” challenge with a safe preview dialog.

The player never sees internal validation scores, rule IDs, model metadata, or Studio controls.
Those checks still run behind the interface: results are bound to the submitted Memory Pack,
evidence must reference real match events, and every opted-in player must receive exactly one
grounded perspective. Review, rejected, malformed, or unavailable results do not reveal a story.

The custom Bermuda map and clock-tower town artwork live in `public/art` as optimized WebPs. The
dedicated MemoryOS Studio remains intentionally separate from this player prototype.

## Run locally

From this directory:

```powershell
npm install
npm run dev
```

Open the local URL printed by the development server. The frontend calls `/api/discover`, which
uses the local MemoryOS backend when it is available. If the backend is offline, the exact included
Battle Royale pack can use its canonical sample result; altered or unknown packs fail closed.

To run the optional backend, start it from the repository root:

```powershell
python -m uvicorn backend.main:app --reload
```

## Quality checks

```powershell
npm run typecheck
npm run lint
npm test
```

The challenge dialog is a simulation only. It does not send a real invitation or persist player
actions.
