# Phase 3: Explainable AI Delivery and Feedback Loop

## Purpose

Phase 3 turns the current prototype into a clear, judge-ready demonstration of responsible AI.
MemoryOS does not claim that a model decides what happened in a match or what a player should feel.
Trusted telemetry and deterministic safeguards establish eligible moments. AI turns the permitted
evidence into a relevant reminder, teammate perspectives, and a return-to-play mission.

The work is planned, not yet implemented. It begins after the collaborator dashboard work is
available to integrate.

## One shared dashboard

The dashboard is a single consent-safe tool for collaborators, development/testing, and the live
demo. It should make this sequence easy to follow:

```text
trusted telemetry and squad statistics
→ deterministic eligibility, consent, source-quality, and selection checks
→ AI memory presentation and mission, grounded in allowed event references
→ deterministic validation
→ player accept or decline feedback
→ offline evaluation of a later prompt/model version
```

For every prepared synthetic delivery, the dashboard will show:

- The selected match/event evidence and relevant squad statistics.
- Why deterministic selection surfaced the moment: eligibility, source status, redactions, and
  ranking reasons.
- What the AI contributed: title, notification teaser, grounded explanation, perspectives, and
  mission proposal.
- The allowed event references for factual generated statements, validation status, and
  provider/model/prompt version.
- The recorded player decision and any source-quality flag.

It must not expose raw prompts, model chain-of-thought, API keys, opted-out identities, or
unvalidated generated text. The dashboard explains observable inputs, outputs, references, and
validation—not hidden model reasoning.

## Player feedback and improvement policy

The player flow remains intentionally simple:

- **Accept mission** starts the squad-safe reunion path.
- **Decline → Not relevant to me** suppresses that exact memory for the player and contributes a
  relevance signal to aggregate evaluation.
- **Decline → Details are wrong** suppresses that exact memory for the player and creates a
  source-quality item for investigation. It does not alter match telemetry or ask the model to
  invent a correction.

Each durable decision record will retain only privacy-reviewed metadata needed for analysis:
delivery ID, safe player/session identifier, pack and memory type, decision/reason, source status,
provider/model/prompt version, and timestamp. Production storage requires authentication, retention
rules, and privacy approval; the current process-local store remains a prototype placeholder.

Feedback never edits prompts or facts live. Collaborators will aggregate outcomes, test candidate
prompt/model versions against held-out synthetic fixtures, run grounding/schema/privacy/validation
checks, then explicitly promote a version that improves the agreed measures. This keeps changes
reversible and prevents one player's decline from teaching the system an incorrect fact.

## Open-source model evaluation

The implementation will add candidate providers only behind the current structured-generation
boundary. Ranking, consent, redaction, source verification, mission constraints, and final
fail-closed validation remain deterministic.

For each candidate free/open-source model, record:

- licence, runtime/hosting requirements, hardware needs, and expected latency;
- typed schema adherence and provider failure rate;
- evidence-reference precision, privacy-leak count, validation pass rate, and perspective quality;
- comparison with the deterministic provider and optional live OpenAI demo provider.

No model becomes the selected prototype provider until it passes the existing deterministic
evaluation suite and never exposes malformed or ungrounded content to the player.

## Clip-first delivery

The first implementation uses a curated synthetic clip asset mapped to a verified match and event
ID. The clip is the notification's captivation layer: the player sees the moment first, then the AI
reminds them of the squad context and offers the mission.

The backend validates that the selected asset belongs to the prepared memory's allowed event IDs.
If no valid mapping exists, the clip is omitted and the notification fails safely rather than
showing unrelated footage. Live game-video retrieval, automatic clipping, and AI video analysis
are explicitly outside this milestone.

## Acceptance checks

- A dashboard trace visibly separates deterministic selection from AI presentation.
- Dashboard output is redacted and contains no secrets, raw prompts, chain-of-thought, opted-out
  identities, or unvalidated content.
- Both decline reasons persist correctly and suppress the exact delivery; `details_wrong` creates
  a dashboard source-quality flag without altering telemetry.
- Evaluation reports are reproducible from synthetic fixtures and require safety checks before a
  prompt/model version is promoted.
- Clip rendering requires a valid event-linked fixture; unknown or mismatched clips fail closed.
- Existing delivery, OpenAPI, privacy, and ready-only rendering regression tests remain green.
