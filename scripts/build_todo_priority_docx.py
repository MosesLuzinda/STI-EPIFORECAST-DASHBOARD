"""
Build STI-EPI-FORECAST_Todo_Priority_Checklist.docx using only Python stdlib.
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
    parts.append(_p("STI-EPI-FORECAST - Prioritized Todo Checklist", bold=True))
    parts.append(_p(f"Generated: {date.today().isoformat()}"))
    parts.append(_p(""))
    parts.append(
        _p(
            "This document converts the master feature list into execution priorities: Now, Later, and Drop for current phase.",
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
  <dc:title>STI-EPI-FORECAST Prioritized Todo Checklist</dc:title>
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
    out = root / "STI-EPI-FORECAST_Todo_Priority_Checklist.docx"

    sections: list[tuple[str, list[str]]] = [
        (
            "1. NOW (execute in current phase)",
            [
                "- User authentication (email/password).",
                "- Role-based access (admin, analyst, viewer, developer).",
                "- Saved dashboards and CSV/PDF exports (basic version).",
                "- Reliable ingestion pipelines for outbreak and health data first.",
                "- API connectors with retries, timeout and fallback handling.",
                "- Data validation checks before forecasts and dashboard rendering.",
                "- Scheduled refresh jobs and manual refresh controls.",
                "- Forecast confidence intervals and uncertainty messaging.",
                "- Scenario simulation (best, expected, worst).",
                "- Fully responsive UI for mobile, tablet and desktop.",
                "- Fast loading pages with caching and chart optimization.",
                "- API versioning and validation (/v1 baseline with OpenAPI docs).",
                "- API keys/JWT and endpoint permissions.",
                "- HTTPS everywhere and secret management.",
                "- Encryption in transit and at rest.",
                "- Backups, retention rules and disaster recovery baseline.",
                "- Cloud deployment, CI/CD and dev/staging/prod separation.",
                "- Centralized logs, metrics, tracing and uptime monitoring.",
                "- Automated tests (unit + integration + smoke e2e).",
                "- Health checks/readiness probes and graceful degradation on feed failure.",
                "- Admin console baseline (users, roles, data source toggles).",
                "- Change logs and release notes.",
            ],
        ),
        (
            "2. LATER (phase 2 after stable online launch)",
            [
                "- OAuth and optional 2FA.",
                "- Multi-tenant support for multiple institutions.",
                "- Real-time alerts expanded to SMS and WhatsApp (start with email/webhook first).",
                "- Mobility and weather feeds after outbreak + health feeds are stable.",
                "- Model versioning and experiment tracking platform.",
                "- Explainability panels in richer detail (driver breakdown by signal family).",
                "- Drift detection and automated model-performance alerts.",
                "- Accessibility hardening for screen-reader compliance audits.",
                "- Localization (language and timezone packs).",
                "- Background job queue for heavy analytics/report generation.",
                "- Compliance expansion (formal governance pack, consent workflows).",
                "- Auto-scaling, load balancing, CDN and WAF optimization.",
                "- Incident runbooks and on-call process maturity upgrades.",
                "- Feature flags and workflow approvals for larger team operations.",
                "- Deep usage analytics and product funnel tracking.",
            ],
        ),
        (
            "3. DROP FOR NOW (not immediate priority)",
            [
                "- Offline-first PWA behavior for full dashboard.",
                "- Complex multi-step public content approval workflow if team is still small.",
                "- Full enterprise experimentation platform before data pipelines stabilize.",
                "- Advanced social-media firehose integrations before governance/legal approvals.",
            ],
        ),
        (
            "4. Why this prioritization",
            [
                "Focus first on reliability, security, and decision-quality outputs so users trust the system.",
                "Delay expensive complexity until core workflows and data quality are stable.",
                "Keep delivery speed high by reducing scope in the first online release.",
            ],
        ),
    ]

    write_docx(out, sections)
    print(f"Wrote: {out}")


if __name__ == "__main__":
    main()
