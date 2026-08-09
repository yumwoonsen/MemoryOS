# MemoryOS player prototype

This frontend is the compact, mobile-first player view for the latest MemoryOS prototype. It keeps
one focused Free Fire Battle Royale example so the end-to-end idea is easy to understand without
turning the player screen into an internal dashboard.

The experience is split into four focused routes:

- `/` — the current memory, grounded explanation, player perspective, and Accept/Decline choice;
- `/mission` — the accepted squad invitation, scripted prototype game, and continuation;
- `/history` — a read-only, privacy-safe timeline of the current session and eligible past matches;
- `/studio` — developer-facing pipeline observability.

The player story never exposes internal validation scores, rule IDs, prompts, or credentials. It
accepts only `live_ai_validated` delivery content and labels it
**AI-prepared · evidence-checked**. Deterministic runs and `saved_live_replay` artifacts are
Studio-only and cannot be projected into the player flow. A navigation link opens the separate
Developer Studio without mixing its controls into the story itself. The
checks still run behind the interface: results are bound to the consent-safe telemetry view,
evidence must reference real match events, and every opted-in player must receive exactly one
grounded perspective. Review, rejected, malformed, or unavailable results do not reveal a story.

The custom Bermuda map and clock-tower town artwork live in `public/art` as optimized WebPs. The
dedicated MemoryOS Studio remains intentionally separate from this player prototype.

## V2 implementation status

The canonical `/` route uses the AI-first v2 adapter and proxies:

- `POST /v2/memories/interpret-delivery` for raw telemetry to one fully enriched, validated public
  delivery; and
- `POST /v2/deliveries/{delivery_id}/decision` for acceptance or one structured decline reason.

The live provider's compact decision is internal to the backend. AI authors memory and perspective
language, ranks feasible mission affordances through request-scoped `A#` references, and writes the
selected mission title and short story bridge against nested typed `O#` capabilities. The first ranked affordance resolves
to its linked `W#` episode. The backend derives the selected
match/event IDs, complete grounded claims, eligible media, mission family, exact objective
descriptions, objective assignments/rules,
and the ordered proposal perspectives before validation. It validates that the provider-supplied
perspective IDs equal the exact eligible set; it does not restore a missing perspective. Only after
the complete proposal passes does the pipeline create the delivery record, safe Studio trace, and
public result. The same-origin player proxy receives that complete public result,
validates it, and
returns only the current player's perspective, verified moment summaries, one Next Chapter, and a
safe invitation roster. Raw telemetry, teammate perspective prose, consent records, compact output,
and Studio internals do not cross into the player UI.

The backend offers only evidence-supported, feasible, and verifiable `reunion`, `role_reversal`,
`redemption`, `return_to_place`, `landing_rendezvous`, and `duo_assist` options. AI compares those
episode-and-mission combinations and normally selects the
strongest direct evidence-linked continuation, then writes its title and story bridge naturally.
The backend supplies the exact player-facing steps. Reunion is the general
fallback when no more coherent specific continuation is supported. Serialized `A#` order/reference
number and nested `O#` count are not preference signals, and deterministic validation does not
impose a family priority. It checks the selected option's grounding and consent, and rejects a story
bridge that contradicts its target/operator, introduces an unoffered mechanic, asserts an unsupported
fact, or violates privacy or safety. The story bridge does not need to repeat every objective rule.

For readability, the player projection combines overlapping roster-participation and
completed-match requirements into one clear step, such as **Complete one match with the invited
squad**. The separate backend rules are unchanged and remain visible in Developer Studio.

This preserves the compact player sequence: one memory, its grounded explanation,
the current player's perspective, one clear Next Chapter, and one decision. `/history` remains a
read-only timeline rather than a second delivery or feedback surface.

## Developer Studio

Open `/studio` for the developer-facing observability workspace. Its selector is backed by exactly
five versioned backend scenarios:

- rescue evidence, expected to test `role_reversal`;
- a complete invited-squad drop, expected to test `landing_rendezvous`;
- a consent-safe assist-to-elimination pair, expected to test `duo_assist`;
- repeated near misses, expected to test `redemption`; and
- ordinary sparse telemetry, expected to test `not_generated` abstention.

The browser first loads `GET /v2/studio/scenarios`. **Prepare scenario — no AI call** invokes
`POST /v2/studio/scenarios/{scenario_id}/prepare`, which normalizes and privacy-filters the exact
registered fixture, forms neutral event windows, and compiles feasible affordances without
initializing a provider. **Run new live interpretation — uses provider quota** invokes
`POST /v2/studio/scenarios/{scenario_id}/interpret`, which sends only that registered raw fixture
through the existing V2 pipeline. The manifest's expected status and mission-family labels remain
outside raw telemetry, the Story Brief, and provider input; Studio compares them with the actual
result only after a run.

The Studio distinguishes these result origins:

- **Live AI** — a configured Gemini, Groq, or OpenAI provider produced a result that passed the
  existing enrichment and validation path;
- **No player content** — the live interpreter validly abstained or the result was otherwise
  withheld; and
- **Saved live replay** — Studio displayed a reviewed live capture whose scenario ID, fixture
  SHA-256, fixture revision, provider, model, prompt version, result schema, and capture time match
  the selected scenario exactly.

`saved_live_replay` is Studio-only. Its registry is currently empty until a reviewed capture is
committed, and it cannot enter the player decision or continuation flow. A failed live run never
falls back to a generic rescue result or deterministic prose. Studio also has no completed-result
cache or request deduplication: the UI blocks concurrent duplicate clicks, but every later live-run
click starts a new pipeline execution and may use a second provider call if correction is needed.

Pipeline events are labelled as completed snapshots rather than a live token trace. When the
backend supplies them, the Studio displays safe aggregate and per-stage request counts, token
counts, latency, and configured retry limits. For v2, the safe trace may additionally show
synthetic raw telemetry, normalization and eligibility outcomes, offered window and affordance IDs, validated
evidence links, provider/model/prompt version, validator issue codes, final status, and structured
feedback. It never displays raw prompts, chain-of-thought, API keys, server environment values,
the raw compact provider draft, opted-out identities, raw provider exceptions, or rejected and
unvalidated proposal prose.

The backend's normalized evidence distinguishes `player`, `squad`, and `match` event scopes. A
perspective may use its player's direct actor/target events and only those collective squad events
whose allowlisted membership telemetry proves full-roster participation. Categorical detail values
are allowlisted. Categorical and ordinary numeric detail claims require the typed value plus an
associated field/action cue; survival wording may use positive squad-alive telemetry without
restating its numeric count. Conservative lexical enrichment adds candidate evidence rather than claiming a unique semantic
mapping; the complete tuple and prose validators still run. Mission story wording is bounded by the
selected candidate's deterministic `authoring_scope` plus conservative checks for tested conflicting
actions, quantities, operators, names, and known extra-condition terms; this is not unrestricted
semantic proof. Exact objective descriptions are backend-compiled from the selected capability.

The smaller provider schema is expected to improve structured-output reliability because the model
no longer repeats identifiers and control values already owned by the backend. This does not weaken
the player boundary or validation. The updated backend/frontend suites and one telemetry-only live
interpretation passed historically on 8 August 2026 with Groq `openai/gpt-oss-120b` and the former
v2.4 prompt. The current v2.1 mission-affordance path uses
`memory-interpreter-v2.12-richer-missions` from `memory_interpreter_v2_12.txt`; historical
V2.4 and V2.10 runs are not comparative
reliability results for the active prompt.

## Run locally

From this directory:

```powershell
npm install
npm run dev
```

Open the local URL printed by the development server. The canonical `/` player route calls the
same-origin `/api/delivery/prepare` and `/api/delivery/decision` proxies and requires the local
MemoryOS backend. It fails closed when the backend is unavailable or returns an invalid delivery.
Because authentication is deferred, the provider-consuming `/api/delivery/prepare` route accepts
only a real local-browser request: the request URL must use `localhost`, `127.0.0.1`, or `[::1]`,
its `Origin` must exactly match that URL's origin, and `Sec-Fetch-Site` must be absent or
`same-origin`. Missing-origin, hosted, and cross-site requests receive `403` before any backend or
provider call.
`/api/discover` and its exact-fixture sample fallback remain compatibility infrastructure and are
not used by the canonical player flow.

The Studio uses `/api/studio/health`, `/api/studio/scenarios`,
`/api/studio/scenarios/prepare`, and `/api/studio/scenarios/interpret`. During local development,
those routes connect to `http://127.0.0.1:8000`. Catalog and deterministic preparation remain
available without provider quota, including in a configured hosted Studio. Fresh
`/api/studio/scenarios/interpret` runs use the same strict local-browser gate as player delivery;
hosted live interpretation remains disabled until authentication and rate limiting are implemented.
In a hosted environment, `MEMORYOS_API_URL` can connect the zero-provider inspection routes. If the public backend is
protected with the optional proxy boundary, set
`MEMORYOS_PROXY_TOKEN` only in the frontend server environment. It is attached to server-to-server
requests and is never serialized into the browser bundle.

## Current memory and squad history

`/` is the local AI Memory Inbox. It submits the server-held synthetic raw telemetry fixture through
the `/api/delivery/prepare` proxy, receives one evidence-validated live-AI delivery with explicit
`live_ai_validated` provenance, displays **AI-prepared · evidence-checked**, then records only an
accept decision or one of two decline reasons through
`/api/delivery/decision`.
The v2 proxy preserves those semantics while binding the decision to the opaque delivery ID.
`/history` is a separate read-only view built from verified, confirmed, deduplicated safe-list data.
It performs no delivery preparation and records no player decision. Player feedback does not
rewrite telemetry.

An accepted v2 delivery starts the validated mission and hands off to the invitation flow. A
decline requires exactly `not_relevant` or `details_wrong` and suppresses that exact prototype
delivery. `details_wrong` is also an operations source-quality signal; it is not a
client-side correction or an automatic prompt/model update. The current process- and session-local
stores remain prototype-only until authentication, retention, deletion, consent, and privacy
decisions approve durable storage.

`lib/api.generated.ts` is generated from the FastAPI OpenAPI snapshot. Run
`npm run generate:api-types` after a backend schema change; pytest verifies that the snapshot has
not drifted. The legacy exact-fixture fallback remains limited to `/api/discover` and is not used
by the canonical player routes.

## Phase 3 Next Chapter continuation

After an accepted `/` delivery, layout-scoped in-memory state hands the validated delivery to
`/mission`. The player sees a consent-safe mission start and a backend-authorized invitation roster.
Inactive but consented original squadmates remain eligible and move from Invited to Joined during
the simulation. Once the complete roster joins, the app runs a short, clearly labelled static
prototype game and shows a successful outcome matching the selected mission family. The primary
deterministic completed-chapter titles are **Together Again**, **The Favour Returned**,
**The Comeback Complete**, **Back Where It Began**, **Same Drop, Same Squad**, and
**The Setup and the Finish** for reunion, role reversal, redemption, return to place, landing
rendezvous, and duo assist, respectively. A collision-safe alternative is used when a title would
repeat the accepted mission. **Story Continues** and optional chapter feedback unlock afterward.

This Phase 3 slice remains intentionally ephemeral. The accepted handoff is not placed in a URL,
browser storage, or durable store, so a refresh or direct `/mission` visit correctly shows no active
mission. It sends no real invitation, reads or verifies no live Garena match result, and does not persist
chapter feedback while authentication, retention, consent, and privacy policy are unresolved.

Any moment clip, thumbnail, or keyframe shown by this prototype is a curated synthetic asset with a
deterministic event mapping. It is eligible only when all events represented by the media reference
belong to the selected episode; it need not represent every selected event. MemoryOS does not
currently inspect or understand gameplay video.

To inspect deterministic Studio preparation without spending provider quota, start the backend
from the repository root in deterministic mode:

```powershell
$env:MEMORYOS_PROVIDER = "deterministic"
python -m uvicorn backend.main:app --reload
```

This mode supports the scenario catalog and **Prepare scenario — no AI call**. A fresh Studio
interpretation, like the canonical player route, requires a configured live provider; deterministic
mode does not generate replacement Studio prose.

The canonical player route intentionally refuses deterministic narrative. To test the player flow
through the preferred hosted prototype provider, start the backend with
`MEMORYOS_PROVIDER=gemini`, a server-side `GEMINI_API_KEY`,
`GEMINI_MODEL=gemini-3.6-flash`, and `GEMINI_V2_MAX_OUTPUT_TOKENS=4000`. Gemini uses Google's
official OpenAI-compatible endpoint with low reasoning, no explicit temperature, a 60-second
per-attempt timeout, no hidden SDK retries, and a strict schema with provider-unsupported hints
removed. The frontend proxy waits up to 130 seconds for the initial request plus at most one
explicit semantic correction. Returned JSON still must pass
the original Pydantic and deterministic validators, and failures return no partial player delivery.
Use only synthetic, non-sensitive telemetry for free-tier testing. Groq and OpenAI remain available
through the configurations in the root README.

## Quality checks

```powershell
npm run typecheck
npm run lint
npm test
npm audit --audit-level=high
```

The challenge, invitation, rematch, and continuation are simulations only. They do not send a real
invitation or persist player actions.
