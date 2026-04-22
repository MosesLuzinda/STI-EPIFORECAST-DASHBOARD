import streamlit as st
import pandas as pd
import plotly.express as px
import random
from datetime import datetime, timedelta
from pathlib import Path
import time
from data_services import (
    load_malaria_uganda_real,
    fetch_realtime_outbreak_data,
    evaluate_and_send_admin_notifications,
)
from app_pages import (
    render_disease_explorer,
    render_region_watch,
    render_forecast_lab,
    render_alerts_and_recommendations,
    render_admin,
    render_global_view,
    render_executive_brief,
    render_roi_financing,
    render_sidebar_social_action_plan,
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

# Optional map support
try:
    import folium
    from streamlit_folium import st_folium
    FOLIUM_OK = True
except:
    FOLIUM_OK = False

# ---------------- PAGE CONFIG ----------------
st.set_page_config(page_title="STI-EpiForecast App | Pathogen Economy", page_icon="🦠", layout="wide")

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
    .hero-topnav-wrap {
        margin-bottom: 14px;
        border-radius: 18px;
        overflow: visible;
        border: 1px solid rgba(255, 255, 255, 0.12);
        box-shadow: 0 14px 30px rgba(15, 23, 42, 0.20);
        background:
            radial-gradient(130% 220% at 50% -60%, rgba(236, 72, 153, 0.35), rgba(76, 29, 149, 0.12) 38%, rgba(17, 24, 39, 0.96) 72%),
            linear-gradient(90deg, #111827 0%, #1f1147 50%, #111827 100%);
    }
    .hero-topnav {
        min-height: 76px;
        padding: 0 20px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 20px;
    }
    .hero-brand {
        color: #f8fafc !important;
        text-decoration: none !important;
        font-weight: 700;
        white-space: nowrap;
        letter-spacing: 0.2px;
    }
    .hero-nav-links {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 12px;
        flex: 1;
        color: #d1d5db;
        font-size: 0.92rem;
        font-weight: 500;
    }
    .hero-nav-cta {
        text-decoration: none !important;
        color: #ffffff !important;
        background: linear-gradient(135deg, #7c3aed, #4f46e5);
        border-radius: 12px;
        padding: 10px 14px;
        font-weight: 700;
        font-size: 0.88rem;
        white-space: nowrap;
        box-shadow: 0 8px 18px rgba(79, 70, 229, 0.35);
    }
</style>
""", unsafe_allow_html=True)

# ---------------- SHARED UX HELPERS ----------------
def set_page(page_name: str):
    st.session_state["selected_nav"] = page_name


def nav_action_button(label: str, target_page: str, key: str):
    is_active = st.session_state.get("selected_nav") == target_page
    if st.button(label, key=key, disabled=is_active, width="stretch"):
        set_page(target_page)


def render_top_navigation():
    grouped = [
        ("Signals", ["Strategic signals", "Global Surveillance", "Uganda Hotspots"]),
        ("Operations", ["Clinical trial sites", "NMS 100-day surge", "East Africa regional market", "Action Plan"]),
        ("Leadership", ["Executive Briefing", "EPI-ThinkTank", "Developers", "Admin"]),
        ("Pathogen Economy", ["Pathogen workspace", "VDTEC & Pathogen ROI", "STI venture matrix", "7-1-7 impact estimator"]),
        ("Analysis", ["Disease Profiler", "Forecast Lab", "Reports library"]),
    ]
    nav_html = " / ".join(label for label, _ in grouped)
    st.markdown(
        f"""
        <div class="hero-topnav-wrap">
            <div class="hero-topnav">
                <div class="hero-brand">
                    STI-OP Navigation
                </div>
                <div class="hero-nav-links">{nav_html}</div>
                <span class="hero-nav-cta">ROI &amp; Financing</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    cols = st.columns([1.1, 1.1, 1.1, 1.2, 1.0, 0.9])
    for idx, (label, modules) in enumerate(grouped):
        with cols[idx]:
            with st.popover(label, use_container_width=True):
                for module in modules:
                    key = "nav_pop_" + module.replace(" ", "_").replace("&", "and").replace("/", "_")
                    nav_action_button(module, module, key)
    with cols[5]:
        nav_action_button("ROI & Financing", "ROI & Financing", "nav_roi_financing_cta")


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
    except Exception:
        pass
    st.session_state["retry_request"] = None
elif retry_request == "outbreak":
    fetch_realtime_outbreak_data.clear()
    try:
        get_outbreak_data_resilient()
    except Exception:
        pass
    st.session_state["retry_request"] = None

realtime_data = get_outbreak_data_resilient()
if "last_admin_notification_check" not in st.session_state:
    st.session_state["last_admin_notification_check"] = datetime.min
if (datetime.now() - st.session_state["last_admin_notification_check"]) >= timedelta(minutes=30):
    st.session_state["last_admin_notification_result"] = evaluate_and_send_admin_notifications(realtime_data)
    st.session_state["last_admin_notification_check"] = datetime.now()

logo_path = Path("logo1.png")
if logo_path.exists():
    st.sidebar.image(str(logo_path), use_container_width=True)

st.sidebar.title("Science, Technology and Innovation")
st.sidebar.caption("Making Uganda the STI powerhouse of East Africa")

hosts = ["Human", "Animal", "Plant"]
if "pe_host" not in st.session_state:
    st.session_state["pe_host"] = "Human"
if st.session_state["pe_host"] not in hosts:
    st.session_state["pe_host"] = "Human"
pe_host = st.sidebar.selectbox(
    "Host realm",
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
    "Condition class",
    conds,
    index=conds.index(st.session_state["pe_condition"]),
    key="pe_condition_sb",
)
st.session_state["pe_condition"] = pe_condition

disease_opts = diseases_for(pe_host, pe_condition)
if "pe_disease" not in st.session_state or st.session_state["pe_disease"] not in disease_opts:
    st.session_state["pe_disease"] = disease_opts[0]
pe_disease = st.sidebar.selectbox(
    "Disease / condition focus",
    disease_opts,
    index=disease_opts.index(st.session_state["pe_disease"]),
    key=f"pe_disease_sb_{pe_host}_{pe_condition}",
)
st.session_state["pe_disease"] = pe_disease

legacy_profiler = ["Cholera", "Malaria", "Typhoid", "Marburg"]
if pe_disease in legacy_profiler:
    st.session_state["policy_disease"] = pe_disease

st.sidebar.divider()

nav_options = NAV_MODULES
if "selected_nav" not in st.session_state:
    st.session_state["selected_nav"] = nav_options[0]
if st.session_state["selected_nav"] not in nav_options:
    st.session_state["selected_nav"] = nav_options[0]

nav = st.session_state["selected_nav"]

st.sidebar.divider()
if "last_manual_refresh" not in st.session_state:
    st.session_state["last_manual_refresh"] = datetime.now()

if st.sidebar.button("🔄 Refresh Live Feeds", key="refresh_live_feeds"):
    st.cache_data.clear()
    st.session_state["last_manual_refresh"] = datetime.now()
    st.rerun()

st.sidebar.caption(f"Last manual refresh: {st.session_state['last_manual_refresh'].strftime('%H:%M:%S')}")
st.sidebar.markdown(
    f"""
    <div class="status-panel">
        <b>Feed status</b><br/>
        {health_badge("malaria", "OWID malaria")}<br/>
        <small>Last success: {last_success_text("malaria")}</small><br/>
        {health_badge("outbreak", "Outbreak signal")}<br/>
        <small>Last success: {last_success_text("outbreak")}</small>
    </div>
    """,
    unsafe_allow_html=True,
)

st.sidebar.markdown("#### Feed diagnostics")
for feed_key, feed_label in [
    ("malaria", "Malaria"),
    ("outbreak", "Outbreak"),
]:
    diag = st.session_state["feed_diagnostics"][feed_key]
    latency_text = f"{diag['last_latency_ms']} ms" if diag["last_latency_ms"] is not None else "n/a"
    st.sidebar.caption(f"{feed_label}: latency {latency_text} • retries {diag['retry_count']}")
    if diag["last_error"]:
        st.sidebar.caption(f"Last error: {diag['last_error']}")

if nav == "Action Plan":
    render_sidebar_social_action_plan(realtime_data)

st.sidebar.info("📡 VDTEC: vaccines, drugs, diagnostics, consumables, devices — risk → volumes → ROI.")

# ---------------- TOP NAV + LEADERSHIP ----------------
render_top_navigation()
nav = st.session_state["selected_nav"]
render_pe_leadership_strip()

# ---------------- HELPERS ----------------
def make_trend_series(base_value: int, days: int = 14, daily_step: int = 300, noise: int = 3000):
    dates = pd.date_range(end=datetime.now(), periods=days)
    vals = [base_value - random.randint(noise, noise * 2) + i * daily_step for i in range(days)]
    return dates, vals

# ---------------- PATHOGEN ECONOMY + CORE MODULES ----------------
if nav == "Executive Briefing":
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
    st.title("🌍 Strategic signals (national dashboard)")
    st.caption(f"🔄 {realtime_data['last_updated']} • {realtime_data['data_source']}")
    if st.session_state["feed_health"]["outbreak"]["status"] == "degraded":
        st.warning("Outbreak feed is in degraded mode. Showing baseline signals while enrichment feed is unavailable.")
    live_col1, live_col2, live_col3 = st.columns([1.4, 1.2, 1])
    with live_col1:
        st.markdown("`Live mode`: Cached feeds are refreshed continuously by TTL and manual trigger.")
    with live_col2:
        st.markdown(
            f"`Freshness`: Outbreak bundle ~30s cache + manual refresh | Pulled at {st.session_state['last_manual_refresh'].strftime('%H:%M:%S')}"
        )
    with live_col3:
        if st.button("Refresh Dashboard Feed", key="dash_refresh_btn"):
            st.cache_data.clear()
            st.session_state["last_manual_refresh"] = datetime.now()
            st.rerun()

    # Compact controls make the dashboard easier to scan and tune.
    ctl1, ctl2, ctl3 = st.columns([1.2, 1, 1])
    with ctl1:
        focus_metric = st.selectbox(
            "Focus metric",
            ["Cholera", "Malaria", "News signal"],
            help="Highlights the selected area for quick review.",
        )
    with ctl2:
        trend_days = st.slider("Trend window (days)", 7, 30, 14)
    with ctl3:
        quick_mode = st.toggle("Quick mode", value=True, help="Skips heavy visual blocks for faster loading.")

    metric_order = [
        ("🌊 Cholera – Africa (simulated)", f"{int(realtime_data['cholera_cases']):,}", f"+{random.randint(800, 2500)} vs last week"),
        ("🦟 Malaria – Uganda cases (est.)", f"{int(realtime_data['malaria_ug_cases_est']):,}", "High transmission context"),
        ("🌍 Affected countries (sim.)", realtime_data["affected_countries"], "Multi-country outbreak"),
        ("📰 Health news (24h, sim./GDELT)", f"{realtime_data['news_mentions']:,}", "Signal volume"),
    ]
    if focus_metric == "Malaria":
        metric_order = [metric_order[1], metric_order[0], metric_order[2], metric_order[3]]
    elif focus_metric == "News signal":
        metric_order = [metric_order[3], metric_order[0], metric_order[1], metric_order[2]]

    col1, col2, col3, col4 = st.columns(4)
    for col, card in zip([col1, col2, col3, col4], metric_order):
        with col:
            st.metric(card[0], card[1], card[2])

    left, right = st.columns([1.2, 1])
    with left:
        st.subheader("📈 Situation trends")
        dates, vals = make_trend_series(
            int(realtime_data["cholera_cases"]),
            days=trend_days,
            daily_step=350,
            noise=3000,
        )
        fig_cholera = px.line(
            x=dates,
            y=vals,
            title=f"Cholera trend ({trend_days}-day, simulated)",
            labels={"x": "Date", "y": "Cases"},
        )
        fig_cholera.update_traces(line_color="#f97316", line_width=3)
        fig_cholera.update_layout(
            hovermode="x unified",
            margin=dict(l=20, r=20, t=50, b=10),
            template="plotly_dark",
        )
        st.plotly_chart(fig_cholera, use_container_width=True)

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
                st.plotly_chart(fig_malaria, use_container_width=True)
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

        signal_score = min(100, 35 + int(realtime_data["news_mentions"]) // 80)
        st.progress(signal_score / 100)
        risk_level = "High" if signal_score >= 75 else ("Medium" if signal_score >= 55 else "Low")
        st.caption(f"Signal intensity score: {signal_score}/100 • Risk level: {risk_level}")
        if signal_score >= 75:
            st.warning("Escalation suggested: Increase daily district review cadence.")
        elif signal_score >= 55:
            st.info("Moderate watch: Keep active community surveillance and rapid reporting.")
        else:
            st.success("Baseline watch: Maintain routine monitoring protocols.")

        with st.expander("🗺️ Hotspots map", expanded=False):
            if FOLIUM_OK:
                m = folium.Map(location=[1.0, 32.0], zoom_start=6, tiles="CartoDB dark_matter")
                folium.Marker(
                    [2.5, 32.5],
                    popup="Northern Uganda – cholera risk (simulated)",
                    icon=folium.Icon(color="red"),
                ).add_to(m)
                folium.Marker(
                    [0.3, 32.5],
                    popup="Kampala – malaria surge (simulated)",
                    icon=folium.Icon(color="orange"),
                ).add_to(m)
                st_folium(m, width=620, height=420)
            else:
                st.info("Folium not installed. Run: pip install folium streamlit-folium")

# ---------------- DISEASE EXPLORER ----------------
elif nav == "Disease Profiler":
    render_disease_explorer()

# ---------------- REGION WATCH ----------------
elif nav == "Uganda Hotspots":
    render_region_watch()

# ---------------- FORECAST LAB ----------------
elif nav == "Forecast Lab":
    render_forecast_lab()

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
st.sidebar.caption("STI-OP decision support workspace")