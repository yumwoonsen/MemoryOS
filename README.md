# Garena Next Chapter / MemoryOS

MemoryOS is the AI memory engine behind **Garena Next Chapter**. It turns lightweight historical
match data into reviewable squad memories, distinct teammate perspectives, and a grounded quest
that gives the squad a specific reason to return.

The Phase 1/2 backend answers two questions:

1. Which moments in a player's history are most likely to be worth remembering?
2. After a player verifies and confirms one, can AI turn it into a safe, evidence-backed next
   chapter?

> [!IMPORTANT]
> This is a hackathon prototype built with synthetic Memory Pack fixtures. It does not connect to
> Free Fire production services, contain player data, or claim access to Garena's internal APIs.

## System boundary

MemoryOS deliberately separates decisions that must be reliable from language that benefits from
AI:

| Deterministic code owns | AI may propose |
|---|---|
| Evidence compilation and ranking | Bounded memory title and type |
| Eligibility, consent, and redaction | Quest title, mission, and recipe |
| Review state and final status | Composition from allowed quest templates |
| Closed factual clauses plus final validation | No factual control state |

Humans make two independent decisions: whether the source accurately describes the match and
whether the moment is meaningful. AI is never the authority for either decision.

## What the backend supports

- Strict, versioned Memory Pack and response contracts
- Historical discovery across up to 50 packs with an explainable deterministic top-three ranking
- Duplicate suppression and candidate diversity
- Separate source-verification and meaning-confirmation states
- Consent-aware evidence compilation and stable anonymization of opted-out players
- Bounded discovery, perspective, and quest generation stages
- Deterministic evidence-reference, assignment, lexical-claim, distinctness, and safe-abstention
  checks
- A credential-free deterministic provider plus an optional OpenAI Structured Outputs provider
- FastAPI, command-line, pytest, and generated OpenAPI entry points

## Quick start

Requirements: Python 3.11 or newer.

```powershell
cd memoryos-build
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
$env:MEMORYOS_PROVIDER = "deterministic"
pytest
```

Run the API in deterministic mode (the safe default, made explicit here so a local `.env` cannot
silently select the paid provider):

```powershell
$env:MEMORYOS_PROVIDER = "deterministic"
uvicorn backend.main:app --reload
```

Open `http://127.0.0.1:8000/docs` for the live request and response schemas.

The original single-pack CLI remains useful for a credential-free golden-path check:

```powershell
python -m backend.run_memory backend/data/funny_memory.json --provider deterministic
```

The main API flow is:

```text
POST /v1/memories/discover-history
    -> player verifies and confirms one candidate
POST /v1/memories/generate
    -> validated memory + perspectives + quest
```

Each history request uses one target, squad, roster, and current consent snapshot. The base `score`
is the weighted component sum and controls the `0.45` eligibility gate; the separate
`ranking_score` may subtract the `0.08` repeated-type diversity penalty during top-candidate
selection. Clients consume both values from OpenAPI instead of recomputing them.

`POST /v1/memories/discover` remains available as the deprecated v1.0 single-pack compatibility
route. Unlike the new review-gated route, it preserves the legacy behavior in which an unconfirmed
pack can still produce reviewable draft artifacts. New clients must use `/generate` for the split
source/meaning gate.

The streaming route is an NDJSON snapshot view of the same completed generation call, not a second
AI implementation, token stream, or real-time per-stage trace.

Only the top-level `status: "ready"` marks artifacts as ready. The nested `validation.passed` field
can also be true for a safe abstention or a candidate waiting for human review, so clients must not
use it as a readiness shortcut.

## Run in VS Code

Open the repository folder and accept the recommended Python extension. The workspace selects
`.venv\Scripts\python.exe` and enables pytest discovery automatically. In **Run and Debug**:

- **MemoryOS: Run API** starts FastAPI in deterministic mode.
- **MemoryOS: Run API (Live OpenAI)** explicitly selects the paid provider and reads the key from
  the local environment or `.env`.
- **MemoryOS: Run Golden Path** processes the original confirmed fixture in the terminal.

## Optional live AI mode

Deterministic mode is intentionally the default: it is repeatable, free, and cannot spend API
credits accidentally. To opt in to live generation:

```powershell
Copy-Item .env.example .env
```

Add a server-side `OPENAI_API_KEY` to `.env`, then launch with an explicit provider selection:

```powershell
$env:MEMORYOS_PROVIDER = "openai"
uvicorn backend.main:app --reload
```

Never commit `.env` or expose the key to browser code. The model receives a sanitized evidence
ledger plus the preceding typed stage output. It produces typed semantic outputs; deterministic
validation still decides whether the result may be returned as ready. Validation combines exact
schema/reference checks with conservative lexical heuristics, so human source and meaning review
remain essential. The default live model is documented in the official
[gpt-5.6-luna model reference](https://developers.openai.com/api/docs/models/gpt-5.6-luna).

Core gameplay clauses are closed server renderings in both modes: memory summary/evidence,
player-specific perspective messages/references, and quest-objective descriptions must match their
deterministic templates exactly. The model retains bounded framing fields such as memory title and
type and quest title, mission, and recipe; those still pass privacy, evidence, action, and lexical
checks.

See [the API guide](docs/api.md) for configuration and request shapes.

## Player prototype

The integrated `frontend/` is the teammate-built, mobile-first Phase 1 player experience. It reveals
one grounded memory, shows evidence and the current player's perspective, then previews the Next
Chapter quest. It currently uses the deprecated single-pack `/v1/memories/discover` adapter, which
the backend keeps during migration. The historical candidate picker and split verification flow are
the next frontend integration milestone.

```powershell
cd frontend
npm ci
npm run dev
```

Run the deterministic backend from the repository root before opening the frontend. When the
backend is unavailable, only the exact committed demo fixture can use the hosted sample; modified
or unknown packs fail closed.

## Verify changes

Run the same checks as CI:

```powershell
$env:MEMORYOS_PROVIDER = "deterministic"
ruff check .
ruff format --check .
pytest

cd frontend
npm ci
npm audit --audit-level=high
npm run typecheck
npm run lint
npm test
```

CI tests Python 3.11 and 3.13. The test suite includes the OpenAPI contract smoke test, ranking and
compatibility cases, privacy failures, provider failures, and the original Phase 1 golden paths.

Run the synthetic fixture-regression harness without credentials:

```powershell
python -m backend.evaluate
```

Live evaluation is deliberately opt-in and may incur API cost:

```powershell
python -m backend.evaluate --provider openai
```

## Repository map

```text
memoryos-build/
|-- backend/
|   |-- agents/          # Bounded semantic and validation stages
|   |-- data/            # Synthetic Memory Pack fixtures
|   |-- models/          # Pydantic API and pipeline contracts
|   |-- prompts/         # Version-controlled model behavior
|   |-- services/        # Evidence, ranking, and provider boundaries
|   |-- main.py          # FastAPI app and OpenAPI contract
|   `-- pipeline.py      # Canonical orchestration
|-- docs/                # Product, architecture, API, decisions, and evaluation
|-- frontend/            # Integrated Phase 1 player demo and backend compatibility adapter
`-- tests/               # Contract, ranking, grounding, privacy, and pipeline tests
```

## Documentation

| Document | Purpose |
|---|---|
| [Product context](docs/product_context.md) | Product thesis, experience loop, and guardrails |
| [Architecture](docs/architecture.md) | Historical ranking, AI boundary, trust, and privacy |
| [API reference](docs/api.md) | Endpoints, status flow, configuration, and handoff |
| [Decision log](docs/decisions.md) | Accepted architecture decisions |
| [Evaluation](docs/evaluation.md) | Quality metrics and regression workflow |
| [Roadmap](docs/roadmap.md) | Integration path and production questions |
| [Shank integration review](docs/shank-integration-review.md) | Merge choices, compatibility, and next work |
| [Phase 2B demo and test guide](docs/prototype-demo-test.md) | Local historical-review walkthrough and acceptance checks |
| [Phase 1 foundation](docs/phase-1-foundation.md) | Original single-memory vertical slice |

## Known limitations

- Fixtures represent data Garena could plausibly assemble; they are not a published Garena schema.
- There is no backend persistence, authentication, notification delivery, or live telemetry feed.
- Deterministic ranking weights are prototype hypotheses and need calibration against player labels.
- The validator checks typed references and selected lexical patterns; it cannot prove that every
  possible natural-language implication is supported by telemetry.
- The evaluation report is a synthetic regression summary. Its distinctness and grounding metrics
  are exact-string/reference proxies, not human judgments of story quality.
- Stable anonymization protects generated content inside one request; production identity handling
  requires a broader privacy and retention design.
- OpenAI mode needs a valid server-side key and separate cost, latency, and output-quality testing.
- Disconnecting an NDJSON client does not reliably cancel its synchronous worker or an in-flight
  provider request; work may continue until completion or timeout.
- The integrated frontend still carries hand-written v1.0 compatibility types. Replace them with
  OpenAPI-generated v1.1 types when implementing the historical review flow.

## License

MemoryOS is available under the [MIT License](LICENSE). Copyright (c) 2026 Ryan Neo Liang Zhi.
