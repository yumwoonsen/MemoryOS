# Roadmap

## Phase 1 — Memory Engine foundation (complete)

- Versioned Memory Pack and result contracts
- Discovery, perspective, quest, and validation stages
- Deterministic and structured-model providers
- Golden fixtures and quality tests

## Phase 2A — Historical discovery backend (complete for prototype)

- Deterministic ranking across up to 50 packs
- Split source-verification and meaning-confirmation states
- Consent-aware evidence compilation and redaction
- Selected-memory generation and strengthened validation
- OpenAPI contract and regression evaluation

## Phase 2B — Human review and clickable experience (in progress)

Completed in the integrated teammate slice and Phase 2B review flow:

- Mobile-first reveal flow for one grounded legacy memory
- Evidence-first story, current-player perspective, and quest preview
- Server-side backend proxy with an exact-fixture hosted fallback
- Runtime result guards and rendered HTML regression tests
- Historical top-candidate picker using `/v1/memories/discover-history`
- Separate source verify/dispute and meaning confirm/dismiss actions
- Evidence-first source review and ready-only player reveal
- Consent redaction presentation and opted-in perspective controls
- OpenAPI-derived client types and API contract tests

The `/history` player flow now implements candidate selection plus separate source and meaning
review. It intentionally keeps choices only for the active session; durable feedback is deferred.

## Phase 3 — Reunion and continuation loop

- In-app Memory Inbox or notification delivery with a curated moment clip
- Squad invitation and acceptance simulation
- Deterministic mission verification from a new match result
- “Story Continues” chapter generation
- Memory timeline and feedback capture
- Optional dismissal feedback, kept separate from factual source disputes

## Production questions to resolve later

- Which Free Fire event and social signals are genuinely available internally?
- What consent, retention, and regional privacy rules apply to squad memories?
- What model, latency, and cost envelope is acceptable at Garena scale?
- Which constrained-generation, semantic-grounding, moderation, and human-audit layers should
  replace the prototype's lexical validation heuristics?
- How should player edits and confirmations update future memory ranking?
- What experiment design can isolate dormant-squad reactivation impact?
- How should pseudonyms, deletions, and consent changes propagate across stored squad memories?
