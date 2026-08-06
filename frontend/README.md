# Next Chapter frontend

The Phase 2 MemoryOS experience turns the backend’s three synthetic Memory Packs into a story-first
review flow. It calls the local FastAPI service when available and falls back to matching sample
results so the interface remains demonstrable when deployed on its own.

The interface mirrors the backend guardrails: gameplay evidence and opted-in identities enter in
blue, canonical transformation appears in mint, and validated output appears in teal. White is the
main canvas and charcoal is used for accessible text throughout.

The UI also exposes the strengthened contract:

- eventless, weak, or consent-insufficient packs are safely skipped;
- AI may propose structure, but factual wording is rebuilt from verified Memory Pack fields;
- every opted-in player receives exactly one evidence-linked perspective;
- every quest objective displays its machine-checkable rule and source event IDs; and
- backend failures are normalized into stable JSON errors before reaching the browser.

## Run locally

Start the FastAPI service from the repository root:

```powershell
python -m uvicorn backend.main:app --reload
```

Then start the frontend in a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`. The header reports whether the response came from the live local
engine or safe sample mode.

## Quality checks

```powershell
npm run lint
npm test
```

The review controls are intentionally session-only. Confirmation persistence, authentication, and
real invitation delivery remain outside this prototype.
