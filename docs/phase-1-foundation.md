# Phase 1 foundation: the first MemoryOS vertical slice

> This document records the original single-pack milestone. The current historical-discovery and
> split-review architecture is described in [Architecture](architecture.md) and [API](api.md).

## Milestone summary

This initial repository establishes the AI Memory Engine underneath **Garena Next Chapter**. It
proves a complete backend-first flow from a realistic synthetic Memory Pack to a grounded memory,
distinct player perspectives, a squad-specific quest, and a deterministic validation report.

The milestone is intentionally about output quality rather than interface polish. A future frontend
can consume the versioned API after the memory and quest behavior is credible.

## What was delivered

- Strict Pydantic contracts for gameplay, social, human, and current-context signals.
- A staged pipeline for discovery, personalized perspectives, quest generation, and validation.
- A credential-free deterministic implementation for repeatable demos and tests.
- An optional OpenAI Structured Outputs adapter behind the same contracts.
- Human confirmation states that distinguish ready memories from reviewable candidates.
- Safe abstention when the input does not support meaningful personalization.
- Evidence checks that reject invented event identifiers and unsupported relationship claims.
- FastAPI, command-line, and VS Code entry points.
- Synthetic chaos, comeback, and insufficient-evidence fixtures.
- Architecture, API, decision, evaluation, roadmap, and contribution documentation.

## Why the architecture is hybrid

Language models are useful for interpreting episodes, selecting narrative focus, writing personal
recalls, and remixing a memory into a new mission. They should not decide whether evidence exists,
whether a player consented, whether a verification condition was met, or whether an unsupported
relationship claim is acceptable.

MemoryOS therefore places generative stages inside deterministic boundaries. The same validator
runs after local rules and live model calls, making provider comparisons possible without changing
the API or weakening the product guardrails.

## Golden-path story

“Worst Plan, Best Night” combines four grounded events: Amir calls for retreat, Mei revives Lee, Jo
drives the squad away from Clock Tower, and the team survives into the final zone. The saved caption
and reactions establish human meaning. Each teammate receives a different recall, and the generated
quest returns the original squad to Clock Tower while reversing the rescue role.

The result passes all four Phase 1 quality dimensions: specificity, evidence grounding, perspective
distinctness, and quest connection.

## Safety cases

The repository also demonstrates two non-happy paths:

- On the original v1.0 compatibility pipeline, a strong comeback becomes
  `needs_human_confirmation` and its generated artifacts remain reviewable rather than ready.
- A routine low-signal elimination becomes `rejected` without manufactured nostalgia.

These cases are core product behavior, not fallback error handling.

The Phase 2 `/v1/memories/generate` route is intentionally stricter: it makes no model call and
returns no generated artifacts until source verification and meaning confirmation are both
positive. The legacy behavior above remains only for migration compatibility.

## Verification snapshot

At the time of the initial commit:

- 9 tests pass.
- Ruff linting passes.
- Ruff formatting passes.
- The CLI returns a fully validated `ready` result for the golden fixture.
- The live `/health` endpoint responds successfully in deterministic mode.

## Deliberately deferred from Phase 1

At Phase 1 completion, the milestone did not include a frontend, database, authentication,
notifications, real Free Fire integration, media understanding, production deployment, or
new-match continuation. Later prototype phases added the frontend and a synthetic continuation
flow; production persistence, authentication, notifications, ingestion, and media understanding
remain deferred.

## Original next milestone (historical)

The original next milestone was a human review loop for discovered memories. Phase 2A delivered the
historical ranking and split review-state compatibility backend. The AI-first v2 pivot subsequently
moved source verification upstream and made the player's accept/decline choice a relevance decision;
durable feedback persistence remains deferred.
