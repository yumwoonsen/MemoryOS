# MemoryOS Review Studio

The player-facing review experience for MemoryOS. It connects to the Phase 1 FastAPI memory engine,
shows the evidence behind a candidate, previews each opted-in player's perspective, and lets a
reviewer confirm, edit, or dismiss the memory.

## Local development

```powershell
pnpm install
pnpm run dev
```

By default the studio calls `http://127.0.0.1:8000`. If the backend is unavailable, it remains
usable with the versioned golden-path fixture. Copy `.env.example` to `.env.local` to point the UI
at a different backend.

Review decisions are persisted in the deployed site's D1 database. The local development binding
uses the same schema from `db/schema.ts`.

## Checks

```powershell
pnpm run build
pnpm run lint
```
