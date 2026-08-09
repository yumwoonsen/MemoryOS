"""Deterministic rotation over already-grounded v2 mission affordances.

This policy never creates, edits, or relaxes an affordance.  It only orders the
backend-valid affordances it receives, making it safe to apply after deterministic
preparation.  A caller supplies a stable generation seed and recent selected families;
the returned ranking contains every offered affordance exactly once, with the selected
affordance first, as required by the v2 proposal and validator contracts.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from hashlib import sha256

from backend.models.v2_schemas import MissionAffordanceV2, MissionFamilyV2


@dataclass(frozen=True, slots=True)
class MissionVariationDecisionV2:
    """Auditable result of one deterministic mission-rotation decision."""

    selected_affordance_id: str
    selected_family: MissionFamilyV2
    ranked_affordance_ids: tuple[str, ...]
    available_families: tuple[MissionFamilyV2, ...]
    deferred_recent_families: tuple[MissionFamilyV2, ...]


class MissionVariationPolicyV2:
    """Choose a reproducible specialized mission while avoiding recent families.

    Specialized families always outrank the generic reunion fallback.  When more than
    one specialized family is available, recently selected families are temporarily
    removed from the choice pool.  If that would remove every specialized family, the
    bag resets and all specialized families become eligible again.

    The hash-based shuffle is deliberately independent of Python's randomized ``hash``
    implementation and of the input affordance order.  Callers can therefore reproduce
    a decision from the same affordances, seed, recent-family history, and cooldown.
    """

    def __init__(self, *, recent_family_cooldown: int = 2) -> None:
        if recent_family_cooldown < 0:
            raise ValueError("recent_family_cooldown must be non-negative")
        self._recent_family_cooldown = recent_family_cooldown

    def select(
        self,
        affordances: Iterable[MissionAffordanceV2],
        *,
        seed: str | int,
        recent_families: Sequence[MissionFamilyV2 | str] = (),
    ) -> MissionVariationDecisionV2:
        """Return a full selected-first ranking without changing any affordance."""

        seed_text = str(seed)
        if not seed_text:
            raise ValueError("seed must not be empty")

        offered = tuple(affordances)
        if not offered:
            raise ValueError("at least one mission affordance is required")
        affordance_ids = [affordance.affordance_id for affordance in offered]
        if len(affordance_ids) != len(set(affordance_ids)):
            raise ValueError("mission affordance IDs must be unique")

        by_family: dict[MissionFamilyV2, list[MissionAffordanceV2]] = {}
        for affordance in offered:
            by_family.setdefault(affordance.family, []).append(affordance)

        available_families = tuple(sorted(by_family, key=lambda family: family.value))
        specialized_families = {
            family for family in available_families if family != MissionFamilyV2.REUNION
        }
        recent = self._recent_family_set(recent_families)

        if specialized_families:
            non_recent = specialized_families - recent
            selection_pool = non_recent or specialized_families
        else:
            selection_pool = {MissionFamilyV2.REUNION}

        shuffled_selection_pool = self._shuffle_families(selection_pool, seed_text)
        selected_family = shuffled_selection_pool[0]
        shuffled_selected_affordances = self._shuffle_affordances(
            by_family[selected_family],
            seed_text,
        )
        selected_affordance = shuffled_selected_affordances[0]

        deferred_recent = specialized_families - selection_pool
        ranked_families = list(shuffled_selection_pool)
        ranked_families.extend(self._shuffle_families(deferred_recent, seed_text))
        if MissionFamilyV2.REUNION in by_family and MissionFamilyV2.REUNION not in ranked_families:
            ranked_families.append(MissionFamilyV2.REUNION)

        ranked_affordance_ids = [selected_affordance.affordance_id]
        for family in ranked_families:
            for affordance in self._shuffle_affordances(by_family[family], seed_text):
                if affordance.affordance_id != selected_affordance.affordance_id:
                    ranked_affordance_ids.append(affordance.affordance_id)

        if len(ranked_affordance_ids) != len(offered):
            raise RuntimeError("variation policy failed to rank every offered affordance")

        return MissionVariationDecisionV2(
            selected_affordance_id=selected_affordance.affordance_id,
            selected_family=selected_family,
            ranked_affordance_ids=tuple(ranked_affordance_ids),
            available_families=available_families,
            deferred_recent_families=tuple(
                sorted(deferred_recent, key=lambda family: family.value)
            ),
        )

    def _recent_family_set(
        self,
        recent_families: Sequence[MissionFamilyV2 | str],
    ) -> set[MissionFamilyV2]:
        if self._recent_family_cooldown == 0:
            return set()
        normalized = [MissionFamilyV2(family) for family in recent_families]
        return set(normalized[-self._recent_family_cooldown :])

    @classmethod
    def _shuffle_families(
        cls,
        families: Iterable[MissionFamilyV2],
        seed: str,
    ) -> list[MissionFamilyV2]:
        return sorted(
            families,
            key=lambda family: cls._shuffle_key(seed, "family", family.value),
        )

    @classmethod
    def _shuffle_affordances(
        cls,
        affordances: Iterable[MissionAffordanceV2],
        seed: str,
    ) -> list[MissionAffordanceV2]:
        return sorted(
            affordances,
            key=lambda affordance: cls._shuffle_key(
                seed,
                "affordance",
                affordance.affordance_id,
            ),
        )

    @staticmethod
    def _shuffle_key(seed: str, scope: str, value: str) -> tuple[bytes, str]:
        digest = sha256(f"{seed}\x1f{scope}\x1f{value}".encode()).digest()
        return digest, value
