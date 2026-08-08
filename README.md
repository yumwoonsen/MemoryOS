# Garena Next Chapter / MemoryOS

MemoryOS is the AI memory engine behind **Garena Next Chapter**. The current v1.1 compatibility
prototype turns synthetic historical Memory Packs into reviewable squad memories, distinct
teammate perspectives, and a grounded quest. The implemented v2 contract instead starts from raw
telemetry, asks AI for one complete Memory Proposal, and accepts it only after deterministic
privacy, evidence, and mission validation.

The project answers two questions:

1. Which moments in a player's history are most likely to be worth remembering?
2. Can AI turn one eligible episode into a safe, evidence-backed next chapter without becoming the
   authority for telemetry, consent, or mission verification?

> [!IMPORTANT]
> This is a hackathon prototype built with synthetic fixtures. It does not connect to
> Free Fire production services, contain player data, or claim access to Garena's internal APIs.

## System boundary

The v2 path deliberately separates decisions that must be reliable from the creative proposal
that benefits from AI:

| Deterministic code owns | AI proposes |
|---|---|
| Raw-input normalization, source-quality gates, consent, and eligible event windows | Selection of one offered chronological event window |
| Allowed identities, facts, current-context signals, and media mappings | One typed `MemoryProposal`: title, summary, relevance, perspectives, and mission prose |
| Evidence references, exact perspective roster, assignments, required flags, and verification rules | Narrative framing within the supplied facts and controls |
| Proposal validation, correction eligibility, delivery status, suppression, and final decision state | No telemetry, consent, source-quality, or final-status authority |

Source quality is resolved upstream. The player decides whether a validated delivery is relevant;
**Details are wrong** creates an operations signal and never edits trusted telemetry in the client.

## AI-first v2 implementation

```text
raw telemetry
    -> deterministic normalization, consent filtering, and eligible windows
    -> one typed AI MemoryProposal
    -> deterministic grounding, privacy, media, and mission validation
    -> pending player decision or a closed rejection
```

The v2 API boundary is `POST /v2/memories/interpret-delivery`, followed by
`POST /v2/deliveries/{delivery_id}/decision`. A live provider failure, refusal, malformed output,
or failed correction returns no player-facing proposal. Groq GPT-OSS is the preferred live v2
provider. Deterministic narrative generation remains useful for tests and explicitly labelled
offline Studio demonstrations, but it is not a live-AI fallback.

The implemented v1.0/v1.1 endpoints remain available as compatibility surfaces alongside the
separate v2 raw-telemetry DTO, proposal validator, API routes, and frontend adapter. V2 does not
inherit the composed `MemoryPackV11` input contract.

## What the current v1.1 backend supports

- Strict, versioned Memory Pack and response contracts
- Historical discovery across up to 50 packs with an explainable deterministic top-three ranking
- Duplicate suppression and candidate diversity
- Separate source-verification and meaning-confirmation states
- Consent-aware evidence compilation and stable anonymization of opted-out players
- Bounded discovery, perspective, and quest generation stages
- Deterministic evidence-reference, assignment, lexical-claim, distinctness, and safe-abstention
  checks
- A credential-free deterministic provider plus Groq GPT-OSS and OpenAI live providers
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

The current v1.1 compatibility flow is:

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
- **MemoryOS: Run API (Live Groq GPT-OSS 20B)** selects the recommended live provider and reads
  `GROQ_API_KEY` from the local environment or `.env`.
- **MemoryOS: Run API (Live OpenAI)** explicitly selects the paid provider and reads the key from
  the local environment or `.env`.
- **MemoryOS: Run Golden Path** processes the original confirmed fixture in the terminal.

## Optional live AI mode for the current v1.1 pipeline

Deterministic mode is intentionally the default: it is repeatable, free, and cannot spend API
credits accidentally. To opt in to live generation:

```powershell
Copy-Item .env.example .env
```

Add a server-side `GROQ_API_KEY` to `.env`, then launch the recommended free-tier provider:

```powershell
$env:MEMORYOS_PROVIDER = "groq"
uvicorn backend.main:app --reload
```

Never commit `.env` or expose the key to browser code. The model receives a sanitized evidence
ledger plus the preceding typed stage output. It produces typed semantic outputs; deterministic
validation still decides whether the result may be returned as ready. Validation combines exact
schema/reference checks with conservative lexical heuristics, so human source and meaning review
remain essential. Groq defaults to `openai/gpt-oss-20b`; the existing OpenAI provider remains
available by selecting `MEMORYOS_PROVIDER=openai` and setting `OPENAI_API_KEY`.

For a deployed server-side frontend proxy, `MEMORYOS_PROXY_TOKEN` can additionally protect
data-bearing routes, including Studio trace retrieval, through the `X-MemoryOS-Proxy-Token`
header. Leave it unset for local development, and never expose it in client-side JavaScript.

In the implemented v1.1 live mode, three bounded model stages write player-facing narrative onto
deterministic scaffolds. The v2 route replaces those stages with one complete typed
proposal, while deterministic code still owns eligibility, consent, evidence constraints,
assignments, verification rules, and final status. A failed v2 live call will fail closed instead
of silently substituting deterministic narrative.

See [the API guide](docs/api.md) for configuration and request shapes.

## Player prototype

The integrated `frontend/` contains the mobile-first player experience, AI Memory Inbox, reunion
simulation, read-only history, and Developer Studio. The canonical `/` route uses same-origin
proxies for v2 interpretation and decisions. `/history` is a read-only timeline and never prepares
a delivery or records a decision.

```powershell
cd frontend
npm ci
npm run dev
```

Run the backend from the repository root before opening the frontend. The player route requires a
configured live provider and fails closed when it is unavailable. Deterministic interpretation is
limited to tests and the clearly labelled offline Studio sample; modified or unknown inputs do not
receive a generated fallback.

The hosted Vinext/Cloudflare site does not run the Python service. Live hosted AI therefore needs a
separately deployed HTTPS FastAPI backend. Store `GROQ_API_KEY`, `MEMORYOS_PROVIDER=groq`, and the
optional `MEMORYOS_PROXY_TOKEN` on that backend; configure only `MEMORYOS_API_URL` and the matching
proxy token in the frontend server environment. Never place the Groq key in the browser bundle.

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
python -m backend.evaluate --provider groq
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
|-- frontend/            # Integrated player, mission, history, Studio, and API proxy routes
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
| [Prototype demo and test guide](docs/prototype-demo-test.md) | Current Phase 3 walkthrough and v2 acceptance checks |
| [Phase 1 foundation](docs/phase-1-foundation.md) | Original single-memory vertical slice |

## Known limitations

- The AI-first v2 path is implemented with synthetic telemetry and prototype process-local state;
  it is not connected to Garena production telemetry, authentication, or notifications.
- Fixtures represent data Garena could plausibly assemble; they are not a published Garena schema.
- Delivery decisions are process-local, there is no player authentication or notification delivery,
  and observability is reported as completed stage snapshots rather than a live token trace.
- Deterministic ranking weights are prototype hypotheses and need calibration against player labels.
- The validator checks typed references and selected lexical patterns; it cannot prove that every
  possible natural-language implication is supported by telemetry.
- The evaluation report is a synthetic regression summary. Its distinctness and grounding metrics
  are exact-string/reference proxies, not human judgments of story quality.
- Stable anonymization protects generated content inside one request; production identity handling
  requires a broader privacy and retention design.
- Live Groq or OpenAI mode needs a valid server-side key and separate latency and output-quality
  testing.
- Disconnecting an NDJSON client does not reliably cancel its synchronous worker or an in-flight
  provider request; work may continue until completion or timeout.
- The legacy player adapter still carries hand-written v1.0 compatibility guards; the v1.1 API
  surface is generated from OpenAPI and checked for drift.
- Media is limited to curated synthetic clips, thumbnails, or keyframes with deterministic event
  mappings. The prototype performs no automated video understanding.
- Authenticated durable delivery decisions, suppression, feedback, deletion, and retention remain
  deferred until consent, privacy, and operations policies are approved.

## License

MemoryOS is available under the [MIT License](LICENSE). Copyright (c) 2026 Ryan Neo Liang Zhi.
