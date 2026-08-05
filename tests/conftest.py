"""Global test safety configuration."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def force_deterministic_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """Never allow a developer's local .env file to spend API credits in tests."""

    monkeypatch.setenv("MEMORYOS_PROVIDER", "deterministic")
