"""Turn a discovered memory into a verifiable, squad-specific next chapter."""

from __future__ import annotations

import re

from backend.models.schemas import (
    MemoryPack,
    MemoryRecord,
    NextChapter,
    PlayerPerspective,
    QuestObjective,
    QuestRecipe,
    VerificationRule,
)
from backend.services.structured_generator import StructuredGenerator


class QuestAgent:
    def __init__(self, generator: StructuredGenerator | None = None) -> None:
        self._generator = generator

    def create(
        self,
        pack: MemoryPack,
        memory: MemoryRecord,
        perspectives: list[PlayerPerspective],
    ) -> NextChapter:
        if self._generator:
            return self._generator.generate(
                prompt_name="quest_prompt.txt",
                payload={
                    "memory_pack": pack.model_dump(mode="json"),
                    "discovered_memory": memory.model_dump(mode="json"),
                    "player_perspectives": [
                        perspective.model_dump(mode="json") for perspective in perspectives
                    ],
                },
                response_model=NextChapter,
            )
        return self._create_deterministically(pack, memory)

    def _create_deterministically(self, pack: MemoryPack, memory: MemoryRecord) -> NextChapter:
        evidence_ids = {item.event_id for item in memory.evidence}
        events = [event for event in pack.match_events if event.event_id in evidence_ids]
        location = next((event.location for event in events if event.location), pack.match.map_name)
        member_ids = [member.player_id for member in pack.squad.members if member.opted_in]
        all_source_ids = [event.event_id for event in events]
        slug = re.sub(r"[^a-z0-9]+", "-", memory.title.lower()).strip("-")

        objectives = [
            QuestObjective(
                objective_id="reassemble-original-squad",
                description="Complete a match with the opted-in members of the original squad.",
                verification=VerificationRule(
                    metric="squad_member_ids",
                    operator="contains_all",
                    target=member_ids,
                ),
                source_event_ids=all_source_ids,
            )
        ]

        if location:
            objectives.append(
                QuestObjective(
                    objective_id="return-to-location",
                    description=f"Return to {location} during the new match.",
                    verification=VerificationRule(
                        metric="visited_locations",
                        operator="contains_all",
                        target=[location],
                    ),
                    source_event_ids=[
                        event.event_id for event in events if event.location == location
                    ],
                )
            )

        revive = next((event for event in events if event.type == "revive"), None)
        if revive and revive.actor_id and revive.target_id:
            rescued_name = self._name(pack, revive.target_id)
            rescuer_name = self._name(pack, revive.actor_id)
            objectives.append(
                QuestObjective(
                    objective_id="return-the-favour",
                    description=(
                        f"{rescued_name} revives {rescuer_name}, reversing the original roles."
                    ),
                    assigned_player_id=revive.target_id,
                    verification=VerificationRule(
                        metric=f"revives.{revive.target_id}.targets",
                        operator="contains_all",
                        target=[revive.actor_id],
                    ),
                    source_event_ids=[revive.event_id],
                )
            )

        escape = next((event for event in events if event.type == "vehicle_escape"), None)
        if escape and escape.actor_id:
            driver_name = self._name(pack, escape.actor_id)
            passenger_target = max(int(escape.details.get("passengers", 2)), 2)
            objectives.append(
                QuestObjective(
                    objective_id="driver-seat-open",
                    description=(
                        f"{driver_name} drives at least {passenger_target} teammates out of "
                        f"{location or 'the first contested location'}."
                    ),
                    assigned_player_id=escape.actor_id,
                    required=False,
                    verification=VerificationRule(
                        metric=f"vehicle_escape.{escape.actor_id}.passengers",
                        operator="at_least",
                        target=passenger_target,
                    ),
                    source_event_ids=[escape.event_id],
                )
            )

        retreat = next((event for event in events if event.type == "retreat_ping"), None)
        if retreat and retreat.actor_id:
            caller_name = self._name(pack, retreat.actor_id)
            objectives.append(
                QuestObjective(
                    objective_id="caller-chooses-route",
                    description=f"{caller_name} chooses the squad's first rotation route.",
                    assigned_player_id=retreat.actor_id,
                    required=False,
                    verification=VerificationRule(
                        metric="initial_route_caller_id",
                        operator="equals",
                        target=retreat.actor_id,
                    ),
                    source_event_ids=[retreat.event_id],
                )
            )

        title_suffix = "Return the Favour" if revive else "One More Run"
        mission = (
            f"Reassemble the original squad and remix {memory.title}"
            + (f" at {location}" if location else "")
            + " using roles grounded in the original match."
        )
        return NextChapter(
            title=f"{memory.title} II: {title_suffix}" if slug else title_suffix,
            mission=mission,
            recipe=QuestRecipe.REMIX if revive else QuestRecipe.RECREATE,
            objectives=objectives,
        )

    @staticmethod
    def _name(pack: MemoryPack, player_id: str) -> str:
        return next(
            member.display_name for member in pack.squad.members if member.player_id == player_id
        )
