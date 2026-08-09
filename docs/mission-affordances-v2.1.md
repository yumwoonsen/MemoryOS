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

The current catalogue contains exactly six mission families:

| Family | Evidence condition | Backend-owned objectives |
| --- | --- | --- |
| Reunion | Reunion is allowed and at least two players permit memory appearance and mission invitations | Reassemble the eligible roster and complete one match |
| Role reversal | A consent-safe revive identifies a previous rescuer and saved player | Reassemble, perform the role reversal, add compatible same-window mechanics such as a grounded return, and complete the match |
| Redemption | At least two supplied matches ended from fourth through sixth place | Reassemble, reach the top three, and complete the match |
| Return to place | A consent-safe revive in the selected window has a named location | Reassemble, return to that rescue location, add compatible same-window mechanics, and complete the match |
| Landing rendezvous | Every invitation-ready player has a landing event at the same named location within a 30-second span | Reassemble, land at that location, add compatible same-window mechanics, and complete the match |
| Duo assist | One invitation-ready player assists a distinct invitation-ready teammate who then records an elimination at the same location within 30 seconds | Reassemble, repeat the grounded assist pairing, add compatible same-window mechanics, and complete the match |

## Compound chapters: two to five steps

An affordance remains one selectable continuation, not a bag of unrelated quests. After the atomic
capabilities for one neutral window are known, deterministic preparation composes each offered
chapter into **two to five ordered objectives**:

1. one required invitation-safe squad prerequisite;
2. one required primary mechanic for every specialized family;
3. zero to two compatible support or optional bonus mechanics from the same window; and
4. one required match-completion objective.

Only the `bonus` role is optional. Prerequisite, primary, support, and completion objectives are
required and determine chapter completion. The player and Studio preserve the same complete order;
the UI labels each role instead of collapsing lifecycle rules into a single step.

The primary family mechanic is always retained. Secondary mechanics are added only when their
typed source events belong to the same window and do not create a conflicting landing/return
target. Redemption stays focused on its cross-match placement arc. Every composed candidate gets
an affordance-local ID and the selected family's recipe, so provider references remain unique and
the exact objective set can still be verified after the AI selects one chapter. The backend never
pads a chapter with an unsupported action merely to reach five steps.

Landing-rendezvous grounding is roster-complete, not inferred from a squad label or nearby-player
count. For each named location in a neutral window, preparation deterministically keeps the first
landing event per invitation-ready player and offers the family only when the resulting player set
equals the complete invitation roster and the event timestamps span no more than 30 seconds. The
backend owns the target location and the `match.invited_squad_lands_at_location = location`
verification rule.

Duo-assist grounding requires an explicit assist-to-elimination pair in one neutral window. The
assist actor and target must be distinct invitation-ready players; the target must be the actor on a
later elimination at the same named location, zero to 30 seconds after the assist. The backend owns
the assigned assister, finishing teammate, source pair, minimum count of one, and
`match.assigned_player_assisted_elimination_player_ids contains_all [teammate]` verification rule.

A tactical-signal mechanic is grounded only by the first consent-safe `SIGNAL` event in the window;
the backend assigns its actor and owns
`match.first_squad_tactical_signal_actor_id equals <player>`. A vehicle-extraction mechanic requires
a full-roster collective `VEHICLE_ENTER` followed at the same named location by a full-roster
collective `ESCAPE` within 60 seconds. Its rule is
`match.invited_squad_vehicle_escape_within_seconds equals true`. These mechanics can become support
or bonus steps only when compatibility and the two-to-five-step grammar permit them.

## Story-linked selection

The provider compares `episode × mission affordance` options rather than treating the candidate
list as a menu of interchangeable daily quests. It should normally select the continuation with the
strongest direct connection to the source episode: for example, a consent-safe rescue may support a
role reversal or a return to its named location, repeated near misses may support redemption, a
complete shared drop may support landing rendezvous, and a proven assist-to-elimination pair may
support duo assist. The AI still chooses that connection and writes the memory, title, and short
story bridge; deterministic code does not assign a narrative meaning to the episode. Deterministic
code does write the exact objective descriptions for the selected capability.

`reunion` is the general fallback. It remains a valid AI choice when no more coherent specific
continuation is supported. This is prompt-level selection guidance, not a deterministic family
priority: validation does not automatically prefer or reject a mission merely because its family is
`role_reversal`, `redemption`, `return_to_place`, `landing_rendezvous`, `duo_assist`, or `reunion`.
It validates only that the chosen option was offered, grounded, consent-safe, and feasible, and that
its story bridge does not contradict its backend-owned rules or introduce an unsupported mechanic.

The order of `A#` entries, their request-scoped reference numbers, and the number of nested `O#`
objectives are not preference or quality signals. The AI must reason from the evidence connection
and capability meaning, not choose `A1`, the first serialized option, or the option with the most
objectives by default.

Current activity is context, not invitation authority. An inactive original squad member remains
invitation-eligible when the required consent is present. Activity may be shown as Online or Away,
while invitation acceptance is represented separately as Invited or Joined.

## Controlled mission variation

The consumer prototype uses one coherent server-owned synthetic squad history rather than exposing
four fixtures for the player to choose. A trusted same-origin proxy generates a fresh opaque nonce
for each request. Before provider authoring, deterministic policy excludes the last two successfully
delivered families when alternatives exist, selects at most one affordance per family, and narrows
the provider input to at most three specialized grounded choices. The provider ranks and authors
only inside that pool; it cannot select a hidden or unsupported affordance. `reunion` remains the
fallback only when no specialized family is feasible.

This gives reruns real variety without making model temperature a safety mechanism. The nonce and
raw telemetry remain server-side, successful-family history is process-local prototype state, and
each rerun may consume provider quota.

## Backend-compiled objective copy

Each provider-facing `O#` communicates a deterministic capability: invited-squad participation,
minimum completed matches, a consent-safe assigned first reviver, a placement limit, a named return
or landing location, or an invitation-safe assister/finishing-teammate pair. The provider uses those
capabilities to compare continuations, but does not write their authoritative objective descriptions.

After the AI selects an affordance, the backend compiles every chosen `O#` into exact player-facing
copy such as **Queue into a match with the invited squad**, **Lee completes the first revive**, or
**Reach the top three**, **Land at Peak with the invited squad**, or **Lee assists Mei with an
elimination**. Canonical assignments, metrics, operators, targets, evidence, consent, and privacy
remain deterministic. The public `next_chapter` shape stays stable: `mission` carries the AI-authored
short story bridge, while `objectives` carry the backend-compiled steps.

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

The completed chapter is constructed locally from the mission family: **Together Again** for
reunion, **The Favour Returned** for role reversal, **The Comeback Complete** for redemption,
**Back Where It Began** for return to place, **Same Drop, Same Squad** for landing rendezvous, and
**The Setup and the Finish** for duo assist. Fixed alternatives avoid repeating the accepted mission
title. This is deterministic presentation copy, not another provider call or a claim that new match
telemetry was interpreted.

The player projection preserves every ordered backend objective and labels its role. Prerequisite
and completion remain separate lifecycle steps around the selected primary, support, and bonus
mechanics. Developer Studio displays the same objective count plus the backend-owned controls for
auditability.

## Failure and provenance

Live AI receives one bounded correction attempt for repairable schema or grounding issues. Safe
feedback uses provider-visible authored-section and request references without revealing canonical
candidate IDs. The unchanged `W#`/`A#`/`O#` catalogue keeps any corrected selection or story bridge
inside the original capability boundary.
Rejected prose and free-form validator messages are not returned. If the corrected proposal still
fails, MemoryOS withholds all generated artifacts. One live run therefore uses one initial provider
call and may use one correction call.

V2.1 adds an explicit content origin:

- backend result `live_ai_validated` for player-deliverable pending output;
- backend result `no_player_content` for an abstention or withheld result;
- backend result `deterministic_studio_sample` for offline/test output only; and
- top-level Studio `saved_live_replay` for a reviewed exact-version live capture used only for
  inspection.

The player accepts only `live_ai_validated` and shows
**AI-prepared · evidence-checked**. A replay requires matching scenario ID, fixture hash/revision,
provider, model, prompt, result schema, and capture time; no replay is currently committed. It never
acts as a generic rescue or deterministic fallback.

Studio registers Rescue, Landing rendezvous, Duo assist, Repeated near miss, and Ordinary scenarios.
Their expected labels remain outside telemetry and model input. Preparation constructs windows and
affordances with zero provider calls. Studio does not cache or deduplicate completed live results:
every later run may use the initial call plus the bounded correction, while the UI only locks
concurrent clicks.

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

The current prompt contract is `memory-interpreter-v2.13-perspective-safe-variation`, loaded from
`memory_interpreter_v2_13.txt`. Historical V2.4 and V2.10 smoke results remain historical evidence
and must not be described as validation of the current prompt.
