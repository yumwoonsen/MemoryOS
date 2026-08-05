"""Shared identity normalization for consent, redaction, and leak detection."""

from __future__ import annotations

import re


def identity_tokens(value: str) -> tuple[str, ...]:
    """Normalize an identity while treating spaces, hyphens, and underscores alike."""

    return tuple(token.casefold() for token in re.findall(r"[^\W_]+", value, flags=re.UNICODE))


def identity_pattern(value: str) -> str:
    """Return a boundary-safe pattern for the normalized forms of an identity."""

    tokens = identity_tokens(value)
    body = r"[\W_]+".join(re.escape(token) for token in tokens) or re.escape(value)
    return rf"(?<!\w){body}(?!\w)"


def contains_identity(text: str, identity: str) -> bool:
    """Check whether text contains an identity across common separator variants."""

    return bool(re.search(identity_pattern(identity), text, re.IGNORECASE))


def identifier_contains_identity(identifier: str, identity: str) -> bool:
    """Check an opaque identifier without allowing substring-only matches."""

    identifier_parts = identity_tokens(identifier)
    identity_parts = identity_tokens(identity)
    if not identity_parts:
        return False
    identity_length = len(identity_parts)
    return any(
        identifier_parts[index : index + identity_length] == identity_parts
        for index in range(len(identifier_parts) - identity_length + 1)
    )
