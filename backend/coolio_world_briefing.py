"""
**Coolio world briefing** — when local validated history is missing (or ML is disabled),
synthesize a meaningful panel from **open web context** (Wikipedia, WHO RSS, OWID for COVID)
plus optional LLM wording. This is **not** training a model on the internet; it is
**retrieval + synthesis** with citable hooks.
"""
from __future__ import annotations

import os

import pandas as pd

from .ai_config import chat_text_from_prompts, llm_configured, openai_compatible_env_credentials
from .coolio_token_policy import coolio_max_tokens_from_env
from .coolio_world_context import build_world_context_pack
from .coolio_llm import coolio_llm_layer_enabled
from .coolio_memory import append_coolio_observation, recent_memory_for_prompt
from .statistical_forecast import no_ai_mode

COOLIO_VERSION = "1.0.0"


def _has_any_llm() -> bool:
    return not no_ai_mode() and llm_configured()


def run_coolio_world_briefing(
    *,
    disease: str | None,
    horizon_days: int,
    lookback_days: int,
    local_daily: pd.DataFrame,
) -> dict:
    dlabel = disease or "All diseases"
    rows_available = int(len(local_daily)) if local_daily is not None and not local_daily.empty else 0
    local_tip = ""
    if rows_available > 0 and "count" in local_daily.columns:
        try:
            c = int(local_daily["count"].sum())
            local_tip = f"Local validated signal-days in window: {rows_available} calendar day(s), total count sum={c}."
        except Exception:
            local_tip = f"Local validated signal-days in window: {rows_available}."

    pack = build_world_context_pack(disease)
    ctx = pack.get("prompt_block") or ""
    sources = pack.get("sources") or []
    mem_block = recent_memory_for_prompt(disease=dlabel)

    note = (
        f"Coolio v{COOLIO_VERSION} **world mode**: briefing from Wikipedia + WHO RSS keyword match "
        f"(+ OWID for COVID-like names). Not a local time-series model. {local_tip}".strip()
    )

    llm_text = ""
    llm_err = ""
    llm_model = ""
    use_llm = coolio_llm_layer_enabled() and _has_any_llm()
    if use_llm:
        system = (
            "You are **Coolio**, a global disease intelligence assistant.\n"
            "You ONLY cite situational claims that are supported by the CONTEXT block or the "
            "local deployment summary given below. If CONTEXT lacks recent outbreak news, say "
            "you could not confirm a current event from these sources in this fetch — do not invent.\n"
            "Use markdown: short sections, bullets. Include a **Limitations** line (these are snapshots, "
            "not exhaustive global surveillance).\n"
            "Do not give individualized medical advice."
        )
        user = (
            f"Disease focus: **{dlabel}**\n"
            f"Horizon (days) user asked: {int(horizon_days)}\n"
            f"Lookback window (days): {int(lookback_days)}\n"
            f"{local_tip}\n\n"
            f"{mem_block + chr(10) + chr(10) if mem_block else ''}"
            f"CONTEXT (open web, this run):\n{ctx}\n\n"
            "Deliver: (1) **Snapshot** — what these sources say about the disease entity / epidemiology. "
            "(2) **Recent signals** — only if WHO headlines matched; otherwise say none matched keywords. "
            "(3) **For this deployment** — how absence or presence of local validated data matters. "
            "(4) **What to verify next** — concrete checks."
        )
        try:
            to = float(os.getenv("EPFORECAST_COOLIO_WORLD_LLM_TIMEOUT_SEC", "100") or "100")
        except ValueError:
            to = 100.0
        to = min(180.0, max(20.0, to))
        mx = coolio_max_tokens_from_env(
            "EPFORECAST_COOLIO_WORLD_LLM_MAX_TOKENS",
            default=1800,
        )
        if mx is not None:
            mx = max(400, min(8000, mx))

        m_override = (os.getenv("EPFORECAST_COOLIO_LLM_MODEL") or "").strip() or None
        llm_text, llm_err = chat_text_from_prompts(
            system,
            user,
            temperature=0.25,
            timeout_sec=to,
            max_tokens=mx,
            model=m_override,
        )
        _, _, dm = openai_compatible_env_credentials()
        llm_model = (m_override or dm or "").strip()
        llm_text = (llm_text or "").strip()
        llm_err = (llm_err or "").strip()

    if llm_text:
        narrative = llm_text
    elif use_llm and llm_err:
        narrative = (
            f"_(LLM error: {llm_err})_\n\n### Retrieved context (still useful)\n\n{ctx}\n\n"
            "---\n\n_Check API quota, base URL, or model id._"
        ).strip()
    else:
        narrative = (
            f"### Snapshot (open web only)\n\n{ctx}\n\n"
            "---\n\n"
            "_Add an LLM (`AI_API_KEY` / `LOCAL_LLM_URL`, `EPFORECAST_NO_AI=0`, `EPFORECAST_COOLIO_LLM=1`) "
            "for a richer Coolio synthesis over these snippets._"
        ).strip()

    llm_ok = bool(use_llm and llm_text and not llm_err)

    append_coolio_observation(
        disease=dlabel,
        summary=narrative[:1100] if narrative else ctx[:900],
        source_count=len(sources),
    )

    return {
        "ok": True,
        "reason": "",
        "history": local_daily if rows_available else pd.DataFrame(columns=["date", "count"]),
        "forecast": pd.DataFrame(columns=["date", "predicted", "lower", "upper"]),
        "feature_importance": [],
        "backtest": {},
        "disease": dlabel,
        "horizon_days": int(horizon_days),
        "lookback_days": int(lookback_days),
        "min_history_days": 0,
        "rows_available": rows_available,
        "forecast_method": "coolio_world_briefing",
        "forecast_note": note,
        "coolio_world_narrative": narrative,
        "coolio_world_sources": sources,
        "coolio_llm_analysis": llm_text if llm_ok else "",
        "coolio_llm_error": llm_err if use_llm and not llm_ok else "",
        "coolio_llm_model": llm_model if use_llm else "",
    }
