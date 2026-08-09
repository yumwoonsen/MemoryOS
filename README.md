# Garena Next Chapter / MemoryOS

MemoryOS is the AI memory engine behind **Garena Next Chapter**. The current v1.1 compatibility
prototype turns synthetic historical Memory Packs into reviewable squad memories, distinct
teammate perspectives, and a grounded quest. The implemented v2 contract instead starts from raw
telemetry, constructs a consent-safe Story Brief with several feasible mission affordances, asks
AI to select one continuation and author its memory framing and short story bridge, then accepts it
only after privacy, evidence, and mission validation. The backend compiles the exact objective copy
from the selected deterministic capability.

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
| Allowed identities, facts, current-context signals, media mappings, and mission affordances | Ranking and selection of one offered affordance plus player-facing language |
| Selected match/event IDs, complete `GroundedClaim` records, perspective roster, media, mission family, assignments, exact objective descriptions, objective rules, and invitation eligibility | Title, summary, current relevance, perspectives, mission title, and a short story bridge within the supplied facts and capabilities |
| Proposal validation, correction eligibility, delivery status, suppression, and final decision state | No telemetry, consent, source-quality, or final-status authority |

Source quality is resolved upstream. The player decides whether a validated delivery is relevant;
**Details are wrong** creates an operations signal and never edits trusted telemetry in the client.

## AI-first v2 implementation

```text
raw telemetry
    -> deterministic normalization, consent filtering, and eligible windows
    -> typed Story Brief and feasible, verifiable reunion / role-reversal / redemption affordances
    -> AI comparison of episode x mission options and one compact typed draft, or a grounded abstention
    -> deterministic proposal/control enrichment and exact objective-copy compilation
    -> deterministic grounding, privacy, media, and mission validation
    -> delivery/trace construction, not-generated abstention, or a closed rejection
```

The compact draft is an internal provider contract, not a weaker public contract. AI chooses one
offered window and writes memory language, perspectives, a mission title, a short story bridge, and
small fact/capability references. The backend
resolves those references and derives the authoritative match and event IDs, complete grounded
claims, the ordered and validated perspective list, media mapping, and the selected affordance's
complete objective set, exact objective descriptions, and controls. The story bridge remains in the
public `next_chapter.mission` field, while the backend-compiled steps remain in
`next_chapter.objectives`. The backend does not create a missing perspective: the provider must return every eligible
player ID exactly once. After the full proposal validates, the pipeline creates the delivery record,
safe Studio trace, and public result. Unresolvable or unsupported references fail closed. The public
v2 response remains the
fully enriched `InterpretDeliveryResultV2`.

The provider receives the consent-safe `previous_session_at`, `days_since_full_squad`,
`recent_rematch_count`, active-player, available-mode, and reunion-eligibility signals. Secret-like
or instruction-unsafe social text is removed or rejected before provider use. Privacy-safe display
labels such as `Player 3` remain groundable identities even though the original identity is hidden.

Normalized event facts carry an explicit `event_scope`: `player` events retain actor/target roles,
`squad` events describe the squad collectively, and `match` events describe match-level facts.
Provider perspective permissions list each eligible player's direct-role events and only those
squad events whose allowlisted membership count proves that the full submitted roster participated.
Categorical telemetry details pass deterministic value allowlists. Categorical and ordinary numeric
detail claims require lexical detection of both the value and an associated field/action cue;
survival wording may instead use a positive squad-alive detail without restating its numeric count.
Literal player, action, location,
or match terms may add conservative candidate evidence from the selected episode; they do not create
a unique semantic proof and the complete tuple, prose, and claim validators still run. To keep the
claim set bounded, expansion retains lexically selected candidate events for a section, or at most
one cited fallback event when no event evidence is inferred.

Each mission affordance groups two to five ordered backend-owned objective capabilities and an `authoring_scope`
containing only its permitted intent, player IDs, and targets. At the provider boundary, neutral
windows, feasible affordances, and their nested typed objectives receive request-scoped `W#`, `A#`,
and `O#` references. The provider ranks the `A#` choices and writes the selected mission title and
short story bridge; each `A#` is an episode-and-mission pair, so the first ranked `A#` selects both the
continuation and its linked episode without a redundant selected-window output field. The backend
then resolves those short references to the authoritative window, family, recipe, assignments, source
evidence, exact objective descriptions, and verification rules. Deterministic composition keeps the
primary family mechanic, adds only compatible capabilities from the same neutral window, and never
pads a chapter with fabricated actions. The player still receives one clear Next Chapter rather than an
internal candidate menu.
The ordered grammar is explicit: an invitation-safe prerequisite, one primary family mechanic,
zero to two compatible support or optional bonus mechanics, and match completion. Bonus objectives
are the only optional steps and never decide whether the chapter completes. Current grounded bonus
capabilities include the first tactical signal and a full-squad vehicle escape within 60 seconds;
both require their exact source events in the selected window.
The model is instructed to choose the strongest direct evidence-linked continuation, not the first
serialized candidate. Role reversal can continue a rescue episode, redemption can continue a
repeated near miss, return to place can call back to a named rescue site, landing rendezvous can
continue a complete invited-squad drop, and duo assist can continue a proven assist-to-elimination
pair. Reunion remains the general fallback when no more coherent specific continuation is
supported. `A#` order and reference number, and the number of nested `O#`
objectives, are deliberately not preference signals. This is AI selection guidance rather than a
deterministic family ranking: final validation checks grounding, consent, feasibility, and rule
consistency without automatically preferring one mission family. The provider's story bridge does
not have to restate every backend-owned rule. The backend compiles each selected `O#` into its exact
public objective description instead.
Conservative lexical mission checks reject tested conflicting actions, operators,
metric-associated target counts, player names, and known unoffered gameplay conditions; unrelated
participant counts are not mistaken for the mission target. These bounded checks are not a universal
semantic proof for unrestricted prose.
The provider Story Brief also includes neutral evidence scopes that bind canonical event roles and
exact categorical terms to consent-safe evidence IDs. Typed mission capabilities explain only what
the game can verify; neither the scopes nor the capabilities pre-author a memory or its story. The
backend uses those capabilities to compile objective copy, and deterministic reference resolution
plus the existing claim, role, privacy, and mission validators remain authoritative.
When one bounded correction is allowed, the request reuses the unchanged provider-visible `W#`,
`A#`, and `O#` catalogue. Safe issue sections and request-scoped references never expose canonical
backend selection IDs. Rejected prose and free-form validator messages are still withheld.
Optional media remains backend-selected only when every event represented by that media reference
is inside the selected episode (`media.event_ids` is a subset of the selected event IDs). Media for
collective or match-scoped events requires media consent from the complete submitted roster because
actor/target fields cannot identify everyone potentially visible.

Validation checks the AI-authored story bridge for contradictory targets or operators, unoffered
mechanics, unsupported facts, privacy violations, and unsafe content; it no longer requires that
bridge to restate every backend-owned rule. The backend-compiled objective descriptions carry those
requirements exactly. Delivered memory categories are also checked against episode/history signals
(for example, `first` cannot be used when prior sessions exist). Secret-like, unsafe, or unsupported
observation language fails closed before delivery.

This smaller structured output is intended to reduce malformed or internally inconsistent model
responses without moving authority from deterministic code to AI. A historical telemetry-only
smoke run passed on 8 August 2026 with Groq `openai/gpt-oss-120b` and the former
`memory-interpreter-v2.4-grounded-controls` prompt. The current v2.1 mission-affordance contract uses
`memory-interpreter-v2.13-perspective-safe-variation` from `memory_interpreter_v2_13.txt`; the historical
result is not evidence for the newer prompt or for the default 20B model.

Two controlled historical live smokes on 9 August 2026 used Gemini `gemini-3.6-flash` and
`memory-interpreter-v2.10.1-category-safe-perspectives`. The synthetic rescue selected `role_reversal` and
completed in 4.74 seconds; repeated near misses selected `redemption` and completed in 4.81 seconds.
Both passed validation without correction. These are two successful paths, not a complete provider
reliability, reunion-counterfactual, or abstention matrix, and not evidence for the active V2.12
prompt.

The general v2 API boundary is `POST /v2/memories/interpret-delivery`. The player prototype uses
`POST /v2/memories/interpret-varied-delivery`, followed by
`POST /v2/deliveries/{delivery_id}/decision`. A live provider failure, refusal, malformed output,
or failed correction returns no player-facing proposal. A validated AI abstention instead returns
`not_generated` with no artifacts. Gemini `gemini-3.6-flash` is the preferred hosted prototype v2
provider. Groq GPT-OSS and OpenAI remain available as alternatives. Deterministic narrative
generation remains useful for tests, but the current Studio checkpoint produces no deterministic
narrative and is not a live-AI fallback.

The player route holds one coherent synthetic squad history on the server. For each new chapter it
generates a private nonce, removes the last two successfully delivered mission families when other
grounded choices exist, and gives Gemini at most three distinct specialized affordances to compare.
Gemini still selects the episode-and-mission pair and authors its narrative; deterministic
preparation, objective compilation, and validation remain authoritative. `reunion` is used only
when no specialized family is available. A rerun consumes provider quota and resets the prior
player-flow state before generation.

Developer Studio now compares five backend-owned, versioned scenarios: rescue to role reversal,
landing together to landing rendezvous, an assist-to-elimination pair to duo assist, repeated near
misses to redemption, and ordinary sparse telemetry to a possible abstention. It loads their safe
descriptors through `GET /v2/studio/scenarios`, inspects deterministic preparation
through `POST /v2/studio/scenarios/{scenario_id}/prepare`, and starts a live interpretation through
`POST /v2/studio/scenarios/{scenario_id}/interpret`. Preparation performs normalization, privacy
filtering, neutral-window construction, and affordance compilation with **zero provider calls**.
The expected status/family labels come from the offline evaluation manifest and never enter raw
telemetry, the Story Brief, or provider input.

Studio does not cache or deduplicate completed interpretations. Its browser lock prevents a second
concurrent click, but every new live-run click starts a fresh pipeline execution and may use two
provider calls when the one permitted correction is needed. A reviewed `saved_live_replay` may be
shown only in Studio when its scenario ID, fixture SHA-256, fixture revision, provider, model,
prompt, result schema, and capture time all match. The committed replay registry is currently
empty. There is no generic rescue or deterministic narrative fallback. The player path accepts
only `live_ai_validated` content.

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
- A credential-free deterministic provider plus Gemini, Groq GPT-OSS, and OpenAI live providers
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
silently select an external provider):

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
- **MemoryOS: Run API (Live Gemini 3.6 Flash)** selects the preferred hosted prototype provider and
  reads `GEMINI_API_KEY` from the local environment or `.env`.
- **MemoryOS: Run API (Live Groq GPT-OSS 20B)** selects the Groq alternative and reads
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

Add the following server-side Gemini settings to `.env`:

```dotenv
MEMORYOS_PROVIDER=gemini
GEMINI_API_KEY=your_server_side_key
GEMINI_MODEL=gemini-3.6-flash
GEMINI_V2_MAX_OUTPUT_TOKENS=4000
```

Then launch the API:

```powershell
$env:MEMORYOS_PROVIDER = "gemini"
uvicorn backend.main:app --reload
```

Never commit `.env` or expose the key to browser code. The model receives a sanitized evidence
ledger plus the preceding typed stage output. It produces typed semantic outputs; deterministic
validation still decides whether the result may be returned as ready. Validation combines exact
schema/reference checks with conservative lexical heuristics, so human source and meaning review
remain essential. Gemini uses Google's official OpenAI-compatible endpoint, low reasoning, no
explicit temperature, a 60-second per-attempt timeout, no hidden SDK transport retries, and a strict
schema with provider-unsupported hints removed. MemoryOS may make one explicit semantic correction;
the same-origin proxy allows 130 seconds for that bounded path. Returned JSON still has to pass the
complete Pydantic and deterministic validators.
Use only synthetic, non-sensitive telemetry for free-tier prototype testing; this configuration is
not approval to process production player data. Groq remains available with
`MEMORYOS_PROVIDER=groq` and `GROQ_API_KEY`; OpenAI remains available with
`MEMORYOS_PROVIDER=openai` and `OPENAI_API_KEY`.

For a deployed server-side frontend proxy, `MEMORYOS_PROXY_TOKEN` can additionally protect
data-bearing routes, including Studio trace retrieval, through the `X-MemoryOS-Proxy-Token`
header. Leave it unset for local development, and never expose it in client-side JavaScript.

In the implemented v1.1 live mode, three bounded model stages write player-facing narrative onto
deterministic scaffolds. The v2 route replaces those stages with one compact typed draft followed by
deterministic enrichment, while deterministic code still owns eligibility, consent, evidence
constraints, match/event IDs, complete claims, media, roster, assignments, verification rules,
delivery/trace construction, and final status. A failed v2 live call will fail closed instead of
silently substituting deterministic narrative.

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
configured live provider and fails closed when it is unavailable. A delivered player memory is
labelled **AI-prepared · evidence-checked** and is accepted only when its provenance is
`live_ai_validated`. Studio preparation remains available without a provider, while a compatible
saved live replay is Studio-only and cannot enter the player delivery route.

The hosted Vinext/Cloudflare site does not run the Python service. Live hosted AI therefore needs a
separately deployed HTTPS FastAPI backend. For the preferred prototype path, store `GEMINI_API_KEY`,
`GEMINI_MODEL=gemini-3.6-flash`, `GEMINI_V2_MAX_OUTPUT_TOKENS=4000`,
`MEMORYOS_PROVIDER=gemini`, and the optional `MEMORYOS_PROXY_TOKEN` on that backend; configure only
`MEMORYOS_API_URL` and the matching proxy token in the frontend server environment. Never place a
provider key in the browser bundle.

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
python -m backend.evaluate --provider gemini
python -m backend.evaluate --provider groq
python -m backend.evaluate --provider openai

# Current v2.1 labelled manifest; explicitly permits hosted API use
python -m backend.evaluate_v2 --provider gemini --allow-live-api
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
| [V2.1 mission affordances](docs/mission-affordances-v2.1.md) | Dynamic mission selection and the scripted prototype-game boundary |
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
- The invitation, lobby, game, and successful completion sequence is a labelled static simulation.
  Live post-match telemetry ingestion and objective verification are deferred. Its completion
  chapter title is selected deterministically by mission family—**Together Again**,
  **The Favour Returned**, or **The Comeback Complete**—with a collision-safe alternative when it
  would repeat the accepted mission title.
- Developer Studio does not cache or deduplicate completed live interpretations. Every explicit
  live-run click may use an initial provider call plus one correction call. The UI only blocks
  duplicate concurrent clicks.
- The saved-replay mechanism is Studio-only, requires exact scenario and live-run provenance, and
  currently has no committed replay artifacts. It is not a generic rescue fallback.
- Deterministic ranking weights are prototype hypotheses and need calibration against player labels.
- The validator checks typed references and selected lexical patterns; it cannot prove that every
  possible natural-language implication is supported by telemetry.
- The evaluation report is a synthetic regression summary. Its distinctness and grounding metrics
  are exact-string/reference proxies, not human judgments of story quality.
- Stable anonymization protects generated content inside one request; production identity handling
  requires a broader privacy and retention design.
- Live Gemini, Groq, or OpenAI mode needs a valid server-side key and separate latency and
  output-quality testing. Gemini free-tier prototype runs must use synthetic, non-sensitive data.
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
