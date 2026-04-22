"""
Build a comprehensive government-ready handbook for STI-EPI-FORECAST.
Uses only Python standard library and writes a .docx directly.
"""
from __future__ import annotations

from pathlib import Path

from build_user_manual_docx import write_docx


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    out = root / "STI-EPI-FORECAST_Comprehensive_Government_Handbook.docx"

    sections: list[tuple[str, list[str]]] = [
        (
            "Part 1 — Executive overview and purpose",
            [
                "STI-EPI-FORECAST is a government-oriented epidemic intelligence platform tailored to Uganda-focused surveillance, forecasting, and response coordination.",
                "The platform combines open-web signal ingestion, role-based workflows, dashboard analytics, AI-assisted alert summarization, and operational action guidance.",
                "This handbook is designed for Ministry of Health leadership, surveillance teams, technical administrators, district command centers, and partner stakeholders.",
                "Use this handbook as a full reference for presentation, deployment, governance, operations, and troubleshooting.",
            ],
        ),
        (
            "Part 2 — Core objectives",
            [
                "Detect outbreak signal acceleration as early as possible using open-web and news proxies.",
                "Support rapid operational planning using role-based module views and action recommendations.",
                "Provide AI-generated risk summaries and configurable alert routing to authorized administrators.",
                "Offer a web dashboard for strategic decision-making and a mobile app prototype for field-facing situational awareness.",
            ],
        ),
        (
            "Part 3 — System architecture (high level)",
            [
                "Web frontend: Streamlit application entry point at app.py.",
                "Page render modules: app_pages.py contains feature-specific rendering functions.",
                "Data and intelligence services: data_services.py contains feed adapters, risk scoring, AI calls, and notification logic.",
                "API backend: api_server.py provides FastAPI endpoints for health checks, NLP alerts, chat proxy, model listing, and SEIR forecast.",
                "Mobile client: mobile-app directory contains Expo React Native application.",
                "Automation scripts: scripts directory includes document generators and helper tooling.",
            ],
        ),
        (
            "Part 4 — Role-based governance model",
            [
                "National Incident Commander: executive posture, escalation, and cross-module command decisions.",
                "Surveillance Analyst: monitoring feed quality, anomalies, and regional signal verification.",
                "Epidemiology Modeler: forecasting, intervention scenarios, and analytical calibration.",
                "Border Operations Lead: corridor and entry-point risk operations.",
                "Policy and Investment Lead: response financing and policy prioritization.",
                "System Administrator: platform settings, integration operations, and reliability checks.",
            ],
        ),
        (
            "Part 5 — Navigation and layout",
            [
                "Sidebar includes role selector, navigation radio, feed controls, diagnostics, quick actions, and operational status notes.",
                "Main panel renders module-specific analytics and controls based on selected role and active page.",
                "Role context panel summarizes mission and workflow handoff guidance for presentation-grade continuity.",
            ],
        ),
        (
            "Part 6 — Data sources and signal semantics",
            [
                "Real source: OWID malaria Uganda mortality dataset.",
                "Open-web source: GDELT article volume for outbreak-related terms.",
                "Open-web source: Reddit public JSON search (time-windowed recent volume).",
                "Open-web source: Hacker News Algolia API volume.",
                "Optional keyed source: NewsAPI total results for disease-topic query.",
                "Illustrative elements remain clearly labelled where not yet linked to official district APIs.",
            ],
        ),
        (
            "Part 7 — Dashboard module (National Outbreak Operations Dashboard)",
            [
                "Purpose: fast situational picture for command-level awareness.",
                "Top KPI row provides headline metrics for cholera estimate, malaria estimate, countries under watch, and news signal volume.",
                "Focus metric selector reorders emphasis for faster scan and briefing flow.",
                "Trend chart window control allows short and medium horizon framing.",
                "Quick mode reduces heavy render cost for faster first paint in live demos.",
                "Map and heavier visuals are deferred via expanders for performance control.",
            ],
        ),
        (
            "Part 8 — Executive Briefing module",
            [
                "Single-screen policy-level summary suitable for meetings and decision memos.",
                "Provides risk posture, signal intensity, watch-country count, and current update time.",
                "Includes timeline and action checklist framing for 24–72 hour governance windows.",
            ],
        ),
        (
            "Part 9 — Global Surveillance module",
            [
                "Heatmap tab shows illustrative cross-country intensity for communication and regional framing.",
                "AI Risk Intelligence tab provides alert narratives through AI service or deterministic fallback.",
                "Source Monitor tab reports feed status per source and freshness indicators.",
            ],
        ),
        (
            "Part 10 — Uganda Hotspots module",
            [
                "District-level risk visualization for localized prioritization.",
                "Supports risk sorting, risk labels, case estimate context, and trend labels.",
                "Suitable for district command-center review sessions and hotspot briefing.",
            ],
        ),
        (
            "Part 11 — Disease Profiler module",
            [
                "Compares disease profiles through host composition, age vulnerability, and environment sensitivity.",
                "Used for contextual understanding and communication rather than definitive epidemiological inference.",
            ],
        ),
        (
            "Part 12 — Forecast Lab module",
            [
                "SEIR-based trajectory modeling with intervention effectiveness controls.",
                "Travel corridor risk panel supports border operations planning context.",
                "Statistical baseline panel visualizes distribution and abnormality framing.",
                "Machine learning placeholder indicates future path for trained predictive models.",
            ],
        ),
        (
            "Part 13 — Action Plan module",
            [
                "Contains operations, social/open-web interpretation, and scenario planning tabs.",
                "Provides disease-specific procurement, prevention, and strategic investment guidance.",
                "Includes checklist controls for immediate planning cycles and command tracking.",
            ],
        ),
        (
            "Part 14 — ROI and Financing module",
            [
                "Supports policy and investment narrative through cost-benefit framing.",
                "Outputs investment totals, benefits, net gain, and ROI multiplier over selected horizon.",
                "Designed for strategic budget discussions and preparedness investment justification.",
            ],
        ),
        (
            "Part 15 — Administration and Governance module",
            [
                "Central place for configuration posture and integration visibility.",
                "Includes risk email routing controls for daily and emergency communication.",
                "Provides test email execution path for operational validation.",
            ],
        ),
        (
            "Part 16 — AI integration model",
            [
                "The app supports OpenAI-compatible upstream endpoints through configurable environment variables.",
                "Credential resolution supports CURSOR_API_KEY, AI_API_KEY, OPENAI_API_KEY, and XAI_API_KEY paths.",
                "Base URL and model selection are also environment-configurable.",
                "If AI is unavailable, fallback narratives ensure continuity and no dashboard dead-end.",
            ],
        ),
        (
            "Part 17 — FastAPI endpoint catalog",
            [
                "GET /health",
                "GET /v1/catalog/public-apis",
                "GET /v1/models",
                "POST /v1/chat/completions (OpenAI-compatible proxy)",
                "POST /v1/cursor/chat (convenience endpoint naming, not official Cursor product API)",
                "POST /v1/nlp-alerts",
                "POST /v1/forecast/seir",
            ],
        ),
        (
            "Part 18 — Email alert workflow",
            [
                "Admin config is persisted in admin_alerts_config.json.",
                "Daily summaries trigger at configured UTC hour.",
                "Emergency alerts trigger when risk score crosses threshold with cooldown controls.",
                "SMTP variables govern transport and sender identity.",
                "Workflow supports recipient management from Admin page.",
            ],
        ),
        (
            "Part 19 — Required environment variables",
            [
                "AI routing: CURSOR_API_KEY, CURSOR_API_BASE_URL, CURSOR_AI_MODEL (or AI_* / OPENAI_* equivalents).",
                "Feed enrichment: NEWSAPI_KEY optional.",
                "Alert API bridge: ALERTS_API_URL optional override.",
                "Email transport: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, SMTP_USE_TLS, ALERT_FROM_EMAIL.",
            ],
        ),
        (
            "Part 20 — Performance design and controls",
            [
                "Caching used across malaria data, outbreak feeds, and NLP alert generation.",
                "Quick mode and expander-based deferred rendering improve first load responsiveness.",
                "External source timeouts and parallel calls are configured to reduce wait inflation.",
                "Manual refresh controls allow operators to force recache when needed.",
            ],
        ),
        (
            "Part 21 — Mobile application (Expo)",
            [
                "Mobile app includes API URL settings for local/LAN backend targeting.",
                "Disease switching, surveillance alert list, travel risk visualization, and action text are available.",
                "Use start:expo for LAN and start:expo:tunnel for cross-network QR access.",
            ],
        ),
        (
            "Part 22 — Deployment to Streamlit Community Cloud",
            [
                "Repository: MosesLuzinda/STI-EPIFORECAST-DASHBOARD",
                "Branch: main",
                "Main file path: app.py",
                "requirements.txt is required and included for dependency install.",
                "Configure secrets/environment variables in Streamlit Cloud Advanced settings.",
            ],
        ),
        (
            "Part 23 — Local operations quick start",
            [
                "From project root, run start-all.ps1 to open API, Streamlit, and Expo processes.",
                "API docs available at http://127.0.0.1:8000/docs.",
                "Streamlit typically starts on localhost 8501+ depending on free port.",
                "Expo default configured port is 8082 to avoid common 8081 conflicts.",
            ],
        ),
        (
            "Part 24 — Security and governance considerations",
            [
                "Never commit .env with real credentials.",
                "Use role-appropriate access procedures when sharing outputs.",
                "Treat AI-generated text as assistive intelligence requiring human validation.",
                "For production, add audit logging, auth, and formal data governance controls.",
            ],
        ),
        (
            "Part 25 — Presentation guidance for Government briefings",
            [
                "Begin with Executive Briefing for strategic posture.",
                "Move to Dashboard for operational signal trends.",
                "Use Hotspots and Action Plan for district-level prioritization.",
                "Use ROI and Financing for policy and resource justification discussions.",
                "Conclude with Admin/Governance status to show institutional readiness.",
            ],
        ),
        (
            "Part 26 — Troubleshooting",
            [
                "If Streamlit shows blank top bar issues, confirm CSS header override in app.py.",
                "If QR fails for Expo, switch to tunnel mode and verify network/firewall constraints.",
                "If feeds appear stale, use refresh controls and verify source availability.",
                "If AI output falls back, validate keys/base URL/model and backend endpoint health.",
                "If emails do not send, validate SMTP credentials, host/port/TLS, and recipient list.",
            ],
        ),
        (
            "Part 27 — Future roadmap (recommended)",
            [
                "Integrate official district datasets (e.g., DHIS2 exports/APIs) for non-simulated district analytics.",
                "Introduce authenticated role access and audit trails.",
                "Add calibrated forecasting and supervised ML models trained on historical records.",
                "Introduce scheduled background worker for email and report generation independent of UI sessions.",
                "Add PDF/brief export workflows for cabinet and district reporting packets.",
            ],
        ),
        (
            "Part 28 — File-by-file technical map",
            [
                "app.py: Streamlit entry point, role routing, sidebar orchestration, dashboard rendering flow.",
                "app_pages.py: feature module renderers and admin UI.",
                "data_services.py: feed ingestion, risk analysis, AI generation, notification services.",
                "api_server.py: backend endpoints and OpenAI-compatible proxy.",
                "mobile-app/App.js: mobile UI and API interaction logic.",
                "start-all.ps1: convenience launcher for API + web + mobile.",
                "requirements.txt: deployment dependency list.",
            ],
        ),
        (
            "Part 29 — Acceptance checklist for presentation readiness",
            [
                "Application starts successfully for API, web, and mobile.",
                "Dashboard displays with high-contrast UI and role-aligned module visibility.",
                "Feed status and source monitor indicators update as expected.",
                "AI alerts generate (or fallback gracefully) with clear source labeling.",
                "Admin email settings save and test email path validates.",
                "Repository includes reproducible setup artifacts and dependency manifest.",
            ],
        ),
        (
            "Part 30 — Closing statement",
            [
                "STI-EPI-FORECAST is now structured as a professional, government-facing decision-support platform with clear operational modules, deployment pathways, and governance controls.",
                "This handbook is intended to be used as both onboarding material and executive reference during preparedness and response engagements.",
            ],
        ),
    ]

    write_docx(out, sections)
    print(f"Wrote: {out}")


if __name__ == "__main__":
    main()
