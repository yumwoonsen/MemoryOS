"""Shared conservative screening for secrets and unsafe player-facing text."""

from __future__ import annotations

import re

SECRET_LIKE_PATTERN = re.compile(
    r"(?i)\b(?:"
    r"sk-[a-z0-9_-]{8,}|"
    r"gsk_[a-z0-9_-]{8,}|"
    r"ghp_[a-z0-9]{20,}|"
    r"github_pat_[a-z0-9_]{20,}|"
    r"glpat-[a-z0-9_-]{12,}|"
    r"xox[baprs]-[a-z0-9-]{10,}|"
    r"AKIA[0-9A-Z]{16}|"
    r"bearer\s+[a-z0-9._-]{8,}|"
    r"api[_ -]?key\s*[:=]?\s*[a-z0-9._-]{8,}"
    r")\b"
)

UNSAFE_PLAYER_CONTENT_PATTERN = re.compile(
    r"(?i)\b(?:"
    r"doxx(?:ed|ing)?|"
    r"home address|phone number|credit card|bank account|"
    r"password|credentials?|one[- ]time code|otp|"
    r"threaten(?:ed|ing)?|harass(?:ed|ing|ment)?|"
    r"real[- ]world harm|"
    r"system prompt|chain[- ]of[- ]thought|hidden instructions|"
    r"ignore (?:all |any |the )?(?:previous|system|developer) instructions?"
    r")\b|https?://"
)


def contains_secret_like(text: str) -> bool:
    return bool(SECRET_LIKE_PATTERN.search(text))


def contains_unsafe_player_content(text: str) -> bool:
    return bool(UNSAFE_PLAYER_CONTENT_PATTERN.search(text))
