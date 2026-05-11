"""
Deterministic forecasting and alert text — no LLM, no paid AI APIs.

Enable with EPFORECAST_NO_AI=1 (see .env.example). Optionally skip all live feed
HTTP with EPFORECAST_OFFLINE_SNAPSHOT=1 and use only local signals.db + UI.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

FOUR_DISEASES = ("Cholera", "Malaria", "Typhoid", "Marburg")

PRIORITY_DISEASE_LOWER: frozenset[str] = frozenset(d.lower() for d in FOUR_DISEASES)


def is_priority_disease_name(name: str) -> bool:
    return str(name or "").strip().lower() in PRIORITY_DISEASE_LOWER


# Outbreak-relevance vocabulary. Single source of truth for the cheap pre-filter
# used by ``signal_validator`` and ``data_services._is_outbreak_relevant``.
OUTBREAK_KEYWORDS: tuple[str, ...] = (
    "outbreak", "epidemic", "pandemic", "cholera", "malaria", "ebola",
    "marburg", "dengue", "influenza", "h5n1", "h7n9", "covid", "mpox",
    "measles", "rabies", "yellow fever", "polio", "lassa", "anthrax",
    "typhoid", "rift valley", "zika", "rsv", "tuberculosis", "hiv",
    "diphtheria", "meningitis", "leptospirosis",
)


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


def _truthy(val: str | None) -> bool:
    return (val or "").strip().lower() in ("1", "true", "yes", "on")


def no_ai_mode() -> bool:
    return _truthy(os.getenv("EPFORECAST_NO_AI"))


def offline_snapshot_mode() -> bool:
    return _truthy(os.getenv("EPFORECAST_OFFLINE_SNAPSHOT"))


def nlp_alerts_statistical(
    disease: str,
    news_mentions: int,
    cholera_cases: int,
    affected_countries: int,
    *,
    validated_signals_24h: int = 0,
) -> tuple[list[str], str]:
    """
    Rule-based alert lines from numeric inputs only (same shape as AI NLP alerts).
    """
    d = (disease or "Outbreak").strip() or "Outbreak"
    nm = max(0, int(news_mentions or 0))
    cc = max(0, int(cholera_cases or 0))
    ac = max(0, int(affected_countries or 0))
    vs = max(0, int(validated_signals_24h or 0))

    tier = "baseline"
    if nm >= 2000 or cc >= 25_000 or vs >= 8:
        tier = "high"
    elif nm >= 800 or cc >= 8_000 or vs >= 3 or ac >= 12:
        tier = "elevated"

    lines: list[str] = [
        f"Stat • {d}: media-mention index {nm:,} (24h) — tier **{tier.upper()}** vs dashboard thresholds.",
        f"Stat • Surveillance breadth proxy: {ac} geographies in watch mix; validated store signals (24h): {vs}.",
    ]
    if tier == "high":
        lines.append(
            f"Stat • **{d}** — recommend daily EOC review and verify lab / treatment stock posture within 24h."
        )
    elif tier == "elevated":
        lines.append(
            f"Stat • **{d}** — elevated watch: increase district reporting cadence and cross-check lab surge capacity."
        )
    else:
        lines.append(
            f"Stat • **{d}** — routine monitoring; re-run after fresh snapshot or new `signals.db` ingest."
        )
    lines.append(
        "Stat • Method: deterministic thresholds only (set EPFORECAST_NO_AI=0 to allow LLM-enriched wording)."
    )
    normalized = []
    for line in lines[:4]:
        t = str(line).strip()
        if not t.startswith("NLP Alert") and not t.startswith("Stat •"):
            t = f"Stat • {t}"
        normalized.append(t)
    while len(normalized) < 4:
        normalized.append(f"Stat • Continue monitoring **{d}** against national standard operating thresholds.")
    return normalized[:4], "statistical"


def four_disease_brief_from_metrics(realtime_data: dict | None) -> dict[str, Any]:
    """Structured brief compatible with Forecast Lab charts — no model call."""
    rt = realtime_data or {}
    dash = rt.get("dashboard") or {}
    score = int(dash.get("signal_score") or 0)
    risk = str(dash.get("risk_level") or "Low")
    posture = str(dash.get("posture") or "Routine")
    open_w = int(dash.get("open_web_total") or 0)
    official = int(dash.get("official_total") or 0)
    val24 = int(rt.get("validated_signals_24h") or dash.get("validated_signals_24h") or 0)

    # Map composite intensity into 0–100 indices per disease (static stencil + one global scaler).
    base = max(12, min(88, 28 + score // 2 + min(20, val24 * 2)))
    delta = {"Cholera": 6, "Malaria": 4, "Typhoid": -4, "Marburg": 10}
    burden = {d: max(5, min(95, base + delta[d])) for d in FOUR_DISEASES}
    fwd = {d: max(5, min(95, burden[d] + (3 if risk == "High" else -2 if risk == "Baseline" else 1))) for d in FOUR_DISEASES}

    fm: dict[str, dict[str, int]] = {}
    for d in FOUR_DISEASES:
        row = {k: DEFAULT_FACTOR_IMPUTE for k in FACTOR_KEYS}
        if d == "Cholera":
            row.update({"sanitation": base + 8, "water": base + 10, "environmental": base + 4})
        elif d == "Malaria":
            row.update({"vector": base + 12, "climatic": base + 6, "environmental": base + 3})
        elif d == "Typhoid":
            row.update({"water": base + 6, "sanitation": base + 6, "behavioral": base + 4})
        else:
            row.update({"border": base + 5, "health_system": base + 8, "mobility": base + 4})
        fm[d] = {k: max(0, min(100, int(v))) for k, v in row.items()}

    narratives = {
        "Cholera": f"WASH-sensitive pathogen; rule-based index reflects signal score {score}/100 and open-web volume {open_w:,}.",
        "Malaria": f"Vector/climate-sensitive; indices scale from dashboard posture **{posture}** (no LLM narrative).",
        "Typhoid": f"Food/water hygiene stress; official-feed component {official:,} contributes to composite risk label **{risk}**.",
        "Marburg": f"High-consequence pathogen placeholder; validated signals (24h) in store: {val24}.",
    }

    units = [
        {
            "level": "region",
            "name": "Central / Greater Kampala",
            "parent": None,
            "diseases_priority": ["Typhoid", "Malaria"],
            "risk_tier": "High" if risk == "High" else "Medium",
            "current_conditions": "Dense mobility + water stress — statistical brief only.",
            "interventions": ["Daily situational report", "Lab triage surge check"],
        },
        {
            "level": "region",
            "name": "Border West (DRC adjacency proxy)",
            "parent": None,
            "diseases_priority": ["Marburg", "Malaria"],
            "risk_tier": "Medium",
            "current_conditions": "Cross-border mobility signal weight in composite index.",
            "interventions": ["Border screening drill", "Referral pathway test"],
        },
        {
            "level": "district",
            "name": "Kasese",
            "parent": "Western",
            "diseases_priority": ["Marburg", "Cholera"],
            "risk_tier": "Medium",
            "current_conditions": "Elevated watch when national posture not Routine.",
            "interventions": ["IPC refresh", "Community alert templates"],
        },
        {
            "level": "district",
            "name": "Gulu",
            "parent": "Northern",
            "diseases_priority": ["Malaria"],
            "risk_tier": "Low" if risk == "Baseline" else "Medium",
            "current_conditions": "Seasonal transmission proxy from static stencil.",
            "interventions": ["CHW fever triage", "Bed-net gap map"],
        },
        {
            "level": "subcounty",
            "name": "Lumino (Busoga illustrative)",
            "parent": "Jinja",
            "diseases_priority": ["Cholera"],
            "risk_tier": "Medium",
            "current_conditions": "Water-side communities — WASH indices upweighted.",
            "interventions": ["Water-quality spot checks", "ORS pre-positioning"],
        },
        {
            "level": "district",
            "name": "Moroto (Karamoja proxy)",
            "parent": "Northern",
            "diseases_priority": ["Malaria", "Typhoid"],
            "risk_tier": "Medium",
            "current_conditions": "Humanitarian mobility stress — narrative is heuristic.",
            "interventions": ["Vaccination micro-plan", "Nutrition-IPC joint review"],
        },
    ]

    recs = [
        {
            "target": "National EOC",
            "disease": "All",
            "priority": "P1" if risk == "High" else "P2",
            "action": "Run statistical-only mode review — confirm escalation rules vs ground truth.",
            "evidence": f"Composite score {score}/100, posture {posture}.",
        },
        {
            "target": "District rapid response",
            "disease": "Cholera",
            "priority": "P2",
            "action": "Pre-position ORS/chlorination where WASH indices peak in matrix.",
            "evidence": "Deterministic factor stencil from dashboard snapshot.",
        },
    ]

    return {
        "executive_summary": (
            f"**Statistical mode (no LLM):** national signal index **{score}/100**, risk **{risk}**, "
            f"posture **{posture}**. Open-web **{open_w:,}**, official feeds **{official:,}**, **{val24}** "
            f"validated signals in DB (24h). Charts use rule-based 0–100 indices for cross-disease comparison only."
        ),
        "disease_narrative": narratives,
        "factor_matrix": fm,
        "comparative_burden_0_100": burden,
        "forecast_6m_relative_0_100": fwd,
        "uganda_units": units,
        "eac_regional_patterns": (
            "Statistical placeholder: cross-border trade and displacement patterns are not inferred from AI here — "
            "calibrate with national briefings and partner reports."
        ),
        "recommendations": recs,
        "data_limitations": (
            "No generative narrative; no live NER/geocode. Improve with DHIS2 line lists and curated regional CSVs."
        ),
        "evidence_caveat": (
            f"Heuristic brief generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} — "
            "not a substitute for official surveillance."
        ),
    }


def offline_snapshot_headers() -> dict[str, Any]:
    """Minimal `fetch_realtime_outbreak_data`-shaped dict with no network-derived counts."""
    now_local = datetime.now().strftime("%H:%M:%S EAT")
    snap = datetime.now(timezone.utc).isoformat()
    return {
        "cholera_cases": 0,
        "malaria_ug_cases_est": 0,
        "affected_countries": 0,
        "news_mentions": 0,
        "recent_alerts": [
            "Offline snapshot: live feeds skipped (EPFORECAST_OFFLINE_SNAPSHOT=1). "
            "Use Forecast Lab / signals.db for trend work, or disable offline mode for real pulls."
        ],
        "data_source": "Offline — no HTTP feeds (local database + UI only).",
        "last_updated": now_local,
        "snapshot_utc": snap,
        "gdelt_ok": False,
        "reddit_ok": False,
        "hackernews_ok": False,
        "newsapi_ok": False,
        "who_ok": False,
        "cdc_ok": False,
        "un_ok": False,
        "cidrap_ok": False,
        "reliefweb_ok": False,
        "paho_ok": False,
        "x_ok": False,
        "linkedin_ok": False,
        "meta_ok": False,
        "gdelt_articles_ok": False,
        "x_status": "offline_mode",
        "linkedin_status": "offline_mode",
        "meta_status": "offline_mode",
        "social_sources_note": (
            "Feeds disabled by EPFORECAST_OFFLINE_SNAPSHOT. SQLite signal history and manual CSV uploads (future) "
            "can still drive statistical charts."
        ),
        "source_links": {},
        "news_links": [],
        "social_channels": {},
        "health_site_signals": {},
        "open_web_cases": [],
        "official_cases": [],
        "social_sentiment_index": 0.0,
        "social_urgency_score": 0,
        "sim_recommended_tier": "Routine",
    }
