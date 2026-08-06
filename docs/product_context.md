# Product context

## Product name

- **Garena Next Chapter** is the player-facing experience.
- **MemoryOS** is the internal AI memory architecture.

## Product thesis

Existing returner systems usually use generic rewards or generic quests. Next Chapter uses a
player-owned squad memory as the reason to return and turns that past episode into something new to
play together.

The unit of reactivation is the squad, not only the individual account.

## Core experience

The longer product loop is:

> Capture → Understand → Remember → Remix → Reunite → Continue

Phase 1 focuses on the center of that loop: understand a historical Memory Pack, create personal
recalls, remix it into a quest, and require player confirmation before activation.

## Product guardrails

- AI identifies candidate memories; humans confirm importance.
- Gameplay telemetry establishes facts, not feelings.
- Player-authored context may express meaning but cannot rewrite match facts.
- A weak candidate should be skipped instead of decorated with generic nostalgia.
- Opted-out players do not receive generated perspectives.
- In this prototype, opt-out also prevents quest assignment but does not remove a player's
  participation from shared match evidence; production data-exclusion semantics remain unresolved.
- “Best friend,” intent, and emotional-state claims require evidence the current schema does not
  provide, so the validator rejects them.
- Mission success is not required for a meaningful reunion; future chapter generation should
  preserve both wins and failures honestly.

## Golden path

“Worst Plan, Best Night” combines a retreat call, a late revive, a vehicle escape, a squad caption,
and positive reactions. Each player receives a different factual role in the same memory, then the
quest reverses the rescue role while recreating the original location and squad composition.

The test is simple:

> If the names and location can be removed without breaking the quest, it is not personal enough.
