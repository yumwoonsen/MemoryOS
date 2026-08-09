"""Deterministically compile player-facing copy for backend-owned mission rules."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from backend.models.v2_schemas import MissionAffordanceV2, MissionCapabilityCandidate


class MissionCopyCompilationError(ValueError):
    """Raised when an affordance cannot be compiled without changing its rules."""


def compile_mission_objective_descriptions(
    affordance: MissionAffordanceV2,
    ordered_candidates: Sequence[MissionCapabilityCandidate],
    safe_player_display_names: Mapping[str, str],
) -> dict[str, str]:
    """Return canonical copy keyed by candidate ID, preserving objective order.

    The compiler owns only the wording of backend-authored verification rules. It
    deliberately fails closed when a selected candidate is missing, reordered, or
    cannot be expressed by one of the currently supported mission capabilities.
    """

    candidate_ids = [candidate.candidate_id for candidate in ordered_candidates]
    if candidate_ids != affordance.objective_candidate_ids:
        raise MissionCopyCompilationError(
            "ordered candidates must exactly match the affordance objective order"
        )
    if len(candidate_ids) != len(set(candidate_ids)):
        raise MissionCopyCompilationError("objective candidate IDs must be unique")

    descriptions: dict[str, str] = {}
    for candidate in ordered_candidates:
        if candidate.window_id != affordance.window_id:
            raise MissionCopyCompilationError(
                f"candidate {candidate.candidate_id} belongs to a different event window"
            )
        descriptions[candidate.candidate_id] = _compile_candidate(
            affordance,
            candidate,
            safe_player_display_names,
        )
    return descriptions


def _compile_candidate(
    affordance: MissionAffordanceV2,
    candidate: MissionCapabilityCandidate,
    safe_player_display_names: Mapping[str, str],
) -> str:
    rule = candidate.verification
    metric = rule.metric

    if metric == "squad.participant_ids":
        if (
            rule.operator != "contains_all"
            or not isinstance(rule.target, list)
            or not rule.target
            or len(rule.target) != len(set(rule.target))
            or candidate.assigned_player_id is not None
        ):
            raise MissionCopyCompilationError(
                f"candidate {candidate.candidate_id} has an invalid invited-squad rule"
            )
        missing_players = [
            player_id for player_id in rule.target if player_id not in safe_player_display_names
        ]
        if missing_players:
            raise MissionCopyCompilationError(
                f"candidate {candidate.candidate_id} references a player outside the safe map"
            )
        return "Queue into a match with the invited squad."

    if metric == "squad.matches_completed":
        if (
            rule.operator != "at_least"
            or isinstance(rule.target, bool)
            or not isinstance(rule.target, int)
            or rule.target < 1
            or candidate.assigned_player_id is not None
        ):
            raise MissionCopyCompilationError(
                f"candidate {candidate.candidate_id} has an invalid match-completion rule"
            )
        noun = "match" if rule.target == 1 else "matches"
        return f"Complete at least {rule.target} {noun}."

    if metric == "match.first_squad_revive_actor_id":
        if (
            rule.operator != "equals"
            or not isinstance(rule.target, str)
            or not rule.target
            or candidate.assigned_player_id != rule.target
        ):
            raise MissionCopyCompilationError(
                f"candidate {candidate.candidate_id} has an inconsistent first-revive assignment"
            )
        display_name = _safe_display_name(rule.target, safe_player_display_names)
        return f"{display_name} completes the squad's first revive."

    if metric == "match.top_three_reached":
        if (
            rule.operator != "equals"
            or rule.target is not True
            or candidate.assigned_player_id is not None
        ):
            raise MissionCopyCompilationError(
                f"candidate {candidate.candidate_id} has an invalid top-three rule"
            )
        return "Reach the top 3 in the new match."

    if metric == "match.invited_squad_visits_location":
        if (
            rule.operator != "equals"
            or not isinstance(rule.target, str)
            or not rule.target.strip()
            or candidate.assigned_player_id is not None
        ):
            raise MissionCopyCompilationError(
                f"candidate {candidate.candidate_id} has an invalid squad-location rule"
            )
        return f"Return to {rule.target} with the invited squad."

    if metric == "match.invited_squad_lands_at_location":
        invitation_player_ids = affordance.parameters.get("invitation_player_ids")
        if (
            rule.operator != "equals"
            or not isinstance(rule.target, str)
            or not rule.target.strip()
            or candidate.assigned_player_id is not None
            or affordance.parameters.get("landing_location") != rule.target
            or not isinstance(invitation_player_ids, list)
            or not invitation_player_ids
            or any(
                not isinstance(player_id, str)
                or player_id not in safe_player_display_names
                for player_id in invitation_player_ids
            )
        ):
            raise MissionCopyCompilationError(
                f"candidate {candidate.candidate_id} has an invalid landing-rendezvous rule"
            )
        return f"Land at {rule.target} with the invited squad."

    if metric == "match.assigned_player_assisted_elimination_player_ids":
        assister_id = affordance.parameters.get("assister_player_id")
        teammate_id = affordance.parameters.get("elimination_player_id")
        if (
            rule.operator != "contains_all"
            or rule.target != [teammate_id]
            or candidate.assigned_player_id != assister_id
            or not isinstance(assister_id, str)
            or not isinstance(teammate_id, str)
            or assister_id == teammate_id
        ):
            raise MissionCopyCompilationError(
                f"candidate {candidate.candidate_id} has an invalid duo-assist rule"
            )
        assister_name = _safe_display_name(assister_id, safe_player_display_names)
        teammate_name = _safe_display_name(teammate_id, safe_player_display_names)
        return f"{assister_name} assists {teammate_name} with an elimination."

    if metric == "match.first_squad_tactical_signal_actor_id":
        signal_player_id = affordance.parameters.get("signal_player_id")
        if (
            rule.operator != "equals"
            or not isinstance(rule.target, str)
            or not rule.target
            or candidate.assigned_player_id != rule.target
            or signal_player_id != rule.target
        ):
            raise MissionCopyCompilationError(
                f"candidate {candidate.candidate_id} has an invalid tactical-signal rule"
            )
        display_name = _safe_display_name(rule.target, safe_player_display_names)
        return f"{display_name} places the squad's first tactical signal."

    if metric == "match.invited_squad_vehicle_escape_within_seconds":
        invitation_player_ids = affordance.parameters.get("invitation_player_ids")
        maximum_seconds = affordance.parameters.get("vehicle_escape_window_seconds")
        if (
            rule.operator != "equals"
            or rule.target is not True
            or candidate.assigned_player_id is not None
            or not isinstance(invitation_player_ids, list)
            or len(invitation_player_ids) < 2
            or len(invitation_player_ids) != len(set(invitation_player_ids))
            or any(
                not isinstance(player_id, str)
                or player_id not in safe_player_display_names
                for player_id in invitation_player_ids
            )
            or isinstance(maximum_seconds, bool)
            or not isinstance(maximum_seconds, int)
            or not 1 <= maximum_seconds <= 300
        ):
            raise MissionCopyCompilationError(
                f"candidate {candidate.candidate_id} has an invalid vehicle-extraction rule"
            )
        return (
            "Board one vehicle with the invited squad and leave the danger zone together "
            f"within {maximum_seconds} seconds."
        )

    raise MissionCopyCompilationError(
        f"candidate {candidate.candidate_id} uses unsupported metric {metric!r}"
    )


def _safe_display_name(player_id: str, safe_player_display_names: Mapping[str, str]) -> str:
    display_name = safe_player_display_names.get(player_id)
    if (
        not isinstance(display_name, str)
        or not display_name
        or display_name != display_name.strip()
        or len(display_name) > 64
        or any(ord(character) < 32 for character in display_name)
    ):
        raise MissionCopyCompilationError(
            f"player {player_id!r} has no safe display name for mission copy"
        )
    return display_name
