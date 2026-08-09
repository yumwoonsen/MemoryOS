"""Single-proposal interpretation boundary for MemoryOS v2."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from backend.models.schemas import MemoryType, QuestRecipe
from backend.models.v2_provider_schemas import (
    MissionObjectiveKindV2,
    ProviderInterpretationDecisionV2,
    ProviderMemoryProposalV2,
    ProviderMissionAffordanceV2,
    ProviderMissionChoiceV2,
    ProviderMissionObjectiveV2,
    ProviderSourceRoleBindingV2,
    ProviderStoryBriefV2,
    ProviderWindowV2,
)
from backend.models.v2_schemas import (
    CanonicalEventType,
    ClaimPredicate,
    CompactInterpretationDecisionV2,
    CompactMemoryProposalV2,
    CompactMissionChoiceV2,
    CompactPerspectiveV2,
    CompactSectionDraftV2,
    GroundedClaim,
    InterpretationAbstentionReasonV2,
    InterpretationDecisionKindV2,
    MemoryProposalV2,
    MissionAffordanceV2,
    MissionCapabilityCandidate,
    MissionFamilyV2,
    ProposedMissionObjectiveV2,
    ProposedMissionV2,
    ProposedPerspectiveV2,
)
from backend.services.structured_generator import StructuredGenerator
from backend.services.v2_mission_copy_compiler import (
    compile_mission_objective_descriptions,
)
from backend.services.v2_preparation import PreparedInterpretationV2
from backend.services.v2_proposal_expander import (
    CompactProposalExpanderV2,
    CompactProposalExpansionError,
)

MAX_PROVIDER_PAYLOAD_BYTES = 96_000
PROVIDER_REFERENCE_PATTERN = re.compile(r"^[WAO][1-9][0-9]*$")


class ProviderInputLimitError(ValueError):
    """The sanitized prompt projection exceeded a deterministic provider boundary."""


@dataclass(frozen=True)
class _ProviderCatalogV2:
    """Request-scoped aliases used only across the external model boundary."""

    brief: ProviderStoryBriefV2
    window_id_by_ref: dict[str, str]
    affordance_id_by_ref: dict[str, str]
    objective_id_by_ref: dict[str, str]
    window_ref_by_id: dict[str, str]
    affordance_ref_by_id: dict[str, str]
    objective_ref_by_id: dict[str, str]


EVENT_LANGUAGE: dict[CanonicalEventType, tuple[ClaimPredicate, str]] = {
    CanonicalEventType.LANDING: (ClaimPredicate.LANDED, "landed"),
    CanonicalEventType.KNOCK: (ClaimPredicate.KNOCKED, "knocked an opponent"),
    CanonicalEventType.ELIMINATION: (ClaimPredicate.ELIMINATED, "secured an elimination"),
    CanonicalEventType.REVIVE: (ClaimPredicate.REVIVED, "revived a squadmate"),
    CanonicalEventType.ASSIST: (ClaimPredicate.ASSISTED, "recorded an assist"),
    CanonicalEventType.HEAL: (ClaimPredicate.HEALED, "recovered health"),
    CanonicalEventType.VEHICLE_ENTER: (
        ClaimPredicate.ENTERED_VEHICLE,
        "entered a vehicle",
    ),
    CanonicalEventType.VEHICLE_EXIT: (ClaimPredicate.EXITED_VEHICLE, "left a vehicle"),
    CanonicalEventType.ESCAPE: (ClaimPredicate.ESCAPED, "escaped the area"),
    CanonicalEventType.ZONE_MOVE: (ClaimPredicate.MOVED_ZONE, "rotated toward safety"),
    CanonicalEventType.LOOT: (ClaimPredicate.LOOTED, "collected supplies"),
    CanonicalEventType.SIGNAL: (ClaimPredicate.SIGNALLED, "placed a tactical signal"),
    CanonicalEventType.MATCH_COMPLETE: (
        ClaimPredicate.COMPLETED_MATCH,
        "completed the match",
    ),
}


class MemoryInterpreterV2:
    """Ask one live provider for a complete proposal, or run an explicit demo interpreter."""

    prompt_version = "memory-interpreter-v2.13-perspective-safe-variation"

    def __init__(self, generator: StructuredGenerator | None = None) -> None:
        self._generator = generator
        self._expander = CompactProposalExpanderV2()

    @property
    def provider_name(self) -> str:
        return self._generator.provider_name if self._generator else "deterministic"

    @property
    def model_name(self) -> str:
        return self._generator.model_name if self._generator else "grounded-demo-v2"

    @property
    def mode(self) -> str:
        return "live_ai" if self._generator else "deterministic_demo"

    @property
    def observability(self) -> dict[str, object]:
        value = getattr(self._generator, "observability", {})
        return dict(value) if isinstance(value, dict) else {}

    def validate_configuration(self) -> None:
        validate = getattr(self._generator, "validate_configuration", None)
        if validate:
            validate()

    def propose(
        self,
        prepared: PreparedInterpretationV2,
        *,
        validation_feedback: list[dict[str, str]] | None = None,
    ) -> MemoryProposalV2 | InterpretationAbstentionReasonV2:
        if prepared.normalized is None or prepared.ledger is None or prepared.story_brief is None:
            raise ValueError("prepared telemetry is required")
        if self._generator is None:
            return self._deterministic_demo(prepared)

        payload = self._provider_payload(prepared)
        stage = "memory_interpretation"
        if validation_feedback:
            stage = "memory_interpretation_correction"
            payload["correction"] = {
                "validation_issues": validation_feedback,
                "instruction": (
                    "Return one complete corrected ProviderInterpretationDecisionV2 and emit "
                    "every schema field. Resolve each issue in its allowlisted section when "
                    "supplied. This is a strict rewrite, not an edit: do not carry over any "
                    "unsupported context from a prior draft. Copy only offered request-scoped "
                    "A references, rank every offered A reference once with the selection first, "
                    "and use only its reason codes. Write a fresh mission title and short story "
                    "bridge; the backend renders the objective requirements. When "
                    "text mentions a player, action, location, match value, category, or number, "
                    "cite exact support or remove that wording. For every section flagged with "
                    "unsupported_categorical_detail, remove all exact categorical and zone values "
                    "from that section instead of trying to preserve decorative detail."
                ),
                "strict_section_rules": {
                    "story": (
                        "Use only literal facts from the selected evidence IDs. Do not use a "
                        "source match outside the selected affordance's linked window as evidence "
                        "for player-story sections; additional source_match_ids are mission-"
                        "selection context only. Do not use a "
                        "category word such as a vehicle, zone, weapon, item, or ping type unless "
                        "the unchanged evidence_bound_terms contains that exact field and value "
                        "for evidence cited in the section. A zone phase is not a zone state."
                    ),
                    "perspectives": (
                        "Write one short first-person sentence per narrator. Use that narrator's "
                        "unchanged player_event_roles map literally: actor allows active wording, "
                        "target allows only passive or affected wording, and full_squad allows "
                        "only we/the squad. For perspectives_not_distinct, assign exactly one "
                        "different permitted linked-window event to each narrator before changing "
                        "wording. Prefer actor or target evidence over full_squad evidence. Use I "
                        "only for actor or target evidence and We/The squad only for full_squad "
                        "evidence. Normalized messages must be unique. Every perspective must cite "
                        "a permitted event from the "
                        "selected linked window; match or context IDs alone are insufficient. Do "
                        "not mention another player's action as before/after context. Keep every "
                        "perspective category-free: do not copy vehicle types, weapon classes, "
                        "item types, ping types, health states, zone states, or zone phases from "
                        "evidence_bound_terms. Use the supported action and location instead. A "
                        "narrator with only full_squad evidence must use one short collective "
                        "sentence beginning with 'We' or 'The squad', such as 'We escaped the "
                        "area together.'"
                    ),
                    "action_roles": (
                        "Use one gameplay action per sentence. Put the supported actor directly "
                        "before the action and its supported target directly after it, or use "
                        "'<target> was <action> by <actor>'. Do not use action clauses introduced "
                        "by after, before, while, when, or as."
                    ),
                    "mission": (
                        "Use only the first-ranked A affordance and its nested O capabilities. "
                        "Treat A order, reference number, objective count, and wording ease as "
                        "non-preference signals. Recompare how directly each offered A continues "
                        "its source evidence, using reunion as the general fallback rather than "
                        "the automatic first choice. Write only a short story_bridge explaining "
                        "why the selected continuation follows from the episode. It may paraphrase "
                        "the selected mechanic, but it must not add another mechanic, target, "
                        "threshold, player assignment, or condition. Objective requirements are "
                        "backend-owned and must not be rewritten. Treat objective_role and "
                        "required as authoritative; never promote a bonus into a requirement."
                    ),
                },
            }
        encoded_size = len(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        )
        if encoded_size > MAX_PROVIDER_PAYLOAD_BYTES:
            raise ProviderInputLimitError("sanitized provider payload exceeds its byte limit")
        decision = self._generator.generate(
            prompt_name="memory_interpreter_v2_13.txt",
            payload=payload,
            response_model=ProviderInterpretationDecisionV2,
            stage=stage,
        )
        # Compatibility for test generators and v2.0 provider fixtures during migration.
        if isinstance(decision, CompactMemoryProposalV2):
            decision = CompactInterpretationDecisionV2(
                decision=InterpretationDecisionKindV2.GENERATE,
                abstention_reason_code=None,
                proposal=decision,
            )
        if isinstance(decision, CompactInterpretationDecisionV2):
            if decision.decision == InterpretationDecisionKindV2.ABSTAIN:
                assert decision.abstention_reason_code is not None
                return decision.abstention_reason_code
            assert decision.proposal is not None
            return self._expander.expand(prepared, decision.proposal)
        if decision.decision == InterpretationDecisionKindV2.ABSTAIN:
            assert decision.abstention_reason_code is not None
            return decision.abstention_reason_code
        assert decision.proposal is not None
        compact = self._resolve_provider_proposal(prepared, decision.proposal)
        return self._expander.expand(prepared, compact)

    @classmethod
    def _provider_payload(cls, prepared: PreparedInterpretationV2) -> dict[str, Any]:
        assert prepared.normalized is not None
        assert prepared.ledger is not None
        assert prepared.story_brief is not None
        catalog = cls._provider_catalog(prepared)
        return {
            "contract": "ProviderInterpretationDecisionV2",
            # Empty optional placeholders add tokens but carry no evidence. Keep every
            # concrete value—including false privacy/capability signals—while omitting
            # only nulls from the provider projection.
            "story_brief": catalog.brief.model_dump(
                mode="json",
                exclude_none=True,
            ),
        }

    @classmethod
    def _provider_catalog(cls, prepared: PreparedInterpretationV2) -> _ProviderCatalogV2:
        """Project canonical preparation into compact, request-scoped provider handles."""

        assert prepared.normalized is not None
        assert prepared.story_brief is not None

        window_ref_by_id = {
            window.window_id: f"W{index}" for index, window in enumerate(prepared.windows, start=1)
        }
        affordance_ref_by_id = {
            affordance.affordance_id: f"A{index}"
            for index, affordance in enumerate(prepared.mission_affordances, start=1)
        }
        objective_ref_by_id = {
            objective.candidate_id: f"O{index}"
            for index, objective in enumerate(prepared.mission_candidates, start=1)
        }
        if len(window_ref_by_id) != len(prepared.windows):
            raise ValueError("eligible event window IDs must be unique")
        if len(affordance_ref_by_id) != len(prepared.mission_affordances):
            raise ValueError("mission affordance IDs must be unique")
        if len(objective_ref_by_id) != len(prepared.mission_candidates):
            raise ValueError("mission objective candidate IDs must be unique")

        provider_windows = [
            ProviderWindowV2(
                window_ref=window_ref_by_id[window.window_id],
                match_id=window.match_id,
                event_ids=window.event_ids,
                participant_ids=window.participant_ids,
                start_seconds=window.start_seconds,
                end_seconds=window.end_seconds,
            )
            for window in prepared.windows
        ]
        candidate_by_id = {
            candidate.candidate_id: candidate for candidate in prepared.mission_candidates
        }
        display_name_by_id = {
            player.player_id: player.display_name for player in prepared.normalized.players
        }
        event_by_id = {
            event.event_id: event for match in prepared.normalized.matches for event in match.events
        }
        provider_affordances: list[ProviderMissionAffordanceV2] = []
        for affordance in prepared.mission_affordances:
            objectives = [
                cls._provider_objective(
                    candidate_by_id[candidate_id],
                    affordance,
                    objective_ref_by_id[candidate_id],
                    prepared.story_brief.invitation_player_ids,
                    display_name_by_id,
                )
                for candidate_id in affordance.objective_candidate_ids
            ]
            role_binding = cls._provider_role_binding(
                affordance,
                objectives,
                event_by_id,
            )
            provider_affordances.append(
                ProviderMissionAffordanceV2(
                    affordance_ref=affordance_ref_by_id[affordance.affordance_id],
                    family=affordance.family,
                    window_ref=window_ref_by_id[affordance.window_id],
                    source_event_ids=affordance.source_event_ids,
                    source_match_ids=affordance.source_match_ids,
                    source_context_ids=affordance.source_context_ids,
                    allowed_reason_codes=affordance.allowed_reason_codes,
                    objectives=objectives,
                    source_role_binding=role_binding,
                )
            )

        story = prepared.story_brief
        brief = ProviderStoryBriefV2(
            request_id=story.request_id,
            target_player_id=story.target_player_id,
            players_requiring_perspectives=story.players_requiring_perspectives,
            invitation_player_ids=story.invitation_player_ids,
            active_player_ids=story.active_player_ids,
            evidence_ledger=story.evidence_ledger,
            windows=provider_windows,
            affordances=provider_affordances,
            authoring_constraints=story.authoring_constraints,
            squad_history=story.squad_history,
            current_context=story.current_context,
            media_references=story.media_references,
        )
        return _ProviderCatalogV2(
            brief=brief,
            window_id_by_ref={value: key for key, value in window_ref_by_id.items()},
            affordance_id_by_ref={value: key for key, value in affordance_ref_by_id.items()},
            objective_id_by_ref={value: key for key, value in objective_ref_by_id.items()},
            window_ref_by_id=window_ref_by_id,
            affordance_ref_by_id=affordance_ref_by_id,
            objective_ref_by_id=objective_ref_by_id,
        )

    @staticmethod
    def _provider_objective(
        candidate: MissionCapabilityCandidate,
        affordance: MissionAffordanceV2,
        objective_ref: str,
        invitation_player_ids: list[str],
        display_name_by_id: dict[str, str],
    ) -> ProviderMissionObjectiveV2:
        metric = candidate.verification.metric
        target = candidate.verification.target
        if metric == "squad.participant_ids":
            if target != invitation_player_ids:
                raise ValueError(
                    "participant capability must use the consent-safe invitation roster"
                )
            return ProviderMissionObjectiveV2(
                objective_ref=objective_ref,
                kind=MissionObjectiveKindV2.REQUIRED_PARTICIPANTS,
                objective_role=candidate.objective_role,
                required=candidate.required,
                required_terms=["invited squad", "queue", "match"],
                roster_ref="invitation_player_ids",
            )
        if metric == "squad.matches_completed":
            if type(target) is not int:
                raise ValueError("match completion capability requires an integer target")
            return ProviderMissionObjectiveV2(
                objective_ref=objective_ref,
                kind=MissionObjectiveKindV2.COMPLETED_MATCHES,
                objective_role=candidate.objective_role,
                required=candidate.required,
                required_terms=["complete", f"at least {target}", "match"],
                minimum_count=target,
            )
        if metric == "match.first_squad_revive_actor_id":
            if (
                not isinstance(target, str)
                or candidate.assigned_player_id != target
                or target not in invitation_player_ids
            ):
                raise ValueError("event actor capability requires one invitation-safe assignee")
            return ProviderMissionObjectiveV2(
                objective_ref=objective_ref,
                kind=MissionObjectiveKindV2.EVENT_ACTOR,
                objective_role=candidate.objective_role,
                required=candidate.required,
                required_terms=[display_name_by_id[target], "completes", "first", "revive"],
                assigned_player_id=target,
                event_type=CanonicalEventType.REVIVE,
                ordinal="first",
            )
        if metric == "match.top_three_reached":
            placement = affordance.parameters.get("target_placement_max")
            if target is not True or type(placement) is not int:
                raise ValueError("placement capability requires an authoritative placement limit")
            return ProviderMissionObjectiveV2(
                objective_ref=objective_ref,
                kind=MissionObjectiveKindV2.PLACEMENT_AT_MOST,
                objective_role=candidate.objective_role,
                required=candidate.required,
                required_terms=[f"top {placement}"],
                placement_at_most=placement,
            )
        if metric == "match.invited_squad_visits_location":
            if (
                candidate.assigned_player_id is not None
                or candidate.verification.operator != "equals"
                or not isinstance(target, str)
                or not target.strip()
            ):
                raise ValueError("squad-location capability requires one non-empty location")
            return ProviderMissionObjectiveV2(
                objective_ref=objective_ref,
                kind=MissionObjectiveKindV2.RETURN_TO_LOCATION,
                objective_role=candidate.objective_role,
                required=candidate.required,
                required_terms=["return", target, "invited squad"],
                location=target,
            )
        if metric == "match.invited_squad_lands_at_location":
            invitation_ids = affordance.parameters.get("invitation_player_ids")
            if (
                candidate.assigned_player_id is not None
                or candidate.verification.operator != "equals"
                or not isinstance(target, str)
                or not target.strip()
                or affordance.parameters.get("landing_location") != target
                or invitation_ids != invitation_player_ids
            ):
                raise ValueError("landing capability requires the safe roster and one location")
            return ProviderMissionObjectiveV2(
                objective_ref=objective_ref,
                kind=MissionObjectiveKindV2.LANDING_RENDEZVOUS,
                objective_role=candidate.objective_role,
                required=candidate.required,
                required_terms=["land", target, "invited squad"],
                roster_ref="invitation_player_ids",
                location=target,
            )
        if metric == "match.assigned_player_assisted_elimination_player_ids":
            assister_id = affordance.parameters.get("assister_player_id")
            teammate_id = affordance.parameters.get("elimination_player_id")
            if (
                candidate.verification.operator != "contains_all"
                or target != [teammate_id]
                or candidate.assigned_player_id != assister_id
                or not isinstance(assister_id, str)
                or not isinstance(teammate_id, str)
                or assister_id == teammate_id
                or assister_id not in invitation_player_ids
                or teammate_id not in invitation_player_ids
            ):
                raise ValueError("duo-assist capability requires one invitation-safe pair")
            return ProviderMissionObjectiveV2(
                objective_ref=objective_ref,
                kind=MissionObjectiveKindV2.DUO_ASSIST,
                objective_role=candidate.objective_role,
                required=candidate.required,
                required_terms=[
                    display_name_by_id[assister_id],
                    "assists",
                    display_name_by_id[teammate_id],
                    "an elimination",
                ],
                assigned_player_id=assister_id,
                teammate_player_id=teammate_id,
                minimum_count=1,
            )
        if metric == "match.first_squad_tactical_signal_actor_id":
            signal_player_id = affordance.parameters.get("signal_player_id")
            if (
                candidate.verification.operator != "equals"
                or not isinstance(target, str)
                or candidate.assigned_player_id != target
                or signal_player_id != target
                or target not in invitation_player_ids
            ):
                raise ValueError(
                    "tactical-signal capability requires one invitation-safe assignee"
                )
            return ProviderMissionObjectiveV2(
                objective_ref=objective_ref,
                kind=MissionObjectiveKindV2.TACTICAL_SIGNAL,
                objective_role=candidate.objective_role,
                required=candidate.required,
                required_terms=[
                    display_name_by_id[target],
                    "places",
                    "first",
                    "tactical signal",
                ],
                assigned_player_id=target,
                ordinal="first",
            )
        if metric == "match.invited_squad_vehicle_escape_within_seconds":
            invitation_ids = affordance.parameters.get("invitation_player_ids")
            maximum_seconds = affordance.parameters.get("vehicle_escape_window_seconds")
            if (
                candidate.verification.operator != "equals"
                or target is not True
                or candidate.assigned_player_id is not None
                or invitation_ids != invitation_player_ids
                or isinstance(maximum_seconds, bool)
                or not isinstance(maximum_seconds, int)
                or not 1 <= maximum_seconds <= 300
            ):
                raise ValueError(
                    "vehicle-extraction capability requires the safe roster and time window"
                )
            return ProviderMissionObjectiveV2(
                objective_ref=objective_ref,
                kind=MissionObjectiveKindV2.FULL_SQUAD_VEHICLE_EXTRACTION,
                objective_role=candidate.objective_role,
                required=candidate.required,
                required_terms=[
                    "invited squad",
                    "board",
                    "one vehicle",
                    "leave",
                    "danger zone",
                    f"within {maximum_seconds} seconds",
                ],
                roster_ref="invitation_player_ids",
                maximum_seconds=maximum_seconds,
            )
        raise ValueError(f"unsupported mission capability metric: {metric}")

    @staticmethod
    def _provider_role_binding(
        affordance: MissionAffordanceV2,
        objectives: list[ProviderMissionObjectiveV2],
        event_by_id: dict[str, Any],
    ) -> ProviderSourceRoleBindingV2 | None:
        if affordance.family != MissionFamilyV2.ROLE_REVERSAL:
            return None
        source_event = next(
            (
                event_by_id[event_id]
                for event_id in affordance.source_event_ids
                if event_id in event_by_id
                and event_by_id[event_id].event_type == CanonicalEventType.REVIVE
            ),
            None,
        )
        actor_objective = next(
            (
                objective
                for objective in objectives
                if objective.kind == MissionObjectiveKindV2.EVENT_ACTOR
            ),
            None,
        )
        if (
            source_event is None
            or source_event.actor_id is None
            or source_event.target_id is None
            or actor_objective is None
            or actor_objective.assigned_player_id is None
        ):
            raise ValueError("role reversal capability requires source and future actor roles")
        return ProviderSourceRoleBindingV2(
            source_event_id=source_event.event_id,
            event_type=source_event.event_type,
            source_actor_id=source_event.actor_id,
            source_target_id=source_event.target_id,
            future_actor_id=actor_objective.assigned_player_id,
        )

    @classmethod
    def _resolve_provider_proposal(
        cls,
        prepared: PreparedInterpretationV2,
        proposal: ProviderMemoryProposalV2,
    ) -> CompactMemoryProposalV2:
        """Normalize harmless handle formatting, then restore canonical backend IDs."""

        catalog = cls._provider_catalog(prepared)
        canonical_ranking: list[str] = []
        seen_affordances: set[str] = set()
        for index, raw_ref in enumerate(proposal.mission.ranked_affordance_refs):
            reference = cls._normalize_provider_ref(raw_ref, "A")
            affordance_id = (
                catalog.affordance_id_by_ref.get(reference) if reference is not None else None
            )
            if affordance_id is None:
                code = (
                    "invented_mission_affordance"
                    if index == 0
                    else "mission_affordance_ranking_invalid"
                )
                raise CompactProposalExpansionError(code)
            if affordance_id not in seen_affordances:
                canonical_ranking.append(affordance_id)
                seen_affordances.add(affordance_id)
        if set(canonical_ranking) != set(catalog.affordance_ref_by_id):
            raise CompactProposalExpansionError("mission_affordance_ranking_invalid")

        selected_affordance_id = canonical_ranking[0]
        selected_affordance = next(
            item
            for item in prepared.mission_affordances
            if item.affordance_id == selected_affordance_id
        )
        return CompactMemoryProposalV2(
            selected_window_id=selected_affordance.window_id,
            memory_type=proposal.memory_type,
            narrative_angle=proposal.narrative_angle,
            title=proposal.title,
            notification_teaser=proposal.notification_teaser,
            summary=proposal.summary,
            why_this_matters_now=proposal.why_this_matters_now,
            perspectives=proposal.perspectives,
            mission=CompactMissionChoiceV2(
                ranked_affordance_ids=canonical_ranking,
                selected_affordance_id=selected_affordance_id,
                selection_reason_codes=proposal.mission.selection_reason_codes,
                title=proposal.mission.title,
                story_bridge=proposal.mission.story_bridge,
            ),
        )

    @staticmethod
    def _normalize_provider_ref(value: str, prefix: str) -> str | None:
        normalized = value.strip().upper()
        if not PROVIDER_REFERENCE_PATTERN.fullmatch(normalized):
            return None
        if not normalized.startswith(prefix):
            return None
        return normalized

    def demo_compact_proposal(
        self,
        prepared: PreparedInterpretationV2,
    ) -> CompactMemoryProposalV2:
        """Return a compact deterministic fixture for provider-boundary tests."""

        canonical = self._deterministic_demo(prepared)
        return CompactMemoryProposalV2(
            selected_window_id=canonical.selected_window_id,
            memory_type=canonical.memory_type,
            narrative_angle=canonical.narrative_angle,
            title=self._compact_section(canonical, "title", canonical.title),
            notification_teaser=self._compact_section(
                canonical,
                "notification_teaser",
                canonical.notification_teaser,
            ),
            summary=self._compact_section(canonical, "summary", canonical.summary),
            why_this_matters_now=self._compact_section(
                canonical,
                "why_this_matters_now",
                canonical.why_this_matters_now,
            ),
            perspectives=[
                CompactPerspectiveV2(
                    player_id=item.player_id,
                    message=item.message,
                    evidence_ids=item.evidence_event_ids,
                )
                for item in canonical.perspectives
            ],
            mission=CompactMissionChoiceV2(
                ranked_affordance_ids=canonical.mission.ranked_affordance_ids,
                selected_affordance_id=canonical.mission.affordance_id,
                selection_reason_codes=canonical.mission.selection_reason_codes,
                title=canonical.mission.title,
                story_bridge=canonical.mission.mission,
            ),
        )

    def demo_provider_decision(
        self,
        prepared: PreparedInterpretationV2,
    ) -> ProviderInterpretationDecisionV2:
        """Return the deterministic fixture expressed through provider-only handles."""

        compact = self.demo_compact_proposal(prepared)
        catalog = self._provider_catalog(prepared)
        provider_proposal = ProviderMemoryProposalV2(
            memory_type=compact.memory_type,
            narrative_angle=compact.narrative_angle,
            title=compact.title,
            notification_teaser=compact.notification_teaser,
            summary=compact.summary,
            why_this_matters_now=compact.why_this_matters_now,
            perspectives=compact.perspectives,
            mission=ProviderMissionChoiceV2(
                ranked_affordance_refs=[
                    catalog.affordance_ref_by_id[affordance_id]
                    for affordance_id in compact.mission.ranked_affordance_ids
                ],
                selection_reason_codes=compact.mission.selection_reason_codes,
                title=compact.mission.title,
                story_bridge=compact.mission.story_bridge,
            ),
        )
        return ProviderInterpretationDecisionV2(
            decision=InterpretationDecisionKindV2.GENERATE,
            abstention_reason_code=None,
            proposal=provider_proposal,
        )

    @classmethod
    def _compact_section(
        cls,
        canonical: MemoryProposalV2,
        output_section: str,
        text: str,
    ) -> CompactSectionDraftV2:
        evidence_ids: list[str] = []
        for claim in canonical.claims:
            if claim.output_section != output_section:
                continue
            evidence_ids.extend(claim.supporting_event_ids)
            evidence_ids.extend(
                cls._compact_context_id(context_id, canonical.selected_match_id)
                for context_id in claim.supporting_context_ids
            )
        return CompactSectionDraftV2(
            text=text,
            evidence_ids=list(dict.fromkeys(evidence_ids)),
        )

    @staticmethod
    def _compact_context_id(context_id: str, selected_match_id: str) -> str:
        prefix = f"match:{selected_match_id}:"
        if context_id.startswith(prefix):
            return f"match:{context_id[len(prefix) :]}"
        return context_id

    def _deterministic_demo(self, prepared: PreparedInterpretationV2) -> MemoryProposalV2:
        """A test/Studio demonstration, never a fallback for failed live AI."""

        assert prepared.normalized is not None
        affordance_window_ids = {item.window_id for item in prepared.mission_affordances}
        window = max(
            [item for item in prepared.windows if item.window_id in affordance_window_ids],
            key=lambda item: (len(item.event_ids), len(item.participant_ids), item.window_id),
        )
        matches = {match.match_id: match for match in prepared.normalized.matches}
        match = matches[window.match_id]
        event_map = {event.event_id: event for event in match.events}
        events = [event_map[event_id] for event_id in window.event_ids]
        people = {player.player_id: player for player in prepared.normalized.players}
        location = next((event.location for event in events if event.location), None)
        place_phrase = f" at {location}" if location else ""
        event_types = {event.event_type for event in events}
        if CanonicalEventType.REVIVE in event_types:
            memory_type = MemoryType.COMEBACK
            angle = "A squadmate recovery connected a short sequence of shared actions."
        elif CanonicalEventType.ESCAPE in event_types:
            memory_type = MemoryType.CHAOS
            angle = "Several squad actions formed one connected escape sequence."
        elif CanonicalEventType.KNOCK in event_types:
            memory_type = MemoryType.CLUTCH
            angle = "The squad's actions converged during a compact combat sequence."
        else:
            memory_type = MemoryType.OTHER
            angle = "The telemetry shows a connected sequence involving the squad."

        title = f"A Squad Moment{place_phrase}"
        teaser = f"Your squad shared a connected moment{place_phrase}."
        sentences: list[str] = []
        action_claims: list[GroundedClaim] = []
        for index, event in enumerate(events[:3], start=1):
            predicate, language = EVENT_LANGUAGE[event.event_type]
            if event.event_type == CanonicalEventType.KNOCK and event.actor_id is None:
                predicate, language = ClaimPredicate.WAS_KNOCKED, "was knocked"
            elif event.event_type == CanonicalEventType.ELIMINATION and event.actor_id is None:
                predicate, language = ClaimPredicate.WAS_ELIMINATED, "was eliminated"
            subject_id = event.actor_id or event.target_id or "squad"
            name = people.get(subject_id).display_name if subject_id in people else "The squad"
            target_name = (
                people[event.target_id].display_name
                if event.target_id and event.target_id in people
                else None
            )
            suffix = f" for {target_name}" if target_name and event.target_id != subject_id else ""
            event_place = f" at {event.location}" if event.location else ""
            sentences.append(f"{name} {language}{suffix}{event_place}.")
            action_claims.append(
                GroundedClaim(
                    claim_id=f"claim:summary:{index}",
                    output_section="summary",
                    subject_id=subject_id,
                    predicate=predicate,
                    target_id=(
                        None
                        if predicate in {ClaimPredicate.WAS_KNOCKED, ClaimPredicate.WAS_ELIMINATED}
                        else event.target_id
                    ),
                    location=event.location,
                    supporting_event_ids=[event.event_id],
                )
            )
        summary = " ".join(sentences)
        if not summary:
            summary = f"The squad completed a connected sequence{place_phrase}."

        base_claims = [
            GroundedClaim(
                claim_id=f"claim:{section}",
                output_section=section,
                subject_id="squad",
                predicate=ClaimPredicate.CONNECTED_EPISODE,
                location=location,
                supporting_event_ids=window.event_ids,
            )
            for section in ("title", "notification_teaser")
        ]
        base_claims.extend(action_claims)

        history = prepared.normalized.squad_history
        if history.days_since_full_squad is not None:
            why_now = (
                f"It has been {history.days_since_full_squad} days since the full squad played."
            )
            context_ids = ["context:days_since_full_squad"]
            context_value: int | list[str] = history.days_since_full_squad
        else:
            why_now = "The current squad context allows a reunion invitation."
            context_ids = ["context:reunion_eligible"]
            context_value = True
        base_claims.append(
            GroundedClaim(
                claim_id="claim:why-now",
                output_section="why_this_matters_now",
                subject_id="squad",
                predicate=ClaimPredicate.CURRENT_REUNION_OPPORTUNITY,
                value=context_value,
                supporting_context_ids=context_ids,
            )
        )

        perspectives: list[ProposedPerspectiveV2] = []
        for player in prepared.normalized.players:
            if not player.memory_eligible:
                continue
            direct = next(
                (
                    event
                    for event in events
                    if player.player_id in {event.actor_id, event.target_id}
                ),
                None,
            )
            if direct and direct.actor_id == player.player_id:
                predicate, language = EVENT_LANGUAGE[direct.event_type]
                direct_place = f" at {direct.location}" if direct.location else ""
                message = (
                    f"{player.display_name}, you {language}{direct_place}; "
                    "that action became part of this moment."
                )
                target_id = direct.target_id
            else:
                predicate = ClaimPredicate.PARTICIPATED_MATCH
                message = (
                    f"{player.display_name}, you were part of the squad match behind this "
                    "shared moment."
                )
                target_id = None
            evidence_ids = [direct.event_id] if direct else [window.event_ids[0]]
            perspectives.append(
                ProposedPerspectiveV2(
                    player_id=player.player_id,
                    message=message,
                    evidence_event_ids=evidence_ids,
                )
            )
            base_claims.append(
                GroundedClaim(
                    claim_id=f"claim:perspective:{player.player_id}",
                    output_section=f"perspective:{player.player_id}",
                    subject_id=player.player_id,
                    predicate=predicate,
                    target_id=target_id,
                    location=direct.location if direct else None,
                    supporting_event_ids=evidence_ids,
                )
            )

        available_affordances = [
            affordance
            for affordance in prepared.mission_affordances
            if affordance.window_id == window.window_id
        ]
        family_priority = {
            MissionFamilyV2.ROLE_REVERSAL: 0,
            MissionFamilyV2.DUO_ASSIST: 1,
            MissionFamilyV2.RETURN_TO_PLACE: 2,
            MissionFamilyV2.LANDING_RENDEZVOUS: 3,
            MissionFamilyV2.REDEMPTION: 4,
            MissionFamilyV2.REUNION: 5,
        }
        selected_affordance = min(
            available_affordances,
            key=lambda item: (family_priority[item.family], item.affordance_id),
        )
        candidate_map = {
            candidate.candidate_id: candidate for candidate in prepared.mission_candidates
        }
        chosen = [
            candidate_map[candidate_id]
            for candidate_id in selected_affordance.objective_candidate_ids
        ]
        recipe = chosen[0].recipe if chosen else QuestRecipe.RECREATE
        compiled_descriptions = compile_mission_objective_descriptions(
            selected_affordance,
            chosen,
            {player_id: player.display_name for player_id, player in people.items()},
        )
        objectives = [
            ProposedMissionObjectiveV2(
                candidate_id=candidate.candidate_id,
                description=compiled_descriptions[candidate.candidate_id],
                objective_role=candidate.objective_role,
                required=candidate.required,
            )
            for candidate in chosen
        ]
        for candidate in chosen:
            base_claims.append(
                GroundedClaim(
                    claim_id=f"claim:objective:{candidate.candidate_id}",
                    output_section=f"objective:{candidate.candidate_id}",
                    subject_id=candidate.assigned_player_id or "squad",
                    predicate=ClaimPredicate.MISSION_RULE,
                    supporting_mission_candidate_ids=[candidate.candidate_id],
                )
            )
        base_claims.append(
            GroundedClaim(
                claim_id="claim:mission",
                output_section="mission",
                subject_id="squad",
                predicate=ClaimPredicate.MISSION_RULE,
                supporting_mission_candidate_ids=[item.candidate_id for item in chosen],
            )
        )
        selected_media = next(
            (
                media
                for media in prepared.normalized.media_references
                if set(media.event_ids).issubset(window.event_ids)
            ),
            None,
        )
        if selected_affordance.family == MissionFamilyV2.ROLE_REVERSAL:
            mission_title = "Return the Favour"
            mission_text = "Turn the original rescue into a role reversal for the next match."
        elif selected_affordance.family == MissionFamilyV2.REDEMPTION:
            mission_title = "Finish the Final Circle"
            mission_text = "Turn those near misses into a top-three comeback."
        elif selected_affordance.family == MissionFamilyV2.RETURN_TO_PLACE:
            mission_title = "Return to the Rescue"
            mission_text = "Go back to the place where the squad recovered together."
        elif selected_affordance.family == MissionFamilyV2.LANDING_RENDEZVOUS:
            mission_title = "Same Drop, New Chapter"
            mission_text = "Bring the squad back together at its shared landing point."
        elif selected_affordance.family == MissionFamilyV2.DUO_ASSIST:
            mission_title = "Set Up the Finish"
            mission_text = "Turn the original assist partnership into the next shared finish."
        else:
            mission_title = "Return Together"
            mission_text = "Bring the original squad back together for the next chapter."
        ranked_affordance_ids = [
            selected_affordance.affordance_id,
            *sorted(
                affordance.affordance_id
                for affordance in prepared.mission_affordances
                if affordance.affordance_id != selected_affordance.affordance_id
            ),
        ]
        return MemoryProposalV2(
            selected_match_id=window.match_id,
            selected_window_id=window.window_id,
            selected_event_ids=window.event_ids,
            memory_type=memory_type,
            narrative_angle=angle,
            title=title,
            notification_teaser=teaser,
            summary=summary,
            why_this_matters_now=why_now,
            perspectives=perspectives,
            mission=ProposedMissionV2(
                affordance_id=selected_affordance.affordance_id,
                family=selected_affordance.family,
                ranked_affordance_ids=ranked_affordance_ids,
                selection_reason_codes=[selected_affordance.allowed_reason_codes[0]],
                title=mission_title,
                mission=mission_text,
                recipe=recipe,
                objectives=objectives,
            ),
            claims=base_claims,
            media_id=selected_media.media_id if selected_media else None,
        )
