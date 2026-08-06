# Next Chapter frontend

The Phase 2 MemoryOS experience turns the backend’s three synthetic Memory Packs into a story-first
review flow. It calls the local FastAPI service when available and falls back to matching sample
results so the interface remains demonstrable when deployed on its own.

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
