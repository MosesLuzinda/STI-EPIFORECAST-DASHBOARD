import random

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from data_services import (
    analyze_outbreak_risk,
    build_admin_update_message,
    generate_ai_nlp_alerts,
    load_admin_alert_config,
    save_admin_alert_config,
    send_admin_email,
)


UGANDA_TRAVEL_POINTS = {
    "Entebbe Airport": 0.72,
    "Malaba Border": 0.81,
    "Mpondwe Border": 0.76,
    "Elegu Border": 0.63,
}


def _risk_level(score: float):
    if score >= 0.75:
        return "High", "#ef4444"
    if score >= 0.5:
        return "Medium", "#f59e0b"
    return "Low", "#22c55e"


def _selected_disease():
    default_disease = st.session_state.get("policy_disease", "Cholera")
    disease = st.selectbox(
        "Disease focus",
        ["Cholera", "Malaria", "Typhoid", "Marburg"],
        index=["Cholera", "Malaria", "Typhoid", "Marburg"].index(default_disease),
        key="disease_focus_select",
    )
    st.session_state["policy_disease"] = disease
    return disease


def render_disease_explorer():
    st.title("🔬 Disease Profiler (Epidemiology)")
    disease = _selected_disease()
    st.caption("Host profile, age-risk profile, and climate sensitivity are simulated for rapid planning.")

    host_profiles = {
        "Cholera": {"Humans": 85, "Animals": 10, "Birds": 5},
        "Malaria": {"Humans": 72, "Animals": 22, "Birds": 6},
        "Typhoid": {"Humans": 90, "Animals": 8, "Birds": 2},
        "Marburg": {"Humans": 45, "Animals": 50, "Birds": 5},
    }
    age_profiles = {
        "Cholera": [22, 25, 18, 22, 13],
        "Malaria": [38, 30, 12, 14, 6],
        "Typhoid": [14, 26, 29, 21, 10],
        "Marburg": [7, 15, 28, 32, 18],
    }
    climate_amplifier = {"Cholera": 1.15, "Malaria": 1.28, "Typhoid": 1.08, "Marburg": 1.12}

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Host Origin (Donut)")
        df_host = pd.DataFrame(
            {"Host": list(host_profiles[disease].keys()), "Share": list(host_profiles[disease].values())}
        )
        fig_host = px.pie(df_host, names="Host", values="Share", hole=0.62, title=f"{disease} host signal mix")
        fig_host.update_layout(template="plotly_dark")
        st.plotly_chart(fig_host, use_container_width=True)

    with c2:
        st.subheader("Age Vulnerability (Bar)")
        age_groups = ["0-4", "5-14", "15-24", "25-49", "50+"]
        df_age = pd.DataFrame({"Age Group": age_groups, "Risk Index": age_profiles[disease]})
        fig_age = px.bar(df_age, x="Age Group", y="Risk Index", color="Risk Index", title=f"{disease} age-risk index")
        fig_age.update_layout(template="plotly_dark")
        st.plotly_chart(fig_age, use_container_width=True)

    st.subheader("Environment Sensitivity (Line)")
    temps = np.arange(16, 37, 1)
    baseline = np.clip((temps - 16) * 2.2, 1, None)
    env_risk = baseline * climate_amplifier[disease]
    df_env = pd.DataFrame({"Temperature C": temps, "Spread Potential": env_risk})
    fig_env = px.line(
        df_env,
        x="Temperature C",
        y="Spread Potential",
        markers=True,
        title=f"{disease}: effect of temperature on spread potential",
    )
    fig_env.update_traces(line_width=3, line_color="#22c55e")
    fig_env.update_layout(template="plotly_dark")
    st.plotly_chart(fig_env, use_container_width=True)


def render_region_watch():
    st.title("📍 Uganda Vulnerability Map (Hotspots & Risk)")
    disease = _selected_disease()
    districts = [
        ("Kampala", 0.72),
        ("Wakiso", 0.64),
        ("Gulu", 0.58),
        ("Arua", 0.61),
        ("Mbale", 0.49),
        ("Kasese", 0.68),
        ("Mbarara", 0.45),
        ("Lira", 0.53),
    ]
    disease_scale = {"Cholera": 1.18, "Malaria": 1.10, "Typhoid": 0.96, "Marburg": 1.26}

    records = []
    for district, base_risk in districts:
        risk = min(0.98, base_risk * disease_scale[disease] + random.uniform(-0.05, 0.07))
        records.append(
            {
                "District": district,
                "RiskScore": round(risk, 2),
                "RiskLabel": "High" if risk > 0.7 else ("Medium" if risk > 0.5 else "Low"),
                "Estimated Cases (14d)": int(500 + risk * 2800),
                "Trend": random.choice(["Rising", "Stable", "Falling"]),
            }
        )
    df_risk = pd.DataFrame(records).sort_values("RiskScore", ascending=False)

    c1, c2 = st.columns([1.2, 1.8])
    with c1:
        st.metric("Districts in high risk", int((df_risk["RiskLabel"] == "High").sum()))
        st.metric("Highest risk district", df_risk.iloc[0]["District"])
        st.metric("Max risk score", f"{df_risk.iloc[0]['RiskScore']:.2f}")
    with c2:
        fig_hotspot = px.bar(
            df_risk,
            x="District",
            y="RiskScore",
            color="RiskLabel",
            title=f"{disease} hotspot risk by district (UBOS shapefile-ready prototype)",
            color_discrete_map={"High": "#ef4444", "Medium": "#f59e0b", "Low": "#22c55e"},
        )
        fig_hotspot.update_layout(template="plotly_dark")
        st.plotly_chart(fig_hotspot, use_container_width=True)

    st.dataframe(df_risk, use_container_width=True)


def render_forecast_lab():
    st.title("🔮 Uganda Vulnerability (SEIR + ML Signal)")
    disease = _selected_disease()

    population = st.number_input("Total population", min_value=1_000_000, max_value=80_000_000, value=48_000_000, step=1_000_000)
    initial_infected = st.number_input("Initial infected", min_value=100, max_value=400_000, value=12000, step=100)
    days = st.slider("Forecast horizon", 30, 100, 100)
    intervention = st.slider("Intervention effectiveness", 0.0, 0.9, 0.35, 0.01)

    base_beta = {"Cholera": 0.36, "Malaria": 0.31, "Typhoid": 0.27, "Marburg": 0.44}[disease]
    beta = base_beta * (1.0 - intervention)
    sigma = 1 / 5.2
    gamma = 1 / 8.5

    S = np.zeros(days + 1)
    E = np.zeros(days + 1)
    I = np.zeros(days + 1)
    R = np.zeros(days + 1)
    S[0] = population - initial_infected
    I[0] = initial_infected
    E[0] = initial_infected * 0.45
    R[0] = 0

    for day in range(days):
        new_exposed = beta * S[day] * I[day] / population
        new_infectious = sigma * E[day]
        recovered = gamma * I[day]
        S[day + 1] = max(0, S[day] - new_exposed)
        E[day + 1] = max(0, E[day] + new_exposed - new_infectious)
        I[day + 1] = max(0, I[day] + new_infectious - recovered)
        R[day + 1] = max(0, R[day] + recovered)

    curve = pd.DataFrame(
        {
            "Day": np.arange(days + 1),
            "Susceptible": S.astype(int),
            "Exposed": E.astype(int),
            "Infected": I.astype(int),
            "Recovered": R.astype(int),
        }
    )
    fig_curve = go.Figure()
    for metric, color in [
        ("Susceptible", "#60a5fa"),
        ("Exposed", "#f59e0b"),
        ("Infected", "#ef4444"),
        ("Recovered", "#22c55e"),
    ]:
        fig_curve.add_trace(go.Scatter(x=curve["Day"], y=curve[metric], name=metric, line=dict(width=3, color=color)))
    fig_curve.update_layout(
        title=f"{disease} SEIR projection for Uganda (100-day planning curve)",
        xaxis_title="Days",
        yaxis_title="People",
        template="plotly_dark",
        hovermode="x unified",
        transition={"duration": 450, "easing": "cubic-in-out"},
    )
    st.plotly_chart(fig_curve, use_container_width=True)

    st.subheader("Travel Risk (Borders & Airport)")
    travel_df = pd.DataFrame(
        {
            "Entry Point": list(UGANDA_TRAVEL_POINTS.keys()),
            "Risk Score": [min(0.99, max(0.05, score * (0.9 + beta))) for score in UGANDA_TRAVEL_POINTS.values()],
        }
    )
    fig_travel = px.bar(
        travel_df,
        x="Entry Point",
        y="Risk Score",
        color="Risk Score",
        color_continuous_scale="Reds",
        title="Entebbe, Malaba, Mpondwe, and Elegu travel corridor risk",
    )
    fig_travel.update_layout(template="plotly_dark")
    st.plotly_chart(fig_travel, use_container_width=True)

    st.subheader("Statistical Normal Baseline")
    daily_new = np.diff(np.maximum(I, 0))
    baseline_series = daily_new[-30:] if len(daily_new) >= 30 else daily_new
    mu = float(np.mean(baseline_series)) if len(baseline_series) > 0 else 0.0
    sigma = float(np.std(baseline_series)) if len(baseline_series) > 0 else 1.0
    sigma = sigma if sigma > 0 else 1.0

    x = np.linspace(mu - 3 * sigma, mu + 3 * sigma, 160)
    pdf = (1.0 / (sigma * np.sqrt(2 * np.pi))) * np.exp(-0.5 * ((x - mu) / sigma) ** 2)
    df_norm = pd.DataFrame({"x": x, "pdf": pdf})
    fig_norm = go.Figure()
    fig_norm.add_trace(
        go.Histogram(
            x=baseline_series,
            nbinsx=20,
            histnorm="probability density",
            marker_color="#60a5fa",
            opacity=0.5,
            name="Observed distribution",
        )
    )
    fig_norm.add_trace(
        go.Scatter(
            x=df_norm["x"],
            y=df_norm["pdf"],
            mode="lines",
            line=dict(color="#f43f5e", width=3),
            name="Normal fit",
        )
    )
    fig_norm.update_layout(
        title="Daily new infections vs normal distribution baseline",
        xaxis_title="Daily new infections",
        yaxis_title="Density",
        template="plotly_dark",
        legend_title="Statistical legend",
    )
    st.plotly_chart(fig_norm, use_container_width=True)
    st.caption(
        f"Normal baseline summary: mean={mu:,.0f}, std-dev={sigma:,.0f}. "
        "Use this to detect abnormal surge behavior beyond expected variation."
    )

    st.subheader("Machine Learning Signal (Random Forest placeholder)")
    ml_probability = min(0.98, max(0.05, (I[-1] / max(1, population * 0.01)) * 0.65 + random.uniform(0.08, 0.2)))
    st.metric("Random Forest Outbreak Probability", f"{ml_probability * 100:.1f}%")
    ml_label, _ = _risk_level(ml_probability)
    st.caption(f"Current ML risk category: {ml_label}")
    st.caption("Prototype uses a synthetic score. Replace with trained model (e.g., sklearn RandomForest) using historical district records.")


def render_learning_hub():
    st.title("📚 Learning Hub")
    st.markdown("#### Data sources in this prototype")
    st.markdown(
        "- **Malaria death rate (Uganda)**: Our World in Data dataset, derived from WHO and partners.[web:61][web:54]\n"
        "- **Optional OWID health datasets**: additional country time series can be wired from OWID CSV endpoints.[web:91]\n"
        "- **Cholera & some KPIs**: simulated values based on plausible outbreak magnitudes, not official.\n"
        "- **HealthMap iframe**: external real-time map of infectious disease signals.[web:57][web:60]"
    )
    st.markdown("#### How to go fully real for STI‑FORECAST")
    st.markdown(
        "- Connect to MoH / DHIS2 APIs or CSV exports for district-level data.[web:73]\n"
        "- Use WHO GHO API for official cholera and malaria indicators.[web:90]\n"
        "- Store data in PostgreSQL and feed this dashboard from your own ETL."
    )


def _social_df_from_realtime(realtime_data: dict) -> pd.DataFrame:
    ch = realtime_data.get("social_channels") or {}
    return pd.DataFrame({"Channel": list(ch.keys()), "Volume (24h est.)": list(ch.values())})


def render_sidebar_social_action_plan(realtime_data: dict):
    """Compact social + simulation strip for sidebar when Action Plan is active."""
    disease = st.session_state.get("policy_disease", "Cholera")
    st.sidebar.markdown("#### Social & open-web monitor")
    st.sidebar.caption(realtime_data.get("social_sources_note", ""))
    st.sidebar.metric("Composite urgency", f"{realtime_data.get('social_urgency_score', 0)}/100")
    st.sidebar.metric("Sentiment index", f"{realtime_data.get('social_sentiment_index', 0):.2f}", help="Simulated −1 negative … +1 positive")
    st.sidebar.metric("Response tier", realtime_data.get("sim_recommended_tier", "Routine"))
    df = _social_df_from_realtime(realtime_data)
    fig = px.bar(
        df,
        x="Channel",
        y="Volume (24h est.)",
        color="Channel",
        title=f"Open-web + proxy channels ({disease})",
        color_discrete_sequence=px.colors.qualitative.Bold,
    )
    fig.update_layout(template="plotly_dark", height=260, margin=dict(t=36, b=40), showlegend=False)
    st.sidebar.plotly_chart(fig, use_container_width=True)


def render_alerts_and_recommendations(realtime_data: dict):
    st.title("🚨 Uganda Action Plan (Control & Invest)")
    disease = _selected_disease()

    tab_ops, tab_social, tab_sim = st.tabs(["Operations", "Social & open web", "Measures & scenarios"])
    with tab_ops:
        _render_action_plan_operations(disease)
    with tab_social:
        _render_action_plan_social(disease, realtime_data)
    with tab_sim:
        _render_action_plan_simulations(disease, realtime_data)


def _render_action_plan_operations(disease: str):
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Priority-1 alerts", "2", "Immediate review required")
    with c2:
        st.metric("High-risk districts", "6", "Resource surge recommended")
    with c3:
        st.metric("Response window", "24-72h", "Critical decision period")

    st.error(f"P1 • {disease} risk rising across key surveillance zones and travel corridors.")
    st.warning("P2 • Vulnerable districts require immediate procurement and diagnostics reinforcement.")
    st.info("P3 • Surveillance quality variance detected between districts (simulated monitoring signal).")

    action_map = {
        "Cholera": {
            "buy": "ORS, IV fluids, chlorine tabs, rapid cholera tests",
            "prevent": "WASH campaigns, water testing, cholera vaccination",
            "invest": "District water labs and UVRI cholera sequencing support",
        },
        "Malaria": {
            "buy": "ACTs, RDT kits, LLINs, indoor residual spray stocks",
            "prevent": "Mosquito control operations and CHW fever-screening sweeps",
            "invest": "Entomology labs and district vector-surveillance systems",
        },
        "Typhoid": {
            "buy": "Typhoid conjugate vaccines, antibiotics, lab reagents",
            "prevent": "Food-water hygiene enforcement and school sanitation checks",
            "invest": "Microbiology diagnostics hubs in referral hospitals",
        },
        "Marburg": {
            "buy": "PPE kits, PCR reagents, isolation ward consumables",
            "prevent": "IPC drills, rapid contact tracing, burial protocol training",
            "invest": "High-biosafety containment and UVRI emergency diagnostics",
        },
    }
    plan = action_map[disease]

    st.markdown("### Recommended operational actions")
    st.success(f"**Procurement now:** {plan['buy']}")
    st.info(f"**Prevention now:** {plan['prevent']}")
    st.warning(f"**Strategic investment:** {plan['invest']}")

    a1, a2 = st.columns(2)
    with a1:
        st.markdown(
            "- Activate district rapid response teams in identified hotspots.\n"
            "- Increase WASH and oral cholera vaccination micro-planning.\n"
            "- Escalate case verification and line-listing for the next 72 hours.\n"
            "- Pre-position treatment commodities in referral centers."
        )
    with a2:
        st.markdown(
            "- Intensify LLIN and IRS targeting for high-transmission malaria zones.\n"
            "- Strengthen community health worker reporting cadence (daily).\n"
            "- Run synchronized risk communication through district channels.\n"
            "- Trigger weekly command-center review until signal normalizes."
        )

    st.markdown("### 72-hour action checklist")
    st.checkbox("Deploy field verification teams", key="alert_task_verify")
    st.checkbox("Update district preparedness status board", key="alert_task_board")
    st.checkbox("Send daily escalation brief to leadership", key="alert_task_brief")
    st.checkbox("Validate medicine and logistics buffer stock", key="alert_task_stock")


def _render_action_plan_social(disease: str, realtime_data: dict):
    st.subheader("What the dashboard is watching (social layer)")
    st.caption(
        "News / open web: GDELT (articles, 24h), Reddit public JSON search, Hacker News via Algolia. "
        "Set NEWSAPI_KEY for NewsAPI totals. Native X/Meta/TikTok feeds are not queried without their APIs."
    )
    df = _social_df_from_realtime(realtime_data)
    c1, c2 = st.columns([1.2, 1])
    with c1:
        fig_bar = px.bar(
            df,
            x="Channel",
            y="Volume (24h est.)",
            color="Volume (24h est.)",
            color_continuous_scale="Turbo",
            title=f"Live open-web attention by channel — {disease}",
        )
        fig_bar.update_layout(template="plotly_dark", height=380)
        st.plotly_chart(fig_bar, use_container_width=True)
    with c2:
        hours = list(range(24))[::-1]
        base = int(realtime_data.get("social_urgency_score", 50))
        trend = [max(5, min(98, base + random.randint(-8, 8) - i)) for i in range(24)]
        fig_line = px.line(
            x=hours,
            y=trend,
            markers=True,
            title="Simulated social urgency (last 24 hourly ticks)",
            labels={"x": "Hours ago", "y": "Urgency score"},
        )
        fig_line.update_traces(line_color="#f472b6", line_width=3)
        fig_line.update_layout(template="plotly_dark", height=380)
        st.plotly_chart(fig_line, use_container_width=True)
    m1, m2, m3 = st.columns(3)
    with m1:
        st.metric("GDELT / news signal", f"{realtime_data.get('news_mentions', 0):,}")
    with m2:
        st.metric("Simulated sentiment", f"{realtime_data.get('social_sentiment_index', 0):.2f}")
    with m3:
        st.metric("Sim. response tier", realtime_data.get("sim_recommended_tier", "Routine"))


def _render_action_plan_simulations(disease: str, realtime_data: dict):
    st.subheader("Scenario lab — what measures to take (simulation)")
    urgency = int(realtime_data.get("social_urgency_score", 40))
    surge = st.slider("Simulated surge intensity", 0, 100, min(urgency, 95), help="Raises synthetic load on response levers.")
    coverage = st.slider("Simulated intervention coverage %", 10, 95, 45)
    leak = st.slider("Simulated border screening gap %", 0, 40, 12)

    risk_raw = surge * 0.45 + leak * 1.1 - coverage * 0.35 + random.uniform(-5, 8)
    residual_risk = max(5, min(95, risk_raw))
    st.metric("Residual outbreak pressure (sim.)", f"{residual_risk:.0f}/100")

    scen = pd.DataFrame(
        {
            "Lever": ["Lab surge", "WASH push", "Risk comms", "Border checks", "Vaccine push"],
            "Impact if funded (sim.)": [
                max(0, 72 - surge * 0.35 + coverage * 0.2),
                max(0, 65 - surge * 0.25 + coverage * 0.25),
                max(0, 58 - leak * 0.8 + coverage * 0.15),
                max(0, 80 - leak * 1.2 + coverage * 0.1),
                max(0, 50 - surge * 0.15 + coverage * 0.3),
            ],
        }
    )
    fig = px.bar(scen, x="Lever", y="Impact if funded (sim.)", color="Impact if funded (sim.)", color_continuous_scale="Viridis")
    fig.update_layout(template="plotly_dark", title=f"Where to push next — {disease} (illustrative)")
    st.plotly_chart(fig, use_container_width=True)

    if residual_risk >= 70:
        st.error("Simulation: **Surge posture** — accelerate procurement, daily command briefs, border tightening.")
    elif residual_risk >= 45:
        st.warning("Simulation: **Elevated posture** — verify stocks, intensify surveillance, pre-position teams.")
    else:
        st.success("Simulation: **Routine posture** — maintain monitoring and scheduled reviews.")

    st.caption("All scenario numbers are synthetic for planning drills; replace with calibrated models from your data.")


def render_admin():
    st.title("⚙️ Administration and Governance")
    st.info("Platform configuration, governance controls, and integration status for production readiness.")
    st.markdown("#### Current integrations")
    st.write(
        "- Real malaria death-rate time series from Our World in Data (Uganda).[web:61][web:54]\n"
        "- Open-web signal ingestion from GDELT, Reddit public search, and Hacker News Algolia.\n"
        "- Optional NewsAPI enrichment when NEWSAPI_KEY is configured.\n"
        "- Scenario modeling layer for planning and training exercises."
    )
    st.markdown("#### Next integration targets")
    st.write(
        "- WHO GHO OData API for cholera cases.[web:90]\n"
        "- World Malaria Report 2025 indicators for consistency.[web:63]\n"
        "- MoH Uganda (DHIS2) API or CSV for district-level case data.[web:73]"
    )

    st.markdown("#### Admin risk email routing")
    cfg = load_admin_alert_config()
    enabled = st.toggle("Enable daily + emergency risk emails", value=bool(cfg.get("enabled", False)))
    daily_hour = st.slider("Daily summary hour (UTC)", min_value=0, max_value=23, value=int(cfg.get("daily_hour_utc", 6)))
    risk_threshold = st.slider(
        "Emergency trigger threshold (risk /100)",
        min_value=50,
        max_value=95,
        value=int(cfg.get("risk_threshold", 72)),
    )
    recipients_text = st.text_area(
        "Recipients (one email per line)",
        value="\n".join(cfg.get("recipients", [])),
        help="These contacts receive daily updates and emergency outbreak alerts.",
    )
    recipients = [line.strip() for line in recipients_text.splitlines() if line.strip()]
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Save alert settings", key="save_admin_alerts"):
            cfg["enabled"] = enabled
            cfg["daily_hour_utc"] = int(daily_hour)
            cfg["risk_threshold"] = int(risk_threshold)
            cfg["recipients"] = recipients
            save_admin_alert_config(cfg)
            st.success("Alert settings saved.")
    with c2:
        if st.button("Send test email now", key="send_test_admin_email"):
            test_data = st.session_state.get("feed_snapshots", {}).get("outbreak", {})
            if not test_data:
                st.warning("No outbreak snapshot yet. Visit Dashboard first, then retry.")
            elif not recipients:
                st.warning("Add at least one recipient email first.")
            else:
                risk = analyze_outbreak_risk(test_data)
                body = build_admin_update_message(test_data, risk)
                ok, msg = send_admin_email(
                    subject=f"[Test] STI-EPI-FORECAST {risk['risk_level']} risk bulletin",
                    body_text=body,
                    recipients=recipients,
                )
                if ok:
                    st.success("Test email sent.")
                else:
                    st.error(f"Test email failed: {msg}")
    st.caption(
        "SMTP env vars required: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, ALERT_FROM_EMAIL. "
        "Emergency emails are triggered when computed risk exceeds threshold."
    )


def render_global_view(realtime_data):
    st.title("🌐 Global Surveillance (News + Social Signals)")
    st.caption(
        "GDELT, Reddit, and Hacker News (Algolia) return real 24h counts when reachable; "
        "NewsAPI activates with NEWSAPI_KEY. Choropleth values remain illustrative until district case feeds are connected."
    )

    tab1, tab2, tab3 = st.tabs(["Global Heatmap", "NLP Alerts", "Source Monitor"])

    with tab1:
        countries = [
            {"iso_code": "UGA", "location": "Uganda"},
            {"iso_code": "KEN", "location": "Kenya"},
            {"iso_code": "TZA", "location": "Tanzania"},
            {"iso_code": "RWA", "location": "Rwanda"},
            {"iso_code": "ETH", "location": "Ethiopia"},
            {"iso_code": "COD", "location": "DR Congo"},
            {"iso_code": "ZMB", "location": "Zambia"},
            {"iso_code": "MWI", "location": "Malawi"},
        ]
        base = int(realtime_data.get("cholera_cases", 38000))
        df_cholera = pd.DataFrame(countries)
        weights = [0.25, 0.14, 0.12, 0.08, 0.13, 0.10, 0.10, 0.08]
        df_cholera["cholera_cases_sim"] = [int(base * w) for w in weights]

        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("Estimated outbreak mentions", f"{df_cholera['cholera_cases_sim'].sum():,}")
        with c2:
            st.metric("Countries in watchlist", df_cholera.shape[0])
        with c3:
            st.metric("Signal mentions (24h)", f"{int(realtime_data.get('news_mentions', 0)):,}")

        fig_cholera = px.choropleth(
            df_cholera,
            locations="iso_code",
            color="cholera_cases_sim",
            hover_name="location",
            color_continuous_scale="YlOrRd",
            title="Global outbreak discussion heatmap (illustrative intensity view)",
        )
        fig_cholera.update_layout(
            legend_title_text="Outbreak discussion intensity",
            transition={"duration": 420, "easing": "cubic-in-out"},
        )
        st.plotly_chart(fig_cholera, use_container_width=True)

    with tab2:
        disease = st.session_state.get("policy_disease", "Cholera")
        st.subheader("AI Risk Intelligence Feed")
        alert_key = (
            disease,
            int(realtime_data.get("news_mentions", 0)),
            int(realtime_data.get("cholera_cases", 0)),
            int(realtime_data.get("affected_countries", 0)),
        )
        if "cached_nlp_alerts" not in st.session_state:
            st.session_state["cached_nlp_alerts"] = {}
        refresh_ai = st.button("Refresh AI Alerts", key="refresh_ai_alerts_btn")
        if refresh_ai or alert_key not in st.session_state["cached_nlp_alerts"]:
            st.session_state["cached_nlp_alerts"][alert_key] = generate_ai_nlp_alerts(
                disease=disease,
                news_mentions=alert_key[1],
                cholera_cases=alert_key[2],
                affected_countries=alert_key[3],
            )
        nlp_alerts, source = st.session_state["cached_nlp_alerts"][alert_key]
        if source == "ai":
            st.caption("Source: AI API (OpenAI-compatible provider configured from environment variables)")
        else:
            st.caption(
                "Source: fallback rules — configure CURSOR_API_KEY + CURSOR_API_BASE_URL (or AI_* / OPENAI_*) "
                "or run the local FastAPI /v1/nlp-alerts endpoint."
            )
        for alert in nlp_alerts:
            st.warning(alert)
        st.markdown(
            "**Legend:** 🔴 High urgency NLP alert • 🟠 Elevated watch • 🟢 Routine monitoring",
        )
        st.caption("Future enrichment: GDELT/NewsAPI ingestion + HuggingFace NER/geocoding + district geotagging.")

    with tab3:
        st.subheader("Feed Quality and Freshness")
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("Signal mentions (24h)", f"{int(realtime_data.get('news_mentions', 0)):,}")
        with c2:
            st.metric("Countries in active watch", int(realtime_data.get("affected_countries", 0)))
        with c3:
            st.metric("Feed update time", realtime_data.get("last_updated", "n/a"))

        st.markdown("#### Operational data status")
        st.success("Outbreak signal engine: online")
        if realtime_data.get("gdelt_ok"):
            st.success("GDELT: online")
        else:
            st.warning("GDELT: unavailable (baseline news estimate)")
        if realtime_data.get("reddit_ok"):
            st.success("Reddit public search: online")
        else:
            st.warning("Reddit public search: unavailable")
        if realtime_data.get("hackernews_ok"):
            st.success("Hacker News (Algolia): online")
        else:
            st.warning("Hacker News (Algolia): unavailable")
        if realtime_data.get("newsapi_ok"):
            st.success("NewsAPI: online (key present)")
        else:
            st.info("NewsAPI: optional (set NEWSAPI_KEY for headline volume)")
        st.info("AI extraction: POST /v1/nlp-alerts or direct OpenAI-compatible chat from env keys.")


def render_executive_brief(realtime_data):
    st.title("🧭 Executive Briefing")
    st.caption("One-screen summary for senior decision makers: status, priorities, and immediate actions.")

    signal_score = min(100, 35 + int(realtime_data["news_mentions"]) // 80)
    outbreak_risk = min(0.98, signal_score / 100)
    risk_label, _ = _risk_level(outbreak_risk)

    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.metric("Overall risk level", risk_label)
    with k2:
        st.metric("Signal intensity", f"{signal_score}/100")
    with k3:
        st.metric("Countries under watch", int(realtime_data.get("affected_countries", 0)))
    with k4:
        st.metric("Update time", realtime_data.get("last_updated", "n/a"))

    st.info(
        f"**National posture:** {risk_label} risk. "
        f"Maintain daily incident command review and district-level escalation checks."
    )

    left, right = st.columns([1.3, 1])
    with left:
        st.subheader("Incident Timeline (Last 7 Days)")
        timeline = pd.DataFrame(
            [
                {"Day": "D-6", "Event": "Signal growth detected in regional media", "Priority": "Medium"},
                {"Day": "D-5", "Event": "Border-adjacent district chatter increased", "Priority": "High"},
                {"Day": "D-3", "Event": "Rapid review triggered for surveillance team", "Priority": "High"},
                {"Day": "D-2", "Event": "Commodity check initiated for treatment stocks", "Priority": "Medium"},
                {"Day": "D-1", "Event": "Situation brief prepared for leadership", "Priority": "Low"},
                {"Day": "Today", "Event": "Action plan refreshed with current disease profile", "Priority": risk_label},
            ]
        )
        st.dataframe(timeline, use_container_width=True, hide_index=True)

    with right:
        st.subheader("Decision Actions (24-72h)")
        st.error("P1 • Confirm hotspot districts and activate response leads.")
        st.warning("P2 • Verify procurement buffer for diagnostics and therapeutics.")
        st.info("P3 • Publish synchronized risk communication guidance.")
        st.markdown("#### Governance checks")
        st.checkbox("Incident command meeting scheduled", key="exec_meeting")
        st.checkbox("Border screening protocol reviewed", key="exec_border")
        st.checkbox("District stock report validated", key="exec_stock")


def render_roi_financing():
    st.title("💰 ROI of Pandemic & Health Investments – Uganda (illustrative)")
    st.markdown(
        "This page uses simple health economics logic to estimate the **economic return** on "
        "government investments in epidemic preparedness and health programs. "
        "Numbers below are **illustrative**, not official MoH values.[web:104][web:105]"
    )

    col_in1, col_in2, col_in3 = st.columns(3)
    with col_in1:
        gov_invest = st.number_input(
            "Gov. annual investment in preparedness (USD)",
            min_value=1_000_000,
            max_value=1_000_000_000,
            value=50_000_000,
            step=1_000_000,
        )
    with col_in2:
        avoided_outbreak_cost = st.number_input(
            "Estimated annual avoided losses (USD)",
            min_value=10_000_000,
            max_value=10_000_000_000,
            value=800_000_000,
            step=10_000_000,
        )
    with col_in3:
        time_horizon = st.number_input("Time horizon (years)", min_value=1, max_value=30, value=10, step=1)

    total_invest = gov_invest * time_horizon
    total_benefit = avoided_outbreak_cost * time_horizon
    net_benefit = total_benefit - total_invest
    roi_ratio = total_benefit / total_invest if total_invest > 0 else 0
    roi_percent = (roi_ratio - 1) * 100 if roi_ratio > 0 else 0

    st.markdown("### 📊 ROI summary (illustrative)")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Total investment", f"${total_invest:,.0f}")
    with c2:
        st.metric("Total benefit", f"${total_benefit:,.0f}")
    with c3:
        st.metric("Net benefit", f"${net_benefit:,.0f}")
    with c4:
        st.metric("ROI multiple", f"{roi_ratio:,.1f}x")
    st.caption(
        "Many immunization and preparedness studies estimate ROI > 10x in low- and middle-income settings.[web:104][web:105]"
    )

    st.markdown("### 🧱 Aggregate costs vs benefits")
    df_roi = pd.DataFrame({"Category": ["Total investment", "Total economic benefit"], "USD": [total_invest, total_benefit]})
    fig_roi = px.bar(
        df_roi,
        x="Category",
        y="USD",
        text_auto=".2s",
        color="Category",
        color_discrete_sequence=["#ef4444", "#22c55e"],
        title="Costs vs economic benefits over selected period (illustrative)",
    )
    fig_roi.update_layout(yaxis_title="USD")
    st.plotly_chart(fig_roi, use_container_width=True)

    st.markdown("### 📈 Cumulative investment vs benefits over time")
    years = list(range(1, time_horizon + 1))
    cum_invest = [gov_invest * y for y in years]
    cum_benefit = [avoided_outbreak_cost * y for y in years]
    df_cum = pd.DataFrame(
        {"Year": years, "Cumulative investment": cum_invest, "Cumulative benefit": cum_benefit}
    )
    df_cum_melt = df_cum.melt(id_vars="Year", var_name="Type", value_name="USD")
    fig_cum = px.line(
        df_cum_melt,
        x="Year",
        y="USD",
        color="Type",
        markers=True,
        color_discrete_map={"Cumulative investment": "#ef4444", "Cumulative benefit": "#22c55e"},
        title="Cumulative flows over time (illustrative)",
    )
    st.plotly_chart(fig_cum, use_container_width=True)

    st.markdown("### 🧮 How this simple ROI model works")
    st.markdown(
        f"- **Annual investment**: {gov_invest:,.0f} USD × {time_horizon} years = {total_invest:,.0f} USD.\n"
        f"- **Annual avoided losses** (treatment costs, productivity loss, deaths avoided): "
        f"{avoided_outbreak_cost:,.0f} USD × {time_horizon} years = {total_benefit:,.0f} USD.\n"
        f"- **ROI multiple** = total benefit ÷ total investment = {roi_ratio:,.1f}x "
        f"(≈ {roi_percent:,.0f}% net gain over the period)."
    )
    st.info(
        "To make this **official for Uganda**, you would replace these assumptions with:\n"
        "- Real health security and preparedness spending from MoH / Ministry of Finance.[web:100][web:106]\n"
        "- Disease burden & economic loss estimates from WHO/World Bank studies (e.g. ROI of immunization).[web:104][web:105]"
    )
