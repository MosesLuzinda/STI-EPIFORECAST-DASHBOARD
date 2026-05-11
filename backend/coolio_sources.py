"""
Source tiers for Coolio: validator-approved rows in ``signals.db`` already passed
the gate; this module separates **institutional / verified publisher** labels
from **open-web** channels so the dashboard and optional forecast filters can
emphasize official-sourced events.
"""
from __future__ import annotations

# Normalized substrings / labels for feeds the app tags as agency or multilateral.
_OFFICIAL_SUBSTR: tuple[str, ...] = (
    "who news",
    "who africa",
    "afro.who",
    "cdc",
    "un global health",
    "paho",
    "cidrap",
    "reliefweb",
)

_OPEN_WEB_SUBSTR: tuple[str, ...] = (
    "gdelt",
    "reddit",
    "hacker news",
    "newsapi",
)


def source_tier(source: str | None) -> str:
    """
    Return ``"official"`` | ``"open_web"`` | ``"other"``.
    ``"other"`` is still validator-approved but not matched as agency or open-web label.
    """
    s = (source or "").strip().lower()
    if not s:
        return "other"
    if any(x in s for x in _OFFICIAL_SUBSTR):
        return "official"
    if any(x in s for x in _OPEN_WEB_SUBSTR):
        return "open_web"
    return "other"


def is_official_verified_source(source: str | None) -> bool:
    return source_tier(source) == "official"
