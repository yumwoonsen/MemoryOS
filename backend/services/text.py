"""Small text helpers shared by deterministic generation stages."""

from __future__ import annotations


def truncate_text(value: str, max_length: int) -> str:
    """Fit generated text inside an output contract and mark truncation visibly."""

    if max_length < 1:
        raise ValueError("max_length must be positive")
    if len(value) <= max_length:
        return value
    if max_length <= 3:
        return value[:max_length]
    return f"{value[: max_length - 3].rstrip()}..."
