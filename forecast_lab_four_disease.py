"""
AI-powered four-disease (Cholera, Malaria, Typhoid, Marburg) planning brief for Forecast Lab.
Produces structured JSON for visualization; requires configured AI API (OpenAI-compatible).

Reuses :func:`ai_config.openai_compatible_env_credentials` so xAI / OpenAI routing stays consistent app-wide.
"""
from __future__ import annotations

import json
from typing import Any

import pandas as pd
import plotly.graph_objects as go
from ai_config import chat_text_from_prompts, openai_compatible_env_credentials

FOUR_DISEASES = ("Cholera", "Malaria", "Typhoid", "Marburg")
FACTOR_KEYS = (
    "environmental",
    "climatic",
    "behavioral",
    "sanitation",
    "vector",
    "water",
    "mobility",
    "border",
    "health_system",
)
DEFAULT_FACTOR_IMPUTE = 20
_V1_CHAT_TIMEOUT_SEC = 120.0
_RADAR_COLORS = ("#3b82f6", "#22c55e", "#f59e0b", "#f43f5e")


def _clip_0_100(value: object) -> int:
    try:
        return int(min(100, max(0, int(float(value)))))
    except (TypeError, ValueError):
        return 0


def _chat_completions(
    base_url: str, api_key: str, model: str, system: str, user: str
) -> tuple[bool, str | None, str | None]:
    """Call provider chat (OpenAI-compatible or native Gemini)."""
    text, err = chat_text_from_prompts(
        system,
        user,
        temperature=0.2,
        timeout_sec=_V1_CHAT_TIMEOUT_SEC,
        model=model,
    )
    if not text:
        return False, None, err or "Empty assistant message in API response."
    return True, str(text), None


def _strip_code_fence(text: str) -> str:
    t = (text or "").strip()
    if t.startswith("```"):
        parts = t.split("```", 2)
        if len(parts) >= 2:
            t = parts[1]
        if t.lower().startswith("json"):
            t = t[4:]
    return t.strip()


def _compact_realtime_context(realtime_data: dict) -> str:
    """Small JSON string for the model; avoids huge payloads."""
    dash = (realtime_data or {}).get("dashboard") or {}
    return json.dumps(
        {
            "last_updated": (realtime_data or {}).get("last_updated"),
            "news_mentions_24h": (realtime_data or {}).get("news_mentions", 0),
            "open_web_total": dash.get("open_web_total", 0),
            "official_total": dash.get("official_total", 0),
            "signal_score_0_100": dash.get("signal_score", 0),
            "signal_risk_label": dash.get("risk_level"),
            "posture": dash.get("posture"),
            "social_urgency_0_100": (realtime_data or {}).get("social_urgency_score", 0),
            "feeds_online": f"{dash.get('feeds_online', 0)}/{dash.get('feeds_total', 10)}",
            "validated_signals_24h": (realtime_data or {}).get("validated_signals_24h", 0),
        },
        ensure_ascii=False,
    )


def _system_prompt_json_schema() -> str:
    return """You are a senior public-health epidemiologist supporting Uganda MoH and EAC border coordination.
You MUST return ONLY valid JSON (no markdown fences). The JSON must follow this exact schema keys:

{
  "executive_summary": "string, 3-5 sentences, Uganda + planning focus",
  "disease_narrative": { "Cholera": "...", "Malaria": "...", "Typhoid": "...", "Marburg": "..." },
  "factor_matrix": {
     "Cholera":   { "environmental": 0-100, "climatic": 0-100, ... 9 keys ... },
     "Malaria":   { same 9 keys },
     "Typhoid":   { same 9 keys },
     "Marburg":   { same 9 keys }
  },
  "comparative_burden_0_100": { "Cholera": int, "Malaria": int, "Typhoid": int, "Marburg": int },
  "forecast_6m_relative_0_100": { "Cholera": int, "Malaria": int, "Typhoid": int, "Marburg": int },
  "uganda_units": [
     {
        "level": "region|district|subcounty",
        "name": "string",
        "parent": "string or null",
        "diseases_priority": [ "0-2 disease names from the four" ],
        "risk_tier": "High|Medium|Low",
        "current_conditions": "1-2 sentences (water, camps, border, season, as relevant)",
        "interventions": [ "2-3 concrete actions" ]
     }
  ],
  "eac_regional_patterns": "string, 3-5 sentences: Kenya/Tanzania/Rwanda/SSudan/Congo links, trade routes, cross-border health",
  "recommendations": [
     { "target": "national or named district/region", "disease": "one of the four or All", "priority": "P1|P2|P3", "action": "decision text", "evidence": "1 sentence" }
  ],
  "data_limitations": "string, what would improve with DHIS2 line lists",
  "evidence_caveat": "string, AI synthesis not substitute for official surveillance"
}

The nine factor keys in factor_matrix must be exactly: environmental, climatic, behavioral, sanitation, vector, water, mobility, border, health_system.
Integer scores 0-100 are RELATIVE model estimates for policy discussion, not confirmed case counts.
Include at least 6 uganda_units entries covering multiple regions (e.g. Karamoja, border Kasese, Kampala/Wakiso, Busoga/water, refugee-hosting, cattle corridor) and at least 2 with subcounty or district precision.
""".replace(
        "\n", " "
    ).strip()


def _user_prompt_with_context(ctx_json: str) -> str:
    return f"""Build the JSON as specified. Context snapshot from the live Pathogen Economy Epiforecast dashboard (may be partial):
{ctx_json}

Use Uganda geography: 4 main regions and common districts; mention counties/subcounties only where it strengthens targeting.
Tie Cholera to WASH, floods, water; Malaria to vector season and rain; Typhoid to STH/water/food; Marburg to animal exposure and filovirus history in Uganda/region.
Quantitative scores in factor_matrix and burden fields are model-style indices for cross-disease comparison, 0-100, not case counts.
"""


def _ensure_factor_matrix(brief: dict) -> None:
    """Mutate brief in place: each of the four diseases has all 9 factor keys (0-100)."""
    fm = brief.get("factor_matrix")
    if not isinstance(fm, dict):
        brief["factor_matrix"] = {
            d: {k: DEFAULT_FACTOR_IMPUTE for k in FACTOR_KEYS} for d in FOUR_DISEASES
        }
        return
    for d in FOUR_DISEASES:
        if d not in fm or not isinstance(fm[d], dict):
            fm[d] = {k: DEFAULT_FACTOR_IMPUTE for k in FACTOR_KEYS}
            continue
        for k in FACTOR_KEYS:
            if k not in fm[d]:
                fm[d][k] = DEFAULT_FACTOR_IMPUTE
            else:
                fm[d][k] = _clip_0_100(fm[d][k])
    brief["factor_matrix"] = fm


_SYSTEM = _system_prompt_json_schema()


def generate_four_disease_brief_json(realtime_data: dict) -> dict[str, Any]:
    """
    Call the chat model; return { "ok": bool, "brief"?: dict, "error"?: str, "raw_excerpt"?: str }.
    """
    api_key, base_url, model = openai_compatible_env_credentials()
    if not api_key:
        return {
            "ok": False,
            "error": "No AI API key (set OPENAI_API_KEY, AI_API_KEY, CURSOR_API_KEY, or XAI_API_KEY) and base URL for your provider.",
        }

    user = _user_prompt_with_context(_compact_realtime_context(realtime_data or {}))
    ok, text, err = _chat_completions(base_url, api_key, model, _SYSTEM, user)
    if not ok or text is None:
        return {"ok": False, "error": err or "Request failed", "raw_excerpt": ""}

    raw_excerpt = text[:2000]
    try:
        data = json.loads(_strip_code_fence(text))
    except json.JSONDecodeError as exc:
        return {
            "ok": False,
            "error": f"Model did not return valid JSON: {exc}",
            "raw_excerpt": raw_excerpt,
        }

    if not isinstance(data, dict):
        return {"ok": False, "error": "Top-level JSON must be an object", "raw_excerpt": raw_excerpt}

    _ensure_factor_matrix(data)
    return {"ok": True, "brief": data, "raw_excerpt": raw_excerpt}


def brief_to_heatmap_df(brief: dict) -> Any:
    fm = (brief or {}).get("factor_matrix") or {}
    rows = []
    for d in FOUR_DISEASES:
        row = fm.get(d) or {}
        rows.append({cat: _clip_0_100(row.get(cat, 0)) for cat in FACTOR_KEYS})
    return pd.DataFrame(rows, index=list(FOUR_DISEASES), columns=list(FACTOR_KEYS))


def brief_to_burden_df(brief: dict) -> Any:
    b = (brief or {}).get("comparative_burden_0_100") or {}
    f6 = (brief or {}).get("forecast_6m_relative_0_100") or {}
    out = []
    for d in FOUR_DISEASES:
        out.append(
            {
                "Disease": d,
                "Comparative burden (0-100)": _clip_0_100(b.get(d, 0)),
                "6m forecast index (0-100)": _clip_0_100(f6.get(d, 0)),
            }
        )
    return pd.DataFrame(out)


def brief_to_radar_figure(brief: dict) -> Any:
    fm = (brief or {}).get("factor_matrix") or {}
    fig = go.Figure()
    for d, col in zip(FOUR_DISEASES, _RADAR_COLORS):
        row = fm.get(d) or {}
        vals = [float(_clip_0_100(row.get(k, 0))) for k in FACTOR_KEYS]
        closed = vals + vals[:1]
        theta = [k.replace("_", " ") for k in FACTOR_KEYS] + [FACTOR_KEYS[0].replace("_", " ")]
        fig.add_trace(
            go.Scatterpolar(
                r=closed,
                theta=theta,
                fill="toself",
                name=d,
                line=dict(color=col),
                fillcolor=col,
                opacity=0.32,
            )
        )
    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
        title="Causal / driver profile (0–100) — cross-disease comparison (planning model)",
        template="plotly_dark",
        showlegend=True,
    )
    return fig


def uganda_units_to_rows(brief: dict) -> list[dict]:
    uu = (brief or {}).get("uganda_units") or []
    rows: list[dict] = []
    for u in uu:
        if not isinstance(u, dict):
            continue
        dp = u.get("diseases_priority")
        if isinstance(dp, list):
            dps = ", ".join(str(x) for x in dp)
        else:
            dps = str(dp or "")
        acts = u.get("interventions") or []
        act_s = " | ".join(str(x) for x in acts) if isinstance(acts, list) else str(acts)
        rows.append(
            {
                "Level": u.get("level", ""),
                "Name": u.get("name", ""),
                "Parent": u.get("parent", ""),
                "Priority diseases": dps,
                "Risk": u.get("risk_tier", ""),
                "Current conditions": (u.get("current_conditions") or "")[:200],
                "Interventions (draft)": act_s[:500],
            }
        )
    return rows


def recommendations_to_rows(brief: dict) -> list[dict]:
    out = []
    for r in (brief or {}).get("recommendations") or []:
        if not isinstance(r, dict):
            continue
        out.append(
            {
                "Target": r.get("target", ""),
                "Disease": r.get("disease", ""),
                "P": r.get("priority", ""),
                "Action": (r.get("action") or "")[:400],
                "Evidence (brief)": (r.get("evidence") or "")[:300],
            }
        )
    return out
