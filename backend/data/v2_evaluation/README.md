# V2.1 offline evaluation set

This directory contains telemetry-only evaluation cases and human-authored expected outcomes. The
labels evaluate the pipeline; they are never included in the interpreter prompt.

The set covers:

- a rescue episode expected to select `role_reversal`;
- the same scenario with the revive removed, where `role_reversal` must not be offered;
- repeated fourth/fifth-place finishes expected to select `redemption`;
- ordinary sparse telemetry where live AI is expected to return the typed `not_generated` result.

Run the free deterministic baseline from the repository root:

```powershell
python -m backend.evaluate_v2
```

Live calls are deliberately opt-in. They require the matching provider credential and the explicit
flag below; repeating `--model` compares identical cases under each named model.

```powershell
python -m backend.evaluate_v2 --provider groq --allow-live-api --repeats 3 `
  --model openai/gpt-oss-20b --model openai/gpt-oss-120b
```

The JSON report includes terminal status, offered and selected mission family, correction and
validation outcomes, end-to-end latency, and aggregate provider token usage. It excludes API keys,
raw telemetry, prompts, generated prose, and provider error text.

The deterministic baseline does not imitate semantic abstention, so the ordinary-telemetry label is
expected to fail there. That case is designed for controlled live-model evaluation.
