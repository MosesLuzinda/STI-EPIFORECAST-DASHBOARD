"""
Coolio capability matrix — maps product vision to what the stack does today.

**Coolio** (when ``EPFORECAST_SIGNAL_FORECAST_ENGINE=coolio``) owns numeric
forecasting: ensemble ML on validated signals, OWID merge for COVID-like diseases,
live OWID context on the dashboard, lag/rolling **pattern** features.

**OpenAI-compatible chain** (OpenAI, xAI / Grok, Gemini, Groq failover, local
LLM) still powers **language-heavy** flows when keys exist: batched signal
validation, Forecast Lab JSON briefs, NLP-style alerts — presented in the UI as
Coolio’s optional **language & validation assist**, not a second forecast brain.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CapabilityItem:
    title: str
    vision: str
    today_coolio: str


@dataclass(frozen=True)
class CapabilityPillar:
    name: str
    icon: str
    items: tuple[CapabilityItem, ...]


CAPABILITY_PILLARS: tuple[CapabilityPillar, ...] = (
    CapabilityPillar(
        name="Advanced predictive modeling",
        icon="🧠",
        items=(
            CapabilityItem(
                "Hyper-local forecasting",
                "Outbreak risk at neighborhood scale, not only city or national aggregates.",
                "Coolio trains on whatever daily series you store in `signals.db` (disease-filtered). "
                "Subnational or facility rows appear in forecasts once ingested and aggregated by day.",
            ),
            CapabilityItem(
                '"What-if" simulations',
                'Model interventions — e.g. "close schools for two weeks."',
                "Scenario-style narratives in the app remain heuristic; numeric what-if SEIR-style "
                "shortcuts live in legacy API paths. Coolio focuses on data-driven short-horizon "
                "trajectories from observed signals.",
            ),
            CapabilityItem(
                "Long-term projection & seasonality",
                "Multi-month trends with weather/season cues via deep models.",
                "Coolio uses an RF + histogram gradient boosting ensemble with lags and rolling "
                "windows (not deep learning). Seasonality shows up indirectly via features and "
                "OWID context for COVID-like runs.",
            ),
        ),
    ),
    CapabilityPillar(
        name="Early warning & signal detection",
        icon="🕵️",
        items=(
            CapabilityItem(
                "Anomaly detection",
                "Catch small unusual spikes before lab confirmation.",
                "Structured anomaly cues: rolling means, lags, ensemble residual vs recent level, "
                "plus cross-feed dashboard drivers. Raw search/pharmacy feeds are not wired as "
                "first-class sources yet.",
            ),
            CapabilityItem(
                "Sentiment & misinformation proxy",
                "Gauge fear or rumor spread from social and news.",
                "Open-web volume, keyword signals, optional LLM validation of items when API keys "
                "are set (`signal_validator` + provider chain).",
            ),
            CapabilityItem(
                "Clustering & emerging patterns",
                "Group cases to hint at strain or variant shifts from symptom patterns.",
                "Automatic grouping is by validated disease labels and 24h counts in the dashboard; "
                "clinical symptom clustering is not implemented in-engine.",
            ),
        ),
    ),
    CapabilityPillar(
        name="Automated data management",
        icon="🧹",
        items=(
            CapabilityItem(
                "Data cleaning",
                "Fix missing/duplicate hospital rows automatically.",
                "Pandas-based merges, dedupe on ingest paths, and validator gating — not a full "
                "ETL autobiography model.",
            ),
            CapabilityItem(
                "NLP extraction",
                "Read unstructured notes or email for hidden case mentions.",
                "LLM-assisted validation and NLP alert endpoints when configured; handwritten OCR "
                "is out of scope here.",
            ),
            CapabilityItem(
                "Normalization & reporting delays",
                "Adjust for weekend reporting dips and backfill delays.",
                "Daily aggregation and calendar features (e.g. day-of-week in Coolio features); "
                "explicit delay models are future work.",
            ),
        ),
    ),
    CapabilityPillar(
        name="Optimized resource planning",
        icon="🎯",
        items=(
            CapabilityItem(
                "Inventory & surge logistics",
                "ICU beds, ventilators, supplies by site and date.",
                "Recommendations in ROI / action-plan pages are driven by dashboard KPIs and "
                "rules — Coolio forecasts inform trajectory, not hospital inventory optimizers.",
            ),
            CapabilityItem(
                "Vaccine / outreach prioritization",
                "Target high-transmission pockets to slow spread fastest.",
                "Not a dedicated solver; use forecast + geography layers as decision support.",
            ),
        ),
    ),
    CapabilityPillar(
        name="Smart interaction",
        icon="⚡",
        items=(
            CapabilityItem(
                "Automated reporting",
                "Written summaries for officials who skip raw charts.",
                "Executive brief and Forecast Lab outputs use metrics + optional LLM text "
                "(OpenAI-compatible) when `EPFORECAST_NO_AI` is off and keys exist.",
            ),
            CapabilityItem(
                "Real-time alerts",
                "Push to clinics when a surge is detected.",
                "Email/admin routing and in-app warnings; push to mobile apps depends on deployment.",
            ),
        ),
    ),
)


def llm_assist_roles_markdown() -> str:
    """Former 'OpenAI primary + Groq failover' logic, reframed under Coolio."""
    return (
        "### Language & validation assist (OpenAI-compatible)\n\n"
        "The same **primary -> failover** chain as before:\n\n"
        "- **Primary** (`AI_API_KEY` / OpenAI / Gemini / xAI Grok, or local `LOCAL_LLM_URL`): "
        "batched **signal validation**, **Forecast Lab** structured briefs, **NLP alerts** wording.\n"
        "- **Failover** (`AI_FAILOVER_API_KEY` / `GROQ_*`): identical routes when the primary "
        "is down or rate-limited.\n\n"
        "**Coolio** does not replace those calls; it **adds** the supervised forecasting and "
        "OWID layer so numbers and charts are driven by one on-box engine while language tasks "
        "stay on whichever provider you configure."
    )


def format_capabilities_markdown(*, coolio_engine_active: bool) -> str:
    lines: list[str] = []
    coolio_ver = "1.0.0"
    try:
        from .coolio_engine import COOLIO_VERSION

        coolio_ver = COOLIO_VERSION
    except Exception:
        pass
    if coolio_engine_active:
        lines.append(
            f"**Coolio v{coolio_ver}** is the **predictive & pattern core**: ensemble forecast, "
            "signal history features, and optional OWID fusion + live dashboard context."
        )
    else:
        lines.append(
            "Forecasting uses the **legacy signal Random Forest** path unless you set "
            "`EPFORECAST_SIGNAL_FORECAST_ENGINE=coolio`."
        )
    lines.append("")
    lines.append(llm_assist_roles_markdown())
    lines.append("")
    lines.append("### Capability map (vision -> today)")
    lines.append("")
    for pillar in CAPABILITY_PILLARS:
        lines.append(f"#### {pillar.icon} {pillar.name}")
        for it in pillar.items:
            lines.append(f"**{it.title}** — *Goal:* {it.vision}")
            lines.append(f"- **Stack today:** {it.today_coolio}")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"
