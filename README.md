# Garena Next Chapter / MemoryOS Build

MemoryOS is the AI memory architecture underneath **Garena Next Chapter**: a prototype that turns a
specific, player-confirmed squad memory into distinct teammate perspectives and a playable mission
derived from that same history.

The Phase 1 question is deliberately narrow:

> Given a realistic Garena-style Memory Pack, can the system discover a meaningful moment, explain
> why it matters to each participant, create a connected quest, and reject claims it cannot ground?

The repository began backend-first and now includes a Phase 2 review experience for the validated
memory output. Live Free Fire integration, notification delivery, and the mission-result loop remain
deferred.

> [!IMPORTANT]
> This is a hackathon prototype built with synthetic Memory Pack fixtures. It does not connect to
> Free Fire production services, contain player data, or claim access to Garena's internal APIs.

## What works now

- Strict, versioned Memory Pack input and Memory Engine output contracts
- A five-stage pipeline: input → discovery → perspectives → quest → validation
- Three test stories: confirmed chaos, unconfirmed comeback, and insufficient evidence
- A credential-free deterministic provider for demos and tests
- An optional OpenAI Responses API adapter using Pydantic Structured Outputs
- FastAPI and command-line entry points
- Grounding, consent, distinctness, relationship-claim, and safe-abstention checks
- A story-first web demo covering ready, confirmation-required, and safely-skipped memories
- Evidence timelines, per-player perspectives, quest previews, and local review controls

## Quick start

Requirements: Python 3.11 or newer.

```powershell
cd memoryos-build
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
pytest
```

Run the confirmed golden path without an API key:

```powershell
python -m backend.run_memory backend/data/funny_memory.json
```

Run the API:

```powershell
uvicorn backend.main:app --reload
```

Then open `http://127.0.0.1:8000/docs` or send a Memory Pack to:

```text
POST /v1/memories/discover
```

Run the player-facing demo in a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Then open `http://localhost:3000`. The frontend calls the local engine when it is available and uses
matching synthetic sample results when it is not.

## Run in VS Code

Open this folder in VS Code and accept the recommended Python extension if it is not installed.
The workspace is already configured to use `.venv\Scripts\python.exe`.

From **Run and Debug**, choose either:

- **MemoryOS: Run API** — starts the FastAPI server; open `http://127.0.0.1:8000/docs`.
- **MemoryOS: Run Golden Path** — processes `backend/data/funny_memory.json` in the terminal.

VS Code's Testing panel is configured to discover the pytest suite automatically.

## Verify the project

Run the same quality gates expected before every commit:

```powershell
ruff format --check .
ruff check .
pytest
```

The Phase 1 baseline contains nine tests covering the golden path, safe abstention, human review,
evidence grounding, unsupported relationship claims, input validation, and the HTTP contract.

## Optional live AI mode

The local provider is the default so evaluation stays fast, repeatable, and free. To exercise the
model boundary, copy `.env.example` to `.env`, add a server-side API key, and set:

```dotenv
MEMORYOS_PROVIDER=openai
OPENAI_API_KEY=your_key_here
OPENAI_MODEL=gpt-5.6-luna
```

Never commit `.env` or expose the API key in a browser client. The adapter uses the Responses API
and parses each generative stage directly into its Pydantic schema. Deterministic validation always
runs afterward. See the official OpenAI guides for the
[Responses API](https://developers.openai.com/api/docs/guides/text) and
[Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs).

## Repository map

```text
memoryos-build/
├── backend/
│   ├── agents/          # Discovery, perspective, quest, validation stages
│   ├── data/            # Versioned Memory Pack fixtures
│   ├── models/          # Strict Pydantic contracts
│   ├── prompts/         # Version-controlled model behavior
│   ├── services/        # Prompt loader and OpenAI adapter
│   ├── main.py          # FastAPI app
│   ├── pipeline.py      # Five-stage orchestration
│   └── run_memory.py    # JSON-to-JSON CLI
├── docs/                # Product, architecture, decisions, and evaluation
├── frontend/            # Phase 2 review and story experience
└── tests/               # Golden path, abstention, grounding, and API tests
```

## Expected fixture outcomes

| Fixture | Why it exists | Expected status |
|---|---|---|
| `funny_memory.json` | Rich telemetry + player-confirmed caption/tags | `ready` |
| `comeback_memory.json` | Strong candidate with no human confirmation yet | `needs_human_confirmation` |
| `insufficient_memory.json` | Weak ordinary event with no positive human signal | `rejected` |

## Definition of good output

The prototype does not grade prose by how dramatic it sounds. It asks four measurable questions:

1. **Specificity:** Could another squad receive this unchanged?
2. **Evidence:** Can each factual reference be traced to an input event?
3. **Perspective:** Does each teammate receive a meaningfully different recall?
4. **Quest connection:** Does the mission continue or remix the memory itself?

## Documentation

| Document | Purpose |
|---|---|
| [Product context](docs/product_context.md) | Product thesis, experience loop, and guardrails |
| [Architecture](docs/architecture.md) | Pipeline stages, provider boundary, and failure behavior |
| [API reference](docs/api.md) | Endpoints, configuration, statuses, and examples |
| [Decision log](docs/decisions.md) | Accepted Phase 1 architecture decisions |
| [Evaluation](docs/evaluation.md) | Quality rubric and prompt evaluation workflow |
| [Roadmap](docs/roadmap.md) | Phase 2, Phase 3, and production questions |
| [Phase 1 foundation](docs/phase-1-foundation.md) | Reusable write-up for the initial repository milestone |
| [Contributing](CONTRIBUTING.md) | Development workflow and quality gates |

## Known limitations

- Memory Packs are synthetic representations of data Garena could plausibly assemble; they are not
  a published Garena schema.
- The default provider uses deterministic rules so the demo and tests run without credentials.
- OpenAI mode is implemented but requires a valid server-side API key and separate output evaluation.
- The frontend uses synthetic fixtures and keeps review decisions in the current browser session.
- There is no persistence, authentication, live telemetry, or notification delivery yet.

## License

MemoryOS is available under the [MIT License](LICENSE). Copyright © 2026 Ryan Neo Liang Zhi.
