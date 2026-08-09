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
            candidate,
            safe_player_display_names,
        )
    return descriptions


def _compile_candidate(
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
        return "Play a match with the invited squad."

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
