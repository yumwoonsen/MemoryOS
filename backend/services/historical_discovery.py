"""Deterministic screening and ranking for historical Memory Packs."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC

from backend.agents.memory_agent import MemoryAgent
from backend.models.schemas import (
    CandidateScoreBreakdown,
    DiscoveryAssessment,
    HistoricalCandidate,
    HistoricalDiscoveryRequest,
    HistoricalDiscoveryResponse,
    HistoricalFilterCounts,
    MeaningStatus,
    MemoryPack,
    MemoryPackV11,
    MemoryType,
    RedactionNotice,
    SourceStatus,
)
from backend.services.evidence import apply_consent_snapshot, sanitize_memory_pack


@dataclass(frozen=True)
class ScoredPack:
    pack: MemoryPack | MemoryPackV11
    safe_pack: MemoryPack | MemoryPackV11
    memory_type: MemoryType
    breakdown: CandidateScoreBreakdown
    selection_score: float
    reasons: tuple[str, ...]
    redactions: tuple[RedactionNotice, ...]


class HistoricalMemoryRanker:
    """Rank likely memories without spending model tokens."""

    threshold = 0.45
    diversity_penalty = 0.08

    def __init__(self) -> None:
        self._memory_agent = MemoryAgent()

    def discover(self, request: HistoricalDiscoveryRequest) -> HistoricalDiscoveryResponse:
        counters = {
            "received": len(request.memory_packs),
            "duplicates_removed": 0,
            "no_grounded_events": 0,
            "below_threshold": 0,
            "disputed": 0,
            "dismissed": 0,
            "target_opted_out": 0,
            "eligible_not_selected": 0,
        }
        eligible: list[ScoredPack] = []
        consent_snapshot = self._consent_snapshot(request.memory_packs)

        for original_pack in request.memory_packs:
            pack = apply_consent_snapshot(original_pack, consent_snapshot)
            rejection = self._hard_filter(pack)
            if rejection:
                counters[rejection] += 1
                continue
            scored = self.score_pack(pack)
            if scored.breakdown.total < self.threshold:
                counters["below_threshold"] += 1
                continue
            eligible.append(scored)

        deduplicated: dict[str, ScoredPack] = {}
        for scored in eligible:
            current = deduplicated.get(scored.pack.match.match_id)
            if current is None or self._base_sort_key(scored) < self._base_sort_key(current):
                if current is not None:
                    counters["duplicates_removed"] += 1
                deduplicated[scored.pack.match.match_id] = scored
            else:
                counters["duplicates_removed"] += 1

        selected = self._select_diverse(list(deduplicated.values()), request.limit)
        counters["eligible_not_selected"] = len(deduplicated) - len(selected)
        candidates = [self._to_candidate(item, index + 1) for index, item in enumerate(selected)]

        return HistoricalDiscoveryResponse(
            candidates=candidates,
            filters=HistoricalFilterCounts(**counters),
            metadata={
                "pipeline_version": "phase-2-history-v1",
                "provider": "deterministic",
                "model": "rules-v1",
                "consent_policy": "consistent_request_snapshot",
                "threshold": self.threshold,
                "weights": {
                    "evidence_strength": 0.35,
                    "human_signals": 0.30,
                    "squad_specificity": 0.20,
                    "resurfacing_relevance": 0.15,
                },
                "normalized_legacy_packs": sum(
                    pack.schema_version == "1.0" for pack in request.memory_packs
                ),
            },
        )

    def assess(self, pack: MemoryPack | MemoryPackV11) -> DiscoveryAssessment:
        rejection = self._hard_filter(pack)
        if rejection:
            return DiscoveryAssessment(
                signal_score=0.0,
                threshold=self.threshold,
                reasons=[self._filter_reason(rejection)],
                eligible=False,
            )
        scored = self.score_pack(pack)
        return DiscoveryAssessment(
            signal_score=scored.breakdown.total,
            threshold=self.threshold,
            reasons=list(scored.reasons),
            eligible=scored.breakdown.total >= self.threshold,
        )

    def score_pack(self, pack: MemoryPack | MemoryPackV11) -> ScoredPack:
        safe_pack, redactions = sanitize_memory_pack(pack)
        evidence_raw, evidence_reasons = self._evidence_score(safe_pack)
        human_raw, human_reasons = self._human_score(safe_pack)
        squad_raw, squad_reasons = self._squad_score(safe_pack)
        relevance_raw, relevance_reasons = self._relevance_score(safe_pack)

        evidence = round(evidence_raw * 0.35, 4)
        human = round(human_raw * 0.30, 4)
        squad = round(squad_raw * 0.20, 4)
        relevance = round(relevance_raw * 0.15, 4)
        total = round(evidence + human + squad + relevance, 4)
        preview = self._memory_agent.preview(safe_pack, total)
        return ScoredPack(
            pack=pack,
            safe_pack=safe_pack,
            memory_type=preview.memory_type,
            breakdown=CandidateScoreBreakdown(
                evidence_strength=evidence,
                human_signals=human,
                squad_specificity=squad,
                resurfacing_relevance=relevance,
                total=total,
            ),
            selection_score=total,
            reasons=tuple(evidence_reasons + human_reasons + squad_reasons + relevance_reasons),
            redactions=tuple(redactions),
        )

    @staticmethod
    def _hard_filter(pack: MemoryPack | MemoryPackV11) -> str | None:
        if not pack.target_player_opted_in:
            return "target_opted_out"
        if pack.source_status == SourceStatus.DISPUTED:
            return "disputed"
        if pack.meaning_status == MeaningStatus.DISMISSED:
            return "dismissed"
        if not pack.match_events:
            return "no_grounded_events"
        return None

    @staticmethod
    def _filter_reason(code: str) -> str:
        return {
            "target_opted_out": "the target player has not opted in",
            "disputed": "the gameplay source was disputed",
            "dismissed": "the player dismissed this memory",
            "no_grounded_events": "no grounded gameplay events were present",
        }[code]

    @staticmethod
    def _evidence_score(pack: MemoryPack | MemoryPackV11) -> tuple[float, list[str]]:
        importance = {"low": 0.05, "medium": 0.12, "high": 0.25}
        raw = min(sum(importance[event.importance.value] for event in pack.match_events), 0.75)
        reasons = [f"{len(pack.match_events)} grounded event(s)"]
        event_types = {event.type for event in pack.match_events}
        if {"revive", "vehicle_escape"} <= event_types:
            raw += 0.15
            reasons.append("connected rescue-and-escape evidence")
        if {"last_player_alive", "revive"} <= event_types:
            raw += 0.20
            reasons.append("last-player-alive comeback evidence")
        return min(raw, 1.0), reasons

    @staticmethod
    def _human_score(pack: MemoryPack | MemoryPackV11) -> tuple[float, list[str]]:
        raw = 0.0
        reasons: list[str] = []
        if pack.human_memory and pack.human_memory.caption:
            raw += 0.25
            reasons.append("player-authored caption")
        if pack.human_memory and pack.human_memory.tags:
            raw += 0.15
            reasons.append("player-selected memory tags")
        if pack.meaning_status == MeaningStatus.CONFIRMED:
            raw += 0.20
            reasons.append("player-confirmed meaning")
        raw += min(pack.reactions.laugh_count / 20, 1.0) * 0.15
        raw += min(pack.reactions.fire_count / 10, 1.0) * 0.10
        if pack.reactions.saved:
            raw += 0.20
            reasons.append("saved by a player")
        if pack.reactions.laugh_count or pack.reactions.fire_count:
            reasons.append("positive squad reactions")
        return min(raw, 1.0), reasons

    @staticmethod
    def _squad_score(pack: MemoryPack | MemoryPackV11) -> tuple[float, list[str]]:
        opted_in = {member.player_id for member in pack.squad.members if member.opted_in}
        involved = {
            player_id
            for event in pack.match_events
            for player_id in (event.actor_id, event.target_id)
            if player_id in opted_in
        }
        involvement = len(involved) / max(len(opted_in), 1)
        roles = {
            member.role
            for member in pack.squad.members
            if member.player_id in involved and member.role
        }
        role_diversity = min(len(roles) / max(len(opted_in), 1), 1.0)
        raw = involvement * 0.70 + role_diversity * 0.30
        return min(raw, 1.0), [f"{len(involved)} opted-in member(s) grounded in events"]

    @staticmethod
    def _relevance_score(pack: MemoryPack | MemoryPackV11) -> tuple[float, list[str]]:
        raw = 0.0
        reasons: list[str] = []
        if pack.squad.days_since_full_squad is not None:
            raw += min(pack.squad.days_since_full_squad / 30, 1.0) * 0.50
            reasons.append(f"{pack.squad.days_since_full_squad} days since the full squad played")
        if pack.current_context.resurfacing_reason:
            raw += 0.25
            reasons.append("current resurfacing context")
        if pack.current_context.original_mode_available:
            raw += 0.15
        opted_in_count = sum(member.opted_in for member in pack.squad.members)
        active_count = len(
            set(pack.current_context.active_member_ids)
            & {member.player_id for member in pack.squad.members if member.opted_in}
        )
        raw += (active_count / max(opted_in_count, 1)) * 0.10
        return min(raw, 1.0), reasons

    @staticmethod
    def _timestamp(pack: MemoryPack | MemoryPackV11) -> float:
        played_at = pack.match.played_at
        if played_at is None:
            return float("-inf")
        if played_at.utcoffset() is None:
            played_at = played_at.replace(tzinfo=UTC)
        return played_at.timestamp()

    @classmethod
    def _base_sort_key(cls, scored: ScoredPack) -> tuple[float, float, str]:
        return (-scored.breakdown.total, -cls._timestamp(scored.pack), scored.pack.pack_id)

    @classmethod
    def _selection_sort_key(cls, scored: ScoredPack) -> tuple[float, float, str]:
        return (-scored.selection_score, -cls._timestamp(scored.pack), scored.pack.pack_id)

    def _select_diverse(self, items: list[ScoredPack], limit: int) -> list[ScoredPack]:
        remaining = list(items)
        selected: list[ScoredPack] = []
        seen_types: set[MemoryType] = set()
        while remaining and len(selected) < limit:
            adjusted: list[ScoredPack] = []
            for item in remaining:
                penalty = self.diversity_penalty if item.memory_type in seen_types else 0.0
                breakdown = item.breakdown.model_copy(
                    update={
                        "diversity_penalty": penalty,
                    }
                )
                adjusted.append(
                    replace(
                        item,
                        breakdown=breakdown,
                        selection_score=round(max(item.breakdown.total - penalty, 0.0), 4),
                    )
                )
            chosen = min(adjusted, key=self._selection_sort_key)
            selected.append(chosen)
            seen_types.add(chosen.memory_type)
            remaining = [item for item in remaining if item.pack.pack_id != chosen.pack.pack_id]
        return selected

    def _to_candidate(self, scored: ScoredPack, rank: int) -> HistoricalCandidate:
        preview = self._memory_agent.preview(scored.safe_pack, scored.breakdown.total)
        reasons = list(scored.reasons)
        if scored.breakdown.diversity_penalty:
            reasons.append("diversity adjustment for a repeated memory type")
        return HistoricalCandidate(
            rank=rank,
            pack_id=scored.pack.pack_id,
            match_id=scored.pack.match.match_id,
            memory_type=preview.memory_type,
            title=preview.title,
            summary=preview.summary,
            score=scored.breakdown.total,
            ranking_score=scored.selection_score,
            score_breakdown=scored.breakdown,
            reasons=reasons,
            source_status=scored.pack.source_status,
            meaning_status=scored.pack.meaning_status,
            redactions=list(scored.redactions),
        )

    @staticmethod
    def _consent_snapshot(
        packs: list[MemoryPack | MemoryPackV11],
    ) -> dict[str, bool]:
        player_ids = {member.player_id for pack in packs for member in pack.squad.members}
        return {
            player_id: all(
                any(
                    member.player_id == player_id and member.opted_in
                    for member in pack.squad.members
                )
                for pack in packs
            )
            for player_id in player_ids
        }
