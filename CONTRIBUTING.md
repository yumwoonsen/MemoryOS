# Contributing to MemoryOS

MemoryOS is a handoff-stage hackathon prototype. Contributions should strengthen the central claim: a
Next Chapter must be specific to one squad, grounded in evidence, distinct for each participant,
and safe to abstain when the input is weak.

## Local setup

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

The included VS Code settings select the local virtual environment and enable pytest discovery.

## Quality gates

Run all checks before committing:

```powershell
python scripts/verify.py
```

This expects the backend development environment and frontend packages to be installed. To apply
the backend formatter locally, run `ruff format .` and then repeat the verification suite.

## Change guidelines

- Keep the v1.0 compatibility contract stable, and make intentional v1.1 contract changes through
  the Pydantic models and generated OpenAPI rather than duplicating frontend schemas.
- Add or update a fixture whenever a new behavior or failure mode is introduced.
- Keep eligibility, evidence, consent, verification, and safety checks deterministic.
- Preserve the historical-request invariants: one target, one squad ID, one roster, one current
  consent snapshot, and unique pack IDs.
- Treat prompt changes like code: document the intent and evaluate all eligible fixtures.
- Do not add claims about Garena's internal telemetry or APIs without an authoritative source.
- Do not commit real player data, API keys, any `.env*` file other than `.env.example`, generated
  evaluation exports, or local environments.
- Preserve safe abstention; more generated content is not automatically better output.

## Commit style

Use a concise Conventional Commit-style subject followed by a body that explains the product or
architecture impact. Examples:

```text
feat: add human confirmation review state
fix: reject quest evidence not present in the Memory Pack
docs: explain the provider and validation boundary
test: cover duplicate event identifiers
```

## Pull requests

A useful pull request explains:

1. What behavior changed and why.
2. Which contract, prompt, or pipeline stage is affected.
3. Which fixtures and tests demonstrate the change.
4. Whether grounding, consent, cost, latency, or privacy behavior changed.
