# Product context

## Product name

- **Garena Next Chapter** is the player-facing experience.
- **MemoryOS** is the internal AI memory architecture.

## Product thesis

Most returner systems use generic rewards or generic quests. Next Chapter uses a player-owned squad
memory as the reason to return and turns that episode into something new to play together. The unit
of reactivation is the squad, not only the individual account.

Historical ranking matters because it changes the product from “summarize this match” into “find the
few moments this squad may genuinely want back.” Human review then supplies something telemetry and
AI cannot: whether the facts are correct and whether the moment carries personal meaning.

## Core experience

> Capture → Understand → Remember → Remix → Reunite → Continue

Phase 1/2 covers the center of that loop: rank historical Memory Packs, let a player verify and
confirm one, create personal recalls, and remix it into a quest.

The integrated player demo currently shows the reveal-and-remix half of this loop for one verified
fixture. Historical browsing and the two review decisions remain the active Phase 2B product work;
the attractive reveal screen should not be mistaken for completion of the trust flow.

## Product guardrails

- Deterministic ranking identifies candidates; humans verify source truth and confirm importance.
- Gameplay telemetry establishes facts, not feelings.
- Player-authored context may express meaning but cannot rewrite match facts.
- A weak candidate is skipped instead of decorated with generic nostalgia.
- Opted-out identities are anonymized before prompting; those players receive no perspective or
  quest assignment.
- “Best friend,” intent, and emotional-state claims require evidence the current schema does not
  provide. The prototype rejects known lexical patterns and keeps interpretation reviewable; this
  heuristic is a guardrail, not complete semantic proof.
- Mission success is not required for a meaningful reunion; future chapters should preserve wins
  and failures honestly.

## Golden path

“Worst Plan, Best Night” combines a retreat call, a late revive, a vehicle escape, a squad caption,
and positive reactions. Each player receives a different factual role in the same memory, then the
quest reverses the rescue role while recreating the original location and squad composition.

The test is simple:

> If the names and location can be removed without breaking the quest, it is not personal enough.
