"""Discover a candidate memory from grounded gameplay and human signals."""

from __future__ import annotations

from backend.models.schemas import (
    DiscoveryAssessment,
    EvidenceRef,
    MatchEvent,
    MemoryPack,
    MemoryRecord,
    MemoryType,
)
from backend.services.structured_generator import StructuredGenerator


class MemoryAgent:
    threshold = 0.45

    def __init__(self, generator: StructuredGenerator | None = None) -> None:
        self._generator = generator

    def discover(self, pack: MemoryPack) -> tuple[DiscoveryAssessment, MemoryRecord | None]:
        assessment = self._assess_signals(pack)
        if not assessment.eligible:
            return assessment, None

        if self._generator:
            memory = self._generator.generate(
                prompt_name="memory_prompt.txt",
                payload={"memory_pack": pack.model_dump(mode="json")},
                response_model=MemoryRecord,
            )
            return assessment, memory

        return assessment, self._discover_deterministically(pack, assessment.signal_score)

    def _assess_signals(self, pack: MemoryPack) -> DiscoveryAssessment:
        score = 0.0
        reasons: list[str] = []

        importance_points = {"low": 0.02, "medium": 0.05, "high": 0.10}
        event_score = min(
            sum(importance_points[event.importance.value] for event in pack.match_events), 0.35
        )
        if event_score:
            score += event_score
            reasons.append(f"{len(pack.match_events)} grounded gameplay event(s)")

        event_types = {event.type for event in pack.match_events}
        if {"revive", "vehicle_escape"}.issubset(event_types):
            score += 0.15
            reasons.append("connected rescue-and-escape pattern")
        if "last_player_alive" in event_types and "revive" in event_types:
            score += 0.20
            reasons.append("last-player-alive comeback pattern")

        human_memory = pack.human_memory
        if human_memory and human_memory.caption:
            score += 0.15
            reasons.append("player-authored caption")
        if human_memory and human_memory.tags:
            score += 0.10
            reasons.append("player-selected memory tags")
        if human_memory and human_memory.confirmed:
            score += 0.20
            reasons.append("player-confirmed meaning")

        reaction_score = min(pack.reactions.laugh_count * 0.01, 0.10)
        reaction_score += min(pack.reactions.fire_count * 0.01, 0.05)
        if pack.reactions.saved:
            reaction_score += 0.10
        if reaction_score:
            score += reaction_score
            reasons.append("positive save or reaction signals")

        score = round(min(score, 1.0), 2)
        return DiscoveryAssessment(
            signal_score=score,
            threshold=self.threshold,
            reasons=reasons or ["no meaningful memory signals were present"],
            eligible=score >= self.threshold,
        )

    def _discover_deterministically(self, pack: MemoryPack, score: float) -> MemoryRecord:
        selected_events = self._select_evidence(pack.match_events)
        human_confirmed = bool(pack.human_memory and pack.human_memory.confirmed)
        title = self._title(pack, selected_events)
        memory_type = self._memory_type(pack, selected_events)
        summary = self._summary(pack, selected_events)
        evidence = [
            EvidenceRef(
                event_id=event.event_id,
                event_type=event.type,
                significance=self._event_significance(event, pack),
            )
            for event in selected_events
        ]
        return MemoryRecord(
            title=title,
            memory_type=memory_type,
            summary=summary,
            confidence=score,
            evidence=evidence,
            human_confirmed=human_confirmed,
        )

    @staticmethod
    def _select_evidence(events: list[MatchEvent]) -> list[MatchEvent]:
        importance_order = {"high": 0, "medium": 1, "low": 2}
        ranked = sorted(
            events,
            key=lambda event: (
                importance_order[event.importance.value],
                event.timestamp_seconds if event.timestamp_seconds is not None else 10**9,
            ),
        )
        return ranked[:4] or events[:1]

    @staticmethod
    def _display_name(pack: MemoryPack, player_id: str | None) -> str:
        for member in pack.squad.members:
            if member.player_id == player_id:
                return member.display_name
        return "the squad"

    def _title(self, pack: MemoryPack, events: list[MatchEvent]) -> str:
        if pack.human_memory and pack.human_memory.caption:
            return pack.human_memory.caption.strip().title()
        location = next((event.location for event in events if event.location), None)
        event_types = {event.type for event in events}
        if "last_player_alive" in event_types:
            return f"{location or 'The Squad'} Comeback"
        if "revive" in event_types:
            return f"The {location or 'Final Circle'} Rescue"
        return f"{location or 'Squad'} Memory Candidate"

    @staticmethod
    def _memory_type(pack: MemoryPack, events: list[MatchEvent]) -> MemoryType:
        tags = {tag.lower() for tag in (pack.human_memory.tags if pack.human_memory else [])}
        event_types = {event.type for event in events}
        if tags & {"funny", "chaos"} or "vehicle_escape" in event_types:
            return MemoryType.CHAOS
        if "comeback" in tags or "last_player_alive" in event_types:
            return MemoryType.COMEBACK
        if "clutch" in tags or "final_zone_survival" in event_types:
            return MemoryType.CLUTCH
        if "ritual" in tags:
            return MemoryType.RITUAL
        if "first" in tags:
            return MemoryType.FIRST
        return MemoryType.OTHER

    def _summary(self, pack: MemoryPack, events: list[MatchEvent]) -> str:
        revive = next((event for event in events if event.type == "revive"), None)
        escape = next((event for event in events if event.type == "vehicle_escape"), None)
        last_alive = next((event for event in events if event.type == "last_player_alive"), None)
        location = next((event.location for event in events if event.location), pack.match.map_name)

        if revive and escape:
            rescuer = self._display_name(pack, revive.actor_id)
            rescued = self._display_name(pack, revive.target_id)
            driver = self._display_name(pack, escape.actor_id)
            return (
                f"At {location or 'the final rotation'}, {rescuer} revived {rescued} before "
                f"{driver} drove the squad out of danger."
            )
        if last_alive and revive:
            survivor = self._display_name(pack, last_alive.actor_id)
            rescued = self._display_name(pack, revive.target_id)
            return (
                f"At {location or 'the late game'}, {survivor} was the last squad member alive "
                f"and brought {rescued} back into the match."
            )
        primary = events[0]
        actor = self._display_name(pack, primary.actor_id)
        return (
            f"At {primary.location or pack.match.map_name or 'the match'}, {actor} triggered "
            f"the squad's {primary.type.replace('_', ' ')} moment."
        )

    def _event_significance(self, event: MatchEvent, pack: MemoryPack) -> str:
        actor = self._display_name(pack, event.actor_id)
        target = self._display_name(pack, event.target_id) if event.target_id else None
        if event.type == "revive" and target:
            return f"{actor} revived {target}"
        if event.type == "vehicle_escape":
            passengers = event.details.get("passengers")
            suffix = f" with {passengers} passenger(s)" if passengers is not None else ""
            return f"{actor} completed the vehicle escape{suffix}"
        if event.type == "retreat_ping":
            count = event.details.get("count")
            suffix = f" {count} time(s)" if count is not None else ""
            return f"{actor} called for retreat{suffix}"
        if event.type == "last_player_alive":
            return f"{actor} became the squad's last surviving player"
        return f"Verified {event.type.replace('_', ' ')} event involving {actor}"
