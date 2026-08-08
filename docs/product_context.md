# Product context

## Product name

- **Garena Next Chapter** is the player-facing experience.
- **MemoryOS** is the internal AI memory architecture.

## Product thesis

Most returner systems use generic rewards or generic quests. Next Chapter uses a player-owned squad
memory as the reason to return and turns that episode into something new to play together. The unit
of reactivation is the squad, not only the individual account.

The v2 product begins with sparse gameplay evidence rather than a pre-authored memory. AI provides
the memory intelligence: it chooses one connected episode, finds a supported angle, and writes the
memory, perspectives, and reunion mission. Deterministic code remains the safety referee for
telemetry roles, consent, privacy, evidence claims, and mission feasibility.

## Core experience

> Capture → Understand → Remember → Remix → Reunite → Continue

The current prototype covers the center and continuation of that loop: interpret a telemetry-only
batch, validate one generated memory, let the player accept or decline it, simulate a squad
invitation and new match, verify the mission deterministically, and unlock “Story Continues.”
Historical browsing remains a separate read-only timeline rather than a second decision interface.

## Product guardrails

- Authenticated upstream telemetry must establish source truth; the player judges relevance rather
  than auditing raw events.
- AI chooses only among deterministic, consent-safe connected event windows.
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

The synthetic Free Fire fixture contains sparse landing, knock, ping, revive, vehicle, escape, and
match-result telemetry plus limited current squad context. It does not supply “Worst Plan, Best
Night,” a narrative angle, perspectives, or a mission. Those are proposed by AI, then withheld
unless every material fact and mission control passes deterministic validation.

The test is simple:

> If the names and location can be removed without breaking the quest, it is not personal enough.
