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

## Phase 2B — Consumer memory delivery (in progress)

Completed in the integrated teammate slice and Phase 2B delivery flow:

- Mobile-first reveal flow for one grounded legacy memory
- Evidence-first story, current-player perspective, and quest preview
- Server-side backend proxy with an exact-fixture hosted fallback
- Runtime result guards and rendered HTML regression tests
- Consumer-facing AI Memory Inbox that prepares one source-verified moment
- Accept-mission and structured-decline decisions, without asking players to audit telemetry
- Ready-only player reveal and consent-safe redaction presentation
- OpenAPI-derived client types and API contract tests

The `/history` player flow is now an AI Memory Inbox: it prepares one source-verified memory and
mission, then records accept, not-relevant, or details-wrong feedback in process-local prototype
storage. Source verification remains an upstream telemetry/data-quality responsibility; player
feedback expresses relevance and is never used to rewrite match facts.

## Phase 3 — Backend validation, dashboard, and reunion loop (next)

### 3.1 — Test and select a no-cost/open-source model

- Define a provider evaluation harness using the existing synthetic Memory Pack fixtures and
  deterministic validators as the safety baseline.
- Evaluate locally runnable or free-tier open-source models for structured title, perspective, and
  mission generation; compare format adherence, grounding, latency, hardware needs, and failure
  rate against the current deterministic provider and optional OpenAI demo provider.
- Add the selected provider behind the existing provider boundary rather than changing ranking,
  consent, redaction, or validation ownership.
- Document the model licence, hosting/runtime requirements, prompt format, known failure modes,
  and fallback behaviour. A model is eligible only if malformed or ungrounded output fails closed.

### 3.2 — Collaborator dashboard and backend visibility

- Connect the backend to the teammate-built dashboard through server-side API routes and the
  versioned OpenAPI contract.
- Provide a safe, demo-oriented operations view of the pipeline: submitted synthetic pack,
  eligibility outcome, source-quality state, selected delivery, generated artifacts, validation
  outcome, provider used, and recorded delivery decision.
- Keep player-facing data minimal: redact opted-out identities and do not expose raw prompts,
  secrets, internal scores, or unvalidated model output.
- Add dashboard integration checks for loading, API/provider errors, malformed responses, and
  empty states so judges can see both the successful path and the safety gates.

### 3.3 — Complete the consumer decision path

- Adjust the player frontend around the final delivery contract: one AI-prepared memory, its
  grounded explanation, and a clear reunion mission.
- On **Accept mission**, show the squad-safe mission-start state and hand off to the invitation /
  continuation experience.
- On **Decline**, capture exactly one structured reason: **Not relevant to me** or **Details are
  wrong**; suppress the mission and show a respectful completion state. “Details are wrong” is a
  source-quality signal for operations, not a client-side correction to trusted telemetry.
- Replace the prototype in-memory decision store with authenticated, durable, privacy-reviewed
  storage only after data-retention and consent decisions are approved.

### 3.4 — Reunion and continuation experience

- In-app Memory Inbox or notification delivery with a curated moment clip
- Squad invitation and acceptance simulation
- Deterministic mission verification from a new match result
- “Story Continues” chapter generation
- Memory timeline and feedback capture
- Optional dismissal feedback, kept separate from factual source disputes

## Production questions to resolve later

- Which Free Fire event and social signals are genuinely available internally?
- What consent, retention, and regional privacy rules apply to squad memories?
- Which open-source model and hosting path meets the required quality, latency, licence, and
  operational-cost envelope at Garena scale?
- Which constrained-generation, semantic-grounding, moderation, and human-audit layers should
  replace the prototype's lexical validation heuristics?
- How should player edits and confirmations update future memory ranking?
- What experiment design can isolate dormant-squad reactivation impact?
- How should pseudonyms, deletions, and consent changes propagate across stored squad memories?
