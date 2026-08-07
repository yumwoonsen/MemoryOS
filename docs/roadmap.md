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

## Phase 3 — Explainable AI delivery and feedback loop (planned)

Phase 3 makes the system understandable to collaborators and judges. It will show what trusted
telemetry and deterministic safeguards selected, what AI contributed to the presentation, and how
player decisions are safely incorporated into later, reviewed improvements. See
[`phase-3-explainable-delivery-plan.md`](phase-3-explainable-delivery-plan.md) for the shared
implementation brief.

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

- Build one shared, consent-safe dashboard for collaborator development, testing, and the judge
  demo; it is not a second player product.
- Add a redacted delivery-trace contract keyed by `delivery_id`: trusted events and squad
  statistics; deterministic eligibility, consent, source-quality, and selection reasons;
  AI-prepared presentation; allowed evidence references; validation result; provider/model/prompt
  version; and the delivery decision.
- Label deterministic selection and AI storytelling as separate responsibilities. The dashboard
  exposes an auditable decision trace, not raw prompts, secrets, chain-of-thought, opted-out
  identities, or unvalidated output.
- Add a feedback/evaluation view for accept and decline results by memory type, source-quality
  state, and model/prompt version, including safe provider and malformed-response states.

### 3.3 — Complete the consumer decision path

- Keep the player journey binary: one AI-prepared memory and relevant clip, then **Accept mission**
  or **Decline**.
- On **Accept mission**, show the squad-safe mission-start state and hand off to the invitation /
  continuation experience.
- On **Decline**, capture exactly one structured reason: **Not relevant to me** or **Details are
  wrong**; suppress that exact memory for the player and show a respectful completion state.
- Treat **Not relevant to me** as a relevance signal for aggregate offline evaluation. Treat
  **Details are wrong** as a source-quality flag in the dashboard; do not resurface that exact pack
  to the player until it is investigated, and never let the client rewrite trusted telemetry.
- Persist safe decision metadata with model/prompt version in authenticated, durable,
  privacy-reviewed storage. Improve prompts or models only through aggregate, reproducible offline
  evaluation and explicit promotion; no live prompt rewriting or per-decline factual learning.

### 3.4 — Reunion and continuation experience

- Deliver a clip-first notification: a curated synthetic clip mapped to the selected verified
  match/event, followed by the AI reminder and reunion mission.
- Deterministically validate the clip mapping before presentation. Unknown or mismatched clips fail
  closed; live game-video ingestion, automatic clipping, and AI video understanding remain future
  work.
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
- What authenticated, retention-limited feedback store is appropriate before real player data is
  accepted?
- What experiment design can isolate dormant-squad reactivation impact?
- How should pseudonyms, deletions, and consent changes propagate across stored squad memories?
