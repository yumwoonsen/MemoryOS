# MemoryOS Review Studio

The player-facing review experience for MemoryOS. Its Live Memory Lab streams visible progress as
OpenAI discovers a memory from grounded events, writes distinct player perspectives, creates a
follow-up quest, and validates its references. A reviewer can then confirm, edit, or dismiss it.

## Local development

```powershell
pnpm install
pnpm run dev
```

Copy `.env.example` to `.env.local`, add a server-only `OPENAI_API_KEY`, and optionally choose a
model with `OPENAI_MODEL`. Without a key, the versioned golden-path fixture remains reviewable.
Never expose the API key through a `NEXT_PUBLIC_` environment variable.

Review decisions are persisted in the deployed site's D1 database. The local development binding
uses the same schema from `db/schema.ts`.

## Checks

```powershell
pnpm run build
pnpm run lint
```
