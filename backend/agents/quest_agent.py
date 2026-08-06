"""Turn a discovered memory into a verifiable, squad-specific next chapter."""

from __future__ import annotations

import re

from backend.models.schemas import (
    MatchEvent,
    MemoryPack,
    MemoryRecord,
    NextChapter,
    PlayerPerspective,
    QuestObjective,
    QuestRecipe,
    VerificationRule,
)
from backend.services.structured_generator import StructuredGenerator
from backend.services.text import truncate_text


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
            generated = self._generator.generate(
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
            return self._canonicalize_generated_quest(pack, memory, generated)
        return self._create_deterministically(pack, memory)

    def _canonicalize_generated_quest(
        self, pack: MemoryPack, memory: MemoryRecord, quest: NextChapter
    ) -> NextChapter:
        """Render model-selected quest structure into bounded, canonical player-facing text."""

        input_events = {event.event_id: event for event in pack.match_events}
        memory_event_ids = {item.event_id for item in memory.evidence}
        memory_events = [event for event in pack.match_events if event.event_id in memory_event_ids]
        location = next(
            (event.location for event in memory_events if event.location),
            pack.match.map_name,
        )
        objectives = [
            objective.model_copy(
                update={
                    "description": self._render_objective_description(pack, objective, input_events)
                }
            )
            for objective in quest.objectives
        ]
        has_revive_rule = any(
            objective.verification.metric.startswith("revives.") for objective in objectives
        )
        title_suffix = "Return the Favour" if has_revive_rule else "One More Run"
        title = truncate_text(f"{memory.title} II: {title_suffix}", 120)
        mission = (
            f'Reassemble the original squad and remix "{memory.title}"'
            + (f" at {location}" if location else "")
            + " using roles grounded in the original match."
        )
        return quest.model_copy(
            update={
                "title": title,
                "mission": truncate_text(mission, 500),
                "objectives": objectives,
            }
        )

    def _render_objective_description(
        self,
        pack: MemoryPack,
        objective: QuestObjective,
        input_events: dict[str, MatchEvent],
    ) -> str:
        rule = objective.verification
        target = rule.target
        members = {member.player_id: member for member in pack.squad.members if member.opted_in}

        def player_name(player_id: object) -> str:
            member = members.get(player_id) if isinstance(player_id, str) else None
            return member.display_name if member else "an eligible squad member"

        if rule.metric == "squad_member_ids":
            description = "Complete a match with the opted-in members of the original squad."
        elif rule.metric == "visited_locations":
            grounded_locations = {
                event.location
                for event_id in objective.source_event_ids
                if (event := input_events.get(event_id)) is not None
                and getattr(event, "location", None)
            }
            if pack.match.map_name:
                grounded_locations.add(pack.match.map_name)
            requested_locations = target if isinstance(target, list) else []
            locations = [
                location
                for location in requested_locations
                if isinstance(location, str) and location in grounded_locations
            ]
            location_text = ", ".join(locations) or "a grounded match location"
            description = f"Return to {location_text} during the new match."
        elif rule.metric == "initial_route_caller_id":
            description = f"{player_name(target)} chooses the squad's first rotation route."
        elif (
            revive_actor := self._metric_subject(rule.metric, "revives.", ".targets")
        ) is not None:
            target_ids = target if isinstance(target, list) else []
            target_names = [player_name(player_id) for player_id in target_ids]
            target_text = ", ".join(target_names) or "an eligible squad member"
            description = f"{player_name(revive_actor)} revives {target_text} in the new match."
        elif (
            driver_id := self._metric_subject(rule.metric, "vehicle_escape.", ".passengers")
        ) is not None:
            max_passengers = max(len(members) - 1, 1)
            passenger_target = (
                min(target, max_passengers)
                if isinstance(target, int) and not isinstance(target, bool) and target >= 1
                else 1
            )
            teammate_label = "teammate" if passenger_target == 1 else "teammates"
            description = (
                f"{player_name(driver_id)} drives at least {passenger_target} "
                f"{teammate_label} during a vehicle escape."
            )
        else:
            description = "Complete this objective only when its verification rule passes."
        return truncate_text(description, 400)

    def _create_deterministically(self, pack: MemoryPack, memory: MemoryRecord) -> NextChapter:
        evidence_ids = {item.event_id for item in memory.evidence}
        events = [event for event in pack.match_events if event.event_id in evidence_ids]
        location = next((event.location for event in events if event.location), pack.match.map_name)
        member_ids = [member.player_id for member in pack.squad.members if member.opted_in]
        opted_in_ids = set(member_ids)
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
            location_source_ids = [
                event.event_id for event in events if event.location == location
            ] or all_source_ids
            objectives.append(
                QuestObjective(
                    objective_id="return-to-location",
                    description=f"Return to {location} during the new match.",
                    verification=VerificationRule(
                        metric="visited_locations",
                        operator="contains_all",
                        target=[location],
                    ),
                    source_event_ids=location_source_ids,
                )
            )

        revive = next(
            (
                event
                for event in events
                if event.type == "revive"
                and event.actor_id in opted_in_ids
                and event.target_id in opted_in_ids
            ),
            None,
        )
        if revive:
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

        escape = next(
            (
                event
                for event in events
                if event.type == "vehicle_escape" and event.actor_id in opted_in_ids
            ),
            None,
        )
        max_passengers = max(len(member_ids) - 1, 0)
        if escape and max_passengers:
            driver_name = self._name(pack, escape.actor_id)
            passenger_target = self._passenger_target(
                escape.details.get("passengers"), max_passengers
            )
            teammate_label = "teammate" if passenger_target == 1 else "teammates"
            objectives.append(
                QuestObjective(
                    objective_id="driver-seat-open",
                    description=(
                        f"{driver_name} drives at least {passenger_target} {teammate_label} out of "
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

        retreat = next(
            (
                event
                for event in events
                if event.type == "retreat_ping" and event.actor_id in opted_in_ids
            ),
            None,
        )
        if retreat:
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
            f'Reassemble the original squad and remix "{memory.title}"'
            + (f" at {location}" if location else "")
            + " using roles grounded in the original match."
        )
        quest_title = f"{memory.title} II: {title_suffix}" if slug else title_suffix
        return NextChapter(
            title=truncate_text(quest_title, 120),
            mission=truncate_text(mission, 500),
            recipe=QuestRecipe.REMIX if revive else QuestRecipe.RECREATE,
            objectives=objectives,
        )

    @staticmethod
    def _passenger_target(raw_value: object, max_passengers: int) -> int:
        """Convert loose telemetry into a possible, consent-bounded objective target."""

        default = min(2, max_passengers)
        try:
            if isinstance(raw_value, bool):
                raise ValueError
            if isinstance(raw_value, float) and not raw_value.is_integer():
                raise ValueError
            parsed = int(raw_value) if raw_value is not None else default
        except (TypeError, ValueError, OverflowError):
            parsed = default
        return min(max(parsed, default), max_passengers)

    @staticmethod
    def _metric_subject(metric: str, prefix: str, suffix: str) -> str | None:
        if not metric.startswith(prefix) or not metric.endswith(suffix):
            return None
        subject = metric[len(prefix) : -len(suffix)]
        return subject or None

    @staticmethod
    def _name(pack: MemoryPack, player_id: str) -> str:
        return next(
            member.display_name for member in pack.squad.members if member.player_id == player_id
        )
