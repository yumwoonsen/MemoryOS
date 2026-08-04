# MemoryOS Review Studio

The player-facing review experience for MemoryOS. Its Live Memory Lab streams visible progress as
the credential-free local engine discovers a memory from grounded events, writes distinct player
perspectives, creates a follow-up quest, and validates its references. A reviewer can then confirm,
edit, or dismiss it.

## Local development

From the repository root, start both the local engine and the site with no API key:

```powershell
.\start-local.ps1
```

The site opens at `http://localhost:3000` and sends generation requests only to the local FastAPI
engine at `http://127.0.0.1:8000`. Press Ctrl+C in the terminal to stop both processes.

Review decisions are persisted in the deployed site's D1 database. The local development binding
uses the same schema from `db/schema.ts`.

## Checks

```powershell
pnpm run build
pnpm run lint
```
