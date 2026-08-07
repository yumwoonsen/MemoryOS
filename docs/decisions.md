# Architecture decision log

## ADR-001 — Backend before frontend

**Status:** accepted

The backend proves ranking, grounding, personalization, and quest connection before frontend
integration. The concurrent UI consumes the resulting versioned API instead of defining product
truth independently.

## ADR-002 — Python, FastAPI, and Pydantic

**Status:** accepted

Python supports fast AI iteration; FastAPI exposes the prototype with minimal ceremony; Pydantic is
the shared contract for request validation, model Structured Outputs, and response validation.

## ADR-003 — Lightweight Memory Packs, not full telemetry

**Status:** accepted

The prototype uses key events, squad context, and human signals that a live-service game could
reasonably assemble. It does not require every movement or bullet event and does not pretend that an
undocumented Garena API exists.

## ADR-004 — Human confirmation is part of the product

**Status:** accepted

AI cannot reliably infer that a match felt funny or meaningful. Humans independently decide whether
the source is accurate and whether they want the memory resurfaced.

## ADR-005 — Hybrid intelligence

**Status:** accepted

Player-facing memory framing, personalized perspectives, and quest wording may use a model.
Eligibility, selected evidence, identity references, consent, review state, quest verification
controls, validation, and final status remain deterministic.

## ADR-006 — One bounded model call per semantic stage

**Status:** accepted for Phase 1/2

Discovery, perspectives, and quest generation have separate prompts and schemas. This improves
traceability and evaluation. Calls may be consolidated later only if latency and cost data justify
it without reducing quality or grounding.

## ADR-007 — Deterministic provider as the default

**Status:** accepted

The repository must run without credentials and produce stable test results. Live AI is explicit,
shares the same contracts, and still ends in deterministic validation.

## ADR-008 — No backend persistence in Phase 1/2

**Status:** accepted

JSON fixtures are sufficient for historical discovery. The frontend may persist prototype review
feedback, but backend database and feedback-learning design should wait until schemas have been
tested with users.

Until that persistence exists, the client keeps the complete selected pack, applies the review
decision, and resubmits it. A discovery rank, candidate ID, or score does not represent stored
review state.

## ADR-009 — Deterministic historical ranking

**Status:** accepted

Ranking up to 50 packs must be explainable, repeatable, and inexpensive. Evidence, human signals,
squad specificity, and reactivation context use fixed weights and an explicit threshold. Historical
ranking itself never calls AI, and a model cannot alter either eligibility or candidate order.

`/v1/memories/generate` accepts one complete pack and recomputes deterministic eligibility and
review state before any model call. It does not require proof that the pack previously appeared in a
top-candidate response. A caller could therefore submit every eligible pack separately; production
admission control, authentication, and rate limiting remain separate responsibilities.

The weighted component sum is the eligibility `score`. The repeated-type diversity penalty affects
only the iterative `ranking_score`; it never changes the threshold decision. A request also uses one
squad, target, roster, and current consent snapshot so ranking cannot combine conflicting identity
or consent state.

## ADR-010 — Source truth and personal meaning are separate

**Status:** accepted

Schema v1.1 replaces the overloaded confirmation meaning with `source_status` and
`meaning_status`. A player may verify that an event happened without wanting it resurfaced. Only a
verified and confirmed memory may enter the new v1.1 `/generate` path; disputed and dismissed
memories are filtered. The deprecated v1.0 `/discover` adapter intentionally remains an exception
during migration and can produce reviewable drafts for `confirmed: false` packs.

## ADR-011 — Python owns the canonical contract

**Status:** accepted

FastAPI, Pydantic, and generated OpenAPI define request, response, consent, ranking, and status
semantics. The frontend consumes that interface instead of maintaining a separate Worker pipeline.
This prevents two runtimes from disagreeing about whether a memory is safe or ready.

## ADR-012 — Privacy is enforced before prompting

**Status:** accepted

The evidence compiler anonymizes opted-out participants before data reaches a generative stage.
Opted-out players receive no perspective and cannot be assigned quest objectives. Post-generation
validation remains a second defense, not the primary privacy mechanism. Model stages receive the
sanitized ledger and the preceding typed output rather than the original Memory Pack.

Validation combines exact type, evidence, identity, and quest-rule checks with conservative lexical
heuristics for known hallucination patterns. It fails closed, but it is not a proof system for every
possible implication in natural language; source and meaning review remain human decisions.

The model authors all player-facing prose, but not its factual control plane. Memory evidence,
player-specific references, safe identities, quest assignments, required flags, source IDs, and
verification rules come from deterministic scaffolds. Model-authored confidence and confirmation
are overwritten from trusted pipeline state. The merged narrative must still pass the deterministic
checks above.
