"""Regression tests for the synthetic historical evaluation metrics."""

from __future__ import annotations

import json
from pathlib import Path

from backend.evaluate import DATA_DIR, evaluate
from backend.services.identity import contains_identity


def test_consent_leak_matcher_normalizes_common_identity_separators() -> None:
    assert contains_identity("private user", "private_user")
    assert contains_identity("private-user", "private_user")
    assert not contains_identity("private userland", "private_user")


def test_abstention_correctness_requires_deterministic_ineligibility(tmp_path: Path) -> None:
    """An eligible duplicate outside the top three must not count as an abstention."""

    labels_path = tmp_path / "labels.json"
    labels_path.write_text(
        json.dumps(
            {
                "relevant_pack_ids": [],
                "should_abstain_pack_ids": [
                    "history-weak-001",
                    "history-chaos-duplicate",
                ],
            }
        ),
        encoding="utf-8",
    )

    report = evaluate(
        "deterministic",
        DATA_DIR / "historical_memory_packs.json",
        labels_path,
    )

    assert report["abstention_correctness"] == 0.5
