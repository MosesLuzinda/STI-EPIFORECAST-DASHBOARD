"""
Build STI-EPI-FORECAST_User_Manual.docx using only the Python standard library (no python-docx).
"""
from __future__ import annotations

import html
import zipfile
from datetime import date
from pathlib import Path


def _p(text: str, bold: bool = False) -> str:
    esc = html.escape(text, quote=False)
    b = "<w:b/>" if bold else ""
    return (
        f'<w:p><w:r><w:rPr>{b}</w:rPr><w:t xml:space="preserve">{esc}</w:t></w:r></w:p>'
    )


def _build_document_xml(sections: list[tuple[str, list[str]]]) -> str:
    parts: list[str] = []
    parts.append(_p("STI-EPI-FORECAST — User manual (buttons & features)", bold=True))
    parts.append(_p(f"Generated: {date.today().isoformat()}", bold=False))
    parts.append(_p("", bold=False))
    parts.append(
        _p(
            "This document describes the Streamlit web dashboard, the FastAPI backend, and the Expo mobile prototype.",
            bold=False,
        )
    )
    parts.append(_p("", bold=False))
    for title, lines in sections:
        parts.append(_p(title, bold=True))
        for line in lines:
            parts.append(_p(line, bold=False))
        parts.append(_p("", bold=False))
    body = "".join(parts)
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    {body}
    <w:sectPr>
      <w:pgSz w:w="12240" w:h="15840"/>
      <w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/>
    </w:sectPr>
  </w:body>
</w:document>"""


def write_docx(out_path: Path, sections: list[tuple[str, list[str]]]) -> None:
    document_xml = _build_document_xml(sections)
    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""
    rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""
    doc_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>
"""
    core_props = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
  xmlns:dc="http://purl.org/dc/elements/1.1/"
  xmlns:dcterms="http://purl.org/dc/terms/"
  xmlns:dcmitype="http://purl.org/dc/dcmitype/"
  xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>STI-EPI-FORECAST User Manual</dc:title>
  <dc:creator>STI-EPI-FORECAST</dc:creator>
  <cp:lastModifiedBy>Build script</cp:lastModifiedBy>
  <dcterms:created xsi:type="dcterms:W3CDTF">{date.today().isoformat()}</dcterms:created>
  <dcterms:modified xsi:type="dcterms:W3CDTF">{date.today().isoformat()}</dcterms:modified>
</cp:coreProperties>"""
    app_props = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
  xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>STI-EPI-FORECAST</Application>
</Properties>"""

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", rels)
        zf.writestr("word/document.xml", document_xml)
        zf.writestr("word/_rels/document.xml.rels", doc_rels)
        zf.writestr("docProps/core.xml", core_props)
        zf.writestr("docProps/app.xml", app_props)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    out = root / "STI-EPI-FORECAST_User_Manual.docx"
    sections: list[tuple[str, list[str]]] = [
        (
            "1. How to run the system",
            [
                "Web dashboard: from project folder run: venv\\Scripts\\python.exe -m streamlit run app.py (or streamlit run app.py if on PATH). Default browser URL is usually http://localhost:8501 .",
                "API server: python -m uvicorn api_server:app --host 0.0.0.0 --port 8000 . API docs: http://localhost:8000/docs .",
                "Mobile (Expo Go): in folder mobile-app run npm run start:expo , then scan the QR in the terminal with Expo Go. Set API base URL in the app to your PC LAN IP if using a phone (not 127.0.0.1).",
            ],
        ),
        (
            "2. Global layout (all screens)",
            [
                "Role banner (top of main area): shows your selected role, mission text, and a suggested next module. It updates when you change role or page.",
                "Left sidebar: logo (if logo1.png exists), app title, role selector, navigation radio list, refresh and feed tools, quick-action buttons, footer caption.",
                "Main area: content for the selected module (charts, tables, maps, forms).",
            ],
        ),
        (
            "3. Sidebar — controls and what they do",
            [
                "Role workspace (dropdown): chooses one of National Incident Commander, Surveillance Analyst, Epidemiology Modeler, Border Operations Lead, Policy & Investment Lead, System Administrator. Each role shows only the modules relevant to that role.",
                "Navigation (radio list): switches the main screen. The list changes based on role.",
                "Refresh Live Feeds (button): clears Streamlit cached data (st.cache_data), updates the last-manual-refresh time, and reloads the app so malaria and outbreak feeds fetch again.",
                "Last manual refresh (caption): time of the last manual refresh from the button above.",
                "Feed status panel: OWID malaria and Outbreak signal health (ok / degraded) and last successful fetch time for each.",
                "Retry Malaria (button): marks a malaria retry, clears the malaria cache on next run, and reloads to pull OWID malaria again.",
                "Retry Outbreak (button): same pattern for the simulated/GDELT-style outbreak feed.",
                "Feed diagnostics (text): per-feed last latency, retry count, and last error snippet if any.",
                "Quick actions — Dashboard (button): jumps to Dashboard (hidden if not in your role’s module list).",
                "Quick actions — Briefing (button): jumps to Executive Briefing (only if that module is in your role list).",
                "Quick actions — Forecast (button): jumps to Forecast Lab (if available for role).",
                "Quick actions — Global (button): jumps to Global Surveillance (if available for role).",
                "Disabled state: when a quick-nav target is already the current page, that button is disabled to avoid useless clicks.",
            ],
        ),
        (
            "4. Executive Briefing",
            [
                "Purpose: one-screen summary for decision makers (risk, timeline, actions).",
                "Metrics: overall risk level, signal intensity, countries under watch, update time — derived from the live outbreak snapshot.",
                "National posture panel: short text tied to risk colour.",
                "Incident Timeline table: illustrative last-7-days events for command review (prototype data).",
                "Decision Actions: priority-style messages for 24–72h response.",
                "Governance checks (checkboxes): local tracking only (not saved to a server); use for meeting prep checklists.",
            ],
        ),
        (
            "5. Dashboard (Live Outbreak)",
            [
                "Caption line: shows last update time and data source string for the outbreak snapshot.",
                "Degraded warning: appears if the outbreak feed is in baseline mode (e.g. GDELT enrichment unavailable).",
                "Refresh Dashboard Feed (button): same as sidebar refresh — clears caches and reloads.",
                "Focus metric (dropdown): Cholera, Malaria, or News signal — reorders the four KPI cards so the chosen topic appears first.",
                "Trend window (days) (slider): 7–30 days; controls length of the simulated cholera trend line chart.",
                "Right column caption: notes that external HealthMap embed was removed for a cleaner workflow.",
                "KPI cards: four metrics (cholera estimate, malaria estimate, affected countries, news mentions); values come from the outbreak engine plus OWID where noted on charts.",
                "Situation trends chart: simulated cholera trend over the selected window.",
                "Malaria mortality chart: real Uganda time series from Our World in Data when the feed succeeds.",
                "Priority alerts: list from outbreak snapshot; visual legend explains colour meaning for risk messaging.",
                "Signal intensity: progress bar 0–100 plus High/Medium/Low label; escalation text changes by band.",
                "Hotspots map: interactive Folium map of Uganda with two markers if folium and streamlit-folium are installed; otherwise an info message with pip install hint.",
            ],
        ),
        (
            "6. Global Surveillance",
            [
                "Tab Global Heatmap: choropleth of simulated regional discussion intensity for a fixed country watchlist.",
                "Tab NLP Alerts: calls generate_ai_nlp_alerts — first your FastAPI POST /v1/nlp-alerts if ALERTS_API_URL is set/reachable, else direct AI env, else fallback text. Shows four alert lines and a legend line.",
                "Tab Source Monitor: KPIs for signal volume and feed freshness; shows whether GDELT enrichment is on or baseline; reminds that AI uses /v1/nlp-alerts with fallback.",
            ],
        ),
        (
            "7. Uganda Hotspots",
            [
                "Disease focus (dropdown): Cholera, Malaria, Typhoid, Marburg — drives risk scaling and charts.",
                "Metrics: count of high-risk districts, highest district name, max risk score.",
                "Bar chart: district risk scores coloured by High/Medium/Low.",
                "Table: district-level simulated risk, label, estimated 14-day cases, trend.",
            ],
        ),
        (
            "8. Disease Profiler",
            [
                "Disease focus (dropdown): same four diseases; updates all three charts.",
                "Host origin donut: simulated host mix (Humans/Animals/Birds).",
                "Age vulnerability bar: simulated relative risk by age band.",
                "Environment line: temperature vs spread potential (illustrative curve).",
            ],
        ),
        (
            "9. Forecast Lab",
            [
                "Disease focus (dropdown): sets base transmission parameter for the SEIR loop.",
                "Total population (number input): Uganda default ~48M; used as N in SEIR.",
                "Initial infected (number input): starting I compartment.",
                "Forecast horizon (slider): 30–100 days of projection.",
                "Intervention effectiveness (slider): 0–0.9; reduces effective beta.",
                "SEIR chart: Susceptible, Exposed, Infected, Recovered over time (animated transition on layout).",
                "Travel risk bars: Entebbe, Malaba, Mpondwe, Elegu — scores derived from base travel weights and model beta.",
                "Statistical normal baseline: histogram of recent daily new infections with overlaid normal PDF (mean/std from last 30 daily deltas).",
                "Random Forest placeholder: synthetic outbreak probability from final infected scale; caption explains replacement with a real model.",
            ],
        ),
        (
            "10. Action Plan (Uganda)",
            [
                "Disease focus (dropdown): selects disease-specific procurement, prevention, and investment text blocks.",
                "Top metrics: illustrative P1 alert count, high-risk districts, response window.",
                "Priority messages: three stacked alerts (P1–P3 style).",
                "Recommended actions: three coloured panels — Buy, Prevent, Invest — content switches with disease.",
                "Bullet lists: general operational steps in two columns.",
                "72-hour checklist (checkboxes): local UI state only for team task tracking.",
            ],
        ),
        (
            "11. ROI & Financing",
            [
                "Inputs: government annual preparedness spend, estimated avoided losses per year, time horizon in years.",
                "Outputs: total investment, total benefit, net benefit, ROI multiple; bar chart of costs vs benefits; cumulative line chart over years.",
                "Info panel: reminds that figures are illustrative until replaced with official national data.",
            ],
        ),
        (
            "12. Admin",
            [
                "Read-only description of current integrations (OWID malaria, HealthMap references in older docs, simulated outbreak KPIs) and suggested next API targets (WHO, DHIS2, etc.).",
            ],
        ),
        (
            "13. FastAPI backend (reference)",
            [
                "GET /health — returns JSON status for uptime checks.",
                "POST /v1/nlp-alerts — JSON body: disease, news_mentions, cholera_cases, affected_countries; returns alerts[] and source ai|fallback.",
                "POST /v1/forecast/seir — JSON body for SEIR parameters; returns daily points.",
                "Environment: AI_API_KEY or XAI_API_KEY, AI_BASE_URL, AI_MODEL for upstream LLM when generating alerts.",
            ],
        ),
        (
            "14. Mobile app (Expo) — screens and controls",
            [
                "API Settings: text field for backend base URL (no trailing path); Apply API URL saves and refetches NLP alerts.",
                "Disease Focus pills: Cholera, Malaria, Typhoid, Marburg — switches disease and reloads alerts.",
                "Global Surveillance Alerts: shows up to four lines from POST /v1/nlp-alerts or fallback; shows source label (ai or fallback).",
                "Travel Risk: horizontal bars for Entebbe, Malaba, Mpondwe, Elegu (static prototype scores).",
                "SEIR snapshot: short multi-step infected projection (illustrative, not full SEIR).",
                "Uganda Action Plan: Buy / Prevent / Invest lines change with disease selection.",
            ],
        ),
        (
            "15. Data & limitations",
            [
                "Malaria death rate for Uganda: real public CSV via Our World in Data when the network allows.",
                "Cholera counts, district risk tables, SEIR parameters, and many KPIs: prototype / simulated unless you connect MoH or other official feeds.",
                "AI alerts: depend on your API keys and network; otherwise deterministic fallback text is shown.",
            ],
        ),
    ]
    write_docx(out, sections)
    print(f"Wrote: {out}")


if __name__ == "__main__":
    main()
