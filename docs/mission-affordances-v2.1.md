# MemoryOS v2.1 mission affordances

MemoryOS presents one **Next Chapter** to a player, but it does not hard-code one mission type.
The backend derives several feasible mission affordances from consent-safe evidence, the AI ranks
and selects one of them, and deterministic validation checks the selection before delivery.

## Responsibility boundary

1. Raw telemetry is normalized and privacy-filtered.
2. Deterministic preparation forms neutral event windows and a typed `StoryBriefV2`.
3. The backend compiles only the mission affordances supported by the evidence.
4. The AI selects one offered window and one offered affordance, then authors the memory and mission
   language.
5. Deterministic validation checks evidence, consent, assignments, mission mechanics, and all
   player-facing factual claims.
6. A validated delivery reaches the player, or the AI may return a validated `not_generated`
   abstention when no episode deserves a memory.

The current catalogue contains exactly three mission families:

| Family | Evidence condition | Backend-owned objectives |
| --- | --- | --- |
| Reunion | Reunion is allowed and at least two players permit memory appearance and mission invitations | Reassemble the eligible roster and complete one match |
| Role reversal | A consent-safe revive identifies a previous rescuer and saved player | Reassemble, complete a match, and assign the first future revive to the previously saved player |
| Redemption | At least two supplied matches ended from fourth through sixth place | Reassemble, complete a match, and reach the top three |

Current activity is context, not invitation authority. An inactive original squad member remains
invitation-eligible when the required consent is present. Activity may be shown as Online or Away,
while invitation acceptance is represented separately as Invited or Joined.

## Prototype gameplay boundary

The player-facing continuation after mission acceptance is intentionally scripted:

```text
mission accepted -> invitations sent -> eligible squad joined -> game started
-> prototype game ended -> selected mission shown as complete
```

This demonstrates the end-to-end product idea without claiming integration with a live Garena
match-result feed. The completion screen is labelled **Prototype match simulation**. Real
post-match verification and durable mission-result storage are deferred until an authenticated
game telemetry integration exists.

## Failure and provenance

Live AI receives one bounded correction attempt for repairable schema or grounding issues. If the
corrected proposal still fails, MemoryOS withholds all generated artifacts. Deterministic prose is
available only in explicitly labelled Studio demonstrations and is never substituted into the
live player path.

V2.1 adds an explicit content origin:

- `live_ai_validated` for player-deliverable AI output;
- `deterministic_studio_sample` for offline or saved Studio demonstrations.

Studio displays offered affordances, the ranked and selected IDs, concise allowlisted selection
reason codes, backend-owned objective rules, and validation status. It does not expose prompts,
chain-of-thought, rejected prose, secrets, or opted-out identities.

## Compatibility

The public endpoints remain under `/v2`. The interpretation endpoint accepts existing v2.0 raw
telemetry payloads and returns the v2.1 delivery/trace contract. V1.0 and v1.1 scaffold-led routes
remain deprecated compatibility paths.

The current prompt contract is `memory-interpreter-v2.6-mission-affordances`. Historical v2.4
smoke results remain historical evidence and must not be described as validation of the current
prompt.
