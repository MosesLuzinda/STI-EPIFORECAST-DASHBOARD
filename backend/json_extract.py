"""Shared helpers for parsing LLM JSON-ish replies.

Avoids duplicate fence-stripping and tolerant-loading logic in
``signal_validator``, ``forecast_lab_four_disease``, ``coolio_commands_llm``
and inline copies in ``data_services``.
"""
from __future__ import annotations

import json
import re
from typing import Any


def strip_markdown_fence(text: str) -> str:
    """Drop a leading ```json / ``` fence and any trailing fence."""
    t = (text or "").strip()
    if not t:
        return t
    if t.startswith("```"):
        parts = t.split("```", 2)
        if len(parts) >= 2:
            t = parts[1]
        if t.lower().startswith("json"):
            t = t[4:]
    if t.endswith("```"):
        t = t[: -3]
    return t.strip()


def parse_json_loose(text: str) -> Any | None:
    """Best-effort JSON parse: try direct, then strip fences, then regex-extract."""
    raw = (text or "").strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    cleaned = strip_markdown_fence(raw)
    if cleaned and cleaned != raw:
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass
    m = re.search(r"\{[\s\S]*\}\s*", raw)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    m = re.search(r"\[[\s\S]*\]\s*", raw)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return None
