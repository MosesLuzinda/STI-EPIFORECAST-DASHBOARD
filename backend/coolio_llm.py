"""
LLM reasoning layer for **Coolio**: flagship-style synthesis over the numeric ensemble.

The sklearn ensemble in ``coolio_engine`` remains the source of truth for ``predicted``
and bands. When enabled, this module adds ``coolio_llm_analysis`` — interpretation,
caveats, and monitoring ideas — using your configured OpenAI-compatible provider
(or Gemini native path via ``ai_config``).

Set ``AI_MODEL`` to your strongest model, or override only for Coolio with
``EPFORECAST_COOLIO_LLM_MODEL``. Disable with ``EPFORECAST_COOLIO_LLM=0`` or
``EPFORECAST_NO_AI=1``.
"""
from __future__ import annotations

import os
from typing import Any

import pandas as pd

from .ai_config import chat_text_from_prompts, openai_compatible_env_credentials
from .coolio_token_policy import coolio_max_tokens_from_env
from .statistical_forecast import no_ai_mode

COOLIO_LLM_SYSTEM = """You are **Coolio**, the senior epidemic intelligence reasoning layer for Pathogen Economy Epiforecast.
Think with the depth and care of a flagship frontier model briefing a national operations center: precise, structured, honest about uncertainty.

**Non‑negotiable rules:**
- A **supervised ML ensemble** (not you) already produced every numeric point and interval in the forecast. Those quantities are **authoritative for this run** — do not substitute or contradict them with your own numbers or dates.
- Your job is **interpretation**: patterns, caveats, surveillance posture, early-warning checks, and what humans might overlook reading only charts.
- Use short titled sections and bullet lists. No individualized medical advice.
- If history is thin or backtest metrics are weak, state that clearly."""


def coolio_llm_layer_enabled() -> bool:
    if no_ai_mode():
        return False
    v = (os.getenv("EPFORECAST_COOLIO_LLM") or "1").strip().lower()
    return v not in ("0", "false", "no", "off")


def coolio_llm_model_override() -> str | None:
    m = (os.getenv("EPFORECAST_COOLIO_LLM_MODEL") or "").strip()
    return m or None


def _digest_history(hist: Any) -> str:
    try:
        if hist is None or (isinstance(hist, pd.DataFrame) and hist.empty):
            return "(empty)"
        df = hist.copy()
        if "date" not in df.columns or "count" not in df.columns:
            return "(unavailable)"
        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        lines: list[str] = []
        for _, r in df.tail(14).iterrows():
            lines.append(f"- {r['date']}: {int(r['count'])}")
        return "\n".join(lines) if lines else "(empty)"
    except Exception:
        return "(unavailable)"


def _digest_forecast(fc: Any) -> str:
    try:
        if fc is None or (isinstance(fc, pd.DataFrame) and fc.empty):
            return "(empty)"
        df = fc.copy()
        pred = df["predicted"].astype(float)
        return (
            f"horizon_days={len(df)}, sum_predicted={pred.sum():.1f}, mean={pred.mean():.2f}, "
            f"max={pred.max():.2f}, first_day={pred.iloc[0]:.2f}, last_day={pred.iloc[-1]:.2f}"
        )
    except Exception:
        return "(unavailable)"


def enrich_coolio_forecast_with_llm(result: dict) -> dict:
    """
    Mutates ``result`` in place and returns it. Adds ``coolio_llm_analysis``,
    ``coolio_llm_error``, ``coolio_llm_model`` when the layer is enabled and
    ``ok`` is True.
    """
    result.setdefault("coolio_llm_analysis", "")
    result.setdefault("coolio_llm_error", "")
    result.setdefault("coolio_llm_model", "")

    if not result.get("ok") or not coolio_llm_layer_enabled():
        return result

    api_key, _, _ = openai_compatible_env_credentials()
    if not (api_key or "").strip():
        return result

    disease = str(result.get("disease") or "All")
    method = str(result.get("forecast_method") or "")
    note = str(result.get("forecast_note") or "")
    backtest = result.get("backtest") or {}
    top_feat = result.get("feature_importance") or []
    top3 = top_feat[:5] if isinstance(top_feat, list) else []

    user = f"""## Context
- Disease scope: {disease}
- Forecast method line: {method}
- Ensemble note: {note}

## Recent validated daily counts (up to last 14 rows)
{_digest_history(result.get("history"))}

## Forecast summary (ensemble output — use these totals conceptually, do not recompute)
{_digest_forecast(result.get("forecast"))}

## Backtest (hold-out, if any)
{backtest}

## Top features by importance (ensemble drivers)
{top3}

## Requested output
Structure your reply roughly as:
1. **Trajectory read** — what the ensemble path implies for the next surveillance window.
2. **Uncertainty & limits** — data, weekend effects, external drivers not in the model.
3. **Pattern spotter** — what might be easy to miss from tables alone.
4. **Watch list** — 3–6 concrete monitoring or verification actions."""

    try:
        to_sec = float(os.getenv("EPFORECAST_COOLIO_LLM_TIMEOUT_SEC", "90") or "90")
    except ValueError:
        to_sec = 90.0
    to_sec = min(180.0, max(15.0, to_sec))

    max_tok = coolio_max_tokens_from_env(
        "EPFORECAST_COOLIO_LLM_MAX_TOKENS",
        default=1400,
    )
    if max_tok is not None:
        max_tok = max(256, min(8000, max_tok))

    text, err = chat_text_from_prompts(
        COOLIO_LLM_SYSTEM,
        user,
        temperature=0.35,
        timeout_sec=to_sec,
        max_tokens=max_tok,
        model=coolio_llm_model_override(),
    )
    _, _, default_model = openai_compatible_env_credentials()
    result["coolio_llm_model"] = (coolio_llm_model_override() or default_model or "").strip()
    if text:
        result["coolio_llm_analysis"] = text
        result["coolio_llm_error"] = ""
    else:
        result["coolio_llm_analysis"] = ""
        result["coolio_llm_error"] = (err or "LLM returned no text").strip()
    return result
