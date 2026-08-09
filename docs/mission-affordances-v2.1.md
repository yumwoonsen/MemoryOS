# MemoryOS v2.1 mission affordances

MemoryOS presents one **Next Chapter** to a player, but it does not hard-code one mission type.
The backend derives feasible, verifiable mission affordances from consent-safe evidence. The AI
compares each eligible episode-and-mission combination, selects the strongest coherent continuation,
and authors its title and story bridge naturally. The backend compiles the selected capability into
exact objective copy. Deterministic validation checks that the selection and story remain inside the
offered evidence and capabilities before delivery.

## Responsibility boundary

1. Raw telemetry is normalized and privacy-filtered.
2. Deterministic preparation forms neutral event windows and a typed `StoryBriefV2`.
3. The backend compiles only mission affordances that are supported by the evidence and that a
   future game result could verify.
4. The provider receives neutral request-scoped `W#` windows and `A#` affordances with nested typed
   `O#` objective capabilities. Each `A#` is one episode-and-mission pair. The provider ranks those
   choices and authors the memory language, perspectives, mission title, and short story bridge; the
   first `A#` determines its linked episode without a redundant selected-window output field.
5. The backend resolves the selected capability and compiles its exact player-facing objective
   descriptions, assignments, metrics, operators, targets, and verification rules.
6. Deterministic validation checks evidence, consent, assignments, mission mechanics, and all
   player-facing factual claims.
7. A validated delivery reaches the player, or the AI may return a validated `not_generated`
   abstention when no episode deserves a memory.

The current catalogue contains exactly three mission families:

| Family | Evidence condition | Backend-owned objectives |
| --- | --- | --- |
| Reunion | Reunion is allowed and at least two players permit memory appearance and mission invitations | Reassemble the eligible roster and complete one match |
| Role reversal | A consent-safe revive identifies a previous rescuer and saved player | Reassemble, complete a match, and assign the first future revive to the previously saved player |
| Redemption | At least two supplied matches ended from fourth through sixth place | Reassemble, complete a match, and reach the top three |

## Story-linked selection

The provider compares `episode × mission affordance` options rather than treating the candidate
list as a menu of interchangeable daily quests. It should normally select the continuation with the
strongest direct connection to the source episode: for example, a consent-safe rescue may support a
role reversal, while repeated near misses may support redemption. The AI still chooses that
connection and writes the memory, title, and short story bridge; deterministic code does not assign
a narrative meaning to the episode. Deterministic code does write the exact objective descriptions
for the selected capability.

`reunion` is the general fallback. It remains a valid AI choice when no more coherent specific
continuation is supported. This is prompt-level selection guidance, not a deterministic family
priority: validation does not automatically prefer or reject a mission merely because its family is
`role_reversal`, `redemption`, or `reunion`. It validates only that the chosen option was offered,
grounded, consent-safe, and feasible, and that its story bridge does not contradict its backend-owned
rules or introduce an unsupported mechanic.

The order of `A#` entries, their request-scoped reference numbers, and the number of nested `O#`
objectives are not preference or quality signals. The AI must reason from the evidence connection
and capability meaning, not choose `A1`, the first serialized option, or the option with the most
objectives by default.

Current activity is context, not invitation authority. An inactive original squad member remains
invitation-eligible when the required consent is present. Activity may be shown as Online or Away,
while invitation acceptance is represented separately as Invited or Joined.

## Backend-compiled objective copy

Each provider-facing `O#` communicates a deterministic capability: invited-squad participation,
minimum completed matches, a consent-safe assigned first reviver, or a placement limit. The provider
uses those capabilities to compare continuations, but does not write their authoritative objective
descriptions.

After the AI selects an affordance, the backend compiles every chosen `O#` into exact player-facing
copy such as **Complete one match with the invited squad**, **Lee completes the first revive**, or
**Reach the top three**. Canonical assignments, metrics, operators, targets, evidence, consent, and
privacy remain deterministic. The public `next_chapter` shape stays stable: `mission` carries the
AI-authored short story bridge, while `objectives` carry the backend-compiled steps.

The story bridge does not need to repeat every mechanical rule. Validation still rejects a bridge
that contradicts an offered target or operator, invents an unoffered mechanic, asserts unsupported
facts, leaks private information, or contains unsafe content.

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

The player projection combines the roster-participation rule and the completed-match rule into one
clear step when they describe the same action, such as **Complete one match with the invited
squad**. This is a presentation simplification only. Developer Studio retains and displays the
separate backend-owned participant and completion rules for auditability.

## Failure and provenance

Live AI receives one bounded correction attempt for repairable schema or grounding issues. Safe
feedback uses provider-visible authored-section and request references without revealing canonical
candidate IDs. The unchanged `W#`/`A#`/`O#` catalogue keeps any corrected selection or story bridge
inside the original capability boundary.
Rejected prose and free-form validator messages are not returned. If the corrected proposal still
fails, MemoryOS withholds all generated artifacts.
Deterministic prose is available only in explicitly labelled Studio demonstrations and is never
substituted into the live player path.

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

The short references exist only inside one provider request. The backend deterministically resolves
them to canonical window, affordance, and objective IDs before authoritative expansion and
validation. Typed capabilities communicate feasible mechanics without supplying finished mission
story or narrative meaning; the backend, not the provider, supplies the finished objective copy.

The current prompt contract is `memory-interpreter-v2.11-backend-mission-copy`, loaded from
`memory_interpreter_v2_11.txt`. Historical V2.4 and V2.10 smoke results remain historical evidence
and must not be described as validation of the current prompt.
