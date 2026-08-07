"""Create a grounded, distinct recall for each opted-in squad member."""

from __future__ import annotations

from backend.models.schemas import (
    MatchEvent,
    MemoryPack,
    MemoryRecord,
    PerspectiveSet,
    PlayerPerspective,
)
from backend.services.evidence import safe_generation_payload
from backend.services.structured_generator import StructuredGenerator


class PerspectiveAgent:
    def __init__(self, generator: StructuredGenerator | None = None) -> None:
        self._generator = generator

    def create(
        self,
        pack: MemoryPack,
        memory: MemoryRecord,
        validation_feedback_codes: list[str] | None = None,
    ) -> list[PlayerPerspective]:
        if self._generator:
            canonical = [
                self._perspective_for(member.player_id, member.display_name, pack, memory)
                for member in pack.squad.members
                if member.opted_in
            ]
            result = self._generator.generate(
                prompt_name="perspective_prompt.txt",
                payload=safe_generation_payload(
                    pack,
                    validation_feedback_codes=validation_feedback_codes or [],
                    discovered_memory=memory.model_dump(mode="json"),
                    required_perspective_scaffolds=[
                        {
                            **perspective.model_dump(mode="json", exclude={"message"}),
                            "required_meaning": perspective.message,
                        }
                        for perspective in canonical
                    ],
                ),
                response_model=PerspectiveSet,
                stage="perspectives",
            )
            if self._perspective_ids_match(canonical, result.perspectives):
                generated_by_player = {
                    perspective.player_id: perspective for perspective in result.perspectives
                }
                return [
                    perspective.model_copy(
                        update={
                            "message": generated_by_player[perspective.player_id].message,
                        }
                    )
                    for perspective in canonical
                ]
            return result.perspectives

        return [
            self._perspective_for(member.player_id, member.display_name, pack, memory)
            for member in pack.squad.members
            if member.opted_in
        ]

    @staticmethod
    def _perspective_ids_match(
        canonical: list[PlayerPerspective], generated: list[PlayerPerspective]
    ) -> bool:
        if len(canonical) != len(generated):
            return False

        canonical_by_player = {item.player_id: item for item in canonical}
        generated_by_player = {item.player_id: item for item in generated}
        if len(generated_by_player) != len(generated):
            return False
        if set(canonical_by_player) != set(generated_by_player):
            return False
        return True

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
            message = (
                f"{actor} came back for you at {location}. That verified revive became your "
                f"part of “{memory.title}.”"
            )
            used_events = [targeted_revive.event_id]
        elif authored_revive:
            target = self._name(pack, authored_revive.target_id)
            location = authored_revive.location or pack.match.map_name or "the late game"
            message = (
                f"You revived {target} at {location}. Your rescue is one of the grounded "
                f"events behind “{memory.title}.”"
            )
            used_events = [authored_revive.event_id]
        elif authored_escape:
            location = authored_escape.location or pack.match.map_name or "the final rotation"
            passengers = authored_escape.details.get("passengers")
            passenger_text = f" with {passengers} passengers" if passengers is not None else ""
            message = (
                f"You drove the squad out of {location}{passenger_text}. The getaway is the "
                f"chaotic turn in “{memory.title}.”"
            )
            used_events = [authored_escape.event_id]
        elif authored_retreat:
            count = authored_retreat.details.get("count")
            count_text = f" {count} times" if count is not None else ""
            escape = next((event for event in events if event.type == "vehicle_escape"), None)
            if escape:
                message = (
                    f"You called for retreat{count_text}. The squad's verified escape turned "
                    f"that call into part of “{memory.title}.”"
                )
            else:
                message = (
                    f"You called for retreat{count_text}. That grounded call became your part "
                    f"of “{memory.title}.”"
                )
            used_events = [authored_retreat.event_id]
            if escape:
                used_events.append(escape.event_id)
        elif authored_last_alive:
            location = authored_last_alive.location or pack.match.map_name or "the late game"
            message = (
                f"You were the last squad member alive at {location}. That moment anchors the "
                f"comeback remembered as “{memory.title}.”"
            )
            used_events = [authored_last_alive.event_id]
        else:
            primary = self._best_witness_event(events, player_id)
            location = primary.location or pack.match.map_name or "the match"
            message = (
                f"You were part of the original squad at {location} when the verified "
                f"{primary.type.replace('_', ' ')} became “{memory.title}.”"
            )
            used_events = [primary.event_id]
            event_label = primary.type.replace("_", " ")
            if primary.actor_id == player_id:
                message = (
                    f"{display_name}, you triggered the squad's verified {event_label} at "
                    f"{location}. That event is your grounded part of the selected memory."
                )
            elif primary.target_id == player_id:
                message = (
                    f"At {location}, the verified {event_label} lists {display_name} as its "
                    "target. That event is your grounded part of the selected memory."
                )

        return PlayerPerspective(
            player_id=player_id,
            display_name=display_name,
            message=message,
            evidence_event_ids=used_events,
        )

    @staticmethod
    def _name(pack: MemoryPack, player_id: str | None) -> str:
        return next(
            (member.display_name for member in pack.squad.members if member.player_id == player_id),
            "a squadmate",
        )

    @staticmethod
    def _best_witness_event(events: list[MatchEvent], player_id: str) -> MatchEvent:
        involved = [event for event in events if player_id in {event.actor_id, event.target_id}]
        return (involved or events)[0]
