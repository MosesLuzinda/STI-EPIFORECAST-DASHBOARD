import os
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st
from data_services import (
    analyze_outbreak_risk,
    build_admin_update_message,
    compute_dashboard_metrics,
    generate_ai_nlp_alerts,
    get_signal_sources,
    list_validated_signal_diseases,
    load_admin_alert_config,
    run_signal_forecast,
    save_admin_alert_config,
    send_admin_email,
)
from forecast_lab_four_disease import (
    brief_to_burden_df,
    brief_to_heatmap_df,
    brief_to_radar_figure,
    generate_four_disease_brief_json,
    recommendations_to_rows,
    uganda_units_to_rows,
)


def get_dashboard(realtime_data: dict | None) -> dict:
    """Single source of truth for dashboard KPIs across every page."""
    if not realtime_data:
        return compute_dashboard_metrics({})
    cached = realtime_data.get("dashboard")
    if isinstance(cached, dict) and cached:
        return cached
    return compute_dashboard_metrics(realtime_data)


def render_signal_sources_panel(realtime_data: dict, *, key_suffix: str = "", default_tab: str = "open_web"):
    """
    Render a unified, clickable list of the actual feed items behind the dashboard KPIs.
    Each item links to the original article / post on the source site (Reddit, GDELT, WHO, etc.).
    """
    sources = get_signal_sources(realtime_data or {})
    open_web = sources.get("open_web") or []
    official = sources.get("official") or []
    news = sources.get("news") or []
    portals = sources.get("portals") or {}

    def _render_items(items, empty_msg):
        if not items:
            st.info(empty_msg)
            return
        for idx, item in enumerate(items[:25], start=1):
            title = str(item.get("title") or "Untitled signal")
            url = str(item.get("url") or "").strip()
            source = str(item.get("source") or "Source")
            meta = str(item.get("meta") or "")
            confidence = str(item.get("confidence") or "").strip()
            badge = f" · `{confidence}` confidence" if confidence else ""
            suffix = f" — _{meta}_" if meta else ""
            if url:
                st.markdown(f"{idx}. [{title}]({url}) · **{source}**{badge}{suffix}")
            else:
                st.markdown(f"{idx}. {title} · **{source}**{badge}{suffix}")

    tab_labels = ["Open-web items", "Official feeds", "GDELT articles", "Source portals"]
    tabs = st.tabs(tab_labels)
    with tabs[0]:
        st.caption("Reddit posts, Hacker News stories, and GDELT articles — click any title to open the original source.")
        _render_items(open_web, "No open-web signal items in the current snapshot.")
    with tabs[1]:
        st.caption("WHO Disease Outbreak News, CDC outbreak updates, and UN global health references.")
        _render_items(official, "No official feed items available right now.")
    with tabs[2]:
        st.caption("Top GDELT-tracked outbreak news articles, sorted by recency.")
        _render_items(news, "No GDELT article links returned in the current snapshot.")
    with tabs[3]:
        st.caption("Direct links to the upstream source portals used by the dashboard.")
        if not portals:
            st.info("No portal references configured.")
        else:
            for label, url in portals.items():
                st.markdown(f"- **{label}** → [{url}]({url})")


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
    canonical = ["Cholera", "Malaria", "Typhoid", "Marburg"]
    pe = st.session_state.get("pe_disease")
    default_disease = pe if pe in canonical else st.session_state.get("policy_disease", "Cholera")
    if default_disease not in canonical:
        default_disease = "Cholera"
    disease = st.selectbox(
        "Disease focus",
        canonical,
        index=canonical.index(default_disease),
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


def _hotspot_scale(disease: str) -> float:
    m = {
        "Cholera": 1.18,
        "Malaria": 1.10,
        "Typhoid": 0.96,
        "Marburg": 1.26,
        "Ebola": 1.22,
        "Yellow fever": 1.14,
        "COVID-19": 1.05,
        "HIV/AIDS": 0.92,
        "Tuberculosis": 0.94,
    }
    return float(m.get(disease, 1.0))


def render_region_watch():
    st.title("📍 Uganda Vulnerability Map (Hotspots & Risk)")
    focus = st.session_state.get("pe_disease") or _selected_disease()
    st.caption(f"Spatial risk uses sidebar **Pathogen focus**: **{focus}** (scalar defaults for diseases not yet calibrated).")
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
    scale = _hotspot_scale(focus)

    records = []
    for district, base_risk in districts:
        risk = min(0.98, base_risk * scale)
        if risk >= 0.65:
            trend = "Rising"
        elif risk >= 0.50:
            trend = "Stable"
        else:
            trend = "Falling"
        records.append(
            {
                "District": district,
                "RiskScore": round(risk, 2),
                "RiskLabel": "High" if risk > 0.7 else ("Medium" if risk > 0.5 else "Low"),
                "Estimated Cases (14d)": int(500 + risk * 2800),
                "Trend": trend,
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
            title=f"{focus} hotspot risk by district (UBOS shapefile-ready prototype)",
            color_discrete_map={"High": "#ef4444", "Medium": "#f59e0b", "Low": "#22c55e"},
        )
        fig_hotspot.update_layout(template="plotly_dark")
        st.plotly_chart(fig_hotspot, use_container_width=True)

    st.dataframe(df_risk, use_container_width=True)


def render_forecast_lab(realtime_data: dict | None = None):
    st.title("🔮 Uganda Vulnerability (SEIR + ML Signal)")
    st.caption(
        "Structured workflow: tune epidemiological assumptions, review transmission dynamics, "
        "then validate ML outputs with incident history and live signal blending."
    )

    st.subheader("AI four-disease public-health planning brief (Uganda)")
    st.caption(
        "Targets **Cholera, Malaria, Typhoid, and Marburg** with **causal domains** (environment, climate, "
        "WASH, vectors, movement, border, health system) plus **Uganda** districts/subcounties and **EAC** context, "
        "**relative** burden and forward indices, and **recommendations**. Synthesis is for early warning and planning — "
        "calibrate to MoH, DHIS2, and EOC. Requires an AI key (see `.env` / host secrets)."
    )
    c_run, c_clr, c_ht = st.columns([1.25, 0.55, 1.0])
    with c_run:
        if st.button("🧠 Generate 4-disease analysis & visual comparison", type="primary", key="fl4_run"):
            with st.spinner("AI cross-disease analysis (up to ~2 min)…"):
                st.session_state["fl4_result"] = generate_four_disease_brief_json(realtime_data or {})
    with c_clr:
        if st.button("Clear", key="fl4_clear"):
            st.session_state.pop("fl4_result", None)
    with c_ht:
        st.caption("Uses current **dashboard snapshot** (signals, feeds) + model estimates **0–100** (not case counts).")

    fl4 = st.session_state.get("fl4_result")
    if fl4 is not None:
        if not fl4.get("ok"):
            st.error(str(fl4.get("error") or "AI brief failed."))
            if fl4.get("raw_excerpt"):
                with st.expander("Model output (debug, truncated)"):
                    st.text(str(fl4["raw_excerpt"])[:4000])
        else:
            br = (fl4.get("brief") or {}) if isinstance(fl4.get("brief"), dict) else {}
            st.markdown("#### Executive summary")
            st.markdown(str(br.get("executive_summary") or "_—_"))
            t_a, t_b, t_c, t_d = st.tabs(
                ["Causal structure (heatmap & radar)", "Burden, forecast index & subnational", "EAC + recommendations", "Caveats"]
            )
            with t_a:
                hdf = brief_to_heatmap_df(br)
                fig_heat = px.imshow(
                    hdf,
                    zmin=0,
                    zmax=100,
                    color_continuous_scale="YlOrRd",
                    aspect="auto",
                    labels=dict(
                        x="Causal / system domain (model index, not absolute risk)",
                        y="Disease",
                        color="0–100",
                    ),
                    title="Causal & driver index matrix — 4 priority diseases, 9 domains",
                )
                fig_heat.update_layout(template="plotly_dark")
                st.plotly_chart(fig_heat, use_container_width=True)
                st.plotly_chart(brief_to_radar_figure(br), use_container_width=True)
                nrs = br.get("disease_narrative")
                if isinstance(nrs, dict):
                    for dname, txt in nrs.items():
                        with st.expander(f"{dname} — short narrative (causal + Uganda)", expanded=False):
                            st.write(str(txt))
            with t_b:
                bdf = brief_to_burden_df(br)
                melt = bdf.melt(
                    id_vars="Disease",
                    value_vars=[c for c in bdf.columns if c != "Disease"],
                    var_name="Metric",
                    value_name="0–100",
                )
                fig_bar = px.bar(
                    melt,
                    x="Disease",
                    y="0–100",
                    color="Metric",
                    barmode="group",
                    title="Comparative burden and 6‑month relative forecast index (planning scale 0–100; not case counts)",
                )
                fig_bar.update_layout(template="plotly_dark")
                st.plotly_chart(fig_bar, use_container_width=True)
                urows = uganda_units_to_rows(br)
                if urows:
                    st.markdown("**Uganda: districts / subcounties / regions (draft targeting)**")
                    st.dataframe(pd.DataFrame(urows), use_container_width=True, hide_index=True)
            with t_c:
                st.markdown("**East Africa / border context**")
                st.markdown(str(br.get("eac_regional_patterns") or "_—_"))
                st.markdown("**Prioritized decision recommendations (evidence-style)**")
                rrows = recommendations_to_rows(br)
                if rrows:
                    st.dataframe(pd.DataFrame(rrows), use_container_width=True, hide_index=True)
            with t_d:
                st.warning(str(br.get("evidence_caveat") or "AI output is a planning aid, not official surveillance."))
                st.info(str(br.get("data_limitations") or "—"))

    st.divider()
    disease = _selected_disease()

    in1, in2, in3, in4 = st.columns([1.2, 1.1, 1, 1.1])
    with in1:
        population = st.number_input(
            "Total population", min_value=1_000_000, max_value=80_000_000, value=48_000_000, step=1_000_000
        )
    with in2:
        initial_infected = st.number_input(
            "Initial infected", min_value=100, max_value=400_000, value=12000, step=100
        )
    with in3:
        days = st.slider("Forecast horizon", 30, 100, 100)
    with in4:
        intervention = st.slider("Intervention effectiveness", 0.0, 0.9, 0.35, 0.01)

    base_beta = {"Cholera": 0.36, "Malaria": 0.31, "Typhoid": 0.27, "Marburg": 0.44}.get(disease, 0.33)
    beta = base_beta * (1.0 - intervention)
    sigma = 1 / 5.2
    gamma = 1 / 8.5
    t1, t2, t3 = st.columns(3)
    with t1:
        st.metric("Transmission factor (beta)", f"{beta:.3f}")
    with t2:
        st.metric("Incubation conversion (sigma)", f"{sigma:.3f}")
    with t3:
        st.metric("Recovery rate (gamma)", f"{gamma:.3f}")

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

    st.subheader("Machine Learning Signal (AI-validated live signals + Random Forest)")
    has_ai_key = bool(
        (os.getenv("AI_API_KEY") or "").strip()
        or (os.getenv("OPENAI_API_KEY") or "").strip()
        or (os.getenv("CURSOR_API_KEY") or "").strip()
        or (os.getenv("XAI_API_KEY") or "").strip()
    )
    st.caption(
        "Forecast Lab now trains directly on the live signal stream. Every feed item "
        "(GDELT / Reddit / HN / WHO / CDC / CIDRAP / ReliefWeb / PAHO) is first run "
        "through the AI signal validator; only items confirmed as real outbreak signals "
        "are persisted to the signal store and used to train the model below."
    )
    if not has_ai_key:
        st.info(
            "AI validation is currently in fallback mode because no API key is configured. "
            "Set AI_API_KEY (or OPENAI_API_KEY / CURSOR_API_KEY / XAI_API_KEY) to unlock "
            "full live signal validation and richer open-web signal items."
        )

    available_diseases = list_validated_signal_diseases(min_count=1)
    disease_options = ["All diseases"] + available_diseases
    default_disease_label = (
        disease.lower() if disease and disease.lower() in [d.lower() for d in available_diseases]
        else "All diseases"
    )
    if default_disease_label != "All diseases":
        default_index = next(
            (i for i, d in enumerate(disease_options) if d.lower() == default_disease_label),
            0,
        )
    else:
        default_index = 0

    fc1, fc2, fc3 = st.columns([1.4, 1.0, 1.0])
    with fc1:
        forecast_disease_label = st.selectbox(
            "Forecast scope",
            disease_options,
            index=default_index,
            help="Train on signals tagged with a specific disease or use the full validated stream.",
        )
    with fc2:
        horizon_days = st.slider("Forecast horizon (days)", 7, 30, 14)
    with fc3:
        lookback_days = st.slider("History window (days)", 30, 180, 120)

    forecast_disease = None if forecast_disease_label == "All diseases" else forecast_disease_label

    try:
        sig_result = run_signal_forecast(
            disease=forecast_disease,
            horizon_days=int(horizon_days),
            lookback_days=int(lookback_days),
        )
    except Exception as exc:
        st.warning(f"Signal-trained forecast unavailable: {exc}")
        sig_result = None

    if sig_result and not sig_result["ok"]:
        st.info(sig_result.get("reason") or "Signal history is still warming up.")
        rows_available = int(sig_result.get("rows_available", 0))
        min_days = int(sig_result.get("min_history_days", 14))
        st.progress(min(1.0, rows_available / max(1, min_days)))
        st.caption(
            f"{rows_available} of {min_days} day(s) of validated signal history collected. "
            "Keep the dashboard refreshing — every accepted feed item is persisted to "
            "the signal store and accelerates this unlock."
        )
    elif sig_result and sig_result["ok"]:
        history_df = sig_result["history"].copy()
        forecast_df = sig_result["forecast"].copy()
        backtest = sig_result.get("backtest") or {}

        history_total = int(history_df["count"].sum())
        forecast_next7 = float(forecast_df.head(7)["predicted"].sum()) if not forecast_df.empty else 0.0
        m1, m2, m3 = st.columns(3)
        with m1:
            st.metric("Validated signals (history window)", f"{history_total:,}")
        with m2:
            st.metric("Forecasted signals (next 7d)", f"{forecast_next7:,.0f}")
        with m3:
            mae_val = backtest.get("mae")
            st.metric(
                "Backtest MAE",
                f"{mae_val:.2f}" if isinstance(mae_val, (int, float)) else "—",
                help=(
                    f"Mean absolute error on the held-out tail "
                    f"({backtest.get('n', 0)} day(s))."
                ),
            )

        fig_pred = go.Figure()
        fig_pred.add_trace(
            go.Scatter(
                x=history_df["date"],
                y=history_df["count"],
                name="Validated history",
                mode="lines+markers",
                line=dict(color="#22c55e", width=2),
            )
        )
        if not forecast_df.empty:
            fig_pred.add_trace(
                go.Scatter(
                    x=forecast_df["date"],
                    y=forecast_df["upper"],
                    name="Upper band",
                    mode="lines",
                    line=dict(color="#fb923c", width=0),
                    showlegend=False,
                )
            )
            fig_pred.add_trace(
                go.Scatter(
                    x=forecast_df["date"],
                    y=forecast_df["lower"],
                    name="Confidence band",
                    mode="lines",
                    fill="tonexty",
                    line=dict(color="#fb923c", width=0),
                    fillcolor="rgba(251,146,60,0.18)",
                )
            )
            fig_pred.add_trace(
                go.Scatter(
                    x=forecast_df["date"],
                    y=forecast_df["predicted"],
                    name="Forecast",
                    mode="lines+markers",
                    line=dict(color="#fb923c", width=3, dash="dot"),
                )
            )
        fig_pred.update_layout(
            title=f"AI-validated signal forecast — {sig_result['disease']}",
            xaxis_title="Date",
            yaxis_title="Validated signals / day",
            template="plotly_dark",
            hovermode="x unified",
        )
        st.plotly_chart(fig_pred, use_container_width=True)

        c1, c2 = st.columns(2)
        with c1:
            importance = sig_result.get("feature_importance") or []
            if importance:
                imp_df = pd.DataFrame(importance).head(10)
                fig_imp = px.bar(
                    imp_df,
                    x="importance",
                    y="feature",
                    orientation="h",
                    title="Top features driving the forecast",
                    color="importance",
                    color_continuous_scale="Tealgrn",
                )
                fig_imp.update_layout(
                    template="plotly_dark",
                    yaxis={"categoryorder": "total ascending"},
                )
                st.plotly_chart(fig_imp, use_container_width=True)
            else:
                st.info("Feature importance unavailable for this slice yet.")
        with c2:
            if not forecast_df.empty:
                table_df = forecast_df.copy()
                table_df["date"] = pd.to_datetime(table_df["date"]).dt.strftime("%Y-%m-%d")
                st.dataframe(
                    table_df.rename(
                        columns={
                            "date": "Date",
                            "predicted": "Predicted",
                            "lower": "Lower",
                            "upper": "Upper",
                        }
                    ),
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.info("No forecast rows generated for this horizon.")

        bt_n = int(backtest.get("n", 0) or 0)
        bt_mape = backtest.get("mape")
        if bt_n > 0 and isinstance(bt_mape, (int, float)):
            st.caption(
                f"Backtest: {bt_n} held-out day(s) • MAE {backtest.get('mae'):.2f} • "
                f"MAPE {bt_mape*100:.1f}% • Trained on validated signals only."
            )
        else:
            st.caption(
                "Backtest deferred until enough held-out history exists. "
                "The current forecast uses the full validated history."
            )


def render_learning_hub():
    st.title("📚 Learning Hub")
    st.markdown("#### Data sources in this prototype")
    st.markdown(
        "- **Malaria death rate (Uganda)**: Our World in Data dataset, derived from WHO and partners.[web:61][web:54]\n"
        "- **Optional OWID health datasets**: additional country time series can be wired from OWID CSV endpoints.[web:91]\n"
        "- **Cholera & some KPIs**: simulated values based on plausible outbreak magnitudes, not official.\n"
        "- **HealthMap iframe**: external real-time map of infectious disease signals.[web:57][web:60]"
    )
    st.markdown("#### How to go fully real for Pathogen Economy Epiforecast")
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
        _render_action_plan_operations(disease, realtime_data)
    with tab_social:
        _render_action_plan_social(disease, realtime_data)
    with tab_sim:
        _render_action_plan_simulations(disease, realtime_data)

    st.markdown("### 🔗 Where each signal came from (live source links)")
    st.caption(
        "These are the actual feed items that drive the KPIs and the recommended posture above. "
        "Click any title to open the original article or post on the source site."
    )
    render_signal_sources_panel(realtime_data, key_suffix="action_plan")


def _render_action_plan_operations(disease: str, realtime_data: dict):
    dashboard = get_dashboard(realtime_data)
    posture = dashboard["posture"]
    posture_caption = {
        "Surge": "Immediate review required",
        "Elevated": "Heightened watch",
        "Routine": "Routine monitoring",
    }.get(posture, "Routine monitoring")

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Priority-1 alerts", dashboard["priority_alerts"], posture_caption)
    with c2:
        st.metric(
            "High-risk districts",
            dashboard["high_risk_districts"],
            f"Urgency {dashboard['urgency']}/100",
        )
    with c3:
        st.metric("Response window", dashboard["response_window"], f"{posture} stance")

    if dashboard["priority_alerts"] >= 1:
        st.error(f"P1 • {disease} risk rising — {dashboard['priority_alerts']} cross-source alert(s) active.")
    else:
        st.success(f"P1 • No surge alerts for {disease} in the current 24h snapshot.")
    if dashboard["official_total"] > 0:
        st.warning(
            f"P2 • {dashboard['official_total']} official health-feed signal(s) active — "
            "verify procurement buffer for diagnostics and therapeutics."
        )
    else:
        st.info("P2 • No active official health-feed signals — keep procurement on routine cadence.")
    st.info(
        f"P3 • Open-web volume {dashboard['open_web_total']:,} (24h) across {dashboard['feeds_online']}/"
        f"{dashboard['feeds_total']} live feeds — keep cross-source monitoring on."
    )

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
    dashboard = get_dashboard(realtime_data)
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
        # Deterministic source-mix donut derived from the real channel volumes.
        non_zero = df[df["Volume (24h est.)"] > 0]
        if non_zero.empty:
            st.info("No live channel volume in the current snapshot.")
        else:
            fig_donut = px.pie(
                non_zero,
                names="Channel",
                values="Volume (24h est.)",
                hole=0.55,
                title="Source mix (24h)",
            )
            fig_donut.update_traces(textinfo="percent+label")
            fig_donut.update_layout(template="plotly_dark", height=380, showlegend=False)
            st.plotly_chart(fig_donut, use_container_width=True)
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("GDELT / news signal", f"{dashboard['news_mentions']:,}")
    with m2:
        st.metric("Open-web (24h)", f"{dashboard['open_web_total']:,}")
    with m3:
        st.metric("Sentiment proxy", f"{dashboard['sentiment']:.2f}")
    with m4:
        st.metric("Recommended posture", dashboard["posture"], dashboard["response_window"])


def _render_action_plan_simulations(disease: str, realtime_data: dict):
    st.subheader("Scenario lab — what measures to take (simulation)")
    dashboard = get_dashboard(realtime_data)
    urgency = dashboard["urgency"]
    surge = st.slider(
        "Simulated surge intensity",
        0,
        100,
        min(max(urgency, dashboard["signal_score"]), 95),
        help="Pre-set from current signal intensity; adjust to test scenarios.",
    )
    coverage = st.slider("Simulated intervention coverage %", 10, 95, 45)
    leak = st.slider("Simulated border screening gap %", 0, 40, 12)

    risk_raw = surge * 0.45 + leak * 1.1 - coverage * 0.35
    residual_risk = max(5, min(95, risk_raw))
    st.metric("Residual outbreak pressure (sim.)", f"{residual_risk:.0f}/100")

    scen = pd.DataFrame(
        {
            "Lever": ["Lab surge", "WASH push", "Risk comms", "Border checks", "Vaccine push"],
            "Impact if funded (sim.)": [
                max(0.0, 72 - surge * 0.35 + coverage * 0.20),
                max(0.0, 65 - surge * 0.25 + coverage * 0.25),
                max(0.0, 58 - leak * 0.80 + coverage * 0.15),
                max(0.0, 80 - leak * 1.20 + coverage * 0.10),
                max(0.0, 50 - surge * 0.15 + coverage * 0.30),
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

    reports_dir = Path("uploads") / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    st.markdown("#### Pathogen Economy — summary report uploads")
    st.caption("Upload **briefing summaries only** (PDF, DOCX, images, text). Raw line-level datasets are out of scope here.")
    up = st.file_uploader(
        "Upload files to Reports library",
        type=["pdf", "docx", "png", "jpg", "jpeg", "txt", "md"],
        accept_multiple_files=True,
        key="admin_pe_report_upload",
    )
    if up and st.button("Save to Reports library", key="admin_save_reports"):
        for f in up:
            dest = reports_dir / f.name
            dest.write_bytes(f.getvalue())
        st.success(f"Saved {len(up)} file(s) to uploads/reports/.")
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

    st.markdown("#### Year‑1 operations stack (budget alignment)")
    st.caption(
        "Deployment checklist mapped to the 12‑month operational budget. "
        "“Ready” means this host’s environment exposes the expected configuration — "
        "not that billing or vendor contracts are complete."
    )
    primary_ai = bool(
        (
            os.getenv("AI_API_KEY")
            or os.getenv("OPENAI_API_KEY")
            or os.getenv("CURSOR_API_KEY")
            or os.getenv("XAI_API_KEY")
            or ""
        ).strip()
    )
    failover_ai = bool((os.getenv("AI_FAILOVER_API_KEY") or os.getenv("GROQ_API_KEY") or "").strip())
    email_ok = bool(
        (os.getenv("SENDGRID_API_KEY") or "").strip()
        or (
            (os.getenv("SMTP_HOST") or "").strip()
            and (os.getenv("ALERT_FROM_EMAIL") or os.getenv("SMTP_USER") or "").strip()
            and (os.getenv("SMTP_PASS") or os.getenv("SENDGRID_API_KEY") or "").strip()
        )
    )
    heartbeat = bool((os.getenv("BETTER_STACK_HEARTBEAT_URL") or os.getenv("UPTIME_HEARTBEAT_URL") or "").strip())
    r2_ok = bool(
        (os.getenv("R2_BUCKET_NAME") or os.getenv("CLOUDFLARE_R2_BUCKET") or "").strip()
        and (os.getenv("R2_ACCESS_KEY_ID") or os.getenv("AWS_ACCESS_KEY_ID") or "").strip()
    )
    stack_df = pd.DataFrame(
        [
            {
                "P": "P1",
                "Budget item": "Domain registration",
                "Vendor": "Cloudflare",
                "In app / infra": "Public hostname (e.g. PathogenEconomyEpiforecast.com) + TLS certificates",
                "Ready": "✓" if (os.getenv("PUBLIC_SITE_DOMAIN") or "").strip() else "—",
            },
            {
                "P": "P1",
                "Budget item": "DNS + WAF / CDN",
                "Vendor": "Cloudflare",
                "In app / infra": "Terminate TLS, DDoS protection, cache static assets in front of STI / Industry 4.0+ origin",
                "Ready": "✓" if (os.getenv("CLOUDFLARE_ZONE_ID") or "").strip() else "—",
            },
            {
                "P": "P1",
                "Budget item": "AI primary",
                "Vendor": "OpenAI",
                "In app / infra": "Forecast Lab, NLP alerts, AI signal validation (`AI_*` / `OPENAI_*`)",
                "Ready": "✓" if primary_ai else "—",
            },
            {
                "P": "P2",
                "Budget item": "AI failover",
                "Vendor": "Groq",
                "In app / infra": "Automatic failover for chat, validator, and API alerts (`AI_FAILOVER_*` or `GROQ_*`)",
                "Ready": "✓" if failover_ai else "—",
            },
            {
                "P": "P1",
                "Budget item": "Transactional email",
                "Vendor": "SendGrid",
                "In app / infra": "Daily + emergency risk bulletins (`SENDGRID_API_KEY` or generic SMTP)",
                "Ready": "✓" if email_ok else "—",
            },
            {
                "P": "P1",
                "Budget item": "Uptime + paging",
                "Vendor": "Better Stack",
                "In app / infra": "Synthetic checks against `/health` + on-call paging (heartbeat URL optional here)",
                "Ready": "✓" if heartbeat else "—",
            },
            {
                "P": "P2",
                "Budget item": "Backup storage",
                "Vendor": "Cloudflare R2",
                "In app / infra": "Off-site copies of `signals.db`, uploads, configs (`R2_*` / S3-compatible)",
                "Ready": "✓" if r2_ok else "—",
            },
            {
                "P": "P1",
                "Budget item": "App Builder license",
                "Vendor": "ABQ",
                "In app / infra": "Rapid UI / deployment layer alongside this Python codebase (trial tier Y1)",
                "Ready": "✓" if (os.getenv("ABQ_PROJECT_ID") or "").strip() else "—",
            },
            {
                "P": "P1",
                "Budget item": "Technical staff",
                "Vendor": "IT personnel (×2)",
                "In app / infra": "Runbooks: monitor Better Stack, renew domain, rotate API keys, verify R2 backups",
                "Ready": "—",
            },
        ]
    )
    st.dataframe(stack_df, use_container_width=True, hide_index=True)

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
                    subject=f"[Test] Pathogen Economy Epiforecast {risk['risk_level']} risk bulletin",
                    body_text=body,
                    recipients=recipients,
                )
                if ok:
                    st.success("Test email sent.")
                else:
                    st.error(f"Test email failed: {msg}")
    st.caption(
        "Email delivery: set SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, ALERT_FROM_EMAIL — or only "
        "SENDGRID_API_KEY (uses smtp.sendgrid.net / user `apikey`). "
        "Emergency emails trigger when computed risk exceeds threshold."
    )

    st.markdown("#### API setup and live connectivity checks")
    st.caption(
        "Use this panel to verify social and health feed connectors without restarting the app. "
        "Secrets stay in environment variables and are never displayed in full."
    )

    def _mask(value: str, keep: int = 4) -> str:
        if not value:
            return "Not set"
        if len(value) <= keep:
            return "*" * len(value)
        return "*" * (len(value) - keep) + value[-keep:]

    token_x = (os.getenv("X_API_BEARER") or "").strip()
    token_li = (os.getenv("LINKEDIN_ACCESS_TOKEN") or "").strip()
    org_li = (os.getenv("LINKEDIN_ORG_ID") or "").strip()
    token_meta = (os.getenv("META_ACCESS_TOKEN") or "").strip()
    page_meta = (os.getenv("META_PAGE_ID") or "").strip()
    key_news = (os.getenv("NEWSAPI_KEY") or os.getenv("NEWS_API_KEY") or "").strip()

    cfg_df = pd.DataFrame(
        [
            {"Integration": "X / Twitter", "Credential": _mask(token_x), "Extra": ""},
            {"Integration": "LinkedIn", "Credential": _mask(token_li), "Extra": f"ORG: {_mask(org_li, keep=3)}"},
            {"Integration": "Facebook / Meta", "Credential": _mask(token_meta), "Extra": f"PAGE: {_mask(page_meta, keep=3)}"},
            {"Integration": "NewsAPI", "Credential": _mask(key_news), "Extra": ""},
        ]
    )
    st.dataframe(cfg_df, use_container_width=True, hide_index=True)

    if st.button("Run live connector checks", key="admin_run_connector_checks"):
        checks = []

        def _run(name: str, fn):
            try:
                ok, msg = fn()
                checks.append({"Source": name, "Status": "online" if ok else "offline", "Detail": msg})
            except Exception as exc:
                checks.append({"Source": name, "Status": "offline", "Detail": str(exc)[:140]})

        def _check_x():
            if not token_x:
                return False, "Missing X_API_BEARER"
            r = requests.get(
                "https://api.twitter.com/2/tweets/search/recent",
                params={"query": "cholera OR malaria OR outbreak lang:en", "max_results": 10},
                timeout=8,
                headers={"Authorization": f"Bearer {token_x}"},
            )
            if r.status_code != 200:
                return False, f"HTTP {r.status_code}"
            return True, f"{len(r.json().get('data') or [])} recent posts"

        def _check_linkedin():
            if not token_li:
                return False, "Missing LINKEDIN_ACCESS_TOKEN"
            if not org_li:
                return False, "Missing LINKEDIN_ORG_ID"
            r = requests.get(
                "https://api.linkedin.com/v2/shares",
                params={"q": "owners", "owners": f"urn:li:organization:{org_li}", "count": 10},
                timeout=8,
                headers={"Authorization": f"Bearer {token_li}"},
            )
            if r.status_code != 200:
                return False, f"HTTP {r.status_code}"
            return True, f"{len(r.json().get('elements') or [])} org shares"

        def _check_meta():
            if not token_meta:
                return False, "Missing META_ACCESS_TOKEN"
            if not page_meta:
                return False, "Missing META_PAGE_ID"
            r = requests.get(
                f"https://graph.facebook.com/v20.0/{page_meta}/posts",
                params={"limit": 10, "access_token": token_meta},
                timeout=8,
            )
            if r.status_code != 200:
                return False, f"HTTP {r.status_code}"
            return True, f"{len(r.json().get('data') or [])} page posts"

        def _check_who():
            r = requests.get(
                "https://www.who.int/feeds/entity/emergencies/disease-outbreak-news/rss.xml",
                timeout=8,
                headers={"User-Agent": "PathogenEconomyEpiforecast/1.0"},
            )
            if r.status_code != 200:
                return False, f"HTTP {r.status_code}"
            if "<item>" not in r.text:
                return False, "No feed items detected"
            return True, "WHO outbreak feed reachable"

        def _check_cdc():
            r = requests.get(
                "https://tools.cdc.gov/api/v2/resources/media/403372.rss",
                timeout=8,
                headers={"User-Agent": "PathogenEconomyEpiforecast/1.0"},
            )
            if r.status_code != 200:
                return False, f"HTTP {r.status_code}"
            if "<item>" not in r.text:
                return False, "No feed items detected"
            return True, "CDC feed reachable"

        def _check_un():
            r = requests.get(
                "https://www.un.org",
                timeout=8,
                headers={"User-Agent": "PathogenEconomyEpiforecast/1.0"},
            )
            if r.status_code != 200:
                return False, f"HTTP {r.status_code}"
            return True, "UN portal reachable"

        _run("X / Twitter API", _check_x)
        _run("LinkedIn API", _check_linkedin)
        _run("Facebook / Meta API", _check_meta)
        _run("WHO feed", _check_who)
        _run("CDC feed", _check_cdc)
        _run("UN portal", _check_un)

        df_checks = pd.DataFrame(checks)
        st.dataframe(df_checks, use_container_width=True, hide_index=True)
        online_n = int((df_checks["Status"] == "online").sum())
        st.info(f"Connector check complete: {online_n}/{len(df_checks)} online.")


def render_global_view(realtime_data):
    st.title("🌐 Global Surveillance (News + Social Signals)")
    st.caption(
        "GDELT, Reddit, Hacker News, WHO, CDC, and UN feeds drive every KPI. "
        "Click any signal in the Source Monitor tab to open the original article on the source site."
    )

    dashboard = get_dashboard(realtime_data)
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
        # Distribute the real combined-signal volume across the regional watchlist
        # using transparent watch weights — no fabricated "38,000 cholera cases".
        base_signal = max(0, dashboard["combined_total"])
        weights = [0.25, 0.14, 0.12, 0.08, 0.13, 0.10, 0.10, 0.08]
        df_cholera = pd.DataFrame(countries)
        df_cholera["signal_share"] = [round(base_signal * w) for w in weights]

        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric(
                "Combined signal volume (24h)",
                f"{dashboard['combined_total']:,}",
                f"{dashboard['feeds_online']}/{dashboard['feeds_total']} feeds online",
            )
        with c2:
            st.metric("Countries on watchlist", df_cholera.shape[0])
        with c3:
            st.metric(
                "GDELT mentions (24h)",
                f"{dashboard['news_mentions']:,}",
                f"Signal {dashboard['signal_score']}/100",
            )

        if base_signal == 0:
            st.info(
                "Choropleth is empty because no live feed returned signals in the current snapshot. "
                "Try refreshing or check the Source Monitor tab for feed connectivity."
            )
        else:
            fig_cholera = px.choropleth(
                df_cholera,
                locations="iso_code",
                color="signal_share",
                hover_name="location",
                hover_data={"iso_code": False, "signal_share": ":,"},
                color_continuous_scale="YlOrRd",
                title="Regional share of combined live signal volume (24h)",
            )
            fig_cholera.update_layout(
                legend_title_text="Share of live signal volume",
                transition={"duration": 420, "easing": "cubic-in-out"},
            )
            st.plotly_chart(fig_cholera, use_container_width=True)
        st.caption(
            "Distribution above uses transparent regional watch weights applied to the live combined "
            "signal volume — district case totals are not synthesized."
        )

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
            st.metric("Signal mentions (24h)", f"{dashboard['news_mentions']:,}")
        with c2:
            st.metric("Countries in active watch", dashboard["affected_countries"])
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
        if realtime_data.get("who_ok"):
            st.success("WHO feed: online")
        else:
            st.warning("WHO feed: unavailable (using 0 count)")
        if realtime_data.get("cdc_ok"):
            st.success("CDC feed: online")
        else:
            st.warning("CDC feed: unavailable (using 0 count)")
        if realtime_data.get("un_ok"):
            st.success("UN Global Health signal: online")
        else:
            st.warning("UN Global Health signal: unavailable")
        if realtime_data.get("x_ok"):
            st.success("X / Twitter API: online")
        else:
            st.info(f"X / Twitter API: {realtime_data.get('x_status', 'not configured')}")
        if realtime_data.get("linkedin_ok"):
            st.success("LinkedIn API: online")
        else:
            st.info(f"LinkedIn API: {realtime_data.get('linkedin_status', 'not configured')}")
        if realtime_data.get("meta_ok"):
            st.success("Facebook/Meta API: online")
        else:
            st.info(f"Facebook/Meta API: {realtime_data.get('meta_status', 'not configured')}")
        st.info("AI extraction: POST /v1/nlp-alerts or direct OpenAI-compatible chat from env keys.")

        st.markdown("### 🔗 Where each signal came from (live source links)")
        st.caption(
            "Each metric on this page traces back to these feed items — click any title to open the "
            "original article or post on the source site."
        )
        render_signal_sources_panel(realtime_data, key_suffix="global")


def render_executive_brief(realtime_data):
    st.title("🧭 Executive Briefing")
    st.caption("One-screen summary for senior decision makers: status, priorities, and immediate actions.")

    dashboard = get_dashboard(realtime_data)
    signal_score = dashboard["signal_score"]
    risk_label = dashboard["risk_level"]
    posture = dashboard["posture"]

    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.metric("Overall risk level", risk_label, posture)
    with k2:
        st.metric("Signal intensity", f"{signal_score}/100")
    with k3:
        st.metric("Countries under watch", dashboard["affected_countries"])
    with k4:
        st.metric("Update time", realtime_data.get("last_updated", "n/a"))

    st.info(
        f"**National posture:** {risk_label} risk · {posture} stance · "
        f"recommended response window {dashboard['response_window']}."
    )

    social_channels = realtime_data.get("social_channels") or {}
    health_channels = realtime_data.get("health_site_signals") or {}
    top_social = sorted(social_channels.items(), key=lambda x: int(x[1] or 0), reverse=True)[:3]
    top_health = sorted(health_channels.items(), key=lambda x: int(x[1] or 0), reverse=True)[:2]

    left, right = st.columns([1.3, 1])
    with left:
        st.subheader("Current Signal Register")
        timeline_rows = [
            {
                "Window": "24h",
                "Event": f"GDELT outbreak mentions recorded: {dashboard['news_mentions']:,}",
                "Priority": "High" if dashboard["news_mentions"] >= 2000 else "Medium",
            },
            {
                "Window": "24h",
                "Event": f"Open-web volume total: {dashboard['open_web_total']:,}",
                "Priority": "High" if dashboard["open_web_total"] >= 3000 else "Medium",
            },
            {
                "Window": "24h",
                "Event": f"Official health feed volume: {dashboard['official_total']:,}",
                "Priority": "High" if dashboard["official_total"] >= 80 else "Low",
            },
            {
                "Window": "Now",
                "Event": f"Latest snapshot captured at {realtime_data.get('last_updated', 'n/a')}",
                "Priority": risk_label,
            },
        ]
        for label, value in top_social:
            timeline_rows.append(
                {
                    "Window": "Source",
                    "Event": f"{label}: {int(value or 0):,}",
                    "Priority": "Medium",
                }
            )
        for label, value in top_health:
            timeline_rows.append(
                {
                    "Window": "Source",
                    "Event": f"{label}: {int(value or 0):,}",
                    "Priority": "Low",
                }
            )

        timeline = pd.DataFrame(timeline_rows[:8])
        st.dataframe(timeline, use_container_width=True, hide_index=True)

    with right:
        st.subheader(f"Decision Actions ({dashboard['response_window']})")
        st.error("P1 • Confirm hotspot districts and activate response leads.")
        st.warning("P2 • Verify procurement buffer for diagnostics and therapeutics.")
        st.info("P3 • Publish synchronized risk communication guidance.")
        st.markdown("#### Governance checks")
        st.checkbox("Incident command meeting scheduled", key="exec_meeting")
        st.checkbox("Border screening protocol reviewed", key="exec_border")
        st.checkbox("District stock report validated", key="exec_stock")

    st.markdown("### 🔗 Where each signal came from (live source links)")
    st.caption(
        "Each KPI above traces back to these feed items — click any title to open the original "
        "article or post on the source site."
    )
    render_signal_sources_panel(realtime_data, key_suffix="exec")


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
