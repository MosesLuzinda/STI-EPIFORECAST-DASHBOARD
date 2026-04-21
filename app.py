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

# Optional map support
try:
    import folium
    from streamlit_folium import st_folium
    FOLIUM_OK = True
except:
    FOLIUM_OK = False

# ---------------- PAGE CONFIG ----------------
st.set_page_config(page_title="STI-EPI-FORECAST | Uganda MoH", page_icon="🦠", layout="wide")

st.markdown("""
<style>
    .stApp {
        background:
            radial-gradient(circle at 15% 20%, rgba(34, 197, 94, 0.12), transparent 30%),
            radial-gradient(circle at 85% 10%, rgba(56, 189, 248, 0.10), transparent 35%),
            linear-gradient(135deg, #07080e 0%, #101427 50%, #0f1f36 100%);
        background-size: 120% 120%;
        animation: gradientFlow 16s ease-in-out infinite;
        color: white;
    }
    header[data-testid="stHeader"] {
        display: none !important;
    }
    .main { color: white; position: relative; z-index: 2; }
    .main::before, .main::after {
        content: "";
        position: fixed;
        width: 420px;
        height: 420px;
        border-radius: 999px;
        filter: blur(90px);
        z-index: 0;
        pointer-events: none;
    }
    .main::before {
        background: rgba(34, 197, 94, 0.16);
        left: -120px;
        top: 18%;
        animation: floatBlobA 18s ease-in-out infinite;
    }
    .main::after {
        background: rgba(59, 130, 246, 0.18);
        right: -140px;
        top: 62%;
        animation: floatBlobB 22s ease-in-out infinite;
    }
    @keyframes gradientFlow {
        0%, 100% { background-position: 0% 50%; }
        50% { background-position: 100% 50%; }
    }
    @keyframes floatBlobA {
        0%, 100% { transform: translate(0, 0); }
        50% { transform: translate(40px, -35px); }
    }
    @keyframes floatBlobB {
        0%, 100% { transform: translate(0, 0); }
        50% { transform: translate(-35px, 25px); }
    }
    .stButton > button {
        background: linear-gradient(45deg, #22c55e, #16a34a);
        color: white; border-radius: 12px; border: none;
        padding: 10px 20px; font-weight: 700;
        width: 100%;
        transition: all 0.2s ease;
        box-shadow: 0 6px 18px rgba(34, 197, 94, 0.22);
    }
    .stButton > button:hover {
        background: linear-gradient(45deg, #16a34a, #15803d);
        transform: translateY(-1px);
        box-shadow: 0 8px 24px rgba(34, 197, 94, 0.35);
    }
    .stButton > button:focus {
        outline: 2px solid #86efac !important;
        outline-offset: 2px;
    }
    .hero-card {
        background: linear-gradient(135deg, rgba(17,24,39,0.88), rgba(15,23,42,0.88));
        border: 1px solid rgba(34, 197, 94, 0.35);
        border-radius: 20px;
        padding: 24px;
        box-shadow: 0 10px 28px rgba(0,0,0,0.30);
        margin-bottom: 18px;
    }
    .feature-card {
        background: rgba(15, 23, 42, 0.75);
        border: 1px solid rgba(148, 163, 184, 0.25);
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
        border: 1px solid rgba(34, 197, 94, 0.45);
        background: rgba(34, 197, 94, 0.12);
        color: #bbf7d0;
        font-size: 0.88rem;
    }
    .status-panel {
        background: rgba(15, 23, 42, 0.7);
        border: 1px solid rgba(148, 163, 184, 0.28);
        border-radius: 14px;
        padding: 12px;
        margin: 8px 0 12px 0;
    }
    .insight-panel {
        background: rgba(15, 23, 42, 0.62);
        border: 1px solid rgba(56, 189, 248, 0.35);
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
        background: rgba(15, 23, 42, 0.7);
    }
    h1, h2, h3 {color: #ffffff; text-shadow: 0 2px 4px rgba(0,0,0,0.5);}
    .stMarkdown, .stMarkdown p, [data-testid="stMarkdownContainer"] p { color: #e8f1ff !important; }
    .stCaption, [data-testid="stCaption"] { color: #a5c7ff !important; font-weight: 500; }
    label, span[data-baseweb="tag"] { color: #dbeafe !important; }
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, rgba(2, 6, 23, 0.95) 0%, rgba(15, 23, 42, 0.95) 100%) !important;
        border-right: 1px solid rgba(148, 163, 184, 0.35);
    }
    [data-testid="stSidebar"] .stMarkdown,
    [data-testid="stSidebar"] .stMarkdown p,
    [data-testid="stSidebar"] p,
    [data-testid="stSidebar"] span,
    [data-testid="stSidebar"] label {
        color: #f8fafc !important;
        font-weight: 600;
    }
    [data-testid="stSidebar"] [data-testid="stCaption"] {
        color: #e2e8f0 !important;
        font-weight: 600 !important;
    }
    [data-testid="stSidebar"] [data-testid="stMetricValue"] {
        color: #fef08a !important;
    }
    [data-testid="stSidebar"] [data-testid="stMetricLabel"] {
        color: #bbf7d0 !important;
    }
    [data-testid="stSidebar"] .stRadio label,
    [data-testid="stSidebar"] .stSelectbox label {
        color: #ffffff !important;
    }
    [data-testid="stMetricValue"] { color: #fef9c3 !important; }
    [data-testid="stMetricLabel"] { color: #a7f3d0 !important; }
    @keyframes slideInUp {
        from { opacity: 0; transform: translateY(10px); }
        to { opacity: 1; transform: translateY(0); }
    }
    @keyframes slideInRight {
        from { opacity: 0; transform: translateX(18px); }
        to { opacity: 1; transform: translateX(0); }
    }
</style>
""", unsafe_allow_html=True)

# ---------------- SHARED UX HELPERS ----------------
def set_page(page_name: str):
    st.session_state["selected_nav"] = page_name
    st.rerun()


def nav_action_button(label: str, target_page: str, key: str):
    is_active = st.session_state.get("selected_nav") == target_page
    if st.button(label, key=key, disabled=is_active):
        set_page(target_page)


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

st.sidebar.title("🦠 STI-EPI-FORECAST")
st.sidebar.caption("Government-ready outbreak intelligence workspace")
st.sidebar.caption("Prepared for Ministry of Health - Republic of Uganda")

role_to_modules = {
    "National Incident Commander": ["Executive Briefing", "Dashboard", "Global Surveillance", "Uganda Hotspots", "Action Plan", "ROI & Financing"],
    "Surveillance Analyst": ["Global Surveillance", "Dashboard", "Uganda Hotspots", "Disease Profiler"],
    "Epidemiology Modeler": ["Forecast Lab", "Disease Profiler", "Uganda Hotspots", "Global Surveillance"],
    "Border Operations Lead": ["Executive Briefing", "Uganda Hotspots", "Global Surveillance", "Action Plan", "Forecast Lab"],
    "Policy & Investment Lead": ["Executive Briefing", "Action Plan", "ROI & Financing", "Dashboard"],
    "System Administrator": ["Dashboard", "Global Surveillance", "Admin"],
}
role_profiles = {
    "National Incident Commander": {
        "accent": "#ef4444",
        "mission": "Coordinate national response posture and escalation decisions.",
    },
    "Surveillance Analyst": {
        "accent": "#38bdf8",
        "mission": "Monitor signal quality, detect anomalies, and validate outbreak intelligence.",
    },
    "Epidemiology Modeler": {
        "accent": "#a78bfa",
        "mission": "Model disease trajectories and test intervention scenarios.",
    },
    "Border Operations Lead": {
        "accent": "#f59e0b",
        "mission": "Manage entry-point screening and cross-border risk controls.",
    },
    "Policy & Investment Lead": {
        "accent": "#22c55e",
        "mission": "Prioritize policy actions and budget allocation for response readiness.",
    },
    "System Administrator": {
        "accent": "#94a3b8",
        "mission": "Keep the intelligence platform stable, integrated, and available.",
    },
}
role = st.sidebar.selectbox("Role workspace", list(role_to_modules.keys()))
nav_options = role_to_modules[role]
if "selected_nav" not in st.session_state:
    st.session_state["selected_nav"] = nav_options[0]
if "sidebar_nav" not in st.session_state:
    st.session_state["sidebar_nav"] = nav_options[0]
if st.session_state["selected_nav"] not in nav_options:
    st.session_state["selected_nav"] = nav_options[0]
if st.session_state["sidebar_nav"] not in nav_options:
    st.session_state["sidebar_nav"] = nav_options[0]

def _on_sidebar_nav_change():
    st.session_state["selected_nav"] = st.session_state["sidebar_nav"]

default_idx = (
    nav_options.index(st.session_state["selected_nav"])
    if st.session_state["selected_nav"] in nav_options
    else 0
)
st.sidebar.radio("Navigation", nav_options, index=default_idx, key="sidebar_nav", on_change=_on_sidebar_nav_change)
nav = st.session_state["selected_nav"]

st.sidebar.divider()
if "last_manual_refresh" not in st.session_state:
    st.session_state["last_manual_refresh"] = datetime.now()

if st.sidebar.button("🔄 Refresh Live Feeds", key="refresh_live_feeds"):
    st.cache_data.clear()
    st.session_state["last_manual_refresh"] = datetime.now()
    st.rerun()

st.sidebar.caption("Outbreak and open-web snapshot refreshes every <=30s (cache). Malaria OWID refreshes hourly.")
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

st.sidebar.markdown("#### Feed controls")
fc1, fc2 = st.sidebar.columns(2)
with fc1:
    if st.button("Retry Malaria", key="retry_malaria"):
        increment_feed_retry("malaria")
        st.session_state["retry_request"] = "malaria"
        st.session_state["last_manual_refresh"] = datetime.now()
        st.rerun()
    if st.button("Retry Outbreak", key="retry_outbreak"):
        increment_feed_retry("outbreak")
        st.session_state["retry_request"] = "outbreak"
        st.session_state["last_manual_refresh"] = datetime.now()
        st.rerun()
with fc2:
    st.caption("Global feed retry not required")

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

st.sidebar.markdown("#### Quick actions")
qa1, qa2 = st.sidebar.columns(2)
with qa1:
    if "Dashboard" in nav_options:
        nav_action_button("📊 Dashboard", "Dashboard", "qa_dash")
    if "Executive Briefing" in nav_options:
        nav_action_button("🧭 Briefing", "Executive Briefing", "qa_brief")
with qa2:
    if "Forecast Lab" in nav_options:
        nav_action_button("🔮 Forecast", "Forecast Lab", "qa_forecast")
    if "Global Surveillance" in nav_options:
        nav_action_button("🌐 Global", "Global Surveillance", "qa_global")

if nav == "Action Plan":
    render_sidebar_social_action_plan(realtime_data)

st.sidebar.info("📡 Decision modules: surveillance, hotspot monitoring, forecasting, and response planning.")

try:
    frag = getattr(st, "fragment", None)
    if callable(frag):

        @frag(run_every=timedelta(seconds=20))
        def _sidebar_live_tick():
            # Fragment must not use st.sidebar.*; invoke this function inside `with st.sidebar:`.
            st.caption(f"Live UI tick: {datetime.now().strftime('%H:%M:%S')} (partial refresh)")

        with st.sidebar:
            _sidebar_live_tick()
except Exception:
    pass

# ---------------- ROLE CONTEXT ----------------
role_mission = role_profiles[role]["mission"]
handoff_text = f"Current module: {nav}. Next recommended module: {nav_options[min(len(nav_options)-1, (nav_options.index(nav)+1) if nav in nav_options else 0)]}."
st.markdown(f"#### {role}")
st.caption(role_mission)
st.caption(f"Workflow handoff — {handoff_text}")
st.caption("Use this role view to prepare briefing-ready outputs for Cabinet, MoH leadership, and district command teams.")

# ---------------- HELPERS ----------------
def make_trend_series(base_value: int, days: int = 14, daily_step: int = 300, noise: int = 3000):
    dates = pd.date_range(end=datetime.now(), periods=days)
    vals = [base_value - random.randint(noise, noise * 2) + i * daily_step for i in range(days)]
    return dates, vals

# ---------------- DASHBOARD ----------------
if nav == "Executive Briefing":
    render_executive_brief(realtime_data)

elif nav == "Dashboard":
    st.title("🌍 National Outbreak Operations Dashboard")
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

# ---------------- ROI & FINANCING ----------------
elif nav == "ROI & Financing":
    render_roi_financing()

# ---------------- FOOTER ----------------
st.sidebar.markdown("---")
st.sidebar.caption("✅ STI-EPI-FORECAST • Role-based outbreak intelligence workspace")