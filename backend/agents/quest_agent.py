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
from backend.services.evidence import literal_passenger_target, safe_generation_payload
from backend.services.structured_generator import StructuredGenerator


class QuestAgent:
    def __init__(self, generator: StructuredGenerator | None = None) -> None:
        self._generator = generator

    def create(
        self,
        pack: MemoryPack,
        memory: MemoryRecord,
        perspectives: list[PlayerPerspective],
        validation_feedback_codes: list[str] | None = None,
    ) -> NextChapter:
        if self._generator:
            canonical = self._create_deterministically(pack, memory)
            generated = self._generator.generate(
                prompt_name="quest_prompt.txt",
                payload=safe_generation_payload(
                    pack,
                    validation_feedback_codes=validation_feedback_codes or [],
                    discovered_memory=memory.model_dump(mode="json"),
                    player_perspectives=[
                        perspective.model_dump(mode="json") for perspective in perspectives
                    ],
                    required_quest_scaffold={
                        "required_mission_meaning": canonical.mission,
                        "objectives": [
                            {
                                **objective.model_dump(
                                    mode="json",
                                    exclude={"description"},
                                ),
                                "required_meaning": objective.description,
                            }
                            for objective in canonical.objectives
                        ]
                    },
                ),
                response_model=NextChapter,
                stage="quest_generation",
            )
            if self._objective_ids_match(canonical, generated):
                generated_by_objective = {
                    objective.objective_id: objective for objective in generated.objectives
                }
                return canonical.model_copy(
                    update={
                        "title": generated.title,
                        "mission": generated.mission,
                        "recipe": generated.recipe,
                        "objectives": [
                            objective.model_copy(
                                update={
                                    "description": generated_by_objective[
                                        objective.objective_id
                                    ].description,
                                }
                            )
                            for objective in canonical.objectives
                        ],
                    }
                )
            return generated
        return self._create_deterministically(pack, memory)

    @staticmethod
    def _objective_ids_match(canonical: NextChapter, generated: NextChapter) -> bool:
        if len(canonical.objectives) != len(generated.objectives):
            return False

        canonical_by_id = {item.objective_id: item for item in canonical.objectives}
        generated_by_id = {item.objective_id: item for item in generated.objectives}
        if len(generated_by_id) != len(generated.objectives):
            return False
        if set(canonical_by_id) != set(generated_by_id):
            return False
        return True

    def _create_deterministically(self, pack: MemoryPack, memory: MemoryRecord) -> NextChapter:
        evidence_ids = {item.event_id for item in memory.evidence}
        events = [event for event in pack.match_events if event.event_id in evidence_ids]
        location = next((event.location for event in events if event.location), None)
        member_ids = [member.player_id for member in pack.squad.members if member.opted_in]
        all_source_ids = [event.event_id for event in events]
        slug = re.sub(r"[^a-z0-9]+", "-", memory.title.lower()).strip("-")

        objectives = [
            QuestObjective(
                objective_id="reassemble-original-squad",
                description="Complete a match with the opted-in members of the original squad.",
                required=True,
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
                    required=True,
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
            if not self._both_opted_in(pack, revive.actor_id, revive.target_id):
                revive = None
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
                    required=True,
                    verification=VerificationRule(
                        metric=f"revives.{revive.target_id}.targets",
                        operator="contains_all",
                        target=[revive.actor_id],
                    ),
                    source_event_ids=[revive.event_id],
                )
            )

        escape = next((event for event in events if event.type == "vehicle_escape"), None)
        passenger_target = literal_passenger_target(escape) if escape is not None else None
        if (
            escape
            and escape.actor_id
            and self._is_opted_in(pack, escape.actor_id)
            and passenger_target is not None
        ):
            driver_name = self._name(pack, escape.actor_id)
            objectives.append(
                QuestObjective(
                    objective_id="driver-seat-open",
                    description=(
                        f"{driver_name} drives at least {passenger_target} teammates out of "
                        f"{escape.location or 'danger'}."
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
        if retreat and retreat.actor_id and self._is_opted_in(pack, retreat.actor_id):
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
        quest_title = f"{memory.title} II: {title_suffix}" if slug else title_suffix
        return NextChapter(
            title=quest_title[:120],
            mission=mission,
            recipe=QuestRecipe.REMIX if revive else QuestRecipe.RECREATE,
            objectives=objectives,
        )

    @staticmethod
    def _name(pack: MemoryPack, player_id: str) -> str:
        return next(
            member.display_name for member in pack.squad.members if member.player_id == player_id
        )

    @staticmethod
    def _is_opted_in(pack: MemoryPack, player_id: str) -> bool:
        return any(
            member.player_id == player_id and member.opted_in for member in pack.squad.members
        )

    @classmethod
    def _both_opted_in(cls, pack: MemoryPack, first: str, second: str) -> bool:
        return cls._is_opted_in(pack, first) and cls._is_opted_in(pack, second)
