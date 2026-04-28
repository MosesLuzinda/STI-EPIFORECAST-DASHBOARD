"""
Build STI-EPI-FORECAST_Online_Features_And_Roadmap.docx using only Python stdlib.
"""
from __future__ import annotations

import html
import zipfile
from datetime import date
from pathlib import Path


def _p(text: str, bold: bool = False) -> str:
    esc = html.escape(text, quote=False)
    b = "<w:b/>" if bold else ""
    return f'<w:p><w:r><w:rPr>{b}</w:rPr><w:t xml:space="preserve">{esc}</w:t></w:r></w:p>'


def _build_document_xml(sections: list[tuple[str, list[str]]]) -> str:
    parts: list[str] = []
    parts.append(_p("STI-EPI-FORECAST - Online Features and Rollout Roadmap", bold=True))
    parts.append(_p(f"Generated: {date.today().isoformat()}"))
    parts.append(_p(""))
    parts.append(
        _p(
            "This document lists the capabilities required to run the system online in production, plus a phased delivery roadmap.",
        )
    )
    parts.append(_p(""))
    for title, lines in sections:
        parts.append(_p(title, bold=True))
        for line in lines:
            parts.append(_p(line))
        parts.append(_p(""))
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
  <dc:title>STI-EPI-FORECAST Online Features and Roadmap</dc:title>
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
    out = root / "STI-EPI-FORECAST_Online_Features_And_Roadmap.docx"

    sections: list[tuple[str, list[str]]] = [
        (
            "1. Core Product Features",
            [
                "- Authentication: email/password, optional OAuth, and 2FA for sensitive roles.",
                "- Role-based access control: admin, analyst, decision-maker, and viewer permissions.",
                "- Organization support if multiple institutions will share one platform.",
                "- Saved dashboards, watchlists, and report exports (PDF/CSV).",
                "- Real-time alerting channels: email, SMS, WhatsApp, and webhook notifications.",
            ],
        ),
        (
            "2. Data and Integration Features",
            [
                "- Automated ingestion pipelines for outbreak, weather, mobility, and health datasets.",
                "- Connector resilience: retries, timeout handling, and fallback providers.",
                "- Data quality checks for schema, missing values, and anomaly thresholds.",
                "- Historical warehouse/lake for trend analysis and audit replay.",
                "- Scheduled refresh jobs plus manual refresh controls for operations teams.",
            ],
        ),
        (
            "3. Forecasting and Analytics Features",
            [
                "- Model versioning and experiment tracking for reproducible updates.",
                "- Confidence intervals and uncertainty bands on all key forecasts.",
                "- Scenario simulation: best-case, expected-case, and worst-case planning.",
                "- Explainability panel that states what signals drove risk changes.",
                "- Drift monitoring and alerting when model performance degrades.",
            ],
        ),
        (
            "4. Web and Mobile User Experience",
            [
                "- Responsive UI for phone, tablet, and desktop.",
                "- Performance optimizations: caching, pagination, and lazy chart rendering.",
                "- Accessibility baseline: keyboard navigation, contrast, and readable typography.",
                "- Localization readiness: language, date/time, and timezone support.",
                "- Optional offline-capable behavior for unstable network environments.",
            ],
        ),
        (
            "5. Backend API Features",
            [
                "- Versioned APIs (for example /v1 and /v2) to prevent breaking clients.",
                "- Input validation and full OpenAPI documentation.",
                "- API authentication (JWT/API keys) and endpoint-level authorization.",
                "- Webhook framework for external systems and partner integrations.",
                "- Background job queue for long-running analytics and report generation.",
            ],
        ),
        (
            "6. Security, Compliance, and Governance",
            [
                "- HTTPS/TLS end-to-end with managed certificates.",
                "- Secrets management (no credentials hardcoded in source files).",
                "- Encryption at rest and in transit for sensitive data.",
                "- Audit logs for user actions, configuration changes, and data access.",
                "- Backups, retention policy, and disaster recovery procedures.",
            ],
        ),
        (
            "7. DevOps and Online Operations",
            [
                "- Cloud deployment architecture for frontend, API, and data store.",
                "- CI/CD pipelines for test, build, security scan, and deployment.",
                "- Separate dev, staging, and production environments.",
                "- Observability stack: logs, metrics, traces, uptime checks, and alerts.",
                "- Auto-scaling, load balancing, DNS, CDN, and WAF hardening.",
            ],
        ),
        (
            "8. Reliability and Quality",
            [
                "- Automated tests: unit, integration, and end-to-end flows.",
                "- Load testing and latency budgets for expected traffic growth.",
                "- Health endpoints and readiness checks for deployments.",
                "- Graceful degradation when external feeds fail or delay.",
                "- Incident response playbooks and clear on-call ownership.",
            ],
        ),
        (
            "9. What MVP in 2-4 weeks means",
            [
                "MVP means Minimum Viable Product: the smallest useful online version that real users can access and test safely.",
                "Typical MVP scope for this system: live dashboard, one secured login flow, core outbreak feed integration, basic forecasting view, and one alert channel.",
                "Goal of MVP: prove user value quickly, collect real feedback, and validate technical assumptions before large investment.",
                "In a 2-4 week window, focus on must-have workflows and avoid advanced customization until after validation.",
            ],
        ),
        (
            "10. Production Hardening phase",
            [
                "Production hardening means making the MVP robust, secure, and supportable for everyday operational use.",
                "Activities include: security controls, backup strategy, monitoring, test expansion, performance tuning, and failure recovery.",
                "Exit criteria: stable uptime, acceptable latency, clear runbooks, and confidence to support institutional users.",
            ],
        ),
        (
            "11. Scale-up phase",
            [
                "Scale-up means expanding usage, capacity, and feature depth after the hardened baseline is stable.",
                "Activities include: onboarding more users/regions, adding data sources, richer analytics, mobile enhancements, and cost optimization.",
                "Exit criteria: system performs well at higher load while maintaining governance, quality, and predictable operations.",
            ],
        ),
    ]

    write_docx(out, sections)
    print(f"Wrote: {out}")


if __name__ == "__main__":
    main()
