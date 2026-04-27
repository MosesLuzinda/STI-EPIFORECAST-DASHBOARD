"""
Pathogen economy workspace sections.
Illustrative planning numbers; replace with NMS / MoH / UBOS calibrated feeds.
"""

from __future__ import annotations

import io
import json
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from data_services import (
    analyze_outbreak_risk,
    compute_dashboard_metrics,
    generate_pe_countermeasures_rows,
    generate_venture_matrix_ai,
)

THINKTANK_DIR = Path("assets") / "pe_thinktank"
THINKTANK_MEMBERS_JSON = THINKTANK_DIR / "members.json"


def _default_thinktank_members() -> list[dict]:
    return [
        {
            "name": "Hon. Dr. Monica Musenero Musanza",
            "role": "Hon. Minister — Science, Technology & Innovation (STI-OP)",
            "photo": "Hon.-Dr.-Monica-Musenero-Musanza.jpg",
            "affiliation": "Office of the President — STI",
        },
        {
            "name": "Dr Cosmas Mwikirize",
            "role": "Superintendent, Industrial Value Chains",
            "photo": "Dr-Cosmas-Mwikirize.jpg",
            "affiliation": "",
        },
        {
            "name": "Ms. Brenda Nakazibwe",
            "role": "Team Leader, Pathogen Economy Bureau",
            "photo": "Ms.-Brenda-Nakazibwe.webp",
            "affiliation": "",
        },
        {
            "name": "Pathogen Economy staff",
            "role": "Analytics, partnerships, and field economics",
            "photo": "",
            "affiliation": "Pathogen Economy Bureau",
        },
    ]


def load_thinktank_members() -> list[dict]:
    """Load roster from `assets/pe_thinktank/members.json`; fall back to defaults if missing or invalid."""
    default = _default_thinktank_members()
    if not THINKTANK_MEMBERS_JSON.exists():
        return default
    try:
        data = json.loads(THINKTANK_MEMBERS_JSON.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("members"), list):
            raw = data["members"]
        elif isinstance(data, list):
            raw = data
        else:
            return default
        out: list[dict] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            role = str(item.get("role", "")).strip()
            if not name or not role:
                continue
            photo_raw = str(item.get("photo", "")).strip()
            photo = Path(photo_raw).name if photo_raw else ""
            affiliation = str(item.get("affiliation", "")).strip()
            out.append(
                {
                    "name": name,
                    "role": role,
                    "photo": photo,
                    "affiliation": affiliation,
                }
            )
        return out if out else default
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return default


# Host realm → condition class → focus list (diseases / conditions)
DISEASE_CATALOG: dict[str, dict[str, list[str]]] = {
    "Human": {
        "Communicable": [
            "Cholera",
            "Malaria",
            "Typhoid",
            "Marburg",
            "Ebola",
            "COVID-19",
            "HIV/AIDS",
            "Tuberculosis",
            "Yellow fever",
        ],
        "NCD": [
            "Hypertension",
            "Type 2 diabetes",
            "Breast cancer",
            "Cervical cancer",
            "Chronic kidney disease",
            "Asthma (severe)",
        ],
        "Trauma & injuries": [
            "Road traffic injuries",
            "Burns",
            "Gender-based violence (clinical trauma)",
            "Occupational injuries",
        ],
    },
    "Animal": {
        "Communicable": [
            "Foot-and-mouth disease",
            "Rift Valley fever",
            "African swine fever",
            "Trypanosomiasis (nagana)",
            "Brucellosis",
            "Newcastle disease (poultry)",
        ],
        "NCD": [
            "Bovine mastitis (chronic)",
            "Metabolic disorders (dairy)",
            "Neoplasia (herd screening)",
        ],
        "Trauma & injuries": [
            "Predator attacks (livestock)",
            "Transport injuries",
            "Farm machinery trauma",
        ],
    },
    "Plant": {
        "Communicable": [
            "Maize lethal necrosis (viral complex)",
            "Banana Xanthomonas wilt",
            "Coffee leaf rust",
            "Cassava brown streak disease",
            "Tomato bacterial wilt",
        ],
        "NCD": [
            "Nutrient deficiency syndromes (multi-crop)",
            "Drought stress pathology",
            "Heat stress disorders",
        ],
        "Trauma & injuries": [
            "Hail / mechanical crop damage",
            "Post-harvest crushing losses",
        ],
    },
}


def diseases_for(host: str, condition: str) -> list[str]:
    return list(DISEASE_CATALOG.get(host, {}).get(condition, ["Cholera"]))


def _pe_context() -> tuple[str, str, str]:
    return (
        st.session_state.get("pe_host", "Human"),
        st.session_state.get("pe_condition", "Communicable"),
        st.session_state.get("pe_disease", "Cholera"),
    )


def render_pathogen_workspace_home(realtime_data: dict):
    host, condition, disease = _pe_context()
    risk = analyze_outbreak_risk(realtime_data)
    st.title("Pathogen workspace")
    st.caption(
        "Select **Host realm**, **Condition class**, and **Disease / condition** in the sidebar. "
        "All VDTEC, trial, regional, and 7-1-7 modules use this focus."
    )
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Host realm", host)
    with c2:
        st.metric("Condition class", condition)
    with c3:
        st.metric("Focus", disease)
    with c4:
        st.metric("Composite risk (sim.)", f"{risk['risk_score']}/100", risk["risk_level"])

    st.markdown(
        f"""
        **Strategic read:** Pathogen Economy translates signals into **VDTEC** (vaccines, drugs, diagnostics,
        consumables) and **medical devices** — what to develop, import, or export; first **100-day** surge volumes;
        and **return on public investment** for Government of Uganda. Current open-web urgency:
        **{realtime_data.get('social_urgency_score', 0)}/100** ({realtime_data.get('sim_recommended_tier', 'Routine')} posture).
        """
    )


def render_vdtec_roi(realtime_data: dict):
    host, condition, disease = _pe_context()
    risk = analyze_outbreak_risk(realtime_data)
    st.title("VDTEC & Pathogen ROI")
    st.caption(
        "Countermeasure rows: AI-enriched when API keys are configured; otherwise rule-based catalogue. "
        "**Red** = no licensed vaccine / critical product gap — Pathogen Economy **priority**."
    )

    c_ai, c_rst = st.columns(2)
    with c_ai:
        run_ai = st.button("Run AI enrich (API if configured)", key="vdtec_ai_btn")
    with c_rst:
        if st.button("Rules-based table only", key="vdtec_rule_btn"):
            st.session_state["vdtec_use_ai"] = False
            st.rerun()
    use_ai = bool(st.session_state.get("vdtec_use_ai", False)) or run_ai
    if run_ai:
        st.session_state["vdtec_use_ai"] = True

    df = generate_pe_countermeasures_rows(
        host=host,
        disease=disease,
        condition_class=condition,
        risk_score=risk["risk_score"],
        use_ai=use_ai,
    ).copy()
    surge = 1.0 + min(0.85, risk["risk_score"] / 130.0)
    df["Qty first 100 days (NMS-style est.)"] = (df["_qty_base"] * surge).round(0).astype(int)
    df["Develop / import / export"] = df.apply(
        lambda r: "Domestic scale-up" if r["Licensed (Y/N)"] == "N" and r["Category"] in ("Vaccine", "Drug", "Medical device") else "Import + buffer stock",
        axis=1,
    )
    df["Est. sales value Y1 (USD M, band)"] = (df["_rev_band"] * surge).round(2)
    df["GoU / PE ROI band (5y, illustrative)"] = df["_roi_band"]

    show = df[
        [
            "Category",
            "Product / intervention",
            "Licensed (Y/N)",
            "Qty first 100 days (NMS-style est.)",
            "Unit (illustrative)",
            "Develop / import / export",
            "Est. sales value Y1 (USD M, band)",
            "GoU / PE ROI band (5y, illustrative)",
        ]
    ]

    def _style_rows(row: pd.Series):
        styles = [""] * len(row)
        if row["Licensed (Y/N)"] == "N" and row["Category"] == "Vaccine":
            styles = ["background-color: #7f1d1d; color: #fecaca; font-weight: 600"] * len(row)
        elif row["Licensed (Y/N)"] == "N":
            styles = ["background-color: #451a03; color: #fed7aa"] * len(row)
        return styles

    st.dataframe(show.style.apply(_style_rows, axis=1), use_container_width=True, height=420)
    st.caption(
        "Quantities are **proxy** scalers from national programme envelopes — replace with National Medical Stores "
        "SKU forecasts and outbreak scenarios."
    )

    st.subheader("Harvest for Government of Uganda (illustrative bands)")
    tot_low = float(df["_gou_return_low"].sum() * surge)
    tot_high = float(df["_gou_return_high"].sum() * surge)
    inv = float(df["_gou_invest"].sum() * surge)
    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Indicative public investment (5y band)", f"${inv * 0.85:.1f}M – ${inv * 1.15:.1f}M")
    with c2:
        st.metric("Indicative fiscal & social return (5y)", f"${tot_low:.1f}M – ${tot_high:.1f}M")
    with c3:
        st.metric("Blended ROI (illustrative)", f"{(tot_low + tot_high) / 2 / max(inv, 0.1):.1f}x")


def render_clinical_trial_sites():
    host, condition, disease = _pe_context()
    st.title("Clinical trial sites (Uganda)")
    st.caption("Rank districts by **spatial risk** proxy for this disease — suggest sites where transmission intensity meets operational feasibility.")

    districts = [
        ("Kampala", 0.72),
        ("Wakiso", 0.64),
        ("Gulu", 0.58),
        ("Arua", 0.61),
        ("Mbale", 0.49),
        ("Kasese", 0.68),
        ("Mbarara", 0.45),
        ("Lira", 0.53),
        ("Hoima", 0.56),
        ("Fort Portal", 0.51),
    ]
    host_w = {"Human": 1.0, "Animal": 0.92, "Plant": 0.55}[host]
    records = []
    for district, base in districts:
        r = min(0.98, base * host_w)
        records.append(
            {
                "District": district,
                "Spatial risk score": round(r, 3),
                "Trial fit": "Phase II/III surge" if r > 0.65 else ("Phase I/II" if r > 0.52 else "Feasibility / comparator"),
                "Rationale": f"{disease}: catchment diversity + logistics hub score (sim.)",
            }
        )
    df = pd.DataFrame(records).sort_values("Spatial risk score", ascending=False)
    st.dataframe(df, use_container_width=True)
    top = ", ".join(df.head(3)["District"].tolist())
    st.success(f"Suggested priority districts for **{disease}** ({host}): **{top}**.")


def render_nms_100_day_surge():
    host, condition, disease = _pe_context()
    st.title("NMS 100-day surge quantities")
    st.caption("SKU-level planning view — links sidebar focus to illustrative surge multipliers (replace with NMS master data).")

    base_items = [
        ("ORS sachets", "course", 2_800_000),
        ("IV fluids (L)", "litre", 450_000),
        ("RDT kits", "test", 1_200_000),
        ("Gloves (boxes)", "box", 180_000),
        ("Syringes (auto-disable)", "unit", 4_500_000),
        ("Cotton / gauze (cases)", "case", 95_000),
        ("Laboratory consumables (panels)", "panel", 220_000),
    ]
    if host != "Human":
        base_items = [
            ("Cold chain vaccine doses", "dose", 800_000),
            ("Vet antibiotics (course)", "course", 120_000),
            ("Disinfectant (L)", "litre", 90_000),
            ("PPE kits", "kit", 40_000),
        ]
    mult = {"Communicable": 1.25, "NCD": 0.55, "Trauma & injuries": 0.95}.get(condition, 1.0)
    rows = []
    for name, u, q0 in base_items:
        q = int(q0 * mult * (1.1 if disease in ("Cholera", "Ebola", "Marburg") else 1.0))
        rows.append({"SKU": name, "Unit": u, "Qty first 100 days (est.)": q, "Notes": f"Scaled for {disease} / {host}"})
    st.dataframe(pd.DataFrame(rows), use_container_width=True)


def render_east_africa_regional(realtime_data: dict):
    st.title("East Africa regional market")
    st.caption("Populations (approx.) and **burden / export opportunity** when neighbours signal outbreaks (e.g. DRC).")

    rows = [
        ("Uganda", "UGA", 48.8, 0.72, "Primary manufacturing & NMS anchor"),
        ("Kenya", "KEN", 56.2, 0.88, "High private-sector VDTEC pull"),
        ("Tanzania", "TZA", 67.9, 0.76, "Cross-lake cholera / malaria corridors"),
        ("Rwanda", "RWA", 14.1, 0.61, "Quality-assured import partner"),
        ("Burundi", "BDI", 13.9, 0.70, "Border surge demand"),
        ("South Sudan", "SSD", 11.2, 0.82, "Humanitarian pipeline"),
        ("DR Congo", "COD", 102.3, 0.95, "Ebola / measles / cholera — **R&D trigger market**"),
    ]
    df = pd.DataFrame(
        rows,
        columns=["Country", "ISO", "Population (M, approx.)", "Burden / demand index (0–1, sim.)", "VDTEC strategic note"],
    )
    fig = px.bar(
        df,
        x="Country",
        y="Burden / demand index (0–1, sim.)",
        color="Population (M, approx.)",
        title="Regional demand intensity vs population (planning view)",
        color_continuous_scale="YlOrRd",
    )
    fig.update_layout(template="plotly_dark")
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(df, use_container_width=True)
    st.info(
        f"Live signal density (24h mentions): **{int(realtime_data.get('news_mentions', 0)):,}** — use as a **weak** proxy for regional media attention until EAC line lists are wired."
    )


def render_717_impact():
    host, condition, disease = _pe_context()
    st.title("7-1-7 early action benefits")
    st.caption("**7** days to detect, **1** day to notify, **7** days to mount public health response — estimate lives and costs saved if STI-EpiForecast enables this cadence.")

    c1, c2, c3 = st.columns(3)
    with c1:
        detect_d = st.slider("Days to detect (actual)", 1, 21, 7)
    with c2:
        notify_d = st.slider("Days to notify (actual)", 1, 7, 1)
    with c3:
        respond_d = st.slider("Days to response (actual)", 1, 21, 7)

    ideal_detect, ideal_notify, ideal_respond = 7, 1, 7
    delay_penalty = max(0, (detect_d - ideal_detect) * 0.04 + (notify_d - ideal_notify) * 0.09 + (respond_d - ideal_respond) * 0.035)
    pop_at_risk_m = st.number_input("Population at risk (M)", 0.5, 120.0, 12.0, 0.5)
    attack = st.slider("Attack rate if unchecked (%)", 0.1, 8.0, 2.0, 0.1) / 100.0
    cfr = st.slider("Case fatality without surge care (%)", 0.05, 6.0, 0.8, 0.05) / 100.0
    cost_per_case = st.number_input("Cost per case without control (USD)", 100, 8000, 1200, 50)

    cases_baseline = pop_at_risk_m * 1_000_000 * attack
    cases_averted_frac = min(0.72, max(0.12, 0.55 - delay_penalty))
    cases_averted = cases_baseline * cases_averted_frac
    deaths_averted = cases_averted * cfr * 0.9
    costs_saved = cases_averted * cost_per_case * 0.45

    st.markdown("#### If prediction + 7-1-7 discipline holds (model sketch)")
    m1, m2, m3 = st.columns(3)
    with m1:
        st.metric("Cases averted (vs delayed response)", f"{cases_averted:,.0f}")
    with m2:
        st.metric("Deaths averted (proxy)", f"{deaths_averted:,.0f}")
    with m3:
        st.metric("Treatment + control costs saved (USD M)", f"${costs_saved / 1e6:,.2f}")

    st.caption(
        f"Focus: **{disease}** ({host}, {condition}). Replace coefficients with calibrated health economics from MoH / WHO AFRO."
    )


def render_sti_venture_matrix():
    st.title("STI venture success matrix")
    st.caption("Weighted scorecard for **fund vs do not fund** — variables can be refined with Pathogen Economy leadership.")

    refresh = st.button("Regenerate variable weights (AI assist)", key="venture_ai_btn")
    if refresh or "venture_df" not in st.session_state:
        st.session_state["venture_df"] = generate_venture_matrix_ai(refresh=refresh)

    df = st.session_state["venture_df"]
    st.dataframe(df, use_container_width=True)

    weights = df.set_index("Variable")["Weight (0–1)"].astype(float)
    scores = df.set_index("Variable")["Project score (0–100)"].astype(float)
    total = float((weights * scores).sum() / weights.sum())
    threshold = st.slider("Fund if score ≥", 50, 90, 68)
    st.metric("Composite venture score", f"{total:.1f} / 100", "FUND" if total >= threshold else "DO NOT FUND (review)")
    st.caption("AI extends the rubric when keys are present; defaults are structured placeholders.")


def render_epi_thinktank():
    st.title("EPI-ThinkTank and Leadership")
    st.caption("Leadership and technical teams aligned to Pathogen Economy delivery.")

    members = load_thinktank_members()
    cols = st.columns(3)
    for i, m in enumerate(members):
        photo_name = (m.get("photo") or "").strip()
        p = THINKTANK_DIR / photo_name if photo_name else None
        with cols[i % 3]:
            if p is not None and p.is_file():
                st.image(str(p), use_container_width=True)
            else:
                st.markdown(
                    "<div style='width:100%;height:220px;border-radius:12px;background:#e5e7eb;display:flex;"
                    "align-items:center;justify-content:center;font-size:2rem;color:#334155;'>👤</div>",
                    unsafe_allow_html=True,
                )
            st.markdown(f"**{m['name']}**")
            st.caption(m["role"])
            aff = (m.get("affiliation") or "").strip()
            if aff:
                st.caption(aff)


def render_developers():
    st.title("Developers and Delivery Team")
    st.caption("Organized by role and delivery responsibility.")
    team = [
        {
            "name": "Abel STI",
            "role": "Product and Domain Lead",
            "affiliation": "Pathogen Economy Bureau / STI-OP",
            "scope": "Government use cases, programme requirements, and rollout priorities.",
            "photo": "",
        },
        {
            "name": "Moses Luzinda",
            "role": "Engineering Lead",
            "affiliation": "Platform Engineering",
            "scope": "Application architecture, data integrations, release quality, and deployment.",
            "photo": "",
        },
    ]
    cols = st.columns(2)
    for idx, member in enumerate(team):
        with cols[idx % 2]:
            photo_name = (member.get("photo") or "").strip()
            image_path = THINKTANK_DIR / photo_name if photo_name else None
            if image_path is not None and image_path.is_file():
                st.image(str(image_path), use_container_width=True)
            else:
                st.markdown(
                    "<div style='width:100%;height:190px;border-radius:12px;background:#e5e7eb;display:flex;"
                    "align-items:center;justify-content:center;font-size:2rem;color:#334155;margin-bottom:8px;'>👤</div>",
                    unsafe_allow_html=True,
                )
            st.markdown(
                f"""
                <div class="feature-card" style="min-height:200px;">
                    <div style="font-size:1.05rem;font-weight:700;margin-bottom:6px;">{member['name']}</div>
                    <div style="font-size:0.95rem;color:#166534;font-weight:700;">{member['role']}</div>
                    <div style="font-size:0.85rem;margin-top:4px;color:#475569;">{member['affiliation']}</div>
                    <div style="font-size:0.88rem;margin-top:12px;line-height:1.45;">{member['scope']}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


REPORTS_DIR = Path("uploads") / "reports"


def render_reports_library(realtime_data: dict):
    st.title("Reports library")
    st.caption("Download **summary** briefs only. Raw datasets stay in secured pipelines — not distributed from this shelf.")

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    host, condition, disease = _pe_context()
    risk = analyze_outbreak_risk(realtime_data)
    dashboard = realtime_data.get("dashboard") or compute_dashboard_metrics(realtime_data)
    rr1, rr2, rr3 = st.columns(3)
    with rr1:
        st.metric("Risk score", f"{int(risk.get('risk_score', 0))}/100", risk.get("risk_level", "n/a"))
    with rr2:
        st.metric("Open-web signals (24h)", f"{dashboard['open_web_total']:,}")
    with rr3:
        st.metric("Official health signals (24h)", f"{dashboard['official_total']:,}")

    st.markdown("#### Brief generation")
    if st.button("Generate one-page summary (text)", key="gen_summary_txt"):
        buf = io.StringIO()
        generated_utc = f"{datetime.utcnow().isoformat()}Z"
        risk_score = int(risk.get("risk_score", 0))
        risk_level = risk.get("risk_level", "Unknown")
        urgency = int(risk.get("social_urgency", 0))
        mentions = int(risk.get("mentions", 0))
        countries = int(risk.get("countries", 0))
        cholera_cases = int(realtime_data.get("cholera_cases", 0))
        malaria_cases = int(realtime_data.get("malaria_ug_cases_est", 0))
        tier = realtime_data.get("sim_recommended_tier", "Routine")
        last_updated = realtime_data.get("last_updated", "n/a")
        source_note = realtime_data.get("data_source", "n/a")
        recent_alerts = realtime_data.get("recent_alerts", [])
        if isinstance(recent_alerts, list):
            top_alerts = recent_alerts[:5]
        else:
            top_alerts = []

        buf.write("STI-EpiForecast App — Executive Summary\n")
        buf.write("=" * 52 + "\n")
        buf.write(f"Generated (UTC): {generated_utc}\n")
        buf.write(f"Feed snapshot time: {last_updated}\n")
        buf.write(f"Source context: {source_note}\n\n")

        buf.write("1) Strategic focus\n")
        buf.write("-" * 52 + "\n")
        buf.write(f"Host realm: {host}\n")
        buf.write(f"Condition class: {condition}\n")
        buf.write(f"Disease / condition focus: {disease}\n\n")

        buf.write("2) Situation overview\n")
        buf.write("-" * 52 + "\n")
        buf.write(f"Risk level: {risk_level} ({risk_score}/100)\n")
        buf.write(f"Recommended posture: {tier}\n")
        buf.write(f"Social urgency score: {urgency}/100\n")
        buf.write(f"Signal mentions (24h): {mentions:,}\n")
        buf.write(f"Affected countries: {countries}\n")
        buf.write(f"Estimated cholera cases: {cholera_cases:,}\n")
        buf.write(f"Estimated Uganda malaria cases: {malaria_cases:,}\n\n")

        buf.write("3) Priority signals\n")
        buf.write("-" * 52 + "\n")
        if top_alerts:
            for idx, alert in enumerate(top_alerts, start=1):
                buf.write(f"{idx}. {alert}\n")
        else:
            buf.write("No alerts available in current snapshot.\n")
        buf.write("\n")

        buf.write("4) Operational priorities (next 7-14 days)\n")
        buf.write("-" * 52 + "\n")
        buf.write("1. Validate hotspots and surveillance anomalies with district teams.\n")
        buf.write("2. Align first 100-day commodity assumptions in VDTEC workflows.\n")
        buf.write("3. Prioritize diagnostics and treatment readiness where alerts recur.\n")
        buf.write("4. Track import, local production, and stock buffer options for critical gaps.\n")
        buf.write("5. Prepare weekly executive brief updates for leadership review.\n\n")

        buf.write("5) VDTEC and investment direction\n")
        buf.write("-" * 52 + "\n")
        buf.write("Use the `VDTEC & Pathogen ROI` module to review:\n")
        buf.write("- Countermeasure gaps (red rows = priority)\n")
        buf.write("- First 100-day quantity estimates\n")
        buf.write("- Domestic scale-up vs import pathways\n")
        buf.write("- ROI bands for public and ecosystem investment decisions\n\n")

        buf.write("6) Caveats\n")
        buf.write("-" * 52 + "\n")
        buf.write("This summary is generated from cached/open-web signals and illustrative planning indicators.\n")
        buf.write("Use ministry, NMS, and district validated data for formal operational approvals.\n")
        st.session_state["pe_summary_txt"] = buf.getvalue()

    if st.session_state.get("pe_summary_txt"):
        st.download_button(
            "Download latest generated summary (.txt)",
            st.session_state["pe_summary_txt"],
            file_name=f"STI_EpiForecast_summary_{disease.replace(' ', '_')}.txt",
            mime="text/plain",
            key="dl_gen_summary_txt",
        )

    st.markdown("### Social + official health-site signal report")
    st.caption(
        "Build a focused signal report from social/open-web channels plus official health-site domains "
        "(WHO, CDC, UN Global Health pages detected through GDELT domain monitoring)."
    )
    social_channels = realtime_data.get("social_channels") or {}
    health_channels = realtime_data.get("health_site_signals") or {}
    report_rows = []
    for source, value in social_channels.items():
        report_rows.append({"Channel": source, "Type": "Social/Open web", "Signals_24h": int(value or 0)})
    for source, value in health_channels.items():
        report_rows.append({"Channel": source, "Type": "Official health sites", "Signals_24h": int(value or 0)})
    if report_rows:
        df_signals = pd.DataFrame(report_rows).sort_values(["Type", "Signals_24h"], ascending=[True, False])
        social_total = int(df_signals[df_signals["Type"] == "Social/Open web"]["Signals_24h"].sum())
        health_total = int(df_signals[df_signals["Type"] == "Official health sites"]["Signals_24h"].sum())
        combined_total = social_total + health_total
        social_arrow = "↑ rising" if social_total >= 1400 else ("→ steady" if social_total >= 500 else "↓ low")
        health_arrow = "↑ rising" if health_total >= 60 else ("→ steady" if health_total >= 20 else "↓ low")
        signal_mix = "Social-dominant" if social_total > health_total * 2 else ("Balanced" if health_total > 0 else "Sparse")
        k1, k2, k3 = st.columns(3)
        with k1:
            st.metric("Social signal volume (24h)", f"{social_total:,}", social_arrow)
        with k2:
            st.metric("Official health-site volume (24h)", f"{health_total:,}", health_arrow)
        with k3:
            st.metric("Combined signal volume (24h)", f"{combined_total:,}", signal_mix)

        mix_df = df_signals.groupby("Type", as_index=False)["Signals_24h"].sum()
        fig_mix = px.bar(
            mix_df,
            x="Type",
            y="Signals_24h",
            color="Type",
            title="Signal mix: social/open-web vs official health sites (24h)",
            color_discrete_map={
                "Social/Open web": "#2563eb",
                "Official health sites": "#16a34a",
            },
        )
        fig_mix.update_layout(showlegend=False)
        st.plotly_chart(fig_mix, use_container_width=True)

        top_channels = df_signals.sort_values("Signals_24h", ascending=False).head(8)
        fig_top = px.bar(
            top_channels,
            x="Signals_24h",
            y="Channel",
            color="Type",
            orientation="h",
            title="Top channels by signal count (24h)",
            color_discrete_map={
                "Social/Open web": "#3b82f6",
                "Official health sites": "#22c55e",
            },
        )
        fig_top.update_layout(yaxis={"categoryorder": "total ascending"})
        st.plotly_chart(fig_top, use_container_width=True)

        st.dataframe(df_signals, use_container_width=True, hide_index=True)
        if st.button("Generate social + health signal report (.txt)", key="gen_social_health_txt"):
            buf = io.StringIO()
            generated_utc = f"{datetime.utcnow().isoformat()}Z"
            buf.write("STI-EpiForecast - Social and Health-Site Signals Report\n")
            buf.write("=" * 62 + "\n")
            buf.write(f"Generated (UTC): {generated_utc}\n")
            buf.write(f"Snapshot time: {realtime_data.get('last_updated', 'n/a')}\n")
            buf.write(f"Social signal volume (24h): {social_total:,} ({social_arrow})\n")
            buf.write(f"Official health-site volume (24h): {health_total:,} ({health_arrow})\n")
            buf.write(f"Combined signal volume (24h): {combined_total:,}\n")
            buf.write(
                "Coverage note: WHO and CDC values are derived from their public feed endpoints; "
                "UN Global Health is domain signal monitoring via GDELT (un.org). "
                "Social values from X/LinkedIn/Meta require official API keys and permissions.\n\n"
            )
            buf.write("A) Social/open-web channels (24h)\n")
            buf.write("-" * 62 + "\n")
            for row in df_signals[df_signals["Type"] == "Social/Open web"].itertuples():
                buf.write(f"- {row.Channel}: {row.Signals_24h:,}\n")
            buf.write("\nB) Official health-site channels (24h)\n")
            buf.write("-" * 62 + "\n")
            for row in df_signals[df_signals["Type"] == "Official health sites"].itertuples():
                buf.write(f"- {row.Channel}: {row.Signals_24h:,}\n")
            buf.write("\nC) How to use this report\n")
            buf.write("-" * 62 + "\n")
            buf.write("1. Cross-check spikes against district events and routine surveillance reports.\n")
            buf.write("2. Use WHO/CDC/UN domain spikes to prioritize rapid desk review and evidence validation.\n")
            buf.write("3. Combine signal velocity with forecast and hotspot modules before policy actions.\n")
            st.session_state["social_health_report_txt"] = buf.getvalue()
        if st.session_state.get("social_health_report_txt"):
            st.download_button(
                "Download social + health signal report (.txt)",
                st.session_state["social_health_report_txt"],
                file_name=f"STI_EpiForecast_social_health_signals_{disease.replace(' ', '_')}.txt",
                mime="text/plain",
                key="dl_social_health_txt",
            )
    else:
        st.info("Signal report preview unavailable in this snapshot.")

    st.markdown("### Uploaded report assets")
    files = sorted(
        (p for p in REPORTS_DIR.glob("*") if p.is_file() and p.name != ".gitkeep"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not files:
        st.info("No uploaded reports yet. Admins can upload PDF/DOCX summaries under **Admin → Report uploads**.")
    else:
        st.caption("Most recent report files:")
        for idx, f in enumerate(files[:40]):
            if f.is_file():
                data = f.read_bytes()
                st.download_button(
                    f"Download {f.name}",
                    data,
                    file_name=f.name,
                    key=f"dl_{f.name}_{idx}",
                )


def render_pe_leadership_strip():
    st.markdown(
        """
        <div class="hero-card" style="margin-bottom:14px;padding:16px 20px;">
        <div style="font-size:0.95rem;color:#166534;font-weight:700;margin-bottom:10px;">Science, Technology &amp; Innovation - Office of the President</div>
        <div style="display:flex;flex-wrap:wrap;gap:10px 16px;font-size:0.9rem;font-weight:700;">
        <span style="color:#14532d;">Minister, STI-OP</span>
        <span style="color:#166534;">Superintendent, Industrial Value Chains</span>
        <span style="color:#1d4ed8;">Team Leader, Pathogen Economy Bureau</span>
        <span style="color:#7c2d12;">Pathogen Economy Staff</span>
        </div>
        <div style="margin-top:12px;padding-top:12px;border-top:1px solid #d6e3da;font-size:0.86rem;color:#334155;line-height:1.45;">
        Supporting STI-OP programmes with practical intelligence for vaccines, drugs, diagnostics, consumables, devices, and surge planning.
        </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
