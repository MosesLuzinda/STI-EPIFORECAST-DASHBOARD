import html
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_FRONTEND_DIR = Path(__file__).resolve().parent
for p in (ROOT, _FRONTEND_DIR):
    s = str(p)
    if s not in sys.path:
        sys.path.insert(0, s)

from dotenv import load_dotenv

# Load project root .env first so OPENAI_API_KEY / AI_API_KEY / etc. are set
# before backend modules are imported.
load_dotenv(ROOT / ".env")

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import plotly.express as px


def _merge_streamlit_secrets_into_environ() -> None:
    """Mirror st.secrets (Cloud or .streamlit/secrets.toml) into os.environ; .env wins via setdefault."""
    try:
        # Missing secrets.toml locally raises StreamlitSecretNotFoundError (a FileNotFoundError).
        mapping = dict(st.secrets)
    except FileNotFoundError:
        return
    try:
        for name, val in mapping.items():
            if isinstance(val, dict):
                for k, v in val.items():
                    if v is not None and str(v).strip():
                        os.environ.setdefault(str(k), str(v))
            elif val is not None and str(val).strip():
                os.environ.setdefault(str(name), str(val))
    except (KeyError, TypeError, RuntimeError):
        pass


_merge_streamlit_secrets_into_environ()

from backend.coolio_commands import resolve_coolio_command
from backend.global_disease_catalog import world_surveillance_disease_names
from backend.data_services import (
    OUTBREAK_SNAPSHOT_TTL_SEC,
    fetch_realtime_outbreak_data,
    evaluate_and_send_admin_notifications,
    is_priority_disease,
    list_validated_signal_diseases,
    load_malaria_uganda_real,
)
from app_pages import (
    NO_DISEASE_LABEL,
    render_disease_explorer,
    render_disease_surveillance_hub,
    render_region_watch,
    render_forecast_lab,
    render_alerts_and_recommendations,
    render_admin,
    render_global_view,
    render_executive_brief,
    render_roi_financing,
    render_sidebar_social_action_plan,
    render_signal_sources_panel,
    get_dashboard,
    get_policy_disease,
    regional_hotspot_dataframe,
)
from coolio_ui import (
    coolio_dashboard_strip_html,
    coolio_forecast_hero_html,
    disease_signal_skyline_figure,
)
from pathogen_economy_pages import (
    diseases_for,
    render_pathogen_workspace_home,
    render_vdtec_roi,
    render_clinical_trial_sites,
    render_nms_100_day_surge,
    render_east_africa_regional,
    render_717_impact,
    render_sti_venture_matrix,
    render_epi_thinktank,
    render_developers,
    render_reports_library,
    render_pe_leadership_strip,
)

NAV_MODULES = [
    "Home",
    "Strategic signals",
    "Pathogen workspace",
    "VDTEC & Pathogen ROI",
    "Clinical trial sites",
    "NMS 100-day surge",
    "East Africa regional market",
    "7-1-7 impact estimator",
    "STI venture matrix",
    "ROI & Financing",
    "Executive Briefing",
    "Disease Surveillance",
    "Disease Profiler",
    "Global Surveillance",
    "Forecast Lab",
    "Uganda Hotspots",
    "Action Plan",
    "EPI-ThinkTank",
    "Developers",
    "Reports library",
    "Admin",
]
ROI_NAV_MODULES = [
    "VDTEC & Pathogen ROI",
    "ROI & Financing",
    "STI venture matrix",
    "NMS 100-day surge",
    "East Africa regional market",
    "7-1-7 impact estimator",
]
MAIN_NAV_MODULES = [m for m in NAV_MODULES if m not in ROI_NAV_MODULES]

# Display names for operators and decision-makers (internal routing keys stay `NAV_MODULES`).
NAV_LABEL_FOR_USER: dict[str, str] = {
    "Home": "Home",
    "Strategic signals": "National dashboard",
    "Pathogen workspace": "Pathogen planning",
    "VDTEC & Pathogen ROI": "VDTEC & ROI",
    "Clinical trial sites": "Trial locations",
    "NMS 100-day surge": "Medical supplies surge",
    "East Africa regional market": "East Africa region",
    "7-1-7 impact estimator": "Early action (7‑1‑7)",
    "STI venture matrix": "Venture decisions",
    "ROI & Financing": "ROI & financing",
    "Executive Briefing": "Executive summary",
    "Disease Surveillance": "Track a disease",
    "Disease Profiler": "Disease profile",
    "Global Surveillance": "Global picture",
    "Forecast Lab": "Forecasts",
    "Uganda Hotspots": "Maps & hotspots",
    "Action Plan": "Response checklist",
    "EPI-ThinkTank": "Think tank",
    "Developers": "Technical reference",
    "Reports library": "Reports & files",
    "Admin": "Admin settings",
}


def _nav_label(page_id: str) -> str:
    return NAV_LABEL_FOR_USER.get(page_id, page_id)


# Optional map support
try:
    import folium
    from streamlit_folium import st_folium
    FOLIUM_OK = True
except Exception:
    FOLIUM_OK = False

# ---------------- PAGE CONFIG ----------------
st.set_page_config(page_title="Epidemic intelligence | Pathogen Economy", page_icon="🦠", layout="wide")

# ---- Ambient 3D-style backdrop ----
# Streamlit's markdown sanitizer can drop out of <style> mode when HTML and
# nested @media CSS share the same st.markdown call, so we keep them separate:
# (1) styles by themselves, then (2) the decorative <div>s.
st.markdown(
    """
<style>
.epi-3d-bg {
    position: fixed;
    inset: 0;
    z-index: 0;
    pointer-events: none;
    overflow: hidden;
    perspective: 1100px;
    perspective-origin: 50% 30%;
}
.epi-3d-grid {
    position: absolute;
    left: -10%;
    right: -10%;
    bottom: -25%;
    height: 75%;
    background-image:
        linear-gradient(rgba(29, 78, 216, 0.16) 1px, transparent 1px),
        linear-gradient(90deg, rgba(15, 118, 110, 0.16) 1px, transparent 1px);
    background-size: 56px 56px, 56px 56px;
    transform: rotateX(64deg) translateZ(-160px);
    transform-origin: 50% 100%;
    mask-image: radial-gradient(ellipse at 50% 0%, black 40%, transparent 78%);
    -webkit-mask-image: radial-gradient(ellipse at 50% 0%, black 40%, transparent 78%);
    animation: epiGridDrift 28s linear infinite;
    opacity: 0.55;
}
@keyframes epiGridDrift {
    from { background-position: 0 0, 0 0; }
    to   { background-position: 0 56px, 56px 0; }
}
.epi-3d-blob {
    position: absolute;
    border-radius: 50%;
    filter: blur(58px);
    opacity: 0.55;
    will-change: transform;
}
.epi-3d-blob-a {
    width: 520px; height: 520px;
    left: -120px; top: -160px;
    background: radial-gradient(circle, rgba(56,189,248,0.55), rgba(56,189,248,0) 65%);
    animation: epiBlobFloat 22s ease-in-out infinite;
}
.epi-3d-blob-b {
    width: 460px; height: 460px;
    right: -140px; top: 8%;
    background: radial-gradient(circle, rgba(34,197,94,0.42), rgba(34,197,94,0) 65%);
    animation: epiBlobFloat 26s ease-in-out infinite reverse;
}
.epi-3d-blob-c {
    width: 380px; height: 380px;
    left: 30%; bottom: -120px;
    background: radial-gradient(circle, rgba(167,139,250,0.42), rgba(167,139,250,0) 66%);
    animation: epiBlobFloat 30s ease-in-out infinite;
    animation-delay: -7s;
}
.epi-3d-blob-d {
    width: 300px; height: 300px;
    right: 18%; bottom: -80px;
    background: radial-gradient(circle, rgba(244,114,182,0.32), rgba(244,114,182,0) 65%);
    animation: epiBlobFloat 24s ease-in-out infinite;
    animation-delay: -12s;
}
@keyframes epiBlobFloat {
    0%, 100% { transform: translate3d(0, 0, 0) scale(1); }
    25%      { transform: translate3d(28px, -22px, 0) scale(1.06); }
    50%      { transform: translate3d(-18px, 22px, 0) scale(0.96); }
    75%      { transform: translate3d(22px, 14px, 0) scale(1.03); }
}
.epi-3d-particles {
    position: absolute;
    inset: 0;
    background-image:
        radial-gradient(1.5px 1.5px at 18% 22%, rgba(15,23,42,0.28), transparent 60%),
        radial-gradient(1.2px 1.2px at 72% 38%, rgba(15,23,42,0.22), transparent 60%),
        radial-gradient(1.4px 1.4px at 44% 78%, rgba(15,23,42,0.22), transparent 60%),
        radial-gradient(1.2px 1.2px at 88% 82%, rgba(15,23,42,0.22), transparent 60%),
        radial-gradient(1.6px 1.6px at 8% 64%, rgba(15,23,42,0.22), transparent 60%);
    animation: epiParticleDrift 40s linear infinite;
    opacity: 0.55;
}
@keyframes epiParticleDrift {
    from { background-position: 0 0, 0 0, 0 0, 0 0, 0 0; }
    to   { background-position: 60px -40px, -40px 50px, 30px -50px, -50px 40px, 40px 60px; }
}
.stApp { background: transparent !important; }
.stApp::before {
    content: "";
    position: fixed;
    inset: 0;
    z-index: -1;
    background:
        radial-gradient(120% 90% at 50% -10%, rgba(219, 234, 254, 0.55), transparent 60%),
        linear-gradient(180deg, #eef4f9 0%, #e6f0ec 100%);
}
.main, [data-testid="stAppViewContainer"] > .main { position: relative; z-index: 1; }
[data-testid="stSidebar"] { position: relative; z-index: 3; }

/* Subtle 3D card hover used across the app — cards tilt slightly on hover */
.hero-card,
.feature-card,
.status-panel,
.insight-panel,
div[data-testid="stMetric"],
[data-testid="stExpander"],
.forecast-hero-shell,
.forecast-dash-banner {
    transform-style: preserve-3d;
    transition: transform 0.35s cubic-bezier(0.2, 0.7, 0.2, 1),
                box-shadow 0.35s cubic-bezier(0.2, 0.7, 0.2, 1) !important;
    will-change: transform;
}
div[data-testid="stMetric"]:hover,
.feature-card:hover,
.status-panel:hover,
.insight-panel:hover,
.hero-card:hover,
.forecast-dash-banner:hover {
    transform: translateY(-3px) rotateX(2.4deg) rotateY(-2.4deg) !important;
    box-shadow: 0 22px 48px rgba(15, 23, 42, 0.18) !important;
}
.forecast-hero-shell:hover {
    transform: translateY(-2px) rotateX(1.6deg) rotateY(-1.6deg) !important;
    box-shadow: 0 28px 60px rgba(15, 23, 42, 0.22),
                inset 0 1px 0 rgba(255,255,255,0.92) !important;
}

/* Reduce motion: gently slow animations instead of disabling them */
@media (prefers-reduced-motion: reduce) {
    .epi-3d-grid       { animation-duration: 90s !important; }
    .epi-3d-blob-a     { animation-duration: 70s !important; }
    .epi-3d-blob-b     { animation-duration: 80s !important; }
    .epi-3d-blob-c     { animation-duration: 95s !important; }
    .epi-3d-blob-d     { animation-duration: 75s !important; }
    .epi-3d-particles  { animation-duration: 120s !important; }
    .hero-card,
    .feature-card,
    .status-panel,
    .insight-panel,
    div[data-testid="stMetric"],
    [data-testid="stExpander"],
    .forecast-hero-shell,
    .forecast-dash-banner {
        transition-duration: 0.6s !important;
    }
    .hero-card:hover, .feature-card:hover, .status-panel:hover,
    .insight-panel:hover, div[data-testid="stMetric"]:hover,
    .forecast-hero-shell:hover, .forecast-dash-banner:hover {
        transform: translateY(-1.5px) rotateX(1deg) rotateY(-1deg) !important;
    }
}
</style>
""",
    unsafe_allow_html=True,
)

st.markdown(
    """
<div class="epi-3d-bg" aria-hidden="true">
  <div class="epi-3d-grid"></div>
  <div class="epi-3d-blob epi-3d-blob-a"></div>
  <div class="epi-3d-blob epi-3d-blob-b"></div>
  <div class="epi-3d-blob epi-3d-blob-c"></div>
  <div class="epi-3d-blob epi-3d-blob-d"></div>
  <div class="epi-3d-particles"></div>
</div>
""",
    unsafe_allow_html=True,
)

st.markdown("""
<style>
    .stApp {
        background:
            radial-gradient(circle at 12% 12%, rgba(29, 162, 74, 0.10), transparent 34%),
            radial-gradient(circle at 90% 8%, rgba(59, 130, 246, 0.08), transparent 32%),
            linear-gradient(180deg, #f6faf7 0%, #eef6f2 100%);
        color: #0f172a;
    }
    header[data-testid="stHeader"] {
        display: none !important;
    }
    .main { color: #0f172a; position: relative; z-index: 2; }
    .stButton > button {
        background: linear-gradient(45deg, #2b8a3e, #1f7a35);
        color: white; border-radius: 12px; border: none;
        padding: 10px 20px; font-weight: 700;
        width: 100%;
        transition: all 0.2s ease;
        box-shadow: 0 4px 12px rgba(16, 24, 40, 0.15);
    }
    .stButton > button:hover {
        background: linear-gradient(45deg, #16a34a, #15803d);
        transform: translateY(-1px);
        box-shadow: 0 8px 18px rgba(16, 24, 40, 0.20);
    }
    .stButton > button:focus {
        outline: 2px solid #86efac !important;
        outline-offset: 2px;
    }
    .hero-card {
        background: linear-gradient(180deg, #ffffff, #f7fbf8);
        border: 1px solid #d9e7dd;
        border-radius: 20px;
        padding: 24px;
        box-shadow: 0 8px 20px rgba(15, 23, 42, 0.10);
        margin-bottom: 18px;
    }
    .feature-card {
        background: rgba(255, 255, 255, 0.92);
        border: 1px solid #d8e2ea;
        border-radius: 14px;
        padding: 16px;
        min-height: 170px;
        backdrop-filter: blur(3px);
    }
    .kpi-chip {
        display: inline-block;
        padding: 8px 12px;
        border-radius: 999px;
        margin: 4px 6px 4px 0;
        border: 1px solid rgba(34, 139, 34, 0.35);
        background: rgba(34, 139, 34, 0.08);
        color: #14532d;
        font-size: 0.88rem;
    }
    .status-panel {
        background: #ffffff;
        border: 1px solid #d8e2ea;
        border-radius: 14px;
        padding: 12px;
        margin: 8px 0 12px 0;
    }
    .insight-panel {
        background: #f8fbfd;
        border: 1px solid #cfe0ec;
        border-radius: 14px;
        padding: 12px 14px;
        margin-bottom: 10px;
        animation: slideInRight 0.5s ease both;
    }
    .legend-chip {
        display: inline-block;
        margin-right: 8px;
        margin-bottom: 6px;
        padding: 4px 9px;
        border-radius: 999px;
        border: 1px solid rgba(148, 163, 184, 0.35);
        font-size: 0.8rem;
        background: rgba(255, 255, 255, 0.92);
    }
    h1, h2, h3 {color: #0f172a;}
    .stMarkdown, .stMarkdown p, [data-testid="stMarkdownContainer"] p { color: #1f2937 !important; }
    .stCaption, [data-testid="stCaption"] { color: #475569 !important; font-weight: 500; }
    label, span[data-baseweb="tag"] { color: #1f2937 !important; }
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #f4f8f5 0%, #edf4f0 100%) !important;
        border-right: 1px solid #d6e3da;
    }
    [data-testid="stSidebar"] .stMarkdown,
    [data-testid="stSidebar"] .stMarkdown p,
    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] span,
    [data-testid="stSidebar"] label {
        color: #1f2937 !important;
        font-weight: 500;
    }
    [data-testid="stSidebar"] [data-testid="stCaption"] {
        color: #475569 !important;
        font-weight: 500 !important;
    }
    [data-testid="stSidebar"] [data-testid="stMetricValue"] {
        color: #14532d !important;
    }
    [data-testid="stSidebar"] [data-testid="stMetricLabel"] {
        color: #374151 !important;
    }
    [data-testid="stSidebar"] .stRadio label,
    [data-testid="stSidebar"] .stSelectbox label {
        color: #1f2937 !important;
    }
    [data-testid="stMetricValue"] { color: #14532d !important; }
    [data-testid="stMetricLabel"] { color: #334155 !important; }
    @keyframes slideInUp {
        from { opacity: 0; transform: translateY(10px); }
        to { opacity: 1; transform: translateY(0); }
    }
    @keyframes slideInRight {
        from { opacity: 0; transform: translateX(18px); }
        to { opacity: 1; transform: translateX(0); }
    }
    :root {
        --nav-glass-bg: linear-gradient(135deg, rgba(15, 23, 42, 0.55), rgba(30, 64, 175, 0.32));
        --nav-glass-tint: radial-gradient(120% 200% at 50% -50%, rgba(96, 165, 250, 0.18), rgba(15, 23, 42, 0.10) 50%, rgba(15, 23, 42, 0.55) 80%);
        --nav-border: rgba(255, 255, 255, 0.14);
        --nav-border-strong: rgba(255, 255, 255, 0.22);
        --nav-text: #e2e8f0;
        --nav-text-soft: #cbd5e1;
        --nav-text-strong: #f8fafc;
        --nav-chip-bg: rgba(255, 255, 255, 0.06);
        --nav-chip-bg-hover: rgba(59, 130, 246, 0.22);
        --nav-glow: 0 0 22px rgba(96, 165, 250, 0.30);
    }
    html[data-theme="dark"] {
        --nav-glass-bg: linear-gradient(135deg, rgba(2, 6, 23, 0.62), rgba(30, 41, 59, 0.42));
        --nav-glass-tint: radial-gradient(120% 200% at 50% -50%, rgba(56, 189, 248, 0.16), rgba(2, 6, 23, 0.30) 55%, rgba(2, 6, 23, 0.70) 85%);
        --nav-border: rgba(148, 163, 184, 0.22);
        --nav-border-strong: rgba(148, 163, 184, 0.36);
        --nav-text: #e5e7eb;
        --nav-text-soft: #cbd5e1;
        --nav-text-strong: #f8fafc;
        --nav-chip-bg: rgba(255, 255, 255, 0.04);
        --nav-chip-bg-hover: rgba(56, 189, 248, 0.20);
        --nav-glow: 0 0 22px rgba(56, 189, 248, 0.28);
    }
    .st-key-top_nav_shell {
        position: sticky;
        top: 8px;
        z-index: 99;
        margin-bottom: 14px;
        border-radius: 18px;
        border: 1px solid var(--nav-border);
        box-shadow:
            0 16px 40px rgba(2, 6, 23, 0.40),
            inset 0 1px 0 rgba(255, 255, 255, 0.10);
        background:
            var(--nav-glass-tint),
            var(--nav-glass-bg);
        backdrop-filter: blur(18px) saturate(160%);
        -webkit-backdrop-filter: blur(18px) saturate(160%);
        padding: 12px 14px;
        transition: box-shadow 0.25s ease, border-color 0.25s ease, transform 0.25s ease;
        animation: navFadeIn 0.45s ease both;
    }
    .st-key-top_nav_shell:hover {
        border-color: var(--nav-border-strong);
        box-shadow:
            0 22px 50px rgba(2, 6, 23, 0.50),
            inset 0 1px 0 rgba(255, 255, 255, 0.14);
    }
    @keyframes navFadeIn {
        from { opacity: 0; transform: translateY(-6px); }
        to   { opacity: 1; transform: translateY(0); }
    }
    .st-key-top_nav_shell [data-testid="stHorizontalBlock"] {
        align-items: center;
        gap: 0.55rem;
    }
    .top-nav-brand {
        color: var(--nav-text-strong);
        font-family: Inter, "Segoe UI", Roboto, sans-serif;
        font-size: 0.83rem;
        font-weight: 700;
        letter-spacing: 0.22em;
        text-transform: uppercase;
        white-space: nowrap;
        opacity: 0.98;
        text-shadow: 0 1px 0 rgba(0, 0, 0, 0.25);
    }
    .top-nav-active-line {
        display: inline-block;
        color: var(--nav-text);
        background: var(--nav-chip-bg);
        border: 1px solid var(--nav-border);
        border-radius: 999px;
        padding: 7px 12px;
        font-family: Inter, "Segoe UI", Roboto, sans-serif;
        font-size: 0.76rem;
        font-weight: 650;
        letter-spacing: 0.04em;
        text-transform: uppercase;
        white-space: nowrap;
        box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.08);
        backdrop-filter: blur(8px) saturate(140%);
        -webkit-backdrop-filter: blur(8px) saturate(140%);
        text-align: center;
        transition: border-color 0.2s ease, background 0.2s ease, box-shadow 0.2s ease;
    }
    .top-nav-active-line:hover {
        border-color: var(--nav-border-strong);
        background: var(--nav-chip-bg-hover);
        box-shadow: var(--nav-glow);
    }
    .top-nav-divider {
        height: 1px;
        margin: 8px 0 10px 0;
        background: linear-gradient(90deg, rgba(148, 163, 184, 0.04), rgba(148, 163, 184, 0.45), rgba(148, 163, 184, 0.04));
    }
    /* ---- Text-only popover (dropdown) links inside the nav ---- */
    html .st-key-top_nav_shell [data-testid="stPopover"] button,
    html .st-key-top_nav_shell [data-baseweb="popover"] button,
    html .st-key-top_nav_shell div[data-testid="stPopover"] > button {
        position: relative !important;
        display: inline-flex !important;
        align-items: center !important;
        justify-content: center !important;
        gap: 0.35rem !important;
        background: transparent !important;
        background-color: transparent !important;
        background-image: none !important;
        border: none !important;
        outline: none !important;
        box-shadow: none !important;
        backdrop-filter: none !important;
        -webkit-backdrop-filter: none !important;
        color: #ffffff !important;
        font-family: Inter, "Segoe UI", Roboto, sans-serif !important;
        font-size: 0.78rem !important;
        font-weight: 600 !important;
        text-transform: uppercase !important;
        letter-spacing: 0.09em !important;
        padding: 0.4rem 0.65rem !important;
        min-height: auto !important;
        text-shadow: 0 1px 2px rgba(0, 0, 0, 0.35);
        cursor: pointer !important;
        transition: all 0.3s ease-in-out !important;
    }
    /* Sliding underline that grows from the left on hover */
    html .st-key-top_nav_shell [data-testid="stPopover"] button::after {
        content: "";
        position: absolute;
        left: 0.65rem;
        right: 0.65rem;
        bottom: 0.22rem;
        height: 1.5px;
        background: linear-gradient(90deg, rgba(191, 219, 254, 0.95), rgba(96, 165, 250, 0.55));
        border-radius: 1px;
        transform: scaleX(0);
        transform-origin: left center;
        opacity: 0.9;
        box-shadow: 0 0 8px rgba(147, 197, 253, 0.55);
        transition: transform 0.3s ease-in-out, opacity 0.3s ease-in-out;
        pointer-events: none;
    }
    html .st-key-top_nav_shell [data-testid="stPopover"] button:hover {
        background: transparent !important;
        background-color: transparent !important;
        box-shadow: none !important;
        color: #f0f9ff !important;
        text-shadow:
            0 0 10px rgba(147, 197, 253, 0.75),
            0 1px 2px rgba(0, 0, 0, 0.35);
        transform: translateY(-1px) scale(1.04) !important;
    }
    html .st-key-top_nav_shell [data-testid="stPopover"] button:hover::after {
        transform: scaleX(1);
    }
    html .st-key-top_nav_shell [data-testid="stPopover"] button:active {
        transform: translateY(0) scale(1.0) !important;
    }
    html .st-key-top_nav_shell [data-testid="stPopover"] button:focus-visible {
        outline: 2px solid rgba(147, 197, 253, 0.85) !important;
        outline-offset: 4px !important;
        border-radius: 4px !important;
    }
    /* Inherit color into nested label spans/divs Streamlit may render */
    .st-key-top_nav_shell [data-testid="stPopover"] button > div,
    .st-key-top_nav_shell [data-testid="stPopover"] button > span,
    .st-key-top_nav_shell [data-testid="stPopover"] button * {
        background: transparent !important;
        background-color: transparent !important;
        background-image: none !important;
        color: inherit !important;
        text-shadow: inherit !important;
    }
    /* Strip every wrapper inside the nav shell so buttons float on the glass */
    .st-key-top_nav_shell *:not(button):not(svg):not(path) {
        background: transparent !important;
        background-color: transparent !important;
        background-image: none !important;
        border-color: transparent !important;
        box-shadow: none !important;
    }
    .st-key-top_nav_shell button {
        margin: 0 !important;
    }
    /* Restore the active chip styling (it's not a button) */
    .st-key-top_nav_shell .top-nav-active-line {
        background: var(--nav-chip-bg) !important;
        border: 1px solid var(--nav-border) !important;
        box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.08) !important;
    }
    .st-key-top_nav_shell .top-nav-active-line:hover {
        border-color: var(--nav-border-strong) !important;
        background: var(--nav-chip-bg-hover) !important;
        box-shadow: var(--nav-glow) !important;
    }
    /* Restore the divider line */
    .st-key-top_nav_shell .top-nav-divider {
        background: linear-gradient(90deg, rgba(148, 163, 184, 0.04), rgba(148, 163, 184, 0.45), rgba(148, 163, 184, 0.04)) !important;
    }
    .st-key-top_nav_shell [data-testid="stButton"] > button {
        border-radius: 999px !important;
        border: 1px solid var(--nav-border) !important;
        background: var(--nav-chip-bg) !important;
        backdrop-filter: blur(10px) saturate(140%) !important;
        -webkit-backdrop-filter: blur(10px) saturate(140%) !important;
        color: var(--nav-text) !important;
        font-family: Inter, "Segoe UI", Roboto, sans-serif !important;
        font-size: 0.75rem !important;
        font-weight: 680 !important;
        text-transform: uppercase !important;
        letter-spacing: 0.06em !important;
        min-height: 2.02rem !important;
        box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.06) !important;
        padding-left: 0.65rem !important;
        padding-right: 0.65rem !important;
        transition: transform 0.18s ease, box-shadow 0.18s ease, background 0.18s ease, border-color 0.18s ease, color 0.18s ease !important;
    }
    .st-key-top_nav_shell [data-testid="stButton"] > button:hover {
        border-color: rgba(147, 197, 253, 0.75) !important;
        color: #ffffff !important;
        background: var(--nav-chip-bg-hover) !important;
        transform: translateY(-1px) !important;
        box-shadow:
            0 10px 22px rgba(15, 23, 42, 0.45),
            0 0 0 1px rgba(147, 197, 253, 0.45),
            var(--nav-glow) !important;
    }
    .st-key-top_nav_shell [data-testid="stButton"] > button:active {
        transform: translateY(0) !important;
    }
    .st-key-top_nav_shell [data-testid="stButton"] > button[kind="primary"] {
        background: linear-gradient(135deg, rgba(37, 99, 235, 0.85), rgba(30, 64, 175, 0.80)) !important;
        border-color: rgba(147, 197, 253, 0.55) !important;
        color: #ffffff !important;
        box-shadow:
            0 12px 22px rgba(37, 99, 235, 0.40),
            0 0 0 1px rgba(147, 197, 253, 0.45),
            0 0 28px rgba(96, 165, 250, 0.30) !important;
    }
    .st-key-top_nav_shell [data-testid="stButton"] > button[kind="primary"]:hover {
        background: linear-gradient(135deg, rgba(59, 130, 246, 0.95), rgba(37, 99, 235, 0.90)) !important;
        box-shadow:
            0 16px 30px rgba(37, 99, 235, 0.55),
            0 0 0 1px rgba(191, 219, 254, 0.55),
            0 0 36px rgba(96, 165, 250, 0.45) !important;
    }
    /* Vanilla dark-mode toggle button injected into the parent DOM */
    #epi-theme-toggle {
        position: fixed;
        top: 14px;
        right: 18px;
        z-index: 1000;
        width: 42px;
        height: 42px;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        border-radius: 999px;
        border: 1px solid var(--nav-border);
        background: var(--nav-chip-bg);
        color: var(--nav-text-strong);
        font-size: 1.05rem;
        cursor: pointer;
        backdrop-filter: blur(14px) saturate(160%);
        -webkit-backdrop-filter: blur(14px) saturate(160%);
        box-shadow:
            0 10px 24px rgba(2, 6, 23, 0.30),
            inset 0 1px 0 rgba(255, 255, 255, 0.10);
        transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease, background 0.2s ease;
    }
    #epi-theme-toggle:hover {
        transform: translateY(-1px) rotate(-6deg);
        border-color: var(--nav-border-strong);
        box-shadow:
            0 14px 30px rgba(2, 6, 23, 0.40),
            0 0 0 1px rgba(147, 197, 253, 0.40),
            var(--nav-glow);
    }
    #epi-theme-toggle:active { transform: translateY(0) rotate(0); }
    /* Dark mode global surface adjustments */
    html[data-theme="dark"] body,
    html[data-theme="dark"] .stApp,
    html[data-theme="dark"] .main {
        background: #0b1220 !important;
        color: #e5e7eb !important;
    }
    html[data-theme="dark"] .block-container { color: #e5e7eb; }
    html[data-theme="dark"] h1,
    html[data-theme="dark"] h2,
    html[data-theme="dark"] h3,
    html[data-theme="dark"] h4 { color: #f1f5f9 !important; }
    html[data-theme="dark"] p,
    html[data-theme="dark"] li,
    html[data-theme="dark"] label,
    html[data-theme="dark"] span { color: #cbd5e1; }
    html[data-theme="dark"] [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0b1220, #111827) !important;
        color: #e5e7eb !important;
    }
    html[data-theme="dark"] div[data-testid="stMetric"] {
        background: linear-gradient(180deg, #111827, #0f172a) !important;
        border: 1px solid rgba(148, 163, 184, 0.18) !important;
        color: #e5e7eb !important;
    }
    html[data-theme="dark"] [data-testid="stExpander"] {
        background: rgba(15, 23, 42, 0.6) !important;
        border: 1px solid rgba(148, 163, 184, 0.18) !important;
    }
    @media (max-width: 1100px) {
        .st-key-top_nav_shell {
            padding: 10px 10px;
        }
        .top-nav-brand { letter-spacing: 0.16em; font-size: 0.76rem; }
        .top-nav-active-line {
            white-space: normal;
        }
    }
    @media (max-width: 900px) {
        .block-container {
            padding-top: 0.75rem;
            padding-left: 0.7rem;
            padding-right: 0.7rem;
            max-width: 100%;
        }
        .hero-card {
            padding: 16px;
            border-radius: 14px;
        }
        .feature-card {
            min-height: auto;
            padding: 12px;
        }
        .kpi-chip {
            font-size: 0.8rem;
            padding: 6px 10px;
        }
        .stButton > button {
            border-radius: 10px;
            padding: 8px 12px;
            font-size: 0.92rem;
        }
        div[data-testid="stHorizontalBlock"] {
            gap: 0.5rem;
        }
        [data-testid="stSidebar"] {
            min-width: min(86vw, 320px);
        }
    }
    @media (max-width: 640px) {
        .st-key-top_nav_shell {
            margin-bottom: 10px;
            border-radius: 14px;
            padding: 10px 8px;
        }
        .top-nav-brand { display: none; }
        .top-nav-active-line {
            width: 100%;
        }
        h1 { font-size: 1.45rem !important; }
        h2 { font-size: 1.2rem !important; }
        h3 { font-size: 1.05rem !important; }
        p, li {
            font-size: 0.92rem;
            line-height: 1.45;
        }
    }
</style>
""", unsafe_allow_html=True)

st.markdown(
    """
<style>
    :root {
        --app-bg: #f3f6f9;
        --surface: #ffffff;
        --surface-soft: #f8fafc;
        --text-strong: #0f172a;
        --text-muted: #475569;
        --line: #d7dee8;
        --accent: #1d4ed8;
        --accent-2: #0f766e;
    }
    .block-container {
        padding-top: 0.85rem;
        padding-bottom: 1.2rem;
        max-width: 1360px;
    }
    .stApp, .main {
        font-family: "Inter", "Segoe UI", "Helvetica Neue", Arial, sans-serif !important;
        color: var(--text-strong);
    }
    h1, h2, h3 {
        letter-spacing: -0.01em;
        font-weight: 680 !important;
    }
    h1 { font-size: 1.95rem !important; margin-bottom: 0.4rem !important; }
    h2 { font-size: 1.42rem !important; margin-bottom: 0.25rem !important; }
    h3 { font-size: 1.12rem !important; margin-bottom: 0.15rem !important; }
    p, li, label, .stCaption {
        letter-spacing: 0.01em;
    }
    .stButton > button {
        background: linear-gradient(135deg, #1d4ed8, #1e40af) !important;
        border: 1px solid rgba(30, 64, 175, 0.92) !important;
        border-radius: 11px !important;
        font-weight: 650 !important;
        min-height: 2.35rem;
        box-shadow: 0 6px 18px rgba(30, 64, 175, 0.18) !important;
    }
    .stButton > button:hover {
        background: linear-gradient(135deg, #2563eb, #1d4ed8) !important;
        transform: translateY(-1px);
    }
    div[data-testid="stMetric"] {
        background: linear-gradient(180deg, var(--surface), #f8fbff);
        border: 1px solid var(--line);
        border-radius: 14px;
        padding: 12px 14px;
        box-shadow: 0 4px 14px rgba(15, 23, 42, 0.07);
    }
    [data-testid="stMetricLabel"] {
        text-transform: uppercase;
        letter-spacing: 0.06em;
        font-size: 0.72rem !important;
        color: #64748b !important;
    }
    [data-testid="stMetricValue"] {
        font-weight: 700 !important;
        color: #0f172a !important;
    }
    [data-testid="stExpander"] {
        border: 1px solid var(--line);
        border-radius: 12px;
        background: var(--surface);
    }
    [data-testid="stExpander"] details > summary {
        font-weight: 620;
        color: #1e293b;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 0.45rem;
        border-bottom: 1px solid var(--line);
        padding-bottom: 0.35rem;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 999px;
        border: 1px solid transparent;
        background: transparent;
        color: var(--text-muted);
        font-weight: 600;
        padding: 0.35rem 0.9rem;
    }
    .stTabs [aria-selected="true"] {
        background: rgba(29, 78, 216, 0.1) !important;
        color: #1d4ed8 !important;
        border-color: rgba(29, 78, 216, 0.22) !important;
    }
    .stTextInput input,
    .stTextArea textarea,
    .stNumberInput input,
    .stSelectbox [data-baseweb="select"],
    .stMultiSelect [data-baseweb="select"] {
        border-radius: 10px !important;
        border: 1px solid var(--line) !important;
        background: var(--surface) !important;
        box-shadow: none !important;
    }
    .stDataFrame, .stTable {
        border: 1px solid var(--line);
        border-radius: 12px;
        overflow: hidden;
        background: var(--surface);
    }
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #f5f8fc 0%, #edf3f8 100%) !important;
        border-right: 1px solid #d2dbe7 !important;
    }
    .status-panel, .insight-panel, .hero-card, .feature-card {
        border-radius: 14px !important;
        border-color: var(--line) !important;
        box-shadow: 0 6px 18px rgba(15, 23, 42, 0.07) !important;
    }
    @media (max-width: 900px) {
        .block-container {
            padding-left: 0.75rem;
            padding-right: 0.75rem;
        }
        h1 { font-size: 1.55rem !important; }
        h2 { font-size: 1.25rem !important; }
        .stButton > button { min-height: 2.2rem; }
    }
    /* Coolio · forecast dashboard shell */
    .forecast-hero-shell {
        position: relative;
        border-radius: 22px;
        padding: 22px 24px 20px;
        margin-bottom: 4px;
        overflow: hidden;
        border: 1px solid rgba(29, 78, 216, 0.2);
        background:
            linear-gradient(145deg, rgba(255,255,255,0.98) 0%, rgba(241,248,255,0.94) 42%, rgba(236,253,245,0.9) 100%);
        box-shadow:
            0 14px 44px rgba(15, 23, 42, 0.11),
            inset 0 1px 0 rgba(255,255,255,0.9);
    }
    .forecast-hero-shell::before {
        content: "";
        position: absolute;
        inset: 0;
        background-image:
            linear-gradient(90deg, rgba(29,78,216,0.055) 1px, transparent 1px),
            linear-gradient(0deg, rgba(29,78,216,0.055) 1px, transparent 1px);
        background-size: 26px 26px;
        pointer-events: none;
        opacity: 0.65;
        mask-image: linear-gradient(180deg, black 0%, transparent 88%);
    }
    .forecast-hero-head {
        position: relative;
        z-index: 2;
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        gap: 18px 22px;
    }
    .coolio-orb-wrap {
        perspective: 460px;
        flex-shrink: 0;
    }
    .coolio-orb {
        width: 88px;
        height: 88px;
        border-radius: 50%;
        position: relative;
        transform-style: preserve-3d;
        animation: coolioFloat 5s ease-in-out infinite;
        box-shadow:
            0 18px 38px rgba(8, 47, 73, 0.34),
            0 0 0 1px rgba(255,255,255,0.55) inset,
            0 -14px 32px rgba(56, 189, 248, 0.22) inset;
        background:
            radial-gradient(circle at 28% 22%, rgba(255,255,255,0.95), transparent 44%),
            radial-gradient(circle at 72% 76%, rgba(15,118,110,0.88), transparent 55%),
            radial-gradient(circle at 50% 50%, #0ea5e9, #0f766e 46%, #0f172a 100%);
    }
    .coolio-orb::after {
        content: "";
        position: absolute;
        inset: -10%;
        border-radius: 50%;
        background: radial-gradient(circle, rgba(56,189,248,0.38), transparent 68%);
        filter: blur(14px);
        z-index: -1;
        animation: coolioPulse 3.2s ease-in-out infinite;
    }
    @keyframes coolioFloat {
        0%, 100% { transform: rotateY(-14deg) rotateX(7deg) translateY(0); }
        50% { transform: rotateY(12deg) rotateX(-5deg) translateY(-7px); }
    }
    @keyframes coolioPulse {
        0%, 100% { opacity: 0.5; transform: scale(1); }
        50% { opacity: 0.88; transform: scale(1.09); }
    }
    .coolio-nameplate {
        font-size: 0.72rem;
        font-weight: 800;
        letter-spacing: 0.26em;
        text-transform: uppercase;
        color: #1d4ed8;
        margin-bottom: 4px;
    }
    .coolio-hero-title {
        font-size: 1.72rem !important;
        font-weight: 800 !important;
        letter-spacing: -0.025em !important;
        margin: 0 0 6px 0 !important;
        line-height: 1.15 !important;
        background: linear-gradient(92deg, #0f172a 0%, #1d4ed8 42%, #0f766e 100%);
        -webkit-background-clip: text;
        background-clip: text;
        color: transparent !important;
    }
    .coolio-hero-sub {
        margin: 0;
        font-size: 0.96rem;
        color: #475569;
        max-width: 520px;
        line-height: 1.48;
    }
    .coolio-risk-chip {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        flex-wrap: wrap;
        margin-top: 12px;
        padding: 8px 14px;
        border-radius: 999px;
        font-size: 0.82rem;
        font-weight: 650;
        background: rgba(29, 78, 216, 0.11);
        border: 1px solid rgba(29, 78, 216, 0.26);
        color: #1e3a8a;
    }
    .forecast-dash-banner {
        position: relative;
        border-radius: 14px;
        padding: 11px 16px;
        margin-bottom: 14px;
        border: 1px solid rgba(29, 78, 216, 0.16);
        background: linear-gradient(95deg, rgba(29,78,216,0.07), rgba(15,118,110,0.06));
        display: flex;
        align-items: center;
        gap: 12px;
    }
    .mini-orb {
        width: 36px;
        height: 36px;
        border-radius: 50%;
        flex-shrink: 0;
        background:
            radial-gradient(circle at 32% 28%, rgba(255,255,255,0.92), transparent 48%),
            radial-gradient(circle at 50% 52%, #0ea5e9, #0f766e 52%, #0f172a);
        box-shadow: 0 5px 16px rgba(15,23,42,0.22), 0 0 0 1px rgba(255,255,255,0.35) inset;
    }
    .forecast-dash-banner-text {
        font-size: 0.9rem;
        color: #334155;
        line-height: 1.4;
    }
    .forecast-dash-hint {
        display: inline-block;
        margin-left: 6px;
        font-size: 0.82rem;
        color: #64748b;
    }
    .coolio-sidebar-row {
        display: flex;
        align-items: center;
        gap: 10px;
        margin: 0 0 8px 0;
    }
    .coolio-sidebar-label {
        font-weight: 750;
        font-size: 0.88rem;
        color: #1e40af;
        letter-spacing: 0.03em;
    }
</style>
""",
    unsafe_allow_html=True,
)

def _validated_24h_for_disease(realtime_data: dict | None, disease: str) -> int:
    for x in (realtime_data or {}).get("validated_disease_counts_24h") or []:
        if not isinstance(x, dict):
            continue
        if str(x.get("disease") or "").strip().lower() == str(disease).strip().lower():
            return int(x.get("count") or 0)
    return 0


# ---------------- SHARED UX HELPERS ----------------
def set_page(page_name: str):
    st.session_state["selected_nav"] = page_name


def nav_action_button(label: str, target_page: str, key: str, force_primary: bool = False):
    is_active = st.session_state.get("selected_nav") == target_page
    button_type = "primary" if (is_active or force_primary) else "secondary"
    if st.button(label, key=key, type=button_type, width="stretch"):
        set_page(target_page)


def inject_theme_toggle():
    """Vanilla JS: persistent dark-mode toggle injected into parent DOM via localStorage."""
    components.html(
        """
        <script>
        (function() {
            try {
                const parentDoc = window.parent.document;
                const html = parentDoc.documentElement;
                const STORAGE_KEY = 'epi-theme';
                const stored = window.parent.localStorage.getItem(STORAGE_KEY) || 'light';
                html.setAttribute('data-theme', stored);

                let btn = parentDoc.getElementById('epi-theme-toggle');
                if (!btn) {
                    btn = parentDoc.createElement('button');
                    btn.id = 'epi-theme-toggle';
                    btn.setAttribute('aria-label', 'Toggle dark mode');
                    btn.setAttribute('title', 'Toggle dark mode');
                    parentDoc.body.appendChild(btn);
                }
                const renderIcon = (theme) => {
                    btn.textContent = theme === 'dark' ? '\U00002600' : '\U0001F319';
                };
                renderIcon(stored);

                btn.onclick = function() {
                    const cur = html.getAttribute('data-theme') || 'light';
                    const next = cur === 'dark' ? 'light' : 'dark';
                    html.setAttribute('data-theme', next);
                    window.parent.localStorage.setItem(STORAGE_KEY, next);
                    renderIcon(next);
                };
            } catch (e) {
                console.warn('Theme toggle init failed', e);
            }
        })();
        </script>
        """,
        height=0,
        width=0,
    )


def _render_coolio_live_strip(realtime_data: dict) -> None:
    snap = realtime_data.get("coolio_live")
    if not isinstance(snap, dict):
        return
    if snap.get("ok"):
        iso = snap.get("iso") or "—"
        dt = snap.get("last_date") or "—"
        cases = float(snap.get("new_cases_smoothed") or 0)
        strg = float(snap.get("stringency_index") or 0)
        url = str(snap.get("source_url") or "").strip()
        link = f"[OWID CSV]({url})" if url else "OWID"
        st.caption(
            f"Coolio live · {link} · **{iso}** latest row **{dt}** · "
            f"smoothed new cases/day **{cases:,.0f}** · stringency **{strg:.1f}**"
        )
    else:
        err = str(snap.get("error") or "unavailable")
        st.caption(f"Coolio live (OWID): _{err}_ — check connectivity or cache under `data/coolio_cache/`.")


def _render_coolio_verified_lens_strip(realtime_data: dict) -> None:
    lens = realtime_data.get("coolio_signal_lens")
    events = realtime_data.get("coolio_verified_events") or []
    if not isinstance(lens, dict):
        return
    total = int(lens.get("validated_in_window") or 0)
    oc = int(lens.get("official_count") or 0)
    wh = int(lens.get("window_hours") or 72)
    if total == 0 and oc == 0:
        return
    by_tier = lens.get("by_tier") or {}
    tier_bits = ", ".join(f"{k}={v}" for k, v in sorted(by_tier.items()) if int(v or 0) > 0)
    extra = f" · tiers **{tier_bits}**" if tier_bits else ""
    st.caption(
        f"Coolio lens · **{oc}** **official-feed** signal(s) validator-approved in **{wh}h** "
        f"({total} approved total in window{extra})."
    )
    if events:
        with st.expander("Official-source approved signals (newest first)", expanded=False):
            for e in events[:15]:
                src = str(e.get("source") or "")
                title = str(e.get("title") or "—")
                url = str(e.get("url") or "").strip()
                dis = str(e.get("disease") or "").strip()
                conf = float(e.get("confidence") or 0)
                if url:
                    st.markdown(
                        f"- [{title[:120]}]({url}) · `{src}` · conf {conf:.2f}"
                        + (f" · _{dis}_" if dis else "")
                    )
                else:
                    st.markdown(
                        f"- **{src}** · conf {conf:.2f}"
                        + (f" · _{dis}_" if dis else "")
                        + f" — {title[:200]}"
                    )


def render_top_navigation():
    inject_theme_toggle()
    selected_nav = st.session_state.get("selected_nav", NAV_MODULES[0])
    grouped = [
        ("Overview", ["Home", "Strategic signals", "Global Surveillance", "Uganda Hotspots"]),
        ("Respond", ["Clinical trial sites", "NMS 100-day surge", "East Africa regional market", "Action Plan"]),
        ("Leadership", ["Executive Briefing", "EPI-ThinkTank", "Developers", "Admin"]),
        ("Economy", ["Pathogen workspace", "VDTEC & Pathogen ROI", "STI venture matrix", "7-1-7 impact estimator"]),
        ("Tools", ["Disease Surveillance", "Disease Profiler", "Forecast Lab", "Reports library"]),
    ]
    active_group = next((label for label, modules in grouped if selected_nav in modules), "Overview")
    here = _nav_label(selected_nav)
    with st.container(key="top_nav_shell"):
        header_l, header_r = st.columns([1.5, 1.5])
        with header_l:
            st.markdown('<div class="top-nav-brand">Pathogen Economy Epiforecast</div>', unsafe_allow_html=True)
        with header_r:
            st.markdown(f'<div class="top-nav-active-line">You are in · {active_group} · {here}</div>', unsafe_allow_html=True)

        st.markdown('<div class="top-nav-divider"></div>', unsafe_allow_html=True)
        cols = st.columns([0.95, 0.95, 0.95, 1.10, 0.95, 1.20])
        for idx, (label, modules) in enumerate(grouped):
            with cols[idx]:
                group_label = f"{label} ▾" if selected_nav not in modules else f"{label} •"
                with st.popover(group_label, width="stretch"):
                    for module in modules:
                        key = "nav_pop_" + module.replace(" ", "_").replace("&", "and").replace("/", "_")
                        nav_action_button(_nav_label(module), module, key)
        with cols[5]:
            nav_action_button(_nav_label("ROI & Financing"), "ROI & Financing", "nav_roi_financing_cta", force_primary=True)


def render_home_landing(realtime_data: dict):
    dashboard = get_dashboard(realtime_data)
    signal = float(dashboard.get("signal_score") or 0)
    risk = str(dashboard.get("risk_level") or "—")

    hero_l, hero_r = st.columns([1.05, 0.95], gap="medium")
    with hero_l:
        st.markdown(
            coolio_forecast_hero_html(
                title="Pathogen Economy Epiforecast",
                subtitle=(
                    "Choose a disease in the sidebar, then pick a task below. "
                    "The skyline opposite shows **live validator-approved signals (24h)** per pathogen — "
                    "tower height = real count from `signals.db`. The dashboard does not auto-pick a disease; "
                    "open the sidebar and choose one only when you want to focus deep-dive views. "
                    "Use **Refresh data** for the latest picture, or tell Coolio where to go from the sidebar."
                ),
                signal_score=signal,
                risk_level=risk,
            ),
            unsafe_allow_html=True,
        )
    with hero_r:
        _vd = realtime_data.get("validated_disease_counts_24h") or []
        _top_disease = ""
        if _vd:
            _top_disease = str(_vd[0].get("disease") or "")
        _cap = "_Live signal skyline (3D) · validated disease signals · last 24h_"
        if _top_disease:
            _cap = f"_Live signal skyline (3D) · loudest pathogen: **{_top_disease}** · last 24h_"
        st.caption(_cap)
        st.plotly_chart(
            disease_signal_skyline_figure(realtime_data, height=300),
            use_container_width=True,
            config={"displayModeBar": False},
        )

    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.metric("Activity level (0–100)", f"{dashboard['signal_score']}/100", dashboard["risk_level"])
    with k2:
        st.metric("News & social (last day)", f"{dashboard['open_web_total']:,}")
    with k3:
        st.metric("Agency feeds (last day)", f"{dashboard['official_total']:,}")
    with k4:
        st.metric("Sources connected", f"{dashboard['feeds_online']}/{dashboard['feeds_total']}")

    _render_coolio_live_strip(realtime_data)
    _render_coolio_verified_lens_strip(realtime_data)

    st.markdown("### What do you want to do?")
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        nav_action_button("National dashboard", "Strategic signals", "home_open_signals", force_primary=True)
    with c2:
        nav_action_button("Track a disease", "Disease Surveillance", "home_open_surv")
    with c3:
        nav_action_button("Forecasts", "Forecast Lab", "home_open_forecast")
    with c4:
        nav_action_button("Executive summary", "Executive Briefing", "home_open_exec")
    with c5:
        nav_action_button("Reports & files", "Reports library", "home_open_reports")

    c6, c7, c8 = st.columns(3)
    with c6:
        nav_action_button("Maps & hotspots", "Uganda Hotspots", "home_open_hotspots")
    with c7:
        nav_action_button("Global picture", "Global Surveillance", "home_open_global")
    with c8:
        nav_action_button("Response checklist", "Action Plan", "home_open_action")

    left, right = st.columns([1.25, 1])
    with left:
        with st.expander("See the news and reports behind the numbers", expanded=False):
            st.markdown(f"- Last updated: **{realtime_data.get('last_updated', 'n/a')}**")
            st.markdown(f"- Snapshot note: {realtime_data.get('data_source', 'n/a')}")
            render_signal_sources_panel(realtime_data, key_suffix="home")

    with right:
        st.markdown("### Needs attention")
        for alert in (realtime_data.get("recent_alerts") or [])[:4]:
            st.warning(alert)
        if not (realtime_data.get("recent_alerts") or []):
            st.success("No urgent alerts right now — routine monitoring is fine.")


def _init_feed_health():
    if "feed_health" not in st.session_state:
        st.session_state["feed_health"] = {
            "malaria": {"status": "unknown", "message": "Not loaded yet"},
            "outbreak": {"status": "unknown", "message": "Not loaded yet"},
        }
    if "feed_snapshots" not in st.session_state:
        st.session_state["feed_snapshots"] = {}
    if "feed_last_success" not in st.session_state:
        st.session_state["feed_last_success"] = {
            "malaria": None,
            "outbreak": None,
        }
    if "retry_request" not in st.session_state:
        st.session_state["retry_request"] = None
    if "feed_diagnostics" not in st.session_state:
        st.session_state["feed_diagnostics"] = {
            "malaria": {"last_latency_ms": None, "retry_count": 0, "last_error": None},
            "outbreak": {"last_latency_ms": None, "retry_count": 0, "last_error": None},
        }


def set_feed_health(feed_name: str, status: str, message: str):
    st.session_state["feed_health"][feed_name] = {"status": status, "message": message}


def health_badge(feed_name: str, label: str):
    health = st.session_state["feed_health"].get(feed_name, {"status": "unknown", "message": ""})
    status = health["status"]
    icon = "🟢" if status == "ok" else ("🟠" if status == "degraded" else "⚪")
    return f"{icon} {label}: {health['message']}"


def mark_feed_success(feed_name: str):
    st.session_state["feed_last_success"][feed_name] = datetime.now()


def last_success_text(feed_name: str):
    last_ok = st.session_state["feed_last_success"].get(feed_name)
    if not last_ok:
        return "No successful fetch yet"
    return last_ok.strftime("%Y-%m-%d %H:%M:%S")


def record_feed_latency(feed_name: str, latency_ms: float):
    st.session_state["feed_diagnostics"][feed_name]["last_latency_ms"] = int(latency_ms)


def record_feed_error(feed_name: str, error_message: str):
    st.session_state["feed_diagnostics"][feed_name]["last_error"] = error_message[:160]


def clear_feed_error(feed_name: str):
    st.session_state["feed_diagnostics"][feed_name]["last_error"] = None


def increment_feed_retry(feed_name: str):
    st.session_state["feed_diagnostics"][feed_name]["retry_count"] += 1


# ---------------- SIDEBAR ----------------
_init_feed_health()


def get_malaria_uganda_data_resilient():
    started = time.perf_counter()
    try:
        df = load_malaria_uganda_real()
        st.session_state["feed_snapshots"]["malaria"] = df
        mark_feed_success("malaria")
        record_feed_latency("malaria", (time.perf_counter() - started) * 1000)
        clear_feed_error("malaria")
        set_feed_health("malaria", "ok", "Live (hourly cache)")
        return df
    except Exception as exc:
        record_feed_error("malaria", str(exc))
        if "malaria" in st.session_state["feed_snapshots"]:
            set_feed_health("malaria", "degraded", "Fallback snapshot (stale)")
            return st.session_state["feed_snapshots"]["malaria"]
        set_feed_health("malaria", "degraded", "Unavailable")
        raise


def get_outbreak_data_resilient():
    started = time.perf_counter()
    # Cache hits return immediately (no visible wait). Cold fetch shows a short, friendly line.
    with st.spinner("Preparing your dashboard…"):
        data = fetch_realtime_outbreak_data()
    st.session_state["feed_snapshots"]["outbreak"] = data
    mark_feed_success("outbreak")
    record_feed_latency("outbreak", (time.perf_counter() - started) * 1000)
    clear_feed_error("outbreak")
    hooks_ok = sum(
        bool(data.get(k))
        for k in ("gdelt_ok", "reddit_ok", "hackernews_ok", "newsapi_ok")
    )
    if hooks_ok >= 1:
        set_feed_health("outbreak", "ok", f"Open-web hooks active ({hooks_ok}/4)")
    else:
        set_feed_health("outbreak", "degraded", "No open-web hooks responded (baseline mode)")
    return data


retry_request = st.session_state.get("retry_request")
if retry_request == "malaria":
    load_malaria_uganda_real.clear()
    try:
        get_malaria_uganda_data_resilient()
    except Exception as exc:
        increment_feed_retry("malaria")
        record_feed_error("malaria", f"Retry failed: {exc}")
    st.session_state["retry_request"] = None
elif retry_request == "outbreak":
    fetch_realtime_outbreak_data.clear()
    try:
        get_outbreak_data_resilient()
    except Exception as exc:
        increment_feed_retry("outbreak")
        record_feed_error("outbreak", f"Retry failed: {exc}")
    st.session_state["retry_request"] = None

_coolio_refresh_sec = int(os.getenv("EPFORECAST_COOLIO_REFRESH_SEC", "0") or "0")
if _coolio_refresh_sec > 0:
    try:
        from backend.coolio_auto_ingest import coolio_live_ingest_enabled

        if coolio_live_ingest_enabled():
            _now = time.time()
            _last = float(st.session_state.get("_coolio_periodic_refresh_ts", 0.0))
            if _now - _last >= float(_coolio_refresh_sec):
                st.session_state["_coolio_periodic_refresh_ts"] = _now
                fetch_realtime_outbreak_data.clear()
                st.rerun()
    except Exception:
        pass

realtime_data = get_outbreak_data_resilient()
if "last_admin_notification_check" not in st.session_state:
    st.session_state["last_admin_notification_check"] = datetime.min
if (datetime.now() - st.session_state["last_admin_notification_check"]) >= timedelta(minutes=30):
    st.session_state["last_admin_notification_result"] = evaluate_and_send_admin_notifications(realtime_data)
    st.session_state["last_admin_notification_check"] = datetime.now()

logo_path = ROOT / "logo1.png"
if logo_path.exists():
    st.sidebar.image(str(logo_path), width="stretch")

st.sidebar.title("Science, Technology and Innovation")
st.sidebar.caption("Your choices here apply to maps, disease pages, and alerts.")

hosts = ["Human", "Animal", "Plant"]
if "pe_host" not in st.session_state:
    st.session_state["pe_host"] = "Human"
if st.session_state["pe_host"] not in hosts:
    st.session_state["pe_host"] = "Human"
pe_host = st.sidebar.selectbox(
    "Who or what is affected?",
    hosts,
    index=hosts.index(st.session_state["pe_host"]),
    key="pe_host_sb",
)
st.session_state["pe_host"] = pe_host

conds = ["Communicable", "NCD", "Trauma & injuries"]
if "pe_condition" not in st.session_state:
    st.session_state["pe_condition"] = "Communicable"
if st.session_state["pe_condition"] not in conds:
    st.session_state["pe_condition"] = "Communicable"
pe_condition = st.sidebar.selectbox(
    "Type of health situation",
    conds,
    index=conds.index(st.session_state["pe_condition"]),
    key="pe_condition_sb",
)
st.session_state["pe_condition"] = pe_condition

disease_opts = diseases_for(pe_host, pe_condition)
if "pe_disease" not in st.session_state or st.session_state["pe_disease"] not in disease_opts:
    st.session_state["pe_disease"] = disease_opts[0]
pe_disease = st.sidebar.selectbox(
    "Planning scenario (workspace tools)",
    disease_opts,
    index=disease_opts.index(st.session_state["pe_disease"]),
    key=f"pe_disease_sb_{pe_host}_{pe_condition}",
)
st.session_state["pe_disease"] = pe_disease

st.sidebar.markdown("##### Disease to watch everywhere")
st.sidebar.caption(
    "Optional — the dashboard, signal skyline, and 24h totals already show **every** disease "
    "the system has captured. Pick one only when you want to focus deep-dive views (forecasts, profiler, etc.). "
    "The list spans **400+** globally recognized pathogens plus any names in your local signal store."
)
if "policy_disease" not in st.session_state:
    st.session_state["policy_disease"] = NO_DISEASE_LABEL

_preset_watch = [
    "Cholera",
    "Malaria",
    "Typhoid",
    "Marburg",
    "Ebola",
    "Measles",
    "Dengue",
    "COVID-19",
    "Influenza",
    "Polio",
    "Yellow fever",
    "Mpox",
    "Lassa fever",
    "Rift Valley fever",
    "Anthrax",
    "Meningitis",
    "Chikungunya",
    "Norovirus",
    "H5N1",
    "Tuberculosis",
    "Plague",
    "Zika",
]
try:
    _validated_labels = list_validated_signal_diseases(min_count=1)
except Exception:
    _validated_labels = []
_pool_seen: set[str] = set()
_focus_pool: list[str] = []


def _add_to_focus_pool(name: str) -> None:
    if not name:
        return
    s = str(name).strip()
    if not s:
        return
    k = s.casefold()
    if k in _pool_seen:
        return
    _pool_seen.add(k)
    _focus_pool.append(s)


for x in _preset_watch + disease_opts + _validated_labels:
    _add_to_focus_pool(str(x))
for x in world_surveillance_disease_names():
    _add_to_focus_pool(x)
_pol = st.session_state.get("policy_disease") or NO_DISEASE_LABEL
if NO_DISEASE_LABEL in _focus_pool:
    _focus_pool.remove(NO_DISEASE_LABEL)
_focus_pool.insert(0, NO_DISEASE_LABEL)
if _pol != NO_DISEASE_LABEL:
    if _pol in _focus_pool:
        _focus_pool.remove(_pol)
    _focus_pool.insert(1, _pol)
st.session_state["_disease_focus_pool"] = list(_focus_pool)

_disease_search = st.sidebar.text_input(
    "Search diseases",
    placeholder="Type letters to narrow the list, or a new name",
    key="sidebar_disease_search",
)
_q = (_disease_search or "").strip().lower()
if _q:
    _filtered = [x for x in _focus_pool if _q in x.lower()]
    if not _filtered:
        _exact = (_disease_search or "").strip()
        _filtered = [_exact] if _exact else list(_focus_pool)
    elif _pol not in _filtered:
        _filtered = [_pol] + _filtered
else:
    _filtered = list(_focus_pool)

if _pol not in _filtered:
    _ix = 0
else:
    _ix = int(_filtered.index(_pol))
_ix = max(0, min(_ix, len(_filtered) - 1))

_sel = st.sidebar.selectbox(
    "Choose disease (charts & maps)",
    _filtered,
    index=_ix,
    key="sidebar_surv_disease_select",
)
st.session_state["policy_disease"] = _sel

if _sel == NO_DISEASE_LABEL:
    _total_24h_sb = int(realtime_data.get("validated_signals_24h", 0) or 0)
    _ndis_sb = sum(
        1
        for x in (realtime_data.get("validated_disease_counts_24h") or [])
        if isinstance(x, dict) and int(x.get("count") or 0) > 0
    )
    st.sidebar.markdown(
        "<div class='status-panel'><b>Now viewing</b><br/>"
        "<span style='font-size:1.05rem'>All diseases</span><br/>"
        f"<small>{_total_24h_sb:,} validated signals across {_ndis_sb} pathogen(s) in 24h</small></div>",
        unsafe_allow_html=True,
    )
else:
    _sig_n = _validated_24h_for_disease(realtime_data, _sel)
    _sel_safe = html.escape(str(_sel))
    st.sidebar.markdown(
        f"<div class='status-panel'><b>Now viewing</b><br/><span style='font-size:1.05rem'>{_sel_safe}</span><br/>"
        f"<small>Matched items in last 24h: <b>{_sig_n}</b></small></div>",
        unsafe_allow_html=True,
    )
if _q and len(_filtered) <= 5:
    st.sidebar.caption(f'Showing {len(_filtered)} match(es) for "{_disease_search.strip()}".')
elif _q:
    st.sidebar.caption(f"Showing {len(_filtered)} match(es). Refine your search to narrow further.")

st.sidebar.divider()

nav_options = NAV_MODULES
if "selected_nav" not in st.session_state:
    st.session_state["selected_nav"] = nav_options[0]
if st.session_state["selected_nav"] not in nav_options:
    st.session_state["selected_nav"] = nav_options[0]

with st.sidebar.expander("Coolio · commands", expanded=False):
    st.markdown(
        '<div class="coolio-sidebar-row"><div class="mini-orb"></div>'
        '<span class="coolio-sidebar-label">Ask in your own words</span></div>',
        unsafe_allow_html=True,
    )
    st.caption(
        "Navigate the app or set the watched disease in **natural language** when an LLM is configured; "
        "intent is routed to **allow-listed actions only** (navigation, disease focus, refresh, help) — "
        "no shell, no arbitrary code."
    )
    _toast = st.session_state.pop("coolio_cmd_toast", None)
    if _toast:
        st.success(_toast)
    with st.form("coolio_cmd_form"):
        _coolio_line = st.text_input(
            "Tell Coolio",
            placeholder='Any phrasing, e.g. "show me Uganda maps" · "watch influenza" · "refresh data"',
            label_visibility="collapsed",
        )
        _coolio_go = st.form_submit_button("Run")
    if _coolio_go and (_coolio_line or "").strip():
        _res = resolve_coolio_command(
            _coolio_line.strip(),
            nav_modules=NAV_MODULES,
            nav_labels=NAV_LABEL_FOR_USER,
        )
        st.session_state["coolio_cmd_toast"] = _res.message
        if _res.navigate_to:
            set_page(_res.navigate_to)
        if _res.set_policy_disease:
            st.session_state["policy_disease"] = _res.set_policy_disease
        if _res.refresh_outbreak:
            load_malaria_uganda_real.clear()
            fetch_realtime_outbreak_data.clear()
        st.rerun()

nav = st.session_state["selected_nav"]

st.sidebar.divider()
if "last_manual_refresh" not in st.session_state:
    st.session_state["last_manual_refresh"] = datetime.now()

if st.sidebar.button("🔄 Refresh data", key="refresh_live_feeds"):
    # Keep refresh targeted: clearing only relevant feed caches avoids evicting
    # unrelated expensive page-level caches.
    load_malaria_uganda_real.clear()
    fetch_realtime_outbreak_data.clear()
    st.session_state["last_manual_refresh"] = datetime.now()
    st.rerun()

with st.sidebar.expander("Having issues? Technical status", expanded=False):
    st.markdown(
        f"""
        <div class="status-panel">
            <b>Source checks</b><br/>
            {health_badge("malaria", "Background trend data")}<br/>
            <small>Last success: {last_success_text("malaria")}</small><br/>
            {health_badge("outbreak", "Live news & signals")}<br/>
            <small>Last success: {last_success_text("outbreak")}</small>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("**Response times**")
    for feed_key, feed_label in [
        ("malaria", "Trend data"),
        ("outbreak", "News bundle"),
    ]:
        diag = st.session_state["feed_diagnostics"][feed_key]
        latency_text = f"{diag['last_latency_ms']} ms" if diag["last_latency_ms"] is not None else "n/a"
        st.markdown(f"**{feed_label}** · {latency_text}")
        if diag["last_error"]:
            st.text(str(diag["last_error"]))

if nav == "Action Plan":
    render_sidebar_social_action_plan(realtime_data)

# ---------------- TOP NAV + LEADERSHIP ----------------
render_top_navigation()
nav = st.session_state["selected_nav"]
render_pe_leadership_strip()

_pool_top = st.session_state.get("_disease_focus_pool") or [NO_DISEASE_LABEL]
_pol_top = st.session_state.get("policy_disease") or NO_DISEASE_LABEL
_t1, _t2 = st.columns([1.05, 1.35])
with _t1:
    _top_search = st.text_input(
        "Search disease",
        placeholder="Type to filter or enter a new disease name",
        key="top_disease_search",
        label_visibility="visible",
    )
with _t2:
    _qt = (_top_search or "").strip().lower()
    if _qt:
        _ft = [x for x in _pool_top if _qt in x.lower()]
        if not _ft:
            _ex = (_top_search or "").strip()
            _ft = [_ex] if _ex else list(_pool_top)
        elif _pol_top not in _ft:
            _ft = [_pol_top] + _ft
    else:
        _ft = list(_pool_top)
    if _pol_top not in _ft:
        _ixt = 0
    else:
        _ixt = int(_ft.index(_pol_top))
    _ixt = max(0, min(_ixt, len(_ft) - 1))
    _st = st.selectbox(
        "Active disease",
        _ft,
        index=_ixt,
        key="top_surv_disease_select",
    )
    st.session_state["policy_disease"] = _st

_active_dis = get_policy_disease()
_total_signals_24h = int(realtime_data.get("validated_signals_24h", 0) or 0)
_n_diseases_24h = sum(
    1
    for x in (realtime_data.get("validated_disease_counts_24h") or [])
    if isinstance(x, dict) and int(x.get("count") or 0) > 0
)
if _active_dis:
    _pv = html.escape(str(_active_dis))
    _pn = _validated_24h_for_disease(realtime_data, _active_dis)
    st.markdown(
        f'<div style="background:linear-gradient(180deg,#f8fafc,#f1f5f9);border:1px solid #e2e8f0;'
        f'border-radius:12px;padding:10px 16px;margin:0 0 14px 0;font-size:0.98rem;">'
        f"<strong>Focused on</strong> · {_pv} &nbsp;·&nbsp; "
        f"<strong>Validated signals (24h)</strong> · {_pn}</div>",
        unsafe_allow_html=True,
    )
else:
    st.markdown(
        f'<div style="background:linear-gradient(180deg,#f0f9ff,#ecfeff);border:1px solid #bae6fd;'
        f'border-radius:12px;padding:10px 16px;margin:0 0 14px 0;font-size:0.98rem;">'
        f"<strong>Showing all diseases</strong> &nbsp;·&nbsp; "
        f"<strong>Validated signals (24h)</strong> · {_total_signals_24h:,} across "
        f"<strong>{_n_diseases_24h}</strong> pathogen(s) &nbsp;·&nbsp; "
        f"<em>Pick one in the sidebar / top bar to focus deep-dive views.</em></div>",
        unsafe_allow_html=True,
    )

# ---------------- PATHOGEN ECONOMY + CORE MODULES ----------------
if nav == "Home":
    render_home_landing(realtime_data)

elif nav == "Executive Briefing":
    render_executive_brief(realtime_data)

elif nav == "Pathogen workspace":
    render_pathogen_workspace_home(realtime_data)

elif nav == "VDTEC & Pathogen ROI":
    render_vdtec_roi(realtime_data)

elif nav == "Clinical trial sites":
    render_clinical_trial_sites()

elif nav == "NMS 100-day surge":
    render_nms_100_day_surge()

elif nav == "East Africa regional market":
    render_east_africa_regional(realtime_data)

elif nav == "7-1-7 impact estimator":
    render_717_impact()

elif nav == "STI venture matrix":
    render_sti_venture_matrix()

elif nav == "EPI-ThinkTank":
    render_epi_thinktank()

elif nav == "Developers":
    render_developers()

elif nav == "Reports library":
    render_reports_library(realtime_data)

elif nav == "Strategic signals":
    st.title("National dashboard")
    st.markdown(coolio_dashboard_strip_html(), unsafe_allow_html=True)
    st.caption(
        f"Updated **{realtime_data['last_updated']}** · {realtime_data['data_source']}"
        + (f" · Snapshot UTC `{_snap}`" if (_snap := (realtime_data.get('snapshot_utc') or '').strip()) else "")
    )
    if st.session_state["feed_health"]["outbreak"]["status"] == "degraded":
        st.warning("Live news feed is limited right now — some numbers use a safe fallback.")
    _render_coolio_live_strip(realtime_data)
    _render_coolio_verified_lens_strip(realtime_data)
    _, _, refresh_col = st.columns([1.4, 1.2, 1])
    with refresh_col:
        if st.button("Refresh dashboard", key="dash_refresh_btn"):
            st.cache_data.clear()
            st.session_state["last_manual_refresh"] = datetime.now()
            st.rerun()

    # Compact controls make the dashboard easier to scan and tune.
    dashboard = get_dashboard(realtime_data)
    social_total = dashboard["open_web_total"]
    official_total = dashboard["official_total"]
    feeds_live = dashboard["feeds_online"]
    feeds_total = dashboard["feeds_total"]

    ctl1, ctl2, ctl3 = st.columns([1.2, 1, 1])
    with ctl1:
        focus_metric = st.selectbox(
            "Highlight",
            ["News & social", "Agency feeds", "Connections"],
        )
    with ctl2:
        st.metric("Sources connected", f"{feeds_live}/{feeds_total}")
    with ctl3:
        quick_mode = st.toggle("Faster simple view", value=True)

    metric_order = [
        ("📰 News & social (24h)", f"{social_total:,}", "Public channels"),
        ("🏥 Agencies (24h)", f"{official_total:,}", "WHO / CDC / UN style feeds"),
        ("🌍 News mentions (24h)", f"{dashboard['news_mentions']:,}", "Press volume"),
        ("🔗 Connections", f"{feeds_live}/{feeds_total}", "Working feeds"),
    ]
    if focus_metric == "Agency feeds":
        metric_order = [metric_order[1], metric_order[0], metric_order[2], metric_order[3]]
    elif focus_metric == "Connections":
        metric_order = [metric_order[3], metric_order[0], metric_order[1], metric_order[2]]

    col1, col2, col3, col4 = st.columns(4)
    detail_keys = ["open_web", "official", "gdelt_news", "feed_reliability"]
    detail_labels = [
        "List news sources",
        "List agency feeds",
        "List recent news links",
        "Connection details",
    ]
    for col, card, detail_key, detail_btn in zip(
        [col1, col2, col3, col4], metric_order, detail_keys, detail_labels
    ):
        with col:
            st.metric(card[0], card[1], card[2])
            if st.button(detail_btn, key=f"sig_detail_btn_{detail_key}", width="stretch"):
                st.session_state["strategic_signal_detail"] = detail_key

    sx1, sx2, sx3 = st.columns(3)
    with sx1:
        st.metric(
            "Overall activity score",
            f"{dashboard['signal_score']}",
        )
    with sx2:
        st.metric(
            "Confirmed signals (24h)",
            f"{int(dashboard.get('validated_signals_24h', 0) or 0):,}",
        )
    with sx3:
        st.metric(
            "All mentions combined (24h)",
            f"{int(dashboard.get('combined_total', 0) or 0):,}",
        )

    selected_detail = st.session_state.get("strategic_signal_detail", "gdelt_news")
    if selected_detail:
        st.markdown("#### Source list")
        if selected_detail == "open_web":
            open_web_cases = realtime_data.get("open_web_cases") or []
            open_web_rows = [{"Source": k, "Signals_24h": int(v or 0)} for k, v in (realtime_data.get("social_channels") or {}).items()]
            if open_web_rows:
                st.markdown("**Signal totals by source**")
                open_web_df = pd.DataFrame(open_web_rows).sort_values("Signals_24h", ascending=False)
                st.dataframe(open_web_df, hide_index=True)
            if open_web_cases:
                st.markdown("**Recent linked signal items**")
                for idx, item in enumerate(open_web_cases[:25], start=1):
                    title = str(item.get("title") or "Untitled signal")
                    url = str(item.get("url") or "").strip()
                    source = str(item.get("source") or "Source")
                    meta = str(item.get("meta") or "")
                    suffix = f" ({meta})" if meta else ""
                    if url:
                        st.markdown(f"{idx}. [{title}]({url}) — **{source}**{suffix}")
                    else:
                        st.markdown(f"{idx}. {title} — **{source}**{suffix}")
            else:
                st.info("No open-web signal rows are available in this snapshot.")
        elif selected_detail == "official":
            official_rows = [
                {"Source": k, "Signals_24h": int(v or 0)} for k, v in (realtime_data.get("health_site_signals") or {}).items()
            ]
            official_cases = realtime_data.get("official_cases") or []
            if official_rows:
                st.markdown("**Signal totals by source**")
                official_df = pd.DataFrame(official_rows).sort_values("Signals_24h", ascending=False)
                st.dataframe(official_df, hide_index=True)
            if official_cases:
                st.markdown("**Recent linked official items**")
                for idx, item in enumerate(official_cases[:20], start=1):
                    title = str(item.get("title") or "Official update")
                    url = str(item.get("url") or "").strip()
                    source = str(item.get("source") or "Official source")
                    meta = str(item.get("meta") or "")
                    suffix = f" ({meta})" if meta else ""
                    if url:
                        st.markdown(f"{idx}. [{title}]({url}) — **{source}**{suffix}")
                    else:
                        st.markdown(f"{idx}. {title} — **{source}**{suffix}")
            else:
                st.info("No official health-feed rows are available in this snapshot.")
        elif selected_detail == "feed_reliability":
            reliability_rows = [
                {"Feed": "GDELT (news, 24h)", "Status": "Online" if realtime_data.get("gdelt_ok") else "Offline"},
                {"Feed": "Reddit (24h)", "Status": "Online" if realtime_data.get("reddit_ok") else "Offline"},
                {"Feed": "Hacker News (24h)", "Status": "Online" if realtime_data.get("hackernews_ok") else "Offline"},
                {"Feed": "NewsAPI (keyed)", "Status": "Online" if realtime_data.get("newsapi_ok") else "Offline"},
                {"Feed": "WHO News + WHO Africa", "Status": "Online" if realtime_data.get("who_ok") else "Offline"},
                {"Feed": "CDC outbreaks", "Status": "Online" if realtime_data.get("cdc_ok") else "Offline"},
                {"Feed": "UN (un.org via GDELT)", "Status": "Online" if realtime_data.get("un_ok") else "Offline"},
                {"Feed": "CIDRAP", "Status": "Online" if realtime_data.get("cidrap_ok") else "Offline"},
                {"Feed": "ReliefWeb (disease disasters)", "Status": "Online" if realtime_data.get("reliefweb_ok") else "Offline"},
                {"Feed": "PAHO", "Status": "Online" if realtime_data.get("paho_ok") else "Offline"},
            ]
            st.dataframe(pd.DataFrame(reliability_rows), hide_index=True)
        else:
            news_links = realtime_data.get("news_links") or []
            if not news_links:
                st.info("No recent article links were returned by the current feed snapshot.")
            else:
                for item in news_links[:10]:
                    title = str(item.get("title") or "Untitled article")
                    url = str(item.get("url") or "").strip()
                    domain = str(item.get("domain") or "source")
                    if url:
                        st.markdown(f"- [{title}]({url}) ({domain})")
                    else:
                        st.markdown(f"- {title} ({domain})")

    left, right = st.columns([1.2, 1])
    with left:
        st.subheader("📈 Real signal mix (current snapshot)")
        signal_rows = []
        for label, value in (realtime_data.get("social_channels") or {}).items():
            signal_rows.append({"Source": label, "Count": int(value or 0), "Group": "Open-web"})
        for label, value in (realtime_data.get("health_site_signals") or {}).items():
            signal_rows.append({"Source": label, "Count": int(value or 0), "Group": "Official health"})
        signal_df = pd.DataFrame(signal_rows).sort_values("Count", ascending=False)
        fig_signals = px.bar(
            signal_df,
            x="Count",
            y="Source",
            color="Group",
            orientation="h",
            title="Cross-source signal volumes (24h)",
            color_discrete_map={"Open-web": "#3b82f6", "Official health": "#22c55e"},
        )
        fig_signals.update_layout(
            margin=dict(l=20, r=20, t=50, b=10),
            template="plotly_dark",
            yaxis={"categoryorder": "total ascending"},
        )
        st.plotly_chart(fig_signals)

        with st.expander("📉 Malaria mortality trend (Uganda)", expanded=not quick_mode):
            try:
                df_ug = get_malaria_uganda_data_resilient()
                fig_malaria = px.area(
                    df_ug,
                    x="Year",
                    y="death_rate",
                    title="Malaria death rate per 100k (OWID/WHO)[web:61][web:54]",
                    labels={"death_rate": "Deaths per 100,000", "Year": "Year"},
                )
                fig_malaria.update_traces(line_color="#22c55e")
                fig_malaria.update_layout(
                    margin=dict(l=20, r=20, t=50, b=10),
                    template="plotly_dark",
                )
                st.plotly_chart(fig_malaria)
            except Exception as e:
                st.warning(f"Could not load real malaria data: {e}")

    with right:
        st.subheader("🔔 Priority alerts")
        st.markdown(
            """
            <div class="insight-panel">
                <b>Visual legend</b><br/>
                <span class="legend-chip" style="color:#f87171;">High risk</span>
                <span class="legend-chip" style="color:#fbbf24;">Medium risk</span>
                <span class="legend-chip" style="color:#4ade80;">Low risk</span>
                <span class="legend-chip" style="color:#93c5fd;">Info signal</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        for idx, alert in enumerate(realtime_data["recent_alerts"], start=1):
            st.error(f"P{idx} • {alert}")

        vd24 = realtime_data.get("validated_disease_counts_24h") or []
        if vd24:
            st.markdown("#### AI-validated signals by disease (24h)")
            st.dataframe(pd.DataFrame(vd24), hide_index=True)
        emerging_sig = [
            x
            for x in vd24
            if isinstance(x, dict)
            and int(x.get("count") or 0) > 0
            and str(x.get("disease") or "").strip()
            and not is_priority_disease(str(x.get("disease") or ""))
        ]
        if emerging_sig:
            st.markdown("#### Emerging pathogen alerts (validated, outside core four)")
            for row in sorted(emerging_sig, key=lambda x: -int(x.get("count") or 0)):
                d = str(row.get("disease") or "").strip()
                c = int(row.get("count") or 0)
                st.warning(
                    f"🆕 **{d}**: **{c}** AI-validated outbreak signal(s) in the last 24h — "
                    "open **Global Surveillance → NLP Alerts** or **Action Plan** for a dedicated brief."
                )

        signal_score = dashboard["signal_score"]
        risk_level = dashboard["risk_level"]
        st.progress(signal_score / 100)
        if dashboard["posture"] == "Surge":
            st.warning("Escalation suggested: Increase daily district review cadence.")
        elif dashboard["posture"] == "Elevated":
            st.info("Moderate watch: Keep active community surveillance and rapid reporting.")
        else:
            st.success("Baseline watch: Maintain routine monitoring protocols.")

        with st.expander("🗺️ Hotspots map", expanded=False):
            if FOLIUM_OK:
                from backend.uganda_folium_maps import build_uganda_operational_map

                _focus = get_policy_disease()
                _df_h = regional_hotspot_dataframe(_focus)
                _m = build_uganda_operational_map(
                    _df_h,
                    focus_disease=_focus,
                    subtitle="Strategic signals — sidebar disease",
                    show_heatmap=True,
                    show_clinical_layer=True,
                )
                if _m is not None:
                    st_folium(_m, use_container_width=True, height=440, key="strategic_hotspots_map")
                else:
                    st.info("Could not build map (folium error).")
            else:
                st.info("Folium not installed. Run: pip install folium streamlit-folium")

        with st.expander("🗂️ Report links & references", expanded=False):
            st.markdown("- Open the **Reports library** page for generated briefs and downloadable files.")
            st.markdown("- Use source links above to verify external reporting context.")

    st.markdown("### 🔗 Where each signal came from (live source links)")
    render_signal_sources_panel(realtime_data, key_suffix="strategic")

# ---------------- DISEASE SURVEILLANCE HUB ----------------
elif nav == "Disease Surveillance":
    render_disease_surveillance_hub(realtime_data)

# ---------------- DISEASE EXPLORER ----------------
elif nav == "Disease Profiler":
    render_disease_explorer()

# ---------------- REGION WATCH ----------------
elif nav == "Uganda Hotspots":
    render_region_watch()

# ---------------- FORECAST LAB ----------------
elif nav == "Forecast Lab":
    render_forecast_lab(realtime_data)

# ---------------- ALERTS & RECOMMENDATIONS ----------------
elif nav == "Action Plan":
    render_alerts_and_recommendations(realtime_data)

# ---------------- ADMIN ----------------
elif nav == "Admin":
    render_admin()

# ---------------- GLOBAL VIEW ----------------
elif nav == "Global Surveillance":
    render_global_view(realtime_data)

# ---------------- ROI & FINANCING (legacy module) ----------------
elif nav == "ROI & Financing":
    render_roi_financing()

# ---------------- FOOTER ----------------
st.sidebar.markdown("---")
