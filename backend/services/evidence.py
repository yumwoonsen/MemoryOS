"""Compile grounded facts and remove opted-out identities before generation."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict

from backend.models.schemas import MatchEvent, MemoryPack, MemoryPackV11, RedactionNotice
from backend.services.identity import identity_pattern, identity_tokens

SAFE_DETAIL_KEYS = {
    "count",
    "duration_seconds",
    "health_state",
    "nearby_enemies",
    "passengers",
    "placement_reached",
    "squad_alive",
    "zone_state",
}


def _anonymous_aliases(
    members: list[dict[str, Any]], opted_out: list[tuple[str, str]]
) -> dict[str, tuple[str, str]]:
    """Allocate deterministic aliases outside every real roster identity namespace."""

    occupied = {
        identity_tokens(value)
        for member in members
        for value in (member["player_id"], member["display_name"])
    }
    aliases: dict[str, tuple[str, str]] = {}
    candidate_index = 1
    for player_id, _ in opted_out:
        while True:
            id_alias = f"anonymous_squadmate_{candidate_index}"
            display_alias = f"Anonymous squadmate {candidate_index}"
            alias_key = identity_tokens(id_alias)
            candidate_index += 1
            if alias_key not in occupied:
                break
        aliases[player_id] = (id_alias, display_alias)
        occupied.add(alias_key)
    return aliases


def literal_passenger_target(event: MatchEvent) -> int | None:
    """Return only the passenger count explicitly present in an event."""

    value = event.details.get("passengers")
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


class EvidenceFact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    event_type: str
    actor_id: str | None
    actor_label: str | None
    target_id: str | None
    target_label: str | None
    timestamp_seconds: int | None
    location: str | None
    details: dict[str, str | int | float | bool]


class EvidenceLedger(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pack_id: str
    match_id: str
    target_player_id: str
    opted_in_players: list[dict[str, str | None]]
    match_context: dict[str, str | int | None]
    human_context: dict[str, str | list[str] | None]
    facts: list[EvidenceFact]
    allowed_player_labels: list[str]
    allowed_locations: list[str]
    allowed_numeric_values: list[float]


def sanitize_memory_pack(
    pack: MemoryPack | MemoryPackV11,
) -> tuple[MemoryPack | MemoryPackV11, list[RedactionNotice]]:
    """Return a structurally valid copy with opted-out identities replaced."""

    payload = pack.model_dump(mode="python")
    opted_out = sorted(
        (
            (member["player_id"], member["display_name"])
            for member in payload["squad"]["members"]
            if not member["opted_in"]
        ),
        key=lambda item: item[0],
    )
    aliases = _anonymous_aliases(payload["squad"]["members"], opted_out)
    private_terms: dict[str, str] = {}
    redactions = [RedactionNotice(alias=id_alias) for id_alias, _ in aliases.values()]
    for player_id, display_name in opted_out:
        _, display_alias = aliases[player_id]
        private_terms[player_id] = display_alias
        private_terms[display_name] = display_alias

    def redact_text(value: str | None, max_length: int | None = None) -> str | None:
        if value is None:
            return None
        redacted = value
        for private in sorted(private_terms, key=len, reverse=True):
            redacted = re.sub(
                identity_pattern(private),
                private_terms[private],
                redacted,
                flags=re.IGNORECASE,
            )
        return redacted[:max_length] if max_length is not None else redacted

    for member in payload["squad"]["members"]:
        if member["opted_in"]:
            member["role"] = redact_text(member["role"], 64)
            continue
        original_id = member["player_id"]
        member["player_id"], member["display_name"] = aliases[original_id]
        member["role"] = None

    def safe_id(player_id: str | None) -> str | None:
        if player_id is None:
            return None
        alias = aliases.get(player_id)
        return alias[0] if alias is not None else player_id

    for event in payload["match_events"]:
        event["actor_id"] = safe_id(event["actor_id"])
        event["target_id"] = safe_id(event["target_id"])
        event["type"] = redact_text(event["type"], 64)
        event["location"] = redact_text(event["location"], 100)
        event["details"] = {
            key: redact_text(value, 100) if isinstance(value, str) else value
            for key, value in event["details"].items()
            if key in SAFE_DETAIL_KEYS
        }

    payload["current_context"]["active_member_ids"] = [
        player_id
        for player_id in payload["current_context"]["active_member_ids"]
        if player_id not in aliases
    ]

    human_memory = payload.get("human_memory")
    if human_memory and human_memory.get("author_player_id"):
        if human_memory["author_player_id"] in aliases:
            payload["human_memory"] = None
        else:
            human_memory["author_player_id"] = safe_id(human_memory["author_player_id"])
    if payload.get("human_memory"):
        caption = redact_text(payload["human_memory"]["caption"], 120)
        payload["human_memory"]["caption"] = (
            caption.strip() if caption and caption.strip() else None
        )
        payload["human_memory"]["tags"] = [
            redact_text(tag, 40) for tag in payload["human_memory"]["tags"]
        ]
    payload["player_profile"]["preferred_role"] = redact_text(
        payload["player_profile"]["preferred_role"], 64
    )
    payload["match"]["mode"] = redact_text(payload["match"]["mode"], 64)
    payload["match"]["map_name"] = redact_text(payload["match"]["map_name"], 100)
    payload["current_context"]["resurfacing_reason"] = redact_text(
        payload["current_context"]["resurfacing_reason"], 300
    )

    return type(pack).model_validate(payload), redactions


def apply_consent_snapshot(
    pack: MemoryPack | MemoryPackV11, consent_by_player_id: dict[str, bool]
) -> MemoryPack | MemoryPackV11:
    """Apply the already-validated request-wide consent snapshot defensively."""

    payload = pack.model_dump(mode="json")
    for member in payload["squad"]["members"]:
        member["opted_in"] = consent_by_player_id.get(member["player_id"], False)
    return type(pack).model_validate(payload)


def compile_evidence_ledger(pack: MemoryPack | MemoryPackV11) -> EvidenceLedger:
    """Create the finite fact set that prompts and validators may rely on."""

    names = {member.player_id: member.display_name for member in pack.squad.members}
    numeric_values: set[float] = set()
    facts: list[EvidenceFact] = []

    for event in pack.match_events:
        if event.timestamp_seconds is not None:
            numeric_values.add(float(event.timestamp_seconds))
        safe_details = {
            key: value for key, value in event.details.items() if key in SAFE_DETAIL_KEYS
        }
        for value in safe_details.values():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                numeric_values.add(float(value))
        facts.append(
            EvidenceFact(
                event_id=event.event_id,
                event_type=event.type,
                actor_id=event.actor_id,
                actor_label=names.get(event.actor_id),
                target_id=event.target_id,
                target_label=names.get(event.target_id),
                timestamp_seconds=event.timestamp_seconds,
                location=event.location,
                details=safe_details,
            )
        )

    locations = {
        location
        for location in [pack.match.map_name, *(event.location for event in pack.match_events)]
        if location
    }
    return EvidenceLedger(
        pack_id=pack.pack_id,
        match_id=pack.match.match_id,
        target_player_id=pack.player_profile.player_id,
        opted_in_players=[
            {
                "player_id": member.player_id,
                "display_name": member.display_name,
                "role": member.role,
            }
            for member in pack.squad.members
            if member.opted_in
        ],
        match_context={
            "mode": pack.match.mode,
            "map_name": pack.match.map_name,
            "placement": pack.match.placement,
        },
        human_context={
            "caption": pack.human_memory.caption if pack.human_memory else None,
            "tags": pack.human_memory.tags if pack.human_memory else [],
            "source_status": pack.source_status.value,
            "meaning_status": pack.meaning_status.value,
        },
        facts=facts,
        allowed_player_labels=sorted(names.values()),
        allowed_locations=sorted(locations),
        allowed_numeric_values=sorted(numeric_values),
    )


def safe_generation_payload(pack: MemoryPack | MemoryPackV11, **extra: Any) -> dict[str, Any]:
    """Build the shared, redacted prompt payload for every model-backed stage."""

    ledger = compile_evidence_ledger(pack)
    return {
        "evidence_ledger": ledger.model_dump(mode="json"),
        **extra,
    }
