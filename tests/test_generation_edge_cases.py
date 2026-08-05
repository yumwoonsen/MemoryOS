"""Focused regressions for sanitized evidence and deterministic generation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.agents.memory_agent import MemoryAgent
from backend.agents.quest_agent import QuestAgent
from backend.models.schemas import MemoryPack
from backend.services.evidence import literal_passenger_target, sanitize_memory_pack

DATA_DIR = Path(__file__).resolve().parents[1] / "backend" / "data"


def _payload() -> dict[str, Any]:
    return json.loads((DATA_DIR / "funny_memory.json").read_text(encoding="utf-8"))


def _rename_player(payload: dict[str, Any], old_id: str, new_id: str) -> None:
    for member in payload["squad"]["members"]:
        if member["player_id"] == old_id:
            member["player_id"] = new_id
    if payload["player_profile"]["player_id"] == old_id:
        payload["player_profile"]["player_id"] = new_id
    for event in payload["match_events"]:
        if event.get("actor_id") == old_id:
            event["actor_id"] = new_id
        if event.get("target_id") == old_id:
            event["target_id"] = new_id
    payload["current_context"]["active_member_ids"] = [
        new_id if player_id == old_id else player_id
        for player_id in payload["current_context"]["active_member_ids"]
    ]
    if payload.get("human_memory", {}).get("author_player_id") == old_id:
        payload["human_memory"]["author_player_id"] = new_id


def test_sanitizer_allocates_stable_aliases_outside_real_roster_namespaces() -> None:
    payload = _payload()
    _rename_player(payload, "mei", "anonymous_squadmate_1")
    for member in payload["squad"]["members"]:
        if member["player_id"] == "anonymous_squadmate_1":
            member["display_name"] = "Anonymous squadmate 1"
        if member["player_id"] == "jo":
            member["opted_in"] = False

    pack = MemoryPack.model_validate(payload)
    safe_pack, redactions = sanitize_memory_pack(pack)
    reordered = pack.model_copy(
        update={
            "squad": pack.squad.model_copy(update={"members": list(reversed(pack.squad.members))})
        }
    )
    _, reordered_redactions = sanitize_memory_pack(reordered)

    assert [notice.alias for notice in redactions] == ["anonymous_squadmate_2"]
    assert redactions == reordered_redactions
    assert {member.player_id for member in safe_pack.squad.members} >= {
        "anonymous_squadmate_1",
        "anonymous_squadmate_2",
    }
    private_member = next(
        member for member in safe_pack.squad.members if member.player_id == "anonymous_squadmate_2"
    )
    assert private_member.display_name == "Anonymous squadmate 2"


def test_whitespace_caption_falls_back_and_every_deterministic_title_is_bounded() -> None:
    payload = _payload()
    payload["human_memory"]["caption"] = "   "
    whitespace_pack = MemoryPack.model_validate(payload)
    assessment, memory = MemoryAgent().discover(whitespace_pack)

    assert memory is not None
    assert memory.title
    assert "player-authored caption" not in assessment.reasons

    payload = _payload()
    payload["human_memory"]["caption"] = None
    for event in payload["match_events"]:
        event["location"] = "L" * 100
    long_location_pack = MemoryPack.model_validate(payload)
    long_title = MemoryAgent().preview(long_location_pack, 0.9).title

    assert len(long_title) == 100

    payload = _payload()
    payload["human_memory"]["caption"] = ("Jo " * 40).strip()
    for member in payload["squad"]["members"]:
        if member["player_id"] == "jo":
            member["opted_in"] = False
    redacted_pack, _ = sanitize_memory_pack(MemoryPack.model_validate(payload))
    redacted_title = MemoryAgent().preview(redacted_pack, 0.9).title

    assert 0 < len(redacted_title) <= 100
    assert "Jo" not in redacted_title


def test_map_name_without_event_locations_does_not_create_location_objective() -> None:
    payload = _payload()
    for event in payload["match_events"]:
        event["location"] = None
    pack = MemoryPack.model_validate(payload)
    memory = MemoryAgent().preview(pack, 0.9)

    quest = QuestAgent().create(pack, memory, [])

    assert "return-to-location" not in {objective.objective_id for objective in quest.objectives}
    assert all(objective.source_event_ids for objective in quest.objectives)


def test_vehicle_objective_requires_and_preserves_literal_passenger_count() -> None:
    payload = _payload()
    escape_payload = next(
        event for event in payload["match_events"] if event["type"] == "vehicle_escape"
    )
    escape_payload["details"].pop("passengers")
    pack_without_count = MemoryPack.model_validate(payload)
    memory_without_count = MemoryAgent().preview(pack_without_count, 0.9)
    quest_without_count = QuestAgent().create(pack_without_count, memory_without_count, [])

    assert "driver-seat-open" not in {
        objective.objective_id for objective in quest_without_count.objectives
    }
    escape_without_count = next(
        event for event in pack_without_count.match_events if event.type == "vehicle_escape"
    )
    assert literal_passenger_target(escape_without_count) is None

    payload = _payload()
    escape_payload = next(
        event for event in payload["match_events"] if event["type"] == "vehicle_escape"
    )
    escape_payload["details"]["passengers"] = 1
    one_passenger_pack = MemoryPack.model_validate(payload)
    memory = MemoryAgent().preview(one_passenger_pack, 0.9)
    quest = QuestAgent().create(one_passenger_pack, memory, [])
    objective = next(item for item in quest.objectives if item.objective_id == "driver-seat-open")
    escape = next(
        event for event in one_passenger_pack.match_events if event.type == "vehicle_escape"
    )

    assert literal_passenger_target(escape) == 1
    assert objective.verification.target == 1
