# Architecture decision log

## ADR-001 — Backend before frontend

**Status:** accepted

Phase 1 proves memory quality, grounding, personalization, and quest connection before UI work. A
Next.js client is deferred but has a stable versioned API contract to consume later.

## ADR-002 — Python, FastAPI, and Pydantic

**Status:** accepted

Python supports fast AI iteration; FastAPI exposes the prototype with minimal ceremony; Pydantic is
the shared contract for request validation, model Structured Outputs, and response validation.

## ADR-003 — Lightweight Memory Packs, not full telemetry

**Status:** accepted

The prototype uses key events, squad context, and human signals that a live-service game could
reasonably assemble. It does not require every movement or bullet event. This demonstrates the
experience without pretending an undocumented Garena API exists.

## ADR-004 — Human confirmation is part of the product

**Status:** accepted

AI can rank likely memories but cannot reliably infer that a match felt funny or meaningful.
Unconfirmed high-signal candidates remain reviewable and cannot become re-engagement content yet.

## ADR-005 — Hybrid intelligence

**Status:** accepted

Semantic interpretation and writing may use a model. Eligibility thresholds, identity references,
evidence integrity, consent, verification rules, and safety checks remain deterministic.

## ADR-006 — One bounded model call per semantic stage

**Status:** accepted for Phase 1

Discovery, perspectives, and quest generation have separate prompts and schemas. This improves
traceability and prompt evaluation. We can consolidate calls later only if latency and cost data
justify it without reducing quality.

## ADR-007 — Deterministic provider as the default

**Status:** accepted

The repository must run without credentials and produce stable test results. The optional OpenAI
provider shares the same contracts, and deterministic validation runs after both providers.

## ADR-008 — No persistence in Phase 1

**Status:** accepted

JSON fixtures are sufficient for historical discovery. Database and feedback-learning design should
wait until the team has refined the Memory Pack and output schemas through evaluation.

