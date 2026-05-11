import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st
from backend.ai_config import llm_configured
from backend.coolio_capabilities import format_capabilities_markdown
from backend.data_services import (
    analyze_outbreak_risk,
    build_admin_update_message,
    compute_dashboard_metrics,
    generate_ai_nlp_alerts,
    get_signal_sources,
    is_priority_disease,
    list_validated_signal_diseases,
    load_admin_alert_config,
    run_signal_forecast,
    save_admin_alert_config,
    send_admin_email,
)
from backend.disease_surveillance import get_disease_surveillance_snapshot
from backend.statistical_forecast import no_ai_mode
from backend.uganda_folium_maps import streamlit_folium_available
from backend.forecast_lab_four_disease import (
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

    tab_labels = ["News & social", "Agencies", "Press articles", "Source homepages"]
    tabs = st.tabs(tab_labels)
    with tabs[0]:
        _render_items(open_web, "No open-web signal items in the current snapshot.")
    with tabs[1]:
        _render_items(official, "No official feed items available right now.")
    with tabs[2]:
        _render_items(news, "No GDELT article links returned in the current snapshot.")
    with tabs[3]:
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


NO_DISEASE_LABEL = "(no focus — pick a disease to watch)"


def get_policy_disease() -> str:
    """Single surveillance / forecast / alert focus — set from sidebar.

    Returns ``""`` when the user has not selected a specific pathogen
    (the sentinel ``NO_DISEASE_LABEL`` is treated as no focus). Pages that
    require a focused disease should guard with ``if not get_policy_disease():``
    and prompt the user to choose, rather than silently defaulting.
    """
    d = st.session_state.get("policy_disease")
    s = (str(d).strip() if d is not None else "")
    if not s or s == NO_DISEASE_LABEL:
        return ""
    return s


def policy_disease_focused() -> bool:
    return bool(get_policy_disease())


def _canonical_disease_options() -> list[str]:
    """Preset watchlist + core + validated store + current policy focus."""
    core = ["Cholera", "Malaria", "Typhoid", "Marburg"]
    presets = [
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
        "HIV",
        "Tuberculosis",
        "Leptospirosis",
        "Plague",
        "Zika",
    ]
    try:
        extra = [x for x in list_validated_signal_diseases(min_count=1) if x]
    except Exception:
        extra = []
    pol = get_policy_disease()
    merged: list[str] = []
    for x in core + presets + extra + [pol]:
        if x and x not in merged:
            merged.append(x)
    merged.sort(key=lambda t: t.lower())
    for preferred in (pol, "Cholera", "Malaria", "Typhoid", "Marburg"):
        if preferred in merged:
            merged.remove(preferred)
            merged.insert(0, preferred)
    return merged


def _count_for_disease(vd24, disease: str) -> int:
    for x in vd24 or []:
        if not isinstance(x, dict):
            continue
        if str(x.get("disease") or "").strip().lower() == str(disease).strip().lower():
            return int(x.get("count") or 0)
    return 0


def _nlp_inputs_scaled(
    disease: str,
    count_24h: int,
    vd24,
    realtime_data: dict,
) -> tuple[int, int, int]:
    """Scale snapshot KPIs so each disease gets its own NLP alert call with plausible inputs."""
    base_nm = int(realtime_data.get("news_mentions", 0) or 0)
    base_cc = int(realtime_data.get("cholera_cases", 0) or 38_000)
    base_ac = int(realtime_data.get("affected_countries", 0) or 0)
    counts_only = [int(x.get("count") or 0) for x in (vd24 or []) if isinstance(x, dict)]
    max_c = max(counts_only) if counts_only else 1
    priority = {"Cholera", "Malaria", "Typhoid", "Marburg"}
    if disease in priority and count_24h <= 0:
        return max(0, base_nm), max(0, base_cc), max(1, base_ac)
    w = max(0.2, min(1.0, (count_24h if count_24h > 0 else 1) / max(max_c, 1)))
    nm = int(base_nm * w) if base_nm else int(400 * w)
    cc = int(base_cc * w) if base_cc else int(8_000 * w)
    ac = int(base_ac * max(0.35, w)) if base_ac else max(2, int(6 * w))
    return max(80, nm), max(400, cc), max(2, ac)


def _render_disease_nlp_alerts_block(
    *,
    disease: str,
    realtime_data: dict,
    vd24,
    cache_namespace: str,
) -> None:
    if "cached_nlp_alerts" not in st.session_state:
        st.session_state["cached_nlp_alerts"] = {}
    count_24h = _count_for_disease(vd24, disease)
    nm, cc, ac = _nlp_inputs_scaled(disease, count_24h, vd24, realtime_data)
    alert_key = (cache_namespace, disease, nm, cc, ac)
    if alert_key not in st.session_state["cached_nlp_alerts"]:
        st.session_state["cached_nlp_alerts"][alert_key] = generate_ai_nlp_alerts(
            disease=disease,
            news_mentions=nm,
            cholera_cases=cc,
            affected_countries=ac,
        )
    nlp_alerts, _ = st.session_state["cached_nlp_alerts"][alert_key]
    for alert in nlp_alerts:
        st.warning(alert)


def _selected_disease():
    """Disease focus for module pages — driven by sidebar `policy_disease` (any pathogen)."""
    return get_policy_disease()


def render_disease_explorer():
    st.title("🔬 Disease Profiler (Epidemiology)")
    disease = _selected_disease()

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

    _ref = "Cholera"
    hp = host_profiles.get(disease, host_profiles[_ref])
    ap = age_profiles.get(disease, age_profiles[_ref])
    ca = float(climate_amplifier.get(disease, climate_amplifier[_ref]))
    if disease not in host_profiles:
        st.info(
            f"**{disease}** is not in the built-in profiler templates — showing **{_ref}**-shaped placeholders "
            "until diseases-specific parameters are calibrated."
        )

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Host Origin (Donut)")
        df_host = pd.DataFrame(
            {"Host": list(hp.keys()), "Share": list(hp.values())}
        )
        fig_host = px.pie(df_host, names="Host", values="Share", hole=0.62, title=f"{disease} host signal mix")
        fig_host.update_layout(template="plotly_dark")
        st.plotly_chart(fig_host)

    with c2:
        st.subheader("Age Vulnerability (Bar)")
        age_groups = ["0-4", "5-14", "15-24", "25-49", "50+"]
        df_age = pd.DataFrame({"Age Group": age_groups, "Risk Index": ap})
        fig_age = px.bar(df_age, x="Age Group", y="Risk Index", color="Risk Index", title=f"{disease} age-risk index")
        fig_age.update_layout(template="plotly_dark")
        st.plotly_chart(fig_age)

    st.subheader("Environment Sensitivity (Line)")
    temps = np.arange(16, 37, 1)
    baseline = np.clip((temps - 16) * 2.2, 1, None)
    env_risk = baseline * ca
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
    st.plotly_chart(fig_env)


def render_disease_surveillance_hub(realtime_data: dict | None):
    """
    Integrated surveillance + forecasting for the **active sidebar disease** (any pathogen name).
    KPIs and anomaly detection use local `signals.db`; national context uses the live snapshot.
    """
    st.title("Track a disease")
    st.caption(f"Watching **{get_policy_disease()}** — change it anytime in the sidebar under *Disease to watch everywhere*.")

    disease = get_policy_disease()
    snap = get_disease_surveillance_snapshot(disease, realtime_data)
    dashboard = get_dashboard(realtime_data or {})

    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("Matched signals (24h)", f"{snap['validated_count_24h']:,}")
    with m2:
        st.metric("Matched signals (7d)", f"{snap['validated_count_7d']:,}")
    with m3:
        st.metric("National activity index", f"{dashboard.get('signal_score', 0)}/100", str(dashboard.get("posture", "—")))
    with m4:
        ann = snap.get("anomaly") or {}
        flag = ann.get("flag", "—") if ann else "n/a"
        st.metric("Compared to usual (14d)", flag, snap.get("trend_label", ""))

    if snap.get("anomaly"):
        a = snap["anomaly"]
        st.info(
            f"**Trend check:** **{a.get('last_day_count', 0)}** recent items vs a typical day around **"
            f"{a.get('baseline_mean_14d_excl_last')}**. Treat as a hint only — confirm with official reports."
        )

    daily = snap.get("daily")
    if daily is not None and not daily.empty:
        fig = go.Figure()
        fig.add_trace(
            go.Bar(
                x=pd.to_datetime(daily["date"]),
                y=daily["count"],
                name="Validated signals / day",
                marker_color="#3b82f6",
            )
        )
        fig.update_layout(
            template="plotly_dark",
            title=f"{disease} — daily validated signal counts (local store)",
            xaxis_title="Date",
            yaxis_title="Count",
        )
        st.plotly_chart(fig)
    else:
        st.warning(
            f"No rows in `signals.db` for **{disease}** yet. Run the dashboard with live feeds (or imports) so the "
            "validator can tag and persist items, or check the spelling matches stored disease labels."
        )

    vd24 = (realtime_data or {}).get("validated_disease_counts_24h") or []
    st.subheader("Contextual risk lines (this pathogen)")
    _render_disease_nlp_alerts_block(
        disease=disease,
        realtime_data=realtime_data or {},
        vd24=vd24,
        cache_namespace="surv_hub_nlp",
    )

    st.subheader("Signal-count forecast (disease-scoped)")
    fc1, fc2, fc3 = st.columns(3)
    with fc1:
        horizon = st.slider("Horizon (days)", 7, 30, 14, key="surv_hub_horizon")
    with fc2:
        lookback = st.slider("Lookback (days)", 30, 180, 90, key="surv_hub_lookback")
    with fc3:
        st.metric("Store label", disease)

    try:
        sig_result = run_signal_forecast(
            disease=disease,
            horizon_days=int(horizon),
            lookback_days=int(lookback),
        )
    except Exception as exc:
        st.warning(f"Forecast error: {exc}")
        sig_result = None

    if sig_result and not sig_result["ok"]:
        st.info(sig_result.get("reason") or "Not enough history for forecast.")
    elif sig_result and sig_result.get("ok"):
        if (sig_result.get("forecast_method") or "") == "coolio_world_briefing":
            fnote = (sig_result.get("forecast_note") or "").strip()
            if fnote:
                st.info(fnote)
            nar = (sig_result.get("coolio_world_narrative") or sig_result.get("coolio_llm_analysis") or "").strip()
            if nar:
                st.subheader("Coolio · world context")
                if (sig_result.get("coolio_llm_model") or "").strip():
                    st.caption(
                        f"LLM `{sig_result.get('coolio_llm_model')}` — synthesis tied to listed sources; "
                        "not exhaustive real-time global surveillance."
                    )
                st.markdown(nar)
            if (sig_result.get("coolio_llm_error") or "").strip():
                st.caption(f"LLM note: {sig_result.get('coolio_llm_error')}")
            srcs = sig_result.get("coolio_world_sources") or []
            if srcs:
                with st.expander("Sources (this run)", expanded=False):
                    for s in srcs:
                        u = (s.get("url") or "").strip()
                        t = s.get("title") or "—"
                        pub = s.get("publisher") or ""
                        st.markdown(f"- **{pub}** · [{t}]({u})" if u else f"- **{pub}** · {t}")
        else:
            fnote = (sig_result.get("forecast_note") or "").strip()
            if fnote:
                st.info(fnote)
            llm_analysis = (sig_result.get("coolio_llm_analysis") or "").strip()
            llm_err = (sig_result.get("coolio_llm_error") or "").strip()
            llm_model = (sig_result.get("coolio_llm_model") or "").strip()
            if llm_analysis:
                st.subheader("Coolio briefing (LLM)")
                if llm_model:
                    st.caption(f"Model: `{llm_model}` — synthesis only; numeric forecast is from the ensemble.")
                st.markdown(llm_analysis)
            elif llm_err and (sig_result.get("forecast_method") or "").lower().startswith("coolio"):
                st.caption(f"Coolio LLM layer: {llm_err}")
            forecast_df = sig_result.get("forecast") or pd.DataFrame()
            hist_df = sig_result.get("history") or pd.DataFrame()
            if hist_df is not None and not hist_df.empty and forecast_df is not None and not forecast_df.empty:
                fig2 = go.Figure()
                fig2.add_trace(
                    go.Scatter(
                        x=hist_df["date"],
                        y=hist_df["count"],
                        name="History",
                        mode="lines+markers",
                        line=dict(color="#22c55e"),
                    )
                )
                fig2.add_trace(
                    go.Scatter(
                        x=forecast_df["date"],
                        y=forecast_df["predicted"],
                        name="Forecast",
                        mode="lines+markers",
                        line=dict(color="#fb923c", dash="dot"),
                    )
                )
                fig2.update_layout(
                    template="plotly_dark",
                    title=f"{disease} — signal trajectory",
                    xaxis_title="Date",
                    yaxis_title="Validated signals / day",
                )
                st.plotly_chart(fig2)

    st.subheader("Regional hotspot map (illustrative)")
    df_map = regional_hotspot_dataframe(disease)
    if streamlit_folium_available():
        from streamlit_folium import st_folium

        from backend.uganda_folium_maps import build_uganda_operational_map

        _mh = build_uganda_operational_map(
            df_map,
            focus_disease=disease,
            subtitle="Surveillance hub",
            show_heatmap=True,
            show_clinical_layer=True,
        )
        if _mh is not None:
            st_folium(_mh, use_container_width=True, height=480, key="surv_hub_map")
        else:
            st.warning("Map could not be built.")
    else:
        st.info("Install **folium** and **streamlit-folium** for the interactive map.")

    st.markdown("### National news links (not filtered to this disease)")
    render_signal_sources_panel(realtime_data or {}, key_suffix="surv_hub")


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


def regional_hotspot_dataframe(focus_disease: str) -> pd.DataFrame:
    """District-level proxy risk table + map-ready rows (illustrative until DHIS2 feeds)."""
    from backend.uganda_geospatial_data import default_hotspot_district_bases

    scale = _hotspot_scale(focus_disease)
    records = []
    for district, base_risk in default_hotspot_district_bases():
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
    return pd.DataFrame(records).sort_values("RiskScore", ascending=False)


def render_region_watch():
    st.title("Maps & hotspots")
    st.caption(f"Using **{get_policy_disease()}** from the sidebar — ring sizes are planning aids, not official case data.")

    focus = get_policy_disease()
    df_risk = regional_hotspot_dataframe(focus)

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
            title=f"{focus} hotspot risk by district (centroid map below)",
            color_discrete_map={"High": "#ef4444", "Medium": "#f59e0b", "Low": "#22c55e"},
        )
        fig_hotspot.update_layout(template="plotly_dark")
        st.plotly_chart(fig_hotspot)

    st.dataframe(df_risk)

    st.subheader("Uganda map")
    if streamlit_folium_available():
        from streamlit_folium import st_folium

        from backend.uganda_folium_maps import build_uganda_operational_map

        _m = build_uganda_operational_map(
            df_risk,
            focus_disease=focus,
            subtitle="Hotspots + referral & trial sites",
            show_heatmap=True,
            show_clinical_layer=True,
        )
        if _m is not None:
            st_folium(_m, use_container_width=True, height=560, key="uganda_hotspots_main_map")
        else:
            st.warning("Folium failed to initialize.")
    else:
        st.info("For maps: `pip install folium streamlit-folium`")


def render_forecast_lab(realtime_data: dict | None = None):
    st.title("🔮 Uganda Vulnerability (SEIR + ML Signal)")

    st.subheader("AI four-disease public-health planning brief (Uganda)")
    if no_ai_mode():
        st.info(
            "**Statistical mode:** causal matrices and narratives are **heuristic** (dashboard KPIs → 0–100 indices). "
            "Set **EPFORECAST_OFFLINE_SNAPSHOT=1** to skip external feed HTTP and use only local `signals.db` tallies."
        )
    c_run, c_clr = st.columns([1.25, 1.0])
    with c_run:
        if st.button("🧠 Generate 4-disease analysis & visual comparison", type="primary", key="fl4_run"):
            with st.spinner(
                "Rule-based cross-disease brief…" if no_ai_mode() else "AI cross-disease analysis (up to ~2 min)…"
            ):
                st.session_state["fl4_result"] = generate_four_disease_brief_json(realtime_data or {})
    with c_clr:
        if st.button("Clear", key="fl4_clear"):
            st.session_state.pop("fl4_result", None)

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
                st.plotly_chart(fig_heat)
                st.plotly_chart(brief_to_radar_figure(br))
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
                st.plotly_chart(fig_bar)
                urows = uganda_units_to_rows(br)
                if urows:
                    st.markdown("**Uganda: districts / subcounties / regions (draft targeting)**")
                    st.dataframe(pd.DataFrame(urows), hide_index=True)
            with t_c:
                st.markdown("**East Africa / border context**")
                st.markdown(str(br.get("eac_regional_patterns") or "_—_"))
                st.markdown("**Prioritized decision recommendations (evidence-style)**")
                rrows = recommendations_to_rows(br)
                if rrows:
                    st.dataframe(pd.DataFrame(rrows), hide_index=True)
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
    st.plotly_chart(fig_curve)

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
    st.plotly_chart(fig_travel)

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
    st.plotly_chart(fig_norm)

    _fc_eng = (os.getenv("EPFORECAST_SIGNAL_FORECAST_ENGINE") or "").strip().lower()
    st.subheader(
        "Machine Learning Signal (Coolio ensemble)"
        if _fc_eng in ("coolio", "coolio1")
        else "Machine Learning Signal (AI-validated live signals + Random Forest)"
    )
    if _fc_eng in ("coolio", "coolio1"):
        st.caption(
            "**Coolio** can run a **numeric ensemble** (RF + gradient boosting) on your **validator-approved** "
            "`signals.db` series, with optional **OWID** merge for COVID-like diseases. "
            "Set **`EPFORECAST_COOLIO_ML=0`** to skip that model and use **world context** only "
            "(Wikipedia + WHO RSS + OWID + optional LLM). "
            "When local history is thin, **`EPFORECAST_COOLIO_WORLD_FALLBACK=1`** (default) fills the gap with that world briefing "
            "so the UI stays meaningful instead of empty. "
            "LLM readout: `EPFORECAST_COOLIO_LLM=1` and `EPFORECAST_COOLIO_LLM_MODEL` for a strong model. "
            "**Coolio commands**: use the sidebar **Coolio · commands** box (e.g. “take me home”). "
            "**Memory**: world briefings can append to `data/coolio_memory/` for richer follow-up prompts (`EPFORECAST_COOLIO_MEMORY`)."
        )
    _fc_stack_title = (
        "Coolio & AI stack — predictive engine, patterns, and language assist"
        if _fc_eng in ("coolio", "coolio1")
        else "Forecast & AI stack — engine, patterns, and optional LLM assist"
    )
    with st.expander(_fc_stack_title, expanded=False):
        st.markdown(
            format_capabilities_markdown(coolio_engine_active=_fc_eng in ("coolio", "coolio1"))
        )
    if not llm_configured():
        st.info(
            "AI validation is currently in fallback mode because no LLM is configured. "
            "Set any of: **AI_API_KEY** / OPENAI_API_KEY / CURSOR_API_KEY / GEMINI_API_KEY / "
            "GOOGLE_AI_API_KEY / XAI_API_KEY, or run a local model and set **LOCAL_LLM_URL** "
            "(Ollama / LiteLLM) to unlock live signal validation and richer open-web items."
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
    elif sig_result and sig_result["ok"]:
        _fm = sig_result.get("forecast_method") or ""
        if _fm == "coolio_world_briefing":
            fnote = (sig_result.get("forecast_note") or "").strip()
            if fnote:
                st.info(fnote)
            nar = (sig_result.get("coolio_world_narrative") or sig_result.get("coolio_llm_analysis") or "").strip()
            if nar:
                st.subheader("Coolio · world context")
                if (sig_result.get("coolio_llm_model") or "").strip():
                    st.caption(
                        f"LLM `{sig_result.get('coolio_llm_model')}` — claims should match the sources below; "
                        "this is not omniscient real-time global coverage."
                    )
                st.markdown(nar)
            if (sig_result.get("coolio_llm_error") or "").strip():
                st.caption(f"LLM note: {sig_result.get('coolio_llm_error')}")
            srcs = sig_result.get("coolio_world_sources") or []
            if srcs:
                with st.expander("Sources checked this run (Wikipedia, WHO RSS, …)", expanded=False):
                    for s in srcs:
                        u = (s.get("url") or "").strip()
                        t = s.get("title") or "—"
                        pub = s.get("publisher") or ""
                        st.markdown(f"- **{pub}** · [{t}]({u})" if u else f"- **{pub}** · {t}")
            rows_av = int(sig_result.get("rows_available") or 0)
            if rows_av > 0:
                h = sig_result.get("history")
                if h is not None and not h.empty and "count" in h.columns:
                    st.metric("Local validated day-rows in your window", f"{rows_av}")
            st.caption(
                "World mode shows **meaningful context** instead of an empty chart. "
                "Set `EPFORECAST_COOLIO_ML=1` for the numeric ensemble when you have enough local history, "
                "or keep world mode with `EPFORECAST_COOLIO_ML=0`."
            )
        else:
            history_df = sig_result["history"].copy()
            forecast_df = sig_result["forecast"].copy()
            backtest = sig_result.get("backtest") or {}

            fnote = (sig_result.get("forecast_note") or "").strip()
            if fnote:
                st.info(fnote)
            llm_analysis = (sig_result.get("coolio_llm_analysis") or "").strip()
            llm_err = (sig_result.get("coolio_llm_error") or "").strip()
            llm_model = (sig_result.get("coolio_llm_model") or "").strip()
            if llm_analysis:
                st.subheader("Coolio briefing (LLM)")
                if llm_model:
                    st.caption(
                        f"Model: `{llm_model}` — synthesis only; numeric forecast is from the ensemble above."
                    )
                st.markdown(llm_analysis)
            elif llm_err and (sig_result.get("forecast_method") or "").lower().startswith("coolio"):
                st.caption(f"Coolio LLM layer: {llm_err}")

            history_total = int(history_df["count"].sum()) if not history_df.empty else 0
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
                )

            fig_pred = go.Figure()
            if not history_df.empty:
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
            method = sig_result.get("forecast_method") or "random_forest"
            if method == "coolio":
                _title_method = "Coolio ensemble"
            elif method == "coolio_naive_fallback":
                _title_method = "Coolio (naive until enough history)"
            elif method == "naive_momentum":
                _title_method = "damped trend (no ML)"
            else:
                _title_method = "Random Forest"
            fig_pred.update_layout(
                title=f"Validated signal forecast — {_title_method} — {sig_result['disease']}",
                xaxis_title="Date",
                yaxis_title="Validated signals / day",
                template="plotly_dark",
                hovermode="x unified",
            )
            st.plotly_chart(fig_pred)

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
                    st.plotly_chart(fig_imp)
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
                        hide_index=True,
                    )
                else:
                    st.info("No forecast rows generated for this horizon.")


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
    disease = get_policy_disease() or "All diseases"
    st.sidebar.markdown("#### Social & open-web monitor")
    st.sidebar.caption(realtime_data.get("social_sources_note", ""))
    st.sidebar.metric("Composite urgency", f"{realtime_data.get('social_urgency_score', 0)}/100")
    st.sidebar.metric("Sentiment index", f"{realtime_data.get('social_sentiment_index', 0):.2f}")
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
    st.sidebar.plotly_chart(fig)


def render_alerts_and_recommendations(realtime_data: dict):
    st.title("🚨 Uganda Action Plan (Control & Invest)")

    vd24 = realtime_data.get("validated_disease_counts_24h") or []
    active_rows = [
        x
        for x in vd24
        if isinstance(x, dict)
        and int(x.get("count") or 0) > 0
        and str(x.get("disease") or "").strip()
    ]
    policy_d = get_policy_disease()
    ordered_keys: list[str] = []
    if policy_d:
        ordered_keys.append(policy_d)
    for row in sorted(active_rows, key=lambda x: -int(x.get("count") or 0)):
        d0 = str(row.get("disease") or "").strip()
        if d0.lower() not in {k.lower() for k in ordered_keys}:
            ordered_keys.append(d0)
    if ordered_keys:
        st.subheader("Per-pathogen situational briefs (24h validated activity)")
        for d in ordered_keys:
            c = _count_for_disease(vd24, d)
            badge = "📌 Focus · " if d.lower() == policy_d.lower() else ""
            em = "🆕 " if not is_priority_disease(d) else ""
            with st.expander(f"{badge}{em}{d} — {c} validated signal(s) in 24h", expanded=(d.lower() == policy_d.lower())):
                _render_disease_nlp_alerts_block(
                    disease=d,
                    realtime_data=realtime_data,
                    vd24=vd24,
                    cache_namespace=f"action_path_{d[:24]}",
                )

    disease = _selected_disease()

    tab_ops, tab_social, tab_sim = st.tabs(["Operations", "Social & open web", "Measures & scenarios"])
    with tab_ops:
        _render_action_plan_operations(disease, realtime_data)
    with tab_social:
        _render_action_plan_social(disease, realtime_data)
    with tab_sim:
        _render_action_plan_simulations(disease, realtime_data)

    st.markdown("### 🔗 Where each signal came from (live source links)")
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
    _default_plan = {
        "buy": "Surge commodities per national emergency list + IPC and lab consumables",
        "prevent": "Case finding, risk communication, and infection prevention per MoH / WHO guidance",
        "invest": "Diagnostics surge, sequencing, and field epidemiology capacity",
    }
    plan = action_map.get(disease, _default_plan)

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
        st.plotly_chart(fig_bar)
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
            st.plotly_chart(fig_donut)
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
    st.plotly_chart(fig)

    if residual_risk >= 70:
        st.error("Simulation: **Surge posture** — accelerate procurement, daily command briefs, border tightening.")
    elif residual_risk >= 45:
        st.warning("Simulation: **Elevated posture** — verify stocks, intensify surveillance, pre-position teams.")
    else:
        st.success("Simulation: **Routine posture** — maintain monitoring and scheduled reviews.")



def render_admin():
    st.title("⚙️ Administration and Governance")
    st.info("Platform configuration, governance controls, and integration status for production readiness.")

    reports_dir = _ROOT / "uploads" / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    st.markdown("#### Pathogen Economy — summary report uploads")
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
    local_llm = bool((os.getenv("LOCAL_LLM_URL") or os.getenv("OLLAMA_BASE_URL") or "").strip())
    primary_ai = bool(
        llm_configured()
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
                "Budget item": "Local LLM (optional, zero token spend)",
                "Vendor": "Ollama / LiteLLM",
                "In app / infra": "When `LOCAL_LLM_URL` is set it overrides cloud keys; same `/v1/chat/completions` shape",
                "Ready": "✓" if local_llm else "—",
            },
            {
                "P": "P1",
                "Budget item": "AI primary (cloud)",
                "Vendor": "OpenAI / Gemini / xAI (Coolio language & validation assist)",
                "In app / infra": "When no `LOCAL_LLM_URL`: signal validator, Forecast Lab briefs, NLP (`AI_*`, `GEMINI_*`, …). "
                "Numeric forecasts run on **Coolio** when `EPFORECAST_SIGNAL_FORECAST_ENGINE=coolio`.",
                "Ready": "✓" if primary_ai else "—",
            },
            {
                "P": "P2",
                "Budget item": "AI failover",
                "Vendor": "Groq (same assist stack)",
                "In app / infra": "Failover for the same OpenAI-compatible routes (`AI_FAILOVER_*` / `GROQ_*`) when primary is unavailable.",
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
    st.dataframe(stack_df, hide_index=True)

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

    st.markdown("#### API setup and live connectivity checks")

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
    st.dataframe(cfg_df, hide_index=True)

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
        st.dataframe(df_checks, hide_index=True)
        online_n = int((df_checks["Status"] == "online").sum())
        st.info(f"Connector check complete: {online_n}/{len(df_checks)} online.")


def render_global_view(realtime_data):
    st.title("🌐 Global Surveillance (News + Social Signals)")

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
            st.plotly_chart(fig_cholera)

    with tab2:
        st.subheader("AI Risk Intelligence Feed (per pathogen)")
        vd24 = realtime_data.get("validated_disease_counts_24h") or []
        core_presets = ["Cholera", "Malaria", "Typhoid", "Marburg"]
        active_sorted = sorted(
            {
                str(x.get("disease") or "").strip()
                for x in vd24
                if isinstance(x, dict) and int(x.get("count") or 0) > 0 and str(x.get("disease") or "").strip()
            },
            key=lambda d: (-_count_for_disease(vd24, d), d.lower()),
        )
        policy_focus = get_policy_disease()
        nlp_targets: list[str] = []
        for d in [policy_focus] + core_presets + active_sorted:
            if d and d not in nlp_targets:
                nlp_targets.append(d)

        if "cached_nlp_alerts" not in st.session_state:
            st.session_state["cached_nlp_alerts"] = {}
        if st.button("Refresh all disease AI alerts", key="refresh_ai_alerts_btn"):
            st.session_state["cached_nlp_alerts"] = {}

        for d in nlp_targets:
            c = _count_for_disease(vd24, d)
            badge = ""
            if d.lower() == policy_focus.lower():
                badge = "📌 Sidebar focus · "
            elif not is_priority_disease(d) and c > 0:
                badge = "🆕 "
            title = f"{badge}{d} — validated signals (24h): {c}"
            with st.expander(title, expanded=(d == policy_focus)):
                _render_disease_nlp_alerts_block(
                    disease=d,
                    realtime_data=realtime_data,
                    vd24=vd24,
                    cache_namespace="global_nlp",
                )
        st.markdown(
            "**Legend:** 🔴 High urgency NLP alert • 🟠 Elevated watch • 🟢 Routine monitoring",
        )

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
        st.info(
            "Language assist: POST /v1/nlp-alerts or OpenAI-compatible chat from env keys. "
            "Short-horizon signal forecasts use **Coolio** when `EPFORECAST_SIGNAL_FORECAST_ENGINE=coolio`."
        )

        st.markdown("### 🔗 Where each signal came from (live source links)")
        render_signal_sources_panel(realtime_data, key_suffix="global")


def render_executive_brief(realtime_data):
    st.title("🧭 Executive Briefing")

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

    vd24_brief = dashboard.get("validated_disease_counts_24h") or []
    emerging_brief = dashboard.get("emerging_validated_diseases_24h") or []
    if vd24_brief:
        st.subheader("AI-validated signal volume by disease (24h)")
        st.dataframe(pd.DataFrame(vd24_brief), hide_index=True)
    if emerging_brief:
        parts = ", ".join(
            f"**{x.get('disease')}** ({int(x.get('count') or 0)})"
            for x in sorted(emerging_brief, key=lambda z: -int(z.get("count") or 0))
        )
        st.error(f"Emerging pathogen activity (outside core four): {parts}")
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
        st.dataframe(timeline, hide_index=True)

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
    st.plotly_chart(fig_roi)

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
    st.plotly_chart(fig_cum)

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
