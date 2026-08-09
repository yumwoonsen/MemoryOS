"""Deterministic factual, privacy, and mission validation for v2 proposals."""

from __future__ import annotations

import json
import re

from backend.models.schemas import MemoryType
from backend.models.v2_schemas import (
    CanonicalEventType,
    ClaimPredicate,
    GroundedClaim,
    MemoryProposalV2,
    ProposalValidationReportV2,
    V2ValidationIssue,
)
from backend.services.content_safety import (
    contains_secret_like,
    contains_unsafe_player_content,
)
from backend.services.identity import contains_identity, identity_pattern
from backend.services.v2_preparation import (
    ALLOWED_CATEGORICAL_DETAILS,
    PreparedInterpretationV2,
    collective_event_includes_full_squad,
)

PREDICATE_EVENT_TYPES: dict[ClaimPredicate, CanonicalEventType] = {
    ClaimPredicate.LANDED: CanonicalEventType.LANDING,
    ClaimPredicate.KNOCKED: CanonicalEventType.KNOCK,
    ClaimPredicate.WAS_KNOCKED: CanonicalEventType.KNOCK,
    ClaimPredicate.ELIMINATED: CanonicalEventType.ELIMINATION,
    ClaimPredicate.WAS_ELIMINATED: CanonicalEventType.ELIMINATION,
    ClaimPredicate.REVIVED: CanonicalEventType.REVIVE,
    ClaimPredicate.ASSISTED: CanonicalEventType.ASSIST,
    ClaimPredicate.HEALED: CanonicalEventType.HEAL,
    ClaimPredicate.ENTERED_VEHICLE: CanonicalEventType.VEHICLE_ENTER,
    ClaimPredicate.EXITED_VEHICLE: CanonicalEventType.VEHICLE_EXIT,
    ClaimPredicate.ESCAPED: CanonicalEventType.ESCAPE,
    ClaimPredicate.MOVED_ZONE: CanonicalEventType.ZONE_MOVE,
    ClaimPredicate.LOOTED: CanonicalEventType.LOOT,
    ClaimPredicate.SIGNALLED: CanonicalEventType.SIGNAL,
    ClaimPredicate.COMPLETED_MATCH: CanonicalEventType.MATCH_COMPLETE,
}

ACTION_WORDS: dict[ClaimPredicate, tuple[str, ...]] = {
    ClaimPredicate.LANDED: ("land", "lands", "landed", "landing"),
    ClaimPredicate.KNOCKED: ("knock", "knocks", "knocked", "knocking"),
    ClaimPredicate.WAS_KNOCKED: ("was knocked",),
    ClaimPredicate.ELIMINATED: (
        "eliminate",
        "eliminates",
        "eliminated",
        "eliminating",
        "elimination",
        "eliminations",
        "kill",
        "kills",
        "killed",
        "killing",
    ),
    ClaimPredicate.WAS_ELIMINATED: ("was eliminated",),
    ClaimPredicate.REVIVED: (
        "revive",
        "revives",
        "revived",
        "reviving",
        "revival",
        "revivals",
    ),
    ClaimPredicate.ASSISTED: ("assist", "assists", "assisted", "assisting"),
    ClaimPredicate.HEALED: (
        "heal",
        "heals",
        "healed",
        "healing",
        "recovered health",
    ),
    ClaimPredicate.ENTERED_VEHICLE: (
        "entered a vehicle",
        "entered the vehicle",
        "enters a vehicle",
        "enters the vehicle",
        "entering a vehicle",
        "entering the vehicle",
        "board",
        "boarded",
        "boards",
        "boarding",
        "got into",
        "gets into",
        "getting into",
        "hopped into",
        "hops into",
        "hopping into",
        "piled into",
        "piles into",
        "piling into",
    ),
    ClaimPredicate.EXITED_VEHICLE: (
        "left a vehicle",
        "leaves a vehicle",
        "leaving a vehicle",
        "exited a vehicle",
        "exits a vehicle",
        "exiting a vehicle",
    ),
    ClaimPredicate.ESCAPED: (
        "escape",
        "escapes",
        "escaped",
        "escaping",
        "flee",
        "flees",
        "fled",
        "fleeing",
        "get out",
        "gets out",
        "getting out",
        "got out",
        "made it out",
        "leave the danger zone",
        "leaves the danger zone",
        "left the danger zone",
        "leave the damage zone",
        "leaves the damage zone",
        "left the damage zone",
    ),
    ClaimPredicate.MOVED_ZONE: (
        "rotate",
        "rotates",
        "rotated",
        "rotating",
        "move into the zone",
        "moves into the zone",
        "moved into the zone",
        "moving into the zone",
    ),
    ClaimPredicate.LOOTED: (
        "loot",
        "loots",
        "looted",
        "looting",
        "collected supplies",
    ),
    ClaimPredicate.SIGNALLED: (
        "tactical signal",
        "signal",
        "signals",
        "signaled",
        "signalled",
        "signaling",
        "signalling",
        "ping",
        "pings",
        "pinged",
        "pinging",
    ),
    ClaimPredicate.COMPLETED_MATCH: (
        "completed the match",
        "complete the match",
        "complete a match",
        "finished the match",
        "finish the match",
        "finish a match",
    ),
}

ROLE_ACTION_PREDICATES = (
    ClaimPredicate.LANDED,
    ClaimPredicate.KNOCKED,
    ClaimPredicate.ELIMINATED,
    ClaimPredicate.REVIVED,
    ClaimPredicate.ASSISTED,
    ClaimPredicate.HEALED,
    ClaimPredicate.ENTERED_VEHICLE,
    ClaimPredicate.EXITED_VEHICLE,
    ClaimPredicate.ESCAPED,
    ClaimPredicate.MOVED_ZONE,
    ClaimPredicate.LOOTED,
    ClaimPredicate.SIGNALLED,
    ClaimPredicate.COMPLETED_MATCH,
)

PASSIVE_ACTION_PREDICATES = {
    ClaimPredicate.KNOCKED: ClaimPredicate.WAS_KNOCKED,
    ClaimPredicate.ELIMINATED: ClaimPredicate.WAS_ELIMINATED,
}

FATAL_VALIDATION_CODES = {
    "privacy_identity_leak",
    "secret_exposure",
    "unsafe_generated_content",
    "unsafe_mission_content",
}

MATCH_PREDICATES = {
    ClaimPredicate.PLAYED_GAME: "game",
    ClaimPredicate.PLAYED_MODE: "mode",
    ClaimPredicate.PLAYED_MAP: "map",
    ClaimPredicate.PLACED: "placement",
    ClaimPredicate.MATCH_RESULT: "result",
}

PREDICATE_DETAIL_KEYS: dict[ClaimPredicate, set[str]] = {
    ClaimPredicate.LANDED: {"team_members_nearby", "count"},
    ClaimPredicate.KNOCKED: {"nearby_enemies", "weapon_class", "zone_phase", "count"},
    ClaimPredicate.WAS_KNOCKED: {"nearby_enemies", "zone_phase", "health_state", "count"},
    ClaimPredicate.ELIMINATED: {"weapon_class", "zone_phase", "count"},
    ClaimPredicate.WAS_ELIMINATED: {"zone_phase", "count"},
    ClaimPredicate.REVIVED: {"zone_phase", "health_state", "nearby_enemies", "count"},
    ClaimPredicate.ASSISTED: {"weapon_class", "count"},
    ClaimPredicate.HEALED: {"health_state", "count"},
    ClaimPredicate.ENTERED_VEHICLE: {"vehicle_type", "squad_members_aboard", "count"},
    ClaimPredicate.EXITED_VEHICLE: {"vehicle_type", "count"},
    ClaimPredicate.ESCAPED: {"squad_members_alive", "zone_phase", "vehicle_type", "count"},
    ClaimPredicate.MOVED_ZONE: {"zone_phase", "zone_state", "distance_meters", "count"},
    ClaimPredicate.LOOTED: {"item_type", "count"},
    ClaimPredicate.SIGNALLED: {"ping_type", "count"},
    ClaimPredicate.COMPLETED_MATCH: {"placement", "squad_members_alive"},
}

UNSAFE_MISSION_PATTERN = re.compile(
    r"(?i)\b(?:password|credential|login|api[_ -]?key|one[- ]time code|otp|"
    r"credit card|bank account|real money|home address|phone number|doxx|"
    r"threaten|harass|or else|no choice|forced to)\b|https?://"
)

VICTORY_WORDS = {"victory", "won", "winner", "booyah", "first place"}
VICTORY_RESULTS = {"win", "won", "victory", "winner", "booyah", "first"}
MISSION_METRIC_PREDICATES = {
    "squad.matches_completed": {ClaimPredicate.COMPLETED_MATCH},
    "match.first_squad_revive_actor_id": {ClaimPredicate.REVIVED},
    "match.top_three_reached": {ClaimPredicate.PLACED},
    "match.invited_squad_visits_location": set(),
    "match.invited_squad_lands_at_location": {ClaimPredicate.LANDED},
    "match.assigned_player_assisted_elimination_player_ids": {
        ClaimPredicate.ASSISTED,
        ClaimPredicate.ELIMINATED,
    },
    "match.first_squad_tactical_signal_actor_id": {ClaimPredicate.SIGNALLED},
    "match.invited_squad_vehicle_escape_within_seconds": {
        ClaimPredicate.ENTERED_VEHICLE,
        ClaimPredicate.ESCAPED,
    },
}

KNOWN_UNSUPPORTED_VEHICLES = {
    "boat",
    "car",
    "helicopter",
    "truck",
    "van",
}

MISSION_METRIC_ALLOWED_ACTIONS = {
    "squad.participant_ids": {ClaimPredicate.COMPLETED_MATCH},
    "squad.matches_completed": {ClaimPredicate.COMPLETED_MATCH},
    "match.first_squad_revive_actor_id": {ClaimPredicate.REVIVED},
    "match.top_three_reached": set(),
    "match.invited_squad_visits_location": set(),
    "match.invited_squad_lands_at_location": {ClaimPredicate.LANDED},
    "match.assigned_player_assisted_elimination_player_ids": {
        ClaimPredicate.ASSISTED,
        ClaimPredicate.ELIMINATED,
    },
    "match.first_squad_tactical_signal_actor_id": {ClaimPredicate.SIGNALLED},
    "match.invited_squad_vehicle_escape_within_seconds": {
        ClaimPredicate.ENTERED_VEHICLE,
        ClaimPredicate.ESCAPED,
    },
}

NUMBER_WORD_VALUES = {
    "zero": 0,
    "one": 1,
    "once": 1,
    "two": 2,
    "twice": 2,
    "three": 3,
    "thrice": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
    "hundred": 100,
}

MISSION_QUANTIFIER_VALUES = {
    **NUMBER_WORD_VALUES,
    "a": 1,
    "an": 1,
    "single": 1,
    "couple": 2,
    "pair": 2,
    "both": 2,
    "double": 2,
    "dozen": 12,
}

MISSION_AMBIGUOUS_QUANTIFIERS = {"few", "several", "multiple"}

MISSION_METRIC_NOUNS = {
    "squad.matches_completed": ("match", "matches", "round", "rounds", "game", "games"),
    "match.assigned_player_assisted_elimination_player_ids": (
        "elimination",
        "eliminations",
        "kill",
        "kills",
    ),
    "match.invited_squad_vehicle_escape_within_seconds": ("second", "seconds"),
}

MISSION_UNOFFERED_CONDITION_PATTERN = re.compile(
    r"\b(?:headshots?|damage|pistols?|sidearms?|rifles?|shotguns?|snipers?|"
    r"weapons?|firearms?|guns?|grenades?|"
    r"melee|armor|helmets?|medkits?|without dying|without taking|"
    r"without moving|without healing|no healing|using only|using|equipped|armed|"
    r"crouch\w*|prone|sprint\w*|jump\w*|camp\w*|hid(?:e|ing)|stealth|"
    r"emotes?|solo|weaponless|entire time|throughout)\b"
)

MISSION_COMBAT_PAIR_PATTERN = re.compile(r"\b(?:kills?|eliminations?|duo)\b")

MISSION_STRONGER_THAN_TOP_THREE_PATTERN = re.compile(
    r"\b(?:win(?:s|ning)?|won|winner|victor(?:y|ious)|booyah|"
    r"(?:first|second)[ -]place|(?:finish|place|rank)\w*\s+(?:first|second)|"
    r"top[ -]+(?:1|one|2|two))\b"
)

UNSUPPORTED_OBSERVATION_PATTERN = re.compile(
    r"\b(?:saw|seen|watch(?:ed|ing)?|heard|hear|notice(?:d|ing)?|"
    r"observe(?:d|ing)?|witness(?:ed|ing)?)\b"
)


def action_language_present(text: str, term: str) -> bool:
    """Match an explicitly allowlisted action form at word boundaries."""

    return bool(re.search(rf"(?<!\w){re.escape(term)}(?!\w)", text.casefold()))


def assigned_player_performs_first_revive(text: str, display_name: str) -> bool:
    """Require the assigned player to be grammatically bound to the first revive."""

    player = identity_pattern(display_name.casefold())
    revive = r"(?:revive|revives|revived|reviving|revival|revivals)"
    first_revive = (
        rf"(?:(?:the|a)\s+)?(?:(?:squad|team)(?:['\u2019]s)?\s+)?"
        rf"first\s+{revive}"
    )
    auxiliary = (
        r"(?:(?:must|should|will|can|could|needs?\s+to|has\s+to|"
        r"is\s+to|is\s+assigned\s+to)\s+)?"
    )
    future_action = r"(?:completes?|performs?|makes?|gets?|secures?|do(?:es)?|takes?)"
    active_first_object = rf"{player}\s+{auxiliary}{future_action}\s+{first_revive}"
    active_first_to_revive = rf"{player}\s+{auxiliary}(?:be\s+)?(?:the\s+)?first\s+to\s+{revive}"
    active_revive_first = (
        rf"{player}\s+{auxiliary}{revive}"
        r"(?:\s+(?:a|the)\s+(?:teammate|squadmate))?\s+first\b"
    )
    passive_assignment = (
        rf"{first_revive}\s+(?:(?:must|should|will|can)\s+)?"
        rf"(?:be\s+)?(?:completed|performed|made|secured|done|taken)\s+by\s+{player}"
    )
    return any(
        re.search(pattern, text, flags=re.IGNORECASE)
        for pattern in (
            active_first_object,
            active_first_to_revive,
            active_revive_first,
            passive_assignment,
        )
    )


def assigned_player_performs_first_signal(text: str, display_name: str) -> bool:
    """Bind the backend-owned first tactical signal to its assigned player."""

    player = identity_pattern(display_name.casefold())
    signal = r"(?:tactical\s+)?(?:signal|ping)\w*"
    first_signal = (
        r"(?:(?:the|a)\s+)?(?:(?:squad|team)(?:['\u2019]s)?\s+)?"
        rf"first\s+{signal}"
    )
    auxiliary = (
        r"(?:(?:must|should|will|can|could|needs?\s+to|has\s+to|"
        r"is\s+to|is\s+assigned\s+to)\s+)?"
    )
    active = (
        rf"{player}\s+{auxiliary}"
        rf"(?:places?|sends?|makes?|sets?|calls?|pings?)\s+{first_signal}"
    )
    passive = (
        rf"{first_signal}\s+(?:(?:must|should|will|can)\s+)?"
        rf"(?:be\s+)?(?:placed|sent|made|set|called|pinged)\s+by\s+{player}"
    )
    return bool(re.search(active, text, flags=re.IGNORECASE)) or bool(
        re.search(passive, text, flags=re.IGNORECASE)
    )


def mission_metric_count_mentions(text: str, metric: str) -> list[int | None]:
    """Return only counts grammatically attached to the selected mission metric."""

    nouns = MISSION_METRIC_NOUNS.get(metric)
    if nouns is None:
        return []
    noun_pattern = "(?:" + "|".join(map(re.escape, nouns)) + ")"
    quantifiers = sorted(
        {*MISSION_QUANTIFIER_VALUES, *MISSION_AMBIGUOUS_QUANTIFIERS},
        key=len,
        reverse=True,
    )
    quantifier_pattern = "(?:" + "|".join(map(re.escape, quantifiers)) + r"|\d+)"
    before_noun_pattern = re.compile(
        rf"(?<!\w)(?P<count>{quantifier_pattern})(?!\w)"
        rf"(?:\s+as\s+many|\s+of)?(?:\s+|-)"
        rf"(?:(?:new|more|full|additional|ranked|squad|team)\s+){{0,2}}"
        rf"{noun_pattern}(?!\w)"
    )
    frequency_words = "(?:once|twice|thrice)"
    cardinal_pattern = (
        "(?:"
        + "|".join(
            map(
                re.escape,
                sorted(
                    {
                        key
                        for key in MISSION_QUANTIFIER_VALUES
                        if key not in {"a", "an", "single", "couple", "pair", "both", "double"}
                    },
                    key=len,
                    reverse=True,
                ),
            )
        )
        + r"|\d+)"
    )
    after_noun_patterns = (
        re.compile(
            rf"(?<!\w){noun_pattern}(?!\w)\s+"
            rf"(?P<count>{frequency_words})(?!\w)"
        ),
        re.compile(
            rf"(?<!\w){noun_pattern}(?!\w)\s+"
            rf"(?P<count>{cardinal_pattern})(?!\w)\s+times?(?!\w)"
        ),
    )
    mentions: list[int | None] = []
    normalized = text.casefold()
    matches = list(before_noun_pattern.finditer(normalized))
    for pattern in after_noun_patterns:
        matches.extend(pattern.finditer(normalized))
    for match in sorted(matches, key=lambda item: item.start()):
        raw = match.group("count")
        if raw.isdigit():
            mentions.append(int(raw))
        elif raw in MISSION_AMBIGUOUS_QUANTIFIERS:
            mentions.append(None)
        else:
            mentions.append(MISSION_QUANTIFIER_VALUES[raw])
    return mentions


class ProposalValidatorV2:
    """Validate structured claims and apply conservative prose-level checks."""

    def validate(
        self,
        prepared: PreparedInterpretationV2,
        proposal: MemoryProposalV2,
        *,
        correction_attempted: bool = False,
    ) -> ProposalValidationReportV2:
        if prepared.normalized is None:
            return ProposalValidationReportV2(
                passed=False,
                correction_attempted=correction_attempted,
                issues=[
                    self._issue("missing_prepared_telemetry", "Prepared telemetry is missing.")
                ],
            )
        issues: list[V2ValidationIssue] = []
        serialized = json.dumps(proposal.model_dump(mode="json"), ensure_ascii=False)
        for term in prepared.forbidden_identity_terms:
            if contains_identity(serialized, term):
                issues.append(
                    self._issue(
                        "privacy_identity_leak",
                        "Generated content references an opted-out identity.",
                    )
                )
                break
        if contains_secret_like(serialized):
            issues.append(self._issue("secret_exposure", "Generated content resembles a secret."))
        if contains_unsafe_player_content(serialized):
            issues.append(
                self._issue(
                    "unsafe_generated_content",
                    "Generated content contains unsafe or instruction-leaking text.",
                )
            )
        mission_text = " ".join(
            (
                proposal.mission.title,
                proposal.mission.mission,
                *(objective.description for objective in proposal.mission.objectives),
            )
        )
        if UNSAFE_MISSION_PATTERN.search(mission_text):
            issues.append(
                self._issue(
                    "unsafe_mission_content",
                    "Mission content requests unsafe, coercive, or credential-related action.",
                )
            )
        if any(issue.code in FATAL_VALIDATION_CODES for issue in issues):
            return ProposalValidationReportV2(
                passed=False,
                correction_attempted=correction_attempted,
                issues=self._deduplicate(issues),
            )

        windows = {window.window_id: window for window in prepared.windows}
        window = windows.get(proposal.selected_window_id)
        if window is None:
            issues.append(self._issue("unknown_event_window", "Selected event window is unknown."))
        elif window.match_id != proposal.selected_match_id:
            issues.append(
                self._issue(
                    "window_match_mismatch", "Selected window does not belong to the match."
                )
            )
        elif proposal.selected_event_ids != window.event_ids:
            issues.append(
                self._issue(
                    "selected_event_set_mismatch",
                    "Selected events must exactly match one eligible event window.",
                )
            )

        match_map = {match.match_id: match for match in prepared.normalized.matches}
        event_map = {
            event.event_id: event for match in prepared.normalized.matches for event in match.events
        }
        selected_ids = set(proposal.selected_event_ids)
        if proposal.selected_match_id not in match_map:
            issues.append(self._issue("unknown_selected_match", "Selected match is unknown."))
        unknown_selected = selected_ids - event_map.keys()
        if unknown_selected:
            issues.append(self._issue("unknown_selected_event", "Selected event is unknown."))
        if any(
            event_map[event_id].match_id != proposal.selected_match_id
            for event_id in selected_ids & event_map.keys()
        ):
            issues.append(
                self._issue(
                    "cross_match_episode", "A memory episode cannot cross match boundaries."
                )
            )
        if not unknown_selected:
            issues.extend(
                self._validate_memory_framing(
                    proposal,
                    [event_map[event_id] for event_id in proposal.selected_event_ids],
                    prepared,
                )
            )

        eligible_players = {
            player.player_id: player
            for player in prepared.normalized.players
            if player.memory_eligible
        }
        invitation_players = {
            player.player_id
            for player in prepared.normalized.players
            if player.memory_eligible and player.invitation_eligible
        }
        perspective_ids = [item.player_id for item in proposal.perspectives]
        if len(perspective_ids) != len(set(perspective_ids)):
            issues.append(
                self._issue(
                    "duplicate_perspective", "Each eligible player may have one perspective."
                )
            )
        if set(perspective_ids) != set(eligible_players):
            issues.append(
                self._issue(
                    "perspective_roster_mismatch",
                    "The proposal must include every and only memory-eligible player.",
                )
            )
        perspective_messages = [
            self._normalize_text(item.message) for item in proposal.perspectives
        ]
        if len(perspective_messages) != len(set(perspective_messages)):
            issues.append(
                self._issue(
                    "perspectives_not_distinct",
                    "Player perspectives must be distinct.",
                )
            )
        for perspective in proposal.perspectives:
            if not set(perspective.evidence_event_ids).issubset(selected_ids):
                issues.append(
                    self._issue(
                        "perspective_evidence_outside_episode",
                        "Perspective evidence must belong to the selected episode.",
                    )
                )

        candidate_map = {
            candidate.candidate_id: candidate for candidate in prepared.mission_candidates
        }
        affordance_map = {
            affordance.affordance_id: affordance for affordance in prepared.mission_affordances
        }
        selected_affordance = affordance_map.get(proposal.mission.affordance_id)
        if selected_affordance is None:
            issues.append(
                self._issue(
                    "invented_mission_affordance",
                    "The proposal selected a mission affordance that was not offered.",
                )
            )
        else:
            if selected_affordance.window_id != proposal.selected_window_id:
                issues.append(
                    self._issue(
                        "mission_affordance_not_linked",
                        "The selected mission affordance is not linked to the episode.",
                    )
                )
            if selected_affordance.family != proposal.mission.family:
                issues.append(
                    self._issue(
                        "mission_family_mismatch",
                        "The mission family differs from the selected affordance.",
                    )
                )
            if len(proposal.mission.ranked_affordance_ids) != len(
                set(proposal.mission.ranked_affordance_ids)
            ) or set(proposal.mission.ranked_affordance_ids) != set(affordance_map):
                issues.append(
                    self._issue(
                        "mission_affordance_ranking_invalid",
                        "The mission ranking must include every offered affordance exactly once.",
                    )
                )
            if proposal.mission.ranked_affordance_ids[0] != proposal.mission.affordance_id:
                issues.append(
                    self._issue(
                        "mission_affordance_selection_not_first",
                        "The selected mission affordance must rank first.",
                    )
                )
            if not set(proposal.mission.selection_reason_codes).issubset(
                selected_affordance.allowed_reason_codes
            ):
                issues.append(
                    self._issue(
                        "mission_selection_reason_invalid",
                        "The mission selection uses a reason code not offered by the backend.",
                    )
                )
        objective_ids = [item.candidate_id for item in proposal.mission.objectives]
        if len(objective_ids) != len(set(objective_ids)):
            issues.append(self._issue("duplicate_mission_candidate", "Mission candidates repeat."))
        if not set(objective_ids).issubset(candidate_map):
            issues.append(
                self._issue(
                    "invented_mission_candidate",
                    "The proposal selected a mission candidate that was not offered.",
                )
            )
        if selected_affordance and objective_ids != selected_affordance.objective_candidate_ids:
            issues.append(
                self._issue(
                    "mission_objective_set_mismatch",
                    "Mission objectives must exactly match the selected affordance.",
                )
            )
        if any(
            item.candidate_id in candidate_map
            and item.objective_role != candidate_map[item.candidate_id].objective_role
            for item in proposal.mission.objectives
        ):
            issues.append(
                self._issue(
                    "mission_objective_role_mismatch",
                    "Mission objective roles must exactly match the backend-owned affordance.",
                )
            )
        if any(
            item.candidate_id in candidate_map
            and item.required != candidate_map[item.candidate_id].required
            for item in proposal.mission.objectives
        ):
            issues.append(
                self._issue(
                    "mission_objective_requirement_mismatch",
                    "Mission objective requirement flags must match the backend-owned affordance.",
                )
            )
        if any(
            candidate_map[item].window_id != proposal.selected_window_id
            or not set(candidate_map[item].source_event_ids).issubset(selected_ids)
            for item in objective_ids
            if item in candidate_map
        ):
            issues.append(
                self._issue(
                    "mission_not_linked_to_episode",
                    "Mission candidates must be linked to the selected event window.",
                )
            )
        if any(
            candidate_map[item].recipe != proposal.mission.recipe
            for item in objective_ids
            if item in candidate_map
        ):
            issues.append(
                self._issue(
                    "mission_recipe_mismatch",
                    "Mission recipe is not supported by its selected candidates.",
                )
            )
        if any(
            candidate_map[item].assigned_player_id is not None
            and candidate_map[item].assigned_player_id not in invitation_players
            for item in objective_ids
            if item in candidate_map
        ):
            issues.append(
                self._issue(
                    "mission_assignment_not_permitted",
                    "Mission assignment targets a player who cannot receive an invitation.",
                )
            )

        media_ids = {media.media_id: media for media in prepared.normalized.media_references}
        if proposal.media_id is not None:
            media = media_ids.get(proposal.media_id)
            if media is None:
                issues.append(self._issue("unknown_media_reference", "Media reference is unknown."))
            elif not set(media.event_ids).issubset(selected_ids):
                issues.append(
                    self._issue(
                        "media_outside_episode",
                        "Media reference is not mapped to the selected episode.",
                    )
                )

        claim_ids = [claim.claim_id for claim in proposal.claims]
        if len(claim_ids) != len(set(claim_ids)):
            issues.append(self._issue("duplicate_claim_id", "Claim IDs must be unique."))
        required_sections = {
            "title",
            "notification_teaser",
            "summary",
            "why_this_matters_now",
            "mission",
            *(f"perspective:{item.player_id}" for item in proposal.perspectives),
            *(f"objective:{item.candidate_id}" for item in proposal.mission.objectives),
        }
        claims_by_section: dict[str, list[GroundedClaim]] = {}
        for claim in proposal.claims:
            claims_by_section.setdefault(claim.output_section, []).append(claim)
            issues.extend(
                self._validate_claim(
                    claim,
                    selected_ids=selected_ids,
                    event_map=event_map,
                    eligible_players=eligible_players,
                    candidate_map=candidate_map,
                    prepared=prepared,
                    selected_match_id=proposal.selected_match_id,
                )
            )
        for section in sorted(required_sections - claims_by_section.keys()):
            issues.append(
                self._issue(
                    "missing_section_claim",
                    f"Output section {section} has no structured grounding claim.",
                )
            )
        extra_sections = set(claims_by_section) - required_sections
        if extra_sections:
            issues.append(
                self._issue("unknown_claim_section", "A claim refers to an unknown output section.")
            )
        if any(
            claim.predicate != ClaimPredicate.CURRENT_REUNION_OPPORTUNITY
            for claim in claims_by_section.get("why_this_matters_now", [])
        ):
            issues.append(
                self._issue(
                    "why_now_claim_mismatch",
                    "Why-this-matters-now must use only structured current-context signals.",
                )
            )

        for perspective in proposal.perspectives:
            section = f"perspective:{perspective.player_id}"
            section_claims = claims_by_section.get(section, [])
            participation_evidence = {
                event_id
                for claim in section_claims
                if claim.predicate == ClaimPredicate.PARTICIPATED_MATCH
                for event_id in claim.supporting_event_ids
            }

            def is_supported_collective_claim(
                claim: GroundedClaim,
                participation_evidence: set[str] = participation_evidence,
            ) -> bool:
                return (
                    claim.subject_id == "squad"
                    and claim.predicate != ClaimPredicate.PARTICIPATED_MATCH
                    and bool(claim.supporting_event_ids)
                    and all(
                        event_id in participation_evidence
                        and event_id in event_map
                        and collective_event_includes_full_squad(
                            event_map[event_id],
                            prepared.normalized,
                        )
                        for event_id in claim.supporting_event_ids
                    )
                )

            if any(
                perspective.player_id not in {claim.subject_id, claim.target_id}
                and not is_supported_collective_claim(claim)
                for claim in section_claims
            ):
                issues.append(
                    self._issue(
                        "perspective_claim_subject_mismatch",
                        "A perspective claim must ground that player as actor or target.",
                    )
                )
            perspective_evidence = set(perspective.evidence_event_ids)
            if (
                any(
                    not set(claim.supporting_event_ids).issubset(perspective_evidence)
                    for claim in section_claims
                )
                or {event_id for claim in section_claims for event_id in claim.supporting_event_ids}
                != perspective_evidence
                or any(
                    perspective.player_id
                    not in {event_map[event_id].actor_id, event_map[event_id].target_id}
                    for claim in section_claims
                    if claim.predicate != ClaimPredicate.PARTICIPATED_MATCH
                    for event_id in claim.supporting_event_ids
                    if event_id in event_map
                    and not (
                        event_id in participation_evidence
                        and collective_event_includes_full_squad(
                            event_map[event_id],
                            prepared.normalized,
                        )
                        and claim.subject_id == "squad"
                    )
                )
            ):
                issues.append(
                    self._issue(
                        "perspective_claim_evidence_mismatch",
                        (
                            "Perspective claims must exactly account for declared events that "
                            "involve that player."
                        ),
                    )
                )

        for objective in proposal.mission.objectives:
            candidate = candidate_map.get(objective.candidate_id)
            if candidate is None:
                continue
            section_claims = claims_by_section.get(f"objective:{objective.candidate_id}", [])
            expected_subject = candidate.assigned_player_id or "squad"
            if not section_claims or any(
                claim.predicate != ClaimPredicate.MISSION_RULE
                or claim.subject_id != expected_subject
                or set(claim.supporting_mission_candidate_ids) != {objective.candidate_id}
                for claim in section_claims
            ):
                issues.append(
                    self._issue(
                        "objective_claim_candidate_mismatch",
                        "Objective claims must bind to that exact authorized candidate.",
                    )
                )

        mission_claims = claims_by_section.get("mission", [])
        mission_rule_claims = [
            claim for claim in mission_claims if claim.predicate == ClaimPredicate.MISSION_RULE
        ]
        selected_candidate_ids = set(objective_ids)
        if (
            any(
                not set(claim.supporting_mission_candidate_ids).issubset(selected_candidate_ids)
                for claim in mission_rule_claims
            )
            or {
                candidate_id
                for claim in mission_rule_claims
                for candidate_id in claim.supporting_mission_candidate_ids
            }
            != selected_candidate_ids
        ):
            issues.append(
                self._issue(
                    "mission_claim_candidate_mismatch",
                    "Mission claims must account for exactly the selected candidates.",
                )
            )

        section_text = {
            "title": proposal.title,
            "notification_teaser": proposal.notification_teaser,
            "summary": proposal.summary,
            "why_this_matters_now": proposal.why_this_matters_now,
            # Both fields are AI-authored and player-facing. Validate them as one
            # mission-framing section against the same selected capabilities and
            # source claims; neither field is the executable rule specification.
            "mission": f"{proposal.mission.title}. {proposal.mission.mission}",
            **{f"perspective:{item.player_id}": item.message for item in proposal.perspectives},
            **{
                f"objective:{item.candidate_id}": item.description
                for item in proposal.mission.objectives
            },
        }
        for section, text in section_text.items():
            section_claims = claims_by_section.get(section, [])
            issues.extend(self._validate_prose(section, text, section_claims, prepared))

        deduplicated = self._deduplicate(issues)
        return ProposalValidationReportV2(
            passed=not any(issue.severity == "error" for issue in deduplicated),
            correction_attempted=correction_attempted,
            issues=deduplicated,
        )

    def _validate_memory_framing(
        self,
        proposal: MemoryProposalV2,
        selected_events: list,
        prepared: PreparedInterpretationV2,
    ) -> list[V2ValidationIssue]:
        """Require the delivered memory category and explicit angle claims to fit telemetry."""

        event_types = {event.event_type for event in selected_events}
        history = prepared.normalized.squad_history
        has_prior_squad_history = bool(
            history.previous_session_at
            or history.days_since_full_squad is not None
            or history.recent_rematch_count > 0
        )
        supported = {
            MemoryType.FIRST: not has_prior_squad_history,
            MemoryType.COMEBACK: bool(
                event_types
                & {
                    CanonicalEventType.REVIVE,
                    CanonicalEventType.HEAL,
                    CanonicalEventType.ESCAPE,
                }
            ),
            MemoryType.CLUTCH: bool(
                event_types
                & {
                    CanonicalEventType.KNOCK,
                    CanonicalEventType.ELIMINATION,
                    CanonicalEventType.REVIVE,
                    CanonicalEventType.ESCAPE,
                }
            ),
            MemoryType.RITUAL: bool(
                history.recent_rematch_count > 0 or len(history.previous_session_at) >= 2
            ),
            MemoryType.CHAOS: bool(len(selected_events) >= 3 and len(event_types) >= 2),
            MemoryType.OTHER: True,
        }[proposal.memory_type]
        issues: list[V2ValidationIssue] = []
        if not supported:
            issues.append(
                self._issue(
                    "memory_type_not_supported",
                    "The selected memory type is not supported by the chosen episode and history.",
                )
            )
        if has_prior_squad_history and re.search(
            r"(?i)\b(?:first[- ]ever|first time|debut)\b",
            proposal.narrative_angle,
        ):
            issues.append(
                self._issue(
                    "narrative_angle_not_supported",
                    "The narrative angle claims a first session despite prior squad history.",
                )
            )
        return issues

    def _validate_claim(
        self,
        claim: GroundedClaim,
        *,
        selected_ids: set[str],
        event_map,
        eligible_players,
        candidate_map,
        prepared,
        selected_match_id: str,
    ) -> list[V2ValidationIssue]:
        issues: list[V2ValidationIssue] = []
        if not set(claim.supporting_event_ids).issubset(selected_ids):
            issues.append(
                self._issue(
                    "claim_evidence_outside_episode",
                    "A claim cites evidence outside the selected episode.",
                )
            )
        if claim.predicate in PREDICATE_EVENT_TYPES:
            expected = PREDICATE_EVENT_TYPES[claim.predicate]
            allowed_keys = PREDICATE_DETAIL_KEYS[claim.predicate]
            if (claim.value is None) != (claim.value_key is None) or (
                claim.value_key is not None and claim.value_key not in allowed_keys
            ):
                issues.append(
                    self._issue(
                        "claim_detail_key_not_supported",
                        "Claim value must use a predicate-specific typed detail key.",
                    )
                )
            cited_events = [
                event_map[event_id]
                for event_id in claim.supporting_event_ids
                if event_id in event_map
            ]
            matching = [event for event in cited_events if event.event_type == expected]
            if not matching:
                issues.append(
                    self._issue(
                        "claim_predicate_not_supported",
                        "Claim predicate is not supported by its cited event type.",
                    )
                )
            elif not any(self._event_supports_claim(event, claim) for event in matching):
                issues.append(
                    self._issue(
                        "claim_roles_not_supported",
                        "Claim actor, target, location, or value conflicts with telemetry.",
                    )
                )
        elif claim.value_key is not None:
            issues.append(
                self._issue(
                    "claim_detail_key_not_supported",
                    "Only event claims may use an event detail key.",
                )
            )

        if claim.predicate in MATCH_PREDICATES:
            field = MATCH_PREDICATES[claim.predicate]
            match = next(
                (
                    item
                    for item in prepared.normalized.matches
                    if item.match_id == selected_match_id
                ),
                None,
            )
            expected_id = f"match:{selected_match_id}:{field}"
            expected_value = None
            if match is not None:
                expected_value = {
                    "game": match.game,
                    "mode": match.mode,
                    "map": match.map_name,
                    "placement": match.placement,
                    "result": match.result,
                }[field]
            if (
                claim.subject_id != "squad"
                or expected_id not in claim.supporting_context_ids
                or claim.value != expected_value
            ):
                issues.append(
                    self._issue(
                        "match_metadata_claim_mismatch",
                        "Match metadata claim conflicts with the selected match.",
                    )
                )
        elif claim.predicate == ClaimPredicate.PARTICIPATED_MATCH:
            if claim.subject_id not in eligible_players or not claim.supporting_event_ids:
                issues.append(
                    self._issue(
                        "participation_claim_not_supported",
                        (
                            "Participation claim requires an eligible roster member and "
                            "match evidence."
                        ),
                    )
                )
        elif claim.predicate == ClaimPredicate.CONNECTED_EPISODE:
            if claim.subject_id != "squad" or len(claim.supporting_event_ids) < 2:
                issues.append(
                    self._issue(
                        "episode_claim_not_supported",
                        "Connected-episode claims require at least two selected events.",
                    )
                )
        elif claim.predicate == ClaimPredicate.CURRENT_REUNION_OPPORTUNITY:
            allowed_context = {
                "context:previous_session_at": [
                    item.isoformat()
                    for item in prepared.normalized.squad_history.previous_session_at
                ],
                "context:days_since_full_squad": (
                    prepared.normalized.squad_history.days_since_full_squad
                ),
                "context:recent_rematch_count": (
                    prepared.normalized.squad_history.recent_rematch_count
                ),
                "context:active_player_ids": prepared.normalized.current_context.active_player_ids,
                "context:available_modes": prepared.normalized.current_context.available_modes,
                "context:reunion_eligible": prepared.normalized.current_context.reunion_eligible,
            }
            if not claim.supporting_context_ids or any(
                item not in allowed_context for item in claim.supporting_context_ids
            ):
                issues.append(
                    self._issue(
                        "unsupported_current_context",
                        "Current-context claim cites an unknown structured signal.",
                    )
                )
            elif claim.value is not None and not any(
                claim.value == allowed_context[item] for item in claim.supporting_context_ids
            ):
                issues.append(
                    self._issue(
                        "current_context_value_mismatch",
                        "Current-context claim value does not match its signal.",
                    )
                )
        elif claim.predicate == ClaimPredicate.MISSION_RULE:
            if not claim.supporting_mission_candidate_ids or any(
                item not in candidate_map for item in claim.supporting_mission_candidate_ids
            ):
                issues.append(
                    self._issue(
                        "unsupported_mission_rule",
                        "Mission claim is not backed by an offered capability candidate.",
                    )
                )
        return issues

    @staticmethod
    def _event_supports_claim(event, claim: GroundedClaim) -> bool:
        passive = claim.predicate in {
            ClaimPredicate.WAS_KNOCKED,
            ClaimPredicate.WAS_ELIMINATED,
        }
        expected_subject = (
            event.target_id
            if passive
            else ("squad" if event.event_scope in {"squad", "match"} else event.actor_id)
        )
        if claim.subject_id != expected_subject:
            return False
        if passive and claim.target_id is not None:
            return False
        if not passive and claim.target_id is not None and claim.target_id != event.target_id:
            return False
        if claim.location is not None and claim.location != event.location:
            return False
        if claim.value is not None:
            if claim.value_key is None or event.details.get(claim.value_key) != claim.value:
                return False
        elif claim.value_key is not None:
            return False
        return True

    def _validate_prose(
        self,
        section: str,
        text: str,
        claims: list[GroundedClaim],
        prepared: PreparedInterpretationV2,
    ) -> list[V2ValidationIssue]:
        issues: list[V2ValidationIssue] = []
        normalized = text.casefold()
        predicates = {claim.predicate for claim in claims}
        candidate_predicates = {
            predicate
            for claim in claims
            for candidate_id in claim.supporting_mission_candidate_ids
            for candidate in prepared.mission_candidates
            if candidate.candidate_id == candidate_id
            and candidate.verification.metric in MISSION_METRIC_PREDICATES
            for predicate in MISSION_METRIC_PREDICATES[candidate.verification.metric]
        }
        candidate_player_ids = {
            player_id
            for claim in claims
            for candidate_id in claim.supporting_mission_candidate_ids
            for candidate in prepared.mission_candidates
            if candidate.candidate_id == candidate_id
            and candidate.verification.metric == "squad.participant_ids"
            and isinstance(candidate.verification.target, list)
            for player_id in candidate.verification.target
            if isinstance(player_id, str)
        }
        candidate_player_ids.update(
            str(candidate.verification.target)
            for claim in claims
            for candidate_id in claim.supporting_mission_candidate_ids
            for candidate in prepared.mission_candidates
            if candidate.candidate_id == candidate_id
            and candidate.verification.metric == "match.first_squad_revive_actor_id"
            and isinstance(candidate.verification.target, str)
        )
        candidate_player_ids.update(
            str(candidate.verification.target)
            for claim in claims
            for candidate_id in claim.supporting_mission_candidate_ids
            for candidate in prepared.mission_candidates
            if candidate.candidate_id == candidate_id
            and candidate.verification.metric == "match.first_squad_tactical_signal_actor_id"
            and isinstance(candidate.verification.target, str)
        )
        context_player_ids = {
            player_id
            for claim in claims
            if claim.predicate == ClaimPredicate.CURRENT_REUNION_OPPORTUNITY
            and "context:active_player_ids" in claim.supporting_context_ids
            and isinstance(claim.value, list)
            for player_id in claim.value
            if isinstance(player_id, str)
        }
        selected_candidates = {
            candidate.candidate_id: candidate
            for claim in claims
            for candidate_id in claim.supporting_mission_candidate_ids
            for candidate in prepared.mission_candidates
            if candidate.candidate_id == candidate_id
        }
        selected_affordance_by_candidate = {
            candidate_id: affordance
            for affordance in prepared.mission_affordances
            for candidate_id in affordance.objective_candidate_ids
            if candidate_id in selected_candidates
        }
        candidate_player_ids.update(
            player_id
            for affordance in selected_affordance_by_candidate.values()
            for parameter_name in ("assister_player_id", "elimination_player_id")
            for player_id in [affordance.parameters.get(parameter_name)]
            if isinstance(player_id, str)
        )
        candidate_locations = {
            str(candidate.verification.target)
            for candidate in selected_candidates.values()
            if candidate.verification.metric
            in {
                "match.invited_squad_visits_location",
                "match.invited_squad_lands_at_location",
            }
            and isinstance(candidate.verification.target, str)
        }
        detected_actions = {
            predicate
            for predicate, keywords in ACTION_WORDS.items()
            if any(action_language_present(normalized, keyword) for keyword in keywords)
        }
        allowed_actions = {
            predicate
            for candidate in selected_candidates.values()
            for predicate in MISSION_METRIC_ALLOWED_ACTIONS.get(
                candidate.verification.metric,
                set(),
            )
        }
        supports_top_three = any(
            candidate.verification.metric == "match.top_three_reached"
            for candidate in selected_candidates.values()
        )
        supports_duo_assist = any(
            candidate.verification.metric == "match.assigned_player_assisted_elimination_player_ids"
            for candidate in selected_candidates.values()
        )
        supports_vehicle_extraction = any(
            candidate.verification.metric == "match.invited_squad_vehicle_escape_within_seconds"
            for candidate in selected_candidates.values()
        )
        extra_capability_language = bool(
            re.search(
                r"\b(?:alive|surviv\w*|safe zone|pickup)\b",
                normalized,
            )
            or (
                not supports_vehicle_extraction
                and re.search(r"\b(?:damage zone|danger zone|vehicle)\b", normalized)
            )
            or (
                not supports_top_three
                and re.search(r"\b(?:victory|win|placement|top\s+(?:3|three))\b", normalized)
            )
            or (supports_top_three and MISSION_STRONGER_THAN_TOP_THREE_PATTERN.search(normalized))
            or (not supports_duo_assist and MISSION_COMBAT_PAIR_PATTERN.search(normalized))
            or MISSION_UNOFFERED_CONDITION_PATTERN.search(normalized)
        )
        if selected_candidates and (
            detected_actions - allowed_actions or extra_capability_language
        ):
            issues.append(
                self._issue(
                    "mission_capability_language_mismatch",
                    (
                        f"Section {section} adds gameplay requirements that are not in the "
                        "selected mission capability."
                    ),
                )
            )
        # Mission prose is an AI-authored story bridge, not the executable mission
        # specification. It may omit literal mechanic wording, while any mechanic it
        # does mention must still agree with the selected capability. Objective copy
        # is backend-compiled and checked literally as an internal invariant.
        requires_literal_rule = section.startswith("objective:")
        for candidate in selected_candidates.values():
            metric = candidate.verification.metric
            target = candidate.verification.target
            if isinstance(target, (int, float)) and not isinstance(target, bool):
                mentioned_targets = mission_metric_count_mentions(normalized, metric)
                if not mentioned_targets and requires_literal_rule:
                    issues.append(
                        self._issue(
                            "mission_rule_not_expressed",
                            (
                                f"Section {section} does not state the selected mission metric "
                                "and target."
                            ),
                        )
                    )
                elif any(value is None or value != target for value in mentioned_targets):
                    issues.append(
                        self._issue(
                            "mission_target_mismatch",
                            (
                                f"Section {section} states a target that differs from the "
                                "selected mission capability."
                            ),
                        )
                    )
            elif metric == "squad.participant_ids" and isinstance(target, list):
                player_map = {player.player_id: player for player in prepared.normalized.players}
                target_names = [
                    player_map[player_id].display_name
                    for player_id in target
                    if isinstance(player_id, str) and player_id in player_map
                ]
                names_stated = bool(target_names) and all(
                    contains_identity(text, name) for name in target_names
                )
                invited_group_stated = bool(
                    re.search(
                        r"\b(?:invited|listed)\s+(?:squad|team|players?|squad members?)\b",
                        normalized,
                    )
                )
                play_intent_stated = bool(
                    re.search(r"\bqueue\w*\b", normalized)
                    or (
                        re.search(r"\b(?:play|complete|finish|join)\w*\b", normalized)
                        and re.search(r"\b(?:match|round|game)\b", normalized)
                    )
                )
                if requires_literal_rule and (
                    not play_intent_stated or not (names_stated or invited_group_stated)
                ):
                    issues.append(
                        self._issue(
                            "mission_rule_not_expressed",
                            (
                                f"Section {section} does not state the selected invited-player "
                                "mission requirement."
                            ),
                        )
                    )
            elif metric == "match.first_squad_revive_actor_id" and isinstance(target, str):
                player = next(
                    (item for item in prepared.normalized.players if item.player_id == target),
                    None,
                )
                incorrect_assignee_stated = any(
                    item.player_id != target
                    and item.memory_eligible
                    and assigned_player_performs_first_revive(text, item.display_name)
                    for item in prepared.normalized.players
                )
                if incorrect_assignee_stated:
                    issues.append(
                        self._issue(
                            "mission_target_mismatch",
                            (
                                f"Section {section} assigns the first revival to a player other "
                                "than the selected mission capability."
                            ),
                        )
                    )
                elif requires_literal_rule and (
                    player is None
                    or not assigned_player_performs_first_revive(text, player.display_name)
                ):
                    issues.append(
                        self._issue(
                            "mission_rule_not_expressed",
                            f"Section {section} does not state the assigned first-revival rule.",
                        )
                    )
            elif metric == "match.top_three_reached":
                if requires_literal_rule and not re.search(
                    r"\b(?:top\s+(?:3|three)|third\s+place)\b", normalized
                ):
                    issues.append(
                        self._issue(
                            "mission_rule_not_expressed",
                            f"Section {section} does not state the top-three requirement.",
                        )
                    )
            elif metric == "match.invited_squad_visits_location" and isinstance(target, str):
                location_stated = bool(
                    re.search(rf"(?<!\w){re.escape(target.casefold())}(?!\w)", normalized)
                )
                return_intent_stated = bool(
                    re.search(r"\b(?:return|revisit|go back|head back)\w*\b", normalized)
                )
                invited_group_stated = bool(
                    re.search(
                        r"\b(?:invited|listed)\s+"
                        r"(?:squad|team|players?|squad members?)\b",
                        normalized,
                    )
                )
                if requires_literal_rule and not (
                    location_stated and return_intent_stated and invited_group_stated
                ):
                    issues.append(
                        self._issue(
                            "mission_rule_not_expressed",
                            f"Section {section} does not state the return-to-location requirement.",
                        )
                    )
            elif metric == "match.invited_squad_lands_at_location" and isinstance(target, str):
                location_stated = bool(
                    re.search(rf"(?<!\w){re.escape(target.casefold())}(?!\w)", normalized)
                )
                landing_stated = bool(re.search(r"\bland\w*\b", normalized))
                invited_group_stated = bool(
                    re.search(
                        r"\b(?:invited|listed)\s+(?:squad|team|players?|squad members?)\b",
                        normalized,
                    )
                )
                other_location_stated = any(
                    location.casefold() != target.casefold() and contains_identity(text, location)
                    for match in prepared.normalized.matches
                    for event in match.events
                    for location in [event.location]
                    if location
                )
                alternative_location_stated = bool(
                    re.search(
                        r"\b(?:somewhere|anywhere)\s+else\b|"
                        r"\b(?:another|different)\s+(?:location|place|drop(?: point)?|poi)\b",
                        normalized,
                    )
                )
                explicit_alternate_destination = bool(
                    landing_stated
                    and not location_stated
                    and re.search(r"\bland\w*\s+(?:at|in|near|on)\s+", normalized)
                    and not re.search(
                        r"\bland\w*\s+(?:at|in|near|on)\s+(?:the\s+|a\s+)?"
                        r"(?:named|shared|same|original)\s+"
                        r"(?:drop(?: point)?|location|place|poi)\b",
                        normalized,
                    )
                )
                landing_negated = bool(
                    re.search(
                        r"\b(?:do not|don't|never|avoid|skip)\s+(?:\w+\s+){0,3}land\w*\b",
                        normalized,
                    )
                )
                invited_group_negated = bool(
                    re.search(
                        r"\b(?:alone|solo)\b|\bwithout\s+(?:the\s+)?"
                        r"(?:invited\s+)?(?:squad|team|players?|squad members?)\b",
                        normalized,
                    )
                )
                if landing_stated and (
                    other_location_stated
                    or alternative_location_stated
                    or explicit_alternate_destination
                ):
                    issues.append(
                        self._issue(
                            "mission_target_mismatch",
                            f"Section {section} changes the selected landing location.",
                        )
                    )
                if landing_stated and (landing_negated or invited_group_negated):
                    issues.append(
                        self._issue(
                            "mission_capability_language_mismatch",
                            f"Section {section} contradicts the squad landing requirement.",
                        )
                    )
                if requires_literal_rule and not (
                    location_stated and landing_stated and invited_group_stated
                ):
                    issues.append(
                        self._issue(
                            "mission_rule_not_expressed",
                            f"Section {section} does not state the landing-rendezvous requirement.",
                        )
                    )
            elif metric == "match.assigned_player_assisted_elimination_player_ids" and isinstance(
                target, list
            ):
                affordance = selected_affordance_by_candidate.get(candidate.candidate_id)
                assister_id = (
                    affordance.parameters.get("assister_player_id") if affordance else None
                )
                teammate_id = (
                    affordance.parameters.get("elimination_player_id") if affordance else None
                )
                player_map = {player.player_id: player for player in prepared.normalized.players}
                mentioned_counts = mission_metric_count_mentions(normalized, metric)
                if any(count is None or count != 1 for count in mentioned_counts):
                    issues.append(
                        self._issue(
                            "mission_target_mismatch",
                            f"Section {section} changes the selected duo-assist count.",
                        )
                    )
                if requires_literal_rule and (
                    not isinstance(assister_id, str)
                    or not isinstance(teammate_id, str)
                    or target != [teammate_id]
                    or assister_id not in player_map
                    or teammate_id not in player_map
                    or not contains_identity(text, player_map[assister_id].display_name)
                    or not contains_identity(text, player_map[teammate_id].display_name)
                    or not re.search(r"\bassist\w*\b", normalized)
                    or not re.search(r"\beliminat\w*\b", normalized)
                ):
                    issues.append(
                        self._issue(
                            "mission_rule_not_expressed",
                            f"Section {section} does not state the assigned duo-assist rule.",
                        )
                    )
            elif metric == "match.first_squad_tactical_signal_actor_id" and isinstance(target, str):
                player_map = {player.player_id: player for player in prepared.normalized.players}
                player = player_map.get(target)
                wrong_assignee = any(
                    player_id != target
                    and assigned_player_performs_first_signal(text, item.display_name)
                    for player_id, item in player_map.items()
                    if item.memory_eligible
                )
                if wrong_assignee:
                    issues.append(
                        self._issue(
                            "mission_target_mismatch",
                            f"Section {section} assigns the tactical signal to another player.",
                        )
                    )
                elif requires_literal_rule and (
                    player is None
                    or not assigned_player_performs_first_signal(
                        text,
                        player.display_name,
                    )
                ):
                    issues.append(
                        self._issue(
                            "mission_rule_not_expressed",
                            f"Section {section} does not state the assigned first-signal rule.",
                        )
                    )
            elif metric == "match.invited_squad_vehicle_escape_within_seconds":
                affordance = selected_affordance_by_candidate.get(candidate.candidate_id)
                maximum_seconds = (
                    affordance.parameters.get("vehicle_escape_window_seconds")
                    if affordance
                    else None
                )
                mentioned_seconds = mission_metric_count_mentions(normalized, metric)
                if any(value is None or value != maximum_seconds for value in mentioned_seconds):
                    issues.append(
                        self._issue(
                            "mission_target_mismatch",
                            f"Section {section} changes the vehicle-extraction time window.",
                        )
                    )
                boarding_stated = bool(
                    re.search(
                        r"\b(?:board|boards|enter|enters|get|gets|hop|hops|pile|piles)\w*"
                        r"(?:\s+\w+){0,3}\s+vehicle\b",
                        normalized,
                    )
                )
                escape_stated = bool(
                    re.search(
                        r"\b(?:leave|leaves|escape|escapes|get|gets|make|makes)\w*\b",
                        normalized,
                    )
                    and re.search(r"\b(?:danger|damage)\s+zone\b", normalized)
                )
                invited_group_stated = bool(
                    re.search(
                        r"\b(?:invited|listed)\s+(?:squad|team|players?|squad members?)\b",
                        normalized,
                    )
                )
                time_window_stated = bool(
                    isinstance(maximum_seconds, int)
                    and re.search(
                        rf"\bwithin\s+{maximum_seconds}\s+seconds?\b",
                        normalized,
                    )
                )
                if requires_literal_rule and not (
                    boarding_stated
                    and escape_stated
                    and invited_group_stated
                    and time_window_stated
                ):
                    issues.append(
                        self._issue(
                            "mission_rule_not_expressed",
                            f"Section {section} does not state the full-squad extraction rule.",
                        )
                    )
            operator = candidate.verification.operator
            metric_nouns = MISSION_METRIC_NOUNS.get(metric, ())
            metric_clauses = [
                clause
                for clause in re.split(r"[.!?;,]|\b(?:and|then)\b", normalized)
                if any(
                    re.search(rf"(?<!\w){re.escape(noun)}(?!\w)", clause) for noun in metric_nouns
                )
            ]
            operator_mismatch = bool(
                isinstance(target, (int, float))
                and not isinstance(target, bool)
                and (
                    (
                        operator == "equals"
                        and any(
                            re.search(r"\b(?:at least|or more|minimum)\b", clause)
                            for clause in metric_clauses
                        )
                    )
                    or (
                        operator == "at_least"
                        and any(
                            re.search(r"\b(?:exactly|no more than|at most)\b", clause)
                            for clause in metric_clauses
                        )
                    )
                )
            )
            if operator_mismatch:
                issues.append(
                    self._issue(
                        "mission_operator_mismatch",
                        (
                            f"Section {section} states an operator that differs from the "
                            "selected mission capability."
                        ),
                    )
                )
        for predicate, keywords in ACTION_WORDS.items():
            equivalent = {predicate}
            if predicate == ClaimPredicate.KNOCKED:
                equivalent.add(ClaimPredicate.WAS_KNOCKED)
            elif predicate == ClaimPredicate.ELIMINATED:
                equivalent.update({ClaimPredicate.WAS_ELIMINATED, ClaimPredicate.MATCH_RESULT})
            if any(action_language_present(normalized, keyword) for keyword in keywords) and not (
                equivalent & (predicates | candidate_predicates)
            ):
                issues.append(
                    self._issue(
                        "unmapped_action_language",
                        f"Section {section} contains action language without a matching claim.",
                    )
                )
                break
        if UNSUPPORTED_OBSERVATION_PATTERN.search(normalized):
            issues.append(
                self._issue(
                    "unsupported_observation_language",
                    f"Section {section} states an observation that telemetry does not record.",
                )
            )
        for player in prepared.normalized.players:
            if (
                player.memory_eligible
                and contains_identity(text, player.display_name)
                and not any(
                    claim.subject_id == player.player_id or claim.target_id == player.player_id
                    for claim in claims
                )
                and player.player_id not in candidate_player_ids
                and player.player_id not in context_player_ids
            ):
                issues.append(
                    self._issue(
                        "unmapped_player_identity",
                        f"Section {section} names a player without a matching claim role.",
                    )
                )
                break
        locations = {
            event.location
            for match in prepared.normalized.matches
            for event in match.events
            if event.location
        }
        for location in locations:
            if (
                contains_identity(text, location)
                and not any(claim.location == location for claim in claims)
                and location not in candidate_locations
            ):
                issues.append(
                    self._issue(
                        "unmapped_location",
                        f"Section {section} names a location without a matching claim.",
                    )
                )
                break
        categorical_terms = {
            key: set(values) - {"other", "unknown"}
            for key, values in ALLOWED_CATEGORICAL_DETAILS.items()
        }
        categorical_terms["vehicle_type"].update(KNOWN_UNSUPPORTED_VEHICLES)
        for key, values in categorical_terms.items():
            if key == "health_state" and not any(
                term in normalized for term in ("health", " hp", "healed")
            ):
                continue
            if key == "zone_state" and "zone" not in normalized:
                continue
            if key == "weapon_class" and not any(
                term in normalized for term in ("weapon", "gun", "rifle", "shotgun", "sniper")
            ):
                continue
            if key == "ping_type" and not any(
                action_language_present(normalized, term) for term in ("ping", "signal")
            ):
                continue
            if key == "item_type" and not any(term in normalized for term in ("loot", "supply")):
                continue
            for value in values:
                display_value = value.replace("_", " ")
                if contains_identity(text, display_value) and not any(
                    claim.value_key == key
                    and isinstance(claim.value, str)
                    and claim.value.casefold() == value.casefold()
                    for claim in claims
                ):
                    issues.append(
                        self._issue(
                            "unsupported_categorical_detail",
                            (
                                f"Section {section} uses a categorical telemetry value without "
                                "matching typed evidence."
                            ),
                        )
                    )
                    break
        for match in prepared.normalized.matches:
            match_terms = (
                (match.game.replace("_", " "), ClaimPredicate.PLAYED_GAME),
                (match.map_name, ClaimPredicate.PLAYED_MAP),
                (match.mode.replace("_", " "), ClaimPredicate.PLAYED_MODE),
                (match.result, ClaimPredicate.MATCH_RESULT),
            )
            for value, predicate in match_terms:
                supported_by_available_modes = bool(
                    predicate == ClaimPredicate.PLAYED_MODE
                    and any(
                        claim.predicate == ClaimPredicate.CURRENT_REUNION_OPPORTUNITY
                        and "context:available_modes" in claim.supporting_context_ids
                        and isinstance(claim.value, list)
                        and any(
                            isinstance(item, str)
                            and item.casefold().replace("_", " ") == value.casefold()
                            for item in claim.value
                        )
                        for claim in claims
                    )
                )
                if (
                    value
                    and value.casefold() in normalized
                    and not supported_by_available_modes
                    and not any(
                        claim.predicate == predicate
                        and isinstance(claim.value, str)
                        and claim.value.casefold().replace("_", " ") == value.casefold()
                        for claim in claims
                    )
                ):
                    issues.append(
                        self._issue(
                            "unmapped_match_metadata",
                            f"Section {section} uses match metadata without a matching claim.",
                        )
                    )
                    break
        if any(word in normalized for word in VICTORY_WORDS):
            if not any(
                claim.predicate == ClaimPredicate.MATCH_RESULT
                and isinstance(claim.value, str)
                and claim.value.casefold() in VICTORY_RESULTS
                for claim in claims
            ):
                issues.append(
                    self._issue(
                        "unsupported_outcome_language",
                        f"Section {section} claims a victory without a matching result.",
                    )
                )
        if any(term in normalized for term in ("survived", "survive", "alive")) and not any(
            (
                claim.predicate == ClaimPredicate.MATCH_RESULT
                and isinstance(claim.value, str)
                and "surviv" in claim.value.casefold()
            )
            or (
                claim.value_key in {"squad_members_alive", "squad_alive"}
                and isinstance(claim.value, int)
                and claim.value > 0
            )
            for claim in claims
        ):
            issues.append(
                self._issue(
                    "unsupported_outcome_language",
                    f"Section {section} claims survival without a matching result.",
                )
            )
        if any(term in normalized for term in ("airdrop", "air drop", "supply drop")):
            if not any(
                claim.predicate == ClaimPredicate.LOOTED
                and claim.value_key == "item_type"
                and isinstance(claim.value, str)
                and claim.value.casefold() in {"airdrop", "air_drop", "supply_drop"}
                for claim in claims
            ):
                issues.append(
                    self._issue(
                        "unsupported_loot_source",
                        f"Section {section} invents an unsupported loot source.",
                    )
                )
        action_count_patterns = (
            (
                {ClaimPredicate.REVIVED},
                (r"reviv\w*\D{0,8}(\d+)\s*times?", r"(\d+)\s*revives?"),
            ),
            (
                {ClaimPredicate.KNOCKED, ClaimPredicate.WAS_KNOCKED},
                (r"knock\w*\D{0,8}(\d+)\s*times?", r"(\d+)\s*knocks?"),
            ),
            (
                {ClaimPredicate.ELIMINATED, ClaimPredicate.WAS_ELIMINATED},
                (r"eliminat\w*\D{0,8}(\d+)\s*times?", r"(\d+)\s*eliminations?"),
            ),
        )
        for allowed_predicates, patterns in action_count_patterns:
            claimed_counts = {
                claim.value
                for claim in claims
                if claim.predicate in allowed_predicates
                and claim.value_key == "count"
                and isinstance(claim.value, int)
                and not isinstance(claim.value, bool)
            }
            mentioned_counts = {
                int(match.group(1))
                for pattern in patterns
                for match in re.finditer(pattern, normalized)
            }
            if mentioned_counts - claimed_counts:
                issues.append(
                    self._issue(
                        "unsupported_action_count",
                        f"Section {section} states an action count without typed count evidence.",
                    )
                )
                break
        issues.extend(self._validate_action_roles(section, text, claims, prepared))
        numeric_text = text
        for player in prepared.normalized.players:
            if player.memory_eligible:
                numeric_text = re.sub(
                    identity_pattern(player.display_name),
                    "",
                    numeric_text,
                    flags=re.IGNORECASE,
                )
        numeric_values = {int(value) for value in re.findall(r"\b\d+\b", numeric_text)}
        supported_numbers = {
            claim.value
            for claim in claims
            if isinstance(claim.value, (int, float)) and not isinstance(claim.value, bool)
        }
        supported_numbers.update(
            int(value)
            for claim in claims
            if claim.predicate == ClaimPredicate.CURRENT_REUNION_OPPORTUNITY
            and "context:previous_session_at" in claim.supporting_context_ids
            and isinstance(claim.value, list)
            for item in claim.value
            if isinstance(item, str)
            for value in re.findall(r"\d+", item)
        )
        for claim in claims:
            for candidate_id in claim.supporting_mission_candidate_ids:
                candidate = next(
                    (
                        item
                        for item in prepared.mission_candidates
                        if item.candidate_id == candidate_id
                    ),
                    None,
                )
                if (
                    candidate
                    and isinstance(candidate.verification.target, (int, float))
                    and not isinstance(candidate.verification.target, bool)
                ):
                    supported_numbers.add(candidate.verification.target)
                if candidate and candidate.verification.metric == "match.top_three_reached":
                    supported_numbers.update(
                        placement
                        for affordance in prepared.mission_affordances
                        if candidate.candidate_id in affordance.objective_candidate_ids
                        for placement in [affordance.parameters.get("target_placement_max")]
                        if type(placement) is int
                    )
                if (
                    candidate
                    and candidate.verification.metric
                    == "match.invited_squad_vehicle_escape_within_seconds"
                ):
                    supported_numbers.add(1)
                    supported_numbers.update(
                        seconds
                        for affordance in prepared.mission_affordances
                        if candidate.candidate_id in affordance.objective_candidate_ids
                        for seconds in [affordance.parameters.get("vehicle_escape_window_seconds")]
                        if type(seconds) is int
                    )
        if numeric_values - supported_numbers:
            issues.append(
                self._issue(
                    "unmapped_numeric_claim",
                    f"Section {section} contains a number without structured support.",
                )
            )
        return issues

    def _validate_action_roles(
        self,
        section: str,
        text: str,
        claims: list[GroundedClaim],
        prepared: PreparedInterpretationV2,
    ) -> list[V2ValidationIssue]:
        """Reject direct actor/target wording unless one claim supports the full tuple."""

        normalized = text.casefold()
        mission_candidate_ids = {
            candidate_id
            for claim in claims
            for candidate_id in claim.supporting_mission_candidate_ids
        }
        mission_candidates = [
            candidate
            for candidate in prepared.mission_candidates
            if candidate.candidate_id in mission_candidate_ids
        ]
        authorized_future_revivers = {
            str(candidate.verification.target)
            for candidate in mission_candidates
            if candidate.verification.metric == "match.first_squad_revive_actor_id"
            and isinstance(candidate.verification.target, str)
        }
        authorized_signal_actors = {
            str(candidate.verification.target)
            for candidate in mission_candidates
            if candidate.verification.metric == "match.first_squad_tactical_signal_actor_id"
            and isinstance(candidate.verification.target, str)
        }
        authorized_vehicle_extraction = any(
            candidate.verification.metric == "match.invited_squad_vehicle_escape_within_seconds"
            for candidate in mission_candidates
        )
        authorized_match_players = {
            player_id
            for candidate in mission_candidates
            if candidate.verification.metric == "squad.participant_ids"
            and isinstance(candidate.verification.target, list)
            for player_id in candidate.verification.target
            if isinstance(player_id, str)
        }
        authorized_assist_pairs = {
            (assister_id, teammate_id)
            for affordance in prepared.mission_affordances
            if any(
                candidate.candidate_id in affordance.objective_candidate_ids
                and candidate.verification.metric
                == "match.assigned_player_assisted_elimination_player_ids"
                for candidate in mission_candidates
            )
            for assister_id in [affordance.parameters.get("assister_player_id")]
            for teammate_id in [affordance.parameters.get("elimination_player_id")]
            if isinstance(assister_id, str) and isinstance(teammate_id, str)
        }
        authorized_assist_eliminators = {teammate_id for _, teammate_id in authorized_assist_pairs}
        authorized_future_landers = {
            player_id
            for affordance in prepared.mission_affordances
            if any(
                candidate.candidate_id in affordance.objective_candidate_ids
                and candidate.verification.metric == "match.invited_squad_lands_at_location"
                for candidate in mission_candidates
            )
            for invitation_player_ids in [affordance.parameters.get("invitation_player_ids")]
            if isinstance(invitation_player_ids, list)
            for player_id in invitation_player_ids
            if isinstance(player_id, str)
        }
        references = [
            (player.player_id, player.display_name.casefold())
            for player in prepared.normalized.players
            if player.memory_eligible
        ]
        if section.startswith("perspective:"):
            perspective_id = section.removeprefix("perspective:")
            if any(
                player.player_id == perspective_id
                for player in prepared.normalized.players
                if player.memory_eligible
            ):
                references.extend(
                    (
                        (perspective_id, "you"),
                        (perspective_id, "your"),
                        (perspective_id, "i"),
                        (perspective_id, "my"),
                        (perspective_id, "me"),
                    )
                )
        else:
            references.extend(
                (
                    (prepared.normalized.target_player_id, "you"),
                    (prepared.normalized.target_player_id, "your"),
                )
            )
        reference_matches = [
            (match.start(), match.end(), player_id)
            for player_id, reference in references
            for match in re.finditer(rf"(?<!\w){re.escape(reference)}(?!\w)", normalized)
        ]
        collective_actor_matches = [
            (match.start(), match.end(), "squad")
            for match in re.finditer(
                r"(?<!\w)(?:we all|we|the squad|our squad|your squad)(?!\w)",
                normalized,
            )
        ]
        if not reference_matches and not collective_actor_matches:
            return []

        for predicate in ROLE_ACTION_PREDICATES:
            terms = sorted(set(ACTION_WORDS[predicate]), key=len, reverse=True)
            action_pattern = r"(?<!\w)(?:" + "|".join(map(re.escape, terms)) + r")(?!\w)"
            for action in re.finditer(action_pattern, normalized):
                clause_marks = ".!?;,\n"
                sentence_start = (
                    max(normalized.rfind(mark, 0, action.start()) for mark in clause_marks) + 1
                )
                sentence_end_candidates = [
                    position
                    for mark in clause_marks
                    if (position := normalized.find(mark, action.end())) >= 0
                ]
                sentence_end = min(sentence_end_candidates, default=len(normalized))
                before = [
                    item for item in reference_matches if sentence_start <= item[0] < action.start()
                ]
                after = [
                    item for item in reference_matches if action.end() <= item[0] <= sentence_end
                ]
                actor_id: str | None = None
                actor_bridge = ""
                if before:
                    actor = max(before, key=lambda item: item[1])
                    actor_bridge = normalized[actor[1] : action.start()]
                    if len(actor_bridge) <= 24 and not re.search(
                        r"\b(?:was|were|got|being|been|by|and|then|while|before|after|when|as|but)\b",
                        actor_bridge,
                    ):
                        actor_id = actor[2]
                collective_before = [
                    item
                    for item in collective_actor_matches
                    if sentence_start <= item[0] < action.start()
                ]
                if collective_before:
                    collective_actor = max(collective_before, key=lambda item: item[1])
                    collective_bridge = normalized[collective_actor[1] : action.start()]
                    nearest_player_end = max((item[1] for item in before), default=-1)
                    possessive_collective = bool(re.search(r"['’]s\b", collective_bridge))
                    squad_claim_supports_action = any(
                        claim.predicate == predicate and claim.subject_id == "squad"
                        for claim in claims
                    )
                    if (
                        collective_actor[1] >= nearest_player_end
                        and len(collective_bridge) <= 24
                        and not re.search(
                            r"\b(?:was|were|got|being|been|by|and|then|while|before|after|when|as|but)\b",
                            collective_bridge,
                        )
                        and (
                            not possessive_collective
                            or squad_claim_supports_action
                            or nearest_player_end < 0
                        )
                    ):
                        actor_id = "squad"
                        actor_bridge = collective_bridge
                target_id: str | None = None
                if after:
                    target = min(after, key=lambda item: item[0])
                    bridge = normalized[action.end() : target[0]]
                    if len(bridge) <= 24 and not re.search(
                        r"\b(?:and|then|while|before|after|when|as|by|but)\b",
                        bridge,
                    ):
                        target_id = target[2]

                actor_role_supported = actor_id is not None and any(
                    claim.predicate == predicate
                    and claim.subject_id == actor_id
                    and (target_id is None or claim.target_id == target_id)
                    for claim in claims
                )
                mission_actor_role_supported = bool(
                    actor_id is not None
                    and (
                        (
                            predicate == ClaimPredicate.REVIVED
                            and target_id is None
                            and actor_id in authorized_future_revivers
                        )
                        or (
                            predicate == ClaimPredicate.COMPLETED_MATCH
                            and target_id is None
                            and actor_id in authorized_match_players
                        )
                        or (
                            predicate == ClaimPredicate.ASSISTED
                            and target_id is not None
                            and (actor_id, target_id) in authorized_assist_pairs
                        )
                        or (
                            predicate == ClaimPredicate.ELIMINATED
                            and target_id is None
                            and actor_id in authorized_assist_eliminators
                        )
                        or (
                            predicate == ClaimPredicate.LANDED
                            and target_id is None
                            and (
                                actor_id in authorized_future_landers
                                or (actor_id == "squad" and bool(authorized_future_landers))
                            )
                        )
                        or (
                            predicate == ClaimPredicate.SIGNALLED
                            and target_id is None
                            and actor_id in authorized_signal_actors
                        )
                        or (
                            predicate in {ClaimPredicate.ENTERED_VEHICLE, ClaimPredicate.ESCAPED}
                            and target_id is None
                            and actor_id == "squad"
                            and authorized_vehicle_extraction
                        )
                    )
                )
                affected_player_idiom_supported = bool(
                    actor_id is not None
                    and predicate == ClaimPredicate.KNOCKED
                    and re.search(r"\b(?:took|suffered)\s+(?:a\s+)?$", actor_bridge)
                    and any(
                        claim.predicate == ClaimPredicate.WAS_KNOCKED
                        and claim.subject_id == actor_id
                        for claim in claims
                    )
                )
                if (
                    actor_id is not None
                    and not actor_role_supported
                    and not mission_actor_role_supported
                    and not affected_player_idiom_supported
                ):
                    return [
                        self._issue(
                            "action_role_mismatch",
                            f"Section {section} assigns an action to an unsupported player role.",
                        )
                    ]
                if (
                    actor_id is None
                    and target_id is not None
                    and not any(
                        (claim.predicate == predicate and claim.target_id == target_id)
                        or (
                            claim.predicate == PASSIVE_ACTION_PREDICATES.get(predicate)
                            and claim.subject_id == target_id
                        )
                        for claim in claims
                    )
                ):
                    return [
                        self._issue(
                            "action_role_mismatch",
                            f"Section {section} assigns an action to an unsupported player role.",
                        )
                    ]

                for player_id, reference in references:
                    passive_pattern = (
                        rf"(?<!\w){re.escape(reference)}(?!\w)\s+"
                        rf"(?:was|were|got|being)\s+{action_pattern}"
                    )
                    passive_match = re.search(passive_pattern, normalized)
                    if passive_match is None:
                        continue
                    passive_end_candidates = [
                        position
                        for mark in ".!?;,\n"
                        if (position := normalized.find(mark, passive_match.end())) >= 0
                    ]
                    passive_end = min(passive_end_candidates, default=len(normalized))
                    passive_tail = normalized[passive_match.end() : passive_end]
                    by_actor_ids = {
                        actor_player_id
                        for actor_player_id, actor_reference in references
                        if re.search(
                            rf"\bby\s+{re.escape(actor_reference)}(?!\w)",
                            passive_tail,
                        )
                    }
                    if by_actor_ids:
                        passive_supported = any(
                            claim.predicate == predicate
                            and claim.subject_id in by_actor_ids
                            and claim.target_id == player_id
                            for claim in claims
                        )
                    else:
                        passive_supported = any(
                            (claim.predicate == predicate and claim.target_id == player_id)
                            or (
                                claim.predicate == PASSIVE_ACTION_PREDICATES.get(predicate)
                                and claim.subject_id == player_id
                            )
                            for claim in claims
                        )
                    if not passive_supported:
                        return [
                            self._issue(
                                "action_role_mismatch",
                                (
                                    f"Section {section} assigns an action to an unsupported "
                                    "player role."
                                ),
                            )
                        ]
        return []

    @staticmethod
    def _normalize_text(value: str) -> str:
        return " ".join(value.casefold().split())

    @staticmethod
    def _issue(code: str, message: str) -> V2ValidationIssue:
        return V2ValidationIssue(code=code, severity="error", message=message)

    @staticmethod
    def _deduplicate(issues: list[V2ValidationIssue]) -> list[V2ValidationIssue]:
        seen: set[tuple[str, str]] = set()
        result: list[V2ValidationIssue] = []
        for issue in issues:
            key = (issue.code, issue.message)
            if key not in seen:
                seen.add(key)
                result.append(issue)
        return result
