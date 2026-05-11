"""
LLM-based Coolio **intent** for sidebar commands.

The model (your internet-connected provider: OpenAI, xAI, Gemini, local, etc.)
interprets free-form language; we **only execute** validated actions: navigate,
set watched disease, refresh caches, or show help — still no arbitrary code.
"""
from __future__ import annotations

import os
from difflib import get_close_matches
from typing import TYPE_CHECKING

from .ai_config import chat_text_from_prompts, llm_configured
from .coolio_token_policy import coolio_max_tokens_from_env
from .json_extract import parse_json_loose
from .statistical_forecast import no_ai_mode

if TYPE_CHECKING:
    from .coolio_commands import CoolioCommandResult

_ALLOWED_ACTIONS = frozenset({"navigate", "set_disease", "refresh_data", "help", "unclear"})


def coolio_command_llm_enabled() -> bool:
    if no_ai_mode():
        return False
    v = (os.getenv("EPFORECAST_COOLIO_COMMANDS_LLM") or "1").strip().lower()
    return v not in ("0", "false", "no", "off")


def _has_llm_credentials() -> bool:
    return llm_configured()


def _catalog_block(nav_modules: list[str], nav_labels: dict[str, str]) -> str:
    lines: list[str] = []
    for p in nav_modules:
        lbl = nav_labels.get(p) or p
        lines.append(f'  "{p}": user may say «{lbl}» or similar')
    return "CATALOG (internal page id → user label):\n" + "\n".join(lines)


def _extract_json_object(text: str) -> dict | None:
    obj = parse_json_loose(text)
    return obj if isinstance(obj, dict) else None


def _coerce_page(page_raw: str, nav_modules: list[str], nav_labels: dict[str, str]) -> str | None:
    p = (page_raw or "").strip()
    if not p:
        return None
    if p in nav_modules:
        return p
    pl = p.casefold()
    for nm in nav_modules:
        if nm.casefold() == pl:
            return nm
    for nm, lbl in nav_labels.items():
        if (lbl or "").strip().casefold() == pl:
            return nm
    pool: list[str] = []
    idx: list[str] = []
    for nm in nav_modules:
        pool.append(nm)
        idx.append(nm)
        lbl = (nav_labels.get(nm) or "").strip()
        if lbl:
            pool.append(lbl)
            idx.append(nm)
    hits = get_close_matches(p, pool, n=1, cutoff=0.42)
    if not hits:
        return None
    h = hits[0]
    for i, candidate in enumerate(pool):
        if candidate == h:
            return idx[i]
    return None


def resolve_coolio_command_llm(
    user_text: str,
    *,
    nav_modules: list[str],
    nav_labels: dict[str, str],
) -> "CoolioCommandResult | None":
    """Return None to fall back to rule-based resolver."""
    from .coolio_commands import CoolioCommandResult

    if not coolio_command_llm_enabled() or not _has_llm_credentials():
        return None
    ut = (user_text or "").strip()
    if len(ut) < 2:
        return None

    system = (
        "You are Coolio's **command router** for a Streamlit epidemic intelligence app.\n"
        "The user speaks naturally. You infer what they want and answer with **only one JSON object**, "
        "no markdown, no code fences, no text before or after.\n"
        "Schema:\n"
        '  "action": "navigate" | "set_disease" | "refresh_data" | "help" | "unclear"\n'
        '  "page": string — MUST be an exact **internal page id** from CATALOG, or "" if not navigating\n'
        '  "disease": string — disease name to watch, or ""\n'
        '  "message": string — one short friendly sentence shown in the UI\n'
        "Rules:\n"
        "- For navigation, set action navigate and **page** to the best matching CATALOG id.\n"
        "- For monitoring a pathogen, set_disease and put the disease name in disease (normalize spelling).\n"
        "- For reload/update/live data, refresh_data.\n"
        "- For how-to / what can you do, help.\n"
        "- If you cannot map safely, unclear and explain in message.\n"
        "- Never invent page ids outside CATALOG.\n"
    )
    user = f"{_catalog_block(nav_modules, nav_labels)}\n\nUSER SAID:\n{ut}\n"

    mx = coolio_max_tokens_from_env(
        "EPFORECAST_COOLIO_COMMAND_LLM_MAX_TOKENS",
        default=None,
    )
    try:
        to = float(os.getenv("EPFORECAST_COOLIO_COMMAND_LLM_TIMEOUT_SEC", "45") or "45")
    except ValueError:
        to = 45.0
    to = min(120.0, max(8.0, to))
    model_ov = (os.getenv("EPFORECAST_COOLIO_COMMAND_LLM_MODEL") or "").strip() or None
    raw, err = chat_text_from_prompts(
        system,
        user,
        temperature=0.1,
        timeout_sec=to,
        max_tokens=mx,
        model=model_ov,
    )
    if err or not raw:
        return None
    data = _extract_json_object(raw)
    if not isinstance(data, dict):
        return None
    action = str(data.get("action") or "unclear").strip().lower()
    if action not in _ALLOWED_ACTIONS:
        action = "unclear"
    msg = str(data.get("message") or "").strip() or "Done."

    if action == "help":
        return CoolioCommandResult(
            msg
            + "\n\nYou can ask in your own words to **open a page**, **watch a disease**, or **refresh data**."
        )
    if action == "refresh_data":
        return CoolioCommandResult(msg, refresh_outbreak=True)
    if action == "set_disease":
        dis = str(data.get("disease") or "").strip()
        if len(dis) < 2:
            return CoolioCommandResult(msg)
        return CoolioCommandResult(msg, set_policy_disease=dis)
    if action == "navigate":
        page = _coerce_page(str(data.get("page") or ""), nav_modules, nav_labels)
        if not page:
            return CoolioCommandResult(
                msg if "unclear" not in msg.lower() else "I could not map that to a screen id — try naming the page."
            )
        return CoolioCommandResult(msg, navigate_to=page)
    return CoolioCommandResult(msg)
