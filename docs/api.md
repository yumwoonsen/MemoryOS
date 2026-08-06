# API reference

The Phase 1 service exposes a small synchronous HTTP interface. FastAPI also generates interactive
OpenAPI documentation at `/docs` while the server is running.

## Start the service

```powershell
uvicorn backend.main:app --reload
```

Default base URL: `http://127.0.0.1:8000`

## `GET /health`

Confirms the service is running and identifies the active generation provider.

Example response:

```json
{
  "status": "ok",
  "phase": "1",
  "provider": "deterministic",
  "model": "rules-v1"
}
```

## `POST /v1/memories/discover`

Runs the complete input → discovery → perspectives → quest → validation pipeline.

The request body must match `MemoryPack` in `backend/models/schemas.py`. The easiest development
request uses one of the versioned fixtures:

```powershell
$body = Get-Content -Raw backend/data/funny_memory.json
Invoke-RestMethod `
  -Uri http://127.0.0.1:8000/v1/memories/discover `
  -Method Post `
  -ContentType application/json `
  -Body $body
```

### Result statuses

| Status | Meaning | Generated content |
|---|---|---|
| `ready` | Candidate is grounded, valid, and human-confirmed | Memory, perspectives, and quest |
| `needs_human_confirmation` | Candidate is grounded but not confirmed by a player | Reviewable memory, perspectives, and quest |
| `rejected` | Evidence is insufficient or validation failed | Empty on safe abstention; diagnostic report included |

Every successful response includes a discovery assessment, validation report, quality scores, and
provider metadata. Schema-invalid requests return FastAPI's standard HTTP `422` response.

Generation safely abstains when there is no grounded gameplay event or fewer than two squad members
are opted in, even when captions or reactions make the raw signal score exceed the normal threshold.
The reason appears in the existing discovery `reasons` and validation `issues` fields.

## Provider configuration

The deterministic provider is the default and requires no credentials.

```dotenv
MEMORYOS_PROVIDER=deterministic
```

To use the OpenAI adapter:

```dotenv
MEMORYOS_PROVIDER=openai
OPENAI_API_KEY=your_server_side_key
OPENAI_MODEL=gpt-5.6-luna
```

The model handles bounded semantic generation. Input validation, the low-signal gate, and final
validation remain deterministic for both providers.

Invalid or unavailable provider configuration returns HTTP `503` with the stable error code
`pipeline_configuration_error`; secret or provider exception details are not returned to clients.

## Versioning

Input and output objects currently use `schema_version: "1.0"`. Breaking contract changes require a
new schema version and migration notes. HTTP routes remain under `/v1` for the same reason.

## Data boundary

The included JSON files are synthetic evaluation fixtures. This API does not currently receive live
Free Fire telemetry or player information and should not be deployed with real data without
authentication, access controls, retention rules, and a privacy review.
