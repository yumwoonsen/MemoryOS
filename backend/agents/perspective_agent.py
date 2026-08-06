"""Create a grounded, distinct recall for each opted-in squad member."""

from __future__ import annotations

from backend.models.schemas import (
    MatchEvent,
    MemoryPack,
    MemoryRecord,
    PerspectiveSet,
    PlayerPerspective,
)
from backend.services.structured_generator import StructuredGenerator
from backend.services.text import truncate_text


class PerspectiveAgent:
    def __init__(self, generator: StructuredGenerator | None = None) -> None:
        self._generator = generator

    def create(self, pack: MemoryPack, memory: MemoryRecord) -> list[PlayerPerspective]:
        if self._generator:
            result = self._generator.generate(
                prompt_name="perspective_prompt.txt",
                payload={
                    "memory_pack": pack.model_dump(mode="json"),
                    "discovered_memory": memory.model_dump(mode="json"),
                },
                response_model=PerspectiveSet,
            )
            return self._canonicalize_generated_perspectives(pack, memory, result.perspectives)

        return [
            self._perspective_for(member.player_id, member.display_name, pack, memory)
            for member in pack.squad.members
            if member.opted_in
        ]

    def _canonicalize_generated_perspectives(
        self,
        pack: MemoryPack,
        memory: MemoryRecord,
        perspectives: list[PlayerPerspective],
    ) -> list[PlayerPerspective]:
        """Preserve model-selected identities but render player-facing prose deterministically."""

        members = {member.player_id: member for member in pack.squad.members}
        known_event_ids = {event.event_id for event in pack.match_events}
        has_grounded_memory_evidence = any(
            evidence.event_id in known_event_ids for evidence in memory.evidence
        )
        canonical: list[PlayerPerspective] = []
        for perspective in perspectives:
            member = members.get(perspective.player_id)
            if member and member.opted_in and has_grounded_memory_evidence:
                canonical.append(
                    self._perspective_for(
                        member.player_id,
                        member.display_name,
                        pack,
                        memory,
                    )
                )
            else:
                canonical.append(
                    perspective.model_copy(
                        update={
                            "display_name": (member.display_name if member else "Unknown player"),
                            "message": (
                                "Perspective omitted because this player is not eligible for "
                                "personalized output."
                            ),
                        }
                    )
                )
        return canonical

    def _perspective_for(
        self,
        player_id: str,
        display_name: str,
        pack: MemoryPack,
        memory: MemoryRecord,
    ) -> PlayerPerspective:
        evidence_ids = {item.event_id for item in memory.evidence}
        events = [event for event in pack.match_events if event.event_id in evidence_ids]

        targeted_revive = next(
            (event for event in events if event.type == "revive" and event.target_id == player_id),
            None,
        )
        authored_revive = next(
            (event for event in events if event.type == "revive" and event.actor_id == player_id),
            None,
        )
        authored_escape = next(
            (
                event
                for event in events
                if event.type == "vehicle_escape" and event.actor_id == player_id
            ),
            None,
        )
        authored_retreat = next(
            (
                event
                for event in events
                if event.type == "retreat_ping" and event.actor_id == player_id
            ),
            None,
        )
        authored_last_alive = next(
            (
                event
                for event in events
                if event.type == "last_player_alive" and event.actor_id == player_id
            ),
            None,
        )

        if targeted_revive:
            actor = self._name(pack, targeted_revive.actor_id)
            location = targeted_revive.location or pack.match.map_name or "the late game"
            revive_number = self._event_sequence(events, targeted_revive)
            message = (
                f"Verified revive #{revive_number} records {actor} coming back for you at "
                f'{location}. That rescue became your part of "{memory.title}."'
            )
            used_events = [targeted_revive.event_id]
        elif authored_revive:
            target = self._name(pack, authored_revive.target_id)
            location = authored_revive.location or pack.match.map_name or "the late game"
            revive_number = self._event_sequence(events, authored_revive)
            message = (
                f"Verified revive #{revive_number} records you reviving {target} at {location}. "
                f'Your rescue is grounded evidence behind "{memory.title}."'
            )
            used_events = [authored_revive.event_id]
        elif authored_escape:
            location = authored_escape.location or pack.match.map_name or "the final rotation"
            passengers = authored_escape.details.get("passengers")
            passenger_text = f" with {passengers} passengers" if passengers is not None else ""
            message = (
                f"You drove the squad out of {location}{passenger_text}. The getaway is the "
                f'chaotic turn in "{memory.title}."'
            )
            used_events = [authored_escape.event_id]
        elif authored_retreat:
            count = authored_retreat.details.get("count")
            count_text = f" {count} times" if count is not None else ""
            message = (
                f"You called for retreat{count_text}. The squad's verified escape turned that "
                f'call into part of "{memory.title}."'
            )
            used_events = [authored_retreat.event_id]
        elif authored_last_alive:
            location = authored_last_alive.location or pack.match.map_name or "the late game"
            message = (
                f"You were the last squad member alive at {location}. That moment anchors the "
                f'comeback remembered as "{memory.title}."'
            )
            used_events = [authored_last_alive.event_id]
        else:
            primary = self._best_witness_event(events, player_id, pack)
            location = primary.location or pack.match.map_name or "the match"
            evidence_number = events.index(primary) + 1
            event_label = primary.type.replace("_", " ")
            if primary.actor_id == player_id:
                message = (
                    f"Evidence #{evidence_number} records you as the actor in the verified "
                    f'{event_label} at {location}. It anchors your recall of "{memory.title}."'
                )
            elif primary.target_id == player_id:
                message = (
                    f"Evidence #{evidence_number} records you as the target in the verified "
                    f'{event_label} at {location}. It anchors your recall of "{memory.title}."'
                )
            else:
                message = (
                    f"{display_name}, evidence #{evidence_number} records your squad's verified "
                    f'{event_label} at {location}. It anchors your recall of "{memory.title}."'
                )
            used_events = [primary.event_id]

        return PlayerPerspective(
            player_id=player_id,
            display_name=display_name,
            message=truncate_text(message, 400),
            evidence_event_ids=used_events,
        )

    @staticmethod
    def _name(pack: MemoryPack, player_id: str | None) -> str:
        return next(
            (member.display_name for member in pack.squad.members if member.player_id == player_id),
            "a squadmate",
        )

    @staticmethod
    def _best_witness_event(
        events: list[MatchEvent], player_id: str, pack: MemoryPack
    ) -> MatchEvent:
        involved = [event for event in events if player_id in {event.actor_id, event.target_id}]
        if involved:
            return involved[0]
        opted_in_ids = [member.player_id for member in pack.squad.members if member.opted_in]
        player_index = opted_in_ids.index(player_id)
        return events[player_index % len(events)]

    @staticmethod
    def _event_sequence(events: list[MatchEvent], selected: MatchEvent) -> int:
        same_type = [event for event in events if event.type == selected.type]
        return same_type.index(selected) + 1
