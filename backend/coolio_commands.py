"""
Natural-language **commands** for Coolio inside the Streamlit app.

Only **allow-listed** actions (navigate, set watched disease, refresh feeds) are executed.
No arbitrary code execution.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .coolio_commands_llm import resolve_coolio_command_llm


@dataclass
class CoolioCommandResult:
    """What to apply on the client after the user submits a Coolio line."""

    message: str
    navigate_to: str | None = None
    set_policy_disease: str | None = None
    refresh_outbreak: bool = False


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip()).strip()


def _build_nav_triggers(nav_modules: list[str], nav_labels: dict[str, str]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for page in nav_modules:
        page_l = page.casefold()
        out.append((page_l, page))
        lbl = nav_labels.get(page) or ""
        if lbl:
            out.append((lbl.casefold(), page))
    extra = [
        ("home page", "Home"),
        ("main page", "Home"),
        ("landing", "Home"),
        ("start", "Home"),
        ("national dashboard", "Strategic signals"),
        ("strategic signals", "Strategic signals"),
        ("dashboard", "Strategic signals"),
        ("signal dashboard", "Strategic signals"),
        ("track a disease", "Disease Surveillance"),
        ("disease surveillance", "Disease Surveillance"),
        ("surveillance", "Disease Surveillance"),
        ("forecast lab", "Forecast Lab"),
        ("forecasts", "Forecast Lab"),
        ("prediction", "Forecast Lab"),
        ("global", "Global Surveillance"),
        ("global surveillance", "Global Surveillance"),
        ("world map", "Global Surveillance"),
        ("hotspots", "Uganda Hotspots"),
        ("maps", "Uganda Hotspots"),
        ("uganda", "Uganda Hotspots"),
        ("action plan", "Action Plan"),
        ("checklist", "Action Plan"),
        ("executive", "Executive Briefing"),
        ("executive briefing", "Executive Briefing"),
        ("briefing", "Executive Briefing"),
        ("summary", "Executive Briefing"),
        ("admin", "Admin"),
        ("settings", "Admin"),
        ("reports", "Reports library"),
        ("files", "Reports library"),
        ("developers", "Developers"),
        ("api", "Developers"),
        ("pathogen workspace", "Pathogen workspace"),
        ("planner", "Pathogen workspace"),
        ("profiler", "Disease Profiler"),
        ("disease profile", "Disease Profiler"),
        ("roi", "ROI & Financing"),
        ("financing", "ROI & Financing"),
        ("vdtec", "VDTEC & Pathogen ROI"),
        ("clinical trials", "Clinical trial sites"),
        ("think tank", "EPI-ThinkTank"),
        ("epi think", "EPI-ThinkTank"),
    ]
    for phrase, page in extra:
        if page in nav_modules:
            out.append((phrase, page))
    return out


def resolve_coolio_command(
    text: str,
    *,
    nav_modules: list[str],
    nav_labels: dict[str, str],
) -> CoolioCommandResult:
    raw = _norm(text)
    if not raw:
        return CoolioCommandResult("Type a short command, e.g. “take me home” or “open forecasts”.")

    llm_res = resolve_coolio_command_llm(
        raw,
        nav_modules=nav_modules,
        nav_labels=nav_labels,
    )
    if llm_res is not None:
        return llm_res

    lowered = raw.casefold()

    if any(
        x in lowered
        for x in (
            "refresh data",
            "reload data",
            "update feeds",
            "refresh feeds",
            "pull latest",
            "sync data",
        )
    ):
        return CoolioCommandResult("Refreshing live outbreak and trend caches…", refresh_outbreak=True)

    if any(x in lowered for x in ("help", "what can you do", "commands")):
        return CoolioCommandResult(
            "Try: **home** · **national dashboard** · **forecasts** · **track disease** · "
            "**global** · **maps** · **executive briefing** · **refresh data** · "
            "**set disease cholera** (or any disease name)."
        )

    triggers = _build_nav_triggers(nav_modules, nav_labels)
    triggers.sort(key=lambda x: -len(x[0]))
    for phrase, page in triggers:
        if phrase and phrase in lowered:
            label = nav_labels.get(page, page)
            return CoolioCommandResult(f"Opening **{label}**…", navigate_to=page)

    m = re.search(r"(?:take me to|go to|open|navigate to)\s+(.+)$", raw, flags=re.I)
    if m:
        tail = _norm(m.group(1)).casefold()
        for phrase, page in triggers:
            if phrase and (phrase in tail or tail in phrase):
                label = nav_labels.get(page, page)
                return CoolioCommandResult(f"Opening **{label}**…", navigate_to=page)

    for pat in (
        r"(?:set|change)\s+(?:the\s+)?disease\s+to\s+(.+)",
        r"(?:set|change)\s+disease\s*:\s*(.+)",
        r"^watch\s+(.+)",
        r"^track\s+(.+)",
        r"^focus\s+(?:on\s+)?(.+)",
    ):
        m = re.search(pat, raw, flags=re.I)
        if m:
            disease_guess = _norm(m.group(1))
            disease_guess = re.sub(r"^(on|for)\s+", "", disease_guess, flags=re.I).strip()
            if len(disease_guess) >= 2:
                return CoolioCommandResult(
                    f"Watching **{disease_guess}** as the active disease.",
                    set_policy_disease=disease_guess,
                )

    return CoolioCommandResult(
        "I did not recognize that as a built-in screen command. "
        "Try **home**, **forecasts**, **national dashboard**, **set disease …**, or **refresh data**."
    )
