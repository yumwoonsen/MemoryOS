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
from backend.services.evidence import safe_generation_payload
from backend.services.structured_generator import StructuredGenerator
from backend.services.text import truncate_text


class MemoryAgent:
    threshold = 0.45
    episode_window_seconds = 120

    def __init__(self, generator: StructuredGenerator | None = None) -> None:
        self._generator = generator

    def discover(
        self,
        pack: MemoryPack,
        validation_feedback_codes: list[str] | None = None,
    ) -> tuple[DiscoveryAssessment, MemoryRecord | None]:
        assessment = self.assess(pack)
        return self.discover_from_assessment(
            pack,
            assessment,
            validation_feedback_codes=validation_feedback_codes,
        )

    def discover_from_assessment(
        self,
        pack: MemoryPack,
        assessment: DiscoveryAssessment,
        validation_feedback_codes: list[str] | None = None,
    ) -> tuple[DiscoveryAssessment, MemoryRecord | None]:
        if not assessment.eligible:
            return assessment, None

        if self._generator:
            canonical = self._discover_deterministically(pack, assessment.signal_score)
            generated = self._generator.generate(
                prompt_name="memory_prompt.txt",
                payload=safe_generation_payload(
                    pack,
                    validation_feedback_codes=validation_feedback_codes or [],
                    required_memory_scaffold={
                        "confidence": canonical.confidence,
                        "evidence": [
                            reference.model_dump(mode="json") for reference in canonical.evidence
                        ],
                        "human_confirmed": canonical.human_confirmed,
                    },
                ),
                response_model=MemoryRecord,
                stage="memory_discovery",
            )
            return assessment, canonical.model_copy(
                update={
                    "title": generated.title,
                    "memory_type": generated.memory_type,
                    "summary": generated.summary,
                }
            )

        return assessment, self._discover_deterministically(pack, assessment.signal_score)

    def assess(self, pack: MemoryPack) -> DiscoveryAssessment:
        score = 0.0
        reasons: list[str] = []

        if not pack.match_events:
            return DiscoveryAssessment(
                signal_score=0.0,
                threshold=self.threshold,
                reasons=["no grounded gameplay events were present"],
                eligible=False,
            )
        if sum(member.opted_in for member in pack.squad.members) < 2:
            return DiscoveryAssessment(
                signal_score=0.0,
                threshold=self.threshold,
                reasons=["fewer than two squad members are opted in"],
                eligible=False,
            )

        importance_points = {"low": 0.02, "medium": 0.05, "high": 0.10}
        event_score = min(
            sum(importance_points[event.importance.value] for event in pack.match_events), 0.35
        )
        if event_score:
            score += event_score
            reasons.append(f"{len(pack.match_events)} grounded gameplay event(s)")

        if self.connected_pair(pack.match_events, "revive", "vehicle_escape"):
            score += 0.15
            reasons.append("connected rescue-and-escape pattern")
        if self.connected_pair(pack.match_events, "last_player_alive", "revive"):
            score += 0.20
            reasons.append("last-player-alive comeback pattern")

        human_memory = pack.human_memory
        if human_memory and human_memory.caption and human_memory.caption.strip():
            score += 0.15
            reasons.append("player-authored caption")
        if human_memory and human_memory.tags:
            score += 0.10
            reasons.append("player-selected memory tags")
        if human_memory and getattr(human_memory, "confirmed", False):
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

    def preview(self, pack: MemoryPack, score: float) -> MemoryRecord:
        """Create a deterministic, evidence-only candidate preview."""

        return self._discover_deterministically(pack, score)

    def _discover_deterministically(self, pack: MemoryPack, score: float) -> MemoryRecord:
        selected_events = self._select_evidence(pack.match_events)
        human_confirmed = pack.meaning_status.value == "confirmed"
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

    @classmethod
    def _select_evidence(cls, events: list[MatchEvent]) -> list[MatchEvent]:
        importance_order = {"high": 0, "medium": 1, "low": 2}
        ranked = sorted(
            events,
            key=lambda event: (
                importance_order[event.importance.value],
                event.timestamp_seconds if event.timestamp_seconds is not None else 10**9,
            ),
        )
        selected: list[MatchEvent] = []
        for first_type, second_type in (
            ("last_player_alive", "revive"),
            ("revive", "vehicle_escape"),
        ):
            pair = cls.connected_pair(ranked, first_type, second_type)
            if pair:
                for event in pair:
                    if event.event_id not in {item.event_id for item in selected}:
                        selected.append(event)

        for event in ranked:
            if event.event_id not in {item.event_id for item in selected}:
                selected.append(event)
            if len(selected) == 4:
                break
        return selected[:4]

    @classmethod
    def connected_pair(
        cls,
        events: list[MatchEvent],
        first_type: str,
        second_type: str,
    ) -> tuple[MatchEvent, MatchEvent] | None:
        """Return a causal-looking pair only when time, place, and actors support it."""

        first_events = [event for event in events if event.type == first_type]
        second_events = [event for event in events if event.type == second_type]
        for first in first_events:
            for second in second_events:
                if not cls._has_required_participants(first):
                    continue
                if not cls._has_required_participants(second):
                    continue
                if (
                    first_type == "last_player_alive"
                    and second_type == "revive"
                    and first.actor_id != second.actor_id
                ):
                    continue
                if first.timestamp_seconds is None or second.timestamp_seconds is None:
                    continue
                elapsed_seconds = second.timestamp_seconds - first.timestamp_seconds
                if elapsed_seconds < 0 or elapsed_seconds > cls.episode_window_seconds:
                    continue
                if not first.location or not second.location:
                    continue
                if first.location.casefold() != second.location.casefold():
                    continue
                return first, second
        return None

    @staticmethod
    def _has_required_participants(event: MatchEvent) -> bool:
        if event.type == "revive":
            return bool(event.actor_id and event.target_id and event.actor_id != event.target_id)
        if event.type in {"last_player_alive", "vehicle_escape"}:
            return event.actor_id is not None
        return True

    @staticmethod
    def _display_name(pack: MemoryPack, player_id: str | None) -> str:
        for member in pack.squad.members:
            if member.player_id == player_id:
                return member.display_name
        return "the squad"

    def _title(self, pack: MemoryPack, events: list[MatchEvent]) -> str:
        caption = (
            pack.human_memory.caption.strip()
            if pack.human_memory and pack.human_memory.caption
            else ""
        )
        if caption:
            return truncate_text(caption.title(), 100)
        location = next((event.location for event in events if event.location), None)
        event_types = {event.type for event in events}
        if "last_player_alive" in event_types:
            title = f"{location or 'The Squad'} Comeback"
        elif "revive" in event_types:
            title = f"The {location or 'Final Circle'} Rescue"
        else:
            title = f"{location or 'Squad'} Memory Candidate"
        return truncate_text(title, 100)

    @staticmethod
    def _memory_type(pack: MemoryPack, events: list[MatchEvent]) -> MemoryType:
        tags = {
            tag.strip().casefold()
            for tag in (pack.human_memory.tags if pack.human_memory else [])
            if tag.strip()
        }
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
        rescue_pair = self.connected_pair(events, "revive", "vehicle_escape")
        comeback_pair = self.connected_pair(events, "last_player_alive", "revive")

        if rescue_pair:
            revive, escape = rescue_pair
            rescuer = self._display_name(pack, revive.actor_id)
            rescued = self._display_name(pack, revive.target_id)
            driver = self._display_name(pack, escape.actor_id)
            location = revive.location or escape.location or pack.match.map_name
            summary = (
                f"At {location or 'the final rotation'}, {rescuer} revived {rescued} before "
                f"{driver} drove the squad out of danger."
            )
        elif comeback_pair:
            last_alive, revive = comeback_pair
            survivor = self._display_name(pack, last_alive.actor_id)
            rescued = self._display_name(pack, revive.target_id)
            location = last_alive.location or revive.location or pack.match.map_name
            summary = (
                f"At {location or 'the late game'}, {survivor} was the last squad member alive "
                f"and brought {rescued} back into the match."
            )
        else:
            primary = events[0]
            actor = self._display_name(pack, primary.actor_id)
            summary = (
                f"At {primary.location or pack.match.map_name or 'the match'}, {actor} triggered "
                f"the squad's {primary.type.replace('_', ' ')} moment."
            )
        return truncate_text(summary, 500)

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
